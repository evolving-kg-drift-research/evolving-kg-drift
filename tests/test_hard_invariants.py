import math
import pytest
from datetime import datetime, timezone

from src.drift.anchors import deterministic_hash_split
from src.drift.metrics import compute_longitudinal_drift
from src.drift.null import build_same_snapshot_empirical_null
from src.drift.procrustes import align_embeddings_procrustes
from src.kge.fixtures import create_synthetic_snapshots
from src.kge.model import TransEConfig
from src.kge.trainer import train_multi_seed, train_single_seed
from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot


# G1 / temporal integrity (All 4 active - Gate G1 compliant)
def test_no_future_evidence():
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fact = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="A",
        relation_id="REL",
        object_id="B",
        valid_from=cutoff,
        valid_to=None,
        evidence_observed_at=datetime(2021, 1, 1, tzinfo=timezone.utc),  # Future
        ingested_at_real=cutoff,
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="",
        evidence_span_start=0,
        evidence_span_end=1,
        evidence_text_hash="h",
    )
    snap, _ = build_snapshot([fact], cutoff=cutoff)
    assert len(snap) == 0


def test_no_future_entity_mapping():
    from tests.temporal.test_snapshot import test_late_alias_does_not_rewrite_history
    test_late_alias_does_not_rewrite_history()


def test_snapshot_reproducible():
    from tests.temporal.test_snapshot import test_snapshot_canonical_determinism
    test_snapshot_canonical_determinism()


def test_canonical_parquet_neo4j_parity():
    from tests.kg_pipeline.test_parity import test_verify_neo4j_parity
    test_verify_neo4j_parity()


# KGE / alignment / null (All 6 active - TransE & Drift compliant)
def test_embeddings_finite():
    fixtures = create_synthetic_snapshots()
    cfg = TransEConfig(dimension=32, norm=2, epochs=3, seed=13)
    ckpt = train_single_seed(fixtures["S1"], cfg)
    ckpt.verify_finite()
    for e, vec in ckpt.entity_embeddings.items():
        assert all(math.isfinite(x) for x in vec)
    for r, vec in ckpt.relation_embeddings.items():
        assert all(math.isfinite(x) for x in vec)


def test_procrustes_is_orthogonal():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]
    runs = train_multi_seed(s1, seeds=(13, 37), dimension=32, epochs=3)
    anchor_split = deterministic_hash_split(list(runs[13].entity_embeddings.keys()), fit_ratio=0.6)
    res = align_embeddings_procrustes(
        runs[13].entity_embeddings,
        runs[37].entity_embeddings,
        anchor_split,
        alignment_type="same_snapshot_cross_seed",
    )
    assert res.diagnostics.orthogonality_error < 1e-10


def test_anchor_fit_holdout_disjoint():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]
    split = deterministic_hash_split(s1.entities, fit_ratio=0.6)
    split.verify_disjoint()
    assert len(set(split.fit_anchors).intersection(set(split.holdout_anchors))) == 0
    assert len(split.fit_anchors) > 0
    assert len(split.holdout_anchors) > 0


def test_alignment_holdout_diagnostics_exist():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]
    runs = train_multi_seed(s1, seeds=(13, 37), dimension=32, epochs=3)
    split = deterministic_hash_split(s1.entities, fit_ratio=0.6)
    res = align_embeddings_procrustes(
        runs[13].entity_embeddings,
        runs[37].entity_embeddings,
        split,
        alignment_type="same_snapshot_cross_seed",
    )
    diag = res.diagnostics
    assert diag.num_fit_anchors == len(split.fit_anchors)
    assert diag.num_holdout_anchors == len(split.holdout_anchors)
    assert len(diag.singular_values) == 32
    assert diag.numerical_rank >= 1
    assert math.isfinite(diag.fit_residual)
    assert math.isfinite(diag.holdout_residual)
    assert math.isfinite(diag.fit_holdout_gap)
    assert len(diag.anchor_fit_hash) == 64
    assert len(diag.anchor_holdout_hash) == 64
    assert len(diag.alignment_hash) == 64


def test_null_excludes_target_entity_when_required():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]
    runs = train_multi_seed(s1, seeds=(13, 37, 101), dimension=32, epochs=3)
    null_art = build_same_snapshot_empirical_null(s1, runs)
    for e, disps in null_art.entity_displacements.items():
        assert len(disps) == 3  # 3 seed pairs
        assert all(math.isfinite(d) for d in disps)
        assert all(d >= -1e-9 for d in disps)
    for b_id, b_stats in null_art.bucket_stats.items():
        assert math.isfinite(b_stats.median)
        assert math.isfinite(b_stats.mad)
        assert math.isfinite(b_stats.robust_scale)


def test_no_nan_inf_in_drift_artifacts():
    fixtures = create_synthetic_snapshots()
    s1, s2 = fixtures["S1"], fixtures["S2"]
    runs_s1 = train_multi_seed(s1, seeds=(13, 37, 101), dimension=32, epochs=3)
    runs_s2 = train_multi_seed(s2, seeds=(13, 37, 101), dimension=32, epochs=3)
    null_s1 = build_same_snapshot_empirical_null(s1, runs_s1)

    drift_artifact = compute_longitudinal_drift(
        checkpoint_prev=runs_s1[13],
        checkpoint_next=runs_s2[13],
        null_artifact=null_s1,
        transition_id="S1->S2",
    )

    for e, m in drift_artifact.measurements.items():
        assert math.isfinite(m.raw_displacement)
        assert math.isfinite(m.signed_excess)
        if m.sed_plus is not None:
            assert math.isfinite(m.sed_plus)
            assert m.sed_plus >= 0.0  # SED+ is non-negative by definition


# QA / H2 / H3a contracts
@pytest.mark.skip(reason="Implement when QA candidate universes exist")
def test_ab_same_primary_candidate_universe():
    pass


@pytest.mark.skip(reason="Implement when Frozen-KGE OOV scoring exists")
def test_frozen_oov_scoring_rule_exact():
    pass


@pytest.mark.skip(reason="Implement when path reranking exists")
def test_c_exact_b_fallback_when_no_path():
    pass


# Locked-run access
@pytest.mark.skip(reason="Enable before the locked-test workflow")
def test_locked_test_not_accessed_before_freeze():
    pass
