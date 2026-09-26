r"""Drift Measurement: Raw Displacement, Signed Excess, and SED+.

Calculates the three longitudinal representation drift quantities:
  1. Raw temporal displacement (Centered Procrustes Estimand):
       \delta^{time}_{e,g} = 1 - \cos((x_{e,t-1} - \mu_{prev}) Q, x_{e,t} - \mu_{next})
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
from .null import EmpiricalNullArtifact, compute_median
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
    git_commit: str = ""
    git_dirty: bool = False
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
    checkpoint_prev: KGECheckpoint | dict[int, KGECheckpoint],
    checkpoint_next: KGECheckpoint | dict[int, KGECheckpoint],
    null_artifact: EmpiricalNullArtifact,
    anchor_split: Optional[AnchorSplit] = None,
    fit_ratio: float = 0.6,
    epsilon: float = 1e-4,
    transition_id: str = "",
    git_commit: str = "",
    git_dirty: bool = False,
    min_bucket_samples: int = 5,
) -> TransitionDriftArtifact:
    """Computes cross-time Procrustes alignment, raw displacement, signed excess, and SED+.

    Supports single checkpoints or multi-seed checkpoint dicts (aggregating via 3-seed median, A20).
    Enforces Centered Procrustes estimand (A19), LTO null calibration (A22), and alignment gates (A24).

    Args:
        checkpoint_prev: KGE checkpoint(s) at time t-1.
        checkpoint_next: KGE checkpoint(s) at time t.
        null_artifact: Empirical null distribution (typically from pre-transition or post-transition).
        anchor_split: Optional pre-computed anchor split. If None, derived deterministically.
        fit_ratio: Ratio for anchor fit split.
        epsilon: Numerical guard for MAD denominator (locked prior to evaluation).
        transition_id: Label for this transition (e.g. 'S1->S2').
        min_bucket_samples: Minimum sample threshold for LTO null calibration.
    """
    if isinstance(checkpoint_prev, KGECheckpoint):
        ckpts_prev = {checkpoint_prev.provenance.seed: checkpoint_prev}
    else:
        ckpts_prev = dict(checkpoint_prev)

    if isinstance(checkpoint_next, KGECheckpoint):
        ckpts_next = {checkpoint_next.provenance.seed: checkpoint_next}
    else:
        ckpts_next = dict(checkpoint_next)

    common_seeds = sorted(set(ckpts_prev.keys()).intersection(set(ckpts_next.keys())))
    if not common_seeds:
        raise ValueError("No common seeds found between checkpoint_prev and checkpoint_next.")

    snap_prev = next(iter(ckpts_prev.values())).provenance.snapshot_id
    snap_next = next(iter(ckpts_next.values())).provenance.snapshot_id
    if not transition_id:
        transition_id = f"{snap_prev}->{snap_next}"

    # 1. Candidate anchors: persistent entities appearing in both endpoints across common seeds
    entity_sets = [
        set(ckpts_prev[s].entity_embeddings.keys()) & set(ckpts_next[s].entity_embeddings.keys())
        for s in common_seeds
    ]
    persistent = sorted(set.intersection(*entity_sets))
    if not persistent:
        raise ValueError(f"No common persistent entities found between {snap_prev} and {snap_next}.")

    # 2. Parallel seed alignments (A20: 3 parallel seed pairs 13->13, 37->37, 101->101)
    seed_alignments: dict[int, ProcrustesAlignmentResult] = {}
    seed_validities: dict[int, tuple[bool, str]] = {}
    entity_seed_displacements: dict[str, list[float]] = {e: [] for e in persistent}

    for s in common_seeds:
        if anchor_split is not None and len(common_seeds) == 1:
            split_s = anchor_split
        else:
            split_s = deterministic_hash_split(
                persistent,
                fit_ratio=fit_ratio,
                salt=f"cross_time_{transition_id}_seed_{s}",
            )

        res_s = align_embeddings_procrustes(
            ckpts_prev[s].entity_embeddings,
            ckpts_next[s].entity_embeddings,
            split_s,
            alignment_type="cross_time",
        )
        seed_alignments[s] = res_s
        seed_validities[s] = res_s.diagnostics.check_alignment_validity()

        # Centered Procrustes estimand (A19)
        aligned_prev_c = res_s.align_all_entities_centered(ckpts_prev[s].entity_embeddings)
        target_c = res_s.center_all_target_entities(ckpts_next[s].entity_embeddings)

        for e in persistent:
            disp_s = one_minus_cosine(aligned_prev_c[e], target_c[e])
            entity_seed_displacements[e].append(disp_s)

    # 3. Overall alignment validity check (A24)
    all_valid = all(v for v, _ in seed_validities.values())
    invalid_reason = ";".join(
        f"seed_{s}:{reason}" for s, (v, reason) in seed_validities.items() if not v
    )

    if len(common_seeds) == 1:
        primary_diag = asdict(seed_alignments[common_seeds[0]].diagnostics)
        alignment_hash = seed_alignments[common_seeds[0]].diagnostics.alignment_hash
        ckpt_prev_hash = ckpts_prev[common_seeds[0]].artifact_hash
        ckpt_next_hash = ckpts_next[common_seeds[0]].artifact_hash
    else:
        seed_diags = {s: asdict(res.diagnostics) for s, res in seed_alignments.items()}
        alignment_hash = hashlib.sha256(
            "".join(res.diagnostics.alignment_hash for res in seed_alignments.values()).encode("utf-8")
        ).hexdigest()
        primary_diag = {
            "seeds": seed_diags,
            "orthogonality_error": max(d["orthogonality_error"] for d in seed_diags.values()),
            "fit_residual": max(d["fit_residual"] for d in seed_diags.values()),
            "holdout_residual": max(d["holdout_residual"] for d in seed_diags.values()),
            "fit_holdout_gap": max(d["fit_holdout_gap"] for d in seed_diags.values()),
            "numerical_rank": min(d["numerical_rank"] for d in seed_diags.values()),
            "alignment_hash": alignment_hash,
        }
        ckpt_prev_hash = hashlib.sha256(
            "".join(ckpts_prev[s].artifact_hash for s in common_seeds).encode("utf-8")
        ).hexdigest()
        ckpt_next_hash = hashlib.sha256(
            "".join(ckpts_next[s].artifact_hash for s in common_seeds).encode("utf-8")
        ).hexdigest()

    # 4. Entity-level drift metrics for all persistent entities
    measurements: dict[str, EntityDriftMeasurement] = {}

    for e in persistent:
        # 4a. Raw temporal displacement: median across 3 parallel seeds (A20)
        disps = entity_seed_displacements[e]
        raw_disp = compute_median(disps) if len(disps) > 1 else disps[0]

        # 4b. Alignment diagnostics availability gate (A24)
        if not all_valid:
            bucket_id = null_artifact.entity_to_bucket.get(e, "UNKNOWN")
            signed_excess = raw_disp
            sed_plus = None
            null_med = float("nan")
            null_mad = float("nan")
            null_status = f"ALIGNMENT_UNAVAILABLE:{invalid_reason}"
        else:
            # 4c. LTO Null statistics lookup (A22)
            if hasattr(null_artifact, "get_entity_lto_null_stats"):
                b_stats = null_artifact.get_entity_lto_null_stats(e, min_bucket_samples=min_bucket_samples)
            else:
                b_stats = null_artifact.get_entity_null_stats(e)

            if b_stats is None:
                signed_excess = raw_disp
                sed_plus = None
                bucket_id = "UNKNOWN"
                null_med = float("nan")
                null_mad = float("nan")
                null_status = "NULL_UNAVAILABLE"
            elif b_stats.is_degenerate:
                bucket_id = b_stats.bucket_id
                null_med = b_stats.median
                null_mad = b_stats.mad
                signed_excess = raw_disp - null_med
                sed_plus = None
                null_status = f"DEGENERATE_NULL:{b_stats.degeneracy_reason}"
            else:
                bucket_id = b_stats.bucket_id
                null_med = b_stats.median
                null_mad = b_stats.mad
                scale = b_stats.robust_scale
                signed_excess = raw_disp - null_med
                pos_excess = max(0.0, signed_excess)
                sed_plus = pos_excess / (scale + epsilon)
                null_status = "VALID"

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
            alignment_hash=alignment_hash,
            checkpoint_prev_hash=ckpt_prev_hash,
            checkpoint_next_hash=ckpt_next_hash,
        )

    return TransitionDriftArtifact(
        transition_id=transition_id,
        snapshot_prev=snap_prev,
        snapshot_next=snap_next,
        alignment_diagnostics=primary_diag,
        measurements=measurements,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )
    )
