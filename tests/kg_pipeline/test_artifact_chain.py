"""Adversarial tests for C2's run/stage/Parquet binding boundary."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from kge.adapter import load_snapshots_from_run
from kg_pipeline.contracts import make_row
from kg_pipeline.hashing import sha256_json
from kg_pipeline.run import (
    create_stage_manifest,
    init_run,
    resolve_run_table_path,
    verify_stage_manifest,
)
from kg_pipeline.storage import ArtifactConflict, write_parquet_immutable


def _stage_chain(root: Path) -> tuple[Path, Path]:
    init_run(root, "chain_run", mode="snapshot")
    tables = root / "runs/chain_run/tables"
    upstream = tables / "retrievals.parquet"
    downstream = tables / "snapshot_edges.parquet"
    write_parquet_immutable(upstream, "retrievals", [])
    create_stage_manifest(root, "chain_run", "inventory", output_artifacts=[
        {"table": "retrievals", "path": str(upstream)}
    ])
    write_parquet_immutable(downstream, "snapshot_edges", [])
    create_stage_manifest(root, "chain_run", "snapshot_stage", input_artifacts=[
        {"table": "retrievals", "path": str(upstream)}
    ], output_artifacts=[
        {"table": "snapshot_edges", "path": str(downstream)}
    ])
    return upstream, downstream


def test_completed_chain_resolves_and_binds_inputs(tmp_path):
    upstream, downstream = _stage_chain(tmp_path)
    assert resolve_run_table_path(tmp_path, "chain_run", "snapshot_edges") == downstream
    manifest = verify_stage_manifest(tmp_path, "chain_run", "snapshot_stage")
    assert manifest["input_artifacts"][0]["physical_sha256"] == hashlib.sha256(upstream.read_bytes()).hexdigest()
    assert manifest["input_artifacts"][0]["producer_stage_manifest_hash"]


@pytest.mark.parametrize("damage", ["missing_sidecar", "changed_bytes", "missing_producer"])
def test_damaged_ancestor_blocks_consumer(tmp_path, damage):
    upstream, _ = _stage_chain(tmp_path)
    if damage == "missing_sidecar":
        upstream.with_suffix(".parquet.manifest.json").unlink()
    elif damage == "changed_bytes":
        with upstream.open("ab") as stream:
            stream.write(b"tampered")
    else:
        (tmp_path / "runs/chain_run/reports/inventory_manifest.yaml").unlink()
    with pytest.raises((ArtifactConflict, FileNotFoundError)):
        resolve_run_table_path(tmp_path, "chain_run", "snapshot_edges")


def test_parent_not_completed_blocks_consumer(tmp_path):
    _stage_chain(tmp_path)
    path = tmp_path / "runs/chain_run/reports/inventory_manifest.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["status"] = "FAILED"
    doc["stage_manifest_hash"] = sha256_json({
        key: value for key, value in doc.items() if key not in {"created_at_real", "stage_manifest_hash"}
    })
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="not COMPLETED"):
        resolve_run_table_path(tmp_path, "chain_run", "snapshot_edges")


def test_input_binding_change_blocks_consumer(tmp_path):
    _stage_chain(tmp_path)
    path = tmp_path / "runs/chain_run/reports/snapshot_stage_manifest.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["input_artifacts"][0]["producer_stage_manifest_hash"] = "0" * 64
    doc["stage_manifest_hash"] = sha256_json({
        key: value for key, value in doc.items() if key not in {"created_at_real", "stage_manifest_hash"}
    })
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="binding mismatch"):
        verify_stage_manifest(tmp_path, "chain_run", "snapshot_stage")


def test_stage_lineage_cycle_blocks_consumer(tmp_path):
    _stage_chain(tmp_path)
    path = tmp_path / "runs/chain_run/reports/snapshot_stage_manifest.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    ref = dict(doc["output_artifacts"][0])
    ref["producer_stage_manifest_hash"] = "0" * 64
    doc["input_artifacts"] = [ref]
    doc["stage_manifest_hash"] = sha256_json({
        key: value for key, value in doc.items() if key not in {"created_at_real", "stage_manifest_hash"}
    })
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="Stage lineage cycle"):
        verify_stage_manifest(tmp_path, "chain_run", "snapshot_stage")


def test_parent_run_cycle_blocks_consumer(tmp_path):
    _stage_chain(tmp_path)
    path = tmp_path / "runs/chain_run/run_manifest.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["parent_run_id"] = "chain_run"
    doc["semantic_sha256"] = sha256_json({
        key: value for key, value in doc.items() if key not in {"created_at_real", "semantic_sha256"}
    })
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="cycle"):
        resolve_run_table_path(tmp_path, "chain_run", "snapshot_edges")


def test_historical_parent_keeps_its_recorded_code_fingerprint(tmp_path, monkeypatch):
    from kg_pipeline import run

    init_run(tmp_path, "parent_run", mode="inventory")
    parent_table = tmp_path / "runs/parent_run/tables/retrievals.parquet"
    write_parquet_immutable(parent_table, "retrievals", [])
    create_stage_manifest(tmp_path, "parent_run", "inventory", output_artifacts=[
        {"table": "retrievals", "path": str(parent_table)}
    ])
    monkeypatch.setattr(run, "package_fingerprint", lambda root: "new_code_fingerprint")
    init_run(tmp_path, "child_run", mode="snapshot", parent_run_id="parent_run")
    child_table = tmp_path / "runs/child_run/tables/snapshot_edges.parquet"
    write_parquet_immutable(child_table, "snapshot_edges", [])
    create_stage_manifest(tmp_path, "child_run", "snapshot_stage", input_artifacts=[
        {"table": "retrievals", "path": str(parent_table)}
    ], output_artifacts=[
        {"table": "snapshot_edges", "path": str(child_table)}
    ])
    assert resolve_run_table_path(tmp_path, "child_run", "retrievals") == parent_table
    assert resolve_run_table_path(tmp_path, "child_run", "snapshot_edges") == child_table


def test_forged_gate_a_pass_cannot_authorize_downstream(tmp_path):
    from kg_pipeline.gates import require_gate_a

    _stage_chain(tmp_path)
    gate_dir = tmp_path / "runs/chain_run/gates/A"
    gate_dir.mkdir(parents=True)
    (gate_dir / "forged.json").write_text(
        json.dumps({"gate": "A", "run_id": "chain_run", "status": "PASS",
                    "evaluated_at_real": "2026-01-01T00:00:00+00:00"}), encoding="utf-8"
    )
    with pytest.raises(ArtifactConflict, match="semantic hash mismatch"):
        require_gate_a(tmp_path, "chain_run")


def test_m2_requires_snapshot_manifest_and_exact_requested_id(tmp_path, monkeypatch):
    run_id = "m2_chain"
    init_run(tmp_path, run_id, mode="snapshot")
    path = tmp_path / "runs" / run_id / "snapshots/S1/snapshot_edges.parquet"
    edge = make_row("snapshot_edges", edge_id="e1", subject_id="s", relation_id="r",
                    object_id="o", snapshot_id="S1")
    write_parquet_immutable(path, "snapshot_edges", [edge])
    with pytest.raises(PermissionError, match="Gate A has not been evaluated"):
        load_snapshots_from_run(tmp_path, run_id)
    from kg_pipeline import gates
    fixture_gate_ref = {"gate": "A", "run_id": run_id, "semantic_sha256": "fixture_only"}
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: fixture_gate_ref)
    from kg_pipeline import contract_authority
    monkeypatch.setattr(contract_authority, "require_schema_compatible", lambda *args, **kwargs: {})
    create_stage_manifest(tmp_path, run_id, "snapshot_stage", output_artifacts=[
        {"table": "snapshot_edges", "path": str(path)}
    ], gate_a_ref=fixture_gate_ref)
    with pytest.raises(ValueError, match="Missing snapshot manifest"):
        load_snapshots_from_run(tmp_path, run_id)
    with pytest.raises(FileNotFoundError, match="requested snapshot"):
        load_snapshots_from_run(tmp_path, run_id, ["S2"])
    with pytest.raises(ValueError, match="verified manifests"):
        load_snapshots_from_run(tmp_path, run_id, verify_manifest=False)
    semantic = {"snapshot_id": "S1", "cutoff": "2020-01-01T00:00:00+00:00",
                "graph_semantic_hash": hashlib.sha256(b"s\tr\to\n").hexdigest(), "edge_count": 1}
    report = {**semantic, "created_at_real": "2026-01-01T00:00:00+00:00",
              "snapshot_manifest_hash": hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()}
    (path.parent / "snapshot_manifest.yaml").write_text(yaml.safe_dump(report), encoding="utf-8")
    assert len(load_snapshots_from_run(tmp_path, run_id, ["S1"])["S1"].triples) == 1
