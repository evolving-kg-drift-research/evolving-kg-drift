"""Comprehensive tests for Representation Drift, Signed Excess, SED+, and Adversarial cases."""

import math

from src.drift.anchors import deterministic_hash_split
from src.drift.metrics import compute_longitudinal_drift
from src.drift.null import (
    ConditionalBucketStats,
    EmpiricalNullArtifact,
    build_same_snapshot_empirical_null,
    compute_mad,
    compute_median,
    compute_robust_scale,
)
from src.kge.checkpoint import CheckpointProvenance, KGECheckpoint
from src.kge.fixtures import create_synthetic_snapshots
from src.kge.model import TransEConfig
from src.kge.trainer import train_multi_seed, train_single_seed


def test_robust_statistics_median_and_mad():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    # Median is 3.0
    assert compute_median(data) == 3.0
    # Deviations: [2.0, 1.0, 0.0, 1.0, 2.0] -> sorted: [0.0, 1.0, 1.0, 2.0, 2.0] -> median is 1.0
    assert compute_mad(data) == 1.0
    assert abs(compute_robust_scale(data) - 1.4826) < 1e-6

    # Even number of elements
    data_even = [1.0, 2.0, 3.0, 4.0]
    assert compute_median(data_even) == 2.5


def test_signed_excess_retains_negative_values():
    """Invariant 19: r_{e,g} MUST store negative values when temporal movement < null median."""
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]

    cfg = TransEConfig(dimension=16, norm=2, epochs=3, seed=13)
    ckpt = train_single_seed(s1, cfg)

    # Synthetic null artifact with large median
    bucket_stats = {
        "b1": ConditionalBucketStats(
            bucket_id="b1",
            feature_range=(0, 10),
            entity_count=len(s1.entities),
            observation_count=30,
            median=0.5,  # High null median
            mad=0.1,
            robust_scale=0.14826,
            is_degenerate=False,
        )
    }
    null_art = EmpiricalNullArtifact(
        snapshot_id="S1",
        snapshot_hash=s1.snapshot_hash,
        seed_pairs=[(13, 37)],
        entity_displacements={e: [0.5] for e in s1.entities},
        bucket_stats=bucket_stats,
        entity_to_bucket={e: "b1" for e in s1.entities},
    )

    # Measure drift of identical checkpoint against itself: raw displacement will be ~0
    drift_art = compute_longitudinal_drift(
        checkpoint_prev=ckpt,
        checkpoint_next=ckpt,
        null_artifact=null_art,
        transition_id="S1->S1_identity",
    )

    for e, m in drift_art.measurements.items():
        assert m.raw_displacement < 1e-6
        # signed_excess = raw - null_median = ~0 - 0.5 = ~ -0.5 (NEGATIVE!)
        assert m.signed_excess < -0.4, f"Entity {e} signed excess was not negative: {m.signed_excess}"
        # SED+ = max(0, signed_excess) / scale = 0.0
        assert m.sed_plus == 0.0


def test_degenerate_null_safely_marks_sed_unavailable():
    """Invariant 20: If bucket MAD is degenerate (zero MAD or sparse), SED+ must be unavailable (None)."""
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]

    cfg = TransEConfig(dimension=16, norm=2, epochs=3, seed=13)
    ckpt = train_single_seed(s1, cfg)

    # Synthetic degenerate null artifact with zero MAD
    bucket_stats = {
        "b_deg": ConditionalBucketStats(
            bucket_id="b_deg",
            feature_range=(0, 10),
            entity_count=len(s1.entities),
            observation_count=20,
            median=0.1,
            mad=0.0,  # DEGENERATE!
            robust_scale=0.0,
            is_degenerate=True,
            degeneracy_reason="ZERO_MAD",
        )
    }
    null_art = EmpiricalNullArtifact(
        snapshot_id="S1",
        snapshot_hash=s1.snapshot_hash,
        seed_pairs=[(13, 37)],
        entity_displacements={e: [0.1] for e in s1.entities},
        bucket_stats=bucket_stats,
        entity_to_bucket={e: "b_deg" for e in s1.entities},
    )

    drift_art = compute_longitudinal_drift(
        checkpoint_prev=ckpt,
        checkpoint_next=ckpt,
        null_artifact=null_art,
        transition_id="S1->S1_deg",
    )

    for e, m in drift_art.measurements.items():
        assert m.sed_plus is None, "SED+ must be None when null is degenerate!"
        assert "DEGENERATE_NULL" in m.null_status


def test_three_separate_drift_quantities_preserved():
    """Requirement: raw_displacement, signed_excess, and sed_plus must be kept separate."""
    fixtures = create_synthetic_snapshots()
    s1, s2 = fixtures["S1"], fixtures["S2"]

    runs_s1 = train_multi_seed(s1, seeds=(13, 37, 101), dimension=16, epochs=3)
    runs_s2 = train_multi_seed(s2, seeds=(13, 37, 101), dimension=16, epochs=3)
    null_s1 = build_same_snapshot_empirical_null(s1, runs_s1)

    drift_art = compute_longitudinal_drift(
        checkpoint_prev=runs_s1[13],
        checkpoint_next=runs_s2[13],
        null_artifact=null_s1,
    )

    for e, m in drift_art.measurements.items():
        assert hasattr(m, "raw_displacement")
        assert hasattr(m, "signed_excess")
        assert hasattr(m, "sed_plus")
        assert m.raw_displacement >= 0.0
        # signed_excess can be positive or negative
        assert math.isfinite(m.signed_excess)
        if m.sed_plus is not None:
            assert m.sed_plus >= 0.0


def test_drift_pipeline_bound_parameters_from_config():
    """A25: Test KGEDriftPipeline.from_config binds all hyperparameters to protocol config."""
    from src.drift.pipeline import KGEDriftPipeline

    config = {
        "kge": {
            "dimension": 64,
            "seeds": [13, 37, 101],
            "epochs": 15,
        },
        "drift": {
            "fit_ratio": 0.7,
            "epsilon": 1e-5,
            "min_bucket_samples": 8,
            "bin_edges": [4, 8],
        }
    }

    pipeline = KGEDriftPipeline.from_config(config)
    assert pipeline.dimension == 64
    assert pipeline.seeds == (13, 37, 101)
    assert pipeline.epochs == 15
    assert pipeline.fit_ratio == 0.7
    assert pipeline.epsilon == 1e-5
    assert pipeline.min_bucket_samples == 8
    assert pipeline.bin_edges == (4, 8)

