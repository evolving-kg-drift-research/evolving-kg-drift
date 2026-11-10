"""Canonical-ID split contracts; no model outcomes or future snapshots are inputs."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass

from .contract import SnapshotDataset

TripleTuple = tuple[str, str, str]


def content_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ValidationSplit:
    train: tuple[TripleTuple, ...]
    validation: tuple[TripleTuple, ...]
    version: str

    def validate(self, dataset: SnapshotDataset) -> None:
        train, validation = set(self.train), set(self.validation)
        original = {t.to_tuple() for t in dataset.triples}
        if (not self.version or not train or not validation or train & validation
                or train | validation != original or len(train) != len(self.train)
                or len(validation) != len(self.validation)):
            raise ValueError("Invalid disjoint/exhaustive nonempty validation partition")
        entities = {e for h, _, t in train for e in (h, t)}
        relations = {r for _, r, _ in train}
        if any(h not in entities or t not in entities or r not in relations for h, r, t in validation):
            raise ValueError("Validation entity/relation coverage is absent from training")

    def descriptor(self) -> dict:
        return {"version": self.version, "train": sorted(self.train), "validation": sorted(self.validation)}

    @property
    def sha256(self) -> str:
        return content_hash(self.descriptor())


def coverage_split(dataset: SnapshotDataset, fraction: float, salt: str) -> ValidationSplit:
    """Existing pilot's greedy coverage procedure, keyed by canonical triples."""
    if isinstance(fraction, bool) or not math.isfinite(fraction) or not 0 < fraction < 1 or not salt:
        raise ValueError("Explicit validation fraction in (0, 1) and salt required")
    rows = [t.to_tuple() for t in dataset.triples]
    if not rows or len(rows) != len(set(rows)):
        raise ValueError("Nonempty unique triples required for validation")
    entities: Counter[str] = Counter()
    relations: Counter[str] = Counter()
    for h, r, t in rows:
        entities.update({h, t})
        relations[r] += 1
    # Preserve the pilot's existing JSON encoding/order; identity never uses indices.
    order = sorted(rows, key=lambda t: hashlib.sha256(
        json.dumps([salt, *t], ensure_ascii=False, indent=2, sort_keys=True).encode()
    ).hexdigest())
    target = max(1, math.floor(len(rows) * fraction))
    heldout = []
    for h, r, t in order:
        if len(heldout) >= target:
            break
        if relations[r] > 1 and all(entities[e] > 1 for e in {h, t}):
            heldout.append((h, r, t))
            entities.subtract({e: 1 for e in {h, t}})
            relations[r] -= 1
    chosen = set(heldout)
    result = ValidationSplit(tuple(sorted(set(rows) - chosen)), tuple(sorted(chosen)),
                             "coverage_greedy_v1:" + salt)
    result.validate(dataset)
    return result
