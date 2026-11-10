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
from kg_pipeline.experiment_manifest import validate_manifest as validate_experiment_manifest  # noqa: E402

# The historical verifiers use this path when checking their original receipts.
PACKAGE = Path("data/KG_lan2/evolving_kg_downstream_v3")
ACTIVE_PACKAGE = Path("data/evolving_kg_downstream_v3_1")
RELEASE_ID = "evolving_kg_downstream_v3.1"


def require_current_package(root: Path, relative: Path) -> Path:
    package = root.resolve() / ACTIVE_PACKAGE
    if relative != ACTIVE_PACKAGE or package.resolve() != package:
        raise ValueError("Chỉ gói canonical V3.1 được dùng cho lần chạy mới")
    return package


def block_legacy_v3_execution() -> None:
    raise PermissionError("Đường chạy V3 đã ngừng sử dụng. Lần chạy mới cần thiết kế V3.1 được đăng ký.")


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
    # Historical fixture runners retain schema-v1 compatibility. New writers use strict=True.
    validate_experiment_manifest(manifest, strict=False)


def main() -> None:
    package = require_current_package(ROOT, ACTIVE_PACKAGE)
    release_path = safe_file(package, "release_manifest.json")
    release_payload = release_path.read_bytes()
    release = json.loads(release_payload)
    datasets, report = inspect_package(package)
    release_hashes = {item["path"]: item["sha256"] for item in release["artifacts"]}
    if (release["release_id"] != RELEASE_ID or release["snapshot_count"] != len(datasets)
            or any(release_hashes.get(path) != digest for path, digest in report["input_hashes"].items())):
        raise ValueError("Đầu vào không khớp bản kê phát hành V3.1")
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_preflight" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    hashes = {f"{ACTIVE_PACKAGE.as_posix()}/{p}": h for p, h in report["input_hashes"].items()}
    hashes[f"{ACTIVE_PACKAGE.as_posix()}/release_manifest.json"] = sha(release_payload)
    report["release_id"] = RELEASE_ID
    supplemental = []
    for name in ("body_variants", "extracted_claims", "fact_versions", "kg_events"):
        package_relative = f"tables/{name}.parquet"
        relative = ACTIVE_PACKAGE / package_relative
        path = safe_file(ROOT, relative)
        hashes[relative.as_posix()] = sha(path.read_bytes())
        if hashes[relative.as_posix()] != release_hashes.get(package_relative):
            raise ValueError(f"Bảng bổ trợ không khớp bản kê V3.1: {relative}")
        metadata = pq.ParquetFile(path)
        supplemental.append({"path": relative.as_posix(), "sha256": hashes[relative.as_posix()],
                             "rows": metadata.metadata.num_rows, "columns": metadata.schema_arrow.names,
                             "scope": "inventory only; not used for KGE training"})
    report["supplemental_tables"] = supplemental
    report["input_hashes"] = hashes
    report["unresolved_m2_protocol_fields"] = [
        "kge.dimension", "alignment.fit_count", "alignment.holdout_count",
        "drift.bucket_merge_policy", "drift.mad_epsilon"]
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError("Input changed during inspection")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "report.json", report)
    write_json(out / "mappings.json", {s: {"entities": d.get_entity_mapping(),
                                          "relations": d.get_relation_mapping()}
                                        for s, d in datasets.items()})
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft",
                "mode": "m2_external_input_inspection", "scientific_certification": False,
                "git": provenance(), "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)),
                           "snapshot_hash": sha(encode({s: d.snapshot_hash for s, d in datasets.items()})),
                           "query_hash": None,
                           "entity_map_hash": sha(encode({s: d.compute_mapping_hash() for s, d in datasets.items()})),
                           "relation_map_hash": sha(encode({s: d.get_relation_mapping() for s, d in datasets.items()})),
                           "config_hash": hashes[f"{ACTIVE_PACKAGE.as_posix()}/config/downstream_transe_config.yaml"],
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
