"""S4-S6 pure functions: cross-fitted Procrustes distances, null bucket merging, SED+ with leave-target-out.

Registered in configs/s5_drift_v33.yaml before any measurement. No function reads downstream outcomes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import numpy as np

BUCKETS = ((0, 2), (3, 5), (6, 10**9))
MAD_FACTOR = 1.4826


def degree_bucket(degree: int) -> int:
    for index, (lo, hi) in enumerate(BUCKETS):
        if lo <= degree <= hi:
            return index
    raise ValueError(f"degree {degree} outside the registered buckets")


def stratified_folds(entities: Sequence[str], buckets: Sequence[int], salt: str, k: int) -> np.ndarray:
    """Fold index per entity: inside each bucket, rank by hash and take rank mod k (deterministic, stratified)."""
    folds = np.zeros(len(entities), dtype=int)
    for bucket in sorted(set(buckets)):
        members = [i for i, b in enumerate(buckets) if b == bucket]
        members.sort(key=lambda i: hashlib.sha256(f"s5-fold|{salt}|{entities[i]}".encode()).hexdigest())
        for rank, i in enumerate(members):
            folds[i] = rank % k
    return folds


def _procrustes(a_fit: np.ndarray, b_fit: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, float]]:
    ca, cb = a_fit.mean(axis=0), b_fit.mean(axis=0)
    u, s, vt = np.linalg.svd((b_fit - cb).T @ (a_fit - ca))
    q = u @ vt
    tolerance = s.max() * max(a_fit.shape) * np.finfo(float).eps if s.size else 0.0
    rank = int(np.sum(s > tolerance))
    full = min(a_fit.shape[1], a_fit.shape[0] - 1)
    return q, ca, cb, {"orthogonality_error": float(np.abs(q.T @ q - np.eye(q.shape[0])).max()),
                       "rank_fraction": rank / full if full > 0 else 0.0}


def _cosine_distance(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    denom = np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1)
    return 1.0 - np.sum(x * y, axis=1) / np.where(denom == 0, np.nan, denom)


def crossfit_distances(
    a: np.ndarray, b: np.ndarray, folds: np.ndarray, k: int,
    max_orthogonality_error: float = 1e-6, min_rank_fraction: float = 0.90, max_gap: float = 0.65,
) -> tuple[np.ndarray, list[dict[str, object]]]:
    """Per-row (1 - cosine) of ``b`` aligned onto ``a``, each row measured by a fit that excludes its own fold.

    Rows of a fold whose fit fails a diagnostic get NaN and the reason is recorded.
    """
    out = np.full(a.shape[0], np.nan)
    diagnostics: list[dict[str, object]] = []
    for fold in range(k):
        hold, fit = np.where(folds == fold)[0], np.where(folds != fold)[0]
        if len(hold) == 0 or len(fit) < 2:
            diagnostics.append({"fold": fold, "valid": False, "reason": "EMPTY_FOLD_OR_FIT"})
            continue
        q, ca, cb, geo = _procrustes(a[fit], b[fit])
        fit_dist = _cosine_distance(a[fit] - ca, (b[fit] - cb) @ q)
        hold_dist = _cosine_distance(a[hold] - ca, (b[hold] - cb) @ q)
        gap = float(np.nanmedian(hold_dist) - np.nanmedian(fit_dist))
        reasons = []
        if geo["orthogonality_error"] > max_orthogonality_error:
            reasons.append("ORTHOGONALITY")
        if geo["rank_fraction"] < min_rank_fraction:
            reasons.append("RANK")
        if gap > max_gap:
            reasons.append("FIT_HOLDOUT_GAP")
        diagnostics.append({"fold": fold, "valid": not reasons, "reason": ",".join(reasons) or None, "gap": gap,
                            "fit_median": float(np.nanmedian(fit_dist)), "hold_median": float(np.nanmedian(hold_dist)), **geo})
        if not reasons:
            out[hold] = hold_dist
    return out, diagnostics


def merged_groups(counts: Mapping[int, int], support: int) -> dict[int, tuple[int, ...]]:
    """Merge buckets whose reference (count - 1 after leave-target-out) is below ``support``.

    A sparse bucket merges with the adjacent bucket holding more entities (tie: left), repeating until every group
    has count - 1 >= support or only one group remains.
    """
    groups: list[list[int]] = [[b] for b in sorted(counts)]
    size = lambda g: sum(counts[b] for b in g)  # noqa: E731
    while len(groups) > 1:
        sparse = [i for i, g in enumerate(groups) if size(g) - 1 < support]
        if not sparse:
            break
        i = min(sparse, key=lambda j: size(groups[j]))
        left, right = i - 1, i + 1
        if left >= 0 and (right >= len(groups) or size(groups[left]) >= size(groups[right])):
            groups[left] += groups.pop(i)
        else:
            groups[i] += groups.pop(right)
    return {b: tuple(g) for g in groups for b in g}


def entity_scores(delta: np.ndarray, null_value: np.ndarray, buckets: np.ndarray, support: int, eps: float
                  ) -> dict[str, np.ndarray]:
    """Signed excess and SED+ per entity against a leave-target-out reference inside its (merged) bucket."""
    n = len(delta)
    available = np.isfinite(delta) & np.isfinite(null_value)
    counts = {int(b): int(np.sum((buckets == b) & available)) for b in np.unique(buckets)}
    groups = merged_groups(counts, support)
    excess = np.full(n, np.nan)
    sed = np.full(n, np.nan)
    ref_median = np.full(n, np.nan)
    ref_mad = np.full(n, np.nan)
    group_id = np.full(n, -1)
    for i in range(n):
        if not available[i]:
            continue
        members = [j for j in range(n) if available[j] and groups[int(buckets[j])] == groups[int(buckets[i])] and j != i]
        group_id[i] = min(groups[int(buckets[i])])
        if len(members) < support:
            continue
        ref = null_value[members]
        median = float(np.median(ref))
        mad = float(np.median(np.abs(ref - median)))
        ref_median[i], ref_mad[i] = median, mad
        excess[i] = delta[i] - median
        sed[i] = max(0.0, excess[i]) / (MAD_FACTOR * mad + eps)
    return {"signed_excess": excess, "sed_plus": sed, "reference_median": ref_median, "reference_mad": ref_mad,
            "group": group_id}
