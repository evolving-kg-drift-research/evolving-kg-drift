"""Longitudinal centered displacement and calibration from immutable saved artifacts."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from kge.checkpoint import KGECheckpoint
from kge.math_utils import l2_norm, one_minus_cosine

from .null import compute_median

ARTIFACT_DRIFT_VERSION = "saved_alignment_longitudinal_drift_v1"
SEEDS = (13, 37, 101)


def saved_temporal_observations(
    transition: str, entities: Sequence[str], endpoints: tuple[str, str],
    alignments: Mapping[int, tuple[dict[str, Any], str]],
    checkpoints: Mapping[tuple[str, int], KGECheckpoint], centered_norm_floor: float,
) -> list[dict[str, Any]]:
    if (set(alignments) != set(SEEDS) or not entities or len(set(entities)) != len(entities)
            or any(not isinstance(e, str) or not e.strip() for e in entities)
            or len(set(endpoints)) != 2 or transition != "->".join(endpoints)
            or not math.isfinite(centered_norm_floor) or centered_norm_floor <= 0):
        raise ValueError("Temporal displacement requires persistent entities and exactly three parallel seeds")
    rows = []
    prev, nxt = endpoints
    for seed in SEEDS:
        record, digest = alignments[seed]
        if (record["available"] is not True or record["unavailable_reason"]
                or record["alignment_type"] != "cross_time" or record["transition_id"] != transition
                or record["source_snapshot"] != prev or record["target_snapshot"] != nxt
                or record["source_seed"] != seed or record["target_seed"] != seed
                or len(digest) != 64):
            raise ValueError("Temporal alignment unavailable or parallel-seed identity mismatch")
        if (prev, seed) not in checkpoints or (nxt, seed) not in checkpoints:
            raise ValueError("Missing temporal checkpoint seed")
        source, target = checkpoints[prev, seed], checkpoints[nxt, seed]
        dimension = record["dimension"]
        for cp, sid, field in ((source, prev, "source_checkpoint_semantic_hash"),
                               (target, nxt, "target_checkpoint_semantic_hash")):
            cp.verify_finite()
            if (cp.provenance.snapshot_id != sid or cp.provenance.seed != seed
                    or cp.provenance.dimension != dimension or cp.artifact_hash != record[field]):
                raise ValueError("Temporal checkpoint identity/dimension/hash mismatch")
        q, mu_s, mu_t = record["Q"], record["source_mean"], record["target_mean"]
        if (len(q) != dimension or any(len(v) != dimension for v in q)
                or len(mu_s) != dimension or len(mu_t) != dimension
                or not all(math.isfinite(v) for row in [*q, mu_s, mu_t] for v in row)):
            raise ValueError("Invalid saved temporal transformation")
        for entity in sorted(entities):
            if entity not in source.entity_embeddings or entity not in target.entity_embeddings:
                raise ValueError("Missing persistent temporal entity")
            x, y = source.entity_embeddings[entity], target.entity_embeddings[entity]
            if len(x) != dimension or len(y) != dimension:
                raise ValueError("Temporal vector dimension mismatch")
            xc, yc = [x[i] - mu_s[i] for i in range(dimension)], [y[i] - mu_t[i] for i in range(dimension)]
            rotated = [sum(xc[i] * q[i][j] for i in range(dimension)) for j in range(dimension)]
            if l2_norm(rotated) < centered_norm_floor or l2_norm(yc) < centered_norm_floor:
                raise ValueError("Undefined centered temporal cosine")
            displacement = one_minus_cosine(rotated, yc)
            if not math.isfinite(displacement) or not 0 <= displacement <= 2:
                raise ValueError("Invalid temporal displacement")
            rows.append({"transition_id": transition, "entity_id": entity, "seed": seed,
                         "source_snapshot": prev, "target_snapshot": nxt, "temporal_displacement": displacement,
                         "alignment_sha256": digest, "anchor_plan_hash": record["anchor_plan_hash"],
                         "source_checkpoint_sha256": record["source_checkpoint_sha256"],
                         "target_checkpoint_sha256": record["target_checkpoint_sha256"]})
    return rows


def calibrated_metrics(
    temporal: Sequence[float], reference: Mapping[str, Any], epsilon: float, mad_floor: float, min_observations: int,
) -> dict[str, Any]:
    if (len(temporal) != 3 or any(not math.isfinite(v) or not 0 <= v <= 2 for v in temporal)
            or not math.isfinite(epsilon) or epsilon <= 0 or not math.isfinite(mad_floor) or mad_floor <= 0
            or min_observations <= 0 or reference["removed_target_observations"] != 6
            or reference["reference_entity_count"] < 0
            or reference["observation_count"] != 6 * reference["reference_entity_count"]):
        raise ValueError("Incomplete temporal seeds or invalid LTO calibration contract")
    center, mad, scale = reference["median"], reference["mad"], reference["robust_scale"]
    if ((center is None) != (mad is None) or (mad is None) != (scale is None)
            or (center is None) != (reference["observation_count"] == 0)
            or (center is not None and (not math.isfinite(center) or not 0 <= center <= 2))
            or (mad is not None and (not math.isfinite(mad) or mad < 0
                                    or not math.isfinite(scale) or not math.isclose(scale, 1.4826 * mad, abs_tol=1e-12)))):
        raise ValueError("Invalid LTO median/MAD/scale")
    available = reference["available"]
    reason = reference["unavailable_reason"]
    if (type(available) is not bool or available == bool(reason)
            or (available and (center is None or mad < mad_floor or reference["observation_count"] < min_observations))):
        raise ValueError("Inconsistent LTO availability; epsilon cannot rescue an invalid reference")
    delta = float(compute_median(temporal))
    excess = None if center is None else delta - center
    sed = max(0.0, excess) / (1.4826 * mad + epsilon) if available else None
    if sed is not None and not math.isfinite(sed):
        raise ValueError("Nonfinite calibrated drift")
    return {"delta_time": delta, "signed_excess": excess, "SED_plus": sed,
            "available": available, "unavailable_reason": reason}
