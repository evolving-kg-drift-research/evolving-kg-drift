"""Adjudication job converting claims to FactVersions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import pyarrow.parquet as pq

from .adjudication import adjudicate_claims
from .run import get_run_dir
from .storage import write_parquet_immutable, read_yaml
from temporal.schema import Claim

logger = logging.getLogger(__name__)

def run_adjudication(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    extracted_claims_path = run_dir / "tables" / "extracted_claims.parquet"
    if not extracted_claims_path.is_file():
        raise FileNotFoundError(f"Missing {extracted_claims_path}")

    # Load configuration and entities
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    entity_catalog = config.get("entity_catalog", {})

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
            is_speculative=row.get("is_speculative", False)
        )
        claims.append(claim)

        # Simplification: use current time as observation time for demonstration,
        # in a real pipeline we would fetch the true observation time of the source_id
        observation_times[claim.claim_id] = datetime.now(timezone.utc)

    ingested_at = datetime.now(timezone.utc)

    accepted, review = adjudicate_claims(
        claims=claims,
        observation_times=observation_times,
        ingested_at=ingested_at,
        entity_catalog=entity_catalog,
        extractor_version="v1_local",
        entity_map_version="v1_mock"
    )

    fact_versions = [
        {
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
