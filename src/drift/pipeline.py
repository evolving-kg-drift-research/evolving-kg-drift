"""End-to-End Pipeline for TransE Training, Alignment, Null, and Drift Measurement.

Orchestrates:
  1. Synthetic or Canonical Snapshot ingestion via KGE Input Contract.
  2. Multi-seed TransE-L2 training across seeds [13, 37, 101].
  3. Validation of mapping consistency across all seeds within each snapshot.
  4. Same-snapshot empirical null estimation for retraining noise.
  5. Adjacent snapshot transitions:
       - Persistent anchor selection
       - Deterministic disjoint fit/holdout split
       - Centered Orthogonal Procrustes alignment
       - Raw temporal displacement
       - Signed raw excess
       - SED+ computation
  6. Generation and return of immutable artifact dictionaries.
"""

from __future__ import annotations

import itertools
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Sequence

from ..kge.checkpoint import KGECheckpoint
from ..kge.contract import SnapshotDataset
from ..kge.fixtures import create_synthetic_snapshots
from ..kge.trainer import train_multi_seed
from .anchors import AnchorSplit, deterministic_hash_split, select_persistent_anchors
from .metrics import TransitionDriftArtifact, compute_longitudinal_drift
from .null import EmpiricalNullArtifact, build_same_snapshot_empirical_null


class KGEDriftPipeline:
    """End-to-end coordinator for multi-seed KGE and representation drift."""

    def __init__(
        self,
        dimension: int = 32,
        seeds: Sequence[int] = (13, 37, 101),
        epochs: int = 25,
        fit_ratio: float = 0.6,
        epsilon: float = 1e-4,
        git_commit: str = "",
    ) -> None:
        self.dimension = dimension
        self.seeds = tuple(seeds)
        self.epochs = epochs
        self.fit_ratio = fit_ratio
        self.epsilon = epsilon
        self.git_commit = git_commit

    def run_on_snapshots(
        self,
        snapshots: dict[str, SnapshotDataset],
        output_dir: Optional[Path | str] = None,
    ) -> dict[str, Any]:
        """Runs the complete multi-snapshot, multi-seed pipeline.

        Args:
            snapshots: Dict mapping snapshot_id -> SnapshotDataset (e.g. {'S1': ds1, 'S2': ds2, 'S3': ds3}).
            output_dir: Optional directory to save serialized artifacts.

        Returns:
            Dict containing:
              - 'checkpoints': dict[snapshot_id, dict[seed, KGECheckpoint]]
              - 'null_artifacts': dict[snapshot_id, EmpiricalNullArtifact]
              - 'drift_artifacts': dict[transition_id, TransitionDriftArtifact]
        """
        snapshot_keys = sorted(snapshots.keys())  # Deterministic chronological order
        if len(snapshot_keys) < 2:
            raise ValueError("Pipeline requires at least 2 consecutive snapshots to measure drift.")

        # Derive seed pairs from self.seeds (all unique combinations)
        seed_pairs = tuple(
            (a, b) for a, b in itertools.combinations(sorted(self.seeds), 2)
        )

        all_checkpoints: dict[str, dict[int, KGECheckpoint]] = {}
        all_null_artifacts: dict[str, EmpiricalNullArtifact] = {}
        all_drift_artifacts: dict[str, TransitionDriftArtifact] = {}

        # 1. Train TransE on all seeds for each snapshot
        for s_id in snapshot_keys:
            ds = snapshots[s_id]
            ckpts = train_multi_seed(
                dataset=ds,
                seeds=self.seeds,
                dimension=self.dimension,
                epochs=self.epochs,
                git_commit=self.git_commit,
            )
            all_checkpoints[s_id] = ckpts

            # 2. Build same-snapshot empirical null
            null_art = build_same_snapshot_empirical_null(
                dataset=ds,
                checkpoints=ckpts,
                seed_pairs=seed_pairs,
                fit_ratio=self.fit_ratio,
            )
            all_null_artifacts[s_id] = null_art

        # 3. Compute longitudinal drift across consecutive snapshot transitions
        for i in range(len(snapshot_keys) - 1):
            s_prev_id = snapshot_keys[i]
            s_next_id = snapshot_keys[i + 1]
            t_id = f"{s_prev_id}->{s_next_id}"

            # We measure primary drift using the primary seed (seed 13)
            ckpt_prev = all_checkpoints[s_prev_id][self.seeds[0]]
            ckpt_next = all_checkpoints[s_next_id][self.seeds[0]]
            null_prev = all_null_artifacts[s_prev_id]

            drift_art = compute_longitudinal_drift(
                checkpoint_prev=ckpt_prev,
                checkpoint_next=ckpt_next,
                null_artifact=null_prev,
                fit_ratio=self.fit_ratio,
                epsilon=self.epsilon,
                transition_id=t_id,
            )
            all_drift_artifacts[t_id] = drift_art

        return {
            "checkpoints": all_checkpoints,
            "null_artifacts": all_null_artifacts,
            "drift_artifacts": all_drift_artifacts,
        }
