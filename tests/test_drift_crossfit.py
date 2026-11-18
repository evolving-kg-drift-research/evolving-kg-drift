from __future__ import annotations

import numpy as np

from drift.crossfit import crossfit_distances, degree_bucket, entity_scores, merged_groups, stratified_folds


def test_degree_bucket_edges() -> None:
    assert [degree_bucket(d) for d in (1, 2, 3, 5, 6, 40)] == [0, 0, 1, 1, 2, 2]


def test_folds_are_stratified_deterministic_and_balanced() -> None:
    ents = [f"e{i}" for i in range(100)]
    buckets = [0] * 70 + [1] * 20 + [2] * 10
    folds = stratified_folds(ents, buckets, "T01->T02", 5)
    assert (folds == stratified_folds(ents, buckets, "T01->T02", 5)).all()
    for b, size in ((0, 14), (1, 4), (2, 2)):
        assert all(int(np.sum((folds == f) & (np.array(buckets) == b))) == size for f in range(5))


def test_crossfit_recovers_a_rotation_and_flags_unrelated_matrices() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=(200, 12))
    q, _ = np.linalg.qr(rng.normal(size=(12, 12)))
    folds = stratified_folds([f"e{i}" for i in range(200)], [0] * 200, "t", 5)
    dist, diag = crossfit_distances(a, a @ q.T + 2.0, folds, 5)
    assert np.nanmax(dist) < 1e-9 and all(d["valid"] for d in diag)
    noise_dist, noise_diag = crossfit_distances(a, rng.normal(size=a.shape), folds, 5)
    assert np.nanmedian(noise_dist) > 0.5 and len(noise_diag) == 5


def test_rank_deficient_fit_makes_entities_unavailable() -> None:
    a = np.random.default_rng(1).normal(size=(12, 40))
    folds = np.array([0, 1] * 6)
    dist, diag = crossfit_distances(a, a.copy(), folds, 2, min_rank_fraction=1.01)
    assert np.isnan(dist).all() and all("RANK" in str(d["reason"]) for d in diag)


def test_merge_rule_merges_sparse_bucket_with_larger_neighbour_tie_left() -> None:
    # 20 -> merges left into bucket 1 (50 entities, reference 49 < 50) -> still sparse -> merges left into bucket 0
    assert merged_groups({0: 200, 1: 30, 2: 20}, 50) == {0: (0, 1, 2), 1: (0, 1, 2), 2: (0, 1, 2)}
    assert merged_groups({0: 200, 1: 30, 2: 70}, 50) == {0: (0, 1), 1: (0, 1), 2: (2,)}   # larger neighbour is on the left
    assert merged_groups({0: 60, 1: 30, 2: 200}, 50) == {0: (0,), 1: (1, 2), 2: (1, 2)}   # larger neighbour is on the right
    assert merged_groups({0: 200, 1: 200, 2: 200}, 50) == {0: (0,), 1: (1,), 2: (2,)}
    only_left = merged_groups({0: 100, 1: 10, 2: 100}, 50)
    assert only_left[1] == (0, 1)                        # tie between neighbours -> left
    assert merged_groups({0: 10, 1: 10, 2: 10}, 50) == {0: (0, 1, 2), 1: (0, 1, 2), 2: (0, 1, 2)}


def test_scores_use_leave_target_out_and_zero_below_null() -> None:
    rng = np.random.default_rng(2)
    null = rng.normal(0.5, 0.02, 300)
    delta = null.copy()
    delta[0] = 0.9                                       # strong outlier
    delta[1] = 0.2                                       # below the null: SED+ must be exactly 0
    s = entity_scores(delta, null, np.zeros(300, dtype=int), support=50, eps=1e-4)
    assert s["sed_plus"][0] > 5 and s["sed_plus"][1] == 0.0 and s["signed_excess"][1] < 0
    # the target is excluded from its own reference: changing its own null value does not change its reference
    null2 = null.copy()
    null2[0] = 5.0
    s2 = entity_scores(delta, null2, np.zeros(300, dtype=int), support=50, eps=1e-4)
    assert s["reference_median"][0] == s2["reference_median"][0]


def test_entity_unavailable_when_support_cannot_be_met() -> None:
    s = entity_scores(np.full(30, 0.5), np.full(30, 0.5), np.zeros(30, dtype=int), support=50, eps=1e-4)
    assert np.isnan(s["sed_plus"]).all()
