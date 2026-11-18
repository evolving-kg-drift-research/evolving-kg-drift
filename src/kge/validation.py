"""Backbone validation helpers (S3): held-out folds, filtered ranking, baselines, convergence, noise floor.

Pure functions. Nothing here reads drift, RR/MRR of the QA panel or H1; it only judges embedding quality
and stability, which the protocol allows as selection evidence.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence

import numpy as np

Triple = tuple[str, str, str]


def _key(salt: str, snapshot_id: str, triple: Triple) -> int:
    return int(hashlib.sha256(f"{salt}|{snapshot_id}|{'|'.join(triple)}".encode()).hexdigest()[:12], 16)


def make_folds(triples: Sequence[Triple], k: int, snapshot_id: str, salt: str = "s3-valfold-v1") -> list[list[Triple]]:
    """Hash-disjoint validation folds whose removal never orphans an entity or a relation.

    A triple joins fold ``key % k`` only if, after removing it (together with earlier accepted triples of
    the same fold), both endpoints keep degree >= 1 and its relation keeps >= 1 triple in the training part.
    """
    degree: Counter[str] = Counter()
    relation: Counter[str] = Counter()
    for h, r, t in triples:
        degree[h] += 1
        degree[t] += 1
        relation[r] += 1
    folds: list[list[Triple]] = []
    for fold in range(k):
        deg, rel = Counter(degree), Counter(relation)
        chosen: list[Triple] = []
        candidates = sorted((tr for tr in triples if _key(salt, snapshot_id, tr) % k == fold),
                            key=lambda tr: _key(salt, snapshot_id, tr))
        for h, r, t in candidates:
            if h != t and deg[h] >= 2 and deg[t] >= 2 and rel[r] >= 2:
                chosen.append((h, r, t))
                deg[h] -= 1
                deg[t] -= 1
                rel[r] -= 1
        folds.append(chosen)
    return folds


def _rank(target_score: float, scores: np.ndarray, excluded: np.ndarray) -> float:
    """Filtered rank with average tie handling; ``excluded`` candidates are ignored."""
    keep = ~excluded
    better = int(np.sum(scores[keep] > target_score))
    ties = int(np.sum(scores[keep] == target_score)) - 1
    return 1.0 + better + 0.5 * max(ties, 0)


def _truth_maps(all_triples: Sequence[Triple], e2i: Mapping[str, int]):
    tails: dict[tuple[str, str], set[int]] = defaultdict(set)
    heads: dict[tuple[str, str], set[int]] = defaultdict(set)
    for h, r, t in all_triples:
        tails[(h, r)].add(e2i[t])
        heads[(r, t)].add(e2i[h])
    return tails, heads


def filtered_reciprocal_ranks(
    entity: np.ndarray, relation: np.ndarray, e2i: Mapping[str, int], r2i: Mapping[str, int],
    held_out: Sequence[Triple], all_triples: Sequence[Triple],
) -> np.ndarray:
    """Per held-out triple: mean of tail- and head-prediction reciprocal ranks (filtered by all known triples)."""
    tails, heads = _truth_maps(all_triples, e2i)
    out = np.zeros(len(held_out))
    n = entity.shape[0]
    for i, (h, r, t) in enumerate(held_out):
        hi, ri, ti = e2i[h], r2i[r], e2i[t]
        rr = []
        for target, scores, others in (
            (ti, -np.linalg.norm(entity[hi] + relation[ri] - entity, axis=1), tails[(h, r)]),
            (hi, -np.linalg.norm(entity + relation[ri] - entity[ti], axis=1), heads[(r, t)]),
        ):
            mask = np.zeros(n, dtype=bool)
            mask[list(others - {target})] = True
            rr.append(1.0 / _rank(scores[target], scores, mask))
        out[i] = sum(rr) / 2
    return out


def frequency_baseline_reciprocal_ranks(
    e2i: Mapping[str, int], train: Sequence[Triple], held_out: Sequence[Triple], all_triples: Sequence[Triple],
) -> np.ndarray:
    """Baseline: rank candidates by how often they were tail (head) of the relation in training."""
    n = len(e2i)
    tail_count: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n))
    head_count: dict[str, np.ndarray] = defaultdict(lambda: np.zeros(n))
    for h, r, t in train:
        tail_count[r][e2i[t]] += 1
        head_count[r][e2i[h]] += 1
    tails, heads = _truth_maps(all_triples, e2i)
    out = np.zeros(len(held_out))
    for i, (h, r, t) in enumerate(held_out):
        rr = []
        for target, scores, others in ((e2i[t], tail_count[r], tails[(h, r)]), (e2i[h], head_count[r], heads[(r, t)])):
            mask = np.zeros(n, dtype=bool)
            mask[list(others - {target})] = True
            rr.append(1.0 / _rank(scores[target], scores, mask))
        out[i] = sum(rr) / 2
    return out


def random_baseline_mrr(n_candidates: int) -> float:
    """Expected reciprocal rank of a uniformly random ranking over ``n_candidates``."""
    return float(sum(1.0 / k for k in range(1, n_candidates + 1)) / n_candidates)


def bootstrap_ci(values: Sequence[float], draws: int, seed: int, level: float = 0.95) -> tuple[float, float, float]:
    """(mean, lower, upper) percentile bootstrap over the held-out triples."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return math.nan, math.nan, math.nan
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(draws, arr.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [(1 - level) / 2, 1 - (1 - level) / 2])
    return float(arr.mean()), float(lo), float(hi)


def plateau_converged(
    losses: Sequence[float], block: int = 10, relative_tolerance: float = 0.01,
    absolute_tolerance: float = 0.002, min_loss_reduction: float = 0.75,
) -> dict[str, object]:
    """Plateau test on the last two ``block``-epoch means plus a minimum overall reduction."""
    if len(losses) < 2 * block or not all(math.isfinite(x) for x in losses):
        return {"converged": False, "reason": "too_short_or_non_finite"}
    last = float(np.mean(losses[-block:]))
    before = float(np.mean(losses[-2 * block:-block]))
    change = abs(last - before)
    plateau = change <= max(relative_tolerance * before, absolute_tolerance)
    reduced = float(np.mean(losses[-block:])) <= (1.0 - min_loss_reduction) * losses[0]
    return {"converged": bool(plateau and reduced), "plateau": bool(plateau), "reduced": bool(reduced),
            "last_block_mean": last, "previous_block_mean": before, "first_epoch_loss": float(losses[0])}


def noise_aware_converged(
    losses: Sequence[float], block: int = 20, z: float = 2.0, max_last_to_first: float = 0.5,
) -> dict[str, object]:
    """Gate v2: last two ``block``-epoch means differ by <= z standard errors, and the loss has fallen.

    The standard error ignores SGD autocorrelation, so the plateau test is slightly lenient.
    """
    if len(losses) < 2 * block or not all(math.isfinite(x) for x in losses):
        return {"converged": False, "reason": "too_short_or_non_finite"}
    last = np.asarray(losses[-block:], dtype=float)
    prev = np.asarray(losses[-2 * block:-block], dtype=float)
    se = math.sqrt(last.var(ddof=1) / block + prev.var(ddof=1) / block)
    diff = abs(float(last.mean() - prev.mean()))
    plateau = diff <= z * se
    learned = float(last.mean()) <= max_last_to_first * losses[0]
    return {"converged": bool(plateau and learned), "plateau": bool(plateau), "learned": bool(learned),
            "abs_difference": diff, "standard_error": se, "last_block_mean": float(last.mean()),
            "first_epoch_loss": float(losses[0])}


def stability_plateau(noise_by_epoch: Mapping[int, float], epoch: int, next_epoch: int, tolerance: float) -> bool:
    """C2 rule: training further (epoch -> next_epoch) lowers the cross-seed noise floor by at most ``tolerance``."""
    now, later = noise_by_epoch[epoch], noise_by_epoch[next_epoch]
    return bool(math.isfinite(now) and math.isfinite(later) and now - later <= tolerance)


def procrustes_holdout_distance(a: np.ndarray, b: np.ndarray, fit: Sequence[int], hold: Sequence[int]) -> np.ndarray:
    """Centred orthogonal Procrustes fitted on ``fit`` rows; per-row (1 - cosine) on ``hold`` rows."""
    ca, cb = a[list(fit)].mean(axis=0), b[list(fit)].mean(axis=0)
    u, _, vt = np.linalg.svd((b[list(fit)] - cb).T @ (a[list(fit)] - ca))
    q = u @ vt
    x, y = a[list(hold)] - ca, (b[list(hold)] - cb) @ q
    denom = np.linalg.norm(x, axis=1) * np.linalg.norm(y, axis=1)
    return 1.0 - np.sum(x * y, axis=1) / np.where(denom == 0, np.nan, denom)
