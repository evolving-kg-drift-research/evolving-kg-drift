"""Unit tests for Two-Way Fixed Effects OLS and Wild Cluster Bootstrap."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("twfe", ROOT / "src/statistics/two_way_fixed_effects.py")
assert _spec and _spec.loader
_twfe = importlib.util.module_from_spec(_spec)
sys.modules["twfe"] = _twfe
_spec.loader.exec_module(_twfe)
fit_two_way_fe = _twfe.fit_two_way_fe
two_way_demean = _twfe.two_way_demean
wild_cluster_bootstrap = _twfe.wild_cluster_bootstrap


def test_two_way_demean_absorbs_query_and_time_fixed_effects() -> None:
    # 3 queries, 4 transitions
    N = 3
    T = 4
    alpha = np.array([10.0, 20.0, 30.0])
    gamma = np.array([1.0, 2.0, 3.0, 4.0])

    q_idx = np.repeat(np.arange(N), T)
    t_idx = np.tile(np.arange(T), N)

    # Pure fixed effects + zero residual
    y = np.array([alpha[q] + gamma[t] for q, t in zip(q_idx, t_idx)])
    x = np.random.randn(N * T)

    y_tilde, _ = two_way_demean(y, x, q_idx, t_idx)

    # All pure fixed effects should demean to 0
    np.testing.assert_allclose(y_tilde, 0.0, atol=1e-10)


def test_fit_two_way_fe_recovers_known_beta() -> None:
    N = 20
    T = 5
    true_beta = -0.45

    q_idx = np.repeat(np.arange(N), T)
    t_idx = np.tile(np.arange(T), N)

    alpha = np.random.randn(N) * 2.0
    gamma = np.random.randn(T) * 1.5

    x = np.random.randn(N * T)
    noise = np.random.randn(N * T) * 0.05

    y = np.array([alpha[q] + gamma[t] + true_beta * x[i] + noise[i]
                  for i, (q, t) in enumerate(zip(q_idx, t_idx))])

    res = fit_two_way_fe(y, x, q_idx, t_idx)
    assert abs(res["beta"][0] - true_beta) < 0.05
    assert res["t_stat"][0] < -2.0  # highly significant negative effect

    p_val = wild_cluster_bootstrap(res, t_idx, n_draws=199, seed=42)
    assert p_val < 0.05
