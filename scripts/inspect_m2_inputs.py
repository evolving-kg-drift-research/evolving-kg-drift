"""Bounded external-package inspection, authorized separately from M1 certification.

This script checks bytes and structure only. It does not change the certified
M2 adapter, infer historical identity, or run training/drift.
"""
from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kge.contract import SnapshotDataset  # noqa: E402

PACKAGE = Path("data/KG_lan2/evolving_kg_downstream_v3")


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                      allow_nan=False).encode("utf-8")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(encode(value))


def safe_file(root: Path, relative: str | Path) -> Path:
    requested = Path(relative)
    if requested.is_absolute() or "locked_test" in {p.lower() for p in requested.parts}:
        raise ValueError("Input path must be relative and outside locked_test")
    path = (root / requested).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Input path escapes its registered root")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Cutoff must be an explicit ISO timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Cutoff requires a timezone")
    return result


def inspect_snapshot(
    package: Path, spec: dict[str, Any],
) -> tuple[SnapshotDataset, dict[str, Any], dict[str, str]]:
    sid = spec["snapshot_id"]
    if not isinstance(sid, str) or not re.fullmatch(r"T\d{2}", sid):
        raise ValueError("Unsupported external snapshot identifier")
    path = safe_file(package, spec["parquet_path"])
    sidecar_path = safe_file(package, str(path.relative_to(package)) + ".manifest.json")
    manifest_path = safe_file(package, f"snapshots/snapshot_{sid}_manifest.yaml")
    payload = path.read_bytes()
    sidecar_payload = sidecar_path.read_bytes()
    manifest_payload = manifest_path.read_bytes()
    sidecar = json.loads(sidecar_payload)
    manifest = yaml.safe_load(manifest_payload)
    digest = sha(payload)
    if (sidecar["physical_sha256_computed_at_real"] != digest
            or manifest["canonical_physical_sha256"] != digest):
        raise ValueError(f"{sid}: physical SHA-256 mismatch")
    table = pq.read_table(pa.BufferReader(payload))
    if not {"subject_id", "relation_id", "object_id"}.issubset(table.column_names):
        raise ValueError(f"{sid}: unexpected canonical triple schema")
    rows = table.to_pylist()
    semantic = json.dumps({"table_name": sidecar["table_name"],
                           "contract_version": sidecar["contract_version"], "rows": rows},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if sidecar["semantic_sha256"] != sha(semantic) or sidecar["row_count"] != len(rows):
        raise ValueError(f"{sid}: sidecar content mismatch")
    triples = [(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows]
    if not triples or any(not isinstance(v, str) or not v.strip() for t in triples for v in t):
        raise ValueError(f"{sid}: nonempty string IDs required")
    if len(triples) != len(set(triples)):
        raise ValueError(f"{sid}: duplicate canonical triple")
    dataset = SnapshotDataset.create(sid, triples)
    if (manifest["snapshot_id"] != sid
            or timestamp(manifest["cutoff"]) != timestamp(spec["cutoff"])
            or manifest["canonical_triple_count"] != len(triples)
            or spec["edges"] != len(triples)
            or manifest["entity_count"] != len(dataset.entities)
            or spec["entities"] != len(dataset.entities)):
        raise ValueError(f"{sid}: manifest/config identity, cutoff, or count mismatch")
    hashes = {p.relative_to(package).as_posix(): sha(b) for p, b in (
        (path, payload), (sidecar_path, sidecar_payload), (manifest_path, manifest_payload))}
    record = {"snapshot_id": sid, "cutoff": spec["cutoff"], "triples": len(triples),
              "entities": len(dataset.entities), "relations": len(dataset.relations),
              "physical_sha256": digest, "snapshot_hash": dataset.snapshot_hash,
              "entity_map_hash": dataset.compute_mapping_hash(),
              "relation_map_hash": sha(json.dumps(dataset.get_relation_mapping(), sort_keys=True).encode()),
              "degree_histogram": dict(sorted(Counter(m.degree for m in dataset.entity_metadata.values()).items())),
              "self_loops": sum(h == t for h, _, t in triples),
              "source_columns": table.column_names}
    return dataset, record, hashes


def inspect_package(package: Path) -> tuple[dict[str, SnapshotDataset], dict[str, Any]]:
    package = package.resolve()
    config_path = safe_file(package, "config/downstream_transe_config.yaml")
    boundary_path = safe_file(package, "snapshot_boundaries.yaml")
    config = yaml.safe_load(config_path.read_bytes())
    boundaries = yaml.safe_load(boundary_path.read_bytes())
    specs = config["snapshots"]
    if (not specs or config["total_snapshots"] != len(specs)
            or boundaries["n_snapshots"] != len(specs)
            or len(boundaries["boundaries"]) != len(specs)):
        raise ValueError("Missing or inconsistent snapshot counts")
    ids = [s["snapshot_id"] for s in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate snapshot IDs")
    cutoffs = [timestamp(s["cutoff"]) for s in specs]
    if any(a >= b for a, b in zip(cutoffs, cutoffs[1:])):
        raise ValueError("Snapshot cutoffs must be strictly increasing")
    for spec, boundary in zip(specs, boundaries["boundaries"]):
        if (spec["snapshot_id"] != boundary["snapshot_id"]
                or timestamp(spec["cutoff"]) != timestamp(boundary["cutoff"])):
            raise ValueError("Snapshot boundaries disagree with input config")
    hashes = {p.relative_to(package).as_posix(): sha(p.read_bytes())
              for p in (config_path, boundary_path)}
    datasets, records = {}, []
    for spec in specs:
        dataset, record, snapshot_hashes = inspect_snapshot(package, spec)
        datasets[dataset.snapshot_id] = dataset
        records.append(record)
        hashes.update(snapshot_hashes)
    transitions = []
    for prev, nxt in zip(ids, ids[1:]):
        a, b = datasets[prev], datasets[nxt]
        persistent = sorted(set(a.entities) & set(b.entities))
        edges_a = {t.to_tuple() for t in a.triples}
        edges_b = {t.to_tuple() for t in b.triples}
        transitions.append({"transition_id": f"{prev}->{nxt}", "persistent_entities": len(persistent),
                            "persistent_entity_hash": sha(encode(persistent)),
                            "new_entities": len(set(b.entities) - set(a.entities)),
                            "removed_entities": len(set(a.entities) - set(b.entities)),
                            "added_triples": len(edges_b - edges_a), "removed_triples": len(edges_a - edges_b),
                            "pretransition_degree_histogram": dict(sorted(Counter(
                                a.entity_metadata[e].degree for e in persistent).items()))})
    report = {"status": "PACKAGE_TECHNICAL_CHECKS_PASS", "scientific_certification": False,
              "snapshots": records, "transitions": transitions, "input_hashes": hashes,
              "historical_identity_and_temporal_validity": "NOT_CERTIFIED",
              "m1_gate_policy": "Excluded from this user-authorized external-package inspection"}
    return datasets, report


def provenance() -> dict[str, Any]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    return {"commit": commit, "dirty_state": bool(status.strip())}


def validate_manifest(manifest: dict[str, Any]) -> None:
    schema = yaml.safe_load((ROOT / "configs/schemas/experiment_manifest.schema.yaml").read_bytes())
    if any(k not in manifest for k in schema["required"]):
        raise ValueError("Experiment manifest missing required fields")
    for field, rules in schema["fields"].items():
        if any(k not in manifest.get(field, {}) for k in rules.get("required", [])):
            raise ValueError(f"Manifest missing nested fields: {field}")
    if manifest["access"]["state"] not in schema["fields"]["access"]["allowed_state"]:
        raise ValueError("Invalid access state")


def main() -> None:
    package = ROOT / PACKAGE
    datasets, report = inspect_package(package)
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_preflight" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    hashes = {f"{PACKAGE.as_posix()}/{p}": h for p, h in report["input_hashes"].items()}
    supplemental = []
    for name in ("body_variants", "extracted_claims", "fact_versions", "kg_events"):
        relative = Path("data/transe_fact_check_package") / f"{name}.parquet"
        path = safe_file(ROOT, relative)
        hashes[relative.as_posix()] = sha(path.read_bytes())
        metadata = pq.ParquetFile(path)
        supplemental.append({"path": relative.as_posix(), "sha256": hashes[relative.as_posix()],
                             "rows": metadata.metadata.num_rows, "columns": metadata.schema_arrow.names,
                             "scope": "inventory only; not used for KGE training"})
    report["supplemental_tables"] = supplemental
    report["input_hashes"] = hashes
    report["unresolved_m2_protocol_fields"] = [
        "kge.dimension", "alignment.fit_count", "alignment.holdout_count",
        "drift.bucket_merge_policy", "drift.mad_epsilon"]
    write_json(out / "report.json", report)
    write_json(out / "mappings.json", {s: {"entities": d.get_entity_mapping(),
                                          "relations": d.get_relation_mapping()}
                                        for s, d in datasets.items()})
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError("Input changed during inspection")
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft",
                "mode": "m2_external_input_inspection", "scientific_certification": False,
                "git": provenance(), "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)),
                           "snapshot_hash": sha(encode({s: d.snapshot_hash for s, d in datasets.items()})),
                           "query_hash": None,
                           "entity_map_hash": sha(encode({s: d.compute_mapping_hash() for s, d in datasets.items()})),
                           "relation_map_hash": sha(encode({s: d.get_relation_mapping() for s, d in datasets.items()})),
                           "config_hash": hashes[f"{PACKAGE.as_posix()}/config/downstream_transe_config.yaml"],
                           "hashes": hashes, "code_hash": sha(Path(__file__).read_bytes())},
                "environment": {"python": platform.python_version(), "os": platform.platform(),
                                "pyarrow": pa.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.name: sha(p.read_bytes()) for p in out.iterdir()}},
                "access": {"state": "dev", "timestamp": now.isoformat(),
                           "actor_or_runner": "scripts/inspect_m2_inputs.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), "snapshots": len(datasets),
                      "transitions": len(report["transitions"]), "status": report["status"]}, indent=2))


if __name__ == "__main__":
    main()
