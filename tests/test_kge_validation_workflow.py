"""File-backed validation must be reproducible without production artifacts."""
from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.kge.fixtures import create_synthetic_snapshots
from src.kge.model import TransEConfig
from src.kge.splits import coverage_split


def test_split_membership_is_canonical_and_coverage_preserving():
    ds = create_synthetic_snapshots()["S1"]
    first = coverage_split(ds, 0.2, "fixture")
    second = coverage_split(replace(ds, triples=tuple(reversed(ds.triples))), 0.2, "fixture")
    assert first.sha256 == second.sha256
    first.validate(ds)
    assert set(first.train).isdisjoint(first.validation)


@pytest.mark.parametrize("seed", [13, 37, 101])
def test_epoch_logs_are_independently_replayed(tmp_path: Path, seed: int):
    from src.kge.validation import fixed_negative_pairs, train_validation_run
    from scripts.verify_kge_validation import verify

    ds = create_synthetic_snapshots()["S1"]
    split = coverage_split(ds, 0.2, "fixture")
    positives = [t.to_tuple() for t in ds.triples]
    pairs = fixed_negative_pairs(ds, split.validation, positives, seed=37)
    cfg = TransEConfig(dimension=8, epochs=3, seed=seed)
    for folder in ("one", "two"):
        train_validation_run(ds, cfg, split, pairs, positives,
                             training_filter_scope="train", output=tmp_path / folder)
        result = verify(tmp_path / folder)
        assert result["epochs_verified"] == 3
        assert result["ranking_rows_verified"] == 3 * 2 * len(split.validation)
    assert ((tmp_path / "one/epochs/0003.json").read_bytes()
            == (tmp_path / "two/epochs/0003.json").read_bytes())
    with pytest.raises(FileExistsError):
        train_validation_run(ds, cfg, split, pairs, positives,
                             training_filter_scope="train", output=tmp_path / "one")


def test_validation_contract_checks_negative_pairs_and_nonleakage(tmp_path: Path):
    from src.kge.validation import fixed_negative_pairs, train_validation_run

    ds = create_synthetic_snapshots()["S1"]
    split = coverage_split(ds, 0.2, "fixture")
    positives = [t.to_tuple() for t in ds.triples]
    pairs = fixed_negative_pairs(ds, split.validation, positives, seed=37)
    invalid = copy.deepcopy(pairs)
    invalid[0] = (invalid[0][0], invalid[0][0])
    with pytest.raises(ValueError, match="negative"):
        train_validation_run(ds, TransEConfig(epochs=1), split, invalid, positives,
                             training_filter_scope="train", output=tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_verifier_rejects_log_tamper_even_with_rehashed_manifest(tmp_path: Path):
    from src.kge.validation import fixed_negative_pairs, train_validation_run
    from scripts.verify_kge_validation import verify
    import hashlib

    ds = create_synthetic_snapshots()["S1"]
    split = coverage_split(ds, 0.2, "fixture")
    positives = [t.to_tuple() for t in ds.triples]
    pairs = fixed_negative_pairs(ds, split.validation, positives, seed=37)
    out = tmp_path / "run"
    train_validation_run(ds, TransEConfig(dimension=8, epochs=2), split, pairs, positives,
                         training_filter_scope="train", output=out)
    log = json.loads((out / "epoch_log.json").read_bytes())
    log[0]["validation_loss"] += 1
    (out / "epoch_log.json").write_text(json.dumps(log), encoding="utf-8")
    m = json.loads((out / "experiment_manifest.json").read_bytes())
    m["artifacts"]["hashes"]["epoch_log.json"] = hashlib.sha256((out / "epoch_log.json").read_bytes()).hexdigest()
    (out / "experiment_manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="loss"):
        verify(out)


@pytest.fixture
def saved_validation_run(tmp_path: Path) -> Path:
    from src.kge.validation import fixed_negative_pairs, train_validation_run

    ds = create_synthetic_snapshots()["S1"]
    split = coverage_split(ds, 0.2, "binding-fixture")
    positives = [t.to_tuple() for t in ds.triples]
    pairs = fixed_negative_pairs(ds, split.validation, positives, seed=37)
    out = tmp_path / "run"
    train_validation_run(ds, TransEConfig(dimension=8, epochs=2), split, pairs, positives,
                         training_filter_scope="train", output=out)
    return out


@pytest.mark.parametrize("key", ["data_hash", "query_hash", "entity_map_hash", "relation_map_hash"])
def test_verifier_checks_declared_input_identity(saved_validation_run: Path, key: str):
    from scripts.verify_kge_validation import verify

    p = saved_validation_run / "experiment_manifest.json"
    manifest = json.loads(p.read_bytes())
    manifest["inputs"][key] = "0" * 64
    p.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="identity|hash|mapping"):
        verify(saved_validation_run)


@pytest.mark.parametrize("unbound", ["epoch_log.json", "epochs/0001.json.sha256"])
def test_verifier_requires_all_consumed_artifacts_bound(saved_validation_run: Path, unbound: str):
    from scripts.verify_kge_validation import verify

    p = saved_validation_run / "experiment_manifest.json"
    manifest = json.loads(p.read_bytes())
    del manifest["artifacts"]["hashes"][unbound]
    p.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="bound|artifact"):
        verify(saved_validation_run)


def test_verifier_checks_online_loss_accounting(saved_validation_run: Path):
    import hashlib
    from scripts.verify_kge_validation import verify

    p = saved_validation_run / "epoch_log.json"
    rows = json.loads(p.read_bytes())
    rows[0]["online_train_loss"] = 123456.0
    p.write_text(json.dumps(rows), encoding="utf-8")
    mpath = saved_validation_run / "experiment_manifest.json"
    manifest = json.loads(mpath.read_bytes())
    manifest["artifacts"]["hashes"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="loss|account"):
        verify(saved_validation_run)
