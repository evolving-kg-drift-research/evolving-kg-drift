"""Anchor Candidate Selection and Deterministic Disjoint Split.

Only allowed features are used:
  - Persistence across both snapshots (entity present in both endpoints)
  - Stable canonical IDs
  - Pre-transition degree/frequency for stratification (optional)

Strictly forbidden features (enforced by design):
  - No observed embedding drift
  - No future graph changes
  - No fact change / replacement / retraction labels
  - No RR / MRR / QA outcomes / H1 coefficients
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class AnchorSplit:
    """Disjoint deterministic anchor split."""

    fit_anchors: tuple[str, ...]
    holdout_anchors: tuple[str, ...]
    fit_hash: str
    holdout_hash: str

    def verify_disjoint(self) -> None:
        """Verifies that fit_anchors and holdout_anchors are strictly disjoint."""
        fit_set = set(self.fit_anchors)
        holdout_set = set(self.holdout_anchors)
        intersection = fit_set.intersection(holdout_set)
        if intersection:
            raise ValueError(f"Anchor split violation! Overlap found: {intersection}")


def compute_anchor_hash(anchors: Sequence[str]) -> str:
    """Computes deterministic SHA-256 of sorted anchor entity IDs."""
    sorted_anchors = sorted(anchors)
    raw = json.dumps(sorted_anchors, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def select_persistent_anchors(
    source_entities: Sequence[str],
    target_entities: Sequence[str],
) -> list[str]:
    """Extracts candidate anchors that appear in both source and target snapshots.

    Candidate selection relies ONLY on persistent presence across both snapshots.
    """
    intersection = set(source_entities).intersection(set(target_entities))
    return sorted(intersection)


def deterministic_hash_split(
    candidates: Sequence[str],
    fit_ratio: float = 0.6,
    salt: str = "kge_anchor_split_v1",
) -> AnchorSplit:
    """Splits candidate anchors into deterministic, disjoint fit and holdout sets.

    Sorting candidates by SHA-256(salt + entity_id) guarantees deterministic,
    leakage-free assignment.
    """
    if not candidates:
        return AnchorSplit(
            fit_anchors=(),
            holdout_anchors=(),
            fit_hash=compute_anchor_hash([]),
            holdout_hash=compute_anchor_hash([]),
        )

    # Sort each entity by its cryptographic hash
    def entity_key(e: str) -> str:
        return hashlib.sha256(f"{salt}:{e}".encode("utf-8")).hexdigest()

    sorted_by_hash = sorted(candidates, key=entity_key)

    n_total = len(sorted_by_hash)
    if n_total == 1:
        # Edge case: single anchor goes to fit
        fit_list = sorted_by_hash
        holdout_list = []
    else:
        n_fit = max(1, min(n_total - 1, int(round(n_total * fit_ratio))))
        fit_list = sorted_by_hash[:n_fit]
        holdout_list = sorted_by_hash[n_fit:]

    # Canonical alphabetical sorting within each group for stable hashing
    fit_tuple = tuple(sorted(fit_list))
    holdout_tuple = tuple(sorted(holdout_list))

    split = AnchorSplit(
        fit_anchors=fit_tuple,
        holdout_anchors=holdout_tuple,
        fit_hash=compute_anchor_hash(fit_tuple),
        holdout_hash=compute_anchor_hash(holdout_tuple),
    )
    split.verify_disjoint()
    return split
