r"""Drift Measurement: Raw Displacement, Signed Excess, and SED+.

Calculates the three longitudinal representation drift quantities:
  1. Raw temporal displacement:
       \delta^{time}_{e,g} = 1 - \cos(x'_{e,t-1}, x_{e,t})
  2. Signed raw excess (retaining negative values):
       r_{e,g} = \delta^{time}_{e,g} - median(N_{b(e,g),g})
  3. Positive-part standardized drift (SED+):
       SED^+_{e,g} = \frac{\max(0, r_{e,g})}{1.4826 \cdot MAD(N_{b(e,g),g}) + \epsilon}

If the empirical null bucket is degenerate (zero MAD or insufficient sample support),
SED+ is marked unavailable (None) rather than artificially amplified via epsilon.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Optional, Sequence

try:
    from ..kge.checkpoint import KGECheckpoint
    from ..kge.math_utils import one_minus_cosine
except (ImportError, ValueError):
    from kge.checkpoint import KGECheckpoint
    from kge.math_utils import one_minus_cosine
from .anchors import AnchorSplit, deterministic_hash_split, select_persistent_anchors
from .null import EmpiricalNullArtifact
from .procrustes import ProcrustesAlignmentResult, align_embeddings_procrustes


@dataclass(frozen=True)
class EntityDriftMeasurement:
    """Complete drift measurement record for a single entity across a transition."""

    entity_id: str
    transition_id: str
    snapshot_prev: str
    snapshot_next: str
    raw_displacement: float
    signed_excess: float
    sed_plus: Optional[float]  # None if null is degenerate / unavailable
    null_bucket_id: str
    null_median: float
    null_mad: float
    null_status: str  # 'VALID', 'DEGENERATE_NULL', 'NULL_UNAVAILABLE'
    alignment_hash: str
    checkpoint_prev_hash: str
    checkpoint_next_hash: str


@dataclass
class TransitionDriftArtifact:
    """Immutable transition-level drift artifact holding entity measurements and diagnostics."""

    transition_id: str
    snapshot_prev: str
    snapshot_next: str
    alignment_diagnostics: dict[str, Any]
    measurements: dict[str, EntityDriftMeasurement]
    artifact_hash: str = ""

    def __post_init__(self) -> None:
        if not self.artifact_hash:
            self.artifact_hash = self.compute_artifact_hash()

    def compute_artifact_hash(self) -> str:
        payload = {
            "transition_id": self.transition_id,
            "snapshot_prev": self.snapshot_prev,
            "snapshot_next": self.snapshot_next,
            "alignment_hash": self.alignment_diagnostics.get("alignment_hash", ""),
            "measurements": {
                e: {
                    "raw": round(m.raw_displacement, 7),
                    "signed": round(m.signed_excess, 7),
                    "sed_plus": round(m.sed_plus, 7) if m.sed_plus is not None else None,
                    "null_status": m.null_status,
                }
                for e, m in sorted(self.measurements.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get_measurement(self, entity_id: str) -> EntityDriftMeasurement:
        if entity_id not in self.measurements:
            raise KeyError(f"Entity '{entity_id}' not measured in transition {self.transition_id}")
        return self.measurements[entity_id]


def compute_longitudinal_drift(
    checkpoint_prev: KGECheckpoint,
    checkpoint_next: KGECheckpoint,
    null_artifact: EmpiricalNullArtifact,
    anchor_split: Optional[AnchorSplit] = None,
    fit_ratio: float = 0.6,
    epsilon: float = 1e-4,
    transition_id: str = "",
) -> TransitionDriftArtifact:
    """Computes cross-time Procrustes alignment, raw displacement, signed excess, and SED+.

    Args:
        checkpoint_prev: KGE checkpoint at time t-1.
        checkpoint_next: KGE checkpoint at time t.
        null_artifact: Empirical null distribution (typically from pre-transition or post-transition).
        anchor_split: Optional pre-computed anchor split. If None, derived deterministically.
        fit_ratio: Ratio for anchor fit split.
        epsilon: Numerical guard for MAD denominator (locked prior to evaluation).
        transition_id: Label for this transition (e.g. 'S1->S2').
    """
    snap_prev = checkpoint_prev.provenance.snapshot_id
    snap_next = checkpoint_next.provenance.snapshot_id
    if not transition_id:
        transition_id = f"{snap_prev}->{snap_next}"

    # 1. Candidate anchors: persistent entities appearing in both endpoints
    prev_entities = list(checkpoint_prev.entity_embeddings.keys())
    next_entities = list(checkpoint_next.entity_embeddings.keys())
    persistent = select_persistent_anchors(prev_entities, next_entities)

    if not persistent:
        raise ValueError(f"No common persistent entities found between {snap_prev} and {snap_next}.")

    if anchor_split is None:
        anchor_split = deterministic_hash_split(
            persistent,
            fit_ratio=fit_ratio,
            salt=f"cross_time_{transition_id}",
        )

    # 2. Centered Orthogonal Procrustes alignment
    alignment_result = align_embeddings_procrustes(
        checkpoint_prev.entity_embeddings,
        checkpoint_next.entity_embeddings,
        anchor_split,
        alignment_type="cross_time",
    )

    aligned_prev = alignment_result.align_all_entities(checkpoint_prev.entity_embeddings)

    # 3. Entity-level drift metrics for all persistent entities
    measurements: dict[str, EntityDriftMeasurement] = {}

    for e in persistent:
        v_prev_aligned = aligned_prev[e]
        v_next = checkpoint_next.entity_embeddings[e]

        # 3a. Raw temporal displacement: 1 - cos(x'_{e,t-1}, x_{e,t})
        raw_disp = one_minus_cosine(v_prev_aligned, v_next)

        # 3b. Null statistics lookup
        if e in null_artifact.entity_to_bucket:
            bucket_id = null_artifact.entity_to_bucket[e]
            b_stats = null_artifact.bucket_stats[bucket_id]

            null_med = b_stats.median
            null_mad = b_stats.mad
            scale = b_stats.robust_scale

            # 3c. Signed raw excess (MUST preserve negative values!)
            signed_excess = raw_disp - null_med

            # 3d. SED+
            if b_stats.is_degenerate:
                sed_plus = None
                null_status = f"DEGENERATE_NULL:{b_stats.degeneracy_reason}"
            else:
                pos_excess = max(0.0, signed_excess)
                sed_plus = pos_excess / (scale + epsilon)
                null_status = "VALID"
        else:
            # Entity has no null bucket (e.g. missing metadata or not in null artifact)
            # signed_excess is raw displacement minus 0 (no calibration available),
            # explicitly marked as NULL_UNAVAILABLE. SED+ is None.
            signed_excess = raw_disp  # uncalibrated: no null baseline to subtract
            sed_plus = None
            bucket_id = "UNKNOWN"
            null_med = float("nan")  # explicit: no null median available
            null_mad = float("nan")  # explicit: no null MAD available
            null_status = "NULL_UNAVAILABLE"

        measurements[e] = EntityDriftMeasurement(
            entity_id=e,
            transition_id=transition_id,
            snapshot_prev=snap_prev,
            snapshot_next=snap_next,
            raw_displacement=raw_disp,
            signed_excess=signed_excess,
            sed_plus=sed_plus,
            null_bucket_id=bucket_id,
            null_median=null_med,
            null_mad=null_mad,
            null_status=null_status,
            alignment_hash=alignment_result.diagnostics.alignment_hash,
            checkpoint_prev_hash=checkpoint_prev.artifact_hash,
            checkpoint_next_hash=checkpoint_next.artifact_hash,
        )

    return TransitionDriftArtifact(
        transition_id=transition_id,
        snapshot_prev=snap_prev,
        snapshot_next=snap_next,
        alignment_diagnostics=asdict(alignment_result.diagnostics),
        measurements=measurements,
    )
