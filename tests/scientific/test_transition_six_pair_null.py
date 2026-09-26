import pytest

from src.drift.null import (
    build_same_snapshot_empirical_null,
    build_transition_empirical_null,
)
from src.kge.checkpoint import CheckpointProvenance, KGECheckpoint
from src.kge.contract import SnapshotDataset


def test_transition_null_pools_six_seed_pairs():
    """A21: Transition null for S_prev -> S_next must pool 6 seed-pair observations (3 from S_prev, 3 from S_next)."""
    ds_prev = SnapshotDataset.create("S1", [("E1", "r1", "E2"), ("E2", "r1", "E3")])
    ds_next = SnapshotDataset.create("S2", [("E1", "r1", "E2"), ("E2", "r1", "E3"), ("E1", "r2", "E3")])

    def make_ckpt(snap_id: str, seed: int):
        prov = CheckpointProvenance(
            snapshot_id=snap_id,
            snapshot_hash="h",
            seed=seed,
            model="TransE",
            dimension=4,
            norm=2,
            entity_mapping_hash="m",
            relation_mapping_hash="r",
            config_hash="c",
        )
        # Give distinct coordinates per seed
        return KGECheckpoint(
            provenance=prov,
            entity_embeddings={
                "E1": [float(seed) * 0.1, 0.2, 0.3, 0.4],
                "E2": [0.1, float(seed) * 0.2, 0.3, 0.4],
                "E3": [0.1, 0.2, float(seed) * 0.3, 0.4],
            },
            relation_embeddings={"r1": [0.1, 0.1, 0.1, 0.1], "r2": [0.2, 0.2, 0.2, 0.2]},
        )

    ckpts_prev = {13: make_ckpt("S1", 13), 37: make_ckpt("S1", 37), 101: make_ckpt("S1", 101)}
    ckpts_next = {13: make_ckpt("S2", 13), 37: make_ckpt("S2", 37), 101: make_ckpt("S2", 101)}

    null_transition = build_transition_empirical_null(
        dataset_prev=ds_prev,
        checkpoints_prev=ckpts_prev,
        dataset_next=ds_next,
        checkpoints_next=ckpts_next,
        seed_pairs=((13, 37), (13, 101), (37, 101)),
    )

    # 1. Total seed pairs recorded must be 6
    assert len(null_transition.seed_pairs) == 6

    # 2. Every persistent entity must have exactly 6 displacement observations
    # (3 from S1 and 3 from S2)
    for e in ("E1", "E2", "E3"):
        obs = null_transition.entity_displacements[e]
        assert len(obs) == 6, f"Entity {e} had {len(obs)} observations, expected 6 (3 from S1 + 3 from S2)"
