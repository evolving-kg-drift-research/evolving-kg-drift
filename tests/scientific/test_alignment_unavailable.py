import pytest

from src.drift.metrics import compute_longitudinal_drift
from src.drift.null import ConditionalBucketStats, EmpiricalNullArtifact
from src.kge.checkpoint import CheckpointProvenance, KGECheckpoint


def test_alignment_diagnostics_gate_blocks_sed_plus():
    """A24: If alignment diagnostics fail (e.g. rank deficiency), SED+ must be None and status ALIGNMENT_UNAVAILABLE."""
    # Create dimension 8 checkpoints where all points are collapsed to a 1D line:
    # coordinates are [c, 0, 0, 0, 0, 0, 0, 0] -> numerical rank = 1 < 4 (8 // 2)!
    dimension = 8
    entities = [f"E_{i}" for i in range(10)]

    prov_1 = CheckpointProvenance(
        snapshot_id="S1",
        snapshot_hash="h1",
        seed=13,
        model="TransE",
        dimension=dimension,
        norm=2,
        entity_mapping_hash="m",
        relation_mapping_hash="r",
        config_hash="c",
    )
    prov_2 = CheckpointProvenance(
        snapshot_id="S2",
        snapshot_hash="h2",
        seed=13,
        model="TransE",
        dimension=dimension,
        norm=2,
        entity_mapping_hash="m",
        relation_mapping_hash="r",
        config_hash="c",
    )

    # Rank-1 collapsed embeddings
    ckpt_1 = KGECheckpoint(
        provenance=prov_1,
        entity_embeddings={e: [float(i + 1)] + [0.0] * (dimension - 1) for i, e in enumerate(entities)},
        relation_embeddings={"r": [0.1] * dimension},
    )
    ckpt_2 = KGECheckpoint(
        provenance=prov_2,
        entity_embeddings={e: [float(i + 2)] + [0.0] * (dimension - 1) for i, e in enumerate(entities)},
        relation_embeddings={"r": [0.1] * dimension},
    )

    null_art = EmpiricalNullArtifact(
        snapshot_id="S1->S2",
        snapshot_hash="h",
        seed_pairs=[(13, 37)],
        entity_displacements={e: [0.1] * 6 for e in entities},
        bucket_stats={
            "low": ConditionalBucketStats(
                bucket_id="low",
                feature_range=(0, 2),
                entity_count=len(entities),
                observation_count=60,
                median=0.1,
                mad=0.02,
                robust_scale=0.029652,
                is_degenerate=False,
            )
        },
        entity_to_bucket={e: "low" for e in entities},
    )

    drift_art = compute_longitudinal_drift(
        checkpoint_prev=ckpt_1,
        checkpoint_next=ckpt_2,
        null_artifact=null_art,
    )

    for e, m in drift_art.measurements.items():
        assert m.sed_plus is None, f"Entity {e} sed_plus should be None under rank-deficient alignment"
        assert "ALIGNMENT_UNAVAILABLE" in m.null_status
        assert "RANK_DEFICIENT" in m.null_status
