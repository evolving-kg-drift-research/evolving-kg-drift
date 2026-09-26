import pytest

from src.drift.null import (
    ConditionalBucketStats,
    EmpiricalNullArtifact,
)


def test_leave_target_out_excludes_target_observations():
    """A22: Null calibration must exclude target entity's own observations (LTO)."""
    # Create null artifact with 2 entities in the same bucket
    # E_outlier has high noise: [0.9, 0.9]
    # E_normal_1..5 have low noise: [0.1, 0.1] each (10 observations total)
    entity_displacements = {
        "E_outlier": [0.9, 0.9],
        "E_norm_1": [0.1, 0.1],
        "E_norm_2": [0.1, 0.1],
        "E_norm_3": [0.1, 0.1],
        "E_norm_4": [0.1, 0.1],
        "E_norm_5": [0.1, 0.1],
    }
    entity_to_bucket = {e: "low" for e in entity_displacements}

    bucket_stats = {
        "low": ConditionalBucketStats(
            bucket_id="low",
            feature_range=(0, 2),
            entity_count=6,
            observation_count=12,
            median=0.1,
            mad=0.0,
            robust_scale=0.0,
            is_degenerate=True,
        )
    }

    null_art = EmpiricalNullArtifact(
        snapshot_id="S1",
        snapshot_hash="h1",
        seed_pairs=[(13, 37), (13, 101)],
        entity_displacements=entity_displacements,
        bucket_stats=bucket_stats,
        entity_to_bucket=entity_to_bucket,
    )

    # 1. When computing LTO stats for E_outlier:
    # E_outlier's [0.9, 0.9] MUST NOT be present in its reference null pool
    lto_stats_outlier = null_art.get_entity_lto_null_stats("E_outlier", min_bucket_samples=5)
    assert lto_stats_outlier is not None
    assert lto_stats_outlier.observation_count == 10  # 12 - 2 = 10
    assert lto_stats_outlier.median == 0.1  # median of normal entities

    # 2. When computing LTO stats for an entity in a sparse bucket where excluding it
    # drops the count below min_bucket_samples:
    sparse_displacements = {
        "E_1": [0.2],
        "E_2": [0.2],
        "E_3": [0.2],
    }
    sparse_to_bucket = {e: "b_sparse" for e in sparse_displacements}
    sparse_art = EmpiricalNullArtifact(
        snapshot_id="S1",
        snapshot_hash="h1",
        seed_pairs=[(13, 37)],
        entity_displacements=sparse_displacements,
        bucket_stats={
            "b_sparse": ConditionalBucketStats(
                bucket_id="b_sparse",
                feature_range=(0, 2),
                entity_count=3,
                observation_count=3,
                median=0.2,
                mad=0.0,
                robust_scale=0.0,
                is_degenerate=False,
            )
        },
        entity_to_bucket=sparse_to_bucket,
    )

    lto_sparse = sparse_art.get_entity_lto_null_stats("E_1", min_bucket_samples=3)
    assert lto_sparse is not None
    # 3 - 1 = 2 < 3 -> marked degenerate due to INSUFFICIENT_LTO_SAMPLES
    assert lto_sparse.is_degenerate is True
    assert lto_sparse.degeneracy_reason == "INSUFFICIENT_LTO_SAMPLES"
