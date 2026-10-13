"""Read-only package review; never runs acquisition, producers, Neo4j or M2.

Embedded PASS reports are evidence to compare, never certification authority.
No archive extraction is performed; held-out payloads are never read.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import types
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode())


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def load_producer_snapshot(ref: str) -> tuple[Any, Any, dict[str, str]]:
    """Load only the two inspected pure domain modules, with an isolated name."""
    prefix = "_m1_package_audit_temporal"
    package = types.ModuleType(prefix)
    package.__path__ = []
    sys.modules[prefix] = package
    hashes = {}
    for name in ("schema", "snapshot"):
        path = f"src/temporal/{name}.py"
        source = git("show", f"{ref}:{path}")
        hashes[path] = digest(source)
        module = types.ModuleType(f"{prefix}.{name}")
        sys.modules[module.__name__] = module
        exec(compile(source, f"{ref}:{path}", "exec"), module.__dict__)
    return sys.modules[f"{prefix}.schema"].FactVersion, sys.modules[f"{prefix}.snapshot"].build_snapshot, hashes


def hydrate(row: dict[str, Any], fact_type: Any) -> Any:
    values = {k: v for k, v in row.items() if k != "schema_version"}
    for key in ("valid_from", "valid_to", "evidence_observed_at", "ingested_at_real"):
        if values.get(key) is not None:
            values[key] = datetime.fromisoformat(values[key])
    return fact_type(**values)


def inspect(package_path: Path, ref: str) -> dict[str, Any]:
    archive_bytes = package_path.read_bytes()
    result: dict[str, Any] = {
        "audit_mode": "read_only_package_and_pure_function_checks",
        "package": str(package_path), "package_sha256": digest(archive_bytes),
        "branch_ref": ref, "branch_commit": git("rev-parse", ref).decode().strip(),
        "reviewed_at_real": datetime.now(timezone.utc).isoformat(),
        "scientific_certification": "BLOCKED", "production_execution_performed": False,
        "neo4j_read_back_performed": False,
    }
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate archive entry names")
        if sum(entry.file_size for entry in entries) > 128 * 1024 * 1024:
            raise ValueError("Package exceeds this review's in-memory size limit")
        payloads = {}
        for entry in entries:
            path = PurePosixPath(entry.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or ":" in entry.filename:
                raise ValueError("Unsafe archive path")
            if "locked_test" in path.parts:
                raise ValueError("Held-out payload present; not read")
            if not entry.is_dir():
                payloads[entry.filename] = archive.read(entry)
    result["archive"] = {
        "entries": len(entries), "compressed_bytes": len(archive_bytes),
        "uncompressed_bytes": sum(e.file_size for e in entries), "crc_verified": True,
        "files": [{"path": n, "bytes": len(b), "sha256": digest(b)} for n, b in payloads.items()],
    }
    tables = {n: pq.read_table(pa.BufferReader(b)) for n, b in payloads.items() if n.endswith(".parquet")}
    result["parquet_inventory"] = {
        n: {"rows": t.num_rows, "fields": t.schema.names,
            "types": {f.name: str(f.type) for f in t.schema}} for n, t in tables.items()
    }
    integrity = json.loads(payloads["reports/snapshots_integrity_report.json"])
    parity = json.loads(payloads["reports/parity_report.json"])
    boundaries = yaml.safe_load(payloads["snapshot_boundaries.yaml"])
    downstream = yaml.safe_load(payloads["downstream_transe_config.yaml"])
    facts = tables["tables/fact_versions.parquet"].to_pylist()
    events = tables["tables/kg_events.parquet"].to_pylist()
    filters = tables["tables/filter_decisions.parquet"].to_pylist()
    fact_type, build_snapshot, code_hashes = load_producer_snapshot(ref)
    producer_facts = [hydrate(row, fact_type) for row in facts]
    result["producer_code_sha256"] = code_hashes
    result["snapshot_checks"] = []
    snapshot_rows = {}
    fields = [k for k in tables["snapshots/snapshot_T01.parquet"].schema.names if k != "schema_version"]
    by_fact = {r["fact_version_id"]: r for r in facts}
    for boundary in boundaries["boundaries"]:
        sid = boundary["snapshot_id"]
        path = f"snapshots/snapshot_{sid}.parquet"
        rows = tables[path].to_pylist()
        snapshot_rows[sid] = rows
        manifest = next(x for x in integrity["snapshots"] if x["snapshot_id"] == sid)
        pr = next(x for x in parity["snapshots"] if x["snapshot_id"] == sid)
        config = next(x for x in downstream["snapshots"] if x["snapshot_id"] == sid)
        cutoff = datetime.fromisoformat(boundary["cutoff"])
        nodes_path = f"neo4j_materialization/{sid}/nodes.csv"
        edges_path = f"neo4j_materialization/{sid}/relationships.csv"
        nodes = list(csv.DictReader(io.StringIO(payloads[nodes_path].decode("utf-8"))))
        edges = list(csv.DictReader(io.StringIO(payloads[edges_path].decode("utf-8"))))
        csv_fields = [":START_ID", ":END_ID", ":TYPE", "fact_version_id", "logical_fact_id",
                      "valid_from", "valid_to", "evidence_observed_at", "source_id"]
        parquet_fields = ["subject_id", "object_id", "relation_id", *csv_fields[3:]]
        expected_edges = Counter(tuple(str(r[k]) if r[k] is not None else "" for k in parquet_fields) for r in rows)
        actual_edges = Counter(tuple(e[k] for k in csv_fields) for e in edges)
        entities = {r[k] for r in rows for k in ("subject_id", "object_id")}
        rebuilt, rebuilt_hash = build_snapshot(producer_facts, cutoff)
        projected = [{k: r[k] for k in fields} for r in rows]
        expected_rows = [{k: (getattr(f, k).isoformat() if isinstance(getattr(f, k), datetime)
                             else getattr(f, k)) for k in fields} for f in rebuilt]
        unique_triples = {tuple(r[k] for k in ("subject_id", "relation_id", "object_id")) for r in rows}
        result["snapshot_checks"].append({
            "snapshot_id": sid, "cutoff": boundary["cutoff"], "rows": len(rows),
            "entities": len(entities), "unique_triples": len(unique_triples),
            "repeated_triple_rows": len(rows) - len(unique_triples),
            "physical_hash_matches_report": digest(payloads[path]) == manifest["physical_sha256"],
            "semantic_hash_matches_report": canonical_hash(projected) == manifest["semantic_sha256"],
            "producer_replay_hash_matches": rebuilt_hash == manifest["semantic_sha256"],
            "producer_replay_rows_match": projected == expected_rows,
            "report_and_config_counts_match": (manifest["row_count"] == pr["parquet_rows"] == config["edges"] == len(rows)
                                                and manifest["entity_count"] == pr["parquet_entities"] == config["entities"] == len(entities)),
            "cutoff_refs_match": boundary["cutoff"] == manifest["cutoff"] == pr["cutoff"] == config["cutoff"],
            "config_path_exists": config["parquet_path"] in payloads,
            "nodes_csv_hash_matches_report": digest(payloads[nodes_path]) == pr["nodes_csv_sha256"],
            "edges_csv_hash_matches_report": digest(payloads[edges_path]) == pr["relationships_csv_sha256"],
            "csv_node_set_and_count_match": {r["entity_id:ID"] for r in nodes} == entities and len(nodes) == len(entities),
            "csv_edge_multiset_with_temporal_metadata_matches": expected_edges == actual_edges,
            "future_evidence_violations": sum(datetime.fromisoformat(r["evidence_observed_at"]) > cutoff for r in rows),
            "validity_violations": sum(datetime.fromisoformat(r["valid_from"]) > cutoff or
                                       (r["valid_to"] is not None and cutoff >= datetime.fromisoformat(r["valid_to"])) for r in rows),
            "broken_fact_references": sum(r["fact_version_id"] not in by_fact for r in rows),
            "fact_projection_mismatches": sum(r["fact_version_id"] in by_fact and
                                             any(r[k] != by_fact[r["fact_version_id"]][k] for k in fields) for r in rows),
        })
    result["facts"] = {
        "rows": len(facts), "unique_fact_version_ids": len(by_fact),
        "unique_logical_facts": len({r["logical_fact_id"] for r in facts}),
        "unique_triples": len({(r["subject_id"], r["relation_id"], r["object_id"]) for r in facts}),
        "unique_sources": len({r["source_id"] for r in facts}),
        "revision_types": dict(Counter(r["revision_type"] for r in facts)),
        "supersedes_references": sum(r["supersedes_version_id"] is not None for r in facts),
        "entity_map_versions": dict(Counter(r["entity_map_version"] for r in facts)),
        "extractor_versions": dict(Counter(r["extractor_version"] for r in facts)),
        "source_url_schemes": dict(Counter(r["source_url"].split(":")[0] for r in facts)),
        "confidence_values": dict(Counter(str(r["confidence"]) for r in facts)),
        "invalid_span_shapes": sum(r["evidence_span_start"] < 0 or r["evidence_span_end"] <= r["evidence_span_start"] for r in facts),
        "invalid_hash_shapes": sum(re.fullmatch("[0-9a-f]{64}", r["evidence_text_hash"] or "") is None for r in facts),
        "valid_from_equals_evidence": sum(r["valid_from"] == r["evidence_observed_at"] for r in facts),
        "observed_after_registered_window": sum(datetime.fromisoformat(r["evidence_observed_at"]).date().isoformat() > "2026-08-31" for r in facts),
        "missing_clock_and_mapping_fields": [k for k in ("accepted_into_kg_at", "retrieved_at_real", "adjudicated_at_real",
                                                       "mapping_available_at", "evidence_time_basis", "evidence_time_confidence")
                                            if k not in tables["tables/fact_versions.parquet"].schema.names],
    }
    branch_contract = yaml.safe_load(git("show", f"{ref}:config/schema.yaml"))
    current_contract = yaml.safe_load(Path("config/schema.yaml").read_bytes())
    actual_fields = set(tables["tables/fact_versions.parquet"].schema.names) - {"schema_version"}
    result["fact_contract_drift"] = {}
    for label, contract in (("thu_huong_branch", branch_contract), ("current_branch", current_contract)):
        declared = set(contract["fact_versions"]["fields"])
        result["fact_contract_drift"][label] = {"missing_fields": sorted(declared - actual_fields),
                                                "undeclared_fields": sorted(actual_fields - declared)}
    ordered_events = sorted(events, key=lambda x: (x["effective_at"], x["event_id"]))
    supported_ids = [fid for e in events for fid in json.loads(e["source_fact_version_ids_json"])]
    boundary_base = {k: v for k, v in boundaries.items() if k != "boundary_hash"}
    changed_time = dict(boundary_base, created_at_real="2000-01-01T00:00:00+00:00")
    result["events_and_boundaries"] = {
        "events": len(events), "event_types": dict(Counter(e["event_type"] for e in events)),
        "supported_fact_ids": len(supported_ids), "unknown_supported_ids": len(set(supported_ids) - set(by_fact)),
        "facts_not_supported_by_events": len(set(by_fact) - set(supported_ids)),
        "boundary_hash_matches": canonical_hash(boundary_base) == boundaries["boundary_hash"],
        "changing_only_operational_time_changes_boundary_hash": canonical_hash(boundary_base) != canonical_hash(changed_time),
        "distinct_cutoffs": len({b["cutoff"] for b in boundaries["boundaries"]}),
        "cutoffs_outside_registered_window": [b["snapshot_id"] for b in boundaries["boundaries"]
                                              if datetime.fromisoformat(b["cutoff"]).date().isoformat() > "2026-08-31"],
        "quantile_slice_checks": [{"snapshot_id": b["snapshot_id"],
                                   "event_count_matches_slice": len(ordered_events[b["event_slice_indices"][0]:b["event_slice_indices"][1]]) == b["event_count"],
                                   "time_range_matches_slice": (ordered_events[b["event_slice_indices"][0]]["effective_at"] == b["interval_start"]
                                                                and ordered_events[b["event_slice_indices"][1]-1]["effective_at"] == b["cutoff"]),
                                   "ties_after_slice": sum(e["effective_at"] <= b["cutoff"] for e in ordered_events) - b["event_slice_indices"][1]}
                                  for b in boundaries["boundaries"]],
    }
    include = {r["body_variant_id"] for r in filters if r["decision"] == "include"}
    result["filters"] = {"rows": len(filters), "decisions": dict(Counter(r["decision"] for r in filters)),
                         "fact_sources_not_included": len({r["source_id"] for r in facts} - include)}
    anchors = tables["tables/anchor_candidates_prelock.parquet"].to_pylist()
    result["anchors"] = {"rows": len(anchors), "feasibility_status": dict(Counter(r["feasibility_status"] for r in anchors)),
                         "guide_column_feasibility_tier_present": "feasibility_tier" in tables["tables/anchor_candidates_prelock.parquet"].schema.names}
    result["guide_triple_columns_missing"] = sorted({"head_entity_id", "relation", "tail_entity_id"} - set(fields))
    missing = ["run_manifest.yaml", "pipeline_manifest.yaml", "environment_lock", "gates/gate_A.json",
               "reports/quality_gate_report.json", "tables/extracted_claims.parquet", "tables/claim_provenance.parquet",
               "tables/retrievals.parquet", "tables/document_memberships.parquet", "tables/body_variants.parquet",
               "tables/entity_mapping_versions.parquet", "tables/adjudication_decisions.parquet", "tables/transition_metadata.parquet"]
    result["missing_expected_evidence_paths"] = [p for p in missing if p not in payloads]
    result["upstream_evidence_not_supplied"] = ["immutable raw/body texts", "source-lock originals and approved amendment",
                                                "independent human gold", "G1/G2 certificates", "locked extractor cache",
                                                "Neo4j database read-back", "snapshot edge support/exclusions"]
    result["standalone_snapshot_manifests"] = [n for n in names if re.search(r"snapshot_T\d+_manifest\.yaml$", n)]
    result["parquet_sidecars"] = [n for n in names if ".parquet." in n]
    result["partial_lineage_samples"] = []
    for row in facts[:3]:
        result["partial_lineage_samples"].append({
            "fact_version_id": row["fact_version_id"], "source_id": row["source_id"], "source_url": row["source_url"],
            "evidence_text_hash": row["evidence_text_hash"], "span": [row["evidence_span_start"], row["evidence_span_end"]],
            "included_filter_decision_present": row["source_id"] in include,
            "snapshot_ids": [sid for sid, rows in snapshot_rows.items() if any(r["fact_version_id"] == row["fact_version_id"] for r in rows)],
            "source_to_evidence_verification": "BLOCKED: body, claims, memberships, retrievals and public source URL unavailable",
        })
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old = replace(producer_facts[0], fact_version_id="audit_old", logical_fact_id="audit_logical",
                  evidence_observed_at=cutoff - timedelta(days=10), valid_from=cutoff - timedelta(days=10),
                  valid_to=None, supersedes_version_id=None)
    future = replace(old, fact_version_id="audit_future", evidence_observed_at=cutoff - timedelta(days=1),
                     valid_from=cutoff + timedelta(days=10), supersedes_version_id=old.fact_version_id, revision_type="correction")
    active, _ = build_snapshot([old, future], cutoff)
    result["producer_future_effective_regression"] = {
        "expected_ids": [old.fact_version_id], "actual_ids": [f.fact_version_id for f in active],
        "status": "PASS" if [f.fact_version_id for f in active] == [old.fact_version_id] else "FAIL",
        "verification_tier": "TESTED: fixture only",
    }
    quality_code = git("show", f"{ref}:src/kg_pipeline/quality.py")
    tree = ast.parse(quality_code)
    evaluator = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "evaluate_quality")
    runner = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_quality_gate")
    namespace = {"Any": Any, "Iterable": Iterable, "FactVersion": fact_type}
    exec(compile(ast.Module(body=[evaluator], type_ignores=[]), "reviewed_quality_function", "exec"), namespace)
    result["quality_gate_regression"] = {
        "empty_gold_one_fact": namespace["evaluate_quality"](producer_facts[:1], []),
        "runner_calls_evaluator": any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "evaluate_quality" for n in ast.walk(runner)),
        "verification_tier": "TESTED: fixture only; scientific gold absent",
    }
    result["snapshot_embedded_manifest_missing_bindings"] = [k for k in ("git_commit", "dirty_state", "config_hash", "input_hashes", "mapping_hash", "boundary_hash")
                                                           if k not in integrity["snapshots"][0]]
    result["downstream_missing_hash_bindings"] = [k for k in ("physical_sha256", "semantic_sha256", "manifest_hash")
                                                if k not in downstream["snapshots"][0]]
    result["package_unchanged_after_review"] = digest(package_path.read_bytes()) == result["package_sha256"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Use a new report path; previous review evidence is preserved")
    report = inspect(args.zip, args.ref)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({"report": str(args.report), "package_sha256": report["package_sha256"],
                      "files": report["archive"]["entries"], "snapshots": len(report["snapshot_checks"]),
                      "facts": report["facts"], "scientific_certification": report["scientific_certification"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
