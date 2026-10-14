"""Independently inspect saved backbone bytes, full mappings and registered lineage."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, safe_file, sha, validate_manifest, write_json,
)
from kge.contract import SnapshotDataset  # noqa: E402


def verify_saved_job(
    run: Path, dataset: SnapshotDataset, model_config: dict[str, Any], record: dict[str, Any],
    mapping: dict[str, Any], git: dict[str, Any],
) -> dict[str, Any]:
    path = safe_file(run, record["path"])
    repeat_path = safe_file(run, path.with_name(path.name.replace("repeat_1", "repeat_2")).relative_to(run))
    payload = path.read_bytes()
    if payload != repeat_path.read_bytes() or sha(payload) != record["checkpoint_sha256"]:
        raise ValueError("Checkpoint exact byte replay or record hash mismatch")
    for checkpoint_path in (path, repeat_path):
        sidecar = safe_file(run, checkpoint_path.with_name(checkpoint_path.name + ".sha256").relative_to(run))
        expected = sidecar.read_text(encoding="utf-8").split()
        if expected != [sha(checkpoint_path.read_bytes()), checkpoint_path.name]:
            raise ValueError("Checkpoint sidecar missing or mismatched")
    raw = json.loads(payload)
    prov = raw["provenance"]
    cfg_hash = sha(json.dumps(model_config, sort_keys=True).encode())
    entities = dataset.get_entity_mapping()
    relations = dataset.get_relation_mapping()
    entity_hash = sha(json.dumps(entities, sort_keys=True).encode())
    relation_hash = sha(json.dumps(relations, sort_keys=True).encode())
    if (prov["snapshot_id"] != dataset.snapshot_id or record["snapshot_id"] != dataset.snapshot_id
            or prov["snapshot_hash"] != dataset.snapshot_hash or record["snapshot_hash"] != dataset.snapshot_hash
            or prov["seed"] != model_config["seed"] or record["seed"] != model_config["seed"]
            or prov["dimension"] != model_config["dimension"] or record["dimension"] != model_config["dimension"]
            or prov["model"] != "TransE" or prov["norm"] != 2
            or prov["config_hash"] != cfg_hash or record["config_hash"] != cfg_hash
            or prov["entity_mapping_hash"] != entity_hash or record["entity_map_hash"] != entity_hash
            or prov["relation_mapping_hash"] != relation_hash or record["relation_map_hash"] != relation_hash
            or prov["git_commit"] != git["commit"] or prov["git_dirty"] != git["dirty_state"]
            or mapping != {"entities": entities, "relations": relations}
            or set(raw["entity_embeddings"]) != set(entities)
            or set(raw["relation_embeddings"]) != set(relations)
            or record["exact_replay"] is not True
            or (record["triples"], record["entities"], record["relations"])
               != (len(dataset.triples), len(entities), len(relations))):
        raise ValueError("Checkpoint snapshot/config/mapping/git lineage mismatch")
    vectors = [*raw["entity_embeddings"].values(), *raw["relation_embeddings"].values()]
    if any(len(v) != model_config["dimension"] or not all(math.isfinite(x) for x in v) for v in vectors):
        raise ValueError("Checkpoint has invalid vector dimension or non-finite values")
    losses = raw["training_metrics"]["epoch_losses"]
    metrics = raw["training_metrics"]
    if (len(losses) != model_config["epochs"] or not all(math.isfinite(x) and x >= 0 for x in losses)
            or metrics["num_epochs"] != model_config["epochs"] or record["num_epochs"] != model_config["epochs"]
            or metrics["final_loss"] != losses[-1] or record["final_loss"] != losses[-1]
            or record["first_loss"] != losses[0] or metrics["dev_split_ratio"] != 0.0
            or metrics["dev_losses"] != [] or metrics["final_dev_loss"] is not None):
        raise ValueError("Checkpoint training metrics inconsistent with full-snapshot execution")
    semantic = {"provenance": prov, "entities": sorted(raw["entity_embeddings"]),
                "relations": sorted(raw["relation_embeddings"]),
                "entity_vectors": {e: [round(x, 7) for x in raw["entity_embeddings"][e]]
                                   for e in sorted(raw["entity_embeddings"])},
                "relation_vectors": {r: [round(x, 7) for x in raw["relation_embeddings"][r]]
                                     for r in sorted(raw["relation_embeddings"])}}
    if raw["artifact_hash"] != sha(json.dumps(semantic, sort_keys=True).encode()):
        raise ValueError("Checkpoint semantic artifact hash mismatch")
    norms = [math.sqrt(sum(x * x for x in v)) for v in raw["entity_embeddings"].values()]
    return {"snapshot_id": dataset.snapshot_id, "seed": model_config["seed"],
            "entity_norm_range": [min(norms), max(norms)], "first_loss": losses[0], "final_loss": losses[-1]}


def verify(run: Path) -> dict[str, Any]:
    run = run.resolve()
    if not run.is_relative_to((ROOT / "outputs/m2_backbone").resolve()):
        raise ValueError("Verifier requires a registered backbone output directory")
    manifest_path = safe_file(run, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    if (manifest["stage"] != "backbone_training" or manifest["scientific_certification"] is not False
            or manifest["mode"] != "external_package_dev_experiment" or manifest["access"]["state"] != "dev"):
        raise ValueError("Backbone manifest stage/scope mismatch")
    for relative, digest in manifest["artifacts"]["hashes"].items():
        if sha(safe_file(run, relative).read_bytes()) != digest:
            raise ValueError(f"Artifact hash mismatch: {relative}")
    for relative, digest in manifest["inputs"]["hashes"].items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input hash mismatch: {relative}")
    for relative, digest in manifest["inputs"]["code_hashes"].items():
        if sha(safe_file(run / "code", relative).read_bytes()) != digest:
            raise ValueError(f"Archived code hash mismatch: {relative}")
    design = json.loads((run / "resolved_config.json").read_bytes())
    proposal_path = safe_file(ROOT, design["approval"]["proposal_path"])
    if (design["status"] != "APPROVED_FOR_DEV_EXECUTION"
            or design["approval"]["proposal_sha256"] != sha(proposal_path.read_bytes())
            or manifest["inputs"]["config_hash"] != sha(encode(design))
            or manifest["inputs"]["data_hash"] != sha(encode(manifest["inputs"]["hashes"]))):
        raise ValueError("Approval, resolved config, or aggregate data hash mismatch")
    for field, relative in (("preflight_manifest_hash", design["input_preflight"]),
                            ("pilot_manifest_hash", design["pilot_run"])):
        path = safe_file(ROOT, f"{relative}/experiment_manifest.json")
        if manifest["inputs"][field] != sha(path.read_bytes()):
            raise ValueError("Prior-stage manifest lineage mismatch")
    datasets, _ = inspect_package(ROOT / PACKAGE)
    model_configs = json.loads((run / "model_configs.json").read_bytes())
    mappings = json.loads((run / "mappings.json").read_bytes())
    summary = json.loads((run / "summary.json").read_bytes())
    jobs = json.loads((run / "registered_jobs.json").read_bytes())
    expected_keys = {(sid, seed) for sid in design["snapshots"] for seed in design["kge"]["seeds"]}
    if (len(expected_keys) != 30 or set(datasets) != set(design["snapshots"])
            or set(mappings) != set(datasets) or set(model_configs) != {"13", "37", "101"}
            or len(jobs) != 30 or len(summary["results"]) != 30
            or {(j["snapshot_id"], j["seed"]) for j in jobs} != expected_keys
            or {(j["snapshot_id"], j["seed"]) for j in summary["results"]} != expected_keys
            or summary["status"] != "BACKBONE_TECHNICAL_CHECKS_PASS"
            or summary["training_executions"] != 60 or summary["byte_identical_replays"] != 30
            or summary["scientific_certification"] is not False):
        raise ValueError("Missing, duplicate, or unexpected registered training jobs")
    cfg = design["kge"]
    for seed in cfg["seeds"]:
        expected_cfg = {"dimension": cfg["dimension"], "norm": cfg["norm"], "margin": cfg["margin"],
                        "learning_rate": cfg["learning_rate"], "epochs": cfg["epochs"], "batch_size": 32,
                        "seed": seed, "normalize_entities": cfg["normalize_entities"]}
        if model_configs[str(seed)] != expected_cfg:
            raise ValueError("Serialized runtime config differs from approved parameters")
    if (manifest["inputs"]["snapshot_hash"] != sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()}))
            or manifest["inputs"]["entity_map_hash"] != sha((run / "mappings.json").read_bytes())
            or manifest["inputs"]["relation_map_hash"] != sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}))
            or manifest["inputs"]["query_hash"] is not None):
        raise ValueError("Aggregate mapping/snapshot lineage mismatch")
    checked = []
    pilot_matches = 0
    for record in summary["results"]:
        sid, seed = record["snapshot_id"], record["seed"]
        checked.append(verify_saved_job(run, datasets[sid], model_configs[str(seed)], record, mappings[sid], manifest["git"]))
        checkpoint_path = safe_file(run, record["path"])
        seed_manifest = json.loads(checkpoint_path.with_name(f"seed_{seed}_manifest.json").read_bytes())
        validate_manifest(seed_manifest)
        expected_artifacts = {p.relative_to(run).as_posix(): sha(p.read_bytes())
                              for repeat in (1, 2)
                              for cp in (checkpoint_path.with_name(f"seed_{seed}_repeat_{repeat}.json"),)
                              for p in (cp, cp.with_name(cp.name + ".sha256"))}
        if (seed_manifest["seed"] != seed or seed_manifest["git"] != manifest["git"]
                or seed_manifest["stage"] != "backbone_training"
                or seed_manifest["scientific_certification"] is not False
                or seed_manifest["inputs"]["hashes"] != manifest["inputs"]["hashes"]
                or seed_manifest["inputs"]["code_hashes"] != manifest["inputs"]["code_hashes"]
                or seed_manifest["inputs"]["config_hash"] != manifest["inputs"]["config_hash"]
                or seed_manifest["inputs"]["training_config_hash"] != record["config_hash"]
                or seed_manifest["inputs"]["snapshot_hash"] != datasets[sid].snapshot_hash
                or seed_manifest["inputs"]["entity_map_hash"] != record["entity_map_hash"]
                or seed_manifest["inputs"]["relation_map_hash"] != record["relation_map_hash"]
                or seed_manifest["artifacts"]["hashes"] != expected_artifacts):
            raise ValueError("Per-seed manifest unbound from checkpoint or run")
        if sid in ("T01", "T02"):
            pilot_checkpoint = safe_file(ROOT, f"{design['pilot_run']}/dim_64/{sid}/seed_{seed}_repeat_1.json")
            if checkpoint_path.read_bytes() != pilot_checkpoint.read_bytes():
                raise ValueError("T01/T02 checkpoint differs from equivalent full-snapshot pilot")
            pilot_matches += 1
    return {"status": "BACKBONE_ARTIFACT_VERIFICATION_PASS", "scientific_certification": False,
            "stage": "backbone_training", "manifest_sha256": sha(manifest_path.read_bytes()),
            "checkpoint_configurations": len(checked), "byte_identical_replays": len(checked),
            "exact_pilot_checkpoint_matches": pilot_matches, "per_seed_manifests_checked": 30,
            "input_hashes_checked": len(manifest["inputs"]["hashes"]),
            "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "details": checked, "verified_at_real": datetime.now(timezone.utc).isoformat(),
            "verifier_sha256": sha(Path(__file__).read_bytes()),
            "scope": "Saved full-snapshot Dev backbone bytes/config/mappings/metrics/lineage only; no G3 or temporal certification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    output = args.run / ("independent_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                         + "_" + uuid4().hex[:8] + ".json")
    write_json(output, result)
    print(json.dumps({"output": str(output), **{k: v for k, v in result.items() if k != "details"}}, indent=2))
