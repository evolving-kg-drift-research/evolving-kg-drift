"""Adjudication job converting claims to FactVersions."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .adjudication import adjudicate_claims, validate_append_only_fact_versions
from .claims import resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id, utc_now_iso
from .run import create_stage_manifest, get_run_dir, load_run_manifest, resolve_run_table_path
from .locked_mode import scientific_locked_flag, validate_locked_baseline
from .storage import read_yaml, write_json_immutable, write_parquet_immutable
from temporal.schema import Claim, ContractError, EntityMappingVersion, FactVersion

logger = logging.getLogger(__name__)


def _parse_fact_datetime(value: Any, *, field: str, required: bool) -> datetime | None:
    if value is None or value == "":
        if required:
            raise ContractError(f"Previous FactVersion is missing {field}.")
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError(f"Previous FactVersion has invalid {field}.") from exc
    else:
        raise ContractError(f"Previous FactVersion has invalid {field} type.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"Previous FactVersion {field} must include an explicit timezone.")
    return parsed


def _fact_version_from_row(row: dict[str, Any]) -> FactVersion:
    supporting_claim_ids = row.get("supporting_claim_ids")
    if isinstance(supporting_claim_ids, str):
        try:
            supporting_claim_ids = json.loads(supporting_claim_ids)
        except json.JSONDecodeError as exc:
            raise ContractError("Previous FactVersion has invalid supporting_claim_ids.") from exc
    if not isinstance(supporting_claim_ids, list) or any(
        not isinstance(claim_id, str) or not claim_id for claim_id in supporting_claim_ids
    ):
        raise ContractError("Previous FactVersion has invalid supporting_claim_ids.")

    required_strings = (
        "fact_version_id", "logical_fact_id", "subject_id", "relation_id", "object_id",
        "revision_type", "source_id", "source_url", "evidence_text_hash",
    )
    missing = [name for name in required_strings if not isinstance(row.get(name), str) or not row[name]]
    if missing:
        raise ContractError(f"Previous FactVersion is missing required fields: {missing}")
    for name in ("evidence_span_start", "evidence_span_end"):
        if type(row.get(name)) is not int:
            raise ContractError(f"Previous FactVersion has invalid {name}.")

    return FactVersion(
        fact_version_id=row["fact_version_id"],
        logical_fact_id=row["logical_fact_id"],
        subject_id=row["subject_id"],
        relation_id=row["relation_id"],
        object_id=row["object_id"],
        valid_from=_parse_fact_datetime(row.get("valid_from"), field="valid_from", required=False),
        valid_to=_parse_fact_datetime(row.get("valid_to"), field="valid_to", required=False),
        evidence_observed_at=_parse_fact_datetime(
            row.get("evidence_observed_at"), field="evidence_observed_at", required=True
        ),
        ingested_at_real=_parse_fact_datetime(
            row.get("ingested_at_real"), field="ingested_at_real", required=True
        ),
        supersedes_version_id=row.get("supersedes_version_id"),
        revision_type=row["revision_type"],
        source_id=row["source_id"],
        source_url=row["source_url"],
        evidence_span_start=row["evidence_span_start"],
        evidence_span_end=row["evidence_span_end"],
        evidence_text_hash=row["evidence_text_hash"],
        extractor_version=row.get("extractor_version") or "",
        entity_map_version=row.get("entity_map_version") or "",
        confidence=row.get("confidence"),
        adjudication_status=row.get("adjudication_status"),
        supporting_claim_ids=tuple(supporting_claim_ids),
        temporal_status=row.get("temporal_status") or "VALID",
        evidence_time_basis=row.get("evidence_time_basis") or "",
        evidence_time_confidence=row.get("evidence_time_confidence"),
        evidence_time_source=row.get("evidence_time_source") or "",
    )


def _load_previous_fact_store(repo_root: Path, run_id: str) -> tuple[Path | None, list[dict[str, Any]], list[FactVersion]]:
    parent_run_id = load_run_manifest(repo_root, run_id).get("parent_run_id")
    if not parent_run_id:
        return None, [], []
    try:
        path = resolve_run_table_path(repo_root, parent_run_id, "fact_versions")
    except FileNotFoundError:
        return None, [], []
    rows = pq.read_table(path).to_pylist()
    facts = [_fact_version_from_row(row) for row in rows]
    return path, rows, facts


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

    # Load configuration for versioned ontology rules. The current entity catalog
    # is intentionally not used as historical mapping evidence.
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    res_cfg = config.get("resolved_config", {})
    if scientific_locked_flag(config):
        validate_locked_baseline(config, load_run_manifest(repo_root, run_id))
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

    mapping_path = resolve_run_table_path(repo_root, run_id, "entity_mapping_versions")
    if not mapping_path.is_file():
        raise ContractError(
            "Adjudication requires an artifact-backed entity mapping-decision history; "
            "the current entity catalog cannot stand in for historical decisions."
        )
    mapping_rows = pq.read_table(mapping_path).to_pylist()
    entity_mappings: list[EntityMappingVersion] = []
    for mapping_row in mapping_rows:
        mapping_time = mapping_row.get("mapping_available_at")
        if not mapping_time:
            raise ContractError("Mapping decision is missing mapping_available_at.")
        mapping_dt = datetime.fromisoformat(str(mapping_time).replace("Z", "+00:00"))
        entity_mappings.append(EntityMappingVersion(
            entity_mapping_id=mapping_row.get("entity_mapping_id") or "",
            mention=mapping_row.get("mention") or "",
            canonical_entity_id=mapping_row.get("canonical_entity_id") or "",
            mapping_available_at=mapping_dt,
            entity_map_version=mapping_row.get("entity_map_version") or "",
            supersedes_mapping_id=mapping_row.get("supersedes_mapping_id"),
            mapping_basis=mapping_row.get("mapping_basis") or "",
            mapping_confidence=float(mapping_row.get("mapping_confidence", 1.0)),
        ))

    previous_fact_path, previous_fact_rows, previous_facts = _load_previous_fact_store(
        repo_root, run_id
    )
    accepted, review_queue = adjudicate_claims(
        claims=claims,
        observation_times=observation_times,
        ingested_at=ingested_at,
        entity_catalog={},
        body_to_sources=body_to_sources,
        ontology_rules=ontology_rules,
        existing_facts=previous_facts,
        entity_mappings=entity_mappings,
    )

    fact_versions_rows = [dict(row) for row in previous_fact_rows]
    validate_append_only_fact_versions(previous_facts, [*previous_facts, *accepted])
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
            "decision_type": "PENDING_REVIEW",
            "rule_id": f"rule_{str(r.get('reason', '')).lower()}",
            "decider": "rule_engine_v1",
            "evaluated_at_real": utc_now_iso(),
            "reason": r.get("reason", "UNKNOWN"),
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
            {"table": "entity_mapping_versions", "path": str(mapping_path)},
            *(
                [{"table": "fact_versions", "path": str(previous_fact_path)}]
                if previous_fact_path is not None else []
            ),
        ],
        output_artifacts=[
            {"table": "fact_versions", "path": str(run_dir / "tables" / "fact_versions.parquet"), "count": len(fact_versions_rows)},
            {"table": "adjudication_decisions", "path": str(run_dir / "tables" / "adjudication_decisions.parquet"), "count": len(decisions_rows)},
        ],
        conservation_metrics={
            "claims_count": len(claims),
            "accepted_facts_count": len(accepted),
            "review_queue_count": len(review_queue),
            "decisions_count": len(decisions_rows),
            "adjudication_engine_version": "adjudication-v2-pending-conflicts",
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
