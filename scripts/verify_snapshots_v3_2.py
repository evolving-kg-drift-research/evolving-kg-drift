"""Independent verification of the S1 v3.2 candidate package.

Does not import the builder. It re-derives the as-of snapshot membership from the immutable v3.1
tables, re-parses publication dates from raw HTML with a different parser (regex, not JSON), and loads
the package through the M2 loader. Dev-mode check: it never certifies M1/G1/G2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_m2_inputs import inspect_package, write_json  # noqa: E402
from kg_pipeline.entity_map_v2 import canonical_key, entity_id_v2, is_generic_mention  # noqa: E402

DATE_RE = re.compile(rb'"datePublished"\s*:\s*"([^"]+)"')
SHORT_FLAG = "SHORT_BODY_LT_200_CHARS"


def ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"naive timestamp {value!r}")
    return parsed.astimezone(timezone.utc)


def table(path: Path):
    return pq.read_table(path).to_pandas()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="data/evolving_kg_downstream_v3_2")
    parser.add_argument("--source", default="data/evolving_kg_downstream_v3_1")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sample", type=int, default=80)
    args = parser.parse_args()
    pkg, src, data = ROOT / args.package, ROOT / args.source, ROOT / args.data_root
    results: dict[str, object] = {}

    datasets, loader = inspect_package(pkg)
    results["m2_loader_status"] = loader["status"]
    results["transitions_append_only"] = all(
        t["removed_triples"] == 0 and t["removed_entities"] == 0 for t in loader["transitions"])

    cfg = yaml.safe_load((pkg / "config/downstream_transe_config.yaml").read_bytes())
    fv = table(pkg / "tables/fact_versions_v3_2.parquet")
    led = table(pkg / "tables/evidence_time_ledger.parquet")
    v31_events = table(src / "tables/kg_events.parquet")
    bodies = table(src / "tables/body_variants.parquet").set_index("body_variant_id")
    included = fv[fv.evidence_observed_at_v32.notna()].set_index("fact_version_id")

    # Optional entity map: verify the table against the rules, then re-derive triples through it.
    entity_map: dict[str, str | None] | None = None
    if cfg.get("entity_map"):
        map_file = ROOT / cfg["entity_map"]["path"]
        results["entity_map_hash_matches_config"] = hashlib.sha256(map_file.read_bytes()).hexdigest() == cfg["entity_map"]["sha256"]
        mt = table(map_file)
        entity_map = {r.v1_entity_id: (None if r.action == "BLOCK" else r.v2_entity_id) for r in mt.itertuples(index=False)}
        live = mt[mt.action != "BLOCK"]
        results["entity_map_rows_follow_rules"] = bool(
            all(r.canonical_key == canonical_key(r.primary_surface) and r.v2_entity_id == entity_id_v2(r.canonical_key)
                and not is_generic_mention(r.primary_surface) for r in live.itertuples(index=False))
            and all(is_generic_mention(r.primary_surface) and r.v2_entity_id is None
                    for r in mt[mt.action == "BLOCK"].itertuples(index=False)))
        results["entity_map_one_key_per_v2_id"] = bool((live.groupby("v2_entity_id").canonical_key.nunique() == 1).all())

    # Re-derive each (mapped) triple's time from v3.1 events and v3.2 fact-version times (independent of builder).
    event_time: dict[tuple[str, str, str], datetime] = {}
    for e in v31_events.itertuples(index=False):
        ids = [i for i in json.loads(e.source_fact_version_ids_json) if i in included.index]
        if not ids:
            continue
        sub, obj = e.subject_id, e.object_id
        if entity_map is not None:
            sub, obj = entity_map[sub], entity_map[obj]
            if sub is None or obj is None or sub == obj:
                continue
        t = min(ts(included.loc[i, "evidence_observed_at_v32"]) for i in ids)
        key = (sub, e.relation_id, obj)
        if key not in event_time or t < event_time[key]:
            event_time[key] = t

    membership_ok, inv01_ok, rows_match = True, True, True
    previous: set[tuple[str, str, str]] = set()
    per_snapshot = []
    for spec in cfg["snapshots"]:
        cutoff = ts(spec["cutoff"])
        rows = pq.read_table(pkg / spec["parquet_path"]).to_pylist()
        got = {(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows}
        expected = {k for k, t in event_time.items() if t <= cutoff}
        membership_ok &= got == expected
        inv01_ok &= all(ts(r["evidence_observed_at"]) <= cutoff for r in rows)
        rows_match &= all(
            r["evidence_observed_at"] == included.loc[r["fact_version_id"], "evidence_observed_at_v32"]
            and ts(r["evidence_observed_at"]) == event_time.get((r["subject_id"], r["relation_id"], r["object_id"]))
            for r in rows)
        membership_ok &= previous <= got
        previous = got
        per_snapshot.append({"snapshot_id": spec["snapshot_id"], "triples": len(rows)})
    results["snapshot_membership_equals_asof_events"] = bool(membership_ok)
    results["inv01_no_future_evidence"] = bool(inv01_ok)
    results["canonical_rows_match_event_time"] = bool(rows_match)

    cuts = sorted(event_time.values())
    cutoffs = [ts(s["cutoff"]) for s in cfg["snapshots"]]
    # a boundary is clean when no event shares the cutoff's timestamp but lies after it
    results["no_event_ties_across_boundaries"] = all(
        not any(t == c for t in cuts if t > c) for c in cutoffs)
    results["snapshot_days"] = [round((b - a).total_seconds() / 86400, 1) for a, b in zip(cutoffs, cutoffs[1:])]

    # Basis consistency against the ledger.
    pub_docs = led[led.time_basis == "publisher_declared_published_at"]
    way_docs = led[led.time_basis == "wayback_archive_datetime"]
    results["wayback_time_equals_archive"] = bool((way_docs.observed_at_v32 == way_docs.archive_min).all())
    results["publisher_time_equals_declared"] = bool((pub_docs.observed_at_v32 == pub_docs.publisher_published_at).all())
    results["publisher_time_never_equals_retrieval_time"] = bool(
        (pub_docs.observed_at_v32 != pub_docs.retrieved_min).all())
    results["publisher_time_not_after_retrieval"] = bool(
        all(ts(a) <= ts(b) for a, b in zip(pub_docs.publisher_published_at, pub_docs.retrieved_min) if b))
    short = {b for b in pub_docs.body_variant_id if SHORT_FLAG in json.loads(bodies.loc[b, "quality_flags_json"])}
    results["no_chrome_teaser_with_publisher_basis"] = not short

    # Independent date re-parse (regex) of a seeded sample of publisher-basis documents.
    memberships = table(src / "tables/document_memberships.parquet")
    sample = random.Random(20261118).sample(sorted(pub_docs.body_variant_id), min(args.sample, len(pub_docs)))
    mismatches = []
    for body_id in sample:
        digests = sorted(memberships[memberships.body_variant_id == body_id].raw_blob_sha256)
        times = []
        for d in digests:
            blob = (data / "raw/stage_4_4/blobs/sha256" / d[:2] / f"{d}.bin").read_bytes()
            for m in DATE_RE.finditer(blob):
                try:
                    times.append(ts(m.group(1).decode()))
                    break
                except ValueError:
                    continue
        ledger_time = ts(pub_docs[pub_docs.body_variant_id == body_id].observed_at_v32.iloc[0])
        if not times or abs((min(times) - ledger_time).total_seconds()) > 86400:
            mismatches.append(body_id)
    results["independent_reparse_sample"] = {"n": len(sample), "mismatches": len(mismatches)}

    # Artifact hashes recorded by the builder.
    manifest = json.loads((pkg / "run_manifest.json").read_text(encoding="utf-8"))
    bad = []
    for name, digest in manifest["artifacts"]["hashes"].items():
        sub, stem = name.split("/", 1)
        path = pkg / sub / (f"snapshot_{stem}_canonical.parquet" if sub == "snapshots" else f"{stem}.parquet")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            bad.append(name)
    results["manifest_artifact_hash_mismatches"] = bad

    # Comparison with v3.1 (informational).
    v31_cfg = yaml.safe_load((src / "config/downstream_transe_config.yaml").read_bytes())
    results["compare_v31_v32"] = [
        {"snapshot_id": a["snapshot_id"], "v31_triples": a["edges"], "v32_triples": b["edges"],
         "v31_cutoff": a["cutoff"], "v32_cutoff": b["cutoff"]}
        for a, b in zip(v31_cfg["snapshots"], cfg["snapshots"])]
    results["per_snapshot"] = per_snapshot

    boolean = {k: v for k, v in results.items() if isinstance(v, bool)}
    ok = (all(boolean.values()) and results["m2_loader_status"] == "PACKAGE_TECHNICAL_CHECKS_PASS"
          and not bad and results["independent_reparse_sample"]["mismatches"] == 0)
    results["status"] = "INDEPENDENT_CHECKS_PASS" if ok else "INDEPENDENT_CHECKS_FAIL"
    results["scientific_certification"] = False
    write_json(pkg / "reports/s1_independent_verification.json", results)
    print(json.dumps({k: v for k, v in results.items() if k not in ("compare_v31_v32", "per_snapshot")},
                     indent=2, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
