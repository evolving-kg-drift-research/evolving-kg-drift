"""Adjudication job converting claims to FactVersions with immutable artifact checks."""

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

    fact_versions_path = run_dir / "tables" / "fact_versions.parquet"
    if fact_versions_path.is_file():
        logger.info(f"Reading existing fact_versions.parquet from {fact_versions_path}")
        fact_versions_table = pq.read_table(fact_versions_path)
        return {
            "status": "COMPLETED",
            "run_id": run_id,
            "adjudicated_facts_count": len(fact_versions_table),
            "source": "immutable_artifact_cache"
        }

    # Load configuration and entities
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    entity_catalog = config.get("entity_catalog", {})

    # Map body variants to earliest true temporal acquisition/archive time
    memberships_path = run_dir / "tables" / "document_memberships.parquet"
    retrievals_path = run_dir / "tables" / "retrievals.parquet"
    bv_to_time = {}
    if memberships_path.is_file() and retrievals_path.is_file():
        import json
        ret = pq.read_table(retrievals_path)
        ret_archive = {r["retrieval_id"]: r["archive_datetime"] for r in ret.to_pylist() if r.get("archive_datetime")}
        ret_retrieved = {r["retrieval_id"]: r["retrieved_at_real"] for r in ret.to_pylist() if r.get("retrieved_at_real")}

        dm = pq.read_table(memberships_path)
        for r in dm.to_pylist():
            bv = r["body_variant_id"]
            ret_ids = json.loads(r["retrieval_ids_json"]) if r["retrieval_ids_json"] else []
            arch_times = [ret_archive[rid] for rid in ret_ids if rid in ret_archive]
            if arch_times:
                bv_to_time[bv] = min(arch_times)
            else:
                crawl_times = [ret_retrieved[rid] for rid in ret_ids if rid in ret_retrieved]
                if crawl_times:
                    bv_to_time[bv] = min(crawl_times)

    table = pq.read_table(extracted_claims_path)

    claims = []
    observation_times = {}
    now_utc = datetime.now(timezone.utc)

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
        doc_time_str = bv_to_time.get(claim.source_id)
        if doc_time_str:
            observation_times[claim.claim_id] = datetime.fromisoformat(doc_time_str)
        else:
            observation_times[claim.claim_id] = now_utc

        # Fallback entity catalog auto-resolution using sha256
        s_m = claim.subject_mention.strip()
        o_m = claim.object_mention.strip()
        if s_m and s_m not in entity_catalog:
            from .hashing import sha256_text
            entity_catalog[s_m] = f"ent_{sha256_text(s_m.lower())[:8]}"
        if o_m and o_m not in entity_catalog:
            from .hashing import sha256_text
            entity_catalog[o_m] = f"ent_{sha256_text(o_m.lower())[:8]}"

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
            "schema_version": "ticket_a_v1",
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
        fact_versions_path,
        "fact_versions",
        fact_versions
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "adjudicated_facts_count": len(fact_versions),
        "review_queue_count": len(review)
    }
