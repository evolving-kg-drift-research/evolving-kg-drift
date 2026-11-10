"""Reproductions for the pre-rerun audit, without production I/O."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from src.kge.checkpoint import KGECheckpoint
from src.kge.contract import SnapshotDataset
from src.kge.fixtures import create_synthetic_snapshots
from src.kge.model import TransEConfig, TransEModel
from src.kge.trainer import train_single_seed


def checkpoint():
    return train_single_seed(create_synthetic_snapshots()["S1"], TransEConfig(dimension=8, epochs=2))


def test_missing_checkpoint_sidecar_is_fatal(tmp_path: Path):
    cp = checkpoint()
    p = tmp_path / "missing.json"
    cp.save(tmp_path / "original.json")
    p.write_bytes((tmp_path / "original.json").read_bytes())
    with pytest.raises(ValueError, match="sidecar"):
        KGECheckpoint.load(p)


def test_checkpoint_sidecar_supports_filename_spaces(tmp_path: Path):
    cp = checkpoint()
    path = tmp_path / "model seed 13.json"
    cp.save(path)
    assert KGECheckpoint.load(path).artifact_hash == cp.artifact_hash


def test_checkpoint_semantic_hash_is_checked_without_sidecar(tmp_path: Path):
    cp = checkpoint()
    cp.save(tmp_path / "original.json")
    data = json.loads((tmp_path / "original.json").read_bytes())
    data["entity_embeddings"][next(iter(data["entity_embeddings"]))][0] += 1
    p = tmp_path / "changed.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="semantic"):
        KGECheckpoint.load(p, verify_sidecar=False)


def test_requested_empty_validation_is_fatal():
    ds = SnapshotDataset.create("tiny", [("a", "r", "b"), ("c", "r", "d")])
    with pytest.raises(ValueError, match="validation|coverage"):
        train_single_seed(ds, TransEConfig(epochs=1), dev_split_ratio=1e-12)


def test_validation_observer_does_not_change_training_rng(monkeypatch):
    ds = create_synthetic_snapshots()["S1"]
    cfg = TransEConfig(dimension=8, epochs=4)
    before = train_single_seed(ds, cfg, dev_split_ratio=0.2)
    original = TransEModel.evaluate_loss

    def extra_draws(self, triples, rng, positive_triples_set=None):
        result = original(self, triples, rng, positive_triples_set)
        for _ in range(10):
            rng.random()
        return result

    monkeypatch.setattr(TransEModel, "evaluate_loss", extra_draws)
    after = train_single_seed(ds, cfg, dev_split_ratio=0.2)
    assert before.entity_embeddings == after.entity_embeddings


def test_validation_split_changes_config_identity():
    ds = create_synthetic_snapshots()["S1"]
    cfg = TransEConfig(dimension=8, epochs=2)
    assert (train_single_seed(ds, cfg).provenance.config_hash
            != train_single_seed(ds, cfg, dev_split_ratio=0.2).provenance.config_hash)


def test_no_usable_negative_is_not_successful_zero_loss():
    model = TransEModel({"a": 0, "b": 1}, {"r": 0}, TransEConfig(dimension=4))
    triples = [(h, 0, t) for h in range(2) for t in range(2)]
    with pytest.raises(ValueError, match="negative"):
        model.train_epoch(triples, random.Random(13))


def test_empty_and_unusable_validation_are_fatal():
    model = TransEModel({"a": 0, "b": 1}, {"r": 0}, TransEConfig(dimension=4))
    with pytest.raises(ValueError, match="validation"):
        model.evaluate_loss([], random.Random(13))
    triples = [(h, 0, t) for h in range(2) for t in range(2)]
    with pytest.raises(ValueError, match="negative"):
        model.evaluate_loss(triples, random.Random(13))
    assert model.last_validation_counts["usable_negatives"] == 0


def test_legacy_db_entrypoint_stops_before_connecting(monkeypatch):
    from scripts import import_to_neo4j

    def forbidden(*args, **kwargs):
        pytest.fail("Legacy importer must not connect to a database")

    if hasattr(import_to_neo4j, "GraphDatabase"):
        monkeypatch.setattr(import_to_neo4j.GraphDatabase, "driver", forbidden)
    with pytest.raises(PermissionError, match="verified"):
        import_to_neo4j.main()


def test_combined_m4_entrypoint_cannot_advance_stages(tmp_path: Path, monkeypatch):
    from scripts import run_m4_evaluation_and_stats as runner

    monkeypatch.setattr(runner, "EVAL_OUT_DIR", tmp_path / "eval", raising=False)
    monkeypatch.setattr(runner, "STATS_OUT_DIR", tmp_path / "stats", raising=False)
    if hasattr(runner, "inspect_package"):
        monkeypatch.setattr(runner, "inspect_package", lambda *args: pytest.fail("No production reads"))
    with pytest.raises(PermissionError, match="stage"):
        runner.run_m4_pipeline()
    assert not list(tmp_path.iterdir())
