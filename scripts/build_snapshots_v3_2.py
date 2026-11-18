"""S1: rebuild canonical snapshots (v3.2 CANDIDATE) with corrected evidence-observed time.

Reads the immutable v3.1 package and the raw blobs; writes a NEW package directory. Nothing in
v3.1 or data/raw is modified. Evidence time basis per document (see temporal.evidence_time):
Wayback archive_datetime if present, else publisher-declared publication time, else quarantine.
No retrieval time is ever used as evidence time and no fallback timestamp is fabricated.

Dev-mode technical rebuild: it does not certify M1/G1/G2 and keeps entity_map v1 (S2 changes it).
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_m2_inputs import (  # noqa: E402
    encode, provenance, sha, validate_manifest, write_json,
)
from temporal.evidence_time import (  # noqa: E402
    BASIS_PUBLISHER, event_balanced_cuts, extract_publisher_published_at,
    parse_aware, resolve_document_time, tuoitre_url_published_at,
)

POLICY = "OUTCOME_BLIND_EVENT_BALANCED_V1_TIE_SAFE"
CHROME_FLAG = "SHORT_BODY_LT_200_CHARS"  # producer quality flag: body is page chrome, not the article
CONTRACT = "ticket_a_v1"
MIN_SNAPSHOT_DAYS = 14.0        # candidate threshold from the plan (S1); to be registered
MAX_QUARANTINE_SHARE = 0.05     # candidate threshold from the plan (S1); to be registered
MAX_CROSSCHECK_MEDIAN_DAYS = 15.0
CANONICAL_COLUMNS = ["schema_version", "fact_version_id", "logical_fact_id", "subject_id",
                     "relation_id", "object_id", "valid_from", "valid_to",
                     "evidence_observed_at", "source_id"]


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def blob_path(raw_root: Path, digest: str) -> Path:
    return raw_root / "raw/stage_4_4/blobs/sha256" / digest[:2] / f"{digest}.bin"


def read_table(package: Path, name: str):
    return pq.read_table(package / "tables" / f"{name}.parquet").to_pandas()


def build_document_ledger(package: Path, raw_root: Path, body_ids: set[str]):
    body_flags = {r.body_variant_id: json.loads(r.quality_flags_json)
                  for r in read_table(package, "body_variants").itertuples(index=False)}
    memberships = read_table(package, "document_memberships")
    retrievals = read_table(package, "retrievals").set_index("retrieval_id")
    memberships = memberships[memberships.body_variant_id.isin(body_ids)]
    docs: dict[str, dict[str, Any]] = {}
    for row in memberships.itertuples(index=False):
        doc = docs.setdefault(row.body_variant_id, {"blobs": set(), "retrievals": set()})
        doc["blobs"].add(row.raw_blob_sha256)
        doc["retrievals"].update(json.loads(row.retrieval_ids_json))
    blobs = sorted({b for d in docs.values() for b in d["blobs"]})

    def parse_blob(digest: str):
        path = blob_path(raw_root, digest)
        return digest, (extract_publisher_published_at(path.read_bytes()) if path.is_file() else "MISSING")

    with ThreadPoolExecutor(16) as pool:
        parsed = dict(pool.map(parse_blob, blobs))

    ledger: list[dict[str, Any]] = []
    for body_id, doc in sorted(docs.items()):
        archives, retrieved, urls, sources = [], [], set(), set()
        for rid in doc["retrievals"]:
            if rid not in retrievals.index:
                continue
            r = retrievals.loc[rid]
            for value, bucket in ((r.archive_datetime, archives), (r.retrieved_at_real, retrieved)):
                parsed_value = parse_aware(value) if isinstance(value, str) else None
                if parsed_value is not None:
                    bucket.append(parsed_value)
            if isinstance(r.final_url, str):
                urls.add(r.final_url)
            if isinstance(r.source_id, str):
                sources.add(r.source_id)
        html = [parsed[b] for b in doc["blobs"] if parsed[b] not in (None, "MISSING")]
        missing_blobs = sum(parsed[b] == "MISSING" for b in doc["blobs"])
        html_times = sorted(h[0] for h in html)
        publisher_at = html_times[0] if html_times else None
        publisher_src = html[0][2] if html else None
        url_at = next((t for t in (tuoitre_url_published_at(u) for u in sorted(urls)) if t), None)
        flags: list[str] = []
        if publisher_at is None and url_at is not None:
            publisher_at, publisher_src = url_at, "tuoitre_url_embedded_id"
            flags.append("URL_DERIVED_TIME")
        if url_at is not None and html_times and abs((url_at - html_times[0]).total_seconds()) > 86400:
            flags.append("URL_HTML_TIME_DISAGREE")
        if len(html_times) > 1 and (html_times[-1] - html_times[0]).total_seconds() > 86400:
            flags.append("HTML_TIME_SPREAD_GT_1D")
        if missing_blobs:
            flags.append("RAW_BLOB_MISSING")
        resolved = resolve_document_time(
            min(archives) if archives else None, publisher_at, min(retrieved) if retrieved else None,
            chrome_text_only=CHROME_FLAG in body_flags.get(body_id, []))
        ledger.append({
            "body_variant_id": body_id, "n_raw_blobs": len(doc["blobs"]),
            "source_ids": ",".join(sorted(sources)), "urls": sorted(urls)[:3],
            "archive_min": iso(min(archives) if archives else None),
            "retrieved_min": iso(min(retrieved) if retrieved else None),
            "publisher_published_at": iso(publisher_at), "publisher_time_source": publisher_src,
            "observed_at_v32": iso(resolved.observed_at), "time_basis": resolved.basis,
            "time_confidence": resolved.confidence,
            "time_flags": ",".join(list(resolved.flags) + flags),
            "exclusion_reason": resolved.exclusion_reason,
        })
    return ledger


def crosscheck_article_ids(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    """Independent check: VnExpress article id is monotone in time; calibrate it on Wayback captures."""
    import re

    import numpy as np
    pattern = re.compile(r"vnexpress\.net/.*-(\d{6,8})\.html")

    def article_id(urls: list[str]) -> float | None:
        for u in urls:
            m = pattern.search(u)
            if m:
                return float(m.group(1))
        return None

    cal_x, cal_y, test_x, test_y = [], [], [], []
    for row in ledger:
        aid = article_id(row["urls"])
        if aid is None:
            continue
        if row["archive_min"]:
            cal_x.append(aid)
            cal_y.append(parse_aware(row["archive_min"]).timestamp() / 86400)
        elif row["time_basis"] == BASIS_PUBLISHER:
            test_x.append(aid)
            test_y.append(parse_aware(row["observed_at_v32"]).timestamp() / 86400)
    if len(cal_x) < 50 or not test_x:
        return {"status": "NOT_EVALUATED", "calibration_docs": len(cal_x), "test_docs": len(test_x)}
    coef = np.polyfit(cal_x, cal_y, 1)
    diff = np.abs(np.array(test_y) - np.polyval(coef, test_x))
    return {"status": "PASS" if float(np.median(diff)) <= MAX_CROSSCHECK_MEDIAN_DAYS else "FAIL",
            "calibration_docs": len(cal_x), "test_docs": len(test_x),
            "median_abs_diff_days": round(float(np.median(diff)), 2),
            "p90_abs_diff_days": round(float(np.quantile(diff, 0.9)), 2),
            "max_abs_diff_days": round(float(diff.max()), 2),
            "threshold_median_days": MAX_CROSSCHECK_MEDIAN_DAYS}


def write_parquet(path: Path, table: pa.Table) -> str:
    pq.write_table(table, path, compression="snappy")
    return sha(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="data/evolving_kg_downstream_v3_1")
    parser.add_argument("--data-root", default="data", help="folder containing raw/stage_4_4/blobs")
    parser.add_argument("--out", default="data/evolving_kg_downstream_v3_2")
    parser.add_argument("--n-snapshots", type=int, default=10)
    parser.add_argument("--entity-map", default=None, help="entity_map_v2.parquet; omit to keep v1 ids")
    parser.add_argument("--release-label", default="v3.2")
    args = parser.parse_args()
    package, raw_root, out = ROOT / args.package, ROOT / args.data_root, ROOT / args.out
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {out}")
    started = datetime.now(timezone.utc)
    entity_map: dict[str, str | None] | None = None
    map_path = ROOT / args.entity_map if args.entity_map else None
    if map_path is not None:
        mt = pq.read_table(map_path).to_pandas()
        entity_map = {r.v1_entity_id: (r.v2_entity_id if r.action != "BLOCK" else None)
                      for r in mt.itertuples(index=False)}

    facts = read_table(package, "fact_versions")
    events = read_table(package, "kg_events")
    facts["body_variant_id"] = facts.source_url.str.replace("internal://", "", regex=False)
    ledger = build_document_ledger(package, raw_root, set(facts.body_variant_id))
    by_body = {row["body_variant_id"]: row for row in ledger}

    fv_rows = []
    for f in facts.itertuples(index=False):
        doc = by_body.get(f.body_variant_id)
        observed = doc["observed_at_v32"] if doc else None
        copy_of_observed = f.valid_from == f.evidence_observed_at
        fv_rows.append({
            "fact_version_id": f.fact_version_id, "logical_fact_id": f.logical_fact_id,
            "subject_id": f.subject_id, "relation_id": f.relation_id, "object_id": f.object_id,
            "body_variant_id": f.body_variant_id,
            "evidence_observed_at_v31": f.evidence_observed_at, "valid_from_v31": f.valid_from,
            "evidence_observed_at_v32": observed,
            "valid_from_v32": None if copy_of_observed else f.valid_from,
            "valid_from_v31_was_copy_of_observed": bool(copy_of_observed),
            "time_basis": doc["time_basis"] if doc else None,
            "time_confidence": doc["time_confidence"] if doc else None,
            "time_flags": doc["time_flags"] if doc else "NO_DOCUMENT_LINK",
            "exclusion_reason": (doc["exclusion_reason"] if doc else "NO_DOCUMENT_LINK") if observed is None else None,
        })
    if entity_map is not None:
        for r in fv_rows:
            r["subject_id_v2"], r["object_id_v2"] = entity_map[r["subject_id"]], entity_map[r["object_id"]]
    fv_by_id = {r["fact_version_id"]: r for r in fv_rows}

    event_rows, kept = [], []
    for e in events.itertuples(index=False):
        ids = json.loads(e.source_fact_version_ids_json)
        included = sorted((fv_by_id[i] for i in ids if fv_by_id[i]["evidence_observed_at_v32"]),
                          key=lambda r: (parse_aware(r["evidence_observed_at_v32"]), r["fact_version_id"]))
        row = {"event_id": e.event_id, "logical_fact_id": e.logical_fact_id,
               "effective_at_v31": e.effective_at, "n_fact_versions": len(ids),
               "n_included": len(included),
               "effective_at_v32": included[0]["evidence_observed_at_v32"] if included else None,
               "representative_fact_version_id": included[0]["fact_version_id"] if included else None,
               "exclusion_reason": None if included else "NO_FACT_VERSION_WITH_EVIDENCE_TIME"}
        event_rows.append(row)
        if included:
            kept.append(row)
    mapped: dict[str, dict[str, Any]] = {}
    if entity_map is not None:
        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row, e in zip(event_rows, events.itertuples(index=False)):
            sub, obj = entity_map[e.subject_id], entity_map[e.object_id]
            mapped[row["event_id"]] = {"subject_id_v2": sub, "object_id_v2": obj,
                                       "merged_into_event_id": None, "n_merged_events": None}
            if row["exclusion_reason"] is None and (sub is None or obj is None):
                row["exclusion_reason"] = "GENERIC_ENTITY_BLOCKED"
            elif row["exclusion_reason"] is None and sub == obj:
                row["exclusion_reason"] = "SELF_LOOP_AFTER_MERGE"
            if row["exclusion_reason"] is None:
                groups.setdefault((sub, e.relation_id, obj), []).append(row)
        kept = []
        for members in groups.values():
            members.sort(key=lambda r: (parse_aware(r["effective_at_v32"]), r["logical_fact_id"]))
            mapped[members[0]["event_id"]]["n_merged_events"] = len(members)
            for other in members[1:]:
                mapped[other["event_id"]]["merged_into_event_id"] = members[0]["event_id"]
            kept.append(members[0])
    kept.sort(key=lambda r: (parse_aware(r["effective_at_v32"]), r["logical_fact_id"]))
    times = [parse_aware(r["effective_at_v32"]) for r in kept]
    cuts = event_balanced_cuts(times, args.n_snapshots)
    snapshot_ids = [f"T{i + 1:02d}" for i in range(args.n_snapshots)]
    first_snapshot = {}
    for k, sid in enumerate(snapshot_ids):
        for r in kept[cuts[k]:cuts[k + 1]]:
            first_snapshot[r["event_id"]] = sid
    for r in event_rows:
        r["first_snapshot"] = first_snapshot.get(r["event_id"])
        r.update(mapped.get(r["event_id"], {}))

    out.mkdir(parents=True)
    for sub in ("snapshots", "tables", "config", "reports"):
        (out / sub).mkdir()
    specs, boundaries, snapshot_hashes, canonical_sets = [], [], {}, []
    for k, sid in enumerate(snapshot_ids):
        cutoff = times[cuts[k + 1] - 1]
        members = kept[:cuts[k + 1]]
        rows = []
        for r in members:
            f = fv_by_id[r["representative_fact_version_id"]]
            rows.append({"schema_version": CONTRACT, "fact_version_id": f["fact_version_id"],
                         "logical_fact_id": f["logical_fact_id"],
                         "subject_id": mapped[r["event_id"]]["subject_id_v2"] if entity_map else f["subject_id"],
                         "relation_id": f["relation_id"],
                         "object_id": mapped[r["event_id"]]["object_id_v2"] if entity_map else f["object_id"],
                         "valid_from": f["valid_from_v32"], "valid_to": None,
                         "evidence_observed_at": f["evidence_observed_at_v32"],
                         "source_id": f["body_variant_id"]})
        table = pa.Table.from_pylist(rows, schema=pa.schema(
            [pa.field("schema_version", pa.string(), nullable=False)]
            + [pa.field(c, pa.string()) for c in CANONICAL_COLUMNS[1:]]))
        path = out / "snapshots" / f"snapshot_{sid}_canonical.parquet"
        digest = write_parquet(path, table)
        read_back = pq.read_table(path).to_pylist()
        semantic = sha(json.dumps({"table_name": "snapshot_facts_canonical", "contract_version": CONTRACT,
                                   "rows": read_back}, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")).encode())
        entities = {v for r in rows for v in (r["subject_id"], r["object_id"])}
        created = datetime.now(timezone.utc).isoformat()
        sidecar = {"artifact_type": "canonical_parquet_part", "contract_version": CONTRACT,
                   "created_at_real": created, "physical_sha256_computed_at_real": digest,
                   "row_count": len(rows), "semantic_sha256": semantic,
                   "table_name": "snapshot_facts_canonical"}
        (out / "snapshots" / f"snapshot_{sid}_canonical.parquet.manifest.json").write_text(
            json.dumps(sidecar, indent=2), encoding="utf-8")
        (out / "snapshots" / f"snapshot_{sid}_manifest.yaml").write_text(yaml.safe_dump({
            "schema_version": CONTRACT, "snapshot_id": sid, "cutoff": iso(cutoff),
            "canonical_triple_count": len(rows), "entity_count": len(entities),
            "canonical_physical_sha256": digest, "created_at_real": created}, sort_keys=False),
            encoding="utf-8")
        specs.append({"snapshot_id": sid, "cutoff": iso(cutoff),
                      "parquet_path": f"snapshots/snapshot_{sid}_canonical.parquet",
                      "edges": len(rows), "entities": len(entities), "parquet_sha256": digest,
                      "semantic_sha256": semantic,
                      "manifest_path": f"snapshots/snapshot_{sid}_canonical.parquet.manifest.json"})
        start = times[cuts[k]]
        boundaries.append({"snapshot_id": sid, "cutoff": iso(cutoff), "interval_start": iso(start),
                           "interval_end": iso(cutoff), "event_count": cuts[k + 1] - cuts[k],
                           "duration_days": round((cutoff - start).total_seconds() / 86400, 4),
                           "event_slice_indices": [cuts[k], cuts[k + 1]]})
        snapshot_hashes[sid] = digest
        canonical_sets.append({(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows})

    boundary_hash = sha(encode({"policy": POLICY, "boundaries": boundaries}))
    (out / "snapshot_boundaries.yaml").write_text(yaml.safe_dump({
        "schema_version": CONTRACT, "run_id": f"{args.release_label.replace('.', '_')}_candidate", "partition_rule": POLICY,
        "n_snapshots": args.n_snapshots, "total_kg_events": len(kept),
        "boundary_hash": boundary_hash, "boundaries": boundaries}, sort_keys=False), encoding="utf-8")
    (out / "config/downstream_transe_config.yaml").write_text(yaml.safe_dump({
        "dataset_name": f"evolving_kg_production_{args.release_label.replace('.', '_')}_candidate",
        "data_readiness": "CANDIDATE_NOT_CERTIFIED",
        "source_format": "canonical_parquet", "total_snapshots": args.n_snapshots,
        "release_id": f"evolving_kg_downstream_{args.release_label}-candidate", "snapshot_hash_algorithm": "SHA-256",
        "snapshot_manifests_required": True, "derived_from_release": "evolving_kg_downstream_v3.1",
        "entity_map_version": ("v1_mock (unchanged)" if map_path is None else "entity_map_v2"),
        "entity_map": None if map_path is None else {
            "path": args.entity_map, "sha256": sha(map_path.read_bytes()), "review_status": "PROPOSED_UNREVIEWED"},
        "snapshots": specs},
        sort_keys=False, allow_unicode=True), encoding="utf-8")

    import pandas as pd
    ledger_df = pd.DataFrame(ledger)
    ledger_df["urls"] = ledger_df.urls.map(json.dumps)
    tables = {"evidence_time_ledger": ledger_df, "fact_versions_v3_2": pd.DataFrame(fv_rows),
              "kg_events_v3_2": pd.DataFrame(event_rows),
              "snapshot_exclusions": pd.DataFrame(
                  [{"kind": "fact_version", "id": r["fact_version_id"], "reason": r["exclusion_reason"]}
                   for r in fv_rows if r["exclusion_reason"]]
                  + [{"kind": "event", "id": r["event_id"], "reason": r["exclusion_reason"]}
                     for r in event_rows if r["exclusion_reason"]],
                  columns=["kind", "id", "reason"])}
    table_hashes = {name: write_parquet(out / "tables" / f"{name}.parquet",
                                        pa.Table.from_pandas(df, preserve_index=False))
                    for name, df in tables.items()}

    # ---- validation (technical S1 checks; not a scientific gate) ----
    included = [r for r in fv_rows if r["evidence_observed_at_v32"]]
    cutoffs = [parse_aware(s["cutoff"]) for s in specs]
    inv01 = all(parse_aware(r["evidence_observed_at"]) <= cutoffs[k]
                for k, s in enumerate(specs)
                for r in pq.read_table(out / s["parquet_path"]).to_pylist())
    crawl_as_evidence = sum(1 for r in included
                            if r["time_basis"] == BASIS_PUBLISHER and r["evidence_observed_at_v32"]
                            == by_body[r["body_variant_id"]]["retrieved_min"])
    nested = all(a <= b for a, b in zip(canonical_sets, canonical_sets[1:]))
    boundary_ties = sum(1 for c in cuts[1:-1] if times[c] == times[c - 1])
    durations = [b["duration_days"] for b in boundaries]
    excluded_fv_share = 1 - len(included) / len(fv_rows)
    excluded_ev_share = sum(1 for r in event_rows if r["exclusion_reason"]) / len(event_rows)  # merged events are not quarantined
    cross = crosscheck_article_ids(ledger)
    lags = [(parse_aware(d["archive_min"]) - parse_aware(d["publisher_published_at"])).total_seconds() / 86400
            for d in ledger if d["archive_min"] and d["publisher_published_at"]]
    checks = {
        "INV01_all_rows_observed_le_cutoff": inv01,
        "no_retrieval_time_used_as_publisher_basis": crawl_as_evidence == 0,
        "no_boundary_splits_equal_timestamp_group": boundary_ties == 0,
        "cutoffs_strictly_increasing": all(a < b for a, b in zip(cutoffs, cutoffs[1:])),
        "snapshots_nested_append_only": nested,
        f"min_snapshot_duration_ge_{MIN_SNAPSHOT_DAYS:g}d": min(durations) >= MIN_SNAPSHOT_DAYS,
        f"quarantine_no_evidence_time_le_{MAX_QUARANTINE_SHARE:.0%}": max(
            excluded_fv_share, sum(1 for r in event_rows if r["exclusion_reason"] == "NO_FACT_VERSION_WITH_EVIDENCE_TIME")
            / len(event_rows)) <= MAX_QUARANTINE_SHARE,
        f"quarantine_generic_entity_le_{MAX_QUARANTINE_SHARE:.0%}": sum(
            1 for r in event_rows if r["exclusion_reason"] == "GENERIC_ENTITY_BLOCKED") / len(event_rows)
        <= MAX_QUARANTINE_SHARE,
        "article_id_crosscheck": cross["status"] == "PASS",
    }
    map_summary = None
    if entity_map is not None:
        snap_rows = [r for sp in specs for r in pq.read_table(out / sp["parquet_path"]).to_pylist()]
        checks["all_snapshot_entity_ids_are_v2"] = all(
            r["subject_id"].startswith("ent2_") and r["object_id"].startswith("ent2_") for r in snap_rows)
        checks["no_self_loops_after_merge"] = all(r["subject_id"] != r["object_id"] for r in snap_rows)
        reasons = Counter(r["exclusion_reason"] for r in event_rows if r["exclusion_reason"])
        map_summary = {"events_blocked_generic_entity": reasons.get("GENERIC_ENTITY_BLOCKED", 0),
                       "events_self_loop_after_merge": reasons.get("SELF_LOOP_AFTER_MERGE", 0),
                       "events_merged_into_another": sum(1 for r in event_rows if r.get("merged_into_event_id"))}
    report = {
        "stage": "S1", "status": "TECHNICAL_CHECKS_PASS" if all(checks.values()) else "TECHNICAL_CHECKS_FAIL",
        "scientific_certification": False, "checks": checks,
        "counts": {"fact_versions": len(fv_rows), "fact_versions_included": len(included),
                   "events": len(event_rows), "events_included": len(kept),
                   "documents": len(ledger)},
        "basis_counts_fact_versions": dict(Counter(r["time_basis"] for r in included)),
        "exclusion_reasons": dict(Counter(r["exclusion_reason"] for r in fv_rows if r["exclusion_reason"])),
        "event_exclusion_reasons": dict(Counter(r["exclusion_reason"] for r in event_rows if r["exclusion_reason"])),
        "quarantine_share": {"fact_versions": round(excluded_fv_share, 4), "events": round(excluded_ev_share, 4)},
        "document_flags": dict(Counter(f for d in ledger for f in d["time_flags"].split(",") if f)),
        "valid_from_copy_of_observed_nulled": sum(r["valid_from_v31_was_copy_of_observed"] for r in fv_rows),
        "valid_from_kept_independent": sum(not r["valid_from_v31_was_copy_of_observed"] for r in fv_rows),
        "valid_from_after_observed_kept": sum(
            1 for r in included if r["valid_from_v32"] and r["valid_from_v32"] > r["evidence_observed_at_v32"]),
        "wayback_minus_publisher_lag_days": (
            {"n": len(lags), "median": round(statistics.median(lags), 2),
             "p90": round(sorted(lags)[int(0.9 * len(lags))], 2), "max": round(max(lags), 2),
             "negative": sum(x < 0 for x in lags)} if lags else None),
        "article_id_crosscheck": cross,
        "entity_map": map_summary,
        "snapshots": [{"snapshot_id": s["snapshot_id"], "cutoff": s["cutoff"], "triples": s["edges"],
                       "entities": s["entities"], "duration_days": b["duration_days"],
                       "events_in_slice": b["event_count"]} for s, b in zip(specs, boundaries)],
    }
    write_json(out / "reports/s1_validation_report.json", report)

    inputs = {f"{args.package}/tables/{n}.parquet": sha((package / "tables" / f"{n}.parquet").read_bytes())
              for n in ("fact_versions", "kg_events", "document_memberships", "retrievals")}
    if map_path is not None:
        inputs[args.entity_map] = sha(map_path.read_bytes())
    inputs["src/temporal/evidence_time.py"] = sha((ROOT / "src/temporal/evidence_time.py").read_bytes())
    inputs["scripts/build_snapshots_v3_2.py"] = sha(Path(__file__).read_bytes())
    manifest = {
        "experiment_id": f"s1_snapshots_v3_2_{started.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        "protocol_version": "v1-draft", "mode": "s1_snapshot_retime_candidate",
        "scientific_certification": False, "git": provenance(), "seed": None,
        "inputs": {"data_hash": sha(encode(inputs)), "snapshot_hash": sha(encode(snapshot_hashes)),
                   "query_hash": None, "entity_map_hash": "unchanged_v1_mock",
                   "relation_map_hash": "unchanged", "config_hash": sha(encode(
                       {"policy": POLICY, "n": args.n_snapshots, "min_days": MIN_SNAPSHOT_DAYS})),
                   "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "pyarrow": pa.__version__},
        "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
        "artifacts": {"hashes": {**{f"snapshots/{k}": v for k, v in snapshot_hashes.items()},
                                 **{f"tables/{k}": v for k, v in table_hashes.items()}}},
        "access": {"state": "dev", "timestamp": started.isoformat(),
                   "actor_or_runner": "scripts/build_snapshots_v3_2.py"},
    }
    validate_manifest(manifest)
    write_json(out / "run_manifest.json", manifest)
    print(json.dumps({"output": str(out), "status": report["status"], "checks": checks,
                      "counts": report["counts"]}, indent=2, ensure_ascii=False))
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
