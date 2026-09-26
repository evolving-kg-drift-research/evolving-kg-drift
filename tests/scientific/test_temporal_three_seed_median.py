
from src.drift.metrics import compute_longitudinal_drift
from src.drift.null import ConditionalBucketStats, EmpiricalNullArtifact, compute_median
from src.kge.checkpoint import CheckpointProvenance, KGECheckpoint


def test_temporal_drift_aggregates_across_three_parallel_seeds():
    """A20: Temporal drift must be measured across 3 parallel seed pairs and aggregated via median."""
    def make_ckpt(snap_id: str, seed: int, coord_factor: float):
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
        # Construct embeddings such that E1's displacement varies across seeds
        return KGECheckpoint(
            provenance=prov,
            entity_embeddings={
                "E1": [1.0 * coord_factor, 0.0, 0.0, 0.0],
                "E2": [0.0, 1.0, 0.0, 0.0],
                "E3": [0.0, 0.0, 1.0, 0.0],
            },
            relation_embeddings={"r1": [0.1, 0.1, 0.1, 0.1]},
            training_metrics={},
        )

    # In S1, all seeds have E1 at [1, 0, 0, 0]
    ckpts_s1 = {
        13: make_ckpt("S1", 13, 1.0),
        37: make_ckpt("S1", 37, 1.0),
        101: make_ckpt("S1", 101, 1.0),
    }

    # In S2, seeds 13, 37, 101 have different coordinates for E1
    # resulting in different displacements
    ckpts_s2 = {
        13: make_ckpt("S2", 13, 1.0),  # seed 13 -> 0 drift
        37: make_ckpt("S2", 37, 2.0),
        101: make_ckpt("S2", 101, 1.5),
    }

    null_art = EmpiricalNullArtifact(
        snapshot_id="S1->S2",
        snapshot_hash="h",
        seed_pairs=[(13, 37)],
        entity_displacements={"E1": [0.1], "E2": [0.1], "E3": [0.1]},
        bucket_stats={
            "low": ConditionalBucketStats(
                bucket_id="low",
                feature_range=(0, 2),
                entity_count=3,
                observation_count=3,
                median=0.1,
                mad=0.01,
                robust_scale=0.014826,
                is_degenerate=False,
            )
        },
        entity_to_bucket={"E1": "low", "E2": "low", "E3": "low"},
    )

    drift_art = compute_longitudinal_drift(
        checkpoint_prev=ckpts_s1,
        checkpoint_next=ckpts_s2,
        null_artifact=null_art,
        transition_id="S1->S2",
    )

    expected_seed_displacements = [
        compute_longitudinal_drift(
            ckpts_s1[seed], ckpts_s2[seed], null_art,
            transition_id="S1->S2",
        ).get_measurement("E1").raw_displacement
        for seed in (13, 37, 101)
    ]
    m = drift_art.get_measurement("E1")
    assert isinstance(m.raw_displacement, float)
    assert m.raw_displacement == compute_median(expected_seed_displacements)
    assert m.raw_displacement >= 0.0
