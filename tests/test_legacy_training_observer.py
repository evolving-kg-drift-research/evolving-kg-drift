from __future__ import annotations

from dataclasses import asdict
import sys

from scripts.diagnose_legacy_t01_training import observe_training
from kge.contract import SnapshotDataset
from kge.model import TransEConfig
from kge.trainer import train_single_seed


def test_observer_preserves_checkpoint_and_random_stream() -> None:
    dataset = SnapshotDataset.create("fixture",[("a","r","b"),("b","r","c"),("c","r","d")])
    config = TransEConfig(dimension=32, epochs=3, seed=13)
    plain = train_single_seed(dataset,config,git_commit="fixture",git_dirty=True)
    traced, epochs = observe_training(dataset,config,"fixture",True)
    assert asdict(plain) == asdict(traced)
    assert len(epochs) == 3
    assert [e["loss"] for e in epochs] == plain.training_metrics["epoch_losses"]
    assert all(e["counts"]["triples_visited"] == 3 for e in epochs)
    assert all(len(e["samples"]) == 3 for e in epochs)
    assert sys.gettrace() is None


def test_observer_counts_sampling_exhaustion_without_updates() -> None:
    dataset = SnapshotDataset.create("saturated",[("a","r","a")])
    config = TransEConfig(dimension=32,epochs=1,seed=37)
    _, epochs = observe_training(dataset,config,"fixture",True)
    counts = epochs[0]["counts"]
    assert counts["candidate_draws"] == counts["rejected_original"] == 100
    assert counts["skipped_no_negative"] == 1
    assert counts["valid_negatives"] == counts["active_updates"] == 0
