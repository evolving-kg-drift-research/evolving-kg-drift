"""Independent NumPy noise, bucket/LTO arithmetic and lineage verification."""
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

PAIRS = ((13, 37), (13, 101), (37, 101))


def close(actual: Any, expected: Any, label: str) -> None:
    if expected is None:
        if actual is not None:
            raise ValueError(f"Unavailable statistic fabricated: {label}")
    elif actual is None or not np.allclose(actual, expected, rtol=1e-10, atol=1e-12):
        raise ValueError(f"Independent null arithmetic mismatch: {label}")


def independent_buckets(degrees: dict[str, int], cfg: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
    edges = cfg["degree_bin_edges"]
    labels = ["low", "medium", "high"]
    intervals = []
    for index, label in enumerate(labels):
        population = [e for e, degree in sorted(degrees.items())
                      if (0 if degree < edges[0] else 1 if degree < edges[1] else 2) == index]
        intervals.append({"name": label, "entities": population})
    log = []
    while True:
        sparse = next((i for i, g in enumerate(intervals)
                       if 0 < 6 * len(g["entities"]) < cfg["min_reference_observations"]), None)
        if sparse is None or len(intervals) == 1:
            break
        if sparse == 0:
            neighbor = 1
        elif sparse == len(intervals) - 1:
            neighbor = sparse - 1
        else:
            neighbor = sparse + 1 if len(intervals[sparse + 1]["entities"]) > len(intervals[sparse - 1]["entities"]) else sparse - 1
        first, second = sorted((sparse, neighbor))
        current, partner = intervals[sparse], intervals[neighbor]
        name = intervals[first]["name"] + "+" + intervals[second]["name"]
        entities = sorted(intervals[first]["entities"] + intervals[second]["entities"])
        log.append({"sparse_bucket": current["name"], "sparse_observations": 6 * len(current["entities"]),
                    "partner_bucket": partner["name"], "partner_observations": 6 * len(partner["entities"]),
                    "merged_bucket": name, "merged_observations": 6 * len(entities), "reason": "INSUFFICIENT_POOLED_SAMPLES"})
        intervals = intervals[:first] + [{"name": name, "entities": entities}] + intervals[second + 1:]
    return ({e: g["name"] for g in intervals for e in g["entities"]}, log, [g["name"] for g in intervals])


def independent_stats(values: list[float], entities: int, cfg: dict[str, Any], empty: str, insufficient: str) -> dict[str, Any]:
    if not values:
        return {"reference_entity_count": entities, "observation_count": 0, "median": None, "mad": None,
                "robust_scale": None, "available": False, "unavailable_reason": empty}
    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    reason = (insufficient if len(values) < cfg["min_reference_observations"] else
              "ZERO_MAD" if mad < cfg["degeneracy_mad_threshold"] else "")
    return {"reference_entity_count": entities, "observation_count": len(values), "median": median,
            "mad": mad, "robust_scale": 1.4826 * mad, "available": not reason, "unavailable_reason": reason}


def verify_stats(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, value in expected.items():
        if key in ("median", "mad", "robust_scale"):
            close(actual[key], value, key)
        elif actual[key] != value:
            raise ValueError(f"Null reference support/availability mismatch: {key}")


def verify_null_artifact(artifact: dict[str, Any], values: dict[str, list[float]], degrees: dict[str, int], cfg: dict[str, Any]) -> None:
    assignments, log, bucket_ids = independent_buckets(degrees, cfg)
    if (artifact["component_version"] != "saved_alignment_empirical_null_v1"
            or artifact["pretransition_degrees"] != degrees or artifact["entity_to_bucket"] != assignments
            or artifact["bucket_merge_log"] != log or set(artifact["bucket_statistics"]) != set(bucket_ids)
            or set(artifact["entity_observations"]) != set(values) or set(artifact["lto_statistics"]) != set(values)
            or artifact["reference_bucket_merging_stage"] != "pooled_before_LTO"
            or artifact["no_target_specific_remerge"] is not True):
        raise ValueError("Null population/pretransition bucket allocation mismatch")
    for entity, observations in values.items():
        if len(observations) != 6:
            raise ValueError("Missing six-pair null observations")
        close(artifact["entity_observations"][entity], observations, "six-pair observations")
    for bucket in bucket_ids:
        population = sorted(e for e, b in assignments.items() if b == bucket)
        pooled = [v for e in population for v in values[e]]
        expected = independent_stats(pooled, len(population), cfg, "EMPTY_BUCKET", "INSUFFICIENT_SAMPLES")
        verify_stats(artifact["bucket_statistics"][bucket], {"bucket_id": bucket, **expected})
        for entity in population:
            reference_entities = [e for e in population if e != entity]
            reference = [v for e in reference_entities for v in values[e]]
            expected = independent_stats(reference, len(reference_entities), cfg, "LTO_EMPTY_BUCKET", "INSUFFICIENT_LTO_SAMPLES")
            verify_stats(artifact["lto_statistics"][entity], expected)
            row = artifact["lto_statistics"][entity]
            if (row["entity_id"] != entity or row["bucket_id"] != bucket or row["pretransition_degree"] != degrees[entity]
                    or row["removed_target_observations"] != 6):
                raise ValueError("LTO target exclusion identity/count mismatch")


def verify(run: Path) -> dict[str, Any]:
    run = run.resolve()
    if not run.is_relative_to((ROOT / "outputs/m2_null").resolve()):
        raise ValueError("Verifier requires a registered null output directory")
    manifest_path = safe_file(run, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    if manifest["stage"] != "empirical_null" or manifest["scientific_certification"] is not False or manifest["access"]["state"] != "dev":
        raise ValueError("Null stage verification scope mismatch")
    for base, catalog in ((run, manifest["artifacts"]["hashes"]), (ROOT, manifest["inputs"]["hashes"]),
                          (run / "code", manifest["inputs"]["code_hashes"])):
        for relative, digest in catalog.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Null input/artifact/code hash mismatch: {relative}")
    resolved = json.loads((run / "resolved_config.json").read_bytes())
    stage, approved = resolved["stage"], resolved["approved"]
    if (resolved["stage"] != yaml.safe_load(safe_file(ROOT, "configs/m2_null_v1.yaml").read_bytes())
            or approved != yaml.safe_load(safe_file(ROOT, stage["approved_config_path"]).read_bytes())
            or manifest["inputs"]["config_hash"] != sha(encode(resolved))
            or manifest["inputs"]["data_hash"] != sha(encode(manifest["inputs"]["hashes"]))
            or manifest["inputs"]["alignment_manifest_hash"] != stage["alignment_manifest_sha256"]):
        raise ValueError("Null resolved configuration/lineage mismatch")
    alignment = ROOT / stage["alignment_run"]
    if sha(safe_file(alignment, "experiment_manifest.json").read_bytes()) != stage["alignment_manifest_sha256"]:
        raise ValueError("Alignment manifest mismatch")
    proof = safe_file(ROOT, stage["alignment_verification_path"])
    if sha(proof.read_bytes()) != stage["alignment_verification_sha256"]:
        raise ValueError("Independent alignment receipt hash mismatch")
    alignment_config = json.loads((alignment / "resolved_config.json").read_bytes())
    backbone = ROOT / alignment_config["stage"]["backbone_run"]
    backbone_summary = json.loads(safe_file(backbone, "summary.json").read_bytes())
    checkpoints = {(r["snapshot_id"], r["seed"]): json.loads(safe_file(backbone, r["path"]).read_bytes())
                   for r in backbone_summary["results"]}
    alignment_summary = json.loads((alignment / "summary.json").read_bytes())
    saved_pairs = {}
    for row in alignment_summary["results"]:
        if row["alignment_type"] == "same_snapshot_cross_seed":
            path = safe_file(alignment, row["path"])
            saved_pairs.setdefault(row["transition_id"], {})[row["source_snapshot"], row["source_seed"], row["target_seed"]] = (
                json.loads(path.read_bytes()), sha(path.read_bytes()))
    datasets, _ = inspect_package(ROOT / PACKAGE)
    if (manifest["inputs"]["snapshot_hash"] != sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()}))
            or manifest["inputs"]["entity_map_hash"] != sha(encode({sid: ds.compute_mapping_hash() for sid, ds in datasets.items()}))
            or manifest["inputs"]["relation_map_hash"] != sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}))
            or manifest["inputs"]["query_hash"] is not None):
        raise ValueError("Aggregate null snapshot/mapping lineage mismatch")
    observations_table = pq.read_table(run / "noise_observations.parquet")
    lto_table = pq.read_table(run / "lto_statistics.parquet")
    expected_observation_columns = ["transition_id", "entity_id", "endpoint_snapshot", "source_seed", "target_seed", "noise_displacement",
                                    "alignment_sha256", "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256",
                                    "pretransition_degree", "bucket_id"]
    expected_lto_columns = ["transition_id", "entity_id", "pretransition_degree", "bucket_id", "removed_target_observations", "reference_entity_count",
                           "observation_count", "median", "mad", "robust_scale", "available", "unavailable_reason", "null_artifact_sha256"]
    if (observations_table.column_names != expected_observation_columns or lto_table.column_names != expected_lto_columns
            or observations_table.schema.metadata.get(b"artifact_schema") != b"saved_null_observations_v1"
            or lto_table.schema.metadata.get(b"artifact_schema") != b"saved_null_lto_v1"
            or observations_table.schema.field("noise_displacement").type != pa.float64()
            or any(observations_table.column(i).null_count for i in range(observations_table.num_columns))):
        raise ValueError("Analysis Parquet schema/null contract mismatch")
    observations = observations_table.to_pylist()
    lto_rows = lto_table.to_pylist()
    observation_index = {}
    for row in observations:
        key = row["transition_id"], row["entity_id"], row["endpoint_snapshot"], row["source_seed"], row["target_seed"]
        if key in observation_index:
            raise ValueError("Duplicate endpoint/entity noise observation")
        observation_index[key] = row
    lto_index = {(r["transition_id"], r["entity_id"]): r for r in lto_rows}
    if len(lto_index) != len(lto_rows):
        raise ValueError("Duplicate entity/transition LTO row")
    jobs = json.loads((run / "registered_jobs.json").read_bytes())
    summary = json.loads((run / "summary.json").read_bytes())
    expected_transitions = [f"{a}->{b}" for a, b in zip(approved["snapshots"], approved["snapshots"][1:])]
    if [j["transition_id"] for j in jobs] != expected_transitions or [r["transition_id"] for r in summary["results"]] != expected_transitions:
        raise ValueError("Null transition/job population mismatch")
    available = 0
    observation_count = 0
    entity_count = 0
    for job, result in zip(jobs, summary["results"]):
        transition = job["transition_id"]
        prev, nxt = job["endpoints"]
        entities = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        degrees = {e: datasets[prev].entity_metadata[e].degree for e in entities}
        expected_pairs = [(sid, a, b) for sid in (prev, nxt) for a, b in PAIRS]
        if (job["entities"] != entities or job["pretransition_degrees"] != degrees
                or job["endpoint_pairs"] != [list(p) for p in expected_pairs]
                or set(saved_pairs[transition]) != set(expected_pairs)):
            raise ValueError("Null persistent population or endpoint pair mismatch")
        values: dict[str, list[float]] = {e: [] for e in entities}
        pair_lineage = []
        for sid, a, b in expected_pairs:
            record, digest = saved_pairs[transition][sid, a, b]
            source, target = checkpoints[sid, a], checkpoints[sid, b]
            x = np.asarray([source["entity_embeddings"][e] for e in entities]) - np.asarray(record["source_mean"])
            y = np.asarray([target["entity_embeddings"][e] for e in entities]) - np.asarray(record["target_mean"])
            rotated = x @ np.asarray(record["Q"])
            nx, ny = np.linalg.norm(rotated, axis=1), np.linalg.norm(y, axis=1)
            if np.any(nx < stage["centered_norm_floor"]) or np.any(ny < stage["centered_norm_floor"]):
                raise ValueError("Undefined centered cosine in null input")
            displacements = 1 - np.clip(np.einsum("ij,ij->i", rotated, y) / (nx * ny), -1, 1)
            if not np.isfinite(displacements).all() or record["available"] is not True:
                raise ValueError("Unavailable/non-finite null observation input")
            pair_lineage.append({"endpoint_snapshot": sid, "source_seed": a, "target_seed": b,
                                 "alignment_sha256": digest, "anchor_plan_hash": record["anchor_plan_hash"],
                                 "source_checkpoint_sha256": record["source_checkpoint_sha256"],
                                 "target_checkpoint_sha256": record["target_checkpoint_sha256"]})
            for entity, value in zip(entities, displacements):
                row = observation_index[transition, entity, sid, a, b]
                close(row["noise_displacement"], float(value), "centered noise displacement")
                if (row["pretransition_degree"] != degrees[entity] or row["alignment_sha256"] != digest
                        or row["anchor_plan_hash"] != record["anchor_plan_hash"]
                        or row["source_checkpoint_sha256"] != record["source_checkpoint_sha256"]
                        or row["target_checkpoint_sha256"] != record["target_checkpoint_sha256"]):
                    raise ValueError("Noise row alignment/checkpoint/degree lineage mismatch")
                values[entity].append(float(value))
        path = safe_file(run, result["path"])
        second = safe_file(run, path.with_name("null_repeat_2.json").relative_to(run))
        if path.read_bytes() != second.read_bytes() or sha(path.read_bytes()) != result["null_artifact_sha256"] or result["exact_replay"] is not True:
            raise ValueError("Null repeat byte/hash mismatch")
        artifact = json.loads(path.read_bytes())
        if (artifact["transition_id"] != transition or artifact["config_hash"] != manifest["inputs"]["config_hash"]
                or artifact["alignment_manifest_sha256"] != stage["alignment_manifest_sha256"] or artifact["pair_lineage"] != pair_lineage):
            raise ValueError("Transition null artifact lineage mismatch")
        verify_null_artifact(artifact, values, degrees, approved["null"])
        transition_available = 0
        for entity in entities:
            for sid, a, b in expected_pairs:
                if observation_index[transition, entity, sid, a, b]["bucket_id"] != artifact["entity_to_bucket"][entity]:
                    raise ValueError("Noise row bucket assignment mismatch")
            row = lto_index[transition, entity]
            expected_row = {"transition_id": transition, **artifact["lto_statistics"][entity], "null_artifact_sha256": result["null_artifact_sha256"]}
            if row != expected_row:
                raise ValueError("LTO Parquet/JSON artifact mismatch")
            transition_available += row["available"]
        nested = json.loads(path.with_name("experiment_manifest.json").read_bytes())
        validate_manifest(nested)
        if (nested["git"] != manifest["git"] or nested["stage"] != "empirical_null" or nested["scientific_certification"] is not False
                or nested["inputs"]["hashes"] != manifest["inputs"]["hashes"]
                or nested["inputs"]["code_hashes"] != manifest["inputs"]["code_hashes"]
                or nested["inputs"]["config_hash"] != manifest["inputs"]["config_hash"]
                or nested["inputs"]["pair_lineage"] != pair_lineage
                or nested["inputs"]["alignment_manifest_hash"] != stage["alignment_manifest_sha256"]
                or nested["inputs"]["snapshot_hash"] != sha(encode([datasets[prev].snapshot_hash, datasets[nxt].snapshot_hash]))
                or nested["inputs"]["entity_map_hash"] != sha(encode([datasets[prev].compute_mapping_hash(), datasets[nxt].compute_mapping_hash()]))
                or nested["inputs"]["relation_map_hash"] != sha(encode([datasets[prev].get_relation_mapping(), datasets[nxt].get_relation_mapping()]))
                or nested["artifacts"]["hashes"] != {p.relative_to(run).as_posix(): sha(p.read_bytes()) for p in (path, second)}):
            raise ValueError("Transition null manifest mismatch")
        if (result["entities"] != len(entities) or result["observations"] != 6 * len(entities)
                or result["lto_available"] != transition_available
                or result["lto_unavailable"] != len(entities) - transition_available
                or result["merge_events"] != len(artifact["bucket_merge_log"])):
            raise ValueError("Null transition result counts mismatch")
        available += transition_available
        observation_count += 6 * len(entities)
        entity_count += len(entities)
    if (len(observations) != observation_count or len(lto_rows) != entity_count
            or summary["observations"] != observation_count or summary["entities"] != entity_count
            or summary["lto_available"] != available or summary["lto_unavailable"] != entity_count - available
            or summary["transitions"] != 9 or summary["byte_identical_null_replays"] != 9
            or summary["deterministic_parquet_files"] != 2 or summary["scientific_certification"] is not False
            or summary["auto_execute_next_stage"] is not False
            or summary["status"] != ("NULL_DEV_CHECKS_PASS" if available == entity_count else "NULL_PARTIALLY_UNAVAILABLE")):
        raise ValueError("Null stage counts/availability mismatch")
    return {"status": "NULL_ARTIFACT_VERIFICATION_PASS", "scientific_certification": False,
            "manifest_sha256": sha(manifest_path.read_bytes()), "noise_observations_recomputed": observation_count,
            "entity_LTO_statistics_recomputed": entity_count, "lto_available": available,
            "lto_unavailable": entity_count - available, "transition_manifests_checked": 9, "exact_null_replays": 9,
            "input_hashes_checked": len(manifest["inputs"]["hashes"]), "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "verified_at_real": datetime.now(timezone.utc).isoformat(), "verifier_sha256": sha(Path(__file__).read_bytes()),
            "scope": "Saved noise/LTO/bucket/Parquet/lineage Dev null stage; no temporal drift/SED+/G3 certification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    output = args.run / ("independent_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                         + "_" + uuid4().hex[:8] + ".json")
    write_json(output, result)
    print(json.dumps({"output": str(output), **result}, indent=2))
