from __future__ import annotations

from collections import Counter

import numpy as np

from kge.validation import (
    bootstrap_ci, filtered_reciprocal_ranks, frequency_baseline_reciprocal_ranks, make_folds,
    noise_aware_converged, plateau_converged, procrustes_holdout_distance, random_baseline_mrr, stability_plateau,
)


def _graph(n: int = 40) -> list[tuple[str, str, str]]:
    triples = []
    for i in range(n):
        triples.append((f"e{i}", "r1", f"e{(i + 1) % n}"))
        triples.append((f"e{i}", "r2", f"e{(i + 7) % n}"))
    return triples


def test_folds_are_disjoint_and_never_orphan_entities_or_relations() -> None:
    triples = _graph()
    folds = make_folds(triples, 5, "T00")
    flat = [t for f in folds for t in f]
    assert len(flat) == len(set(flat)) and flat
    for fold in folds:
        held = set(fold)
        deg = Counter(x for h, r, t in triples if (h, r, t) not in held for x in (h, t))
        assert all(deg[h] >= 1 and deg[t] >= 1 for h, _, t in fold)
        train_relations = {r for h, r, t in triples if (h, r, t) not in held}
        assert train_relations == {"r1", "r2"}


def test_folds_are_deterministic_and_salted() -> None:
    triples = _graph()
    assert make_folds(triples, 5, "T00") == make_folds(triples, 5, "T00")
    assert make_folds(triples, 5, "T00") != make_folds(triples, 5, "T00", salt="other")


def test_degree_one_entities_are_never_held_out() -> None:
    triples = [("a", "r", "b"), ("a", "r", "c"), ("c", "r", "d"), ("d", "r", "e")]
    held = {t for f in make_folds(triples, 1, "T00") for t in f}
    assert ("a", "r", "b") not in held and ("d", "r", "e") not in held   # b and e have degree 1


def test_filtered_ranks_perfect_embedding_and_filtering() -> None:
    e2i = {"a": 0, "b": 1, "c": 2, "d": 3}
    r2i = {"r": 0}
    entity = np.array([[0.0, 0.0], [1.0, 0.01], [1.0, 0.0], [5.0, 5.0]])   # c is closer to a+r than b
    relation = np.array([[1.0, 0.0]])
    rr = filtered_reciprocal_ranks(entity, relation, e2i, r2i, [("a", "r", "b")], [("a", "r", "b"), ("a", "r", "c")])
    assert rr[0] == 1.0   # c is another true tail and is filtered out, so b ranks first
    unfiltered = filtered_reciprocal_ranks(entity, relation, e2i, r2i, [("a", "r", "b")], [("a", "r", "b")])
    assert unfiltered[0] < 1.0


def test_frequency_baseline_uses_training_counts_only() -> None:
    e2i = {"a": 0, "b": 1, "c": 2}
    train = [("a", "r", "b"), ("c", "r", "b")]
    rr = frequency_baseline_reciprocal_ranks(e2i, train, [("a", "r", "b")], train + [("a", "r", "b")])
    assert rr[0] > 0.5


def test_random_baseline_and_bootstrap() -> None:
    assert abs(random_baseline_mrr(1) - 1.0) < 1e-12 and random_baseline_mrr(1000) < 0.01
    mean, lo, hi = bootstrap_ci([0.2, 0.4, 0.6, 0.8], 500, 1)
    assert lo <= mean <= hi and bootstrap_ci([], 10, 1)[0] != bootstrap_ci([], 10, 1)[0]


def test_plateau_converged_detects_plateau_and_rejects_drift() -> None:
    flat = [1.0] * 5 + list(np.linspace(0.5, 0.02, 60)) + [0.02] * 30
    assert plateau_converged(flat)["converged"]
    drifting = list(np.linspace(1.0, 0.05, 100))
    assert not plateau_converged(drifting)["converged"]
    assert not plateau_converged([1.0] * 100)["converged"]               # plateau but no learning
    assert not plateau_converged([1.0, float("nan")] * 20)["converged"]


def test_procrustes_recovers_a_rotation_and_random_is_far() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=(200, 16))
    q, _ = np.linalg.qr(rng.normal(size=(16, 16)))
    b = a @ q.T + 3.0
    fit, hold = list(range(0, 120)), list(range(120, 200))
    assert np.nanmedian(procrustes_holdout_distance(a, b, fit, hold)) < 1e-6
    noise = rng.normal(size=(200, 16))
    assert np.nanmedian(procrustes_holdout_distance(a, noise, fit, hold)) > 0.5


def test_noise_aware_gate_accepts_noisy_plateau_and_rejects_drift() -> None:
    rng = np.random.default_rng(1)
    noisy_plateau = [2.0] + list(0.65 + rng.normal(0, 0.02, 99))      # margin-2-like floor, noisy
    assert noise_aware_converged(noisy_plateau)["converged"]
    assert not noise_aware_converged(list(np.linspace(2.0, 0.3, 100)))["converged"]   # still falling
    assert not noise_aware_converged([1.0, float("inf")] * 30)["converged"]
    assert not noise_aware_converged([2.0] * 10)["converged"]


def test_noise_aware_gate_requires_learning() -> None:
    rng = np.random.default_rng(2)
    res = noise_aware_converged([1.0] + list(0.95 + rng.normal(0, 0.01, 99)))
    assert res["plateau"] and not res["learned"] and not res["converged"]


def test_stability_plateau_rule() -> None:
    noise = {100: 0.40, 150: 0.32, 200: 0.315, 300: 0.31, 400: 0.33}
    assert not stability_plateau(noise, 100, 150, 0.01)   # still improving by 0.08
    assert stability_plateau(noise, 150, 200, 0.01)       # improves by 0.005 only
    assert stability_plateau(noise, 300, 400, 0.01)       # noise rises: more training does not help
    assert not stability_plateau({1: float("nan"), 2: 0.1}, 1, 2, 0.01)
