"""Execute Stage Null v2 across all 9 adjacent snapshot transitions with locked D-DIAG thresholds and Affine cosine."""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from kge.checkpoint import KGECheckpoint  # noqa: E402
from drift.measurement_v2 import build_null_stage_v2, content_hash  # noqa: E402
from scripts.verify_m2_measurement_v2 import verify_stage_v2  # noqa: E402
from scripts.inspect_m2_inputs import inspect_package, sha, write_json  # noqa: E402

PACKAGE_DIR = ROOT / "data/evolving_kg_downstream_v3_1"
BACKBONE_DIR = ROOT / "outputs/m2_backbone/20261014T034042Z_65c464ba"
ALIGNMENT_DIR = ROOT / "outputs/m2_alignment/20261014T040001Z_96d9ccbc"
OUT_BASE = ROOT / "outputs/m2_null_v2"

# Locked thresholds and estimand approved by user
LOCKED_SETTINGS: dict[str, Any] = {
    "cosine_estimand": "affine",
    "norm_floor": 1e-12,
    "denominator_floor": 1e-12,
    "rank_relative_tolerance": 1e-6,
    "minimum_rank_fraction": 0.90,
    "maximum_normalized_orthogonality_error": 1e-6,
    "maximum_relative_holdout_residual": 1.50,
    "maximum_relative_fit_holdout_gap": 0.65,
    "gap_statistic": "absolute_holdout_minus_fit",
    "minimum_reference_entities": 50,
    "mad_threshold": 1e-12,
    "epsilon": 1e-4,
}

PARQUET_LTO_SCHEMA = pa.schema([
    pa.field("reference_schema_version", pa.string(), False),
    pa.field("transition_id", pa.string(), False),
    pa.field("entity_id", pa.string(), False),
    pa.field("bucket_id", pa.string(), False),
    pa.field("reference_entity_ids", pa.list_(pa.field("item", pa.string(), False)), False),
    pa.field("removed_target_raw_observation_count", pa.int64(), False),
    pa.field("raw_noise_observation_count", pa.int64(), False),
    pa.field("reference_entity_count", pa.int64(), False),
    pa.field("reference_sample_count", pa.int64(), False),
    pa.field("minimum_reference_entities", pa.int64(), False),
    pa.field("mad_threshold", pa.float64(), False),
    pa.field("median", pa.float64()),
    pa.field("mad", pa.float64()),
    pa.field("robust_scale", pa.float64()),
    pa.field("available", pa.bool_(), False),
    pa.field("unavailable_reason", pa.string(), False),
    pa.field("null_artifact_sha256", pa.string(), False),
], metadata={b"artifact_schema": b"entity_null_reference_v2"})


def assign_degree_buckets(
    entities: list[str],
    degrees: dict[str, int],
    min_count: int = 51,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Assign entities to degree buckets with adjacent merging if count < min_count."""
    # Initial bins: [0, 3), [3, 6), [6, inf)
    groups = [
        {"name": "deg_0_2", "entities": [e for e in entities if degrees[e] < 3]},
        {"name": "deg_3_5", "entities": [e for e in entities if 3 <= degrees[e] < 6]},
        {"name": "deg_6_inf", "entities": [e for e in entities if degrees[e] >= 6]},
    ]
    # Remove empty initial groups
    groups = [g for g in groups if len(g["entities"]) > 0]

    merge_log = []
    # Merge loop: while any group has count < min_count and len(groups) > 1
    while len(groups) > 1:
        sparse_idx = next((i for i, g in enumerate(groups) if 0 < len(g["entities"]) < min_count), None)
        if sparse_idx is None:
            break
        neighbors = [i for i in (sparse_idx - 1, sparse_idx + 1) if 0 <= i < len(groups)]
        # Pick largest neighbor or adjacent
        partner_idx = min(neighbors, key=lambda i: (-len(groups[i]["entities"]), i))
        first, second = sorted((sparse_idx, partner_idx))
        merged_name = f"{groups[first]['name']}+{groups[second]['name']}"
        merged_entities = groups[first]["entities"] + groups[second]["entities"]
        merge_log.append({
            "action": "merge_adjacent_buckets",
            "first": groups[first]["name"],
            "first_count": len(groups[first]["entities"]),
            "second": groups[second]["name"],
            "second_count": len(groups[second]["entities"]),
            "merged": merged_name,
            "merged_count": len(merged_entities),
            "reason": "INSUFFICIENT_ENTITIES_FOR_LTO",
        })
        groups[first:second + 1] = [{"name": merged_name, "entities": merged_entities}]

    bucket_map = {e: g["name"] for g in groups for e in g["entities"]}
    return bucket_map, merge_log


def run_null_stage_all() -> Path:
    start_time = time.perf_counter()
    now = datetime.now(timezone.utc)
    token = now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    out_dir = OUT_BASE / token
    out_dir.mkdir(parents=True, exist_ok=False)

    print(f"[INFO] Initializing Stage Null v2 run in: {out_dir}")

    # 1. Load canonical datasets
    print("[INFO] Inspecting package and loading canonical snapshots...")
    datasets, _ = inspect_package(PACKAGE_DIR)

    # 2. Load backbone checkpoints
    print(f"[INFO] Loading 30 checkpoints from {BACKBONE_DIR}...")
    checkpoints: dict[tuple[str, int], tuple[KGECheckpoint, str]] = {}
    snapshots = [f"T{i:02d}" for i in range(1, 11)]
    seeds = [13, 37, 101]

    for sid in snapshots:
        for seed in seeds:
            ckpt_path = BACKBONE_DIR / f"checkpoints/{sid}/seed_{seed}_repeat_1.json"
            sidecar_path = ckpt_path.with_name(ckpt_path.name + ".sha256")
            physical_sha = sidecar_path.read_text(encoding="utf-8").split()[0]
            cp = KGECheckpoint.load(ckpt_path)
            checkpoints[sid, seed] = (cp, physical_sha)

    # 3. Load anchor plans
    print(f"[INFO] Loading anchor plans from {ALIGNMENT_DIR}...")
    with (ALIGNMENT_DIR / "anchor_plans.json").open("r", encoding="utf-8") as f:
        anchor_plans = json.load(f)

    # 4. Iterate over all 9 transitions
    transitions = [f"T{i:02d}->T{i+1:02d}" for i in range(1, 10)]
    transition_summaries = []
    all_parquet_rows = []

    print(f"\n[INFO] Running Stage Null v2 across {len(transitions)} transitions...")
    for trans in transitions:
        prev, nxt = trans.split("->")
        persistent = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        degrees = {e: datasets[prev].entity_metadata[e].degree for e in persistent}
        plan = anchor_plans[trans]

        # Filter checkpoints for this transition
        t_checkpoints = {
            (sid, seed): checkpoints[sid, seed]
            for sid in (prev, nxt)
            for seed in seeds
        }

        # Load the 6 same-snapshot alignments specifically for this transition
        t_alignments = {}
        for sid in (prev, nxt):
            for a, b in ((13, 37), (13, 101), (37, 101)):
                cid = f"{sid}_seed{a}__{sid}_seed{b}"
                align_path = ALIGNMENT_DIR / f"alignments/{trans.replace('->', '__')}/{cid}_repeat_1.json"
                record = json.loads(align_path.read_bytes())
                phys = sha(align_path.read_bytes())
                sem = content_hash(record)
                t_alignments[sid, sid, a, b] = (record, phys, sem)

        # Bucket assignments
        buckets, merge_log = assign_degree_buckets(persistent, degrees, min_count=51)

        print(f" -> Transition {trans}: {len(persistent)} persistent entities, {len(set(buckets.values()))} buckets")
        if merge_log:
            for ml in merge_log:
                print(f"    * Merged: {ml['first']} ({ml['first_count']}) + {ml['second']} ({ml['second_count']}) -> {ml['merged']} ({ml['merged_count']})")

        # Execute build_null_stage_v2
        stage_result = build_null_stage_v2(
            transition=trans,
            checkpoints=t_checkpoints,
            alignments=t_alignments,
            anchor_plan=plan,
            buckets=buckets,
            settings=LOCKED_SETTINGS,
        )

        # Verify independently with NumPy
        verify_stage_v2(
            artifact=stage_result,
            checkpoints=t_checkpoints,
            alignments=t_alignments,
            plan=plan,
            buckets=buckets,
            cfg=LOCKED_SETTINGS,
            null_stage=None,
        )

        # Write transition artifact
        t_dir = out_dir / "transitions" / trans.replace("->", "__")
        t_dir.mkdir(parents=True, exist_ok=True)
        t_path = t_dir / "null_stage_v2.json"
        write_json(t_path, stage_result)

        null_art = stage_result["null_artifact"]
        null_sha = sha(t_path.read_bytes())

        # Collect Parquet rows
        t_rows = []
        if null_art is not None:
            for entity, lto in null_art["lto_statistics"].items():
                p_row = {
                    "reference_schema_version": "entity_null_reference_v2",
                    "transition_id": trans,
                    "entity_id": entity,
                    "bucket_id": buckets[entity],
                    "reference_entity_ids": lto["reference_entity_ids"],
                    "removed_target_raw_observation_count": lto["removed_target_raw_observation_count"],
                    "raw_noise_observation_count": lto["raw_noise_observation_count"],
                    "reference_entity_count": lto["reference_entity_count"],
                    "reference_sample_count": lto["reference_sample_count"],
                    "minimum_reference_entities": LOCKED_SETTINGS["minimum_reference_entities"],
                    "mad_threshold": LOCKED_SETTINGS["mad_threshold"],
                    "median": lto["median"],
                    "mad": lto["mad"],
                    "robust_scale": lto["robust_scale"],
                    "available": lto["available"],
                    "unavailable_reason": lto["unavailable_reason"],
                    "null_artifact_sha256": null_sha,
                }
                t_rows.append(p_row)
                all_parquet_rows.append(p_row)

        available_count = sum(1 for r in stage_result["entity_results"] if r["available"])
        total_count = len(stage_result["entity_results"])

        medians = [r["median"] for r in t_rows if r["median"] is not None]
        mads = [r["mad"] for r in t_rows if r["mad"] is not None]

        summary_entry = {
            "transition_id": trans,
            "persistent_entities": total_count,
            "alignment_available": stage_result["alignment_available"],
            "null_available_entities": available_count,
            "null_unavailable_entities": total_count - available_count,
            "availability_rate": round(available_count / total_count, 4) if total_count else 0.0,
            "buckets": sorted(set(buckets.values())),
            "merge_events": len(merge_log),
            "median_noise_distribution": {
                "min": round(min(medians), 6) if medians else None,
                "median": round(statistics.median(medians), 6) if medians else None,
                "max": round(max(medians), 6) if medians else None,
            },
            "mad_distribution": {
                "min": round(min(mads), 6) if mads else None,
                "median": round(statistics.median(mads), 6) if mads else None,
                "max": round(max(mads), 6) if mads else None,
            },
            "artifact_path": t_path.relative_to(ROOT).as_posix(),
            "artifact_sha256": null_sha,
        }
        transition_summaries.append(summary_entry)
        print(f"    [PASS] Verified available={available_count}/{total_count} ({summary_entry['availability_rate']*100:.1f}%)")

    # 5. Write combined Parquet file
    table = pa.Table.from_pylist(all_parquet_rows, schema=PARQUET_LTO_SCHEMA)
    parquet_path = out_dir / "all_transitions_entity_null_v2.parquet"
    pq.write_table(table, parquet_path, compression="zstd")
    parquet_sha = sha(parquet_path.read_bytes())
    print(f"\n[INFO] Written {len(all_parquet_rows)} rows to Parquet: {parquet_path}")

    # 6. Write stage summary and manifest
    overall_summary = {
        "stage": "empirical_null_v2",
        "timestamp_utc": now.isoformat(),
        "elapsed_seconds": round(time.perf_counter() - start_time, 2),
        "settings": LOCKED_SETTINGS,
        "total_transitions": len(transitions),
        "total_entity_null_rows": len(all_parquet_rows),
        "total_available_entities": sum(s["null_available_entities"] for s in transition_summaries),
        "total_entities": sum(s["persistent_entities"] for s in transition_summaries),
        "parquet_path": parquet_path.relative_to(ROOT).as_posix(),
        "parquet_sha256": parquet_sha,
        "transitions": transition_summaries,
    }
    write_json(out_dir / "summary.json", overall_summary)

    manifest = {
        "experiment_id": token,
        "protocol_version": "v1-draft",
        "git": {"commit": "HEAD", "dirty": True},
        "seed": None,
        "scientific_certification": False,
        "stage": "empirical_null_v2",
        "inputs": {
            "backbone_dir": BACKBONE_DIR.relative_to(ROOT).as_posix(),
            "alignment_dir": ALIGNMENT_DIR.relative_to(ROOT).as_posix(),
            "settings": LOCKED_SETTINGS,
        },
        "environment": {
            "python": platform.python_version(),
            "os": platform.platform(),
            "pyarrow": pa.__version__,
        },
        "artifacts": {
            p.relative_to(out_dir).as_posix(): sha(p.read_bytes())
            for p in out_dir.rglob("*")
            if p.is_file()
        },
    }
    write_json(out_dir / "experiment_manifest.json", manifest)

    print(f"[SUCCESS] Stage Null v2 successfully completed in {overall_summary['elapsed_seconds']}s!")
    return out_dir


if __name__ == "__main__":
    run_null_stage_all()
