"""One explicit v2 null OR drift stage; inactive/incomplete registration fails closed."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import yaml
import numpy as np
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.inspect_m2_reuse import execution_blockers, source_readiness  # noqa: E402
from drift.measurement_v2 import build_drift_stage_v2, build_null_stage_v2, validate_settings  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402
from scripts.verify_m2_measurement_v2 import verify_stage_v2  # noqa: E402

DEFAULT_CONFIG = Path("configs/m2_measurement_v2_candidate.yaml")


def bound_file(root: Path, descriptor: Mapping[str, Any], inputs: dict[str, str]) -> Path:
    if not isinstance(descriptor, Mapping) or not {"path", "sha256"}.issubset(descriptor):
        raise ValueError("Explicit input path and physical SHA-256 required")
    path = safe_file(root, descriptor["path"])
    actual = sha(path.read_bytes())
    if actual != descriptor["sha256"]:
        raise ValueError("Bound input hash mismatch: " + str(descriptor["path"]))
    inputs[path.relative_to(root).as_posix()] = actual
    return path


def inspect_registration(root: Path, config_path: Path) -> tuple[dict, dict, dict, dict]:
    path = safe_file(root, config_path)
    cfg = yaml.safe_load(path.read_bytes())
    if (set(cfg) != {"version", "status", "stage", "scientific_certification", "parent_config", "settings", "input_plan", "null_stage", "execution"}
            or cfg["version"] != "m2_measurement_runner_v2" or cfg["stage"] not in ("null", "drift")
            or cfg["scientific_certification"] is not False
            or cfg["execution"].get("overwrite_existing_artifacts") is not False
            or cfg["execution"].get("auto_execute_next_stage") is not False
            or cfg["execution"].get("stop_after_stage_report") is not True):
        raise ValueError("Explicit single-stage immutable v2 contract required")
    hashes = {path.relative_to(root).as_posix(): sha(path.read_bytes())}
    parent = yaml.safe_load(bound_file(root, cfg["parent_config"], hashes).read_bytes())
    baseline = parent["source_baseline"]
    if (baseline.get("policy") != "preserve_original_hashes" or baseline.get("replacement_authorized") is not False
            or baseline.get("lock_path") != "data/manifests/sources.lock.json"
            or baseline.get("protocol_path") != "configs/protocol_v1.yaml"
            or parent.get("package_root") != "data/evolving_kg_downstream_v3_1"
            or parent.get("kge", {}).get("seeds") != [13, 37, 101]):
        raise ValueError("Original baseline, data3.1 and fixed seed scope required")
    required = {baseline["lock_path"], baseline["protocol_path"], parent["package_root"] + "/release_manifest.json"}
    if not required.issubset(parent["bindings"]):
        raise ValueError("Parent must bind protocol, source lock and release")
    for relative, digest in parent["bindings"].items():
        bound_file(root, {"path": relative, "sha256": digest}, hashes)
    sources = source_readiness(root, parent)
    for row in sources["roles"]:
        if row["actual_sha256"] is not None:
            hashes[row["path"]] = row["actual_sha256"]
    blockers = execution_blockers(parent, sources)
    if (parent["execution"].get("measurement_allowed") is not True
            or parent["execution"].get("scientific_execution_allowed") is not True):
        blockers.append("PARENT_MEASUREMENT_EXECUTION_NOT_REGISTERED")
    if cfg["status"] != "REGISTERED_STAGE" or cfg["execution"].get("measurement_allowed") is not True:
        blockers.append("RUNNER_STAGE_NOT_REGISTERED")
    try:
        validate_settings(cfg["settings"])
    except ValueError:
        blockers.append("GEOMETRY_OR_CALIBRATION_SETTINGS_INCOMPLETE")
    common = {"cosine_estimand": parent["measurement"]["cosine_estimand"],
              "minimum_reference_entities": parent["reference"]["minimum_entities_after_LTO"],
              "epsilon": parent["measurement"]["epsilon"]["value"],
              "mad_threshold": parent["measurement"]["mad_threshold"]["value"],
              **{k: parent["alignment"][k] for k in ("rank_relative_tolerance", "minimum_rank_fraction",
                "maximum_normalized_orthogonality_error", "maximum_relative_holdout_residual", "maximum_relative_fit_holdout_gap")}}
    if any(cfg["settings"].get(k) != v for k, v in common.items()):
        blockers.append("RUNNER_PARENT_SETTINGS_CONFLICT")
    protocol = yaml.safe_load(safe_file(root, baseline["protocol_path"]).read_bytes())
    registered = protocol.get("drift", {}).get("measurement_v2")
    if (not isinstance(registered, dict) or registered.get("settings") != cfg["settings"]
            or registered.get("frequency_definition") != parent["reference"]["frequency_definition"]
            or not registered.get("frequency_definition")
            or registered.get("merge_order") != parent["reference"]["merge_order"] or not registered.get("merge_order")):
        blockers.append("PROTOCOL_MEASUREMENT_V2_UNREGISTERED")
    if (protocol["kge"]["dimension"] != parent["kge"]["dimension"]
            or protocol["alignment"]["fit_count"] != parent["alignment"]["fit_count"]
            or protocol["alignment"]["holdout_count"] != parent["alignment"]["holdout_count"]
            or protocol["drift"]["mad_epsilon"] != cfg["settings"]["epsilon"]):
        blockers.append("PROTOCOL_BACKBONE_ANCHOR_OR_EPSILON_UNREGISTERED")
    plan = cfg["input_plan"]
    if (not isinstance(plan, dict) or not {"path", "sha256"}.issubset(plan)
            or not isinstance(registered, dict) or plan["sha256"] not in registered.get("approved_input_plan_sha256s", [])):
        blockers.append("INPUT_PLAN_NOT_REGISTERED")
    if cfg["stage"] == "drift" and not isinstance(cfg["null_stage"], dict):
        blockers.append("VERIFIED_NULL_STAGE_MISSING")
    return cfg, parent, {"status": "BLOCKED" if blockers else "READY_FOR_REQUESTED_STAGE",
                         "execution_blockers": sorted(set(blockers)), "source_readiness": sources,
                         "scientific_certification": False, "G3_evaluated": False}, hashes


def load_stage_inputs(root: Path, cfg: Mapping[str, Any], parent: Mapping[str, Any], hashes: dict[str, str]) -> tuple:
    plan = json.loads(bound_file(root, cfg["input_plan"], hashes).read_bytes())
    if set(plan) != {"transition_id", "anchor_plan", "bucket_plan", "checkpoints", "alignments"}:
        raise ValueError("Exact registered stage input-plan fields required")
    transition = plan["transition_id"]
    endpoints = transition.split("->")
    snapshots = parent["snapshots"]
    if len(endpoints) != 2 or tuple(endpoints) not in list(zip(snapshots, snapshots[1:])):
        raise ValueError("Plan transition is outside registered adjacent snapshot population")
    datasets, report = inspect_package(root / parent["package_root"])
    for relative, digest in report["input_hashes"].items():
        hashes[(Path(parent["package_root"]) / relative).as_posix()] = digest
    checkpoints = {}
    for descriptor in plan["checkpoints"]:
        path = bound_file(root, descriptor, hashes)
        sidecar = safe_file(root, path.with_name(path.name + ".sha256").relative_to(root))
        if sidecar.read_text(encoding="utf-8").split() != [sha(path.read_bytes()), path.name]:
            raise ValueError("Missing/mismatched mandatory checkpoint sidecar")
        hashes[sidecar.relative_to(root).as_posix()] = sha(sidecar.read_bytes())
        cp = KGECheckpoint.load(path)
        key = cp.provenance.snapshot_id, cp.provenance.seed
        if key in checkpoints or key[0] not in endpoints or key[1] not in (13, 37, 101):
            raise ValueError("Duplicate/unexpected checkpoint input")
        dataset = datasets[key[0]]
        expected_config = {k: parent["kge"][k] for k in
                           ("dimension", "norm", "margin", "learning_rate", "epochs", "batch_size", "normalize_entities")}
        expected_config["seed"] = key[1]
        if (cp.provenance.snapshot_hash != dataset.snapshot_hash
                or cp.provenance.dimension != parent["kge"]["dimension"]
                or cp.provenance.config_hash != sha(json.dumps(expected_config, sort_keys=True).encode())
                or cp.provenance.entity_mapping_hash != dataset.compute_mapping_hash()
                or cp.provenance.relation_mapping_hash != sha(json.dumps(dataset.get_relation_mapping(), sort_keys=True).encode())
                or set(cp.entity_embeddings) != set(dataset.entities) or set(cp.relation_embeddings) != set(dataset.relations)):
            raise ValueError("Checkpoint differs from actual canonical snapshot/mappings")
        checkpoints[key] = cp, descriptor["sha256"]
    alignments = {}
    for descriptor in plan["alignments"]:
        record = json.loads(bound_file(root, descriptor, hashes).read_bytes())
        key = record["source_snapshot"], record["target_snapshot"], record["source_seed"], record["target_seed"]
        if key in alignments:
            raise ValueError("Duplicate alignment input")
        alignments[key] = record, descriptor["sha256"], sha(encode(record))
    anchors = json.loads(bound_file(root, plan["anchor_plan"], hashes).read_bytes())
    if "key" in plan["anchor_plan"]:
        if plan["anchor_plan"]["key"] != transition:
            raise ValueError("Anchor plan selector differs from transition")
        anchors = anchors[transition]
    if (len(anchors["split"]["fit_anchors"]) != parent["alignment"]["fit_count"]
            or len(anchors["split"]["holdout_anchors"]) != parent["alignment"]["holdout_count"]):
        raise ValueError("Registered fit/holdout counts differ from plan")
    buckets = json.loads(bound_file(root, plan["bucket_plan"], hashes).read_bytes())
    null = None if cfg["stage"] == "null" else json.loads(bound_file(root, cfg["null_stage"], hashes).read_bytes())
    return transition, checkpoints, alignments, anchors, buckets, cfg["settings"], null


def run(root: Path, config_path: Path, check_only: bool = False) -> tuple[Path, bool]:
    cfg, parent, readiness, hashes = inspect_registration(root, config_path)
    code_paths = ["scripts/run_m2_measurement_v2.py", "scripts/verify_m2_measurement_v2.py", "scripts/inspect_m2_inputs.py",
                  "scripts/inspect_m2_reuse.py", "scripts/verify_m2_entity_null_v2.py", "src/drift/measurement_v2.py",
                  "src/drift/artifact_null.py", "src/drift/artifact_drift.py", "src/drift/null.py",
                  "src/kge/checkpoint.py", "src/kge/contract.py", "src/kge/math_utils.py",
                  "configs/schemas/m2_measurement_v2.schema.yaml"]
    code_payloads = {relative: (ROOT / relative).read_bytes() for relative in code_paths}
    now = datetime.now(timezone.utc)
    token = now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    artifact = None
    snapshot_hash = entity_map_hash = relation_map_hash = None
    if not readiness["execution_blockers"]:
        args = load_stage_inputs(root, cfg, parent, hashes)
        transition, checkpoints, alignments, anchors, buckets, settings, null = args
        snapshot_hash = sha(encode({sid: cp.provenance.snapshot_hash for (sid, _), (cp, _) in sorted(checkpoints.items())}))
        entity_map_hash = sha(encode({sid: cp.provenance.entity_mapping_hash for (sid, _), (cp, _) in sorted(checkpoints.items())}))
        relation_map_hash = sha(encode({sid: cp.provenance.relation_mapping_hash for (sid, _), (cp, _) in sorted(checkpoints.items())}))
        if not check_only:
            if cfg["stage"] == "null":
                artifact = build_null_stage_v2(*args[:-1])
            else:
                artifact = build_drift_stage_v2(*args)
            verify_stage_v2(artifact, checkpoints, alignments, anchors, buckets, settings, null)
    # Verify immutable input bytes/code again after computation or inspection.
    for relative, expected in hashes.items():
        if sha(safe_file(root, relative).read_bytes()) != expected:
            raise ValueError("Input changed during stage: " + relative)
    for relative, payload in code_payloads.items():
        if (ROOT / relative).read_bytes() != payload:
            raise ValueError("Code changed during stage: " + relative)
    category = "m2_measurement_v2_readiness" if artifact is None else f"m2_{cfg['stage']}_v2"
    out = root / "outputs" / category / token
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "readiness.json", readiness)
    write_json(out / "resolved_config.json", cfg)
    if artifact is not None:
        write_json(out / "artifact.json", artifact)
        write_json(out / "independent_verification.json", {"status": "INDEPENDENT_NUMPY_STAGE_VERIFICATION_PASS",
                   "artifact_sha256": sha((out / "artifact.json").read_bytes()), "scientific_certification": False,
                   "G3_evaluated": False, "verifier_sha256": sha((ROOT / "scripts/verify_m2_measurement_v2.py").read_bytes())})
    for relative, payload in code_payloads.items():
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as f:
            f.write(payload)
        hashes[relative] = sha(payload)
    manifest = {"experiment_id": token, "protocol_version": "v1-draft", "git": provenance(), "seed": None,
                "scientific_certification": False, "stage": "measurement_v2_readiness" if artifact is None else cfg["stage"],
                "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": snapshot_hash, "query_hash": None,
                           "entity_map_hash": entity_map_hash, "relation_map_hash": relation_map_hash,
                           "config_hash": sha(encode(cfg)), "hashes": hashes},
                "environment": {"python": platform.python_version(), "os": platform.platform(),
                                "numpy": np.__version__, "pyarrow": pa.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_measurement_v2.py"},
                "auto_execute_next_stage": False}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    return out, not readiness["execution_blockers"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--check-only", action="store_true")
    options = parser.parse_args()
    path, ready = run(ROOT, options.config, options.check_only)
    print(json.dumps({"output": path.relative_to(ROOT).as_posix(), "ready": ready, "scientific_certification": False}))
    sys.exit(0 if ready else 2)
