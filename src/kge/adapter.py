"""Public M2 loaders: canonical artifact checks plus scientific certification."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Sequence

from kg_pipeline.canonical_validation import (
    _load_snapshot_from_parquet as _read_canonical_parquet,
    validate_canonical_snapshots,
)
from .contract import SnapshotDataset


def _load_snapshot_from_parquet(
    parquet_path: Path, snapshot_id: str | None = None, *, verify_manifest: bool = True,
) -> SnapshotDataset:
    """Compatibility diagnostic only; public callers must use the certified loader."""
    canonical = _read_canonical_parquet(parquet_path, snapshot_id, verify_manifest=verify_manifest)
    return SnapshotDataset.create(canonical.snapshot_id, canonical.triples)


def _require_artifact_backed_gate(
    repo_root: Path,
    run_id: str,
    gate: str,
    report: dict[str, Any],
    run_manifest: dict[str, Any],
) -> None:
    from kg_pipeline.hashing import sha256_json
    from kg_pipeline.run import get_run_dir

    semantic = {
        key: value for key, value in report.items()
        if key not in {"evaluated_at_real", "semantic_sha256"}
    }
    report_hash = report.get("semantic_sha256")
    if (
        report.get("status") != "PASS"
        or report.get("scope") != "scientific"
        or report.get("gate") != gate
        or report.get("run_id") != run_id
        or report.get("run_manifest_semantic_sha256") != run_manifest.get("semantic_sha256")
        or type(report.get("evaluated_count")) is not int
        or report["evaluated_count"] <= 0
        or not isinstance(report.get("checks"), list)
        or not report["checks"]
        or any(not isinstance(check, dict) or check.get("status") != "PASS" for check in report["checks"])
        or not isinstance(report_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", report_hash)
        or report_hash != sha256_json(semantic)
    ):
        raise PermissionError(f"M2 requires a valid artifact-backed {gate} PASS certificate for run {run_id}")

    report_dir = get_run_dir(repo_root, run_id) / "gates" / gate
    if not report_dir.is_dir() or not any(
        path.is_file() and json.loads(path.read_text(encoding="utf-8")) == report
        for path in report_dir.glob("*.json")
    ):
        raise PermissionError(f"M2 requires the verified {gate} PASS certificate artifact for run {run_id}")


def load_snapshot_from_parquet(
    parquet_path: Path,
    snapshot_id: str | None = None,
    *,
    repo_root: Path | None = None,
    run_id: str | None = None,
    verify_manifest: bool = True,
) -> SnapshotDataset:
    """Load one M2 snapshot only after validating its run, lineage, and gates."""
    if not verify_manifest:
        raise ValueError("M2 snapshot loading requires verified manifests")
    if repo_root is None or not run_id:
        raise PermissionError(
            "Standalone Parquet loading is not a certified M2 handoff; provide repo_root and run_id"
        )

    sid = snapshot_id or parquet_path.parent.name
    from kg_pipeline.run import get_run_dir

    expected_path = get_run_dir(repo_root, run_id) / "snapshots" / sid / "snapshot_edges.parquet"
    if parquet_path.resolve() != expected_path.resolve():
        raise ValueError(f"M2 requested path is not the canonical snapshot in run {run_id}: {parquet_path}")
    return load_snapshots_from_run(repo_root, run_id, [sid], verify_manifest=True)[sid]


def load_snapshots_from_run(
    repo_root: Path,
    run_id: str,
    snapshot_ids: Sequence[str] | None = None,
    *,
    verify_manifest: bool = True,
) -> dict[str, SnapshotDataset]:
    """M2 handoff never exposes an option to bypass scientific gates."""
    if not verify_manifest:
        raise ValueError("M2 run loading requires verified manifests")
    from kg_pipeline.gates import evaluate_scientific_gate
    from kg_pipeline.run import load_run_manifest

    canonical = validate_canonical_snapshots(repo_root, run_id, snapshot_ids)
    run_manifest = load_run_manifest(repo_root, run_id)
    results = {
        sid: SnapshotDataset.create(sid, snapshot.triples)
        for sid, snapshot in canonical.items()
    }
    gate_reports = [
        evaluate_scientific_gate(repo_root, run_id, gate)
        for gate in ("G1", "G2")
    ]
    if any(report.get("status") != "PASS" for report in gate_reports):
        raise PermissionError("M2 requires artifact-backed G1 and G2 PASS certificates")
    for gate, report in zip(("G1", "G2"), gate_reports, strict=True):
        _require_artifact_backed_gate(repo_root, run_id, gate, report, run_manifest)

    return results
