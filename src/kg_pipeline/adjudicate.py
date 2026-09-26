"""Adjudication job converting claims to FactVersions with verified temporal provenance."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from temporal.schema import Claim
from .adjudication import adjudicate_claims, parse_extracted_date
from .contracts import CONTRACT_VERSION
from .run import get_run_dir, load_run_manifest
from .storage import read_yaml, write_parquet_immutable

logger = logging.getLogger(__name__)


def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def run_adjudication(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    manifest = load_run_manifest(repo_root, run_id)

    extracted_claims_path = run_dir / "tables" / "extracted_claims.parquet"
    if not extracted_claims_path.is_file():
        raise FileNotFoundError(f"Missing {extracted_claims_path}")

    # Load configuration and entities
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    entity_catalog = config.get("entity_catalog", {})

    # Load source trust policy
    trusted_sources: set[str] = set()
    sources_yaml_path = repo_root / "config" / "sources.yaml"
    if sources_yaml_path.is_file():
        sources_cfg = read_yaml(sources_yaml_path)
        if isinstance(sources_cfg, dict) and "sources" in sources_cfg:
            trusted_sources.update(sources_cfg["sources"].keys())

    if "trusted_sources" in config and isinstance(config["trusted_sources"], list):
        trusted_sources.update(config["trusted_sources"])
    if "whitelist_sources" in config and isinstance(config["whitelist_sources"], list):
        trusted_sources.update(config["whitelist_sources"])

    # Fallback default timestamp from run manifest
    manifest_ts = manifest.get("created_at_real")
    if manifest_ts:
        default_observed_at = _parse_iso_ts(manifest_ts) or datetime(2026, 1, 1, tzinfo=timezone.utc)
    else:
        default_observed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # Recover timestamps and provenance from inventory tables if present
    retrievals_path = run_dir / "tables" / "retrievals.parquet"
    memberships_path = run_dir / "tables" / "document_memberships.parquet"

    retrieval_timestamps: dict[str, datetime] = {}
    source_to_timestamps: dict[str, list[datetime]] = {}
    trusted_retrieval_sources: set[str] = set()

    if retrievals_path.is_file():
        retrievals_table = pq.read_table(retrievals_path)
        for r_row in retrievals_table.to_pylist():
            r_id = r_row.get("retrieval_id")
            s_id = r_row.get("source_id")
            event_ts_str = r_row.get("recorded_event_at") or r_row.get("retrieved_at_real")
            event_ts = _parse_iso_ts(event_ts_str)
            if r_id and event_ts:
                retrieval_timestamps[r_id] = event_ts
            if s_id and event_ts:
                source_to_timestamps.setdefault(s_id, []).append(event_ts)
            if r_row.get("strict_source_input_eligible") or r_row.get("provenance_status") == "VERIFIED_ACQUISITION_EVIDENCE":
                if s_id:
                    trusted_retrieval_sources.add(s_id)

    body_to_timestamps: dict[str, list[datetime]] = {}
    body_to_sources: dict[str, set[str]] = {}

    if memberships_path.is_file():
        memberships_table = pq.read_table(memberships_path)
        for m_row in memberships_table.to_pylist():
            b_id = m_row.get("body_variant_id")
            r_ids_json = m_row.get("retrieval_ids_json")
            if b_id and r_ids_json:
                try:
                    r_ids = json.loads(r_ids_json)
                    for r_id in r_ids:
                        if r_id in retrieval_timestamps:
                            body_to_timestamps.setdefault(b_id, []).append(retrieval_timestamps[r_id])
                except (json.JSONDecodeError, TypeError):
                    pass

    table = pq.read_table(extracted_claims_path)
    claims = []
    observation_times = {}

    for row in table.to_pylist():
        claim = Claim(
            claim_id=row["claim_id"],
            source_id=row["source_id"],
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
        )
        claims.append(claim)

        # Resolve observation time with strict precedence:
        # 1. Timestamps associated with the body variant
        # 2. Timestamps associated with the source_id in retrievals
        # 3. Fallback to manifest creation timestamp
        observed_at = None
        if claim.source_id in body_to_timestamps and body_to_timestamps[claim.source_id]:
            observed_at = min(body_to_timestamps[claim.source_id])
        elif claim.source_id in source_to_timestamps and source_to_timestamps[claim.source_id]:
            observed_at = min(source_to_timestamps[claim.source_id])
        elif claim.valid_from_extracted:
            extracted_dt = _parse_iso_ts(claim.valid_from_extracted)
            if extracted_dt:
                observed_at = extracted_dt

        if observed_at is None:
            observed_at = default_observed_at

        observation_times[claim.claim_id] = observed_at

        # If source is a body_variant_id that originated from trusted retrieval sources, trust it
        if claim.source_id in body_to_sources:
            if any(s in trusted_sources or s in trusted_retrieval_sources for s in body_to_sources[claim.source_id]):
                trusted_sources.add(claim.source_id)
        elif claim.source_id in trusted_retrieval_sources:
            trusted_sources.add(claim.source_id)

    ingested_at = default_observed_at

    accepted, review = adjudicate_claims(
        claims=claims,
        observation_times=observation_times,
        ingested_at=ingested_at,
        entity_catalog=entity_catalog,
        extractor_version="v1_local",
        entity_map_version="v1_mock",
        trusted_sources=trusted_sources if trusted_sources else None,
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
            "adjudication_status": fact.adjudication_status,
        }
        for fact in accepted
    ]

    write_parquet_immutable(
        run_dir / "tables" / "fact_versions.parquet",
        "fact_versions",
        fact_versions,
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "adjudicated_facts_count": len(fact_versions),
        "review_queue_count": len(review),
    }
