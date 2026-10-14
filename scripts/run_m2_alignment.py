"""One-stage fixed-anchor alignment of the verified M2 Dev backbone; no null/drift."""
from __future__ import annotations

import argparse
import itertools
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
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.verify_m2_backbone import verify as verify_backbone  # noqa: E402
from drift.fixed_anchors import FIXED_ANCHOR_VERSION, select_fixed_stratified_anchors  # noqa: E402
from drift.anchors import AnchorSplit  # noqa: E402
from drift.procrustes import align_embeddings_procrustes  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402

CONFIG_PATH = Path("configs/m2_alignment_v1.yaml")


def comparison_jobs(prev: str, nxt: str, seeds: list[int]) -> list[dict[str, Any]]:
    if seeds != [13, 37, 101] or prev == nxt:
        raise ValueError("Alignment jobs require adjacent distinct snapshots and all registered seeds")
    jobs = [{"source_snapshot": prev, "target_snapshot": nxt, "source_seed": s,
             "target_seed": s, "alignment_type": "cross_time"} for s in seeds]
    jobs.extend({"source_snapshot": sid, "target_snapshot": sid, "source_seed": a,
                 "target_seed": b, "alignment_type": "same_snapshot_cross_seed"}
                for sid in (prev, nxt) for a, b in itertools.combinations(seeds, 2))
    for job in jobs:
        job["comparison_id"] = (f"{job['source_snapshot']}_seed{job['source_seed']}"
                                f"__{job['target_snapshot']}_seed{job['target_seed']}")
    return jobs


def align_one(
    source: KGECheckpoint, target: KGECheckpoint, split: AnchorSplit,
    criteria: dict[str, Any], job: dict[str, Any],
) -> dict[str, Any]:
    split.verify_disjoint()
    if (len(split.fit_anchors) != criteria["fit_count"]
            or len(split.holdout_anchors) != criteria["holdout_count"]
            or len(set(split.fit_anchors)) != len(split.fit_anchors)
            or len(set(split.holdout_anchors)) != len(split.holdout_anchors)):
        raise ValueError("Alignment requires the exact nonempty disjoint anchor counts")
    dimension = source.provenance.dimension
    if dimension != target.provenance.dimension or dimension != criteria["minimum_numerical_rank"]:
        raise ValueError("Checkpoint dimension differs from the registered alignment design")
    for checkpoint, sid, seed in ((source, job["source_snapshot"], job["source_seed"]),
                                   (target, job["target_snapshot"], job["target_seed"])):
        checkpoint.verify_finite()
        if checkpoint.provenance.snapshot_id != sid or checkpoint.provenance.seed != seed:
            raise ValueError("Alignment checkpoint identity differs from registered job")
        if any(len(v) != dimension for v in checkpoint.entity_embeddings.values()):
            raise ValueError("Inconsistent entity vector dimensions")
        if any(e not in checkpoint.entity_embeddings for e in (*split.fit_anchors, *split.holdout_anchors)):
            raise ValueError("Missing fit or holdout anchor in checkpoint")
    result = align_embeddings_procrustes(source.entity_embeddings, target.entity_embeddings,
                                         split, alignment_type=job["alignment_type"])
    valid, reason = result.diagnostics.check_alignment_validity(
        min_numerical_rank=criteria["minimum_numerical_rank"],
        max_fit_holdout_gap=criteria["max_fit_holdout_gap"],
        max_holdout_residual=criteria["max_holdout_residual"],
        max_orthogonality_error=criteria["max_orthogonality_error"])
    record = {**job, "dimension": dimension, "diagnostics": asdict(result.diagnostics),
              "available": valid, "unavailable_reason": reason, "Q": result.Q,
              "source_mean": result.source_mean, "target_mean": result.target_mean,
              "source_checkpoint_semantic_hash": source.artifact_hash,
              "target_checkpoint_semantic_hash": target.artifact_hash}
    encode(record)  # Reject non-finite outputs; never serialize NaN/Inf as availability.
    return record


def run() -> Path:
    stage_path = safe_file(ROOT, CONFIG_PATH)
    stage = yaml.safe_load(stage_path.read_bytes())
    approved_path = safe_file(ROOT, stage["approved_config_path"])
    approved = yaml.safe_load(approved_path.read_bytes())
    if (stage["stage"] != "alignment" or stage["status"] != "APPROVED_FOR_DEV_EXECUTION"
            or stage["scientific_certification"] is not False or stage["repetitions"] != 2
            or stage["auto_execute_next_stage"] is not False
            or stage["anchor_implementation_version"] != FIXED_ANCHOR_VERSION
            or sha(approved_path.read_bytes()) != stage["approved_config_sha256"]):
        raise ValueError("Alignment stage design or approved configuration binding mismatch")
    backbone = ROOT / stage["backbone_run"]
    backbone_manifest_path = safe_file(backbone, "experiment_manifest.json")
    if sha(backbone_manifest_path.read_bytes()) != stage["backbone_manifest_sha256"]:
        raise ValueError("Backbone manifest differs from registered input")
    verification = verify_backbone(backbone)
    backbone_manifest = json.loads(backbone_manifest_path.read_bytes())
    datasets, _ = inspect_package(ROOT / PACKAGE)
    snapshots, seeds = approved["snapshots"], approved["kge"]["seeds"]
    if list(datasets) != snapshots or approved["kge"]["dimension"] != 64:
        raise ValueError("Snapshot population or dimension differs from the approved design")
    criteria = approved["alignment"]
    expected_allocation = {"joint_sample_count": criteria["fit_count"] + criteria["holdout_count"],
                           "sample_quotas": "largest_remainder_by_exact_pretransition_degree",
                           "fit_quotas": "largest_remainder_within_joint_sample",
                           "holdout_quotas": "joint_sample_minus_fit", "quota_tie": "ascending_degree",
                           "entity_order": "sha256_salt_transition_degree_entity_then_entity_id",
                           "same_split_for_all_nine_comparisons": True}
    if stage["anchor_allocation_details"] != expected_allocation:
        raise ValueError("Anchor allocation details differ from the implementation")
    hashes = dict(backbone_manifest["inputs"]["hashes"])
    hashes[CONFIG_PATH.as_posix()] = sha(stage_path.read_bytes())
    hashes[(backbone_manifest_path.relative_to(ROOT)).as_posix()] = sha(backbone_manifest_path.read_bytes())
    for relative, digest in backbone_manifest["artifacts"]["hashes"].items():
        hashes[(backbone.relative_to(ROOT) / relative).as_posix()] = digest
    summary = json.loads((backbone / "summary.json").read_bytes())
    checkpoints = {}
    checkpoint_paths = {}
    for row in summary["results"]:
        key = row["snapshot_id"], row["seed"]
        path = safe_file(backbone, row["path"])
        checkpoints[key] = KGECheckpoint.load(path)
        checkpoint_paths[key] = path
    plans, jobs = {}, []
    for prev, nxt in zip(snapshots, snapshots[1:]):
        transition = f"{prev}->{nxt}"
        persistent = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        degrees = {e: datasets[prev].entity_metadata[e].degree for e in persistent}
        plan = select_fixed_stratified_anchors(persistent, degrees, criteria["fit_count"],
                                               criteria["holdout_count"], f"{criteria['salt']}:{transition}")
        plans[transition] = plan
        jobs.extend({"transition_id": transition, **j} for j in comparison_jobs(prev, nxt, seeds))
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_alignment" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    started, git = time.perf_counter(), provenance()
    resolved = {"stage": stage, "approved": approved}
    config_hash = sha(encode(resolved))
    write_json(out / "resolved_config.json", resolved)
    write_json(out / "input_hashes.json", hashes)
    write_json(out / "backbone_verification.json", verification)
    # All 9 anchor sets and 81 jobs exist before the first SVD/model diagnostic.
    write_json(out / "anchor_plans.json", {t: asdict(p) for t, p in plans.items()})
    write_json(out / "registered_jobs.json", jobs)
    code_paths = [Path(__file__), ROOT / "scripts/verify_m2_alignment.py",
                  ROOT / "scripts/inspect_m2_inputs.py", ROOT / "scripts/verify_m2_backbone.py",
                  *sorted((ROOT / "src/drift").glob("*.py")), *sorted((ROOT / "src/kge").glob("*.py"))]
    code_hashes = {}
    for path in code_paths:
        relative = path.relative_to(ROOT)
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = path.read_bytes()
        with target.open("xb") as handle:
            handle.write(payload)
        code_hashes[relative.as_posix()] = sha(payload)
    write_json(out / "code_hashes.json", code_hashes)
    environment = {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__}
    results = []
    for index, job in enumerate(jobs, start=1):
        transition = job["transition_id"]
        source_key = job["source_snapshot"], job["source_seed"]
        target_key = job["target_snapshot"], job["target_seed"]
        source, target = checkpoints[source_key], checkpoints[target_key]
        record = align_one(source, target, plans[transition].split, criteria, job)
        record.update(source_checkpoint_sha256=sha(checkpoint_paths[source_key].read_bytes()),
                      target_checkpoint_sha256=sha(checkpoint_paths[target_key].read_bytes()),
                      config_hash=config_hash, anchor_plan_hash=sha(encode(asdict(plans[transition]))))
        replay = align_one(source, target, plans[transition].split, criteria, job)
        replay.update({k: record[k] for k in ("source_checkpoint_sha256", "target_checkpoint_sha256", "config_hash", "anchor_plan_hash")})
        if encode(record) != encode(replay):
            raise ValueError("Alignment repeat bytes differ with identical inputs")
        folder = out / "alignments" / transition.replace("->", "__")
        folder.mkdir(parents=True, exist_ok=True)
        paths = [folder / f"{job['comparison_id']}_repeat_{r}.json" for r in (1, 2)]
        write_json(paths[0], record)
        write_json(paths[1], replay)
        entry = {**job, "available": record["available"], "unavailable_reason": record["unavailable_reason"],
                 "path": paths[0].relative_to(out).as_posix(), "diagnostics": record["diagnostics"],
                 "exact_replay": True, "alignment_sha256": sha(paths[0].read_bytes())}
        results.append(entry)
        ds_source, ds_target = datasets[source_key[0]], datasets[target_key[0]]
        manifest = {"experiment_id": f"{out.name}_{transition}_{job['comparison_id']}", "protocol_version": "v1-draft",
                    "stage": "alignment", "mode": stage["mode"], "scientific_certification": False,
                    "git": git, "seed": job["source_seed"], "target_seed": job["target_seed"],
                    "inputs": {"data_hash": sha(encode(hashes)),
                               "snapshot_hash": sha(encode([ds_source.snapshot_hash, ds_target.snapshot_hash])),
                               "query_hash": None,
                               "entity_map_hash": sha(encode([source.provenance.entity_mapping_hash, target.provenance.entity_mapping_hash])),
                               "relation_map_hash": sha(encode([source.provenance.relation_mapping_hash, target.provenance.relation_mapping_hash])),
                               "config_hash": config_hash, "hashes": hashes, "code_hashes": code_hashes,
                               "backbone_manifest_hash": stage["backbone_manifest_sha256"],
                               "anchor_plan_hash": record["anchor_plan_hash"],
                               "checkpoint_hashes": {"source": record["source_checkpoint_sha256"], "target": record["target_checkpoint_sha256"]}},
                    "environment": environment,
                    "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                    "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in paths}},
                    "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_alignment.py"}}
        validate_manifest(manifest)
        write_json(folder / f"{job['comparison_id']}_manifest.json", manifest)
        if index % 9 == 0:
            subset = results[-9:]
            print(f"{transition}: {sum(r['available'] for r in subset)}/9 available; exact repeats PASS", flush=True)
    transitions = {t: {"available": all(r["available"] for r in results if r["transition_id"] == t),
                       "alignment_passed": sum(r["available"] for r in results if r["transition_id"] == t),
                       "persistent_entities": plan.candidate_count, "fit_anchors": len(plan.split.fit_anchors),
                       "holdout_anchors": len(plan.split.holdout_anchors)} for t, plan in plans.items()}
    all_available = all(r["available"] for r in results)
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed during alignment: {relative}")
    for relative, digest in code_hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Code changed during alignment: {relative}")
    summary = {"status": "ALIGNMENT_DEV_CHECKS_PASS" if all_available else "ALIGNMENT_UNAVAILABLE",
               "scientific_certification": False, "comparisons": 81, "svd_executions": 162,
               "byte_identical_replays": 81, "available_comparisons": sum(r["available"] for r in results),
               "transitions": transitions, "results": results, "input_unchanged": True,
               "elapsed_seconds": time.perf_counter() - started, "next_stage": "empirical_null",
               "auto_execute_next_stage": False}
    write_json(out / "summary.json", summary)
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "stage": "alignment",
                "mode": stage["mode"], "scientific_certification": False, "git": git, "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)),
                           "snapshot_hash": sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()})),
                           "query_hash": None, "entity_map_hash": sha(encode({sid: ds.compute_mapping_hash() for sid, ds in datasets.items()})),
                           "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()})),
                           "config_hash": config_hash, "hashes": hashes, "code_hashes": code_hashes,
                           "backbone_manifest_hash": stage["backbone_manifest_sha256"]},
                "environment": environment,
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes())
                                          for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_alignment.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), **{k: v for k, v in summary.items() if k != "results"}}, indent=2))
    return out


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
