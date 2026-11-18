"""Deterministic synthetic calibration of the existing H1 estimator on unbalanced panels."""
from __future__ import annotations

from statistics.two_way_fixed_effects import fit_two_way_fe, wild_cluster_bootstrap

import numpy as np


def _simulate_panel(n_queries: int, beta: float, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Observe each query from its random entry transition through transition six."""
    rng = np.random.default_rng(seed)
    n_transitions = 7
    entries = rng.integers(0, n_transitions - 2, size=n_queries)
    query_indices, time_indices = np.nonzero(np.arange(n_transitions)[None, :] >= entries[:, None])
    alpha = rng.normal(0.0, 1.0, size=n_queries)
    gamma = rng.normal(0.0, 0.5, size=n_transitions)
    x = rng.normal(0.0, 1.0, size=len(query_indices))
    noise = rng.normal(0.0, 0.3, size=len(query_indices))
    y = alpha[query_indices] + gamma[time_indices] + beta * x + noise
    return y, x, query_indices, time_indices


def test_simulated_panel_has_staggered_contiguous_observations() -> None:
    y, x, queries, times = _simulate_panel(n_queries=20, beta=0.5, seed=123)
    assert np.issubdtype(queries.dtype, np.integer)
    assert np.issubdtype(times.dtype, np.integer)
    assert y.shape == x.shape == queries.shape == times.shape
    assert len(np.unique(np.bincount(queries))) > 1
    for query in range(20):
        observed = times[queries == query]
        assert 0 <= observed[0] <= 4
        np.testing.assert_array_equal(observed, np.arange(observed[0], 7))


def test_beta_is_recovered() -> None:
    y, x, queries, times = _simulate_panel(n_queries=400, beta=0.5, seed=42)
    fit = fit_two_way_fe(y, x, queries, times)
    beta_hat = float(fit["beta"][0])
    se = float(fit["se"][0])
    assert abs(beta_hat - 0.5) < 0.05
    assert beta_hat - 3.0 * se <= 0.5 <= beta_hat + 3.0 * se


def test_wcb_size_under_null() -> None:
    p_values = np.empty(150)
    for i in range(len(p_values)):
        seed = 1000 + i
        y, x, queries, times = _simulate_panel(n_queries=150, beta=0.0, seed=seed)
        fit = fit_two_way_fe(y, x, queries, times)
        p_values[i] = wild_cluster_bootstrap(fit, times, n_draws=199, seed=2000 + i)
    rejection_share = float(np.mean(p_values < 0.05))
    mean_p_value = float(np.mean(p_values))
    assert rejection_share <= 0.12, f"Null rejection share: {rejection_share:.3f}"
    assert mean_p_value > 0.35, f"Mean null p-value: {mean_p_value:.3f}"


def test_wcb_has_power() -> None:
    p_values = np.empty(40)
    for i in range(len(p_values)):
        y, x, queries, times = _simulate_panel(n_queries=300, beta=0.3, seed=3000 + i)
        fit = fit_two_way_fe(y, x, queries, times)
        p_values[i] = wild_cluster_bootstrap(fit, times, n_draws=199, seed=4000 + i)
    rejection_share = float(np.mean(p_values < 0.05))
    assert rejection_share >= 0.80, f"Power: {rejection_share:.3f}"
