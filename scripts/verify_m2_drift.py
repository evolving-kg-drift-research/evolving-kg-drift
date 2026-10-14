"""Independent NumPy temporal displacement, calibration, population and handoff validation."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, safe_file, sha, validate_manifest, write_json,
)


def close(actual: Any, expected: Any, label: str) -> None:
    if expected is None:
        if actual is not None:
            raise ValueError(f"Fabricated unavailable drift: {label}")
    elif actual is None or not np.allclose(actual, expected, rtol=1e-10, atol=1e-12):
        raise ValueError(f"Independent drift arithmetic mismatch: {label}")


def verify_metric_row(row: dict[str, Any], temporal: list[float], reference: dict[str, Any],
                      epsilon: float, floor: float, minimum: int) -> None:
    if len(temporal) != 3 or not np.isfinite(temporal).all():
        raise ValueError("Missing independent temporal seeds")
    delta = float(np.median(temporal))
    center, mad = reference["median"], reference["mad"]
    excess = None if center is None else delta - center
    available = reference["available"]
    if available and (center is None or mad is None or mad < floor or reference["observation_count"] < minimum):
        raise ValueError("Invalid reference cannot support SED+")
    sed = max(0.0, excess) / (1.4826 * mad + epsilon) if available else None
    for key, value in (("delta_time", delta), ("signed_excess", excess), ("SED_plus", sed)):
        close(row[key], value, key)
    if row["available"] != available or row["unavailable_reason"] != reference["unavailable_reason"]:
        raise ValueError("Drift availability/reason mismatch")


def verify(run: Path) -> dict[str, Any]:
    run = run.resolve()
    manifest_path = safe_file(run, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    for base, catalog in ((ROOT, manifest["inputs"]["hashes"]), (run, manifest["artifacts"]["hashes"])):
        for relative, digest in catalog.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Drift input/artifact hash mismatch: {relative}")
    for relative, digest in manifest["inputs"]["code_hashes"].items():
        if sha(safe_file(run, Path("code") / relative).read_bytes()) != digest:
            raise ValueError("Drift source archive hash mismatch")
    resolved = json.loads(safe_file(run, "resolved_config.json").read_bytes())
    stage, approved = resolved["stage"], resolved["approved"]
    if (stage != yaml.safe_load(safe_file(ROOT, "configs/m2_drift_v1.yaml").read_bytes())
            or approved != yaml.safe_load(safe_file(ROOT, stage["approved_config_path"]).read_bytes())
            or sha(safe_file(ROOT, stage["approved_config_path"]).read_bytes()) != stage["approved_config_sha256"]
            or stage["stage"] != "longitudinal_drift" or stage["component_version"] != "saved_alignment_longitudinal_drift_v1"
            or stage["scientific_certification"] is not False or stage["auto_execute_next_stage"] is not False
            or stage["repetitions"] != 2 or stage["centered_norm_floor"] != 1e-12
            or manifest["scientific_certification"] is not False or manifest["stage"] != "longitudinal_drift"
            or manifest["access"]["state"] != "dev" or manifest["mode"] != stage["mode"]
            or manifest["inputs"]["config_hash"] != sha(encode(resolved))
            or manifest["inputs"]["data_hash"] != sha(encode(manifest["inputs"]["hashes"]))
            or manifest["inputs"]["query_hash"] is not None or manifest["seed"] is not None):
        raise ValueError("Drift stage identity/config/Dev contract mismatch")
    null_run = ROOT / stage["null_run"]
    parent = json.loads(safe_file(null_run, "experiment_manifest.json").read_bytes())
    receipt = json.loads(safe_file(ROOT, stage["null_verification_path"]).read_bytes())
    if (sha(safe_file(null_run, "experiment_manifest.json").read_bytes()) != stage["null_manifest_sha256"]
            or sha(safe_file(ROOT, stage["null_verification_path"]).read_bytes()) != stage["null_verification_sha256"]
            or receipt["status"] != "NULL_ARTIFACT_VERIFICATION_PASS" or receipt["manifest_sha256"] != stage["null_manifest_sha256"]
            or receipt != json.loads(safe_file(run, "null_verification.json").read_bytes())
            or sha(safe_file(null_run, "code/scripts/verify_m2_null.py").read_bytes()) != receipt["verifier_sha256"]):
        raise ValueError("Null verification lineage mismatch")
    expected_inputs = dict(parent["inputs"]["hashes"])
    expected_inputs.update({(null_run.relative_to(ROOT) / p).as_posix(): h for p, h in parent["artifacts"]["hashes"].items()})
    for path in (ROOT / "configs/m2_drift_v1.yaml", null_run / "experiment_manifest.json", ROOT / stage["null_verification_path"]):
        expected_inputs[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    if expected_inputs != manifest["inputs"]["hashes"] or expected_inputs != json.loads(safe_file(run, "input_hashes.json").read_bytes()):
        raise ValueError("Incomplete upstream drift input lineage")
    null_resolved = json.loads(safe_file(null_run, "resolved_config.json").read_bytes())
    alignment = ROOT / null_resolved["stage"]["alignment_run"]
    align_cfg = json.loads(safe_file(alignment, "resolved_config.json").read_bytes())
    backbone = ROOT / align_cfg["stage"]["backbone_run"]
    checkpoints = {(r["snapshot_id"], r["seed"]): json.loads(safe_file(backbone, r["path"]).read_bytes())
                   for r in json.loads(safe_file(backbone, "summary.json").read_bytes())["results"]}
    records = {}
    for row in json.loads(safe_file(alignment, "summary.json").read_bytes())["results"]:
        if row["alignment_type"] == "cross_time":
            key = row["transition_id"], row["source_seed"]
            if key in records:
                raise ValueError("Duplicate parallel temporal alignment")
            path = safe_file(alignment, row["path"])
            records[key] = json.loads(path.read_bytes()), sha(path.read_bytes())
    null_results = {r["transition_id"]: r for r in json.loads(safe_file(null_run, "summary.json").read_bytes())["results"]}
    datasets, _ = inspect_package(ROOT / PACKAGE)
    for key, expected in (("snapshot_hash", {sid: ds.snapshot_hash for sid, ds in datasets.items()}),
                          ("entity_map_hash", {sid: ds.compute_mapping_hash() for sid, ds in datasets.items()}),
                          ("relation_map_hash", {sid: ds.get_relation_mapping() for sid, ds in datasets.items()})):
        if manifest["inputs"][key] != sha(encode(expected)):
            raise ValueError("Drift mapping/snapshot population hash mismatch")
    temporal_table = pq.read_table(safe_file(run, "temporal_displacements.parquet"))
    drift_table = pq.read_table(safe_file(run, "entity_drift.parquet"))
    for table, label in ((temporal_table, b"saved_temporal_displacements_v1"), (drift_table, b"saved_entity_drift_v1")):
        if (table.schema.metadata.get(b"artifact_schema") != label
                or any(not table.schema.field(i).nullable and table.column(i).null_count for i in range(table.num_columns))):
            raise ValueError("Drift Parquet metadata/null contract mismatch")
        string_fields = ({"transition_id", "entity_id", "source_snapshot", "target_snapshot", "alignment_sha256",
                          "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256"}
                         if table is temporal_table else {"transition_id", "entity_id", "bucket_id", "unavailable_reason", "null_artifact_sha256"})
        floats = ({"temporal_displacement"} if table is temporal_table else
                  {"delta_time", "signed_excess", "SED_plus", "null_median", "null_mad", "null_robust_scale"})
        integers = {"seed": pa.int32()} if table is temporal_table else {
            "pretransition_degree": pa.int64(), "removed_target_observations": pa.int32(),
            "reference_entity_count": pa.int64(), "observation_count": pa.int64()}
        nullable = set() if table is temporal_table else floats - {"delta_time"}
        types = {**{k: pa.string() for k in string_fields}, **{k: pa.float64() for k in floats}, **integers}
        if table is drift_table:
            types["available"] = pa.bool_()
        if (set(table.schema.names) != set(types) or any(f.type != types[f.name] or f.nullable != (f.name in nullable) for f in table.schema)):
            raise ValueError("Drift Parquet field/type/nullability mismatch")
        buffer = pa.BufferOutputStream()
        pq.write_table(table, buffer, compression="zstd", version="2.6")
        name = "temporal_displacements.parquet" if table is temporal_table else "entity_drift.parquet"
        if buffer.getvalue().to_pybytes() != safe_file(run, name).read_bytes():
            raise ValueError("Drift Parquet exact serialization replay mismatch")
    temporal_rows, drift_rows = temporal_table.to_pylist(), drift_table.to_pylist()
    ti = {(r["transition_id"], r["entity_id"], r["seed"]): r for r in temporal_rows}
    di = {(r["transition_id"], r["entity_id"]): r for r in drift_rows}
    if len(ti) != len(temporal_rows) or len(di) != len(drift_rows):
        raise ValueError("Duplicate drift entity/transition/seed")
    jobs = json.loads(safe_file(run, "registered_jobs.json").read_bytes())
    summary = json.loads(safe_file(run, "summary.json").read_bytes())
    transitions = [f"{a}->{b}" for a, b in zip(approved["snapshots"], approved["snapshots"][1:])]
    if ([j["transition_id"] for j in jobs] != transitions or [r["transition_id"] for r in summary["results"]] != transitions
            or set(records) != {(t, seed) for t in transitions for seed in (13, 37, 101)}):
        raise ValueError("Drift transition/seed universe mismatch")
    entity_count, available, positive = 0, 0, 0
    for job, result in zip(jobs, summary["results"]):
        transition, (prev, nxt) = job["transition_id"], job["endpoints"]
        entities = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        if transition != f"{prev}->{nxt}" or job["entities"] != entities or job["seeds"] != [13, 37, 101]:
            raise ValueError("Drift persistent universe mismatch")
        values: dict[str, list[float]] = {e: [] for e in entities}
        for seed in (13, 37, 101):
            record, digest = records[transition, seed]
            source, target = checkpoints[prev, seed], checkpoints[nxt, seed]
            if (record["available"] is not True or record["unavailable_reason"] or record["alignment_type"] != "cross_time"
                    or record["source_snapshot"] != prev or record["target_snapshot"] != nxt
                    or record["source_seed"] != seed or record["target_seed"] != seed
                    or record["source_checkpoint_semantic_hash"] != source["artifact_hash"]
                    or record["target_checkpoint_semantic_hash"] != target["artifact_hash"]):
                raise ValueError("Temporal saved alignment identity mismatch")
            x = np.asarray([source["entity_embeddings"][e] for e in entities]) - record["source_mean"]
            y = np.asarray([target["entity_embeddings"][e] for e in entities]) - record["target_mean"]
            rotated = x @ np.asarray(record["Q"])
            nx, ny = np.linalg.norm(rotated, axis=1), np.linalg.norm(y, axis=1)
            if np.any(nx < stage["centered_norm_floor"]) or np.any(ny < stage["centered_norm_floor"]):
                raise ValueError("Undefined independent centered temporal cosine")
            displacements = 1 - np.clip(np.einsum("ij,ij->i", rotated, y) / (nx * ny), -1, 1)
            for entity, value in zip(entities, displacements):
                row = ti[transition, entity, seed]
                close(row["temporal_displacement"], float(value), "centered temporal displacement")
                if (row["source_snapshot"] != prev or row["target_snapshot"] != nxt
                        or any(row[k] != (digest if k == "alignment_sha256" else record[k]) for k in
                               ("alignment_sha256", "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256"))):
                    raise ValueError("Temporal row alignment/checkpoint lineage mismatch")
                values[entity].append(float(value))
        null_path = safe_file(null_run, null_results[transition]["path"])
        null = json.loads(null_path.read_bytes())
        drift = []
        for entity in entities:
            row, reference = di[transition, entity], null["lto_statistics"][entity]
            verify_metric_row(row, values[entity], reference, approved["null"]["mad_epsilon"],
                              approved["null"]["degeneracy_mad_threshold"], approved["null"]["min_reference_observations"])
            if (row["pretransition_degree"] != datasets[prev].entity_metadata[entity].degree
                    or row["null_artifact_sha256"] != sha(null_path.read_bytes())
                    or any(row[k] != reference[k] for k in ("bucket_id", "removed_target_observations", "reference_entity_count", "observation_count"))
                    or any(row[outkey] != reference[inkey] for outkey, inkey in
                           (("null_median", "median"), ("null_mad", "mad"), ("null_robust_scale", "robust_scale")))):
                raise ValueError("Drift row LTO support/conditioning/hash mismatch")
            drift.append(row)
        path = safe_file(run, result["path"])
        second = path.with_name("drift_repeat_2.json")
        artifact = json.loads(path.read_bytes())
        if (path.read_bytes() != second.read_bytes() or result["sha256"] != sha(path.read_bytes()) or result["exact_replay"] is not True
                or artifact["component_version"] != "saved_alignment_longitudinal_drift_v1" or artifact["transition_id"] != transition
                or artifact["config_hash"] != manifest["inputs"]["config_hash"] or artifact["null_manifest_sha256"] != stage["null_manifest_sha256"]
                or artifact["entity_drift"] != drift
                or artifact["temporal_observations"] != [ti[transition, e, seed] for seed in (13, 37, 101) for e in entities]):
            raise ValueError("Drift replay/JSON/Parquet/lineage mismatch")
        nested = json.loads(path.with_name("experiment_manifest.json").read_bytes())
        validate_manifest(nested)
        if (nested["git"] != manifest["git"] or nested["scientific_certification"] is not False or nested["seed"] is not None
                or any(nested["inputs"][k] != manifest["inputs"][k] for k in ("config_hash", "hashes", "code_hashes", "data_hash", "null_manifest_hash"))
                or nested["inputs"]["snapshot_hash"] != sha(encode([datasets[prev].snapshot_hash, datasets[nxt].snapshot_hash]))
                or nested["inputs"]["entity_map_hash"] != sha(encode([datasets[prev].compute_mapping_hash(), datasets[nxt].compute_mapping_hash()]))
                or nested["inputs"]["relation_map_hash"] != sha(encode([datasets[prev].get_relation_mapping(), datasets[nxt].get_relation_mapping()]))
                or nested["artifacts"]["hashes"] != {p.relative_to(run).as_posix(): sha(p.read_bytes()) for p in (path, second)}):
            raise ValueError("Nested drift manifest mismatch")
        count = sum(r["available"] for r in drift)
        pos = sum(r["signed_excess"] is not None and r["signed_excess"] > 0 for r in drift)
        if result["entities"] != len(entities) or result["available"] != count or result["positive_excess"] != pos:
            raise ValueError("Drift transition counts mismatch")
        for key, col in (("delta_time_median", "delta_time"), ("signed_excess_median", "signed_excess"), ("SED_plus_median", "SED_plus")):
            observed = [r[col] for r in drift if r[col] is not None]
            close(result[key], float(np.median(observed)) if observed else None, key)
        entity_count += len(entities)
        available += count
        positive += pos
    if (len(di) != entity_count or len(ti) != 3 * entity_count or summary["entities"] != entity_count
            or summary["temporal_observations"] != 3 * entity_count or summary["available"] != available
            or summary["unavailable"] != entity_count - available or summary["positive_excess"] != positive
            or summary["transitions"] != 9 or summary["byte_identical_drift_replays"] != 9
            or summary["deterministic_parquet_files"] != 2 or summary["scientific_certification"] is not False
            or summary["auto_execute_next_stage"] is not False or summary["next_stage"] != "M4_readiness"
            or summary["status"] != ("DRIFT_DEV_CHECKS_PASS" if available == entity_count else "DRIFT_PARTIALLY_UNAVAILABLE")):
        raise ValueError("Drift aggregate counts/availability mismatch")
    handoff = json.loads(safe_file(run, "handoff_manifest.json").read_bytes())
    expected_tables = {name: {"sha256": sha(safe_file(run, name).read_bytes()), "rows": table.num_rows,
                             "schema": table.schema.metadata[b"artifact_schema"].decode()}
                       for name, table in (("temporal_displacements.parquet", temporal_table), ("entity_drift.parquet", drift_table))}
    if (handoff["version"] != "m2_to_m4_dev_handoff_v1" or handoff["experiment_id"] != manifest["experiment_id"]
            or handoff["tables"] != expected_tables or handoff["config_hash"] != manifest["inputs"]["config_hash"]
            or handoff["null_manifest_sha256"] != stage["null_manifest_sha256"]
            or handoff["alignment_manifest_sha256"] != null_resolved["stage"]["alignment_manifest_sha256"]
            or handoff["approved_config_sha256"] != stage["approved_config_sha256"]
            or handoff["scientific_certification"] is not False or handoff["access_state"] != "dev"
            or handoff["population"] != "persistent_entities_each_adjacent_transition" or handoff["seeds"] != [13, 37, 101]
            or handoff["M4_executed"] is not False or handoff["query_hash"] is not None):
        raise ValueError("M2 to M4 handoff contract mismatch")
    return {"status": "DRIFT_ARTIFACT_VERIFICATION_PASS", "scientific_certification": False,
            "manifest_sha256": sha(manifest_path.read_bytes()), "temporal_observations_recomputed": 3 * entity_count,
            "entity_drift_recomputed": entity_count, "available": available, "unavailable": entity_count - available,
            "positive_excess": positive, "transition_manifests_checked": 9, "exact_drift_replays": 9, "handoff_verified": True,
            "input_hashes_checked": len(expected_inputs), "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "verified_at_real": datetime.now(timezone.utc).isoformat(), "verifier_sha256": sha(Path(__file__).read_bytes()),
            "scope": "NumPy saved temporal displacement/calibration/population/lineage Dev M2; no M1/G3 certification or M4 execution"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    output = args.run / ("independent_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                         + "_" + uuid4().hex[:8] + ".json")
    write_json(output, result)
    print(json.dumps({"output": str(output), **result}, indent=2))
