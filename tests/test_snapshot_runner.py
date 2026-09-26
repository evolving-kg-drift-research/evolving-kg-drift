from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from kg_pipeline.contracts import CONTRACT_VERSION
from kg_pipeline.run import init_run
from kg_pipeline.snapshot_runner import run_snapshots
from kg_pipeline.storage import write_parquet_immutable
from kge.adapter import load_snapshots_from_run, load_snapshot_from_parquet


def dt(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


def test_snapshot_runner_and_adapter(tmp_path: Path):
    run_id = "test_snap_run"
    init_run(tmp_path, run_id, mode="inventory")
    run_dir = tmp_path / "runs" / run_id

    # Create dummy fact_versions.parquet
    facts = [
        {
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": "fv1",
            "logical_fact_id": "lf1",
            "subject_id": "Apple",
            "relation_id": "is_CEO_of",
            "object_id": "Tim_Cook",
            "valid_from": dt(2020, 1, 1).isoformat(),
            "valid_to": None,
            "evidence_observed_at": dt(2020, 1, 1).isoformat(),
            "ingested_at_real": dt(2025, 1, 1).isoformat(),
            "supersedes_version_id": None,
            "revision_type": "creation",
            "source_id": "trusted_source",
            "source_url": "https://example.com/apple",
            "evidence_span_start": 0,
            "evidence_span_end": 10,
            "evidence_text_hash": "hash1",
            "extractor_version": "v1",
            "entity_map_version": "v1",
            "confidence": 0.95,
            "adjudication_status": "AUTO_ACCEPTED",
        },
        {
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": "fv2",
            "logical_fact_id": "lf2",
            "subject_id": "Microsoft",
            "relation_id": "is_CEO_of",
            "object_id": "Satya_Nadella",
            "valid_from": dt(2021, 6, 1).isoformat(),
            "valid_to": None,
            "evidence_observed_at": dt(2021, 6, 1).isoformat(),
            "ingested_at_real": dt(2025, 1, 1).isoformat(),
            "supersedes_version_id": None,
            "revision_type": "creation",
            "source_id": "trusted_source",
            "source_url": "https://example.com/ms",
            "evidence_span_start": 0,
            "evidence_span_end": 10,
            "evidence_text_hash": "hash2",
            "extractor_version": "v1",
            "entity_map_version": "v1",
            "confidence": 0.95,
            "adjudication_status": "AUTO_ACCEPTED",
        },
        {
            "schema_version": CONTRACT_VERSION,
            "fact_version_id": "fv3",
            "logical_fact_id": "lf3",
            "subject_id": "Google",
            "relation_id": "is_CEO_of",
            "object_id": "Sundar_Pichai",
            "valid_from": dt(2022, 6, 1).isoformat(),
            "valid_to": None,
            "evidence_observed_at": dt(2022, 6, 1).isoformat(),
            "ingested_at_real": dt(2025, 1, 1).isoformat(),
            "supersedes_version_id": None,
            "revision_type": "creation",
            "source_id": "trusted_source",
            "source_url": "https://example.com/google",
            "evidence_span_start": 0,
            "evidence_span_end": 10,
            "evidence_text_hash": "hash3",
            "extractor_version": "v1",
            "entity_map_version": "v1",
            "confidence": 0.95,
            "adjudication_status": "AUTO_ACCEPTED",
        },
    ]

    write_parquet_immutable(run_dir / "tables" / "fact_versions.parquet", "fact_versions", facts)

    # Write cutoffs
    cutoffs_cfg = {
        "cutoffs": [
            {"snapshot_id": "S1", "cutoff_iso": "2020-06-01T00:00:00Z"},
            {"snapshot_id": "S2", "cutoff_iso": "2021-12-31T00:00:00Z"},
            {"snapshot_id": "S3", "cutoff_iso": "2023-01-01T00:00:00Z"},
        ]
    }
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    import yaml
    (tmp_path / "config" / "snapshot_cutoffs.yaml").write_text(yaml.safe_dump(cutoffs_cfg), encoding="utf-8")

    # Run snapshots
    summary = run_snapshots(tmp_path, run_id)
    assert summary["status"] == "COMPLETED"
    assert summary["total_fact_versions"] == 3

    assert (run_dir / "snapshots" / "S1" / "triples.parquet").is_file()
    assert (run_dir / "snapshots" / "S2" / "triples.parquet").is_file()
    assert (run_dir / "snapshots" / "S3" / "triples.parquet").is_file()

    # Load via KGE Adapter
    datasets = load_snapshots_from_run(tmp_path, run_id)
    assert len(datasets) == 3
    assert "S1" in datasets
    assert "S2" in datasets
    assert "S3" in datasets

    # S1 should have 1 triple (Apple)
    assert len(datasets["S1"].triples) == 1
    # S2 should have 2 triples (Apple, Microsoft)
    assert len(datasets["S2"].triples) == 2
    # S3 should have 3 triples (Apple, Microsoft, Google)
    assert len(datasets["S3"].triples) == 3

    # Check entities and mapping hash
    assert datasets["S1"].entities == ["Apple", "Tim_Cook"]
    assert len(datasets["S1"].compute_mapping_hash()) == 64
