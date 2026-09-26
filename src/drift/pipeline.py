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
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    from ..kge.checkpoint import KGECheckpoint
    from ..kge.contract import SnapshotDataset
    from ..kge.trainer import train_multi_seed
except (ImportError, ValueError):
    from kge.checkpoint import KGECheckpoint
    from kge.contract import SnapshotDataset
    from kge.trainer import train_multi_seed
from .metrics import TransitionDriftArtifact, compute_longitudinal_drift
from .null import (
    EmpiricalNullArtifact,
    build_same_snapshot_empirical_null,
    build_transition_empirical_null,
)


class KGEDriftPipeline:
    """End-to-end coordinator for multi-seed KGE and representation drift."""

    def __init__(
        self,
        dimension: int = 32,
        seeds: Sequence[int] = (13, 37, 101),
        epochs: int = 25,
        fit_ratio: float = 0.6,
        epsilon: float = 1e-4,
        min_bucket_samples: int = 5,
        bin_edges: Sequence[int] = (3, 6),
        git_commit: str = "",
        git_dirty: bool | None = None,
    ) -> None:
        self.dimension = dimension
        self.seeds = tuple(seeds)
        self.epochs = epochs
        self.fit_ratio = fit_ratio
        self.epsilon = epsilon
        self.min_bucket_samples = min_bucket_samples
        self.bin_edges = tuple(bin_edges)
        if not git_commit:
            try:
                from ..kg_pipeline.hashing import get_git_info
            except (ImportError, ValueError):
                from kg_pipeline.hashing import get_git_info
            resolved_commit, resolved_dirty = get_git_info()
            self.git_commit = resolved_commit
            self.git_dirty = resolved_dirty if git_dirty is None else git_dirty
        else:
            self.git_commit = git_commit
            self.git_dirty = git_dirty if git_dirty is not None else False

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        git_commit: str = "",
        git_dirty: bool | None = None,
    ) -> KGEDriftPipeline:
        """Constructs pipeline instance with parameters bound to resolved protocol config (A25)."""
        res_cfg = config.get("resolved_config", {})
        drift_cfg = config.get("drift") or res_cfg.get("drift", {})
        kge_cfg = config.get("kge") or res_cfg.get("kge", {})

        dimension = int(kge_cfg.get("dimension") or drift_cfg.get("dimension", 32))
        seeds = kge_cfg.get("seeds") or drift_cfg.get("seeds", [13, 37, 101])
        epochs = int(kge_cfg.get("epochs") or drift_cfg.get("epochs", 25))
        fit_ratio = float(drift_cfg.get("fit_ratio", 0.6))
        epsilon = float(drift_cfg.get("epsilon", 1e-4))
        min_bucket_samples = int(drift_cfg.get("min_bucket_samples", 5))
        bin_edges = tuple(drift_cfg.get("bin_edges", (3, 6)))

        return cls(
            dimension=dimension,
            seeds=seeds,
            epochs=epochs,
            fit_ratio=fit_ratio,
            epsilon=epsilon,
            min_bucket_samples=min_bucket_samples,
            bin_edges=bin_edges,
            git_commit=git_commit,
            git_dirty=git_dirty,
        )

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
        all_transition_null_artifacts: dict[str, EmpiricalNullArtifact] = {}
        all_drift_artifacts: dict[str, TransitionDriftArtifact] = {}

        # 1. Train TransE on all seeds for each snapshot
        out_ckpt_dir = Path(output_dir) / "checkpoints" if output_dir else None
        for s_id in snapshot_keys:
            ds = snapshots[s_id]
            ckpts = train_multi_seed(
                dataset=ds,
                seeds=self.seeds,
                dimension=self.dimension,
                epochs=self.epochs,
                output_dir=out_ckpt_dir,
                git_commit=self.git_commit,
                git_dirty=self.git_dirty,
            )
            all_checkpoints[s_id] = ckpts

            # 2. Build same-snapshot empirical null
            null_art = build_same_snapshot_empirical_null(
                dataset=ds,
                checkpoints=ckpts,
                seed_pairs=seed_pairs,
                bin_edges=self.bin_edges,
                min_bucket_samples=self.min_bucket_samples,
                fit_ratio=self.fit_ratio,
                git_commit=self.git_commit,
                git_dirty=self.git_dirty,
            )
            all_null_artifacts[s_id] = null_art

        # 3. Compute longitudinal drift across consecutive snapshot transitions
        for i in range(len(snapshot_keys) - 1):
            s_prev_id = snapshot_keys[i]
            s_next_id = snapshot_keys[i + 1]
            t_id = f"{s_prev_id}->{s_next_id}"

            # Transition null: pool 6 seed-pair observations (3 from S_prev + 3 from S_next) (A21)
            null_transition = build_transition_empirical_null(
                dataset_prev=snapshots[s_prev_id],
                checkpoints_prev=all_checkpoints[s_prev_id],
                dataset_next=snapshots[s_next_id],
                checkpoints_next=all_checkpoints[s_next_id],
                seed_pairs=seed_pairs,
                bin_edges=self.bin_edges,
                min_bucket_samples=self.min_bucket_samples,
                fit_ratio=self.fit_ratio,
                git_commit=self.git_commit,
                git_dirty=self.git_dirty,
            )
            all_transition_null_artifacts[t_id] = null_transition

            # Measure temporal drift across 3 parallel seed pairs (13->13, 37->37, 101->101)
            # aggregated via median of 3 seeds (A20)
            drift_art = compute_longitudinal_drift(
                checkpoint_prev=all_checkpoints[s_prev_id],
                checkpoint_next=all_checkpoints[s_next_id],
                null_artifact=null_transition,
                fit_ratio=self.fit_ratio,
                epsilon=self.epsilon,
                min_bucket_samples=self.min_bucket_samples,
                transition_id=t_id,
                git_commit=self.git_commit,
                git_dirty=self.git_dirty,
            )
            all_drift_artifacts[t_id] = drift_art

        return {
            "checkpoints": all_checkpoints,
            "null_artifacts": all_null_artifacts,
            "transition_null_artifacts": all_transition_null_artifacts,
            "drift_artifacts": all_drift_artifacts,
        }
