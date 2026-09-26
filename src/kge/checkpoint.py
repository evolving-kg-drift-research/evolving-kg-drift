"""KGE Checkpoint representation, serialization, and deserialization.

Encapsulates:
  - entity_id -> embedding vector
  - relation_id -> embedding vector
  - Provenance: snapshot_id, snapshot_hash, seed, dimension, norm, config_hash, git_commit
  - Serialization to deterministic JSON format with artifact SHA-256 calculation
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CheckpointProvenance:
    snapshot_id: str
    snapshot_hash: str
    seed: int
    model: str
    dimension: int
    norm: int
    entity_mapping_hash: str
    relation_mapping_hash: str
    config_hash: str
    git_commit: str = ""
    git_dirty: bool = False


@dataclass
class KGECheckpoint:
    """Immutable KGE Checkpoint holding embeddings and scientific provenance."""

    provenance: CheckpointProvenance
    entity_embeddings: dict[str, list[float]]
    relation_embeddings: dict[str, list[float]]
    training_metrics: dict[str, Any]
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_hash:
            self.artifact_hash = self.compute_artifact_hash()

    def compute_artifact_hash(self) -> str:
        """Computes deterministic SHA-256 of canonical serialized checkpoint content."""
        payload = {
            "provenance": asdict(self.provenance),
            "entities": sorted(self.entity_embeddings.keys()),
            "relations": sorted(self.relation_embeddings.keys()),
            # Round float values to 7 decimal places for stable cross-platform hashing
            "entity_vectors": {
                e: [round(x, 7) for x in self.entity_embeddings[e]]
                for e in sorted(self.entity_embeddings.keys())
            },
            "relation_vectors": {
                r: [round(x, 7) for x in self.relation_embeddings[r]]
                for r in sorted(self.relation_embeddings.keys())
            },
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    def verify_finite(self) -> None:
        """Asserts that all embedding vectors contain finite, non-NaN numbers."""
        for e, vec in self.entity_embeddings.items():
            for idx, x in enumerate(vec):
                if math.isnan(x) or math.isinf(x):
                    raise ValueError(f"Entity '{e}' embedding has non-finite value {x} at index {idx}")
        for r, vec in self.relation_embeddings.items():
            for idx, x in enumerate(vec):
                if math.isnan(x) or math.isinf(x):
                    raise ValueError(f"Relation '{r}' embedding has non-finite value {x} at index {idx}")

    def get_entity_vector(self, entity_id: str) -> list[float]:
        if entity_id not in self.entity_embeddings:
            raise KeyError(f"Entity '{entity_id}' not present in checkpoint.")
        return list(self.entity_embeddings[entity_id])

    def get_relation_vector(self, relation_id: str) -> list[float]:
        if relation_id not in self.relation_embeddings:
            raise KeyError(f"Relation '{relation_id}' not present in checkpoint.")
        return list(self.relation_embeddings[relation_id])

    def save(self, path: Path | str, immutable: bool = True) -> str:
        """Saves checkpoint to JSON file atomically with SHA-256 sidecar (A26)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if immutable and p.exists():
            raise RuntimeError(f"Refusing to overwrite immutable checkpoint artifact: {p}")

        data = {
            "provenance": asdict(self.provenance),
            "entity_embeddings": self.entity_embeddings,
            "relation_embeddings": self.relation_embeddings,
            "training_metrics": self.training_metrics,
            "artifact_hash": self.artifact_hash,
        }
        payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        file_sha256 = hashlib.sha256(payload).hexdigest()

        # Atomic write via temporary file
        temp_path = p.with_suffix(f"{p.suffix}.{file_sha256[:8]}.tmp")
        temp_path.write_bytes(payload)
        temp_path.replace(p)

        # Write SHA-256 sidecar
        sidecar_path = p.with_name(p.name + ".sha256")
        sidecar_content = f"{file_sha256}  {p.name}\n"
        temp_sidecar = sidecar_path.with_suffix(".tmp")
        temp_sidecar.write_text(sidecar_content, encoding="utf-8")
        temp_sidecar.replace(sidecar_path)

        return str(p)

    @classmethod
    def load(cls, path: Path | str, verify_sidecar: bool = True) -> KGECheckpoint:
        """Loads checkpoint from JSON file, verifying SHA-256 sidecar if present (A26)."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Checkpoint file not found: {p}")

        raw_bytes = p.read_bytes()
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()

        sidecar_path = p.with_name(p.name + ".sha256")
        if verify_sidecar and sidecar_path.is_file():
            expected_hash = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
            if actual_hash != expected_hash:
                raise ValueError(
                    f"Checkpoint sidecar SHA-256 mismatch for {p}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

        data = json.loads(raw_bytes.decode("utf-8"))
        prov = CheckpointProvenance(**data["provenance"])
        ckpt = cls(
            provenance=prov,
            entity_embeddings=data["entity_embeddings"],
            relation_embeddings=data["relation_embeddings"],
            training_metrics=data["training_metrics"],
            artifact_hash=data["artifact_hash"],
        )
        ckpt.verify_finite()
        return ckpt
