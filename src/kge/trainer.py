"""Multi-seed TransE-L2 Trainer.

Manages training across seeds [13, 37, 101] and enforces mapping parity across all runs.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .checkpoint import CheckpointProvenance, KGECheckpoint
from .contract import SnapshotDataset
from .model import TransEConfig, TransEModel
from .splits import coverage_split


def train_single_seed(
    dataset: SnapshotDataset,
    config: TransEConfig,
    dev_split_ratio: float = 0.0,
    git_commit: str = "",
    git_dirty: bool | None = None,
) -> KGECheckpoint:
    """Trains a TransE-L2 model on a single seed with optional dev loss tracking (A18)."""
    entity_to_id = dataset.get_entity_mapping()
    relation_to_id = dataset.get_relation_mapping()

    model = TransEModel(entity_to_id, relation_to_id, config)
    if (not math.isfinite(dev_split_ratio) or not 0 <= dev_split_ratio < 1
            or config.epochs <= 0):
        raise ValueError("Invalid validation ratio or nonpositive epoch budget")

    # Convert triples to integer indices
    indexed_triples = [
        (entity_to_id[t.subject_id], relation_to_id[t.relation_id], entity_to_id[t.object_id])
        for t in dataset.triples
    ]

    # Deterministic train/dev split based on triple hash (A18)
    split = None
    if dev_split_ratio > 0.0:
        split = coverage_split(dataset, dev_split_ratio, "kge-dev-v2")
        def index(rows):
            return [(entity_to_id[h], relation_to_id[r], entity_to_id[t]) for h, r, t in rows]
        train_triples = index(split.train)
        dev_triples = index(split.validation)
    else:
        train_triples = indexed_triples
        dev_triples = []

    rng = random.Random(config.seed)
    epoch_losses: list[float] = []
    dev_losses: list[float] = []
    diagnostics: list[dict] = []
    validation_counts: list[dict] = []
    positive_set = set(indexed_triples)

    for epoch in range(config.epochs):
        loss = model.train_epoch(train_triples, rng, positive_triples_set=positive_set)
        epoch_losses.append(loss)
        diagnostics.append(asdict(model.last_train_diagnostics))
        if dev_triples:
            # Reset an independent stream: fixed negative draws at every epoch.
            eval_seed = hashlib.sha256(f"validation-v2:{config.seed}".encode()).hexdigest()
            dev_loss = model.evaluate_loss(dev_triples, random.Random(eval_seed), positive_triples_set=positive_set)
            dev_losses.append(dev_loss)
            validation_counts.append(dict(model.last_validation_counts))

    # Compute config hash
    config_dict = asdict(config)
    if split is not None:
        config_dict = {"model": config_dict, "split": split.descriptor(),
                       "requested_validation_ratio": dev_split_ratio,
                       "evaluation": "independent_fixed_negative_stream_v2",
                       "positive_filter_scope": "snapshot"}
    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode("utf-8")).hexdigest()

    # Resolve git provenance if not explicitly provided
    if not git_commit:
        try:
            from ..kg_pipeline.hashing import get_git_info
        except (ImportError, ValueError):
            from kg_pipeline.hashing import get_git_info
        resolved_commit, resolved_dirty = get_git_info()
        commit_to_use = resolved_commit
        dirty_to_use = resolved_dirty if git_dirty is None else git_dirty
    else:
        commit_to_use = git_commit
        dirty_to_use = git_dirty if git_dirty is not None else False

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
        git_commit=commit_to_use,
        git_dirty=dirty_to_use,
    )

    checkpoint = KGECheckpoint(
        provenance=prov,
        entity_embeddings=model.get_all_entity_embeddings(),
        relation_embeddings=model.get_all_relation_embeddings(),
        training_metrics={
            "final_loss": epoch_losses[-1] if epoch_losses else 0.0,
            "epoch_losses": epoch_losses,
            "dev_losses": dev_losses,
            "final_dev_loss": dev_losses[-1] if dev_losses else None,
            "dev_split_ratio": dev_split_ratio,
            "num_epochs": config.epochs,
            "epoch_diagnostics": diagnostics,
            "validation_counts": validation_counts,
            "split": split.descriptor() if split is not None else None,
            "split_hash": split.sha256 if split is not None else None,
            "validation_status": "AVAILABLE" if split is not None else "NOT_APPLICABLE_FULL_SNAPSHOT",
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
    dev_split_ratio: float = 0.0,
    output_dir: Path | str | None = None,
    git_commit: str = "",
    git_dirty: bool | None = None,
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
        ckpt = train_single_seed(
            dataset,
            cfg,
            dev_split_ratio=dev_split_ratio,
            git_commit=git_commit,
            git_dirty=git_dirty,
        )

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


def select_best_dimension(
    dataset: SnapshotDataset,
    candidate_dimensions: Sequence[int] = (32, 64),
    seed: int = 13,
    epochs: int = 25,
    dev_split_ratio: float = 0.15,
    learning_rate: float = 0.02,
    margin: float = 1.0,
    git_commit: str = "",
    git_dirty: bool | None = None,
) -> tuple[int, dict[int, float], KGECheckpoint]:
    """Evaluates candidate embedding dimensions on validation loss and selects the optimal dimension (A18).

    Returns:
        tuple of (best_dimension, dimension_to_dev_loss_dict, best_checkpoint)
    """
    dim_losses: dict[int, float] = {}
    checkpoints: dict[int, KGECheckpoint] = {}

    for d in candidate_dimensions:
        cfg = TransEConfig(
            dimension=d,
            norm=2,
            margin=margin,
            learning_rate=learning_rate,
            epochs=epochs,
            seed=seed,
        )
        ckpt = train_single_seed(
            dataset,
            cfg,
            dev_split_ratio=dev_split_ratio,
            git_commit=git_commit,
            git_dirty=git_dirty,
        )
        final_dev = ckpt.training_metrics.get("final_dev_loss")
        if final_dev is None:
            raise ValueError("Dimension selection requires available validation loss")
        metric = final_dev
        dim_losses[d] = metric
        checkpoints[d] = ckpt

    best_dim = min(dim_losses, key=lambda d: dim_losses[d])
    return best_dim, dim_losses, checkpoints[best_dim]
