"""Adjudication job converting claims to FactVersions."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import pyarrow.parquet as pq

from .adjudication import adjudicate_claims
from .contracts import CONTRACT_VERSION
from .run import get_run_dir
from .storage import write_parquet_immutable, read_yaml
from temporal.schema import Claim

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

    extracted_claims_path = run_dir / "tables" / "extracted_claims.parquet"
    if not extracted_claims_path.is_file():
        raise FileNotFoundError(f"Missing {extracted_claims_path}")

    # Load configuration and entities
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    res_cfg = config.get("resolved_config", {})
    entity_catalog = config.get("entity_catalog", {})
    ontology_rules = config.get("ontology_rules") or res_cfg.get("ontology", {}).get("relations", {})
    if not ontology_rules:
        ont_path = repo_root / "config" / "ontology.yaml"
        if ont_path.is_file():
            ont_data = read_yaml(ont_path)
            ontology_rules = ont_data.get("relations", {})

    # Load body_to_sources from document_memberships and retrievals if available (A06)
    memberships_path = run_dir / "tables" / "document_memberships.parquet"
    retrievals_path = run_dir / "tables" / "retrievals.parquet"
    body_to_sources: dict[str, list[dict[str, Any]]] = {}
    latest_retrieval_dt: datetime | None = None

    if memberships_path.is_file() and retrievals_path.is_file():
        m_table = pq.read_table(memberships_path)
        r_table = pq.read_table(retrievals_path)
        retrievals_by_id = {r["retrieval_id"]: r for r in r_table.to_pylist() if r.get("retrieval_id")}

        for mem in m_table.to_pylist():
            bv_id = mem.get("body_variant_id")
            if not bv_id:
                continue
            r_ids_raw = mem.get("retrieval_ids_json", "[]")
            try:
                r_ids = json.loads(r_ids_raw) if isinstance(r_ids_raw, str) else (r_ids_raw or [])
            except (json.JSONDecodeError, TypeError):
                r_ids = []

            for r_id in r_ids:
                ret = retrievals_by_id.get(r_id, {})
                ret_dt_str = ret.get("retrieved_at_real")
                if ret_dt_str:
                    try:
                        parsed_dt = datetime.fromisoformat(ret_dt_str)
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                        if latest_retrieval_dt is None or parsed_dt > latest_retrieval_dt:
                            latest_retrieval_dt = parsed_dt
                    except (ValueError, TypeError):
                        pass

                body_to_sources.setdefault(bv_id, []).append({
                    "publisher_source_id": ret.get("source_id", "unknown"),
                    "source_url": ret.get("final_url") or ret.get("requested_url", ""),
                    "retrieval_id": r_id,
                    "retrieved_at_real": ret.get("retrieved_at_real"),
                    "raw_blob_sha256": mem.get("raw_blob_sha256", ""),
                })

    table = pq.read_table(extracted_claims_path)

    claims = []
    observation_times: dict[str, datetime] = {}

    for row in table.to_pylist():
        bv_id = row.get("body_variant_id") or row.get("source_id", "")
        claim = Claim(
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
            is_speculative=row.get("is_speculative", False)
        )
        claims.append(claim)

        # Look up true observation time from body_to_sources (A07, A08)
        sources = body_to_sources.get(bv_id, [])
        for s in sources:
            ret_str = s.get("retrieved_at_real")
            if ret_str:
                try:
                    dt_val = datetime.fromisoformat(ret_str)
                    observation_times[claim.claim_id] = dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=timezone.utc)
                    break
                except (ValueError, TypeError):
                    continue

    ingested_at = latest_retrieval_dt or datetime.now(timezone.utc)

    accepted, review = adjudicate_claims(
        claims=claims,
        observation_times=observation_times,
        ingested_at=ingested_at,
        entity_catalog=entity_catalog,
        extractor_version="v1_local",
        entity_map_version="v1_mock",
        body_to_sources=body_to_sources,
        ontology_rules=ontology_rules,
    )

    fact_versions = [
        {
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": fact.fact_version_id,
            "logical_fact_id": fact.logical_fact_id,
            "subject_id": fact.subject_id,
            "relation_id": fact.relation_id,
            "object_id": fact.object_id,
            "valid_from": fact.valid_from.isoformat() if fact.valid_from else None,
            "valid_to": fact.valid_to.isoformat() if fact.valid_to else None,
            "evidence_observed_at": fact.evidence_observed_at.isoformat(),
            "ingested_at_real": fact.ingested_at_real.isoformat(),
            "supersedes_version_id": fact.supersedes_version_id,
            "revision_type": fact.revision_type,
            "source_id": fact.source_id,
            "source_url": fact.source_url,
            "evidence_span_start": fact.evidence_span_start,
            "evidence_span_end": fact.evidence_span_end,
            "evidence_text_hash": fact.evidence_text_hash,
            "extractor_version": fact.extractor_version,
            "entity_map_version": fact.entity_map_version,
            "confidence": fact.confidence,
            "adjudication_status": fact.adjudication_status
        }
        for fact in accepted
    ]

    write_parquet_immutable(
        run_dir / "tables" / "fact_versions.parquet",
        "fact_versions",
        fact_versions
    )

    # Could also write review_queue to a separate file or log it

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "adjudicated_facts_count": len(fact_versions),
        "review_queue_count": len(review)
    }
