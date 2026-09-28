from __future__ import annotations

import json
from pathlib import Path

import pytest

from kg_pipeline import snapshot_runner
from kg_pipeline.contracts import make_row
from kg_pipeline.hashing import stable_id
from temporal.schema import ContractError


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def to_pylist(self):
        return self.rows


def _valid_inputs():
    digest = "a" * 64
    fact = {
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
        "accepted_into_kg_at": "2020-02-03T00:00:00Z",
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
    claim = make_row(
        "extracted_claims",
        claim_id="claim_1",
        body_variant_id="bv_1",
        source_id="bv_1",
        subject_mention="Alpha",
        relation_name="REL",
        object_mention="Beta",
        evidence_span_start=10,
        evidence_span_end=20,
        evidence_text_hash="sha256:evidence",
        valid_from_extracted=None,
        valid_to_extracted=None,
        is_negative=False,
        is_speculative=False,
    )
    membership = make_row(
        "document_memberships",
        membership_id="mem_1",
        raw_blob_sha256=digest,
        raw_candidate_id="raw_1",
        body_variant_id="bv_1",
        exact_cluster_id="cluster_1",
        retrieval_ids_json=json.dumps(["ret_1"]),
        source_provenance_status="STRICT",
        strict_input_eligible=True,
        membership_status="INCLUDED",
        reason=None,
    )
    retrieval = make_row(
        "retrievals",
        retrieval_id="ret_1",
        raw_blob_sha256=digest,
        source_id="publisher_1",
        requested_url="https://publisher.test/item",
        final_url="https://publisher.test/item",
        retrieved_at_real="2025-01-01T00:00:00Z",
        archive_datetime=None,
        recorded_event_at=None,
        recorded_event_time_field=None,
        provenance_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
        evidence_file_sha256=None,
        evidence_record_sha256=None,
    )
    source_version = make_row(
        "source_versions",
        source_version_id="sv_1",
        raw_blob_sha256=digest,
        retrieval_id="ret_1",
        source_id="publisher_1",
        canonical_or_final_url="https://publisher.test/item",
        retrieved_at_real="2025-01-01T00:00:00Z",
        archive_datetime=None,
        source_version_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
    )
    provenance = make_row(
        "claim_provenance",
        provenance_id=stable_id("claimprovenance", {
            "claim_id": "claim_1",
            "membership_id": "mem_1",
            "source_version_id": "sv_1",
            "retrieval_id": "ret_1",
            "raw_blob_sha256": digest,
        }),
        claim_id="claim_1",
        membership_id="mem_1",
        source_version_id="sv_1",
        retrieval_id="ret_1",
        raw_blob_sha256=digest,
        publisher_source_id="publisher_1",
        source_url="https://publisher.test/item",
    )
    return {
        "fact_versions": [fact],
        "extracted_claims": [claim],
        "document_memberships": [membership],
        "retrievals": [retrieval],
        "source_versions": [source_version],
        "claim_provenance": [provenance],
        "entity_mapping_versions": [],
    }


def _run_with_inputs(monkeypatch, tmp_path: Path, inputs):
    run_dir = tmp_path / "runs" / "run1"
    tables_dir = run_dir / "tables"
    tables_dir.mkdir(parents=True)
    paths = {}
    for name in inputs:
        path = tables_dir / f"{name}.parquet"
        path.touch()
        paths[name] = path
    path_to_name = {path: name for name, path in paths.items()}
    monkeypatch.setattr(
        snapshot_runner,
        "resolve_run_table_path",
        lambda repo_root, run_id, name: paths.get(name, tables_dir / f"{name}.parquet"),
    )
    monkeypatch.setattr(
        snapshot_runner.pq,
        "read_table",
        lambda path: FakeTable(inputs[path_to_name[path]]),
    )
    writes = []
    monkeypatch.setattr(snapshot_runner, "write_parquet_immutable", lambda *args: writes.append(args))
    monkeypatch.setattr(snapshot_runner, "write_yaml_immutable", lambda *args: writes.append(args))
    monkeypatch.setattr(snapshot_runner, "create_stage_manifest", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        snapshot_runner,
        "load_run_manifest",
        lambda *args, **kwargs: {
            "config_candidates": {},
            "config_approval": {},
            "machine_schema": {},
            "code_fingerprint_sha256": "a" * 64,
        },
    )
    config_dir = run_dir / "inputs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "proposed_config_bundle.yaml").write_text(
        "resolved_config:\n  snapshot_boundaries:\n    policy_version: fixture-only-v1\n",
        encoding="utf-8",
    )
    from kg_pipeline import gates
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: {"gate": "A"})
    from kg_pipeline import contract_authority
    monkeypatch.setattr(contract_authority, "require_schema_compatible", lambda *args, **kwargs: {})
    monkeypatch.setattr(snapshot_runner, "build_snapshot_edges_and_support", lambda **kwargs: ([], [], []))
    return run_dir, writes


def test_snapshot_provenance_validates_full_canonical_chain(monkeypatch, tmp_path):
    run_dir, writes = _run_with_inputs(monkeypatch, tmp_path, _valid_inputs())

    result = snapshot_runner.run_snapshot(
        tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
    )

    assert result["status"] == "COMPLETED"
    assert len(writes) >= 4
    assert (run_dir / "tables").is_dir()


@pytest.mark.parametrize(
    ("table", "mutate", "error"),
    [
        ("document_memberships", lambda rows: rows[0].update(body_variant_id="bv_other"), "no document-membership provenance"),
        ("document_memberships", lambda rows: rows[0].update(raw_blob_sha256="b" * 64), "provenance hash mismatch"),
        ("retrievals", lambda rows: rows[0].update(raw_blob_sha256="b" * 64), "provenance hash mismatch"),
        ("source_versions", lambda rows: rows[0].update(source_version_id="sv_other"), "does not match canonical"),
        ("source_versions", lambda rows: rows[0].update(raw_blob_sha256="b" * 64), "provenance hash mismatch"),
        ("retrievals", lambda rows: rows[0].update(final_url="https://other.test/"), "does not match canonical"),
    ],
)
def test_snapshot_rejects_inconsistent_upstream_provenance_before_writing(
    monkeypatch, tmp_path, table, mutate, error
):
    inputs = _valid_inputs()
    mutate(inputs[table])
    _, writes = _run_with_inputs(monkeypatch, tmp_path, inputs)

    with pytest.raises((ContractError, ValueError), match=error):
        snapshot_runner.run_snapshot(
            tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
        )

    assert writes == []


@pytest.mark.parametrize("missing_table", ["document_memberships", "retrievals", "source_versions", "extracted_claims"])
def test_snapshot_requires_canonical_provenance_inputs(monkeypatch, tmp_path, missing_table):
    inputs = _valid_inputs()
    del inputs[missing_table]
    _, writes = _run_with_inputs(monkeypatch, tmp_path, inputs)

    with pytest.raises(FileNotFoundError, match=missing_table):
        snapshot_runner.run_snapshot(
            tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
        )

    assert writes == []


@pytest.mark.parametrize("change", ["duplicate", "missing", "extra"])
def test_snapshot_requires_exact_provenance_rows(monkeypatch, tmp_path, change):
    inputs = _valid_inputs()
    if change == "duplicate":
        inputs["claim_provenance"].append(dict(inputs["claim_provenance"][0]))
    elif change == "missing":
        inputs["claim_provenance"] = []
    else:
        extra = dict(inputs["claim_provenance"][0])
        extra.update(provenance_id="prov_extra", membership_id="mem_extra")
        inputs["claim_provenance"].append(extra)
    _, writes = _run_with_inputs(monkeypatch, tmp_path, inputs)

    with pytest.raises((ContractError, ValueError)):
        snapshot_runner.run_snapshot(
            tmp_path, "run1", cutoff_iso="2021-01-01T00:00:00Z", snapshot_id="S1"
        )

    assert writes == []
