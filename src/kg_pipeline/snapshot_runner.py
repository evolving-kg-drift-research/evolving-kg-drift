"""Snapshot builder runner converting FactVersions into canonical snapshot datasets."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot
from .contracts import CONTRACT_VERSION
from .hashing import sha256_json
from .run import get_run_dir
from .storage import read_yaml, write_json_immutable, write_parquet_immutable

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def run_snapshots(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    fact_versions_path = run_dir / "tables" / "fact_versions.parquet"

    if not fact_versions_path.is_file():
        raise FileNotFoundError(f"Missing {fact_versions_path}. Run adjudication first.")

    table = pq.read_table(fact_versions_path)
    facts: list[FactVersion] = []

    for row in table.to_pylist():
        valid_from = _parse_ts(row.get("valid_from"))
        evidence_observed_at = _parse_ts(row.get("evidence_observed_at"))
        ingested_at_real = _parse_ts(row.get("ingested_at_real"))

        if not valid_from or not evidence_observed_at or not ingested_at_real:
            continue

        valid_to = _parse_ts(row.get("valid_to"))

        span_start = row.get("evidence_span_start")
        span_end = row.get("evidence_span_end")
        if span_start is None or span_end is None or span_start >= span_end:
            span_start = 0
            span_end = 1

        text_hash = row.get("evidence_text_hash") or "placeholder_hash"

        fact = FactVersion(
            fact_version_id=str(row["fact_version_id"]),
            logical_fact_id=str(row["logical_fact_id"]),
            subject_id=str(row["subject_id"]),
            relation_id=str(row["relation_id"]),
            object_id=str(row["object_id"]),
            valid_from=valid_from,
            valid_to=valid_to,
            evidence_observed_at=evidence_observed_at,
            ingested_at_real=ingested_at_real,
            supersedes_version_id=row.get("supersedes_version_id"),
            revision_type=str(row.get("revision_type", "creation")),
            source_id=str(row.get("source_id", "unknown")),
            source_url=str(row.get("source_url", "")),
            evidence_span_start=int(span_start),
            evidence_span_end=int(span_end),
            evidence_text_hash=str(text_hash),
            extractor_version=str(row.get("extractor_version", "")),
            entity_map_version=str(row.get("entity_map_version", "")),
            confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
            adjudication_status=row.get("adjudication_status"),
        )
        facts.append(fact)

    # Load cutoffs
    cutoffs_cfg_path = repo_root / "config" / "snapshot_cutoffs.yaml"
    cutoffs_list: list[dict[str, Any]] = []
    if cutoffs_cfg_path.is_file():
        cfg = read_yaml(cutoffs_cfg_path)
        if isinstance(cfg, dict) and "cutoffs" in cfg:
            cutoffs_list = cfg["cutoffs"]

    if not cutoffs_list:
        cutoffs_list = [
            {"snapshot_id": "S1", "cutoff_iso": "2021-01-01T00:00:00Z"},
            {"snapshot_id": "S2", "cutoff_iso": "2022-01-01T00:00:00Z"},
            {"snapshot_id": "S3", "cutoff_iso": "2023-01-01T00:00:00Z"},
        ]

    snapshots_summary: dict[str, Any] = {}

    for entry in cutoffs_list:
        snapshot_id = entry["snapshot_id"]
        cutoff_dt = _parse_ts(entry["cutoff_iso"])
        if not cutoff_dt:
            continue

        active_facts, semantic_sha256 = build_snapshot(facts, cutoff=cutoff_dt)

        triples = [
            {
                "schema_version": CONTRACT_VERSION,
                "subject": f.subject_id,
                "relation": f.relation_id,
                "object": f.object_id,
                "fact_version_id": f.fact_version_id,
                "logical_fact_id": f.logical_fact_id,
                "valid_from": f.valid_from.isoformat(),
                "valid_to": f.valid_to.isoformat() if f.valid_to else None,
                "evidence_observed_at": f.evidence_observed_at.isoformat(),
                "source_id": f.source_id,
            }
            for f in active_facts
        ]

        entities = {f.subject_id for f in active_facts} | {f.object_id for f in active_facts}
        relations = {f.relation_id for f in active_facts}

        snapshot_dir = run_dir / "snapshots" / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        triples_path = snapshot_dir / "triples.parquet"
        write_parquet_immutable(triples_path, "canonical_triples", triples)

        manifest = {
            "snapshot_id": snapshot_id,
            "cutoff_iso": cutoff_dt.isoformat(),
            "semantic_sha256": semantic_sha256,
            "num_triples": len(triples),
            "num_entities": len(entities),
            "num_relations": len(relations),
            "entities": sorted(entities),
            "relations": sorted(relations),
        }
        manifest_path = snapshot_dir / "manifest.json"
        write_json_immutable(manifest_path, manifest)

        snapshots_summary[snapshot_id] = {
            "cutoff_iso": cutoff_dt.isoformat(),
            "semantic_sha256": semantic_sha256,
            "num_triples": len(triples),
            "num_entities": len(entities),
            "num_relations": len(relations),
            "triples_path": str(triples_path.relative_to(run_dir)),
        }

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "total_fact_versions": len(facts),
        "snapshots": snapshots_summary,
    }
