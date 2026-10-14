"""User-authorized bounded M2 Dev pilot; never runs longitudinal drift or M4."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.evaluate_legacy_t01 import evaluate, metrics  # noqa: E402
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from drift.anchors import AnchorSplit, compute_anchor_hash, deterministic_hash_split  # noqa: E402
from drift.procrustes import align_embeddings_procrustes  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.model import TransEConfig  # noqa: E402
from kge.trainer import train_single_seed  # noqa: E402

TripleTuple = tuple[str, str, str]


def validation_split(
    rows: list[TripleTuple], fraction: float, salt: str,
) -> tuple[list[TripleTuple], list[TripleTuple]]:
    """Outcome-blind bounded split; no held-out entity or relation is OOV."""
    if not rows or len(rows) != len(set(rows)) or not 0 < fraction < 1:
        raise ValueError("Nonempty unique rows and fraction in (0, 1) required")
    entities: Counter[str] = Counter()
    relations: Counter[str] = Counter()
    for h, r, t in rows:
        entities.update({h, t})
        relations[r] += 1
    order = sorted(rows, key=lambda t: sha(encode([salt, *t])))
    heldout = []
    target = max(1, math.floor(len(rows) * fraction))
    for h, r, t in order:
        if len(heldout) >= target:
            break
        if relations[r] > 1 and all(entities[e] > 1 for e in {h, t}):
            heldout.append((h, r, t))
            entities.subtract({e: 1 for e in {h, t}})
            relations[r] -= 1
    if not heldout:
        raise ValueError("No coverage-preserving validation triples available")
    selected = set(heldout)
    return sorted(t for t in rows if t not in selected), sorted(heldout)


def stratified_anchors(dataset: SnapshotDataset, candidates: list[str], salt: str, ratio: float) -> AnchorSplit:
    if not 0 < ratio < 1 or len(candidates) != len(set(candidates)):
        raise ValueError("Invalid anchor ratio or duplicate candidates")
    groups: dict[int, list[str]] = {}
    for e in candidates:
        groups.setdefault(dataset.entity_metadata[e].degree, []).append(e)
    fit, holdout = [], []
    for degree, entities in sorted(groups.items()):
        split = deterministic_hash_split(entities, fit_ratio=ratio, salt=f"{salt}:degree:{degree}")
        fit.extend(split.fit_anchors)
        holdout.extend(split.holdout_anchors)
    if not fit or not holdout:
        raise ValueError("Pilot requires nonempty fit and holdout anchors")
    result = AnchorSplit(tuple(sorted(fit)), tuple(sorted(holdout)),
                         compute_anchor_hash(fit), compute_anchor_hash(holdout))
    result.verify_disjoint()
    return result


def select_dimension(results: dict[str, Any]) -> int | None:
    eligible = [int(d) for d, r in results.items() if r["alignment_feasible"]]
    if not eligible:
        return None
    return min(eligible, key=lambda d: (-results[str(d)]["mean_validation_MRR"], d))


def train_replayed(
    dataset: SnapshotDataset, config: TransEConfig, out: Path, git: dict[str, Any],
) -> tuple[KGECheckpoint, dict[str, Any]]:
    paths = []
    for repeat in (1, 2):
        ckpt = train_single_seed(dataset, config, dev_split_ratio=0.0,
                                 git_commit=git["commit"], git_dirty=git["dirty_state"])
        ckpt.verify_finite()
        vectors = [*ckpt.entity_embeddings.values(), *ckpt.relation_embeddings.values()]
        losses = ckpt.training_metrics["epoch_losses"]
        if (any(len(v) != config.dimension for v in vectors)
                or len(losses) != config.epochs or not all(math.isfinite(x) for x in losses)
                or set(ckpt.entity_embeddings) != set(dataset.entities)
                or set(ckpt.relation_embeddings) != set(dataset.relations)
                or ckpt.provenance.entity_mapping_hash != dataset.compute_mapping_hash()):
            raise ValueError("Checkpoint structure, losses, or mapping parity failed")
        path = out / f"seed_{config.seed}_repeat_{repeat}.json"
        ckpt.save(path)
        loaded = KGECheckpoint.load(path)
        if loaded != ckpt or loaded.compute_artifact_hash() != loaded.artifact_hash:
            raise ValueError("Checkpoint round-trip failed")
        paths.append(path)
    if paths[0].read_bytes() != paths[1].read_bytes():
        raise ValueError("Same-seed full checkpoint bytes differ")
    return loaded, {"snapshot_id": dataset.snapshot_id, "seed": config.seed,
                    "dimension": config.dimension, "config_hash": loaded.provenance.config_hash,
                    "entity_map_hash": loaded.provenance.entity_mapping_hash,
                    "relation_map_hash": loaded.provenance.relation_mapping_hash,
                    "checkpoint_sha256": sha(paths[0].read_bytes()), "exact_replay": True}


def run(preflight: Path) -> Path:
    if not preflight.resolve().is_relative_to((ROOT / "outputs/m2_preflight").resolve()):
        raise ValueError("Pilot requires a recorded preflight under outputs/m2_preflight")
    preflight_report = json.loads((preflight / "report.json").read_bytes())
    preflight_manifest = json.loads((preflight / "experiment_manifest.json").read_bytes())
    validate_manifest(preflight_manifest)
    if (preflight_report["status"] != "PACKAGE_TECHNICAL_CHECKS_PASS"
            or preflight_manifest["artifacts"]["hashes"]["report.json"] != sha((preflight / "report.json").read_bytes())
            or preflight_manifest["inputs"]["hashes"] != preflight_report["input_hashes"]):
        raise ValueError("Preflight report is unbound or unsuccessful")
    inputs = dict(preflight_report["input_hashes"])
    for relative, digest in inputs.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed since preflight: {relative}")
    datasets, _ = inspect_package(ROOT / PACKAGE)
    config_path = ROOT / "configs/m2_pilot.yaml"
    design = yaml.safe_load(config_path.read_bytes())
    if (design["snapshots"] != ["T01", "T02"] or design["dimensions"] != [32, 64]
            or design["seeds"] != [13, 37, 101] or design["norm"] != 2
            or design["model"] != "TransE" or design["scientific_certification"] is not False
            or design["repetitions"] != 2 or design["validation_snapshot"] != "T01"
            or design["alignment"]["require_full_rank"] is not True):
        raise ValueError("Pilot design exceeds the authorized bounded scope")
    inputs["configs/m2_pilot.yaml"] = sha(config_path.read_bytes())
    for relative in ("configs/protocol_v1.yaml", "configs/kge.yaml",
                     "configs/schemas/experiment_manifest.schema.yaml"):
        inputs[relative] = sha(safe_file(ROOT, relative).read_bytes())
    rows = [t.to_tuple() for t in datasets["T01"].triples]
    train, heldout = validation_split(rows, design["validation"]["target_fraction"], design["validation"]["salt"])
    validation_data = SnapshotDataset.create("T01_PILOT_TRAIN", train)
    if (validation_data.entities != datasets["T01"].entities
            or validation_data.relations != datasets["T01"].relations):
        raise ValueError("Validation split has OOV entities or relations")
    candidates = sorted(set(datasets["T01"].entities) & set(datasets["T02"].entities))
    salt, ratio = design["alignment"]["salt"], design["alignment"]["fit_ratio"]
    splits = {sid: stratified_anchors(datasets[sid], candidates, f"{salt}:{sid}", ratio)
              for sid in ("T01", "T02")}
    splits["T01->T02"] = stratified_anchors(datasets["T01"], candidates, f"{salt}:T01->T02", ratio)
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_pilot" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    git = provenance()
    # Register population, parameters, selection rule and anchors before model outcomes.
    write_json(out / "design.json", design)
    write_json(out / "input_hashes.json", inputs)
    write_json(out / "split.json", {"train": train, "validation": heldout})
    write_json(out / "anchors.json", {key: asdict(split) for key, split in splits.items()})
    write_json(out / "mappings.json", {sid: {"entities": ds.get_entity_mapping(),
                                           "relations": ds.get_relation_mapping()}
                                        for sid, ds in {**{s: datasets[s] for s in design["snapshots"]},
                                                        validation_data.snapshot_id: validation_data}.items()})
    code_paths = [Path(__file__), ROOT / "scripts/inspect_m2_inputs.py",
                  ROOT / "scripts/evaluate_legacy_t01.py", ROOT / "scripts/audit_legacy_split_t01.py",
                  ROOT / "scripts/run_legacy_transe_t01.py",
                  *sorted((ROOT / "src/kge").glob("*.py")),
                  ROOT / "src/drift/anchors.py", ROOT / "src/drift/procrustes.py"]
    code_hashes = {}
    for path in code_paths:
        relative = path.relative_to(ROOT)
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(path.read_bytes())
        code_hashes[relative.as_posix()] = sha(path.read_bytes())
    write_json(out / "code_hashes.json", code_hashes)
    results, checkpoint_records, alignment_records = {}, [], []
    for dimension in design["dimensions"]:
        checkpoints = {}
        validation_metrics = {}
        for sid, ds in {validation_data.snapshot_id: validation_data,
                        **{s: datasets[s] for s in design["snapshots"]}}.items():
            checkpoints[sid] = {}
            for seed in design["seeds"]:
                cfg = TransEConfig(dimension=dimension, norm=2, seed=seed,
                                   epochs=design["epochs"], learning_rate=design["learning_rate"],
                                   margin=design["margin"])
                folder = out / f"dim_{dimension}" / sid
                loaded, record = train_replayed(ds, cfg, folder, git)
                record["path"] = (folder / f"seed_{seed}_repeat_1.json").relative_to(out).as_posix()
                checkpoint_records.append(record)
                checkpoints[sid][seed] = loaded
                if sid == validation_data.snapshot_id:
                    def score(triple: TripleTuple) -> float:
                        h, r, t = triple
                        return -math.sqrt(sum((x + y - z) ** 2 for x, y, z in zip(
                            loaded.entity_embeddings[h], loaded.relation_embeddings[r], loaded.entity_embeddings[t])))
                    ranking_rows = evaluate(heldout, validation_data.entities, set(rows), score)
                    write_json(folder / f"seed_{seed}_validation_ranks.json", ranking_rows)
                    validation_metrics[str(seed)] = metrics(ranking_rows)
                print(f"dimension={dimension} snapshot={sid} seed={seed}: finite, mapping, replay PASS", flush=True)
        checks = []
        pairs = list(itertools.combinations(design["seeds"], 2))
        comparisons = [(sid, sid, a, b, "same_snapshot_cross_seed")
                       for sid in design["snapshots"] for a, b in pairs]
        comparisons.extend(("T01", "T02", s, s, "cross_time") for s in design["seeds"])
        for prev, nxt, a, b, kind in comparisons:
            key = prev if prev == nxt else "T01->T02"
            result = align_embeddings_procrustes(checkpoints[prev][a].entity_embeddings,
                                                checkpoints[nxt][b].entity_embeddings,
                                                splits[key], alignment_type=kind)
            valid, reason = result.diagnostics.check_alignment_validity()
            full_rank = result.diagnostics.numerical_rank == dimension
            record = {"dimension": dimension, "source_snapshot": prev, "target_snapshot": nxt,
                      "source_seed": a, "target_seed": b, "split_key": key,
                      "diagnostics": asdict(result.diagnostics), "operational_valid": valid,
                      "full_rank": full_rank, "reason": reason,
                      "Q": result.Q, "source_mean": result.source_mean, "target_mean": result.target_mean}
            # No entity displacement, null, RR panel or SED is computed here.
            encode(record)
            alignment_records.append(record)
            checks.append(valid and full_rank)
        mrrs = [v["MRR"] for v in validation_metrics.values()]
        results[str(dimension)] = {"validation": validation_metrics,
                                   "mean_validation_MRR": sum(mrrs) / len(mrrs),
                                   "validation_MRR_range": [min(mrrs), max(mrrs)],
                                   "alignment_checks": len(checks), "alignment_passed": sum(checks),
                                   "alignment_feasible": all(checks)}
    selected = select_dimension(results)
    summary = {"status": "PILOT_TECHNICAL_CHECKS_PASS" if selected is not None else "PILOT_ALIGNMENT_BLOCKED",
               "scientific_certification": False, "recommended_dimension": selected,
               "dimensions": results, "train_triples": len(train), "validation_triples": len(heldout),
               "validation_queries": 2 * len(heldout), "candidate_entities": len(validation_data.entities),
               "checkpoints": checkpoint_records, "input_unchanged": True,
               "limitations": ["Coverage-preserving T01 validation favors repeated entities; Dev only",
                               "No G3 certification, global dimension freeze, or longitudinal drift",
                               "Anchor counts, null bucket rules, epsilon await configuration approval",
                               "External snapshot identity and temporal validity remain uncertified"],
               "next_action": "Review configuration proposal; stop before full training/null/drift"}
    write_json(out / "alignments.json", alignment_records)
    for relative, digest in inputs.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed during pilot: {relative}")
    for relative, digest in code_hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError("Code changed during pilot")
    write_json(out / "summary.json", summary)
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "mode": design["mode"],
                "scientific_certification": False, "git": git, "seed": None,
                "inputs": {"data_hash": sha(encode(inputs)),
                           "snapshot_hash": sha(encode({s: datasets[s].snapshot_hash for s in design["snapshots"]})),
                           "query_hash": sha(encode(heldout)),
                           "entity_map_hash": sha((out / "mappings.json").read_bytes()),
                           "relation_map_hash": sha(encode({s: datasets[s].get_relation_mapping() for s in design["snapshots"]})),
                           "config_hash": sha(encode(design)), "hashes": inputs, "code_hashes": code_hashes,
                           "preflight_manifest_hash": sha((preflight / "experiment_manifest.json").read_bytes())},
                "environment": {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes())
                                          for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_pilot.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), "recommended_dimension": selected, "dimensions": results}, indent=2))
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", required=True, type=Path)
    args = parser.parse_args()
    run(args.preflight)
