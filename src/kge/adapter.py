"""Adapter bridging Data/KG pipeline snapshots with KGE and drift measurement."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Sequence

import pyarrow.parquet as pq
import yaml

from .contract import SnapshotDataset, Triple

logger = logging.getLogger(__name__)


def load_snapshot_from_parquet(
    parquet_path: Path,
    snapshot_id: str | None = None,
    *,
    verify_manifest: bool = True,
) -> SnapshotDataset:
    """Loads a SnapshotDataset from a canonical triples.parquet or snapshot_edges.parquet file.

    When verify_manifest is True, verifies physical sidecar hashes and SnapshotManifest integrity.
    """
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Missing triples parquet file: {parquet_path}")

    sid = snapshot_id or parquet_path.parent.name

    # 1. Verify physical sha256 sidecar if present and verification requested
    if verify_manifest:
        sidecar_path = parquet_path.with_name(f"{parquet_path.name}.sha256")
        if sidecar_path.is_file():
            expected_sha = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
            actual_sha = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise ValueError(
                    f"Parquet physical SHA-256 sidecar mismatch for {parquet_path.name}: "
                    f"expected {expected_sha}, got {actual_sha}"
                )

    table = pq.read_table(parquet_path)
    triples: list[Triple] = []

    sub_col = "subject" if "subject" in table.column_names else "subject_id"
    rel_col = "relation" if "relation" in table.column_names else "relation_id"
    obj_col = "object" if "object" in table.column_names else "object_id"

    for row in table.to_pylist():
        triples.append(
            Triple(
                subject_id=str(row[sub_col]),
                relation_id=str(row[rel_col]),
                object_id=str(row[obj_col]),
            )
        )

    dataset = SnapshotDataset.create(snapshot_id=sid, triples=triples)

    # 2. Verify snapshot manifest if present and verification requested
    if verify_manifest:
        manifest_path = parquet_path.parent / "snapshot_manifest.yaml"
        if not manifest_path.is_file():
            manifest_path = parquet_path.parent / "snapshot_manifest.json"

        if manifest_path.is_file():
            try:
                manifest_text = manifest_path.read_text(encoding="utf-8")
                manifest_data: dict[str, Any] = (
                    yaml.safe_load(manifest_text)
                    if manifest_path.suffix in (".yaml", ".yml")
                    else json.loads(manifest_text)
                )
            except Exception as e:
                raise ValueError(f"Failed to read snapshot manifest at {manifest_path}: {e}") from e

            # Check graph semantic hash
            exp_graph_hash = manifest_data.get("graph_semantic_hash")
            if exp_graph_hash and dataset.snapshot_hash != exp_graph_hash:
                raise ValueError(
                    f"Snapshot manifest graph_semantic_hash mismatch: "
                    f"expected {exp_graph_hash}, got {dataset.snapshot_hash}"
                )

            # Check snapshot manifest internal hash
            exp_manifest_hash = manifest_data.get("snapshot_manifest_hash")
            if exp_manifest_hash:
                semantic = {
                    k: v
                    for k, v in manifest_data.items()
                    if k not in ("created_at_real", "snapshot_manifest_hash")
                }
                computed_manifest_hash = hashlib.sha256(
                    json.dumps(semantic, sort_keys=True).encode("utf-8")
                ).hexdigest()
                if computed_manifest_hash != exp_manifest_hash:
                    raise ValueError(
                        f"Snapshot manifest internal hash mismatch: "
                        f"expected {exp_manifest_hash}, got {computed_manifest_hash}"
                    )

    return dataset


def load_snapshots_from_run(
    repo_root: Path,
    run_id: str,
    snapshot_ids: Sequence[str] | None = None,
    *,
    verify_manifest: bool = True,
) -> dict[str, SnapshotDataset]:
    """Loads all snapshot datasets generated in a pipeline run.

    Returns:
        dict[str, SnapshotDataset] ordered by snapshot_id.
    """
    run_dir = repo_root / "runs" / run_id
    snapshots_dir = run_dir / "snapshots"

    if not snapshots_dir.is_dir():
        raise FileNotFoundError(f"No snapshots directory found in run: {snapshots_dir}")

    results: dict[str, SnapshotDataset] = {}

    if snapshot_ids:
        targets = [snapshots_dir / sid for sid in snapshot_ids]
    else:
        targets = sorted(
            [
                p
                for p in snapshots_dir.iterdir()
                if p.is_dir()
                and ((p / "snapshot_edges.parquet").is_file() or (p / "triples.parquet").is_file())
            ],
            key=lambda p: p.name,
        )

    for target in targets:
        triples_file = target / "snapshot_edges.parquet"
        if not triples_file.is_file():
            triples_file = target / "triples.parquet"

        if triples_file.is_file():
            sid = target.name
            dataset = load_snapshot_from_parquet(
                triples_file, snapshot_id=sid, verify_manifest=verify_manifest
            )
            results[sid] = dataset
            logger.info(
                "Loaded snapshot %s with %d triples, %d entities",
                sid,
                len(dataset.triples),
                len(dataset.entities),
            )

    return results
