"""Explicit saved-checkpoint geometry and separate null/drift stage APIs.

No training, anchor/bucket selection, parameter defaults or scientific activation.
Callers must bind physical input hashes and a registered configuration separately.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from kge.checkpoint import KGECheckpoint
from kge.math_utils import svd_ortho_procrustes

from .artifact_drift import calibrated_metrics_v2
from .artifact_null import build_entity_level_null

SEEDS = (13, 37, 101)
CheckpointInputs = Mapping[tuple[str, int], tuple[KGECheckpoint, str]]
AlignmentInputs = Mapping[tuple[str, str, int, int], tuple[dict[str, Any], str, str]]
SETTING_KEYS = {"cosine_estimand", "norm_floor", "denominator_floor", "rank_relative_tolerance",
                "minimum_rank_fraction", "maximum_normalized_orthogonality_error",
                "maximum_relative_holdout_residual", "maximum_relative_fit_holdout_gap", "gap_statistic",
                "minimum_reference_entities", "mad_threshold", "epsilon"}


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                                     allow_nan=False).encode()).hexdigest()


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and not set(value) - set("0123456789abcdef")


def validate_settings(settings: Mapping[str, Any]) -> None:
    numeric = SETTING_KEYS - {"cosine_estimand", "gap_statistic", "minimum_reference_entities"}
    if (set(settings) != SETTING_KEYS or settings["cosine_estimand"] not in ("affine", "centered")
            or settings["gap_statistic"] not in ("absolute_holdout_minus_fit", "positive_part_holdout_minus_fit")
            or any(not _number(settings[k]) or settings[k] <= 0 for k in numeric)
            or not 0 < settings["minimum_rank_fraction"] <= 1
            or not 0 < settings["rank_relative_tolerance"] < 1
            or type(settings["minimum_reference_entities"]) is not int or settings["minimum_reference_entities"] <= 0):
        raise ValueError("Complete explicit v2 geometry, gap, calibration and support settings required")


def _matrix(q: Sequence[Sequence[float]], means: Sequence[Sequence[float]], dimension: int) -> None:
    if (type(dimension) is not int or dimension <= 0 or len(q) != dimension
            or any(len(row) != dimension for row in q) or any(len(m) != dimension for m in means)
            or any(not _number(x) for row in [*q, *means] for x in row)):
        raise ValueError("Finite consistent saved geometry required")


def saved_displacement_v2(
    x: Sequence[float], y: Sequence[float], q: Sequence[Sequence[float]],
    source_mean: Sequence[float], target_mean: Sequence[float], estimand: str, norm_floor: float,
) -> float:
    d = len(x)
    _matrix(q, [x, y, source_mean, target_mean], d)
    if estimand not in ("affine", "centered") or not _number(norm_floor) or norm_floor <= 0:
        raise ValueError("Explicit cosine estimand and positive finite norm floor required")
    rotated = [sum((x[i] - source_mean[i]) * q[i][j] for i in range(d)) for j in range(d)]
    left = [rotated[j] + target_mean[j] for j in range(d)] if estimand == "affine" else rotated
    right = list(y) if estimand == "affine" else [y[j] - target_mean[j] for j in range(d)]
    ln, rn = math.hypot(*left), math.hypot(*right)
    if not math.isfinite(ln) or not math.isfinite(rn) or ln < norm_floor or rn < norm_floor:
        raise ValueError("Undefined declared cosine: zero/near-zero/nonfinite vector norm")
    # Normalize first to avoid overflow; never use the legacy synthetic cos=0 fallback.
    cosine = sum((a / ln) * (b / rn) for a, b in zip(left, right))
    return 1.0 - max(-1.0, min(1.0, cosine))


def collect_alignment_geometry_v2(
    source: KGECheckpoint, target: KGECheckpoint, record: Mapping[str, Any],
    anchor_plan: Mapping[str, Any], rank_relative_tolerance: float | None,
) -> dict[str, Any]:
    """Collect raw geometry without requiring/choosing operating ranges or a gate.

    A missing rank tolerance leaves numerical rank null; the full spectrum is
    retained. Exact-zero denominators produce undefined ratios with raw norms,
    allowing a prospective pilot to inform handling without hidden epsilon.
    """
    if rank_relative_tolerance is not None and (not _number(rank_relative_tolerance)
                                               or not 0 < rank_relative_tolerance < 1):
        raise ValueError("Rank tolerance must be explicit positive relative tolerance or None")
    d = source.provenance.dimension
    if target.provenance.dimension != d or record["dimension"] != d:
        raise ValueError("Alignment/checkpoint dimensions disagree")
    q, ms, mt = record["Q"], record["source_mean"], record["target_mean"]
    _matrix(q, [ms, mt], d)
    fit, hold = anchor_plan["split"]["fit_anchors"], anchor_plan["split"]["holdout_anchors"]
    if (len(fit) < 2 or not hold or len(set(fit)) != len(fit) or len(set(hold)) != len(hold)
            or set(fit) & set(hold) or any(not isinstance(e, str) or not e.strip() for e in [*fit, *hold])):
        raise ValueError("Nonempty distinct disjoint fit/holdout anchors required")
    for cp in (source, target):
        cp.verify_finite()
        if cp.artifact_hash != cp.compute_artifact_hash():
            raise ValueError("Checkpoint semantic hash differs from actual vectors/provenance")
        if any(e not in cp.entity_embeddings for e in [*fit, *hold]):
            raise ValueError("Missing registered anchor")
        if any(len(cp.entity_embeddings[e]) != d or any(not _number(x) for x in cp.entity_embeddings[e]) for e in [*fit, *hold]):
            raise ValueError("Anchor vector dimension/type mismatch")
    for cp, mean in ((source, ms), (target, mt)):
        expected = [sum(cp.entity_embeddings[e][j] for e in fit) / len(fit) for j in range(d)]
        if any(not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) for a, b in zip(mean, expected)):
            raise ValueError("Saved means were not computed from the declared fit anchors")
    covariance = [[sum((source.entity_embeddings[e][i] - ms[i]) * (target.entity_embeddings[e][j] - mt[j])
                        for e in fit) for j in range(d)] for i in range(d)]
    _, singular, _ = svd_ortho_procrustes(covariance)
    optimum = sum(singular)
    achieved = sum(q[i][j] * covariance[i][j] for i in range(d) for j in range(d))
    # Numerical validation of the defining SVD objective, not an operating-range threshold.
    if not math.isclose(achieved, optimum, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("Saved Q does not solve the declared fit-anchor Procrustes problem")
    largest = max(singular)
    rank = (None if rank_relative_tolerance is None else
            sum(s > rank_relative_tolerance * largest for s in singular) if largest > 0 else 0)
    residuals, denominators, numerators = {}, {}, {}
    for name, entities in (("fit", fit), ("holdout", hold)):
        errors, targets = [], []
        for e in entities:
            xc = [source.entity_embeddings[e][i] - ms[i] for i in range(d)]
            yc = [target.entity_embeddings[e][i] - mt[i] for i in range(d)]
            rotated = [sum(xc[i] * q[i][j] for i in range(d)) for j in range(d)]
            errors.extend(a - b for a, b in zip(rotated, yc))
            targets.extend(yc)
        denominator = math.hypot(*targets)
        denominators[name] = denominator
        numerators[name] = math.hypot(*errors)
        residuals[name] = None if denominator == 0 else numerators[name] / denominator
    orth = math.hypot(*(sum(q[k][i] * q[k][j] for k in range(d)) - (1 if i == j else 0)
                        for i in range(d) for j in range(d)))
    signed_gap = None if any(v is None for v in residuals.values()) else residuals["holdout"] - residuals["fit"]
    issues = ["ZERO_TARGET_" + name.upper() + "_NORM" for name in ("fit", "holdout") if denominators[name] == 0]
    if largest == 0:
        issues.append("ZERO_COVARIANCE_SPECTRUM")
    result = {"statistics_version": "saved_alignment_geometry_statistics_v2",
              "source_snapshot": record["source_snapshot"], "target_snapshot": record["target_snapshot"],
              "source_seed": record["source_seed"], "target_seed": record["target_seed"],
              "singular_values": singular, "relative_singular_values": [s / largest if largest > 0 else None for s in singular],
              "rank_relative_tolerance": rank_relative_tolerance, "numerical_rank": rank,
              "rank_fraction": None if rank is None else rank / d,
              "relative_fit_residual": residuals["fit"], "relative_holdout_residual": residuals["holdout"],
              "fit_error_norm": numerators["fit"], "holdout_error_norm": numerators["holdout"],
              "fit_target_norm": denominators["fit"], "holdout_target_norm": denominators["holdout"],
              "signed_holdout_minus_fit": signed_gap,
              "absolute_holdout_minus_fit": None if signed_gap is None else abs(signed_gap),
              "raw_orthogonality_error": orth, "normalized_orthogonality_error": orth / d,
              "undefined_statistics": issues}
    content_hash(result)
    return result


def geometry_diagnostics_v2(
    source: KGECheckpoint, target: KGECheckpoint, record: Mapping[str, Any],
    anchor_plan: Mapping[str, Any], settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply explicitly registered operating ranges to the raw statistics."""
    validate_settings(settings)
    raw = collect_alignment_geometry_v2(source, target, record, anchor_plan, settings["rank_relative_tolerance"])
    d, rank, singular, orth = source.provenance.dimension, raw["numerical_rank"], raw["singular_values"], raw["raw_orthogonality_error"]
    denominators = {name: raw[name + "_target_norm"] for name in ("fit", "holdout")}
    residuals = {name: None if denominators[name] < settings["denominator_floor"] else raw["relative_" + name + "_residual"]
                 for name in ("fit", "holdout")}
    signed_gap = None if any(v is None for v in residuals.values()) else residuals["holdout"] - residuals["fit"]
    gap = (None if signed_gap is None else abs(signed_gap) if settings["gap_statistic"] == "absolute_holdout_minus_fit"
           else max(0.0, signed_gap))
    reasons = []
    if record.get("available") is not True or record.get("unavailable_reason") != "":
        reasons.append("SAVED_ALIGNMENT_UNAVAILABLE")
    for name, value in residuals.items():
        if value is None:
            reasons.append("DEGENERATE_TARGET_" + name.upper() + "_NORM")
    if rank / d < settings["minimum_rank_fraction"]:
        reasons.append("RANK_DEFICIENT")
    if orth / d > settings["maximum_normalized_orthogonality_error"]:
        reasons.append("NORMALIZED_ORTHOGONALITY_VIOLATION")
    if residuals["holdout"] is not None and residuals["holdout"] > settings["maximum_relative_holdout_residual"]:
        reasons.append("EXCESSIVE_RELATIVE_HOLDOUT_RESIDUAL")
    if gap is not None and gap > settings["maximum_relative_fit_holdout_gap"]:
        reasons.append("EXCESSIVE_RELATIVE_FIT_HOLDOUT_GAP")
    result = {"source_snapshot": record["source_snapshot"], "target_snapshot": record["target_snapshot"],
              "source_seed": record["source_seed"], "target_seed": record["target_seed"],
              "singular_values": singular, "numerical_rank": rank, "rank_fraction": rank / d,
              "relative_fit_residual": residuals["fit"], "relative_holdout_residual": residuals["holdout"],
              "fit_target_norm": denominators["fit"], "holdout_target_norm": denominators["holdout"],
              "signed_holdout_minus_fit": signed_gap, "relative_fit_holdout_gap": gap,
              "gap_statistic": settings["gap_statistic"], "raw_orthogonality_error": orth,
              "normalized_orthogonality_error": orth / d, "available": not reasons, "unavailable_reasons": reasons}
    content_hash(result)  # NaN/Inf cannot become a persisted diagnostic.
    return result


def _prepare(
    transition: str, checkpoints: CheckpointInputs, anchor_plan: Mapping[str, Any],
    buckets: Mapping[str, str], settings: Mapping[str, Any],
) -> tuple[str, str]:
    validate_settings(settings)
    endpoints = transition.split("->")
    if len(endpoints) != 2 or not all(s.strip() for s in endpoints) or endpoints[0] == endpoints[1]:
        raise ValueError("Distinct explicit adjacent endpoints required")
    prev, nxt = endpoints
    if set(checkpoints) != {(sid, seed) for sid in endpoints for seed in SEEDS}:
        raise ValueError("Exactly six endpoint checkpoints required")
    for (sid, seed), (cp, physical) in checkpoints.items():
        if (not _hash(physical) or cp.provenance.snapshot_id != sid or cp.provenance.seed != seed
                or cp.provenance.model != "TransE" or cp.provenance.norm != 2
                or type(seed) is not int or cp.artifact_hash != cp.compute_artifact_hash()):
            raise ValueError("Checkpoint identity, physical/semantic hash or backbone mismatch")
        if any(len(v) != cp.provenance.dimension or any(not _number(x) for x in v)
               for v in [*cp.entity_embeddings.values(), *cp.relation_embeddings.values()]):
            raise ValueError("Checkpoint vectors must be finite numeric vectors of the declared dimension")
        baseline = checkpoints[sid, 13][0]
        if (set(cp.entity_embeddings) != set(baseline.entity_embeddings)
                or cp.provenance.entity_mapping_hash != baseline.provenance.entity_mapping_hash
                or cp.provenance.snapshot_hash != baseline.provenance.snapshot_hash
                or cp.provenance.dimension != baseline.provenance.dimension):
            raise ValueError("Within-endpoint seed mapping/snapshot/dimension mismatch")
    persistent = set(checkpoints[prev, 13][0].entity_embeddings) & set(checkpoints[nxt, 13][0].entity_embeddings)
    if (not persistent or set(buckets) != persistent
            or any(not isinstance(e, str) or not e.strip() for e in persistent)
            or any(not isinstance(b, str) or not b.strip() for b in buckets.values())):
        raise ValueError("External bucket plan must cover the entire persistent population exactly")
    if any(e not in persistent for e in [*anchor_plan["split"]["fit_anchors"], *anchor_plan["split"]["holdout_anchors"]]):
        raise ValueError("Anchor plan contains a nonpersistent entity")
    return prev, nxt


def _comparisons(
    transition: str, stage: str, checkpoints: CheckpointInputs, alignments: AlignmentInputs,
    anchor_plan: Mapping[str, Any], buckets: Mapping[str, str], settings: Mapping[str, Any],
) -> tuple[list[tuple[tuple[str, str, int, int], dict[str, Any], str]], list[dict[str, Any]]]:
    prev, nxt = _prepare(transition, checkpoints, anchor_plan, buckets, settings)
    keys = ([(sid, sid, a, b) for sid in (prev, nxt) for a, b in ((13, 37), (13, 101), (37, 101))]
            if stage == "null" else [(prev, nxt, seed, seed) for seed in SEEDS])
    if not set(keys).issubset(alignments):
        raise ValueError("Missing required saved alignment comparison")
    selected, diagnostics = [], []
    for key in keys:
        record, physical, semantic = alignments[key]
        src, tgt, a, b = key
        source, target = checkpoints[src, a][0], checkpoints[tgt, b][0]
        if (not _hash(physical) or not _hash(semantic) or semantic != content_hash(record) or record["transition_id"] != transition
                or (record["source_snapshot"], record["target_snapshot"], record["source_seed"], record["target_seed"]) != key
                or record["alignment_type"] != ("same_snapshot_cross_seed" if stage == "null" else "cross_time")
                or record["anchor_plan_hash"] != content_hash(anchor_plan)
                or record["source_checkpoint_sha256"] != checkpoints[src, a][1]
                or record["target_checkpoint_sha256"] != checkpoints[tgt, b][1]
                or record["source_checkpoint_semantic_hash"] != source.artifact_hash
                or record["target_checkpoint_semantic_hash"] != target.artifact_hash):
            raise ValueError("Saved alignment physical/semantic lineage or comparison identity mismatch")
        selected.append((key, record, physical))
        diagnostics.append(geometry_diagnostics_v2(source, target, record, anchor_plan, settings))
    return selected, diagnostics


def _base(stage: str, transition: str, checkpoints: CheckpointInputs, selected: list,
          plan: Mapping[str, Any], buckets: Mapping[str, str], settings: Mapping[str, Any], diagnostics: list) -> dict[str, Any]:
    return {"component_version": f"saved_checkpoint_{stage}_stage_v2", "stage": stage, "transition_id": transition,
            "scientific_certification": False, "configuration": dict(settings),
            "configuration_sha256": content_hash(dict(settings)), "anchor_plan_sha256": content_hash(plan),
            "bucket_plan_sha256": content_hash(dict(buckets)),
            "checkpoint_hashes": [{"snapshot_id": sid, "seed": seed, "sha256": physical}
                                  for (sid, seed), (_, physical) in sorted(checkpoints.items())],
            "alignment_hashes": [physical for _, _, physical in selected],
            "alignment_content_hashes": [content_hash(record) for _, record, _ in selected], "diagnostics": diagnostics,
            "alignment_available": all(d["available"] for d in diagnostics)}


def _observations(selected: list, checkpoints: CheckpointInputs, entities: Sequence[str],
                  transition: str, settings: Mapping[str, Any], stage: str) -> list[dict[str, Any]]:
    rows = []
    for (src, tgt, a, b), record, physical in selected:
        for entity in sorted(entities):
            distance = saved_displacement_v2(checkpoints[src, a][0].entity_embeddings[entity],
                                              checkpoints[tgt, b][0].entity_embeddings[entity],
                                              record["Q"], record["source_mean"], record["target_mean"],
                                              settings["cosine_estimand"], settings["norm_floor"])
            identity = ({"endpoint_snapshot": src, "source_seed": a, "target_seed": b}
                        if stage == "null" else {"source_snapshot": src, "target_snapshot": tgt, "seed": a})
            rows.append({"transition_id": transition, "entity_id": entity, **identity,
                         "noise_displacement" if stage == "null" else "temporal_displacement": distance,
                         "alignment_sha256": physical, **{k: record[k] for k in
                         ("anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256")}})
    return rows


def build_null_stage_v2(transition: str, checkpoints: CheckpointInputs, alignments: AlignmentInputs,
                        anchor_plan: Mapping[str, Any], buckets: Mapping[str, str], settings: Mapping[str, Any]) -> dict[str, Any]:
    selected, diagnostics = _comparisons(transition, "null", checkpoints, alignments, anchor_plan, buckets, settings)
    result = _base("null", transition, checkpoints, selected, anchor_plan, buckets, settings, diagnostics)
    artifact = None
    if result["alignment_available"]:
        rows = _observations(selected, checkpoints, sorted(buckets), transition, settings, "null")
        cfg = {key: settings[key] for key in ("minimum_reference_entities", "mad_threshold", "cosine_estimand")}
        artifact = build_entity_level_null(transition, rows, buckets, cfg)
    result["null_artifact"] = artifact
    result["entity_results"] = [{"entity_id": e, "available": artifact["lto_statistics"][e]["available"] if artifact else False,
                                 "unavailable_reason": artifact["lto_statistics"][e]["unavailable_reason"]
                                 if artifact else "NULL_ALIGNMENT_UNAVAILABLE"} for e in sorted(buckets)]
    return result


def build_drift_stage_v2(transition: str, checkpoints: CheckpointInputs, alignments: AlignmentInputs,
                         anchor_plan: Mapping[str, Any], buckets: Mapping[str, str], settings: Mapping[str, Any],
                         null_stage: Mapping[str, Any]) -> dict[str, Any]:
    # Verify the attached previous-stage artifact, never write or auto-advance a stage.
    expected_null = build_null_stage_v2(transition, checkpoints, alignments, anchor_plan, buckets, settings)
    if content_hash(null_stage) != content_hash(expected_null):
        raise ValueError("Attached null stage differs from saved inputs, declared geometry or support policy")
    selected, diagnostics = _comparisons(transition, "drift", checkpoints, alignments, anchor_plan, buckets, settings)
    result = _base("drift", transition, checkpoints, selected, anchor_plan, buckets, settings, diagnostics)
    result["null_stage_sha256"] = content_hash(null_stage)
    reason = ("NULL_ALIGNMENT_UNAVAILABLE" if not null_stage["alignment_available"] else
              "TEMPORAL_ALIGNMENT_UNAVAILABLE" if not result["alignment_available"] else "")
    rows = (_observations(selected, checkpoints, sorted(buckets), transition, settings, "drift")
            if result["alignment_available"] else [])
    entities = []
    for entity in sorted(buckets):
        if reason:
            values = sorted(r["temporal_displacement"] for r in rows if r["entity_id"] == entity)
            metric = {"drift_component_version": "saved_checkpoint_drift_row_v2", "calibration_component_version": None,
                      "delta_time": values[1] if values else None, "signed_excess": None, "SED_plus": None,
                      "available": False, "unavailable_reason": reason}
        else:
            temporal = {r["seed"]: r["temporal_displacement"] for r in rows if r["entity_id"] == entity}
            metric = calibrated_metrics_v2(temporal, null_stage["null_artifact"]["lto_statistics"][entity],
                                            settings["epsilon"], settings["mad_threshold"], settings["minimum_reference_entities"])
            metric["calibration_component_version"] = metric["drift_component_version"]
            metric["drift_component_version"] = "saved_checkpoint_drift_row_v2"
        entities.append({"entity_id": entity, **metric})
    result.update(temporal_observations=rows, entity_results=entities)
    return result
