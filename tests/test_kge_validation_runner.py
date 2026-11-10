"""Runner contracts use a canonical-Parquet fixture, never research data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from src.kge.fixtures import create_synthetic_snapshots
from src.kge.splits import coverage_split, content_hash
from src.kge.validation import fixed_negative_pairs


@pytest.fixture
def runner_config(tmp_path: Path):
    from scripts.run_kge_validation import design_identity

    ds = create_synthetic_snapshots()["S1"]
    package_root = "data/evolving_kg_downstream_v3_1"
    folder = tmp_path / package_root / "snapshots"
    folder.mkdir(parents=True)
    rows = [dict(zip(("subject_id", "relation_id", "object_id"), t.to_tuple())) for t in ds.triples]
    p = folder / "snapshot_T01_canonical.parquet"
    pq.write_table(pa.Table.from_pylist(rows), p)
    def sha(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    semantic = json.dumps({"table_name": "fixture", "contract_version": "fixture-v1", "rows": rows},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    (folder / (p.name + ".manifest.json")).write_text(json.dumps({
        "physical_sha256_computed_at_real": sha(p), "table_name": "fixture", "contract_version": "fixture-v1",
        "row_count": len(rows), "semantic_sha256": hashlib.sha256(semantic).hexdigest()}))
    cutoff = "2026-01-01T00:00:00+00:00"
    (folder / "snapshot_T01_manifest.yaml").write_text(yaml.safe_dump({
        "snapshot_id": "T01", "canonical_physical_sha256": sha(p), "cutoff": cutoff,
        "canonical_triple_count": len(rows), "entity_count": len(ds.entities)}))
    split = coverage_split(ds, 0.2, "runner-fixture")
    (tmp_path / "split.json").write_text(json.dumps(split.descriptor()))
    positives = [t.to_tuple() for t in ds.triples]
    (tmp_path / "pairs.json").write_text(json.dumps(fixed_negative_pairs(ds, split.validation, positives, seed=37)))
    def ref(p: Path) -> dict:
        return {"path": p.relative_to(tmp_path).as_posix(), "sha256": sha(p)}
    cfg = {"version": "quality_validation_runner_v1", "status": "CANDIDATE", "scientific_certification": False,
           "package_root": package_root, "snapshot": {"snapshot_id": "T01", "parquet_path": "snapshots/" + p.name,
           "cutoff": cutoff, "edges": len(rows), "entities": len(ds.entities)},
           "snapshot_files": [ref(f) for f in sorted(folder.iterdir())],
           "split": ref(tmp_path / "split.json"), "negative_pairs": ref(tmp_path / "pairs.json"),
           "model": {"dimension": 8, "norm": 2, "epochs": 2, "batch_size": 32,
                     "learning_rate": 0.01, "margin": 1.0, "normalize_entities": True},
           "seeds": [13, 37, 101], "training_filter_scope": "train", "approval": None}
    approval = {"actor": "user", "scope": "quality_validation_dev", "instruction": "fixture approval only",
                "design_sha256": design_identity(cfg)}
    (tmp_path / "approval.json").write_text(json.dumps(approval))
    cfg["approval"] = ref(tmp_path / "approval.json")
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(cfg))
    return tmp_path, config, cfg, content_hash(cfg)


def test_check_only_never_trains_or_creates_output(runner_config, monkeypatch):
    from scripts import run_kge_validation as runner
    root, config, _, _ = runner_config
    monkeypatch.setattr(runner, "train_validation_run", lambda *a, **k: pytest.fail("No training during preflight"))
    result = runner.run(root, config, execute=False)
    assert not result["ready"] and not (root / "outputs").exists()


def test_locked_config_is_rejected_before_hash_read(tmp_path: Path, monkeypatch):
    from scripts import run_kge_validation as runner

    monkeypatch.setattr(runner, "sha256_file", lambda *args: pytest.fail("Must reject before reading"))
    with pytest.raises(ValueError, match="locked_test"):
        runner.run(tmp_path, Path("data/locked_test/do-not-read.yaml"))


def test_v3_package_is_rejected_before_snapshot_read(runner_config, monkeypatch):
    from scripts import run_kge_validation as runner

    root, config, cfg, _ = runner_config
    cfg["package_root"] = "data/KG_lan2/evolving_kg_downstream_v3"
    config.write_text(yaml.safe_dump(cfg))
    monkeypatch.setattr(runner, "inspect_snapshot", lambda *args: pytest.fail("Must reject V3 before reading"))
    with pytest.raises(ValueError, match="V3.1"):
        runner.run(root, config)
    assert not (root / "outputs").exists()


def test_three_seed_execution_requires_matching_approval(runner_config):
    from scripts.run_kge_validation import run
    root, config, cfg, _ = runner_config
    cfg["status"] = "APPROVED_DEV_STAGE"
    config.write_text(yaml.safe_dump(cfg))
    result = run(root, config, execute=True, output=Path("outputs/fixture-run"))
    assert result["executed"] and result["seeds_verified"] == [13, 37, 101]
    assert (root / "outputs/fixture-run/registered_jobs.json").is_file()
    with pytest.raises(FileExistsError):
        run(root, config, execute=True, output=Path("outputs/fixture-run"))


@pytest.mark.parametrize("change", ["approval", "hash", "budget", "locked"])
def test_bad_bindings_fail_before_output(runner_config, change):
    from scripts.run_kge_validation import run
    root, config, cfg, _ = runner_config
    cfg["status"] = "APPROVED_DEV_STAGE"
    if change == "approval":
        cfg["approval"] = None
    if change == "hash":
        cfg["negative_pairs"]["sha256"] = "0" * 64
    if change == "budget":
        cfg["model"]["epochs"] = 3
    if change == "locked":
        cfg["split"]["path"] = "data/locked_test/no-open"
    config.write_text(yaml.safe_dump(cfg))
    with pytest.raises((ValueError, PermissionError)):
        run(root, config, execute=True, output=Path("outputs/bad"))
    assert not (root / "outputs").exists()
