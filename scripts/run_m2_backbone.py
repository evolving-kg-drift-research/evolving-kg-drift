"""One-stage approved M2 Dev backbone training; stops before alignment/null/drift."""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pyarrow as pa
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.run_m2_pilot import train_replayed  # noqa: E402
from scripts.verify_m2_pilot import verify as verify_pilot  # noqa: E402
from kge.model import TransEConfig  # noqa: E402

CONFIG_PATH = Path("configs/m2_external_dev_v1.yaml")
PROPOSAL_SHA256 = "4b959e4f86191bef7545697ea804a0a7e379336a28d3c44681b6a87d61d264b6"


def validate_design(design: dict[str, Any], proposal: dict[str, Any], proposal_hash: str) -> None:
    # The historical proposal spells its null-distribution section as unquoted
    # YAML `null`, which PyYAML loads as a None key. Preserve approved bytes and
    # normalize this known serialization detail before comparing parameters.
    proposal = dict(proposal)
    if None in proposal:
        if "null" in proposal:
            raise ValueError("Proposal contains ambiguous null-distribution sections")
        proposal["null"] = proposal.pop(None)
    approval = design.get("approval", {})
    if (design.get("status") != "APPROVED_FOR_DEV_EXECUTION"
            or design.get("scientific_certification") is not False
            or approval.get("actor") != "user" or not approval.get("instruction")
            or approval.get("proposal_sha256") != proposal_hash
            or proposal_hash != PROPOSAL_SHA256):
        raise PermissionError("M2 Dev execution requires the approved, hash-bound proposal")
    for field in ("mode", "snapshots", "kge", "alignment", "null", "drift", "execution",
                  "pilot_run", "input_preflight", "authorization_scope"):
        if field not in design or design[field] != proposal[field]:
            raise ValueError(f"Resolved design differs from the approved proposal: {field}")
    if (design["snapshots"] != [f"T{i:02d}" for i in range(1, 11)]
            or design["kge"]["seeds"] != [13, 37, 101]
            or design["kge"]["dimension"] != 64
            or design["kge"]["model"] != "TransE" or design["kge"]["norm"] != 2
            or design["kge"]["repetitions"] != 2
            or design["execution"]["next_stage_only"] != "backbone_training"):
        raise ValueError("Backbone design exceeds the registered stage scope")


def model_config(design: dict[str, Any], seed: int) -> TransEConfig:
    cfg = design["kge"]
    return TransEConfig(dimension=cfg["dimension"], norm=cfg["norm"], seed=seed,
                       epochs=cfg["epochs"], learning_rate=cfg["learning_rate"],
                       margin=cfg["margin"], normalize_entities=cfg["normalize_entities"])


def load_registered_inputs(design: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    preflight = ROOT / design["input_preflight"]
    if not preflight.resolve().is_relative_to((ROOT / "outputs/m2_preflight").resolve()):
        raise ValueError("Unregistered preflight directory")
    report = json.loads(safe_file(preflight, "report.json").read_bytes())
    manifest_path = safe_file(preflight, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    if (report["status"] != "PACKAGE_TECHNICAL_CHECKS_PASS"
            or manifest["scientific_certification"] is not False
            or report["input_hashes"] != manifest["inputs"]["hashes"]):
        raise ValueError("Preflight is unsuccessful or not bound to its input hashes")
    for relative, digest in manifest["artifacts"]["hashes"].items():
        if sha(safe_file(preflight, relative).read_bytes()) != digest:
            raise ValueError(f"Preflight artifact changed: {relative}")
    hashes = dict(report["input_hashes"])
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed since preflight: {relative}")
    datasets, current = inspect_package(ROOT / PACKAGE)
    registered = {s["snapshot_id"]: s["snapshot_hash"] for s in report["snapshots"]}
    if ({sid: ds.snapshot_hash for sid, ds in datasets.items()} != registered
            or list(datasets) != design["snapshots"]):
        raise ValueError("Snapshot population or semantic identity changed since preflight")
    pilot = ROOT / design["pilot_run"]
    verification = verify_pilot(pilot)
    if verification["recommended_dimension"] != design["kge"]["dimension"]:
        raise ValueError("Approved dimension differs from the verified pilot selection")
    evidence = {"preflight_manifest_hash": sha(manifest_path.read_bytes()),
                "pilot_manifest_hash": verification["manifest_sha256"],
                "pilot_verification": verification, "snapshot_records": current["snapshots"]}
    return {"datasets": datasets, "evidence": evidence}, hashes


def run() -> Path:
    config_path = safe_file(ROOT, CONFIG_PATH)
    design = yaml.safe_load(config_path.read_bytes())
    proposal_path = safe_file(ROOT, design["approval"]["proposal_path"])
    proposal_bytes = proposal_path.read_bytes()
    validate_design(design, yaml.safe_load(proposal_bytes), sha(proposal_bytes))
    loaded_inputs, hashes = load_registered_inputs(design)
    datasets, evidence = loaded_inputs["datasets"], loaded_inputs["evidence"]
    for relative in (CONFIG_PATH, proposal_path.relative_to(ROOT), Path("configs/protocol_v1.yaml"),
                     Path("configs/kge.yaml"), Path("configs/schemas/experiment_manifest.schema.yaml")):
        hashes[relative.as_posix()] = sha(safe_file(ROOT, relative).read_bytes())
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_backbone" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    git = provenance()
    started = time.perf_counter()
    resolved_configs = {str(seed): asdict(model_config(design, seed)) for seed in design["kge"]["seeds"]}
    write_json(out / "resolved_config.json", design)
    write_json(out / "model_configs.json", resolved_configs)
    write_json(out / "input_hashes.json", hashes)
    write_json(out / "input_evidence.json", evidence)
    write_json(out / "mappings.json", {sid: {"entities": ds.get_entity_mapping(),
                                           "relations": ds.get_relation_mapping()}
                                        for sid, ds in datasets.items()})
    jobs = [{"snapshot_id": sid, "seed": seed, "dimension": design["kge"]["dimension"],
             "snapshot_hash": ds.snapshot_hash, "entity_map_hash": ds.compute_mapping_hash(),
             "relation_map_hash": sha(json.dumps(ds.get_relation_mapping(), sort_keys=True).encode())}
            for sid, ds in datasets.items() for seed in design["kge"]["seeds"]]
    write_json(out / "registered_jobs.json", jobs)
    code_paths = [Path(__file__), ROOT / "scripts/verify_m2_backbone.py",
                  ROOT / "scripts/inspect_m2_inputs.py", ROOT / "scripts/run_m2_pilot.py",
                  ROOT / "scripts/verify_m2_pilot.py", ROOT / "scripts/evaluate_legacy_t01.py",
                  ROOT / "scripts/audit_legacy_split_t01.py", ROOT / "scripts/run_legacy_transe_t01.py",
                  *sorted((ROOT / "src/kge").glob("*.py")),
                  ROOT / "src/drift/anchors.py", ROOT / "src/drift/procrustes.py"]
    code_hashes = {}
    for path in code_paths:
        relative = path.relative_to(ROOT)
        payload = path.read_bytes()
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(payload)
        code_hashes[relative.as_posix()] = sha(payload)
    write_json(out / "code_hashes.json", code_hashes)
    environment = {"python": platform.python_version(), "os": platform.platform(),
                   "numpy": np.__version__, "pyarrow": pa.__version__}
    results = []
    for index, job in enumerate(jobs, start=1):
        sid, seed = job["snapshot_id"], job["seed"]
        ds = datasets[sid]
        folder = out / "checkpoints" / sid
        begin_job = time.perf_counter()
        ckpt, record = train_replayed(ds, model_config(design, seed), folder, git)
        record.update(path=(folder / f"seed_{seed}_repeat_1.json").relative_to(out).as_posix(),
                      elapsed_seconds=time.perf_counter() - begin_job,
                      snapshot_hash=ds.snapshot_hash, triples=len(ds.triples), entities=len(ds.entities),
                      relations=len(ds.relations), first_loss=ckpt.training_metrics["epoch_losses"][0],
                      final_loss=ckpt.training_metrics["final_loss"], num_epochs=design["kge"]["epochs"])
        results.append(record)
        paths = [folder / f"seed_{seed}_repeat_{r}.json" for r in (1, 2)]
        manifest = {"experiment_id": f"{out.name}_{sid}_seed_{seed}", "protocol_version": "v1-draft",
                    "stage": "backbone_training", "mode": design["mode"], "scientific_certification": False,
                    "git": git, "seed": seed,
                    "inputs": {"data_hash": hashes[f"{PACKAGE.as_posix()}/snapshots/snapshot_{sid}_canonical.parquet"],
                               "snapshot_hash": ds.snapshot_hash, "query_hash": None,
                               "entity_map_hash": record["entity_map_hash"], "relation_map_hash": record["relation_map_hash"],
                               "config_hash": sha(encode(design)), "training_config_hash": record["config_hash"],
                               "hashes": hashes, "code_hashes": code_hashes,
                               "preflight_manifest_hash": evidence["preflight_manifest_hash"],
                               "pilot_manifest_hash": evidence["pilot_manifest_hash"]},
                    "environment": environment,
                    "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured",
                                 "elapsed_seconds": record["elapsed_seconds"]},
                    "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes())
                                              for cp in paths for p in (cp, cp.with_name(cp.name + ".sha256"))}},
                    "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_backbone.py"}}
        validate_manifest(manifest)
        write_json(folder / f"seed_{seed}_manifest.json", manifest)
        print(f"{index}/30 {sid} seed={seed}: finite, mapping, serialization, exact replay PASS", flush=True)
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed during training: {relative}")
    for relative, digest in code_hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Code changed during training: {relative}")
    summary = {"status": "BACKBONE_TECHNICAL_CHECKS_PASS", "stage": "backbone_training",
               "scientific_certification": False, "snapshots": 10, "checkpoint_configurations": 30,
               "training_executions": 60, "byte_identical_replays": 30, "results": results,
               "input_unchanged": True, "elapsed_seconds": time.perf_counter() - started,
               "next_stage": "alignment", "stop_after_stage_report": True,
               "limitations": ["External-package Dev training; no historical temporal/identity certification",
                               "No alignment, null, drift, QA ranking or G3 certification in this stage"]}
    write_json(out / "summary.json", summary)
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "stage": "backbone_training",
                "mode": design["mode"], "scientific_certification": False, "git": git, "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)),
                           "snapshot_hash": sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()})),
                           "query_hash": None, "entity_map_hash": sha((out / "mappings.json").read_bytes()),
                           "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()})),
                           "config_hash": sha(encode(design)), "hashes": hashes, "code_hashes": code_hashes,
                           "preflight_manifest_hash": evidence["preflight_manifest_hash"],
                           "pilot_manifest_hash": evidence["pilot_manifest_hash"]},
                "environment": environment,
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured",
                             "elapsed_seconds": summary["elapsed_seconds"]},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes())
                                          for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_backbone.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), **{k: v for k, v in summary.items() if k != "results"}}, indent=2))
    return out


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
