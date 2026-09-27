from pathlib import Path

import pytest

from kg_pipeline import snapshot_runner
from kg_pipeline.hashing import stable_id


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def to_pylist(self):
        return self.rows


def valid_fact_row():
    return {
        "fact_version_id": "fv_1",
        "supporting_claim_ids": ["claim_1"],
        "logical_fact_id": "lf_1",
        "subject_id": "entity_a",
        "relation_id": "REL",
        "object_id": "entity_b",
        "valid_from": "2020-01-01T00:00:00Z",
        "valid_to": None,
        "evidence_observed_at": "2020-02-01T00:00:00Z",
        "ingested_at_real": "2020-02-02T00:00:00Z",
        "supersedes_version_id": None,
        "revision_type": "creation",
        "source_id": "publisher_1",
        "source_url": "https://publisher.test/item",
        "evidence_span_start": 10,
        "evidence_span_end": 20,
        "evidence_text_hash": "sha256:evidence",
        "extractor_version": "extractor-v1",
        "entity_map_version": "entity-map-v1",
        "confidence": 0.9,
        "adjudication_status": "AUTO_ACCEPTED",
    }


def setup_snapshot_io(monkeypatch, tmp_path: Path, rows):
    run_dir = tmp_path / "runs" / "run1"
    run_dir.mkdir(parents=True)
    paths = {}
    fact_path = run_dir / "tables" / "fact_versions.parquet"
    fact_path.parent.mkdir()
    fact_path.touch()
    provenance_path = run_dir / "tables" / "claim_provenance.parquet"
    provenance_path.touch()
    digest = "a" * 64
    expected_provenance_id = stable_id("claimprovenance", {
        "claim_id": "claim_1",
        "membership_id": "membership_1",
        "source_version_id": "sv_1",
        "retrieval_id": "retrieval_1",
        "raw_blob_sha256": digest,
    })
    provenance_rows = [{
        "provenance_id": expected_provenance_id,
        "claim_id": "claim_1",
        "membership_id": "membership_1",
        "source_version_id": "sv_1",
        "retrieval_id": "retrieval_1",
        "raw_blob_sha256": digest,
        "publisher_source_id": "publisher_1",
        "source_url": "https://publisher.test/item",
    }]
    claim_rows = [{
        "claim_id": "claim_1",
        "body_variant_id": "bv_1",
        "subject_mention": "Alpha",
        "relation_name": "REL",
        "object_mention": "Beta",
        "evidence_span_start": 10,
        "evidence_span_end": 20,
        "evidence_text_hash": "sha256:evidence",
    }]
    membership_rows = [{
        "membership_id": "membership_1",
        "raw_blob_sha256": digest,
        "body_variant_id": "bv_1",
        "retrieval_ids_json": '["retrieval_1"]',
    }]
    retrieval_rows = [{
        "retrieval_id": "retrieval_1",
        "raw_blob_sha256": digest,
        "source_id": "publisher_1",
        "requested_url": "https://publisher.test/item",
        "final_url": "https://publisher.test/item",
    }]
    source_version_rows = [{
        "source_version_id": "sv_1",
        "retrieval_id": "retrieval_1",
        "raw_blob_sha256": digest,
    }]
    table_rows = {
        "fact_versions": rows,
        "claim_provenance": provenance_rows,
        "extracted_claims": claim_rows,
        "document_memberships": membership_rows,
        "retrievals": retrieval_rows,
        "source_versions": source_version_rows,
    }
    for name in table_rows:
        path = run_dir / "tables" / f"{name}.parquet"
        path.touch()
        paths[name] = path
    path_to_name = {path: name for name, path in paths.items()}
    monkeypatch.setattr(
        snapshot_runner,
        "resolve_run_table_path",
        lambda repo_root, run_id, name: paths.get(name, run_dir / "tables" / f"{name}.parquet"),
    )
    monkeypatch.setattr(
        snapshot_runner.pq,
        "read_table",
        lambda path: FakeTable(table_rows[path_to_name[path]]),
    )
    writes = []
    monkeypatch.setattr(snapshot_runner, "write_parquet_immutable", lambda *args: writes.append(args))
    monkeypatch.setattr(snapshot_runner, "write_yaml_immutable", lambda *args: writes.append(args))
    monkeypatch.setattr(snapshot_runner, "create_stage_manifest", lambda *args, **kwargs: {})
    from kg_pipeline import gates
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: {"gate": "A"})
    return run_dir, writes


@pytest.mark.parametrize(
    "field",
    [
        "evidence_observed_at",
        "ingested_at_real",
        "subject_id",
        "relation_id",
        "object_id",
        "source_id",
        "evidence_span_start",
        "evidence_span_end",
        "evidence_text_hash",
        "extractor_version",
        "entity_map_version",
    ],
)
def test_snapshot_runner_rejects_missing_fact_fields(monkeypatch, tmp_path, field):
    row = valid_fact_row()
    del row[field]
    _, writes = setup_snapshot_io(monkeypatch, tmp_path, [row])

    with pytest.raises(ValueError, match=field):
        snapshot_runner.run_snapshot(
            tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
        )
    assert writes == []


def test_snapshot_runner_rejects_naive_timestamps(monkeypatch, tmp_path):
    row = valid_fact_row()
    row["evidence_observed_at"] = "2020-02-01T00:00:00"
    setup_snapshot_io(monkeypatch, tmp_path, [row])

    with pytest.raises(ValueError, match="evidence_observed_at.*timezone"):
        snapshot_runner.run_snapshot(
            tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
        )


def test_snapshot_runner_requires_explicit_cutoff_or_operational_configuration(monkeypatch, tmp_path):
    row = valid_fact_row()
    run_dir, writes = setup_snapshot_io(monkeypatch, tmp_path, [row])
    monkeypatch.setattr(snapshot_runner, "read_yaml", lambda path: {})

    with pytest.raises(ValueError, match="cutoff"):
        snapshot_runner.run_snapshot(tmp_path, "run1")
    assert writes == []


def test_snapshot_runner_keeps_explicit_cutoff_and_fact_times(monkeypatch, tmp_path):
    row = valid_fact_row()
    setup_snapshot_io(monkeypatch, tmp_path, [row])
    monkeypatch.setattr(
        snapshot_runner,
        "build_snapshot_edges_and_support",
        lambda **kwargs: ([], [], []),
    )

    captured = {}

    def capture_build(**kwargs):
        captured.update(kwargs)
        return [], [], []

    monkeypatch.setattr(snapshot_runner, "build_snapshot_edges_and_support", capture_build)
    result = snapshot_runner.run_snapshot(
        tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
    )

    fact = captured["fact_versions"][0]
    assert fact.evidence_observed_at.isoformat() == "2020-02-01T00:00:00+00:00"
    assert fact.ingested_at_real.isoformat() == "2020-02-02T00:00:00+00:00"
    assert captured["cutoff"].isoformat() == "2021-01-01T00:00:00+00:00"
    assert result["cutoffs_count"] == 1
