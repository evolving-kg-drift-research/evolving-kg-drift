"""End-to-End integration test for the full KGE and Drift measurement pipeline."""

import math

from src.drift.pipeline import KGEDriftPipeline
from src.kge.fixtures import create_synthetic_snapshots


def test_full_pipeline_end_to_end_s1_s2_s3():
    """Executes the complete pipeline:

    Synthetic S1/S2/S3
      -> TransE x seeds 13, 37, 101
      -> Checkpoints
      -> Same-snapshot empirical null
      -> Centered Procrustes alignment (S1->S2, S2->S3)
      -> Raw displacement
      -> Signed excess
      -> SED+
    """
    snapshots = create_synthetic_snapshots()
    pipeline = KGEDriftPipeline(
        dimension=32,
        seeds=(13, 37, 101),
        epochs=5,
        fit_ratio=0.6,
        epsilon=1e-4,
    )

    results = pipeline.run_on_snapshots(snapshots)

    # 1. Checkpoints verification
    ckpts = results["checkpoints"]
    assert set(ckpts.keys()) == {"S1", "S2", "S3"}
    for s_id in ("S1", "S2", "S3"):
        assert set(ckpts[s_id].keys()) == {13, 37, 101}
        for s in (13, 37, 101):
            ckpt = ckpts[s_id][s]
            ckpt.verify_finite()
            assert ckpt.provenance.snapshot_id == s_id
            assert ckpt.provenance.seed == s
            assert ckpt.provenance.dimension == 32
            assert len(ckpt.artifact_hash) == 64

    # 2. Empirical Null verification
    nulls = results["null_artifacts"]
    assert set(nulls.keys()) == {"S1", "S2", "S3"}
    for s_id in ("S1", "S2", "S3"):
        null_art = nulls[s_id]
        assert null_art.snapshot_id == s_id
        assert len(null_art.bucket_stats) > 0
        for b_id, b_stats in null_art.bucket_stats.items():
            assert math.isfinite(b_stats.median)
            assert math.isfinite(b_stats.mad)

    # 3. Transitions verification (S1->S2 and S2->S3)
    drifts = results["drift_artifacts"]
    assert set(drifts.keys()) == {"S1->S2", "S2->S3"}

    for t_id, drift_art in drifts.items():
        assert len(drift_art.measurements) > 0
        diag = drift_art.alignment_diagnostics
        assert diag["orthogonality_error"] < 1e-10
        assert diag["fit_residual"] >= 0.0
        assert diag["holdout_residual"] >= 0.0

        for e, m in drift_art.measurements.items():
            # Raw displacement >= 0 within floating precision
            assert m.raw_displacement >= -1e-9
            # Signed excess can be positive or negative, must be finite
            assert math.isfinite(m.signed_excess)
            # SED+ is non-negative when available
            if m.sed_plus is not None:
                assert m.sed_plus >= 0.0
                assert math.isfinite(m.sed_plus)

            # Check provenance links
            assert len(m.alignment_hash) == 64
            assert len(m.checkpoint_prev_hash) == 64
            assert len(m.checkpoint_next_hash) == 64
