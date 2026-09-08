"""Mathematical utilities for KGE and Procrustes alignment.

Supports both NumPy (accelerated) and high-precision pure-Python fallback.
"""

from __future__ import annotations

import math
from typing import Sequence

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def dot_product(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Computes Euclidean dot product between two 1D vectors."""
    if HAS_NUMPY and isinstance(v1, np.ndarray) and isinstance(v2, np.ndarray):
        return float(np.dot(v1, v2))
    return sum(x * y for x, y in zip(v1, v2))


def l2_norm(v: Sequence[float]) -> float:
    """Computes L2 norm of a vector."""
    if HAS_NUMPY and isinstance(v, np.ndarray):
        return float(np.linalg.norm(v))
    return math.sqrt(sum(x * x for x in v))


def normalize_vector(v: Sequence[float], eps: float = 1e-12) -> list[float]:
    """Normalizes vector to unit L2 norm."""
    norm = l2_norm(v)
    if norm < eps:
        return [0.0] * len(v)
    return [x / norm for x in v]


def l2_distance(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Computes Euclidean L2 distance between two vectors."""
    if HAS_NUMPY and isinstance(v1, np.ndarray) and isinstance(v2, np.ndarray):
        return float(np.linalg.norm(v1 - v2))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(v1, v2)))


def cosine_similarity(v1: Sequence[float], v2: Sequence[float], eps: float = 1e-12) -> float:
    """Computes cosine similarity between two vectors, clamped to [-1.0, 1.0]."""
    norm1 = l2_norm(v1)
    norm2 = l2_norm(v2)
    if norm1 < eps or norm2 < eps:
        return 0.0
    dot = dot_product(v1, v2)
    cos = dot / (norm1 * norm2)
    # Clamp to avoid numerical precision exceeding [-1, 1]
    return max(-1.0, min(1.0, cos))


def one_minus_cosine(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Computes 1 - cosine_similarity(v1, v2), guaranteed non-negative within floating tolerance."""
    cos = cosine_similarity(v1, v2)
    val = 1.0 - cos
    return max(0.0, val)


def matrix_mult(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> list[list[float]]:
    """Multiplies matrix A (m x k) by matrix B (k x n) -> (m x n)."""
    if HAS_NUMPY:
        arr_A = np.asarray(A, dtype=np.float64)
        arr_B = np.asarray(B, dtype=np.float64)
        return np.matmul(arr_A, arr_B).tolist()

    m = len(A)
    k = len(A[0])
    n = len(B[0])
    result = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for p in range(k):
            a_ip = A[i][p]
            for j in range(n):
                result[i][j] += a_ip * B[p][j]
    return result


def matrix_transpose(A: Sequence[Sequence[float]]) -> list[list[float]]:
    """Transposes matrix A."""
    if HAS_NUMPY:
        return np.asarray(A, dtype=np.float64).T.tolist()
    m = len(A)
    n = len(A[0])
    return [[A[i][j] for i in range(m)] for j in range(n)]


def svd_ortho_procrustes(M: Sequence[Sequence[float]]) -> tuple[list[list[float]], list[float], list[list[float]]]:
    """Computes SVD of square matrix M: M = U @ diag(s) @ Vt.

    Applies canonical null-space alignment: for degenerate singular values (rank < d),
    the null-space basis of U is canonically aligned to V via Gram-Schmidt projection
    so that Q = U @ Vt preserves the unconstrained subspace without arbitrary rotation
    (and yields strictly Q = I when source and target are identical).

    Returns:
        U: left singular vectors (columns)
        s: singular values sorted descending
        Vt: right singular vectors (rows), such that Q = U @ Vt solves Orthogonal Procrustes.
    """
    d = len(M)
    if HAS_NUMPY:
        arr_M = np.asarray(M, dtype=np.float64)
        U, s, Vt = np.linalg.svd(arr_M, full_matrices=True)
        s_max = float(s[0]) if len(s) > 0 else 1.0
        tol = 1e-10 * max(1e-12, s_max)
        r = int(np.sum(s > tol))
        if r < d:
            V = Vt.T
            U_fixed = np.zeros_like(U)
            U_fixed[:, :r] = U[:, :r]
            for k in range(r, d):
                cand = V[:, k].copy()
                for j in range(k):
                    cand -= np.dot(cand, U_fixed[:, j]) * U_fixed[:, j]
                norm_c = float(np.linalg.norm(cand))
                if norm_c > 1e-8:
                    U_fixed[:, k] = cand / norm_c
                else:
                    for trial in range(d):
                        e = np.zeros(d)
                        e[trial] = 1.0
                        for j in range(k):
                            e -= np.dot(e, U_fixed[:, j]) * U_fixed[:, j]
                        norm_e = float(np.linalg.norm(e))
                        if norm_e > 1e-8:
                            U_fixed[:, k] = e / norm_e
                            break
            U = U_fixed
        return U.tolist(), s.tolist(), Vt.tolist()

    # Fallback for pure Python: One-sided Jacobi SVD for square matrix M
    # Start with V = I, B = M
    V = [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
    B = [list(row) for row in M]  # copy

    max_sweeps = 50
    tol = 1e-12
    for _ in range(max_sweeps):
        converged = True
        for i in range(d - 1):
            for j in range(i + 1, d):
                # Columns i and j of B
                bi = [B[k][i] for k in range(d)]
                bj = [B[k][j] for k in range(d)]
                alpha = sum(x * x for x in bi)
                beta = sum(x * x for x in bj)
                gamma = sum(x * y for x, y in zip(bi, bj))

                if abs(gamma) > tol * math.sqrt(max(1e-18, alpha * beta)):
                    converged = False
                    zeta = (beta - alpha) / (2.0 * gamma)
                    t = math.copysign(1.0 / (abs(zeta) + math.sqrt(1.0 + zeta * zeta)), zeta)
                    c = 1.0 / math.sqrt(1.0 + t * t)
                    s_val = c * t

                    # Update columns of B
                    for k in range(d):
                        bik = B[k][i]
                        bjk = B[k][j]
                        B[k][i] = c * bik - s_val * bjk
                        B[k][j] = s_val * bik + c * bjk

                    # Update columns of V
                    for k in range(d):
                        vik = V[k][i]
                        vjk = V[k][j]
                        V[k][i] = c * vik - s_val * vjk
                        V[k][j] = s_val * vik + c * vjk
        if converged:
            break

    # Singular values are norms of columns of B
    s_raw = [math.sqrt(sum(B[k][j] ** 2 for k in range(d))) for j in range(d)]

    # Sort descending by singular value
    indices = sorted(range(d), key=lambda idx: s_raw[idx], reverse=True)
    s_sorted = [s_raw[idx] for idx in indices]
    V_sorted = [[V[r][idx] for idx in indices] for r in range(d)]

    s_max = s_sorted[0] if s_sorted else 1.0
    rank_tol = 1e-10 * max(1e-12, s_max)
    r_rank = sum(1 for val in s_sorted if val > rank_tol)

    U = [[0.0] * d for _ in range(d)]
    # Set non-degenerate columns of U
    for j in range(r_rank):
        orig_idx = indices[j]
        for k in range(d):
            U[k][j] = B[k][orig_idx] / s_sorted[j]

    # Canonically complete null space of U using V columns
    for j in range(r_rank, d):
        cand = [V_sorted[k][j] for k in range(d)]
        for prev in range(j):
            proj = sum(cand[k] * U[k][prev] for k in range(d))
            for k in range(d):
                cand[k] -= proj * U[k][prev]
        norm_c = math.sqrt(sum(x * x for x in cand))
        if norm_c > 1e-8:
            for k in range(d):
                U[k][j] = cand[k] / norm_c
        else:
            for trial in range(d):
                e = [1.0 if k == trial else 0.0 for k in range(d)]
                for prev in range(j):
                    proj_e = sum(e[k] * U[k][prev] for k in range(d))
                    for k in range(d):
                        e[k] -= proj_e * U[k][prev]
                norm_e = math.sqrt(sum(x * x for x in e))
                if norm_e > 1e-8:
                    for k in range(d):
                        U[k][j] = e[k] / norm_e
                    break

    Vt = matrix_transpose(V_sorted)
    return U, s_sorted, Vt
