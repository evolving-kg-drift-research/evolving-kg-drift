"""One-stage longitudinal drift from verified saved alignment and LTO artifacts."""
from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from scripts.run_m2_null import parquet_bytes  # noqa: E402
from drift.artifact_drift import ARTIFACT_DRIFT_VERSION, calibrated_metrics, saved_temporal_observations  # noqa: E402
from drift.null import compute_median  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402

CONFIG_PATH = Path("configs/m2_drift_v1.yaml")
TEMPORAL_SCHEMA = pa.schema([
    pa.field("transition_id", pa.string(), False), pa.field("entity_id", pa.string(), False),
    pa.field("seed", pa.int32(), False), pa.field("source_snapshot", pa.string(), False),
    pa.field("target_snapshot", pa.string(), False), pa.field("temporal_displacement", pa.float64(), False),
    *[pa.field(k, pa.string(), False) for k in ("alignment_sha256", "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256")],
], metadata={b"artifact_schema": b"saved_temporal_displacements_v1"})
DRIFT_SCHEMA = pa.schema([
    pa.field("transition_id", pa.string(), False), pa.field("entity_id", pa.string(), False),
    pa.field("pretransition_degree", pa.int64(), False), pa.field("bucket_id", pa.string(), False),
    pa.field("delta_time", pa.float64(), False), pa.field("signed_excess", pa.float64()), pa.field("SED_plus", pa.float64()),
    pa.field("null_median", pa.float64()), pa.field("null_mad", pa.float64()), pa.field("null_robust_scale", pa.float64()),
    pa.field("removed_target_observations", pa.int32(), False), pa.field("reference_entity_count", pa.int64(), False),
    pa.field("observation_count", pa.int64(), False), pa.field("available", pa.bool_(), False),
    pa.field("unavailable_reason", pa.string(), False), pa.field("null_artifact_sha256", pa.string(), False),
], metadata={b"artifact_schema": b"saved_entity_drift_v1"})


def run() -> Path:
    stage_path = safe_file(ROOT, CONFIG_PATH)
    stage = yaml.safe_load(stage_path.read_bytes())
    approved_path = safe_file(ROOT, stage["approved_config_path"])
    approved = yaml.safe_load(approved_path.read_bytes())
    expected_drift = {"raw_metric": "one_minus_cosine_after_centered_alignment",
                      "temporal_aggregation": "median_three_parallel_seeds",
                      "signed_excess": "temporal_displacement_minus_LTO_null_median",
                      "SED_plus": "max_zero_signed_excess_divided_by_1.4826_MAD_plus_epsilon", "keep_signed_excess": True}
    if (stage["stage"] != "longitudinal_drift" or stage["status"] != "APPROVED_FOR_DEV_EXECUTION"
            or stage["scientific_certification"] is not False or stage["repetitions"] != 2
            or stage["auto_execute_next_stage"] is not False or stage["stop_after_stage_report"] is not True
            or stage["centered_norm_floor"] != 1e-12 or stage["component_version"] != ARTIFACT_DRIFT_VERSION
            or sha(approved_path.read_bytes()) != stage["approved_config_sha256"]
            or approved["kge"]["seeds"] != [13, 37, 101] or approved["drift"] != expected_drift):
        raise ValueError("Drift stage differs from approved design")
    null_run = ROOT / stage["null_run"]
    null_manifest_path = safe_file(null_run, "experiment_manifest.json")
    receipt_path = safe_file(ROOT, stage["null_verification_path"])
    receipt = json.loads(receipt_path.read_bytes())
    if (sha(null_manifest_path.read_bytes()) != stage["null_manifest_sha256"]
            or sha(receipt_path.read_bytes()) != stage["null_verification_sha256"]
            or receipt["manifest_sha256"] != stage["null_manifest_sha256"]
            or receipt["status"] != "NULL_ARTIFACT_VERIFICATION_PASS"
            or receipt["entity_LTO_statistics_recomputed"] != 6897 or receipt["lto_available"] != 6897
            or sha(safe_file(null_run, "code/scripts/verify_m2_null.py").read_bytes()) != receipt["verifier_sha256"]):
        raise ValueError("Drift requires completed verified null inputs")
    parent = json.loads(null_manifest_path.read_bytes())
    validate_manifest(parent)
    for base, catalog in ((ROOT, parent["inputs"]["hashes"]), (null_run, parent["artifacts"]["hashes"])):
        for relative, digest in catalog.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Verified null input/artifact changed: {relative}")
    null_resolved = json.loads(safe_file(null_run, "resolved_config.json").read_bytes())
    alignment = ROOT / null_resolved["stage"]["alignment_run"]
    alignment_resolved = json.loads(safe_file(alignment, "resolved_config.json").read_bytes())
    backbone = ROOT / alignment_resolved["stage"]["backbone_run"]
    checkpoints = {(r["snapshot_id"], r["seed"]): KGECheckpoint.load(safe_file(backbone, r["path"]))
                   for r in json.loads(safe_file(backbone, "summary.json").read_bytes())["results"]}
    datasets, _ = inspect_package(ROOT / PACKAGE)
    records: dict[str, dict[int, tuple[dict[str, Any], str]]] = {}
    for row in json.loads(safe_file(alignment, "summary.json").read_bytes())["results"]:
        if row["alignment_type"] == "cross_time":
            path = safe_file(alignment, row["path"])
            records.setdefault(row["transition_id"], {})[row["source_seed"]] = json.loads(path.read_bytes()), sha(path.read_bytes())
    null_results = {r["transition_id"]: r for r in json.loads(safe_file(null_run, "summary.json").read_bytes())["results"]}
    hashes = dict(parent["inputs"]["hashes"])
    hashes.update({(null_run.relative_to(ROOT) / p).as_posix(): h for p, h in parent["artifacts"]["hashes"].items()})
    for path in (stage_path, null_manifest_path, receipt_path):
        hashes[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_drift" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    started, git = time.perf_counter(), provenance()
    resolved = {"stage": stage, "approved": approved}
    config_hash = sha(encode(resolved))
    write_json(out / "resolved_config.json", resolved)
    write_json(out / "input_hashes.json", hashes)
    write_json(out / "null_verification.json", receipt)
    code_hashes = {}
    code_paths = [Path(__file__), ROOT / "scripts/verify_m2_drift.py", ROOT / "scripts/inspect_m2_inputs.py",
                  ROOT / "scripts/run_m2_null.py", *sorted((ROOT / "src/drift").glob("*.py")),
                  *sorted((ROOT / "src/kge").glob("*.py"))]
    for path in code_paths:
        relative = path.relative_to(ROOT)
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = path.read_bytes()
        with target.open("xb") as handle:
            handle.write(payload)
        code_hashes[relative.as_posix()] = sha(payload)
    write_json(out / "code_hashes.json", code_hashes)
    environment = {"python": platform.python_version(), "os": platform.platform(), "pyarrow": pa.__version__}
    jobs = [{"transition_id": f"{prev}->{nxt}", "endpoints": [prev, nxt],
             "entities": sorted(set(datasets[prev].entities) & set(datasets[nxt].entities)), "seeds": [13, 37, 101]}
            for prev, nxt in zip(approved["snapshots"], approved["snapshots"][1:])]
    write_json(out / "registered_jobs.json", jobs)
    all_temporal, all_drift, results = [], [], []
    for job in jobs:
        prev, nxt = job["endpoints"]
        transition, entities = job["transition_id"], job["entities"]
        null_path = safe_file(null_run, null_results[transition]["path"])
        null = json.loads(null_path.read_bytes())
        null_hash = sha(null_path.read_bytes())
        if null["transition_id"] != transition or set(null["lto_statistics"]) != set(entities):
            raise ValueError("Temporal and LTO persistent populations differ")
        artifacts = []
        for _ in (1, 2):
            temporal = saved_temporal_observations(transition, entities, (prev, nxt), records[transition], checkpoints, stage["centered_norm_floor"])
            values: dict[str, list[float]] = {e: [] for e in entities}
            for row in temporal:
                values[row["entity_id"]].append(row["temporal_displacement"])
            drift = []
            for entity in entities:
                reference = null["lto_statistics"][entity]
                if reference["pretransition_degree"] != datasets[prev].entity_metadata[entity].degree:
                    raise ValueError("LTO conditioning differs from previous snapshot degree")
                metrics = calibrated_metrics(values[entity], reference, approved["null"]["mad_epsilon"],
                                             approved["null"]["degeneracy_mad_threshold"], approved["null"]["min_reference_observations"])
                drift.append({"transition_id": transition, "entity_id": entity, **metrics,
                              "null_median": reference["median"], "null_mad": reference["mad"], "null_robust_scale": reference["robust_scale"],
                              **{k: reference[k] for k in ("pretransition_degree", "bucket_id", "removed_target_observations", "reference_entity_count", "observation_count")},
                              "null_artifact_sha256": null_hash})
            artifacts.append({"component_version": ARTIFACT_DRIFT_VERSION, "transition_id": transition,
                              "config_hash": config_hash, "null_manifest_sha256": stage["null_manifest_sha256"],
                              "temporal_observations": temporal, "entity_drift": drift})
        if encode(artifacts[0]) != encode(artifacts[1]):
            raise ValueError("Drift computation repeat bytes differ")
        folder = out / "transitions" / transition.replace("->", "__")
        folder.mkdir(parents=True, exist_ok=False)
        paths = [folder / f"drift_repeat_{repeat}.json" for repeat in (1, 2)]
        for path, artifact in zip(paths, artifacts):
            write_json(path, artifact)
        drift, temporal = artifacts[0]["entity_drift"], artifacts[0]["temporal_observations"]
        all_drift.extend(drift)
        all_temporal.extend(temporal)
        available = sum(r["available"] for r in drift)
        results.append({"transition_id": transition, "entities": len(entities), "available": available,
                        "positive_excess": sum(r["signed_excess"] is not None and r["signed_excess"] > 0 for r in drift),
                        "delta_time_median": compute_median([r["delta_time"] for r in drift]),
                        "signed_excess_median": compute_median([r["signed_excess"] for r in drift if r["signed_excess"] is not None])
                        if any(r["signed_excess"] is not None for r in drift) else None,
                        "SED_plus_median": compute_median([r["SED_plus"] for r in drift if r["available"]]) if available else None,
                        "path": paths[0].relative_to(out).as_posix(), "sha256": sha(paths[0].read_bytes()), "exact_replay": True})
        nested = {"experiment_id": f"{out.name}_{transition}", "protocol_version": "v1-draft", "stage": "longitudinal_drift",
                  "mode": stage["mode"], "scientific_certification": False, "git": git, "seed": None,
                  "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": sha(encode([datasets[prev].snapshot_hash, datasets[nxt].snapshot_hash])),
                             "query_hash": None, "entity_map_hash": sha(encode([datasets[prev].compute_mapping_hash(), datasets[nxt].compute_mapping_hash()])),
                             "relation_map_hash": sha(encode([datasets[prev].get_relation_mapping(), datasets[nxt].get_relation_mapping()])),
                             "config_hash": config_hash, "hashes": hashes, "code_hashes": code_hashes, "null_manifest_hash": stage["null_manifest_sha256"]},
                  "environment": environment, "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                  "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in paths}},
                  "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_drift.py"}}
        validate_manifest(nested)
        write_json(folder / "experiment_manifest.json", nested)
        print(f"{transition}: {available}/{len(entities)} calibrated entity drift rows", flush=True)
    tables = {}
    for name, rows, schema in (("temporal_displacements.parquet", all_temporal, TEMPORAL_SCHEMA), ("entity_drift.parquet", all_drift, DRIFT_SCHEMA)):
        payload = parquet_bytes(rows, schema)
        if payload != parquet_bytes(rows, schema):
            raise ValueError("Drift Parquet serialization repeats differ")
        with (out / name).open("xb") as handle:
            handle.write(payload)
        tables[name] = {"sha256": sha(payload), "rows": len(rows), "schema": schema.metadata[b"artifact_schema"].decode()}
    write_json(out / "handoff_manifest.json", {"version": "m2_to_m4_dev_handoff_v1", "experiment_id": out.name,
               "mode": stage["mode"], "scientific_certification": False, "access_state": "dev", "config_hash": config_hash,
               "tables": tables, "null_manifest_sha256": stage["null_manifest_sha256"],
               "alignment_manifest_sha256": null_resolved["stage"]["alignment_manifest_sha256"],
               "approved_config_sha256": stage["approved_config_sha256"], "population": "persistent_entities_each_adjacent_transition",
               "seeds": [13, 37, 101], "query_hash": None, "M4_executed": False,
               "limitations": ["External M1 package remains scientifically uncertified", "T01 high-bucket LTO has one reference entity and six correlated observations"]})
    for catalog in (hashes, code_hashes):
        for relative, digest in catalog.items():
            if sha(safe_file(ROOT, relative).read_bytes()) != digest:
                raise ValueError(f"Input/code changed during drift: {relative}")
    count = sum(r["available"] for r in all_drift)
    summary = {"status": "DRIFT_DEV_CHECKS_PASS" if count == len(all_drift) else "DRIFT_PARTIALLY_UNAVAILABLE",
               "scientific_certification": False, "transitions": len(jobs), "entities": len(all_drift), "temporal_observations": len(all_temporal),
               "available": count, "unavailable": len(all_drift) - count, "positive_excess": sum(r["positive_excess"] for r in results),
               "byte_identical_drift_replays": len(jobs), "deterministic_parquet_files": 2, "input_unchanged": True,
               "elapsed_seconds": time.perf_counter() - started, "results": results, "next_stage": "M4_readiness", "auto_execute_next_stage": False}
    write_json(out / "summary.json", summary)
    manifest = {**nested, "experiment_id": out.name,
                "inputs": {**nested["inputs"], "snapshot_hash": sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()})),
                           "entity_map_hash": sha(encode({sid: ds.compute_mapping_hash() for sid, ds in datasets.items()})),
                           "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}))},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), **{k: v for k, v in summary.items() if k != "results"}}, indent=2))
    return out


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
