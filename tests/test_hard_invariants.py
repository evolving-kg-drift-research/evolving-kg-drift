import pytest


# G1 / temporal integrity
@pytest.mark.skip(reason="Implement with temporal snapshot builder by G1")
def test_no_future_evidence():
    pass


@pytest.mark.skip(reason="Implement with versioned entity mapping by G1")
def test_no_future_entity_mapping():
    pass


@pytest.mark.skip(reason="Implement with deterministic snapshot fixtures by G1")
def test_snapshot_reproducible():
    pass


@pytest.mark.skip(reason="Implement with Neo4j materialization by G1")
def test_canonical_parquet_neo4j_parity():
    pass


# KGE / alignment / null
@pytest.mark.skip(reason="Implement when KGE checkpoints exist")
def test_embeddings_finite():
    pass


@pytest.mark.skip(reason="Implement when Procrustes alignment exists")
def test_procrustes_is_orthogonal():
    pass


@pytest.mark.skip(reason="Implement with deterministic anchor split")
def test_anchor_fit_holdout_disjoint():
    pass


@pytest.mark.skip(reason="Implement with alignment diagnostics")
def test_alignment_holdout_diagnostics_exist():
    pass


@pytest.mark.skip(reason="Implement with same-snapshot empirical null")
def test_null_excludes_target_entity_when_required():
    pass


@pytest.mark.skip(reason="Implement when drift artifacts exist")
def test_no_nan_inf_in_drift_artifacts():
    pass


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
