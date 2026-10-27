"""Two-Way Fixed Effects OLS estimation, Transition-clustered WCB inference, and pseudo-drift falsification."""
from __future__ import annotations

import math
from typing import Any

import numpy as np


def two_way_demean(
    y: np.ndarray,
    x: np.ndarray,
    query_indices: np.ndarray,
    time_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Demean y and x across query fixed effects (i) and transition fixed effects (t).

    For balanced or unbalanced panel, alternating projections or explicit dummy demeaning.
    With balanced panel of N queries and T transitions:
      y_tilde = y - mean_i(y) - mean_t(y) + grand_mean(y)
    """
    n_queries = int(np.max(query_indices)) + 1
    n_times = int(np.max(time_indices)) + 1

    # Check balanced
    counts = np.zeros((n_queries, n_times))
    for q, t in zip(query_indices, time_indices):
        counts[q, t] += 1

    is_balanced = np.all(counts == 1)

    if is_balanced:
        # Reshape to (N, T)
        N = n_queries
        T = n_times
        y_grid = np.zeros((N, T))
        y_grid[query_indices, time_indices] = y

        mean_i = y_grid.mean(axis=1, keepdims=True)
        mean_t = y_grid.mean(axis=0, keepdims=True)
        grand_mean = y_grid.mean()
        y_tilde_grid = y_grid - mean_i - mean_t + grand_mean
        y_tilde = y_tilde_grid[query_indices, time_indices]

        # For x: shape (N, T, K) or (N, T)
        if x.ndim == 1:
            x_grid = np.zeros((N, T))
            x_grid[query_indices, time_indices] = x
            x_mean_i = x_grid.mean(axis=1, keepdims=True)
            x_mean_t = x_grid.mean(axis=0, keepdims=True)
            x_grand = x_grid.mean()
            x_tilde_grid = x_grid - x_mean_i - x_mean_t + x_grand
            x_tilde = x_tilde_grid[query_indices, time_indices]
        else:
            K = x.shape[1]
            x_tilde = np.zeros_like(x)
            for k in range(K):
                xg = np.zeros((N, T))
                xg[query_indices, time_indices] = x[:, k]
                x_mean_i = xg.mean(axis=1, keepdims=True)
                x_mean_t = xg.mean(axis=0, keepdims=True)
                x_grand = xg.mean()
                xt_g = xg - x_mean_i - x_mean_t + x_grand
                x_tilde[:, k] = xt_g[query_indices, time_indices]

        return y_tilde, x_tilde

    # Unbalanced: iterative within transformation (Gauss-Seidel / Method of Alternating Projections)
    y_tilde = y.copy()
    x_tilde = x.copy()
    for _ in range(50):
        # Demean by query
        for q in range(n_queries):
            idx = (query_indices == q)
            if np.any(idx):
                y_tilde[idx] -= np.mean(y_tilde[idx])
                if x_tilde.ndim == 1:
                    x_tilde[idx] -= np.mean(x_tilde[idx])
                else:
                    x_tilde[idx] -= np.mean(x_tilde[idx], axis=0)
        # Demean by time
        for t in range(n_times):
            idx = (time_indices == t)
            if np.any(idx):
                y_tilde[idx] -= np.mean(y_tilde[idx])
                if x_tilde.ndim == 1:
                    x_tilde[idx] -= np.mean(x_tilde[idx])
                else:
                    x_tilde[idx] -= np.mean(x_tilde[idx], axis=0)

    return y_tilde, x_tilde


def fit_two_way_fe(
    y: np.ndarray,
    x: np.ndarray,
    query_indices: np.ndarray,
    time_indices: np.ndarray,
) -> dict[str, Any]:
    """Fit Two-Way Fixed Effects OLS on demeaned panel with transition-clustered SE."""
    if x.ndim == 1:
        x_mat = x.reshape(-1, 1)
    else:
        x_mat = x

    y_tilde, x_tilde = two_way_demean(y, x_mat, query_indices, time_indices)

    # OLS: beta = (X'^X)^(-1) X'Y
    XtX = x_tilde.T @ x_tilde
    if np.linalg.matrix_rank(XtX) < x_mat.shape[1]:
        raise ValueError("Degenerate design matrix in Two-Way FE")

    XtX_inv = np.linalg.inv(XtX)
    beta = XtX_inv @ (x_tilde.T @ y_tilde)

    residuals = y_tilde - x_tilde @ beta

    # Transition-clustered standard errors (clustered by time_indices)
    unique_clusters = np.unique(time_indices)
    G = len(unique_clusters)
    N_total = len(y)
    K = x_mat.shape[1]
    df_adjust = (G / (G - 1)) * ((N_total - 1) / (N_total - K))

    meat = np.zeros((K, K))
    cluster_scores = []
    for g in unique_clusters:
        idx = (time_indices == g)
        score_g = x_tilde[idx].T @ residuals[idx]
        meat += np.outer(score_g, score_g)
        cluster_scores.append(score_g)

    cluster_cov = df_adjust * (XtX_inv @ meat @ XtX_inv)
    se = np.sqrt(np.diag(cluster_cov))
    t_stat = beta / se

    return {
        "beta": beta.flatten().tolist(),
        "se": se.flatten().tolist(),
        "t_stat": t_stat.flatten().tolist(),
        "residuals": residuals,
        "x_tilde": x_tilde,
        "y_tilde": y_tilde,
        "XtX_inv": XtX_inv,
        "cluster_scores": cluster_scores,
        "n_obs": N_total,
        "n_clusters": G,
    }


def wild_cluster_bootstrap(
    fit_result: dict[str, Any],
    time_indices: np.ndarray,
    n_draws: int = 999,
    seed: int = 101,
) -> float:
    """Restricted Wild Cluster Bootstrap-t test for H0: beta = 0 using Webb 6-point distribution."""
    rng = np.random.default_rng(seed)
    unique_clusters = np.unique(time_indices)
    G = len(unique_clusters)

    x_tilde = fit_result["x_tilde"]
    residuals = fit_result["residuals"]
    t_stat_orig = abs(fit_result["t_stat"][0])
    XtX_inv = fit_result["XtX_inv"]
    K = x_tilde.shape[1]
    N_total = len(time_indices)
    df_adjust = (G / (G - 1)) * ((N_total - 1) / (N_total - K))

    # Webb 6-point distribution: {-sqrt(3/2), -sqrt(2/2), -sqrt(1/2), sqrt(1/2), sqrt(2/2), sqrt(3/2)}
    webb_points = np.array([
        -math.sqrt(1.5), -1.0, -math.sqrt(0.5),
        math.sqrt(0.5), 1.0, math.sqrt(1.5),
    ])

    extreme_count = 0
    for _ in range(n_draws):
        # Draw one weight per cluster
        v_g = rng.choice(webb_points, size=G)
        v = np.zeros(N_total)
        for i, g in enumerate(unique_clusters):
            v[time_indices == g] = v_g[i]

        # Under H0: beta = 0, y_star = v * residuals
        y_star = v * residuals

        # OLS estimate under bootstrap draw
        beta_star = XtX_inv @ (x_tilde.T @ y_star)
        res_star = y_star - x_tilde @ beta_star

        # Clustered variance for bootstrap draw
        meat_star = np.zeros((K, K))
        for g in unique_clusters:
            idx = (time_indices == g)
            score_star_g = x_tilde[idx].T @ res_star[idx]
            meat_star += np.outer(score_star_g, score_star_g)

        cov_star = df_adjust * (XtX_inv @ meat_star @ XtX_inv)
        se_star = math.sqrt(cov_star[0, 0])
        t_star = abs(beta_star[0] / se_star) if se_star > 1e-12 else 0.0

        if t_star >= t_stat_orig:
            extreme_count += 1

    p_value = (extreme_count + 1) / (n_draws + 1)
    return p_value
