"""Same-Snapshot Cross-Seed Empirical Null Distribution.

Estimates retraining noise within the same snapshot across seeds [13, 37, 101]
using pairwise Centered Orthogonal Procrustes alignment.

Features:
  - Conditional bucketing by degree/frequency
  - Sparse bucket detection and deterministic adjacency merge
  - Median and MAD (1.4826 * MAD)
  - Degenerate null detection (zero MAD or insufficient sample size)
"""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass
from typing import Sequence

try:
    from ..kge.checkpoint import KGECheckpoint
    from ..kge.contract import EntityMetadata, SnapshotDataset
    from ..kge.math_utils import one_minus_cosine
except (ImportError, ValueError):
    from kge.checkpoint import KGECheckpoint
    from kge.contract import EntityMetadata, SnapshotDataset
    from kge.math_utils import one_minus_cosine
from .anchors import deterministic_hash_split
from .procrustes import align_embeddings_procrustes


def compute_median(values: Sequence[float]) -> float:
    """Computes sample median deterministically."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    if n % 2 == 1:
        return sorted_v[mid]
    return (sorted_v[mid - 1] + sorted_v[mid]) / 2.0


def compute_mad(values: Sequence[float]) -> float:
    """Computes Median Absolute Deviation (MAD): median(|x - median(x)|)."""
    if not values:
        return 0.0
    med = compute_median(values)
    deviations = [abs(x - med) for x in values]
    return compute_median(deviations)


def compute_robust_scale(values: Sequence[float], gaussian_factor: float = 1.4826) -> float:
    """Returns Gaussian-referenced robust scale estimate: 1.4826 * MAD."""
    return gaussian_factor * compute_mad(values)


@dataclass
class ConditionalBucketStats:
    """Null distribution statistics for a specific structural bucket."""

    bucket_id: str
    feature_range: tuple[int, int]
    entity_count: int
    observation_count: int
    median: float
    mad: float
    robust_scale: float
    is_degenerate: bool
    degeneracy_reason: str = ""


@dataclass
class EmpiricalNullArtifact:
    """Artifact containing entity cross-seed displacements and bucketed statistics."""

    snapshot_id: str
    snapshot_hash: str
    seed_pairs: list[tuple[int, int]]
    entity_displacements: dict[str, list[float]]
    bucket_stats: dict[str, ConditionalBucketStats]
    entity_to_bucket: dict[str, str]
    git_commit: str = ""
    git_dirty: bool = False
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_hash:
            self.artifact_hash = self.compute_artifact_hash()

    def compute_artifact_hash(self) -> str:
        payload = {
            "snapshot_id": self.snapshot_id,
            "snapshot_hash": self.snapshot_hash,
            "seed_pairs": self.seed_pairs,
            "bucket_stats": {
                b: {
                    "median": round(s.median, 7),
                    "mad": round(s.mad, 7),
                    "is_degenerate": s.is_degenerate,
                    "count": s.observation_count,
                }
                for b, s in sorted(self.bucket_stats.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get_entity_null_stats(self, entity_id: str) -> ConditionalBucketStats | None:
        """Returns null stats for entity, or None if entity has no bucket assignment."""
        bucket_id = self.entity_to_bucket.get(entity_id)
        if bucket_id is None or bucket_id not in self.bucket_stats:
            return None
        return self.bucket_stats[bucket_id]

    def get_entity_lto_null_stats(
        self,
        entity_id: str,
        min_bucket_samples: int = 5,
    ) -> ConditionalBucketStats | None:
        """Returns Leave-Target-Out (LTO) null distribution statistics for entity_id (A22).

        Excludes all noise displacement observations belonging to entity_id from its reference bucket.
        """
        bucket_id = self.entity_to_bucket.get(entity_id)
        if bucket_id is None or bucket_id not in self.bucket_stats:
            return None

        # Exclude observations of entity_id from the bucket's observation pool
        bucket_ents = [e for e, b in self.entity_to_bucket.items() if b == bucket_id]
        lto_obs: list[float] = []
        for other_e in bucket_ents:
            if other_e != entity_id:
                lto_obs.extend(self.entity_displacements.get(other_e, []))

        count = len(lto_obs)
        if count == 0:
            return ConditionalBucketStats(
                bucket_id=bucket_id,
                feature_range=(0, 0),
                entity_count=0,
                observation_count=0,
                median=0.0,
                mad=0.0,
                robust_scale=0.0,
                is_degenerate=True,
                degeneracy_reason="LTO_EMPTY_BUCKET",
            )

        med = compute_median(lto_obs)
        mad = compute_mad(lto_obs)
        scale = 1.4826 * mad
        is_deg = (mad < 1e-12) or (count < min_bucket_samples)
        reason = ""
        if count < min_bucket_samples:
            reason = "INSUFFICIENT_LTO_SAMPLES"
        elif mad < 1e-12:
            reason = "ZERO_MAD"

        return ConditionalBucketStats(
            bucket_id=bucket_id,
            feature_range=(0, 999),
            entity_count=len(bucket_ents) - 1,
            observation_count=count,
            median=med,
            mad=mad,
            robust_scale=scale,
            is_degenerate=is_deg,
            degeneracy_reason=reason,
        )


def assign_bucket(
    degree: int,
    bin_edges: Sequence[int] = (3, 6),
) -> str:
    """Assigns entity degree to a deterministic bucket label.

    Default bins:
      - 'low': degree < 3
      - 'medium': 3 <= degree < 6
      - 'high': degree >= 6
    """
    if degree < bin_edges[0]:
        return "low"
    elif degree < bin_edges[1]:
        return "medium"
    else:
        return "high"


def _compute_snapshot_seed_pair_displacements(
    dataset: SnapshotDataset,
    checkpoints: dict[int, KGECheckpoint],
    seed_pairs: Sequence[tuple[int, int]],
    fit_ratio: float = 0.6,
) -> dict[str, list[float]]:
    """Computes pairwise cross-seed Centered Procrustes displacements within a single snapshot."""
    entity_displacements: dict[str, list[float]] = {e: [] for e in dataset.entities}
    for sA, sB in seed_pairs:
        if sA not in checkpoints or sB not in checkpoints:
            raise KeyError(f"Seed pair ({sA}, {sB}) missing from available checkpoints.")

        ckpt_A = checkpoints[sA]
        ckpt_B = checkpoints[sB]

        common_entities = sorted(
            set(ckpt_A.entity_embeddings.keys()).intersection(set(ckpt_B.entity_embeddings.keys()))
        )
        anchor_split = deterministic_hash_split(
            common_entities,
            fit_ratio=fit_ratio,
            salt=f"null_split_{dataset.snapshot_id}_{sA}_{sB}",
        )

        alignment_res = align_embeddings_procrustes(
            ckpt_A.entity_embeddings,
            ckpt_B.entity_embeddings,
            anchor_split,
            alignment_type="same_snapshot_cross_seed",
        )

        aligned_A_centered = alignment_res.align_all_entities_centered(ckpt_A.entity_embeddings)
        target_B_centered = alignment_res.center_all_target_entities(ckpt_B.entity_embeddings)
        for e in common_entities:
            disp = one_minus_cosine(aligned_A_centered[e], target_B_centered[e])
            entity_displacements[e].append(disp)

    return entity_displacements


def _bucket_and_merge_observations(
    entities: Sequence[str],
    entity_metadata: dict[str, EntityMetadata],
    entity_displacements: dict[str, list[float]],
    bin_edges: Sequence[int] = (3, 6),
    min_bucket_samples: int = 5,
) -> tuple[dict[str, ConditionalBucketStats], dict[str, str]]:
    """Groups observations into degree buckets and strictly merges sparse adjacent buckets."""
    entity_to_bucket: dict[str, str] = {}
    bucket_entities: dict[str, list[str]] = {"low": [], "medium": [], "high": []}

    for e in entities:
        degree = entity_metadata[e].degree if e in entity_metadata else 1
        b = assign_bucket(degree, bin_edges=bin_edges)
        entity_to_bucket[e] = b
        bucket_entities[b].append(e)

    bucket_order = ["low", "medium", "high"]

    class _ActiveInterval:
        def __init__(self, start_idx: int, end_idx: int, ents: list[str], obs: list[float]) -> None:
            self.start_idx = start_idx
            self.end_idx = end_idx
            self.entities = ents
            self.observations = obs

        @property
        def name(self) -> str:
            return "+".join(bucket_order[i] for i in range(self.start_idx, self.end_idx + 1))

    active_intervals: list[_ActiveInterval] = []
    for idx, b_name in enumerate(bucket_order):
        ents = bucket_entities[b_name]
        obs: list[float] = []
        for e in ents:
            obs.extend(entity_displacements.get(e, []))
        active_intervals.append(_ActiveInterval(idx, idx, list(ents), obs))

    # Sparse bucket detection & deterministic STRICT ADJACENT merge (A23)
    changed = True
    while changed and len(active_intervals) > 1:
        changed = False
        for k, current in enumerate(active_intervals):
            obs_count = len(current.observations)
            if 0 < obs_count < min_bucket_samples:
                left_neighbor = active_intervals[k - 1] if k > 0 else None
                right_neighbor = active_intervals[k + 1] if k < len(active_intervals) - 1 else None

                target_neighbor: _ActiveInterval
                if left_neighbor is not None and right_neighbor is not None:
                    if len(right_neighbor.observations) > len(left_neighbor.observations):
                        target_neighbor = right_neighbor
                    else:
                        target_neighbor = left_neighbor
                elif left_neighbor is not None:
                    target_neighbor = left_neighbor
                elif right_neighbor is not None:
                    target_neighbor = right_neighbor
                else:
                    break

                new_start = min(current.start_idx, target_neighbor.start_idx)
                new_end = max(current.end_idx, target_neighbor.end_idx)
                merged_ents = current.entities + target_neighbor.entities
                merged_obs = current.observations + target_neighbor.observations
                merged_interval = _ActiveInterval(new_start, new_end, merged_ents, merged_obs)

                idx_to_remove = [k, active_intervals.index(target_neighbor)]
                first_idx = min(idx_to_remove)
                second_idx = max(idx_to_remove)
                active_intervals.pop(second_idx)
                active_intervals.pop(first_idx)
                active_intervals.insert(first_idx, merged_interval)

                merged_name = merged_interval.name
                for e in merged_ents:
                    entity_to_bucket[e] = merged_name

                changed = True
                break

    bucket_observations = {interval.name: interval.observations for interval in active_intervals}

    bucket_stats: dict[str, ConditionalBucketStats] = {}
    for b_id, obs in bucket_observations.items():
        count = len(obs)
        if count == 0:
            stats = ConditionalBucketStats(
                bucket_id=b_id,
                feature_range=(0, 0),
                entity_count=0,
                observation_count=0,
                median=0.0,
                mad=0.0,
                robust_scale=0.0,
                is_degenerate=True,
                degeneracy_reason="EMPTY_BUCKET",
            )
        else:
            med = compute_median(obs)
            mad = compute_mad(obs)
            scale = 1.4826 * mad
            is_deg = (mad < 1e-12) or (count < min_bucket_samples)
            reason = ""
            if mad < 1e-12:
                reason = "ZERO_MAD"
            elif count < min_bucket_samples:
                reason = "INSUFFICIENT_SAMPLES"

            stats = ConditionalBucketStats(
                bucket_id=b_id,
                feature_range=(0, 999),
                entity_count=sum(1 for e, b in entity_to_bucket.items() if b == b_id),
                observation_count=count,
                median=med,
                mad=mad,
                robust_scale=scale,
                is_degenerate=is_deg,
                degeneracy_reason=reason,
            )
        bucket_stats[b_id] = stats

    return bucket_stats, entity_to_bucket


def build_same_snapshot_empirical_null(
    dataset: SnapshotDataset,
    checkpoints: dict[int, KGECheckpoint],
    seed_pairs: Sequence[tuple[int, int]] = ((13, 37), (13, 101), (37, 101)),
    bin_edges: Sequence[int] = (3, 6),
    min_bucket_samples: int = 5,
    fit_ratio: float = 0.6,
    git_commit: str = "",
    git_dirty: bool = False,
) -> EmpiricalNullArtifact:
    """Constructs same-snapshot cross-seed empirical null across specified seed pairs."""
    entity_displacements = _compute_snapshot_seed_pair_displacements(
        dataset=dataset,
        checkpoints=checkpoints,
        seed_pairs=seed_pairs,
        fit_ratio=fit_ratio,
    )

    empty_entities = [e for e in dataset.entities if len(entity_displacements[e]) == 0]
    if empty_entities:
        warnings.warn(
            f"Empirical null: {len(empty_entities)} entities in dataset have no "
            f"displacement observations: {empty_entities[:5]}...",
            stacklevel=2,
        )

    bucket_stats, entity_to_bucket = _bucket_and_merge_observations(
        entities=dataset.entities,
        entity_metadata=dataset.entity_metadata,
        entity_displacements=entity_displacements,
        bin_edges=bin_edges,
        min_bucket_samples=min_bucket_samples,
    )

    return EmpiricalNullArtifact(
        snapshot_id=dataset.snapshot_id,
        snapshot_hash=dataset.snapshot_hash,
        seed_pairs=list(seed_pairs),
        entity_displacements=entity_displacements,
        bucket_stats=bucket_stats,
        entity_to_bucket=entity_to_bucket,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )


def build_transition_empirical_null(
    dataset_prev: SnapshotDataset,
    checkpoints_prev: dict[int, KGECheckpoint],
    dataset_next: SnapshotDataset,
    checkpoints_next: dict[int, KGECheckpoint],
    seed_pairs: Sequence[tuple[int, int]] = ((13, 37), (13, 101), (37, 101)),
    bin_edges: Sequence[int] = (3, 6),
    min_bucket_samples: int = 5,
    fit_ratio: float = 0.6,
    git_commit: str = "",
    git_dirty: bool = False,
) -> EmpiricalNullArtifact:
    r"""Constructs 6-pair transition empirical null pooling S_prev and S_next (A21).

    Pools 3 within-snapshot cross-seed pairs from S_prev and 3 within-snapshot
    cross-seed pairs from S_next, giving 6 total noise observations per persistent entity.
    """
    disps_prev = _compute_snapshot_seed_pair_displacements(
        dataset=dataset_prev,
        checkpoints=checkpoints_prev,
        seed_pairs=seed_pairs,
        fit_ratio=fit_ratio,
    )
    disps_next = _compute_snapshot_seed_pair_displacements(
        dataset=dataset_next,
        checkpoints=checkpoints_next,
        seed_pairs=seed_pairs,
        fit_ratio=fit_ratio,
    )

    # Persistent entities in transition
    persistent_entities = sorted(set(dataset_prev.entities).intersection(set(dataset_next.entities)))
    pooled_displacements: dict[str, list[float]] = {}
    for e in persistent_entities:
        pooled_displacements[e] = disps_prev.get(e, []) + disps_next.get(e, [])

    # Conditioning features: degree from dataset_prev (pre-transition)
    entity_metadata = {e: dataset_prev.entity_metadata[e] for e in persistent_entities if e in dataset_prev.entity_metadata}

    bucket_stats, entity_to_bucket = _bucket_and_merge_observations(
        entities=persistent_entities,
        entity_metadata=entity_metadata,
        entity_displacements=pooled_displacements,
        bin_edges=bin_edges,
        min_bucket_samples=min_bucket_samples,
    )

    # 6 seed pairs pooled (3 from prev, 3 from next)
    pooled_seed_pairs = list(seed_pairs) + list(seed_pairs)
    transition_id = f"{dataset_prev.snapshot_id}->{dataset_next.snapshot_id}"
    transition_hash = hashlib.sha256(
        f"{dataset_prev.snapshot_hash}_{dataset_next.snapshot_hash}".encode("utf-8")
    ).hexdigest()

    return EmpiricalNullArtifact(
        snapshot_id=transition_id,
        snapshot_hash=transition_hash,
        seed_pairs=pooled_seed_pairs,
        entity_displacements=pooled_displacements,
        bucket_stats=bucket_stats,
        entity_to_bucket=entity_to_bucket,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )
