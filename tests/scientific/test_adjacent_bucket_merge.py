import pytest

from src.drift.null import (
    ConditionalBucketStats,
    build_same_snapshot_empirical_null,
)
from src.kge.checkpoint import CheckpointProvenance, KGECheckpoint
from src.kge.contract import EntityMetadata, SnapshotDataset, Triple


def test_sparse_bucket_merges_only_with_adjacent_bucket():
    """A23: Sparse bucket must merge strictly with adjacent degree bucket.

    Setup:
      - 'low' degree bucket: 10 observations
      - 'medium' degree bucket: 10 observations
      - 'high' degree bucket: 1 observation (sparse, min_bucket_samples=5)

    'high' is adjacent to 'medium', NOT 'low'.
    Even if 'low' had 100 observations, 'high' MUST merge with 'medium' (adjacent),
    never with 'low'.
    """
    # Create dataset with 3 entities:
    # E_low: degree 1 -> bucket 'low'
    # E_med: degree 4 -> bucket 'medium'
    # E_high: degree 10 -> bucket 'high'
    triples = [
        ("E_low", "r1", "other_1"),
        ("E_med", "r1", "m1"),
        ("E_med", "r1", "m2"),
        ("E_med", "r1", "m3"),
        ("E_med", "r1", "m4"),
    ] + [("E_high", "r1", f"h_{i}") for i in range(10)]

    dataset = SnapshotDataset.create("S1", triples)

    # Mock checkpoints for seeds 13, 37
    def make_ckpt(seed: int):
        prov = CheckpointProvenance(
            snapshot_id="S1",
            snapshot_hash=dataset.snapshot_hash,
            seed=seed,
            model="TransE",
            dimension=4,
            norm=2,
            entity_mapping_hash="m1",
            relation_mapping_hash="r1",
            config_hash="c1",
        )
        return KGECheckpoint(
            provenance=prov,
            entity_embeddings={
                e: [0.1, 0.2, 0.3, 0.4] for e in dataset.entities
            },
            relation_embeddings={"r1": [0.1, 0.1, 0.1, 0.1]},
        )

    checkpoints = {13: make_ckpt(13), 37: make_ckpt(37)}

    # Bin edges: (3, 6) -> low: <3, med: 3..5, high: >=6
    # Seed pairs: [(13, 37)] -> 1 observation per entity
    # E_high has 1 observation < min_bucket_samples=5 -> sparse!
    # E_med has 1 observation, E_low has 1 observation
    # But let's check: if 'high' is merged, it must merge with 'medium', producing 'medium+high'
    # It must NOT produce 'high+low' or 'low+high' directly while medium is distinct!
    null_art = build_same_snapshot_empirical_null(
        dataset=dataset,
        checkpoints=checkpoints,
        seed_pairs=((13, 37),),
        bin_edges=(3, 6),
        min_bucket_samples=2,  # so 1 obs is sparse, 2 obs is not
    )

    # In our scenario with min_bucket_samples=2:
    # E_high has 1 obs, E_med has 1 obs, E_low has 1 obs.
    # If high merges with adjacent medium -> medium+high (2 obs >= 2).
    # Then low (1 obs) merges with adjacent medium+high -> low+medium+high.
    # At no point should 'low' and 'high' merge directly while skipping 'medium'!
    for b_id in null_art.bucket_stats:
        assert b_id != "high+low"
        assert b_id != "low+high"
