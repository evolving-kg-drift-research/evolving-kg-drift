r"""Centered Orthogonal Procrustes Alignment and Diagnostics.

Solves the Procrustes problem:
    Q* = argmin_{Q^T Q = I} ||X_c Q - Y_c||_F^2

Applies centering based on fit anchors:
  - Entity vector translation: x' = (x - \mu_{prev}) Q + \mu_{next}
  - Relation vector rotation: r' = r Q
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Sequence

try:
    from ..kge.math_utils import (
        dot_product,
        l2_distance,
        l2_norm,
        matrix_mult,
        matrix_transpose,
        one_minus_cosine,
        svd_ortho_procrustes,
    )
except (ImportError, ValueError):
    from kge.math_utils import (
        dot_product,
        l2_distance,
        l2_norm,
        matrix_mult,
        matrix_transpose,
        one_minus_cosine,
        svd_ortho_procrustes,
    )
from .anchors import AnchorSplit


@dataclass
class AlignmentDiagnostics:
    """Diagnostic outputs from Centered Orthogonal Procrustes."""

    alignment_type: str  # 'cross_time' or 'same_snapshot_cross_seed'
    dimension: int
    num_fit_anchors: int
    num_holdout_anchors: int
    singular_values: list[float]
    numerical_rank: int
    fit_residual: float
    holdout_residual: float
    fit_holdout_gap: float
    orthogonality_error: float
    anchor_fit_hash: str
    anchor_holdout_hash: str
    alignment_hash: str = ""

    def __post_init__(self) -> None:
        if not self.alignment_hash:
            self.alignment_hash = self.compute_alignment_hash()

    def compute_alignment_hash(self) -> str:
        payload = {
            "alignment_type": self.alignment_type,
            "dimension": self.dimension,
            "num_fit_anchors": self.num_fit_anchors,
            "num_holdout_anchors": self.num_holdout_anchors,
            "singular_values": [round(s, 7) for s in self.singular_values],
            "numerical_rank": self.numerical_rank,
            "fit_residual": round(self.fit_residual, 7),
            "holdout_residual": round(self.holdout_residual, 7),
            "orthogonality_error": round(self.orthogonality_error, 7),
            "anchor_fit_hash": self.anchor_fit_hash,
            "anchor_holdout_hash": self.anchor_holdout_hash,
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class ProcrustesAlignmentResult:
    """Holds the orthogonal transformation matrix Q, means, and diagnostic metadata."""

    def __init__(
        self,
        Q: list[list[float]],
        source_mean: list[float],
        target_mean: list[float],
        diagnostics: AlignmentDiagnostics,
    ) -> None:
        self.Q = Q
        self.source_mean = source_mean
        self.target_mean = target_mean
        self.diagnostics = diagnostics
        self.dimension = len(source_mean)

    def align_entity_vector(self, x: Sequence[float]) -> list[float]:
        r"""Aligns source entity vector: x' = (x - \mu_{source}) Q + \mu_{target}."""
        # 1. Centering: x_c = x - \mu_{source}
        x_c = [x[i] - self.source_mean[i] for i in range(self.dimension)]
        # 2. Rotation: x_rot = x_c @ Q
        # Since x_c is 1 x d and Q is d x d: (x_rot)_j = sum_i x_c[i] * Q[i][j]
        x_rot = [
            sum(x_c[i] * self.Q[i][j] for i in range(self.dimension))
            for j in range(self.dimension)
        ]
        # 3. Target translation: x' = x_rot + \mu_{target}
        return [x_rot[j] + self.target_mean[j] for j in range(self.dimension)]

    def align_relation_vector(self, r: Sequence[float]) -> list[float]:
        """Aligns source relation vector: r' = r Q (rotation only, no translation)."""
        return [
            sum(r[i] * self.Q[i][j] for i in range(self.dimension))
            for j in range(self.dimension)
        ]

    def align_all_entities(
        self,
        entity_embeddings: dict[str, list[float]],
    ) -> dict[str, list[float]]:
        """Aligns all entity embeddings in a given dictionary."""
        return {
            e: self.align_entity_vector(vec)
            for e, vec in entity_embeddings.items()
        }


def compute_orthogonality_error(Q: list[list[float]]) -> float:
    """Computes Frobenius norm ||Q^T Q - I||_F."""
    d = len(Q)
    total_sq = 0.0
    for i in range(d):
        for j in range(d):
            val = sum(Q[k][i] * Q[k][j] for k in range(d))
            expected = 1.0 if i == j else 0.0
            diff = val - expected
            total_sq += diff * diff
    return math.sqrt(total_sq)


def align_embeddings_procrustes(
    source_embeddings: dict[str, list[float]],
    target_embeddings: dict[str, list[float]],
    anchor_split: AnchorSplit,
    alignment_type: str = "cross_time",
) -> ProcrustesAlignmentResult:
    """Performs Centered Orthogonal Procrustes alignment based on fit anchors.

    Args:
        source_embeddings: Entity embeddings in source coordinate frame.
        target_embeddings: Entity embeddings in target coordinate frame.
        anchor_split: Deterministic disjoint fit and holdout anchors.
        alignment_type: 'cross_time' (for temporal drift) or 'same_snapshot_cross_seed' (for null).
    """
    fit_anchors = anchor_split.fit_anchors
    if not fit_anchors:
        raise ValueError("Cannot perform Procrustes alignment with 0 fit anchors.")

    # Check anchor presence in both coordinate systems
    for a in fit_anchors:
        if a not in source_embeddings:
            raise KeyError(f"Fit anchor '{a}' missing from source embeddings.")
        if a not in target_embeddings:
            raise KeyError(f"Fit anchor '{a}' missing from target embeddings.")

    sample_vec = next(iter(source_embeddings.values()))
    d = len(sample_vec)
    n_fit = len(fit_anchors)

    # 1. Compute means over fit anchors
    source_mean = [0.0] * d
    target_mean = [0.0] * d
    for a in fit_anchors:
        s_v = source_embeddings[a]
        t_v = target_embeddings[a]
        for i in range(d):
            source_mean[i] += s_v[i]
            target_mean[i] += t_v[i]
    source_mean = [x / n_fit for x in source_mean]
    target_mean = [x / n_fit for x in target_mean]

    # 2. Centered matrices for fit anchors: X_c, Y_c
    # Compute cross-covariance matrix M = X_c^T Y_c (d x d)
    M = [[0.0] * d for _ in range(d)]
    for a in fit_anchors:
        s_c = [source_embeddings[a][i] - source_mean[i] for i in range(d)]
        t_c = [target_embeddings[a][j] - target_mean[j] for j in range(d)]
        for i in range(d):
            for j in range(d):
                M[i][j] += s_c[i] * t_c[j]

    # 3. SVD of M: M = U @ diag(s) @ Vt
    U, s, Vt = svd_ortho_procrustes(M)

    # 4. Optimal Orthogonal Matrix: Q = U @ Vt
    Q = matrix_mult(U, Vt)

    # 5. Diagnostics
    ortho_err = compute_orthogonality_error(Q)

    # Numerical rank: count of singular values > 1e-6 * max(s)
    s_max = s[0] if s else 0.0
    rank_tol = 1e-6 * max(1e-12, s_max)
    numerical_rank = sum(1 for val in s if val > rank_tol)

    # To compute fit/holdout residuals we need to align vectors using Q and means.
    # Build a lightweight alignment helper inline.
    def _align_entity(x: Sequence[float]) -> list[float]:
        """Aligns source entity vector: x' = (x - source_mean) Q + target_mean."""
        x_c = [x[i] - source_mean[i] for i in range(d)]
        x_rot = [
            sum(x_c[i] * Q[i][j] for i in range(d))
            for j in range(d)
        ]
        return [x_rot[j] + target_mean[j] for j in range(d)]

    # Fit residual: RMSE on fit anchors
    fit_sq_err = 0.0
    for a in fit_anchors:
        aligned_v = _align_entity(source_embeddings[a])
        dist = l2_distance(aligned_v, target_embeddings[a])
        fit_sq_err += dist * dist
    fit_rmse = math.sqrt(fit_sq_err / n_fit)

    # Holdout residual: RMSE on holdout anchors
    holdout_anchors = [
        a for a in anchor_split.holdout_anchors
        if a in source_embeddings and a in target_embeddings
    ]
    if holdout_anchors:
        holdout_sq_err = 0.0
        for a in holdout_anchors:
            aligned_v = _align_entity(source_embeddings[a])
            dist = l2_distance(aligned_v, target_embeddings[a])
            holdout_sq_err += dist * dist
        holdout_rmse = math.sqrt(holdout_sq_err / len(holdout_anchors))
    else:
        holdout_rmse = 0.0

    gap = abs(holdout_rmse - fit_rmse)

    diagnostics = AlignmentDiagnostics(
        alignment_type=alignment_type,
        dimension=d,
        num_fit_anchors=n_fit,
        num_holdout_anchors=len(holdout_anchors),
        singular_values=s,
        numerical_rank=numerical_rank,
        fit_residual=fit_rmse,
        holdout_residual=holdout_rmse,
        fit_holdout_gap=gap,
        orthogonality_error=ortho_err,
        anchor_fit_hash=anchor_split.fit_hash,
        anchor_holdout_hash=anchor_split.holdout_hash,
    )

    result_obj = ProcrustesAlignmentResult(
        Q=Q,
        source_mean=source_mean,
        target_mean=target_mean,
        diagnostics=diagnostics,
    )
    return result_obj
