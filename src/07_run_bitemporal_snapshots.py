"""Stage 4.17: Bitemporal Snapshots Builder and Hard Invariants Evaluator.

Builds 10 discrete bitemporal KG snapshots (valid_at=T, known_at=T) from
FactVersions according to snapshot_boundaries.yaml. Validates all hard scientific
invariants and generates cryptographic manifests for downstream TransE.
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
from kg_pipeline.hashing import sha256_file, sha256_json, utc_now_iso
from kg_pipeline.run import get_run_dir
from kg_pipeline.storage import write_json_immutable, write_parquet_immutable
from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot

logger = logging.getLogger("bitemporal_snapshots")


def run_bitemporal_snapshots(repo_root: Path, run_id: str = "production_v2") -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    tables_dir = run_dir / "tables"
    reports_dir = run_dir / "reports"
    snapshots_dir = run_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    boundaries_yaml_path = run_dir / "config" / "snapshot_boundaries.yaml"
    if not boundaries_yaml_path.is_file():
        boundaries_yaml_path = run_dir / "snapshot_boundaries.yaml"
    if not boundaries_yaml_path.is_file():
        raise FileNotFoundError(f"Missing snapshot_boundaries.yaml in {run_dir}")

    with open(boundaries_yaml_path, "r", encoding="utf-8") as f:
        boundaries_cfg = yaml.safe_load(f)

    boundaries = boundaries_cfg.get("boundaries", [])
    if not boundaries:
        raise ValueError("No boundaries defined in snapshot_boundaries.yaml")

    fact_versions_path = tables_dir / "fact_versions.parquet"
    if not fact_versions_path.is_file():
        raise FileNotFoundError(f"Missing {fact_versions_path}")

    fv_table = pq.read_table(fact_versions_path)
    fv_rows = fv_table.to_pylist()

    # Hydrate FactVersion objects
    fact_versions: list[FactVersion] = []
    for r in fv_rows:
        fv = FactVersion(
            fact_version_id=r["fact_version_id"],
            logical_fact_id=r["logical_fact_id"],
            subject_id=r["subject_id"],
            relation_id=r["relation_id"],
            object_id=r["object_id"],
            valid_from=datetime.fromisoformat(r["valid_from"]),
            valid_to=datetime.fromisoformat(r["valid_to"]) if r.get("valid_to") else None,
            evidence_observed_at=datetime.fromisoformat(r["evidence_observed_at"]),
            ingested_at_real=datetime.fromisoformat(r["ingested_at_real"]),
            supersedes_version_id=r.get("supersedes_version_id"),
            revision_type=r.get("revision_type", "creation"),
            source_id=r["source_id"],
            source_url=r.get("source_url", ""),
            evidence_span_start=r["evidence_span_start"],
            evidence_span_end=r["evidence_span_end"],
            evidence_text_hash=r["evidence_text_hash"],
            extractor_version=r.get("extractor_version", ""),
            entity_map_version=r.get("entity_map_version", ""),
            confidence=r.get("confidence"),
            adjudication_status=r.get("adjudication_status"),
        )
        fact_versions.append(fv)

    snapshot_summaries = []
    invariant_results = []
    all_snapshots_pass = True

    # 1. Build and Materialize each snapshot
    for b in boundaries:
        snap_id = b["snapshot_id"]
        cutoff_str = b["cutoff"]
        cutoff = datetime.fromisoformat(cutoff_str)

        # build_snapshot encapsulates known_filter, supersession, validity_filter, canonical_sort, hash
        active_facts, semantic_hash = build_snapshot(fact_versions, cutoff)

        # Materialize snapshot rows
        snap_rows = []
        for f in active_facts:
            snap_rows.append(
                make_row(
                    "snapshot_facts",
                    fact_version_id=f.fact_version_id,
                    logical_fact_id=f.logical_fact_id,
                    subject_id=f.subject_id,
                    relation_id=f.relation_id,
                    object_id=f.object_id,
                    valid_from=f.valid_from.isoformat(),
                    valid_to=f.valid_to.isoformat() if f.valid_to else None,
                    evidence_observed_at=f.evidence_observed_at.isoformat(),
                    source_id=f.source_id,
                )
            )

        validate_rows("snapshot_facts", snap_rows)
        snap_parquet_path = snapshots_dir / f"snapshot_{snap_id}.parquet"
        write_parquet_immutable(snap_parquet_path, "snapshot_facts", snap_rows)

        # Manifest
        manifest_path = snapshots_dir / f"snapshot_{snap_id}_manifest.yaml"
        manifest_payload = {
            "schema_version": CONTRACT_VERSION,
            "snapshot_id": snap_id,
            "cutoff": cutoff_str,
            "row_count": len(snap_rows),
            "entity_count": len(set([r["subject_id"] for r in snap_rows] + [r["object_id"] for r in snap_rows])),
            "semantic_sha256": semantic_hash,
            "physical_sha256": sha256_file(snap_parquet_path),
            "created_at_real": utc_now_iso(),
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(manifest_payload, f, sort_keys=False)

        snapshot_summaries.append(manifest_payload)

    # 2. Evaluate Hard Scientific Invariants
    # Check 1: NO FUTURE EVIDENCE
    # No fact in snapshot_T has evidence_observed_at > cutoff_T
    future_ev_violations = 0
    for b, s in zip(boundaries, snapshot_summaries):
        cutoff = datetime.fromisoformat(b["cutoff"])
        snap_table = pq.read_table(snapshots_dir / f"snapshot_{b['snapshot_id']}.parquet")
        for r in snap_table.to_pylist():
            obs_at = datetime.fromisoformat(r["evidence_observed_at"])
            if obs_at > cutoff:
                future_ev_violations += 1

    invariant_results.append({
        "check_id": "NO_FUTURE_EVIDENCE",
        "status": "PASS" if future_ev_violations == 0 else "FAIL",
        "violations": future_ev_violations,
    })

    # Check 2: STRICT TEMPORAL VALIDITY
    # valid_from <= cutoff and (valid_to is null or cutoff < valid_to)
    validity_violations = 0
    for b in boundaries:
        cutoff = datetime.fromisoformat(b["cutoff"])
        snap_table = pq.read_table(snapshots_dir / f"snapshot_{b['snapshot_id']}.parquet")
        for r in snap_table.to_pylist():
            v_from = datetime.fromisoformat(r["valid_from"])
            if v_from > cutoff:
                validity_violations += 1
            if r.get("valid_to"):
                v_to = datetime.fromisoformat(r["valid_to"])
                if cutoff >= v_to:
                    validity_violations += 1

    invariant_results.append({
        "check_id": "STRICT_TEMPORAL_VALIDITY",
        "status": "PASS" if validity_violations == 0 else "FAIL",
        "violations": validity_violations,
    })

    # Check 3: DETERMINISTIC REBUILD
    # Rebuilding snapshot T01 must produce the exact same semantic hash
    rebuilt_facts, test_hash = build_snapshot(fact_versions, datetime.fromisoformat(boundaries[0]["cutoff"]))
    rebuild_pass = (test_hash == snapshot_summaries[0]["semantic_sha256"])
    invariant_results.append({
        "check_id": "DETERMINISTIC_REBUILD",
        "status": "PASS" if rebuild_pass else "FAIL",
        "reference_snapshot": boundaries[0]["snapshot_id"],
        "hash_matched": rebuild_pass,
    })

    # Check 4: MONOTONIC KNOWN-TIME GROWTH
    # Cumulative known facts monotonically increase across snapshots
    monotonic_pass = True
    for i in range(len(snapshot_summaries) - 1):
        if snapshot_summaries[i]["row_count"] > snapshot_summaries[i + 1]["row_count"]:
            monotonic_pass = False
            break
    invariant_results.append({
        "check_id": "MONOTONIC_GROWTH",
        "status": "PASS" if monotonic_pass else "FAIL",
        "monotonically_increasing": monotonic_pass,
    })

    overall_status = "PASS" if all(inv["status"] == "PASS" for inv in invariant_results) else "FAIL"

    report_payload = {
        "schema_version": CONTRACT_VERSION,
        "stage": "4.17_bitemporal_snapshots",
        "run_id": run_id,
        "status": overall_status,
        "total_snapshots": len(boundaries),
        "snapshots": snapshot_summaries,
        "invariant_checks": invariant_results,
        "evaluated_at_real": utc_now_iso(),
    }

    report_path = reports_dir / "snapshots_integrity_report.json"
    write_json_immutable(report_path, report_payload)

    return report_payload


def main():
    parser = argparse.ArgumentParser(description="Run Stage 4.17: Bitemporal Snapshots Builder.")
    parser.add_argument("--run", default="production_v2", help="Run ID")
    parser.add_argument("--repo-root", default=".", help="Repository root")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    res = run_bitemporal_snapshots(repo_root=repo_root, run_id=args.run)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
