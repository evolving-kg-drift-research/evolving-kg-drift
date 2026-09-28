"""Stage 4.16: Snapshot Boundaries Partitioning.

Determines 10 deterministic snapshot boundaries using the event-quantile rule
strictly blind to downstream drift outcomes. Materializes transition metadata
and boundaries manifest with cryptographic locking.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from kg_pipeline.contracts import CONTRACT_VERSION, make_row, validate_rows
from kg_pipeline.hashing import sha256_json, sha256_text, utc_now_iso
from kg_pipeline.run import get_run_dir
from kg_pipeline.storage import write_parquet_immutable

logger = logging.getLogger("snapshot_boundaries")


def run_snapshot_boundaries(
    repo_root: Path,
    run_id: str = "production_v2",
    n_snapshots: int = 10,
) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    tables_dir = run_dir / "tables"
    config_dir = run_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    kg_events_path = tables_dir / "kg_events.parquet"
    if not kg_events_path.is_file():
        raise FileNotFoundError(f"Missing {kg_events_path}")

    # Load canonical KG events
    events_table = pq.read_table(kg_events_path)
    events = events_table.to_pylist()

    # Deterministic canonical sort
    events.sort(key=lambda e: (e["effective_at"], e["event_id"]))
    n_events = len(events)
    if n_events == 0:
        raise ValueError("Cannot partition empty events table.")

    # 1. Deterministic Event-Quantile Partitioning
    # Event-quantile rule divides the ordered events into equal-sized buckets
    cuts = [int(round(i * n_events / n_snapshots)) for i in range(n_snapshots + 1)]

    boundaries = []
    transition_metadata_rows = []

    for i in range(n_snapshots):
        s_idx = cuts[i]
        e_idx = cuts[i + 1]
        slice_events = events[s_idx:e_idx]
        snap_id = f"T{i + 1:02d}"

        start_t = slice_events[0]["effective_at"]
        end_t = slice_events[-1]["effective_at"]

        dt_start = datetime.fromisoformat(start_t)
        dt_end = datetime.fromisoformat(end_t)
        duration_days = round((dt_end - dt_start).total_seconds() / 86400, 4)

        lfids = set(e["logical_fact_id"] for e in slice_events)
        n_ev = len(slice_events)

        transition_id = f"tr_{sha256_text(f'{snap_id}|{start_t}|{end_t}')[:16]}"
        trans_row = make_row(
            "transition_metadata",
            transition_id=transition_id,
            snapshot_id=snap_id,
            start_at=start_t,
            end_at=end_t,
            duration_days=duration_days,
            n_kg_events=n_ev,
            edge_additions=n_ev,
            edge_removals=0,
            changed_logical_facts=len(lfids),
        )
        transition_metadata_rows.append(trans_row)

        boundaries.append({
            "snapshot_id": snap_id,
            "cutoff": end_t,
            "interval_start": start_t,
            "interval_end": end_t,
            "event_count": n_ev,
            "duration_days": duration_days,
            "event_slice_indices": [s_idx, e_idx],
        })

    # Validate and write transition_metadata.parquet
    validate_rows("transition_metadata", transition_metadata_rows)
    trans_meta_path = tables_dir / "transition_metadata.parquet"
    write_parquet_immutable(trans_meta_path, "transition_metadata", transition_metadata_rows)

    # 2. Write deterministic snapshot_boundaries.yaml & compute boundary_hash
    boundary_payload = {
        "schema_version": CONTRACT_VERSION,
        "run_id": run_id,
        "partition_rule": "deterministic_event_quantile",
        "n_snapshots": n_snapshots,
        "total_kg_events": n_events,
        "boundaries": boundaries,
        "created_at_real": utc_now_iso(),
    }
    boundary_hash = sha256_json(boundary_payload)
    boundary_payload["boundary_hash"] = boundary_hash

    boundaries_yaml_path = config_dir / "snapshot_boundaries.yaml"
    with open(boundaries_yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(boundary_payload, f, sort_keys=False, allow_unicode=True)

    # Also save to root run_dir for top-level visibility
    root_boundaries_yaml = run_dir / "snapshot_boundaries.yaml"
    with open(root_boundaries_yaml, "w", encoding="utf-8") as f:
        yaml.safe_dump(boundary_payload, f, sort_keys=False, allow_unicode=True)

    summary = {
        "status": "PASS",
        "stage": "4.16_snapshot_boundaries",
        "run_id": run_id,
        "n_snapshots": n_snapshots,
        "boundary_hash": boundary_hash,
        "earliest_boundary": boundaries[0]["interval_start"],
        "latest_boundary": boundaries[-1]["interval_end"],
        "boundaries_yaml_path": str(boundaries_yaml_path),
        "transition_metadata_path": str(trans_meta_path),
        "boundaries": boundaries,
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Run Stage 4.16 Snapshot Boundaries Partitioning.")
    parser.add_argument("--run", default="production_v2", help="Run ID")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--n-snapshots", type=int, default=10, help="Number of snapshots")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    res = run_snapshot_boundaries(
        repo_root=repo_root,
        run_id=args.run,
        n_snapshots=args.n_snapshots,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
