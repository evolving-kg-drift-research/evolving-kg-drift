"""Versioned fixed-count, pretransition-degree anchor allocation without outcomes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from .anchors import AnchorSplit, compute_anchor_hash

FIXED_ANCHOR_VERSION = "fixed_degree_joint_sample_then_split_v1"


@dataclass(frozen=True)
class DegreeAllocation:
    degree: int
    available: int
    selected: int
    fit: int
    holdout: int


@dataclass(frozen=True)
class FixedAnchorPlan:
    version: str
    salt: str
    candidate_count: int
    candidate_hash: str
    pretransition_degrees_hash: str
    allocations: tuple[DegreeAllocation, ...]
    split: AnchorSplit


def largest_remainder_allocation(counts: Mapping[int, int], target: int) -> dict[int, int]:
    """Integer proportional allocation; ties prefer smaller degree values."""
    if (type(target) is not int or target < 0 or not counts
            or any(type(d) is not int or d < 0 or type(n) is not int or n < 0 for d, n in counts.items())):
        raise ValueError("Allocation requires integer nonnegative counts and target")
    total = sum(counts.values())
    if total <= 0 or target > total:
        raise ValueError("Insufficient population for fixed-count allocation")
    result = {degree: target * count // total for degree, count in sorted(counts.items())}
    left = target - sum(result.values())
    order = sorted(counts, key=lambda d: (-(target * counts[d] % total), d))
    for degree in order:
        if left == 0:
            break
        if result[degree] < counts[degree]:
            result[degree] += 1
            left -= 1
    if left or sum(result.values()) != target:
        raise ValueError("Fixed-count allocation could not be satisfied")
    return result


def select_fixed_stratified_anchors(
    candidates: Sequence[str], pretransition_degrees: Mapping[str, int],
    fit_count: int, holdout_count: int, salt: str,
) -> FixedAnchorPlan:
    """Jointly sample fit+holdout; allocate fit within that sample, holdout is remainder.

Only canonical IDs and pretransition degrees enter this function. For each
degree, sort by SHA-256(salt:degree:degree_value:entity_id), with ID tie-break.
Allocate the combined sample proportionally from persistent candidates, then
the fit quota proportionally from that sample; both use largest remainder.
"""
    if (type(fit_count) is not int or type(holdout_count) is not int
            or fit_count <= 0 or holdout_count <= 0 or not isinstance(salt, str) or not salt
            or not candidates or len(set(candidates)) != len(candidates)
            or any(not isinstance(e, str) or not e.strip() for e in candidates)):
        raise ValueError("Distinct nonempty IDs, positive fixed counts, and salt required")
    groups: dict[int, list[str]] = {}
    degree_rows = {}
    for entity in sorted(candidates):
        if entity not in pretransition_degrees:
            raise ValueError(f"Missing pretransition degree for {entity}")
        degree = pretransition_degrees[entity]
        if type(degree) is not int or degree < 0:
            raise ValueError("Pretransition degree must be a nonnegative integer")
        degree_rows[entity] = degree
        groups.setdefault(degree, []).append(entity)
    available = {d: len(es) for d, es in groups.items()}
    selected = largest_remainder_allocation(available, fit_count + holdout_count)
    fit_quotas = largest_remainder_allocation(selected, fit_count)
    fit, holdout, allocations = [], [], []
    for degree, entities in sorted(groups.items()):
        ranked = sorted(entities, key=lambda e: (
            hashlib.sha256(f"{salt}:degree:{degree}:{e}".encode()).hexdigest(), e))
        sample = ranked[:selected[degree]]
        fit.extend(sample[:fit_quotas[degree]])
        holdout.extend(sample[fit_quotas[degree]:])
        allocations.append(DegreeAllocation(degree, len(entities), len(sample),
                                            fit_quotas[degree], len(sample) - fit_quotas[degree]))
    split = AnchorSplit(tuple(sorted(fit)), tuple(sorted(holdout)),
                         compute_anchor_hash(fit), compute_anchor_hash(holdout))
    split.verify_disjoint()
    if len(fit) != fit_count or len(holdout) != holdout_count:
        raise ValueError("Anchor counts differ from the registered design")
    return FixedAnchorPlan(FIXED_ANCHOR_VERSION, salt, len(candidates), compute_anchor_hash(candidates),
                           hashlib.sha256(json.dumps(degree_rows, sort_keys=True).encode()).hexdigest(),
                           tuple(allocations), split)
