"""Stage 4.15: KG Events and Feasibility Analyzer.

Materializes KG state transitions (events) from FactVersions and evaluates
temporal recurrence and feasibility for anchor selection and snapshot boundaries.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from kg_pipeline.contracts import CONTRACT_VERSION, make_row, validate_rows
from kg_pipeline.hashing import sha256_text, utc_now_iso
from kg_pipeline.run import get_run_dir
from kg_pipeline.storage import write_json_immutable, write_parquet_immutable

logger = logging.getLogger("kg_events_feasibility")


def run_kg_events_and_feasibility(repo_root: Path, run_id: str = "production_v2") -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    tables_dir = run_dir / "tables"
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    fact_versions_path = tables_dir / "fact_versions.parquet"
    if not fact_versions_path.is_file():
        raise FileNotFoundError(f"Missing {fact_versions_path}")

    memberships_path = tables_dir / "document_memberships.parquet"
    retrievals_path = tables_dir / "retrievals.parquet"

    # Map body variants to earliest true temporal acquisition/archive time
    bv_to_time = {}
    if memberships_path.is_file() and retrievals_path.is_file():
        ret = pq.read_table(retrievals_path)
        ret_archive = {r["retrieval_id"]: r["archive_datetime"] for r in ret.to_pylist() if r.get("archive_datetime")}
        ret_retrieved = {r["retrieval_id"]: r["retrieved_at_real"] for r in ret.to_pylist() if r.get("retrieved_at_real")}

        dm = pq.read_table(memberships_path)
        for r in dm.to_pylist():
            bv = r["body_variant_id"]
            ret_ids = json.loads(r["retrieval_ids_json"]) if r["retrieval_ids_json"] else []
            # Priority 1: archive_datetime (historical observation window 2025-03 -> 2026-08)
            arch_times = [ret_archive[rid] for rid in ret_ids if rid in ret_archive]
            if arch_times:
                bv_to_time[bv] = min(arch_times)
            else:
                crawl_times = [ret_retrieved[rid] for rid in ret_ids if rid in ret_retrieved]
                if crawl_times:
                    bv_to_time[bv] = min(crawl_times)

    fv_table = pq.read_table(fact_versions_path)
    facts_by_lfid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in fv_table.to_pylist():
        facts_by_lfid[r["logical_fact_id"]].append(r)

    # 1. Materialize KG Events (State transitions)
    # Event = KG state transition. Multiple articles supporting the same state transition do not create duplicate events.
    kg_events_rows = []
    entity_events: dict[str, list[str]] = defaultdict(list)
    entity_relations: dict[str, set[str]] = defaultdict(set)

    for lfid, versions in facts_by_lfid.items():
        # Order versions chronologically by source document time or observed time
        versions.sort(key=lambda v: bv_to_time.get(v["source_id"], v["evidence_observed_at"]))
        first_v = versions[0]
        effective_at = bv_to_time.get(first_v["source_id"], first_v["evidence_observed_at"])
        
        event_id = f"ev_{sha256_text(f'{lfid}|assert|{effective_at}')[:16]}"
        s = first_v["subject_id"]
        rel = first_v["relation_id"]
        o = first_v["object_id"]
        v_ids = [v["fact_version_id"] for v in versions]

        event_row = make_row(
            "kg_events",
            event_id=event_id,
            logical_fact_id=lfid,
            subject_id=s,
            relation_id=rel,
            object_id=o,
            event_type="assert",
            effective_at=effective_at,
            source_fact_version_ids_json=json.dumps(v_ids),
            evidence_count=len(versions),
        )
        kg_events_rows.append(event_row)

        entity_events[s].append(effective_at)
        entity_relations[s].add(rel)
        entity_events[o].append(effective_at)
        entity_relations[o].add(rel)

    # Sort canonically
    kg_events_rows.sort(key=lambda x: (x["effective_at"], x["event_id"]))
    validate_rows("kg_events", kg_events_rows)

    kg_events_path = tables_dir / "kg_events.parquet"
    write_parquet_immutable(kg_events_path, "kg_events", kg_events_rows)

    # 2. Materialize Anchor Candidates Prelock
    anchor_rows = []
    for ent, ev_times in entity_events.items():
        ev_times.sort()
        n_ev = len(ev_times)
        n_rel = len(entity_relations[ent])
        first_seen = ev_times[0]
        last_seen = ev_times[-1]

        # Recurrence score: balances event volume across distinct relations
        rec_score = float(n_ev * 0.7 + n_rel * 0.3)
        if n_ev >= 5 and n_rel >= 2:
            feasibility_status = "HIGH_FEASIBILITY"
        elif n_ev >= 2:
            feasibility_status = "MEDIUM_FEASIBILITY"
        else:
            feasibility_status = "LOW_FEASIBILITY"

        candidate_id = f"anc_{sha256_text(f'{ent}|{run_id}')[:16]}"
        anchor_rows.append(
            make_row(
                "anchor_candidates_prelock",
                candidate_id=candidate_id,
                entity_id=ent,
                total_events=n_ev,
                distinct_relations=n_rel,
                first_seen=first_seen,
                last_seen=last_seen,
                recurrence_score=round(rec_score, 4),
                feasibility_status=feasibility_status,
            )
        )

    anchor_rows.sort(key=lambda x: x["recurrence_score"], reverse=True)
    validate_rows("anchor_candidates_prelock", anchor_rows)

    anchor_path = tables_dir / "anchor_candidates_prelock.parquet"
    write_parquet_immutable(anchor_path, "anchor_candidates_prelock", anchor_rows)

    # 3. Compute Feasibility & Temporal Drift Metrics
    event_dates = [e["effective_at"] for e in kg_events_rows]
    min_date = min(event_dates) if event_dates else None
    max_date = max(event_dates) if event_dates else None
    unique_timestamps = len(set(event_dates))

    status_counts = Counter(r["feasibility_status"] for r in anchor_rows)
    relation_counts = Counter(r["relation_id"] for r in kg_events_rows)

    feasibility_summary = {
        "schema_version": CONTRACT_VERSION,
        "stage": "4.15_kg_events_and_feasibility",
        "run_id": run_id,
        "status": "PASS",
        "events_summary": {
            "total_kg_events": len(kg_events_rows),
            "state_transition_type": "assert",
            "earliest_event_at": min_date,
            "latest_event_at": max_date,
            "unique_event_timestamps": unique_timestamps,
            "distinct_logical_facts": len(facts_by_lfid),
            "total_source_fact_versions": len(fv_table),
            "relation_distribution": dict(relation_counts.most_common()),
        },
        "anchor_feasibility": {
            "total_candidates": len(anchor_rows),
            "high_feasibility_count": status_counts.get("HIGH_FEASIBILITY", 0),
            "medium_feasibility_count": status_counts.get("MEDIUM_FEASIBILITY", 0),
            "low_feasibility_count": status_counts.get("LOW_FEASIBILITY", 0),
            "top_anchor_entities": [
                {
                    "entity_id": r["entity_id"],
                    "total_events": r["total_events"],
                    "distinct_relations": r["distinct_relations"],
                    "recurrence_score": r["recurrence_score"],
                    "feasibility_status": r["feasibility_status"],
                }
                for r in anchor_rows[:10]
            ],
        },
        "temporal_drift_potential": {
            "sufficient_signal": len(kg_events_rows) >= 500 and status_counts.get("HIGH_FEASIBILITY", 0) >= 20,
            "recommended_snapshot_range": "8-12 snapshots (Stage 4.16 quantile-based)",
            "qa_feasibility": "FEASIBLE" if status_counts.get("HIGH_FEASIBILITY", 0) >= 10 else "INSUFFICIENT_ANCHORS",
        },
        "evaluated_at_real": utc_now_iso(),
    }

    report_path = reports_dir / "feasibility_report.json"
    write_json_immutable(report_path, feasibility_summary)

    return feasibility_summary


def main():
    parser = argparse.ArgumentParser(description="Run Stage 4.15: KG Events and Feasibility Analyzer.")
    parser.add_argument("--run", default="production_v2", help="Run ID")
    parser.add_argument("--repo-root", default=".", help="Repository root")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    res = run_kg_events_and_feasibility(repo_root=repo_root, run_id=args.run)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
