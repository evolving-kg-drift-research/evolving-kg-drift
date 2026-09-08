"""KGE Input Contract.

This module defines the minimal, self-contained contract required by the KGE and
drift measurement pipeline. It isolates the KGE backbone and longitudinal drift
estimator from unmerged upstream data pipelines, crawlers, and extraction internals.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class Triple:
    """A canonical knowledge graph triple with string entity/relation identifiers."""

    subject_id: str
    relation_id: str
    object_id: str

    def to_tuple(self) -> tuple[str, str, str]:
        return (self.subject_id, self.relation_id, self.object_id)


@dataclass(frozen=True)
class EntityMetadata:
    """Structural metadata used for conditional null stratification (optional)."""

    entity_id: str
    degree: int = 0
    frequency: int = 0


@dataclass(frozen=True)
class SnapshotDataset:
    """Immutable snapshot dataset adhering to the KGE Input Contract.

    Attributes:
        snapshot_id: Unique snapshot identifier (e.g. 'S1', '2026-01-10T00:00:00Z').
        triples: Ordered sequence of canonical Triples.
        entity_metadata: Optional map of entity_id -> EntityMetadata for conditional null.
        snapshot_hash: Deterministic SHA-256 hash of the canonical triples content.
    """

    snapshot_id: str
    triples: tuple[Triple, ...]
    entity_metadata: dict[str, EntityMetadata]
    snapshot_hash: str

    @classmethod
    def create(
        cls,
        snapshot_id: str,
        triples: Sequence[Triple | tuple[str, str, str]],
        entity_metadata: dict[str, EntityMetadata] | None = None,
        validate: bool = True,
    ) -> SnapshotDataset:
        """Constructs a SnapshotDataset with deterministic canonical sorting and hashing."""
        canonical_triples: list[Triple] = []
        for t in triples:
            if isinstance(t, Triple):
                canonical_triples.append(t)
            elif isinstance(t, (tuple, list)) and len(t) == 3:
                canonical_triples.append(
                    Triple(subject_id=str(t[0]), relation_id=str(t[1]), object_id=str(t[2]))
                )
            else:
                raise ValueError(f"Invalid triple format: {t}")

        # Deterministic canonical sort by (subject, relation, object)
        canonical_triples.sort(key=lambda x: (x.subject_id, x.relation_id, x.object_id))

        if validate:
            cls.validate_triples(canonical_triples)

        # Compute deterministic SHA-256 hash of canonical triples
        hasher = hashlib.sha256()
        for tr in canonical_triples:
            hasher.update(f"{tr.subject_id}\t{tr.relation_id}\t{tr.object_id}\n".encode("utf-8"))
        snapshot_hash = hasher.hexdigest()

        # Compute default degree / frequency if not provided
        computed_metadata: dict[str, EntityMetadata] = {}
        degrees: dict[str, int] = {}
        for tr in canonical_triples:
            degrees[tr.subject_id] = degrees.get(tr.subject_id, 0) + 1
            degrees[tr.object_id] = degrees.get(tr.object_id, 0) + 1

        entities = sorted(set(degrees.keys()))
        for e in entities:
            if entity_metadata and e in entity_metadata:
                computed_metadata[e] = entity_metadata[e]
            else:
                computed_metadata[e] = EntityMetadata(
                    entity_id=e,
                    degree=degrees.get(e, 0),
                    frequency=degrees.get(e, 0),
                )

        return cls(
            snapshot_id=snapshot_id,
            triples=tuple(canonical_triples),
            entity_metadata=computed_metadata,
            snapshot_hash=snapshot_hash,
        )

    @staticmethod
    def validate_triples(triples: Sequence[Triple]) -> None:
        """Validates that all triples have non-empty identifiers and no None/whitespace."""
        for idx, t in enumerate(triples):
            if not t.subject_id or not t.subject_id.strip():
                raise ValueError(f"Triple #{idx} has invalid subject_id: '{t.subject_id}'")
            if not t.relation_id or not t.relation_id.strip():
                raise ValueError(f"Triple #{idx} has invalid relation_id: '{t.relation_id}'")
            if not t.object_id or not t.object_id.strip():
                raise ValueError(f"Triple #{idx} has invalid object_id: '{t.object_id}'")

    @property
    def entities(self) -> list[str]:
        """Alphabetically sorted list of all unique entity IDs."""
        ents = set()
        for t in self.triples:
            ents.add(t.subject_id)
            ents.add(t.object_id)
        return sorted(ents)

    @property
    def relations(self) -> list[str]:
        """Alphabetically sorted list of all unique relation IDs."""
        rels = {t.relation_id for t in self.triples}
        return sorted(rels)

    def get_entity_mapping(self) -> dict[str, int]:
        """Deterministic mapping from entity_id to integer index 0..N-1.

        Entities are sorted alphabetically to guarantee strict mapping identity
        regardless of seed or iteration order.
        """
        return {e: idx for idx, e in enumerate(self.entities)}

    def get_relation_mapping(self) -> dict[str, int]:
        """Deterministic mapping from relation_id to integer index 0..R-1."""
        return {r: idx for idx, r in enumerate(self.relations)}

    def compute_mapping_hash(self) -> str:
        """Computes SHA-256 hash of the canonical entity mapping."""
        mapping = self.get_entity_mapping()
        payload = json.dumps(mapping, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
