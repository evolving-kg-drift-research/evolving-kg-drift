"""Adjudication job converting claims to FactVersions."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .adjudication import adjudicate_claims
from .claims import resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id, utc_now_iso
from .run import create_stage_manifest, get_run_dir, resolve_run_table_path
from .storage import read_yaml, write_json_immutable, write_parquet_immutable
from temporal.schema import Claim, ContractError

logger = logging.getLogger(__name__)


def _approved_temporal_inputs(run_dir: Path, claims: list[Claim]) -> tuple[dict[str, datetime], datetime]:
    """Stage 4.10 has no verified artifact contract in the current repository."""
    raise ContractError(
        "Adjudication is blocked: approved evidence_observed_at, evidence_time_basis, "
        "evidence_time_confidence and independent ingested_at_real inputs are unavailable; "
        "retrieved_at_real or archive_datetime cannot substitute for those clocks. "
        f"Run {run_dir.name} has {len(claims)} claims awaiting temporal normalization."
    )

def run_adjudication(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)

    from .gates import require_gate_a
    gate_a_ref = require_gate_a(repo_root, run_id)
    from .contract_authority import require_schema_compatible
    require_schema_compatible(repo_root, ["fact_versions", "adjudication_decisions", "entity_mapping_versions"])

    extracted_claims_path = resolve_run_table_path(repo_root, run_id, "extracted_claims")
    if not extracted_claims_path.is_file():
        raise FileNotFoundError(f"Missing {extracted_claims_path}")

    # Load configuration and entities
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    res_cfg = config.get("resolved_config", {})
    entity_catalog = config.get("entity_catalog") or res_cfg.get("entity_catalog", {})
    if not entity_catalog:
        cat_path = repo_root / "config" / "entity_catalog.yaml"
        if cat_path.is_file():
            try:
                loaded_cat = read_yaml(cat_path)
                if isinstance(loaded_cat, dict):
                    entity_catalog = loaded_cat
            except Exception:
                entity_catalog = {}
    ontology_rules = config.get("ontology_rules") or res_cfg.get("ontology", {}).get("relations", {})
    if not ontology_rules:
        ont_path = repo_root / "config" / "ontology.yaml"
        if ont_path.is_file():
            ont_data = read_yaml(ont_path)
            ontology_rules = ont_data.get("relations", {})

    table = pq.read_table(extracted_claims_path)
    claim_rows = table.to_pylist()
    claims = []
    for row in claim_rows:
        bv_id = row.get("body_variant_id")
        if not bv_id:
            raise ContractError(f"Extracted claim {row.get('claim_id')} has no body_variant_id.")
        claims.append(Claim(
            claim_id=row["claim_id"],
            body_variant_id=bv_id,
            source_id=row.get("source_id") or bv_id,
            subject_mention=row["subject_mention"],
            relation_name=row["relation_name"],
            object_mention=row["object_mention"],
            evidence_span_start=row["evidence_span_start"],
            evidence_span_end=row["evidence_span_end"],
            evidence_text_hash=row["evidence_text_hash"],
            valid_from_extracted=row.get("valid_from_extracted"),
            valid_to_extracted=row.get("valid_to_extracted"),
            is_negative=row.get("is_negative", False),
            is_speculative=row.get("is_speculative", False),
        ))

    provenance_path = resolve_run_table_path(repo_root, run_id, "claim_provenance")
    memberships_path = resolve_run_table_path(repo_root, run_id, "document_memberships")
    retrievals_path = resolve_run_table_path(repo_root, run_id, "retrievals")
    source_versions_path = resolve_run_table_path(repo_root, run_id, "source_versions")
    for table_name, path in (
        ("claim_provenance", provenance_path),
        ("document_memberships", memberships_path),
        ("retrievals", retrievals_path),
        ("source_versions", source_versions_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Missing required {table_name} provenance table: {path}")

    provenance_rows = pq.read_table(provenance_path).to_pylist()
    membership_rows = pq.read_table(memberships_path).to_pylist()
    retrieval_rows = pq.read_table(retrievals_path).to_pylist()
    source_version_rows = pq.read_table(source_versions_path).to_pylist()
    expected_provenance = resolve_claim_provenance(
        claims=claims,
        memberships=membership_rows,
        retrievals=retrieval_rows,
        source_versions=source_version_rows,
    )
    expected_rows = []
    for prov in expected_provenance:
        expected_rows.append({
            "schema_version": CONTRACT_VERSION,
            "claim_id": prov.claim_id,
            "membership_id": prov.membership_id,
            "source_version_id": prov.source_version_id,
            "retrieval_id": prov.retrieval_id,
            "raw_blob_sha256": prov.raw_blob_sha256,
            "publisher_source_id": prov.publisher_source_id,
            "source_url": prov.source_url,
            "provenance_id": stable_id("claimprovenance", {
                "claim_id": prov.claim_id,
                "membership_id": prov.membership_id,
                "source_version_id": prov.source_version_id,
                "retrieval_id": prov.retrieval_id,
                "raw_blob_sha256": prov.raw_blob_sha256,
            }),
        })
    actual_by_id = {row.get("provenance_id"): row for row in provenance_rows}
    if len(actual_by_id) != len(provenance_rows):
        raise ContractError("Duplicate provenance_id in claim_provenance table.")
    expected_by_id = {row["provenance_id"]: row for row in expected_rows}
    if actual_by_id != expected_by_id:
        raise ContractError("claim_provenance does not match extracted claim IDs and upstream provenance links.")

    # Keep source links separate from the temporal-normalization decision.
    retrieval_by_id = {r["retrieval_id"]: r for r in retrieval_rows if r.get("retrieval_id")}
    body_to_sources: dict[str, list[dict[str, Any]]] = {}
    claim_by_id = {c.claim_id: c for c in claims}

    for prov in provenance_rows:
        cid = prov.get("claim_id")
        r_id = prov.get("retrieval_id")
        r = retrieval_by_id.get(r_id) if r_id else None
        c = claim_by_id.get(cid) if cid else None
        if c:
            body_to_sources.setdefault(c.body_variant_id, []).append({
                "publisher_source_id": prov.get("publisher_source_id"),
                "source_url": prov.get("source_url"),
                "retrieved_at_real": r.get("retrieved_at_real") if r else None,
            })

    observation_times, ingested_at = _approved_temporal_inputs(run_dir, claims)

    accepted, review_queue = adjudicate_claims(
        claims=claims,
        observation_times=observation_times,
        ingested_at=ingested_at,
        entity_catalog=entity_catalog,
        body_to_sources=body_to_sources,
        ontology_rules=ontology_rules,
    )

    fact_versions_rows = []
    for f in accepted:
        fact_versions_rows.append({
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": f.fact_version_id,
            "supporting_claim_ids": list(f.supporting_claim_ids),
            "logical_fact_id": f.logical_fact_id,
            "subject_id": f.subject_id,
            "relation_id": f.relation_id,
            "object_id": f.object_id,
            "valid_from": f.valid_from.isoformat() if f.valid_from else None,
            "valid_to": f.valid_to.isoformat() if f.valid_to else None,
            "evidence_observed_at": f.evidence_observed_at.isoformat(),
            "ingested_at_real": f.ingested_at_real.isoformat(),
            "supersedes_version_id": f.supersedes_version_id,
            "revision_type": f.revision_type,
            "source_id": f.source_id,
            "source_url": f.source_url,
            "evidence_span_start": f.evidence_span_start,
            "evidence_span_end": f.evidence_span_end,
            "evidence_text_hash": f.evidence_text_hash,
            "extractor_version": f.extractor_version,
            "entity_map_version": f.entity_map_version,
            "confidence": f.confidence,
            "adjudication_status": f.adjudication_status,
        })

    decisions_rows = []
    for f in accepted:
        for cid in f.supporting_claim_ids:
            decisions_rows.append({
                "schema_version": CONTRACT_VERSION,
                "decision_id": f"dec_acc_{cid}",
                "claim_id": cid,
                "fact_version_id": f.fact_version_id,
                "decision_type": "ACCEPTED",
                "rule_id": "rule_auto_accepted",
                "decider": "rule_engine_v1",
                "evaluated_at_real": utc_now_iso(),
                "reason": "Entity resolved and observation time proven",
            })
    for r in review_queue:
        cid = r.get("claim_id")
        prov_fact = r.get("provisional_fact")
        fact_vid = getattr(prov_fact, "fact_version_id", "") if prov_fact is not None else ""
        decisions_rows.append({
            "schema_version": CONTRACT_VERSION,
            "decision_id": f"dec_rej_{cid}",
            "claim_id": cid,
            "fact_version_id": fact_vid,
            "decision_type": "REJECTED_TO_REVIEW",
            "rule_id": f"rule_{str(r.get('reason', '')).lower()}",
            "decider": "rule_engine_v1",
            "evaluated_at_real": utc_now_iso(),
            "reason": r.get("reason", "UNKNOWN"),
        })

    catalog_available_at = (
        config.get("entity_catalog_available_at")
        or res_cfg.get("entity_catalog_available_at")
    )
    if entity_catalog and not catalog_available_at:
        raise ContractError("Entity catalog mapping_available_at needs independent provenance")
    entity_mapping_rows = []
    for idx, (mention, canonical_id) in enumerate(sorted(entity_catalog.items())):
        entity_mapping_rows.append({
            "schema_version": CONTRACT_VERSION,
            "entity_mapping_id": f"ent_map_{idx}_{stable_id('entity', {'mention': mention, 'id': canonical_id})[:12]}",
            "mention": mention,
            "canonical_entity_id": canonical_id,
            "mapping_available_at": catalog_available_at,
            "entity_map_version": "ticket_a_v1",
            "supersedes_mapping_id": None,
            "mapping_basis": "entity_catalog",
            "mapping_confidence": 1.0,
        })

    write_parquet_immutable(
        run_dir / "tables" / "fact_versions.parquet",
        "fact_versions",
        fact_versions_rows,
    )
    write_parquet_immutable(
        run_dir / "tables" / "adjudication_decisions.parquet",
        "adjudication_decisions",
        decisions_rows,
    )
    write_parquet_immutable(
        run_dir / "tables" / "entity_mappings.parquet",
        "entity_mappings",
        entity_mapping_rows,
    )

    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    write_json_immutable(
        run_dir / "reports" / "adjudication_review_queue.json",
        {
            "schema_version": CONTRACT_VERSION,
            "run_id": run_id,
            "created_at_real": utc_now_iso(),
            "review_queue_count": len(review_queue),
            "review_records": [
                {"claim_id": r.get("claim_id"), "reason": r.get("reason")}
                for r in review_queue
            ],
        },
    )

    create_stage_manifest(
        repo_root,
        run_id,
        "adjudication",
        input_artifacts=[
            {"table": "extracted_claims", "path": str(extracted_claims_path)},
            {"table": "claim_provenance", "path": str(provenance_path)},
            {"table": "document_memberships", "path": str(memberships_path)},
            {"table": "retrievals", "path": str(retrievals_path)},
            {"table": "source_versions", "path": str(source_versions_path)},
        ],
        output_artifacts=[
            {"table": "fact_versions", "path": str(run_dir / "tables" / "fact_versions.parquet"), "count": len(fact_versions_rows)},
            {"table": "adjudication_decisions", "path": str(run_dir / "tables" / "adjudication_decisions.parquet"), "count": len(decisions_rows)},
            {"table": "entity_mappings", "path": str(run_dir / "tables" / "entity_mappings.parquet"), "count": len(entity_mapping_rows)},
        ],
        conservation_metrics={
            "claims_count": len(claims),
            "accepted_facts_count": len(accepted),
            "review_queue_count": len(review_queue),
            "decisions_count": len(decisions_rows),
        },
        gate_a_ref=gate_a_ref,
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "adjudicated_facts_count": len(accepted),
        "review_queue_count": len(review_queue),
        "decisions_count": len(decisions_rows),
    }
