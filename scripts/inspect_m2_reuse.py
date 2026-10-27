"""Inspect candidate registration and saved checkpoints without running M2 training/measurement."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

import numpy as np
import pyarrow as pa
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.verify_m2_backbone import verify_saved_job  # noqa: E402


def validate_candidate(config: Mapping[str, Any]) -> None:
    if (config.get("version") != "m2_data_3_1_candidate_v2" or config.get("status") != "CANDIDATE_NOT_ACTIVE"
            or config.get("scope") != "registration_and_checkpoint_reuse"
            or config.get("scientific_certification") is not False
            or config.get("source_baseline", {}).get("policy") != "preserve_original_hashes"
            or config.get("source_baseline", {}).get("replacement_authorized") is not False):
        raise ValueError("This inspection requires the inactive candidate and preserved original baseline")
    execution = config.get("execution", {})
    if (any(execution.get(k) is not False for k in
            ("training_allowed", "measurement_allowed", "scientific_execution_allowed", "overwrite_existing_artifacts", "auto_advance"))
            or execution.get("stop_after_stage_report") is not True):
        raise ValueError("Candidate inspection cannot activate a training or measurement stage")
    kge = config.get("kge", {})
    required = {"model", "norm", "dimension", "seeds", "epochs", "learning_rate", "margin", "batch_size",
                "normalize_entities", "training", "training_split"}
    if (not required.issubset(kge) or kge["model"] != "TransE" or type(kge["norm"]) is not int or kge["norm"] != 2
            or type(kge["dimension"]) is not int or kge["dimension"] not in (32, 64)
            or kge["seeds"] != [13, 37, 101] or any(type(s) is not int for s in kge["seeds"])
            or any(type(kge[k]) is not int or kge[k] <= 0 for k in ("epochs", "batch_size"))
            or any(type(kge[k]) not in (int, float) or not math.isfinite(kge[k]) or kge[k] <= 0
                   for k in ("learning_rate", "margin"))
            or type(kge["normalize_entities"]) is not bool
            or kge["training"] != "independent_from_scratch_per_snapshot_seed" or kge["training_split"] != "full_snapshot"):
        raise ValueError("Complete, explicit controlled-backbone configuration is required")
    ids = config.get("snapshots")
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or any(not isinstance(s, str) or not s for s in ids):
        raise ValueError("Distinct explicit snapshot IDs required")
    baseline = config["source_baseline"]
    backbone = config.get("backbone", {})
    if (baseline.get("lock_path") != "data/manifests/sources.lock.json"
            or baseline.get("protocol_path") != "configs/protocol_v1.yaml"
            or config.get("package_root") != "data/evolving_kg_downstream_v3_1"
            or config.get("release_id") != "evolving_kg_downstream_v3.1"
            or any(not isinstance(backbone.get(key), str) or not backbone[key]
                   for key in ("run", "verification_receipt", "legacy_package_root"))):
        raise ValueError("Candidate source/release/backbone identity must be explicit")
    required_bindings = {baseline["lock_path"], baseline["protocol_path"],
                         (Path(backbone["run"]) / "experiment_manifest.json").as_posix(),
                         backbone["verification_receipt"],
                         (Path(config["package_root"]) / "release_manifest.json").as_posix(),
                         "configs/m2_external_dev_v1.yaml"}
    bindings = config.get("bindings", {})
    if (not required_bindings.issubset(bindings)
            or any(not isinstance(value, str) or len(value) != 64
                   or set(value) - set("0123456789abcdef") for value in bindings.values())):
        raise ValueError("Candidate must bind source baseline, receipt, release and original backbone manifest")


def model_configs_for_candidate(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_candidate(config)
    kge = config["kge"]
    fields = ("dimension", "norm", "margin", "learning_rate", "epochs", "batch_size", "normalize_entities")
    return {str(seed): {**{key: kge[key] for key in fields}, "seed": seed} for seed in kge["seeds"]}


def validate_saved_model_configs(config: Mapping[str, Any], saved: Mapping[str, Any]) -> None:
    if encode(dict(saved)) != encode(model_configs_for_candidate(config)):
        raise ValueError("Saved checkpoint configuration differs from the proposed training configuration")


def validate_job_inventory(records: Sequence[Mapping[str, Any]], snapshot_ids: Sequence[str], seeds: Sequence[int]) -> None:
    expected = {(sid, seed) for sid in snapshot_ids for seed in seeds}
    if (len(records) != len(expected)
            or any(not isinstance(r.get("snapshot_id"), str) or type(r.get("seed")) is not int for r in records)
            or {(r["snapshot_id"], r["seed"]) for r in records} != expected):
        raise ValueError("Missing, duplicate or unexpected snapshot/seed jobs")


def source_readiness(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    baseline = config["source_baseline"]
    lock = json.loads(safe_file(root, baseline["lock_path"]).read_bytes())
    protocol = yaml.safe_load(safe_file(root, baseline["protocol_path"]).read_bytes())
    if set(lock) != {"proposal", "execution_plan", "patch"}:
        raise ValueError("Original source lock must contain the three registered roles")
    rows = []
    for role, spec in lock.items():
        try:
            path = safe_file(root, spec["path"])
        except FileNotFoundError:
            path = None
        actual = None if path is None else sha(path.read_bytes())
        rows.append({"role": role, "path": spec["path"], "expected_sha256": spec["sha256"],
                     "actual_sha256": actual, "exists": actual is not None,
                     "matches_lock": actual == spec["sha256"],
                     "protocol_matches_lock": protocol["sources"].get(role + "_sha256") == spec["sha256"]})
    return {"ready": all(r["matches_lock"] and r["protocol_matches_lock"] for r in rows), "roles": rows}


def execution_blockers(config: Mapping[str, Any], sources: Mapping[str, Any]) -> list[str]:
    reasons = []
    if not sources["ready"]:
        reasons.append("SOURCE_BASELINE_INCOMPLETE")
    if config["status"] != "ACTIVE_REGISTERED":
        reasons.append("CANDIDATE_NOT_ACTIVE")
    reference, alignment, measurement = config["reference"], config["alignment"], config["measurement"]
    if reference["frequency_definition"] is None:
        reasons.append("STRUCTURAL_FREQUENCY_UNREGISTERED")
    if reference["merge_order"] is None:
        reasons.append("STRUCTURAL_MERGE_ORDER_UNREGISTERED")
    if (alignment["maximum_relative_holdout_residual"] is None
            or alignment["maximum_relative_fit_holdout_gap"] is None):
        reasons.append("RELATIVE_RESIDUAL_OPERATING_RANGE_UNREGISTERED")
    for name in ("epsilon", "mad_threshold"):
        if measurement[name]["registration"] != "scientifically_registered":
            reasons.append(name.upper() + "_NOT_SCIENTIFICALLY_REGISTERED")
    if reference["degree_bin_registration"] != "scientifically_registered":
        reasons.append("INITIAL_BUCKET_BOUNDARIES_UNREGISTERED")
    if (alignment["anchor_count_registration"] != "scientifically_registered"
            or alignment["rank_tolerance_registration"] != "scientifically_registered"):
        reasons.append("ANCHOR_COUNTS_OR_RANK_TOLERANCE_UNREGISTERED")
    return reasons


def inspect_source_history(root: Path, config: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Bounded search of two exact source paths in local Git; never restores substitutes."""
    lock = json.loads(safe_file(root, config["source_baseline"]["lock_path"]).read_bytes())
    targets = {lock[role]["path"]: lock[role]["sha256"] for role in ("execution_plan", "patch")}
    listing = subprocess.check_output(["git", "rev-list", "--objects", "--all", "--", *targets], cwd=root, text=True)
    results = []
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or parts[1] not in targets:
            continue
        payload = subprocess.check_output(["git", "cat-file", "blob", parts[0]], cwd=root)
        actual = sha(payload)
        results.append({"path": parts[1], "git_blob": parts[0], "bytes": len(payload),
                        "expected_sha256": targets[parts[1]], "actual_sha256": actual,
                        "matches_original": actual == targets[parts[1]]})
    return results


def inspect_backbone(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    validate_candidate(config)
    hashes = {}
    for relative, expected in config["bindings"].items():
        actual = sha(safe_file(root, relative).read_bytes())
        if actual != expected:
            raise ValueError(f"Bound input changed: {relative}")
        hashes[relative] = actual
    backbone = root / config["backbone"]["run"]
    # Validate the run path before traversing any of its artifact references.
    manifest_path = safe_file(root, Path(config["backbone"]["run"]) / "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    if manifest["stage"] != "backbone_training" or manifest["scientific_certification"] is not False:
        raise ValueError("Unexpected original checkpoint-run scope")
    artifact_hashes = {}
    for relative, expected in manifest["artifacts"]["hashes"].items():
        actual = sha(safe_file(backbone, relative).read_bytes())
        if actual != expected:
            raise ValueError(f"Saved artifact changed: {relative}")
        artifact_hashes[relative] = actual
    code_comparison = {}
    for relative, expected in manifest["inputs"]["code_hashes"].items():
        archive = safe_file(backbone, Path("code") / relative)
        if sha(archive.read_bytes()) != expected:
            raise ValueError(f"Archived producer code changed: {relative}")
        current = sha(safe_file(root, relative).read_bytes())
        code_comparison[relative] = {"archived_sha256": expected, "current_sha256": current,
                                     "matches": current == expected}
    receipt = json.loads(safe_file(root, config["backbone"]["verification_receipt"]).read_bytes())
    if (receipt["status"] != "BACKBONE_ARTIFACT_VERIFICATION_PASS"
            or receipt["manifest_sha256"] != sha(manifest_path.read_bytes())
            or receipt["verifier_sha256"] != manifest["inputs"]["code_hashes"]["scripts/verify_m2_backbone.py"]):
        raise ValueError("Original verification receipt is not bound to this run/code")
    package = root / config["package_root"]
    safe_file(root, Path(config["package_root"]) / "config/downstream_transe_config.yaml")
    datasets, package_report = inspect_package(package)
    if list(datasets) != config["snapshots"]:
        raise ValueError("Snapshot inventory differs from candidate configuration")
    hashes.update({str(Path(config["package_root"]) / relative).replace("\\", "/"): digest
                   for relative, digest in package_report["input_hashes"].items()})
    frozen_snapshots = []
    for row in package_report["snapshots"]:
        previous = (Path(config["backbone"]["legacy_package_root"]) / "snapshots"
                    / f"snapshot_{row['snapshot_id']}_canonical.parquet").as_posix()
        if manifest["inputs"]["hashes"].get(previous) != row["physical_sha256"]:
            raise ValueError("Current canonical snapshot differs from frozen training-input bytes")
        frozen_snapshots.append({"snapshot_id": row["snapshot_id"], "sha256": row["physical_sha256"],
                                 "matches_frozen_backbone_input": True})
    summary = json.loads(safe_file(backbone, "summary.json").read_bytes())
    jobs = json.loads(safe_file(backbone, "registered_jobs.json").read_bytes())
    model_configs = json.loads(safe_file(backbone, "model_configs.json").read_bytes())
    mappings_path = safe_file(backbone, "mappings.json")
    mappings = json.loads(mappings_path.read_bytes())
    validate_job_inventory(summary["results"], config["snapshots"], config["kge"]["seeds"])
    validate_job_inventory(jobs, config["snapshots"], config["kge"]["seeds"])
    validate_saved_model_configs(config, model_configs)
    if (set(mappings) != set(datasets) or summary["scientific_certification"] is not False
            or summary["status"] != "BACKBONE_TECHNICAL_CHECKS_PASS"
            or summary["training_executions"] != 2 * len(jobs) or summary["byte_identical_replays"] != len(jobs)
            or manifest["inputs"]["snapshot_hash"] != sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()}))
            or manifest["inputs"]["entity_map_hash"] != sha(mappings_path.read_bytes())
            or manifest["inputs"]["relation_map_hash"] != sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}))):
        raise ValueError("Backbone summary or aggregate mapping lineage differs")
    checked = []
    seed_manifests = []
    for record in summary["results"]:
        sid, seed = record["snapshot_id"], record["seed"]
        result = verify_saved_job(backbone, datasets[sid], model_configs[str(seed)], record, mappings[sid], manifest["git"])
        path = safe_file(backbone, record["path"])
        seed_manifest_path = safe_file(backbone, path.with_name(f"seed_{seed}_manifest.json").relative_to(backbone))
        seed_manifest = json.loads(seed_manifest_path.read_bytes())
        validate_manifest(seed_manifest)
        expected_artifacts = {}
        for repeat in (1, 2):
            checkpoint = path.with_name(f"seed_{seed}_repeat_{repeat}.json")
            for artifact in (checkpoint, checkpoint.with_name(checkpoint.name + ".sha256")):
                expected_artifacts[artifact.relative_to(backbone).as_posix()] = sha(artifact.read_bytes())
        if (seed_manifest["seed"] != seed or seed_manifest["git"] != manifest["git"]
                or seed_manifest["stage"] != "backbone_training" or seed_manifest["scientific_certification"] is not False
                or seed_manifest["inputs"]["hashes"] != manifest["inputs"]["hashes"]
                or seed_manifest["inputs"]["code_hashes"] != manifest["inputs"]["code_hashes"]
                or seed_manifest["inputs"]["config_hash"] != manifest["inputs"]["config_hash"]
                or seed_manifest["inputs"]["training_config_hash"] != record["config_hash"]
                or seed_manifest["inputs"]["snapshot_hash"] != datasets[sid].snapshot_hash
                or seed_manifest["inputs"]["entity_map_hash"] != record["entity_map_hash"]
                or seed_manifest["inputs"]["relation_map_hash"] != record["relation_map_hash"]
                or seed_manifest["artifacts"]["hashes"] != expected_artifacts):
            raise ValueError("Per-seed manifest does not bind the verified checkpoint")
        seed_manifests.append({"path": seed_manifest_path.relative_to(backbone).as_posix(), "sha256": sha(seed_manifest_path.read_bytes())})
        checked.append({**result, "checkpoint_sha256": record["checkpoint_sha256"], "saved_replay_byte_identical": True})
    environment = {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__, "pyarrow": pa.__version__}
    environment_matches = all(environment.get(key) == value for key, value in manifest["environment"].items())
    sources = source_readiness(root, config)
    blockers = execution_blockers(config, sources)
    current_code_matches = all(row["matches"] for row in code_comparison.values())
    return {"status": "TECHNICAL_REUSE_CHECKS_PASS" if current_code_matches and environment_matches else "SAVED_ARTIFACTS_VALID_REUSE_CONDITIONAL",
            "technical_reuse_eligible": current_code_matches and environment_matches,
            "scientific_certification": False, "scientific_execution_ready": False, "G3_evaluated": False,
            "execution_blockers": blockers, "source_readiness": sources, "configuration": dict(config),
            "local_source_history": inspect_source_history(root, config),
            "checkpoint_configurations_verified": len(checked), "saved_checkpoint_files_verified": 2 * len(checked),
            "saved_replays_byte_identical": len(checked), "artifact_hashes_checked": len(artifact_hashes),
            "code_comparison": code_comparison, "environment_current": environment,
            "environment_training": manifest["environment"], "environment_matches": environment_matches,
            "snapshot_comparison": frozen_snapshots, "seed_manifests_verified": seed_manifests,
            "checkpoint_details": checked, "original_git": manifest["git"],
            "original_manifest_sha256": sha(manifest_path.read_bytes()),
            "entity_map_hash": sha(mappings_path.read_bytes()),
            "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()})),
            "input_hashes": hashes, "original_artifact_hashes": artifact_hashes,
            "scope": "Saved checkpoint technical reuse, not original M1 recertification or new training/measurement execution",
            "limitations": ["No fresh training/replay was performed; saved repeat files were compared.",
                            "Original legacy input paths were not restored or rewritten; canonical bytes were rebound explicitly.",
                            "Alignment Q and raw noise/temporal distances were not certified for reuse."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/m2_data_3_1_candidate_v2.yaml"))
    args = parser.parse_args()
    config_path = safe_file(ROOT, args.config)
    config = yaml.safe_load(config_path.read_bytes())
    report = inspect_backbone(ROOT, config)
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_reuse_readiness" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "report.json", report)
    write_json(out / "resolved_config.json", config)
    hashes = {"report.json": sha((out / "report.json").read_bytes()), "resolved_config.json": sha((out / "resolved_config.json").read_bytes())}
    inspected = dict(report["input_hashes"])
    inspected[args.config.as_posix()] = sha(config_path.read_bytes())
    inspected["scripts/inspect_m2_reuse.py"] = sha(Path(__file__).read_bytes())
    # Source files are explicit inputs when present; missing originals remain blockers.
    for row in report["source_readiness"]["roles"]:
        if row["actual_sha256"] is not None:
            inspected[row["path"]] = row["actual_sha256"]
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    *[(name, ctypes.c_ulonglong) for name in
                      ("total_physical", "available_physical", "total_pagefile", "available_pagefile",
                       "total_virtual", "available_virtual", "available_extended")]]
    if os.name == "nt":
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise OSError("Could not measure inspection-host RAM")
        ram_bytes = memory.total_physical
    else:
        ram_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "git": provenance(),
                "inputs": {"data_hash": sha(encode(inspected)), "snapshot_hash": sha(encode(report["snapshot_comparison"])),
                           "query_hash": None, "entity_map_hash": report["entity_map_hash"],
                           "relation_map_hash": report["relation_map_hash"],
                           "config_hash": sha(encode(config)), "hashes": inspected},
                "seed": None, "environment": report["environment_current"],
                "hardware": {"cpu": os.environ.get("PROCESSOR_IDENTIFIER", platform.processor()),
                             "ram": ram_bytes},
                "artifacts": {"hashes": hashes},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/inspect_m2_reuse.py"},
                "scientific_certification": False, "stage": "registration_and_reuse_inspection"}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"run": out.relative_to(ROOT).as_posix(), "status": report["status"],
                      "checkpoints": report["checkpoint_configurations_verified"],
                      "scientific_execution_ready": False}))


if __name__ == "__main__":
    main()
