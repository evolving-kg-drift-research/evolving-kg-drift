"""Explicit single-stage Dev validation runner; default is read-only preflight."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import inspect_snapshot, require_current_package  # noqa: E402
from scripts.verify_kge_validation import verify  # noqa: E402
from kge.model import TransEConfig  # noqa: E402
from kge.splits import ValidationSplit, content_hash  # noqa: E402
from kge.validation import train_validation_run, validate_validation_inputs  # noqa: E402
from kg_pipeline.experiment_manifest import bound_file, validate_manifest  # noqa: E402
from kg_pipeline.hashing import get_git_info, sha256_file  # noqa: E402


def design_identity(config: dict[str, Any]) -> str:
    """Approval binds all execution semantics, excluding its own ref/status."""
    return content_hash({k: v for k, v in config.items() if k not in {"status", "approval"}})


def preflight(root: Path, config_path: Path) -> tuple[dict, tuple]:
    root = root.resolve()
    path = config_path if config_path.is_absolute() else root / config_path
    relative = path.resolve().relative_to(root)
    if any(part.lower() == "locked_test" for part in relative.parts):
        raise ValueError("Cannot access locked_test configuration")
    path = bound_file(root, {"path": relative.as_posix(), "sha256": sha256_file(path)})
    cfg = yaml.safe_load(path.read_bytes())
    required = {"version", "status", "scientific_certification", "package_root", "snapshot", "snapshot_files",
                "split", "negative_pairs", "model", "seeds", "training_filter_scope", "approval"}
    if (set(cfg) != required or cfg["version"] != "quality_validation_runner_v1"
            or cfg["scientific_certification"] is not False or cfg["seeds"] != [13, 37, 101]
            or cfg["status"] not in {"CANDIDATE", "APPROVED_DEV_STAGE"}):
        raise ValueError("Explicit Dev validation runner contract required")
    hashes = {relative.as_posix(): sha256_file(path)}

    def load(descriptor: dict) -> Path:
        p = bound_file(root, descriptor)
        hashes[p.relative_to(root).as_posix()] = sha256_file(p)
        return p

    package_rel = Path(cfg["package_root"])
    package = require_current_package(root, package_rel)
    spec = cfg["snapshot"]
    # All three files read by inspect_snapshot must be bound before opening.
    required_paths = {package_rel / spec["parquet_path"],
                      package_rel / (spec["parquet_path"] + ".manifest.json"),
                      package_rel / f"snapshots/snapshot_{spec['snapshot_id']}_manifest.yaml"}
    if {Path(d["path"]) for d in cfg["snapshot_files"]} != required_paths or len(cfg["snapshot_files"]) != 3:
        raise ValueError("Exactly the canonical snapshot/sidecar/manifest bindings are required")
    for descriptor in cfg["snapshot_files"]:
        load(descriptor)
    dataset, record, snapshot_hashes = inspect_snapshot(package, spec)
    for rel, digest in snapshot_hashes.items():
        if hashes.get((package_rel / rel).as_posix()) != digest:
            raise ValueError("Snapshot changed during preflight")
    s = json.loads(load(cfg["split"]).read_bytes())
    if set(s) != {"train", "validation", "version"}:
        raise ValueError("Versioned explicit split required")
    split = ValidationSplit(tuple(tuple(t) for t in s["train"]),
                            tuple(tuple(t) for t in s["validation"]), s["version"])
    pairs = [(tuple(a), tuple(b)) for a, b in json.loads(load(cfg["negative_pairs"]).read_bytes())]
    fields = {"dimension", "norm", "epochs", "batch_size", "learning_rate", "margin", "normalize_entities"}
    if set(cfg["model"]) != fields:
        raise ValueError("All model parameters must be explicit; no hidden defaults")
    positives = [t.to_tuple() for t in dataset.triples]
    jobs = []
    for seed in cfg["seeds"]:
        model = TransEConfig(**cfg["model"], seed=seed)
        validate_validation_inputs(dataset, model, split, pairs, positives,
                                   training_filter_scope=cfg["training_filter_scope"])
        jobs.append(asdict(model))
    blockers = []
    if cfg["status"] != "APPROVED_DEV_STAGE":
        blockers.append("CANDIDATE_NOT_ACTIVE")
    if cfg["approval"] is None:
        blockers.append("EXPLICIT_DEV_APPROVAL_MISSING")
    else:
        approval = json.loads(load(cfg["approval"]).read_bytes())
        if (approval.get("actor") != "user" or approval.get("scope") != "quality_validation_dev"
                or not approval.get("instruction") or approval.get("design_sha256") != design_identity(cfg)):
            blockers.append("DEV_APPROVAL_DESIGN_MISMATCH")
    for rel, digest in hashes.items():
        if sha256_file(root / rel) != digest:
            raise ValueError("Input changed during preflight")
    report = {"ready": not blockers, "executed": False, "scientific_certification": False,
              "scope": "quality_validation_dev; canonical bytes/structure, not M1 temporal certification",
              "blockers": blockers, "snapshot": record, "train_triples": len(split.train),
              "validation_triples": len(split.validation), "split_hash": split.sha256,
              "design_hash": design_identity(cfg), "input_hashes": hashes, "jobs": jobs}
    return report, (cfg, dataset, split, pairs, positives)


def run(root: Path, config_path: Path, *, execute: bool = False, output: Path | None = None) -> dict:
    report, (cfg, dataset, split, pairs, positives) = preflight(root, config_path)
    if not execute:
        return report
    if not report["ready"]:
        raise PermissionError("Validation execution blocked: " + ", ".join(report["blockers"]))
    if output is None:
        raise ValueError("Explicit new output directory required for execution")
    root = root.resolve()
    destination = (root / output).resolve()
    if output.is_absolute() or not destination.is_relative_to(root / "outputs") or destination == root / "outputs":
        raise ValueError("Output must be a new relative directory under outputs")
    if any(part.lower() == "locked_test" for part in destination.parts):
        raise ValueError("Cannot access locked_test")
    commit, dirty = get_git_info(ROOT)
    # Snapshot exact implementation before training and bind its copies in the parent manifest.
    code = {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in [
        Path(__file__), ROOT / "scripts/verify_kge_validation.py", ROOT / "scripts/inspect_m2_inputs.py",
        *sorted((ROOT / "src/kge").glob("*.py")),
        *(ROOT / "src/kg_pipeline" / n for n in ("experiment_manifest.py", "hashing.py", "storage.py"))]}
    destination.mkdir(parents=True, exist_ok=False)

    def write(name: str, value: object) -> None:
        with (destination / name).open("xb") as f:
            f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode())

    write("resolved_config.json", cfg)
    write("readiness.json", report)
    write("registered_jobs.json", report["jobs"])
    for relative, payload in code.items():
        p = destination / "code" / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as f:
            f.write(payload)
    for relative in report["input_hashes"]:
        p = destination / "inputs" / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as f:
            f.write((root / relative).read_bytes())
    for rel, digest in report["input_hashes"].items():
        if sha256_file(root / rel) != digest or sha256_file(destination / "inputs" / rel) != digest:
            raise ValueError("Input changed before validation training")
    if any((ROOT / rel).read_bytes() != payload for rel, payload in code.items()):
        raise ValueError("Code changed before validation training")
    receipts = {}
    for job in report["jobs"]:
        seed = job["seed"]
        folder = destination / f"seed_{seed}"
        train_validation_run(dataset, TransEConfig(**job), split, pairs, positives,
                             training_filter_scope=cfg["training_filter_scope"], output=folder)
        receipts[str(seed)] = verify(folder)
    write("independent_verification.json", receipts)
    for rel, digest in report["input_hashes"].items():
        if sha256_file(root / rel) != digest or sha256_file(destination / "inputs" / rel) != digest:
            raise ValueError("Input changed during validation execution")
    if any((ROOT / rel).read_bytes() != payload for rel, payload in code.items()):
        raise ValueError("Code changed during validation execution")
    manifest = {"experiment_id": destination.name, "protocol_version": "v1-draft", "seed": None,
        "stage": "quality_validation_dev_three_seed", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {"data_hash": dataset.snapshot_hash, "snapshot_hash": dataset.snapshot_hash,
                   "query_hash": content_hash(split.validation), "entity_map_hash": dataset.compute_mapping_hash(),
                   "relation_map_hash": content_hash(dataset.get_relation_mapping()),
                   "config_hash": content_hash(cfg), "hashes": report["input_hashes"]},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": "scripts/run_kge_validation.py"},
        "artifacts": {"hashes": {p.relative_to(destination).as_posix(): sha256_file(p)
                                  for p in destination.rglob("*") if p.is_file()}}}
    validate_manifest(manifest)
    write("experiment_manifest.json", manifest)
    return {**report, "executed": True, "seeds_verified": cfg["seeds"], "output": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(ROOT, args.config, execute=args.execute, output=args.output)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ready"] else 2)
