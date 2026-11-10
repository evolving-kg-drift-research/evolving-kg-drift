"""Development validation engine with explicit partitions and immutable epoch artifacts.

This API does not authorize production data or register a scientific design.
"""
from __future__ import annotations

import json
import math
import platform
import random
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from .checkpoint import CheckpointProvenance, KGECheckpoint
from .contract import SnapshotDataset
from .model import TransEConfig, TransEModel
from .splits import TripleTuple, ValidationSplit, content_hash

try:
    from ..kg_pipeline.experiment_manifest import validate_manifest
    from ..kg_pipeline.hashing import get_git_info, sha256_file
except ImportError:
    from kg_pipeline.experiment_manifest import validate_manifest
    from kg_pipeline.hashing import get_git_info, sha256_file

Pair = tuple[TripleTuple, TripleTuple]


def fixed_negative_pairs(
    dataset: SnapshotDataset, positives: Sequence[TripleTuple],
    filter_positives: Sequence[TripleTuple], *, seed: int,
) -> list[Pair]:
    """Build explicit fixed pairs; never silently skip an unscorable positive."""
    rng = random.Random(seed)
    known = set(filter_positives)
    entities = dataset.entities
    result = []
    for h, r, t in sorted(positives):
        head = rng.random() < 0.5
        negative = None
        for _ in range(100):
            candidate = rng.choice(entities)
            proposed = (candidate, r, t) if head else (h, r, candidate)
            if proposed != (h, r, t) and proposed not in known:
                negative = proposed
                break
        if negative is None:
            raise ValueError("No usable fixed negative for validation positive")
        result.append(((h, r, t), negative))
    return result


def validation_observations(
    model: TransEModel, split: ValidationSplit, pairs: Sequence[Pair],
    filter_positives: Sequence[TripleTuple],
) -> tuple[float, list[dict], dict]:
    def distance(triple: TripleTuple) -> float:
        h, r, t = triple
        return model.score_triple(model.entity_to_id[h], model.relation_to_id[r], model.entity_to_id[t])

    loss = math.fsum(max(0.0, model.config.margin + distance(a) - distance(b)) for a, b in pairs) / len(pairs)
    rows = []
    entities = np.asarray(model.entity_embeddings, dtype=np.float64)
    relations = np.asarray(model.relation_embeddings, dtype=np.float64)
    ids = model.entity_to_id
    relation_ids = model.relation_to_id
    candidates = sorted(ids, key=ids.__getitem__)
    heads: dict[tuple[str, str], list[int]] = {}
    tails: dict[tuple[str, str], list[int]] = {}
    for h, r, t in filter_positives:
        heads.setdefault((r, t), []).append(ids[h])
        tails.setdefault((h, r), []).append(ids[t])
    for h, r, t in sorted(split.validation):
        relation = relations[relation_ids[r]]
        for side, gold, excluded in (("head", h, heads.get((r, t), [])), ("tail", t, tails.get((h, r), []))):
            offsets = entities + relation - entities[ids[t]] if side == "head" else (
                entities[ids[h]] + relation - entities)
            scores = -np.sqrt(np.sum(offsets * offsets, axis=1))
            eligible = np.ones(len(candidates), dtype=bool)
            eligible[excluded] = False
            gold_id = ids[gold]
            eligible[gold_id] = True
            # The scalar scorer decides near ties so the reduction order does not change exact ranks.
            close = eligible & np.isclose(scores, scores[gold_id], rtol=1e-12, atol=1e-14)
            if np.count_nonzero(close) > 1:
                for index in np.flatnonzero(close):
                    candidate = candidates[index]
                    triple = (candidate, r, t) if side == "head" else (h, r, candidate)
                    scores[index] = -distance(triple)
            target = scores[gold_id]
            rank = 1 + int(np.count_nonzero(eligible & (scores > target))) + (
                int(np.count_nonzero(eligible & (scores == target))) - 1) / 2
            rows.append({"triple": [h, r, t], "side": side, "rank": rank,
                         "reciprocal_rank": 1 / rank, "candidate_count": int(np.count_nonzero(eligible))})
    metrics = {"MRR": math.fsum(row["reciprocal_rank"] for row in rows) / len(rows),
               **{f"Hits@{k}": sum(row["rank"] <= k for row in rows) / len(rows) for k in (1, 3, 10)}}
    return loss, rows, metrics


def validate_validation_inputs(
    dataset: SnapshotDataset, config: TransEConfig, split: ValidationSplit,
    pairs: Sequence[Pair], filter_positives: Sequence[TripleTuple], *,
    training_filter_scope: str,
) -> None:
    """Pure preflight: no model initialization, randomness, directory or writes."""
    split.validate(dataset)
    known = set(filter_positives)
    source = {t.to_tuple() for t in dataset.triples}
    if len(known) != len(filter_positives) or known != source:
        raise ValueError("Validation filter must bind the known positives of this train/validation snapshot")
    if training_filter_scope not in {"train", "snapshot"}:
        raise ValueError("Explicit training positive-filter scope required")
    if config.epochs <= 0 or config.norm != 2 or config.seed not in (13, 37, 101):
        raise ValueError("Positive epoch budget, L2 norm and registered model seed required")
    if (type(config.dimension) is not int or config.dimension <= 0
            or type(config.epochs) is not int or type(config.batch_size) is not int or config.batch_size <= 0
            or type(config.normalize_entities) is not bool
            or not math.isfinite(config.learning_rate) or config.learning_rate <= 0
            or not math.isfinite(config.margin) or config.margin < 0):
        raise ValueError("Invalid explicit model parameters")
    if len(pairs) != len(split.validation) or {tuple(a) for a, _ in pairs} != set(split.validation):
        raise ValueError("Exactly one fixed negative per validation positive required")
    for positive, negative in pairs:
        h, r, t = positive
        hn, rn, tn = negative
        if (rn != r or ((hn != h) + (tn != t)) != 1 or tuple(negative) in known
                or hn not in dataset.entities or tn not in dataset.entities):
            raise ValueError("Invalid validation negative pair")


def train_validation_run(
    dataset: SnapshotDataset, config: TransEConfig, split: ValidationSplit,
    pairs: Sequence[Pair], filter_positives: Sequence[TripleTuple], *,
    training_filter_scope: str, output: Path,
) -> Path:
    """Save all monitored epochs; fixed-budget Dev only, no test/early-stop selection."""
    validate_validation_inputs(dataset, config, split, pairs, filter_positives,
                               training_filter_scope=training_filter_scope)
    source = {t.to_tuple() for t in dataset.triples}
    known = set(filter_positives)
    commit, dirty = get_git_info()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("An actual git commit is required before validation training")
    train_data = SnapshotDataset.create(dataset.snapshot_id + "_VALIDATION_TRAIN", split.train)
    design = {"version": "kge_validation_dev_v2", "role": "quality_validation", "model": asdict(config),
              "source_snapshot_id": dataset.snapshot_id, "source_snapshot_hash": dataset.snapshot_hash,
              "source_triples": sorted(source), "split": split.descriptor(), "split_hash": split.sha256,
              "negative_pairs": list(pairs), "filter_positives": sorted(known),
              "candidates": dataset.entities, "training_filter_scope": training_filter_scope,
              "selection": "fixed_budget_no_test_access", "checkpoint_schedule": "every_epoch",
              "ranking": "filtered_average_exact_tie_v1"}
    design_hash = content_hash(design)
    output = Path(output)
    if any(part.lower() == "locked_test" for part in output.resolve().parts):
        raise ValueError("Development validation cannot access locked_test")
    output.mkdir(parents=True, exist_ok=False)

    def write(path: Path, value: object) -> None:
        with path.open("xb") as stream:
            stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode())

    write(output / "design.json", design)
    (output / "epochs").mkdir()
    model = TransEModel(train_data.get_entity_mapping(), train_data.get_relation_mapping(), config)
    def index(triple: TripleTuple) -> tuple[int, int, int]:
        h, r, t = triple
        return model.entity_to_id[h], model.relation_to_id[r], model.entity_to_id[t]
    train = [index(t) for t in split.train]
    training_known = set(train) if training_filter_scope == "train" else {index(t) for t in source}
    rng = random.Random(config.seed)
    logs = []
    prov = CheckpointProvenance(
        snapshot_id=train_data.snapshot_id, snapshot_hash=train_data.snapshot_hash, seed=config.seed,
        model="TransE", norm=2, dimension=config.dimension,
        entity_mapping_hash=train_data.compute_mapping_hash(),
        relation_mapping_hash=content_hash(train_data.get_relation_mapping()),
        config_hash=design_hash, git_commit=commit, git_dirty=dirty,
    )
    for epoch in range(1, config.epochs + 1):
        online_loss = model.train_epoch(train, rng, positive_triples_set=training_known)
        loss, ranks, metrics = validation_observations(model, split, pairs, filter_positives)
        if not math.isfinite(loss):
            raise ValueError("Nonfinite validation loss")
        row = {"epoch": epoch, "seed": config.seed, "snapshot_id": dataset.snapshot_id,
               "design_hash": design_hash, "online_train_loss": online_loss,
               "train_diagnostics": asdict(model.last_train_diagnostics),
               "validation_loss": loss, "validation_pairs": len(pairs), "metrics": metrics,
               "checkpoint": f"epochs/{epoch:04d}.json"}
        KGECheckpoint(prov, model.get_all_entity_embeddings(), model.get_all_relation_embeddings(),
                      {"epoch": epoch, "role": "quality_validation", "design_hash": design_hash,
                       "split_hash": split.sha256}).save(output / row["checkpoint"])
        write(output / "epochs" / f"{epoch:04d}_ranks.json", ranks)
        logs.append(row)
    write(output / "epoch_log.json", logs)
    # Preserve the exact implementation bytes used by this run.
    source_root = Path(__file__).resolve().parents[1]
    executed_sources = [source_root / "kge" / name for name in
                        ("validation.py", "splits.py", "model.py", "checkpoint.py", "contract.py", "math_utils.py")]
    executed_sources.extend(source_root / "kg_pipeline" / name for name in
                            ("experiment_manifest.py", "hashing.py", "storage.py"))
    code_hashes = {}
    for source_file in executed_sources:
        relative = source_file.relative_to(source_root)
        target = output / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source_file.read_bytes())
        code_hashes[relative.as_posix()] = sha256_file(target)
    manifest = {
        "experiment_id": output.name, "protocol_version": "v1-draft", "seed": config.seed,
        "stage": "quality_validation_dev", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {"data_hash": dataset.snapshot_hash, "snapshot_hash": dataset.snapshot_hash,
                   "query_hash": content_hash(split.validation), "entity_map_hash": prov.entity_mapping_hash,
                   "relation_map_hash": prov.relation_mapping_hash, "config_hash": design_hash,
                   "code_hashes": code_hashes},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": "kge.validation.train_validation_run"},
        "artifacts": {"hashes": {p.relative_to(output).as_posix(): sha256_file(p)
                                  for p in output.rglob("*") if p.is_file()}},
    }
    validate_manifest(manifest)
    write(output / "experiment_manifest.json", manifest)
    return output
