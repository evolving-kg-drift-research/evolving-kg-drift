"""Multi-seed TransE-L2 Trainer.

Manages training across seeds [13, 37, 101] and enforces mapping parity across all runs.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .checkpoint import CheckpointProvenance, KGECheckpoint
from .contract import SnapshotDataset
from .model import TransEConfig, TransEModel


def train_single_seed(
    dataset: SnapshotDataset,
    config: TransEConfig,
    git_commit: str = "",
) -> KGECheckpoint:
    """Trains a TransE-L2 model on a single seed and returns a validated KGECheckpoint."""
    entity_to_id = dataset.get_entity_mapping()
    relation_to_id = dataset.get_relation_mapping()

    model = TransEModel(entity_to_id, relation_to_id, config)

    # Convert triples to integer indices
    indexed_triples = [
        (entity_to_id[t.subject_id], relation_to_id[t.relation_id], entity_to_id[t.object_id])
        for t in dataset.triples
    ]

    rng = random.Random(config.seed)
    epoch_losses: list[float] = []

    for epoch in range(config.epochs):
        loss = model.train_epoch(indexed_triples, rng)
        epoch_losses.append(loss)

    # Compute config hash
    config_dict = asdict(config)
    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode("utf-8")).hexdigest()

    # Build provenance
    prov = CheckpointProvenance(
        snapshot_id=dataset.snapshot_id,
        snapshot_hash=dataset.snapshot_hash,
        seed=config.seed,
        model="TransE",
        dimension=config.dimension,
        norm=config.norm,
        entity_mapping_hash=dataset.compute_mapping_hash(),
        relation_mapping_hash=hashlib.sha256(
            json.dumps(relation_to_id, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        config_hash=config_hash,
        git_commit=git_commit,
    )

    checkpoint = KGECheckpoint(
        provenance=prov,
        entity_embeddings=model.get_all_entity_embeddings(),
        relation_embeddings=model.get_all_relation_embeddings(),
        training_metrics={
            "final_loss": epoch_losses[-1] if epoch_losses else 0.0,
            "epoch_losses": epoch_losses,
            "num_epochs": config.epochs,
        },
    )

    # Strict finite check
    checkpoint.verify_finite()
    return checkpoint


def train_multi_seed(
    dataset: SnapshotDataset,
    seeds: Sequence[int] = (13, 37, 101),
    dimension: int = 32,
    epochs: int = 40,
    learning_rate: float = 0.02,
    margin: float = 1.0,
    output_dir: Path | str | None = None,
    git_commit: str = "",
) -> dict[int, KGECheckpoint]:
    """Trains TransE across multiple seeds and verifies mapping parity.

    CRITICAL INVARIANT:
      mapping(seed13) == mapping(seed37) == mapping(seed101)
    """
    checkpoints: dict[int, KGECheckpoint] = {}
    base_mapping_hash = dataset.compute_mapping_hash()

    for s in seeds:
        cfg = TransEConfig(
            dimension=dimension,
            norm=2,
            margin=margin,
            learning_rate=learning_rate,
            epochs=epochs,
            seed=s,
        )
        ckpt = train_single_seed(dataset, cfg, git_commit=git_commit)

        # Invariant check: mapping hash must be identical across all seeds
        if ckpt.provenance.entity_mapping_hash != base_mapping_hash:
            raise RuntimeError(
                f"Mapping parity violation! Seed {s} produced mapping hash "
                f"{ckpt.provenance.entity_mapping_hash} != {base_mapping_hash}"
            )

        if output_dir:
            out_path = Path(output_dir) / dataset.snapshot_id / f"seed_{s}.json"
            ckpt.save(out_path)

        checkpoints[s] = ckpt

    return checkpoints
