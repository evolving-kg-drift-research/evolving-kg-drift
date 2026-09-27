"""Adjudication job converting claims to FactVersions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .claims import resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id
from .run import get_run_dir, resolve_run_table_path
from .storage import read_yaml, write_parquet_immutable
from temporal.schema import Claim, ContractError

logger = logging.getLogger(__name__)

def run_adjudication(repo_root: Path, run_id: str, *, enforce_gate_a: bool = False) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)

    if enforce_gate_a:
        from .gates import latest_gate_a_report
        gate_report = latest_gate_a_report(run_dir)
        if not gate_report:
            raise PermissionError(f"Adjudication blocked: Gate A has not been evaluated for run {run_id}")
        if gate_report.get("status") != "PASS":
            raise PermissionError(f"Adjudication blocked: Gate A status is {gate_report.get('status')}, expected PASS")

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
            source_id=bv_id,
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

    # No approved input currently supplies evidence_observed_at or an independent
    # ingestion event. Retrieval timestamps are project provenance, not known-time.
    if claims:
        raise ContractError(
            "Adjudication is blocked: approved evidence_observed_at and ingested_at_real inputs "
            "are unavailable; retrieved_at_real cannot substitute for either field."
        )

    write_parquet_immutable(
        run_dir / "tables" / "fact_versions.parquet",
        "fact_versions",
        [],
    )
    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "adjudicated_facts_count": 0,
        "review_queue_count": 0,
    }
