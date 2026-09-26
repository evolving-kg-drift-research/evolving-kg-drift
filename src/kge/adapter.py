"""Adapter bridging Data/KG pipeline snapshots with KGE and drift measurement."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import pyarrow.parquet as pq

from .contract import SnapshotDataset, Triple

logger = logging.getLogger(__name__)


def load_snapshot_from_parquet(
    parquet_path: Path,
    snapshot_id: str | None = None,
) -> SnapshotDataset:
    """Loads a SnapshotDataset from a canonical triples.parquet file."""
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Missing triples parquet file: {parquet_path}")

    sid = snapshot_id or parquet_path.parent.name
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

    return SnapshotDataset.create(snapshot_id=sid, triples=triples)


def load_snapshots_from_run(
    repo_root: Path,
    run_id: str,
    snapshot_ids: Sequence[str] | None = None,
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
            [p for p in snapshots_dir.iterdir() if p.is_dir() and (p / "triples.parquet").is_file()],
            key=lambda p: p.name,
        )

    for target in targets:
        triples_file = target / "triples.parquet"
        if triples_file.is_file():
            sid = target.name
            dataset = load_snapshot_from_parquet(triples_file, snapshot_id=sid)
            results[sid] = dataset
            logger.info("Loaded snapshot %s with %d triples, %d entities", sid, len(dataset.triples), len(dataset.entities))

    return results
