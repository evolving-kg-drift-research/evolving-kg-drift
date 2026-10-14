"""One-stage empirical null/LTO from saved alignments, stopping before temporal drift."""
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
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, provenance, safe_file, sha, validate_manifest, write_json,
)
from drift.artifact_null import (  # noqa: E402
    ARTIFACT_NULL_VERSION, SEED_PAIRS, build_artifact_null, saved_noise_observations,
)
from kge.checkpoint import KGECheckpoint  # noqa: E402

CONFIG_PATH = Path("configs/m2_null_v1.yaml")
OBSERVATION_SCHEMA = pa.schema([
    pa.field("transition_id", pa.string(), False), pa.field("entity_id", pa.string(), False),
    pa.field("endpoint_snapshot", pa.string(), False), pa.field("source_seed", pa.int32(), False),
    pa.field("target_seed", pa.int32(), False), pa.field("noise_displacement", pa.float64(), False),
    pa.field("alignment_sha256", pa.string(), False), pa.field("anchor_plan_hash", pa.string(), False),
    pa.field("source_checkpoint_sha256", pa.string(), False), pa.field("target_checkpoint_sha256", pa.string(), False),
    pa.field("pretransition_degree", pa.int64(), False), pa.field("bucket_id", pa.string(), False),
], metadata={b"artifact_schema": b"saved_null_observations_v1"})
LTO_SCHEMA = pa.schema([
    pa.field("transition_id", pa.string(), False), pa.field("entity_id", pa.string(), False),
    pa.field("pretransition_degree", pa.int64(), False), pa.field("bucket_id", pa.string(), False),
    pa.field("removed_target_observations", pa.int32(), False), pa.field("reference_entity_count", pa.int64(), False),
    pa.field("observation_count", pa.int64(), False), pa.field("median", pa.float64()),
    pa.field("mad", pa.float64()), pa.field("robust_scale", pa.float64()), pa.field("available", pa.bool_(), False),
    pa.field("unavailable_reason", pa.string(), False), pa.field("null_artifact_sha256", pa.string(), False),
], metadata={b"artifact_schema": b"saved_null_lto_v1"})


def parquet_bytes(rows: list[dict[str, Any]], schema: pa.Schema) -> bytes:
    table = pa.Table.from_pylist(rows, schema=schema)
    if any(table.schema.field(i).nullable is False and table.column(i).null_count for i in range(table.num_columns)):
        raise ValueError("Null in required analysis artifact field")
    buffer = pa.BufferOutputStream()
    pq.write_table(table, buffer, compression="zstd", version="2.6")
    return buffer.getvalue().to_pybytes()


def run() -> Path:
    stage_path = safe_file(ROOT, CONFIG_PATH)
    stage = yaml.safe_load(stage_path.read_bytes())
    approved_path = safe_file(ROOT, stage["approved_config_path"])
    approved = yaml.safe_load(approved_path.read_bytes())
    if (stage["stage"] != "empirical_null" or stage["status"] != "APPROVED_FOR_DEV_EXECUTION"
            or stage["scientific_certification"] is not False or stage["repetitions"] != 2
            or stage["auto_execute_next_stage"] is not False or stage["no_target_specific_remerge"] is not True
            or stage["reference_bucket_merging_stage"] != "pooled_before_LTO"
            or stage["centered_norm_floor"] != 1e-12 or stage["component_version"] != ARTIFACT_NULL_VERSION
            or sha(approved_path.read_bytes()) != stage["approved_config_sha256"]
            or approved["null"]["endpoint_seed_pairs"] != [list(p) for p in SEED_PAIRS]):
        raise ValueError("Null stage configuration differs from the registered design")
    alignment = ROOT / stage["alignment_run"]
    alignment_manifest_path = safe_file(alignment, "experiment_manifest.json")
    if sha(alignment_manifest_path.read_bytes()) != stage["alignment_manifest_sha256"]:
        raise ValueError("Registered alignment manifest mismatch")
    verification_path = safe_file(ROOT, stage["alignment_verification_path"])
    verification = json.loads(verification_path.read_bytes())
    if (sha(verification_path.read_bytes()) != stage["alignment_verification_sha256"]
            or verification["manifest_sha256"] != stage["alignment_manifest_sha256"]
            or verification["status"] != "ALIGNMENT_ARTIFACT_VERIFICATION_PASS"
            or verification["available_transitions"] != 9 or verification["available_comparisons"] != 81):
        raise ValueError("Empirical null requires the completed, available alignment stage")
    if sha(safe_file(alignment, "code/scripts/verify_m2_alignment.py").read_bytes()) != verification["verifier_sha256"]:
        raise ValueError("Alignment receipt verifier fingerprint mismatch")
    alignment_manifest = json.loads(alignment_manifest_path.read_bytes())
    validate_manifest(alignment_manifest)
    for base, catalog in ((ROOT, alignment_manifest["inputs"]["hashes"]),
                          (alignment, alignment_manifest["artifacts"]["hashes"])):
        for relative, digest in catalog.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Verified alignment input/artifact changed: {relative}")
    alignment_resolved = json.loads((alignment / "resolved_config.json").read_bytes())
    backbone = ROOT / alignment_resolved["stage"]["backbone_run"]
    backbone_summary = json.loads(safe_file(backbone, "summary.json").read_bytes())
    checkpoints = {(r["snapshot_id"], r["seed"]): KGECheckpoint.load(safe_file(backbone, r["path"]))
                   for r in backbone_summary["results"]}
    datasets, _ = inspect_package(ROOT / PACKAGE)
    alignment_summary = json.loads((alignment / "summary.json").read_bytes())
    pair_records = {}
    for row in alignment_summary["results"]:
        if row["alignment_type"] == "same_snapshot_cross_seed":
            path = safe_file(alignment, row["path"])
            key = row["source_snapshot"], row["source_seed"], row["target_seed"]
            pair_records.setdefault(row["transition_id"], {})[key] = (json.loads(path.read_bytes()), sha(path.read_bytes()))
    hashes = dict(alignment_manifest["inputs"]["hashes"])
    hashes[CONFIG_PATH.as_posix()] = sha(stage_path.read_bytes())
    hashes[alignment_manifest_path.relative_to(ROOT).as_posix()] = sha(alignment_manifest_path.read_bytes())
    hashes[verification_path.relative_to(ROOT).as_posix()] = sha(verification_path.read_bytes())
    for relative, digest in alignment_manifest["artifacts"]["hashes"].items():
        hashes[(alignment.relative_to(ROOT) / relative).as_posix()] = digest
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_null" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    started, git = time.perf_counter(), provenance()
    resolved = {"stage": stage, "approved": approved}
    config_hash = sha(encode(resolved))
    jobs = []
    for prev, nxt in zip(approved["snapshots"], approved["snapshots"][1:]):
        persistent = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        jobs.append({"transition_id": f"{prev}->{nxt}", "endpoints": [prev, nxt], "entities": persistent,
                     "pretransition_degrees": {e: datasets[prev].entity_metadata[e].degree for e in persistent},
                     "endpoint_pairs": [[sid, a, b] for sid in (prev, nxt) for a, b in SEED_PAIRS]})
    write_json(out / "resolved_config.json", resolved)
    write_json(out / "input_hashes.json", hashes)
    write_json(out / "alignment_verification.json", verification)
    write_json(out / "registered_jobs.json", jobs)
    code_paths = [Path(__file__), ROOT / "scripts/verify_m2_null.py", ROOT / "scripts/verify_m2_alignment.py",
                  ROOT / "scripts/inspect_m2_inputs.py", *sorted((ROOT / "src/drift").glob("*.py")),
                  *sorted((ROOT / "src/kge").glob("*.py"))]
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
    all_observations, all_lto, results = [], [], []
    environment = {"python": platform.python_version(), "os": platform.platform(), "pyarrow": pa.__version__}
    for job in jobs:
        transition = job["transition_id"]
        descriptors = pair_records[transition]
        artifacts, observations = [], []
        for repeat in (1, 2):
            rows = saved_noise_observations(transition, job["entities"], tuple(job["endpoints"]),
                                             descriptors, checkpoints, stage["centered_norm_floor"])
            values: dict[str, list[float]] = {e: [] for e in job["entities"]}
            for row in rows:
                values[row["entity_id"]].append(row["noise_displacement"])
            artifact = build_artifact_null(transition, values, job["pretransition_degrees"], approved["null"])
            artifact.update(config_hash=config_hash, alignment_manifest_sha256=stage["alignment_manifest_sha256"],
                            pair_lineage=[{"endpoint_snapshot": sid, "source_seed": a, "target_seed": b,
                                           "alignment_sha256": descriptors[sid, a, b][1],
                                           "anchor_plan_hash": descriptors[sid, a, b][0]["anchor_plan_hash"],
                                           "source_checkpoint_sha256": descriptors[sid, a, b][0]["source_checkpoint_sha256"],
                                           "target_checkpoint_sha256": descriptors[sid, a, b][0]["target_checkpoint_sha256"]}
                                          for sid, a, b in map(tuple, job["endpoint_pairs"])])
            artifacts.append(artifact)
            observations.append(rows)
        if encode(artifacts[0]) != encode(artifacts[1]) or encode(observations[0]) != encode(observations[1]):
            raise ValueError("Null observations/LTO repeat bytes differ")
        folder = out / "transitions" / transition.replace("->", "__")
        folder.mkdir(parents=True, exist_ok=True)
        paths = [folder / f"null_repeat_{repeat}.json" for repeat in (1, 2)]
        for path, artifact in zip(paths, artifacts):
            write_json(path, artifact)
        artifact = artifacts[0]
        digest = sha(paths[0].read_bytes())
        for row in observations[0]:
            row.update(pretransition_degree=job["pretransition_degrees"][row["entity_id"]],
                       bucket_id=artifact["entity_to_bucket"][row["entity_id"]])
        all_observations.extend(observations[0])
        all_lto.extend({"transition_id": transition, **stats, "null_artifact_sha256": digest}
                       for stats in artifact["lto_statistics"].values())
        available = sum(s["available"] for s in artifact["lto_statistics"].values())
        results.append({"transition_id": transition, "entities": len(job["entities"]),
                        "observations": len(observations[0]), "lto_available": available,
                        "lto_unavailable": len(job["entities"]) - available, "merge_events": len(artifact["bucket_merge_log"]),
                        "path": paths[0].relative_to(out).as_posix(), "null_artifact_sha256": digest, "exact_replay": True})
        prev, nxt = job["endpoints"]
        manifest = {"experiment_id": f"{out.name}_{transition}", "protocol_version": "v1-draft",
                    "stage": "empirical_null", "mode": stage["mode"], "scientific_certification": False, "git": git, "seed": None,
                    "inputs": {"data_hash": sha(encode(hashes)),
                               "snapshot_hash": sha(encode([datasets[prev].snapshot_hash, datasets[nxt].snapshot_hash])),
                               "query_hash": None, "entity_map_hash": sha(encode([datasets[prev].compute_mapping_hash(), datasets[nxt].compute_mapping_hash()])),
                               "relation_map_hash": sha(encode([datasets[prev].get_relation_mapping(), datasets[nxt].get_relation_mapping()])),
                               "config_hash": config_hash, "hashes": hashes, "code_hashes": code_hashes,
                               "alignment_manifest_hash": stage["alignment_manifest_sha256"], "pair_lineage": artifact["pair_lineage"]},
                    "environment": environment, "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                    "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in paths}},
                    "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_null.py"}}
        validate_manifest(manifest)
        write_json(folder / "experiment_manifest.json", manifest)
        print(f"{transition}: {len(observations[0])} noise observations; {available}/{len(job['entities'])} LTO available", flush=True)
    for name, rows, schema in (("noise_observations.parquet", all_observations, OBSERVATION_SCHEMA),
                                ("lto_statistics.parquet", all_lto, LTO_SCHEMA)):
        payload = parquet_bytes(rows, schema)
        if payload != parquet_bytes(rows, schema):
            raise ValueError("Parquet serialization repeats differ")
        with (out / name).open("xb") as handle:
            handle.write(payload)
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input changed during null stage: {relative}")
    for relative, digest in code_hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Code changed during null stage: {relative}")
    unavailable = sum(r["lto_unavailable"] for r in results)
    summary = {"status": "NULL_DEV_CHECKS_PASS" if unavailable == 0 else "NULL_PARTIALLY_UNAVAILABLE",
               "scientific_certification": False, "transitions": 9, "entities": len(all_lto), "observations": len(all_observations),
               "lto_available": len(all_lto) - unavailable, "lto_unavailable": unavailable,
               "byte_identical_null_replays": 9, "deterministic_parquet_files": 2,
               "input_unchanged": True, "elapsed_seconds": time.perf_counter() - started, "results": results,
               "next_stage": "longitudinal_drift", "auto_execute_next_stage": False}
    write_json(out / "summary.json", summary)
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "stage": "empirical_null", "mode": stage["mode"],
                "scientific_certification": False, "git": git, "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)),
                           "snapshot_hash": sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()})), "query_hash": None,
                           "entity_map_hash": sha(encode({sid: ds.compute_mapping_hash() for sid, ds in datasets.items()})),
                           "relation_map_hash": sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()})),
                           "config_hash": config_hash, "hashes": hashes, "code_hashes": code_hashes,
                           "alignment_manifest_hash": stage["alignment_manifest_sha256"]},
                "environment": environment, "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/run_m2_null.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), **{k: v for k, v in summary.items() if k != "results"}}, indent=2))
    return out


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
