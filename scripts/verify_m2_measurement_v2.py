"""Independent NumPy verification from checkpoints; no production geometry/reducers."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import numpy as np

from scripts.verify_m2_entity_null_v2 import verify_entity_metric_row, verify_entity_null_artifact


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                                     allow_nan=False).encode()).hexdigest()


def _compare(actual: Any, expected: Any) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError("Independent stage fields differ")
        for key, value in expected.items():
            _compare(actual[key], value)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("Independent stage population differs")
        for a, b in zip(actual, expected):
            _compare(a, b)
    elif type(expected) is float:
        if (type(actual) not in (int, float) or not math.isfinite(actual)
                or not math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-10)):
            raise ValueError("Independent numerical result differs")
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("Independent identity/provenance/availability differs")


def _diagnostic(source: Any, target: Any, record: Mapping[str, Any], plan: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict:
    q, ms, mt = (np.asarray(record[k], dtype=float) for k in ("Q", "source_mean", "target_mean"))
    fit, hold = plan["split"]["fit_anchors"], plan["split"]["holdout_anchors"]
    d = source.provenance.dimension
    if (target.provenance.dimension != d or record["dimension"] != d or q.shape != (d, d)
            or ms.shape != (d,) or mt.shape != (d,) or not all(np.all(np.isfinite(a)) for a in (q, ms, mt))
            or len(fit) < 2 or not hold or len(set(fit)) != len(fit) or len(set(hold)) != len(hold) or set(fit) & set(hold)):
        raise ValueError("Independent geometry/anchor shape failure")
    xf, yf = np.array([source.entity_embeddings[e] for e in fit]), np.array([target.entity_embeddings[e] for e in fit])
    if not np.allclose(xf.mean(axis=0), ms, rtol=1e-12, atol=1e-12) or not np.allclose(yf.mean(axis=0), mt, rtol=1e-12, atol=1e-12):
        raise ValueError("Independent fit means differ")
    covariance = (xf - ms).T @ (yf - mt)
    singular = np.linalg.svd(covariance, compute_uv=False)
    if not math.isclose(float(np.sum(q * covariance)), float(singular.sum()), rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("Independent Procrustes objective mismatch")
    rank = int(np.count_nonzero(singular > cfg["rank_relative_tolerance"] * singular.max())) if singular.max() > 0 else 0
    residual, norms = {}, {}
    for name, ids in (("fit", fit), ("holdout", hold)):
        x, y = np.array([source.entity_embeddings[e] for e in ids]) - ms, np.array([target.entity_embeddings[e] for e in ids]) - mt
        denominator = float(np.linalg.norm(y, ord="fro"))
        norms[name] = denominator
        residual[name] = None if denominator < cfg["denominator_floor"] else float(np.linalg.norm(x @ q - y, ord="fro") / denominator)
    orth = float(np.linalg.norm(q.T @ q - np.eye(d), ord="fro"))
    signed = None if any(v is None for v in residual.values()) else residual["holdout"] - residual["fit"]
    gap = None if signed is None else abs(signed) if cfg["gap_statistic"] == "absolute_holdout_minus_fit" else max(0.0, signed)
    reasons = []
    if record.get("available") is not True or record.get("unavailable_reason") != "":
        reasons.append("SAVED_ALIGNMENT_UNAVAILABLE")
    for name, value in residual.items():
        if value is None:
            reasons.append("DEGENERATE_TARGET_" + name.upper() + "_NORM")
    if rank / d < cfg["minimum_rank_fraction"]:
        reasons.append("RANK_DEFICIENT")
    if orth / d > cfg["maximum_normalized_orthogonality_error"]:
        reasons.append("NORMALIZED_ORTHOGONALITY_VIOLATION")
    if residual["holdout"] is not None and residual["holdout"] > cfg["maximum_relative_holdout_residual"]:
        reasons.append("EXCESSIVE_RELATIVE_HOLDOUT_RESIDUAL")
    if gap is not None and gap > cfg["maximum_relative_fit_holdout_gap"]:
        reasons.append("EXCESSIVE_RELATIVE_FIT_HOLDOUT_GAP")
    return {"source_snapshot": record["source_snapshot"], "target_snapshot": record["target_snapshot"],
            "source_seed": record["source_seed"], "target_seed": record["target_seed"],
            "singular_values": singular.tolist(), "numerical_rank": rank, "rank_fraction": rank / d,
            "relative_fit_residual": residual["fit"], "relative_holdout_residual": residual["holdout"],
            "fit_target_norm": norms["fit"], "holdout_target_norm": norms["holdout"],
            "signed_holdout_minus_fit": signed, "relative_fit_holdout_gap": gap,
            "gap_statistic": cfg["gap_statistic"], "raw_orthogonality_error": orth,
            "normalized_orthogonality_error": orth / d, "available": not reasons, "unavailable_reasons": reasons}


def verify_stage_v2(artifact: Mapping[str, Any], checkpoints: Mapping, alignments: Mapping,
                    plan: Mapping[str, Any], buckets: Mapping[str, str], cfg: Mapping[str, Any],
                    null_stage: Mapping[str, Any] | None = None) -> None:
    keys = {"cosine_estimand", "norm_floor", "denominator_floor", "rank_relative_tolerance", "minimum_rank_fraction",
            "maximum_normalized_orthogonality_error", "maximum_relative_holdout_residual", "maximum_relative_fit_holdout_gap",
            "gap_statistic", "minimum_reference_entities", "mad_threshold", "epsilon"}
    numeric = keys - {"cosine_estimand", "gap_statistic", "minimum_reference_entities"}
    if (set(cfg) != keys or cfg["cosine_estimand"] not in ("affine", "centered")
            or cfg["gap_statistic"] not in ("absolute_holdout_minus_fit", "positive_part_holdout_minus_fit")
            or any(type(cfg[k]) not in (int, float) or not math.isfinite(cfg[k]) or cfg[k] <= 0 for k in numeric)
            or not 0 < cfg["minimum_rank_fraction"] <= 1 or not 0 < cfg["rank_relative_tolerance"] < 1
            or type(cfg["minimum_reference_entities"]) is not int or cfg["minimum_reference_entities"] <= 0):
        raise ValueError("Independent explicit settings failure")
    stage, transition = artifact.get("stage"), artifact.get("transition_id")
    if stage not in ("null", "drift") or not isinstance(transition, str) or len(transition.split("->")) != 2:
        raise ValueError("Independent stage/transition failure")
    prev, nxt = transition.split("->")
    if prev == nxt or not prev.strip() or not nxt.strip() or set(checkpoints) != {(s, seed) for s in (prev, nxt) for seed in (13, 37, 101)}:
        raise ValueError("Independent checkpoint coverage failure")
    for (sid, seed), (cp, physical) in checkpoints.items():
        if (not isinstance(physical, str) or len(physical) != 64 or set(physical) - set("0123456789abcdef")
                or cp.provenance.snapshot_id != sid or cp.provenance.seed != seed or type(seed) is not int
                or cp.provenance.model != "TransE" or cp.provenance.norm != 2):
            raise ValueError("Independent checkpoint identity failure")
        prov = cp.provenance
        semantic = {"provenance": vars(prov), "entities": sorted(cp.entity_embeddings), "relations": sorted(cp.relation_embeddings),
                    "entity_vectors": {e: [round(x, 7) for x in cp.entity_embeddings[e]] for e in sorted(cp.entity_embeddings)},
                    "relation_vectors": {r: [round(x, 7) for x in cp.relation_embeddings[r]] for r in sorted(cp.relation_embeddings)}}
        if cp.artifact_hash != hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest():
            raise ValueError("Independent checkpoint semantic hash failure")
        if any(len(v) != prov.dimension or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
               for v in [*cp.entity_embeddings.values(), *cp.relation_embeddings.values()]):
            raise ValueError("Independent checkpoint vector failure")
        first = checkpoints[sid, 13][0]
        if (set(cp.entity_embeddings) != set(first.entity_embeddings) or prov.snapshot_hash != first.provenance.snapshot_hash
                or prov.entity_mapping_hash != first.provenance.entity_mapping_hash or prov.dimension != first.provenance.dimension):
            raise ValueError("Independent endpoint population failure")
    persistent = set(checkpoints[prev, 13][0].entity_embeddings) & set(checkpoints[nxt, 13][0].entity_embeddings)
    if not persistent or persistent != set(buckets):
        raise ValueError("Independent persistent population failure")
    comparisons = ([(s, s, a, b) for s in (prev, nxt) for a, b in ((13, 37), (13, 101), (37, 101))]
                   if stage == "null" else [(prev, nxt, s, s) for s in (13, 37, 101)])
    selected, diagnostics = [], []
    for key in comparisons:
        record, physical, semantic = alignments[key]
        src, tgt, a, b = key
        if (not isinstance(physical, str) or len(physical) != 64 or set(physical) - set("0123456789abcdef")
                or semantic != _sha(record) or record["anchor_plan_hash"] != _sha(plan)
                or record["transition_id"] != transition
                or record["alignment_type"] != ("same_snapshot_cross_seed" if stage == "null" else "cross_time")
                or (record["source_snapshot"], record["target_snapshot"], record["source_seed"], record["target_seed"]) != key
                or record["source_checkpoint_sha256"] != checkpoints[src, a][1]
                or record["target_checkpoint_sha256"] != checkpoints[tgt, b][1]
                or record["source_checkpoint_semantic_hash"] != checkpoints[src, a][0].artifact_hash
                or record["target_checkpoint_semantic_hash"] != checkpoints[tgt, b][0].artifact_hash):
            raise ValueError("Independent saved alignment lineage failure")
        selected.append((key, record, physical))
        diagnostics.append(_diagnostic(checkpoints[src, a][0], checkpoints[tgt, b][0], record, plan, cfg))
    meta = {"component_version": f"saved_checkpoint_{stage}_stage_v2", "stage": stage, "transition_id": transition,
            "scientific_certification": False, "configuration": dict(cfg), "configuration_sha256": _sha(dict(cfg)),
            "anchor_plan_sha256": _sha(plan), "bucket_plan_sha256": _sha(dict(buckets)),
            "checkpoint_hashes": [{"snapshot_id": sid, "seed": seed, "sha256": physical}
                                  for (sid, seed), (_, physical) in sorted(checkpoints.items())],
            "alignment_hashes": [physical for _, _, physical in selected],
            "alignment_content_hashes": [_sha(record) for _, record, _ in selected], "diagnostics": diagnostics,
            "alignment_available": all(d["available"] for d in diagnostics)}
    for key, value in meta.items():
        _compare(artifact.get(key), value)
    if stage == "drift":
        if null_stage is None:
            raise ValueError("Independent drift requires attached null stage")
        verify_stage_v2(null_stage, checkpoints, alignments, plan, buckets, cfg)
        _compare(artifact.get("null_stage_sha256"), _sha(null_stage))
    reason = ("NULL_ALIGNMENT_UNAVAILABLE" if stage == "drift" and not null_stage["alignment_available"] else
              ("NULL_ALIGNMENT_UNAVAILABLE" if stage == "null" else "TEMPORAL_ALIGNMENT_UNAVAILABLE")
              if not meta["alignment_available"] else "")
    observations = []
    if meta["alignment_available"]:
        for (src, tgt, a, b), record, physical in selected:
            q, ms, mt = (np.asarray(record[k]) for k in ("Q", "source_mean", "target_mean"))
            for entity in sorted(buckets):
                x, y = np.asarray(checkpoints[src, a][0].entity_embeddings[entity]), np.asarray(checkpoints[tgt, b][0].entity_embeddings[entity])
                left, right = (x - ms) @ q, y - mt
                if cfg["cosine_estimand"] == "affine":
                    left, right = left + mt, y
                ln, rn = float(np.linalg.norm(left)), float(np.linalg.norm(right))
                if min(ln, rn) < cfg["norm_floor"] or not math.isfinite(ln + rn):
                    raise ValueError("Independent undefined cosine")
                distance = 1.0 - float(np.clip(np.dot(left / ln, right / rn), -1, 1))
                identity = ({"endpoint_snapshot": src, "source_seed": a, "target_seed": b} if stage == "null"
                            else {"source_snapshot": src, "target_snapshot": tgt, "seed": a})
                observations.append({"transition_id": transition, "entity_id": entity, **identity,
                                     "noise_displacement" if stage == "null" else "temporal_displacement": distance,
                                     "alignment_sha256": physical, **{k: record[k] for k in
                                     ("anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256")}})
    if stage == "null":
        actual_null = artifact.get("null_artifact")
        if reason:
            _compare(actual_null, None)
        else:
            raw = actual_null["raw_observations"]
            def order(r: Mapping[str, Any]) -> tuple:
                return r["entity_id"], r["endpoint_snapshot"], r["source_seed"], r["target_seed"]
            _compare(sorted(raw, key=order), sorted(observations, key=order))
            null_cfg = {k: cfg[k] for k in ("minimum_reference_entities", "mad_threshold", "cosine_estimand")}
            verify_entity_null_artifact(actual_null, raw, buckets, null_cfg)
        expected_rows = [{"entity_id": e, "available": actual_null["lto_statistics"][e]["available"] if actual_null else False,
                          "unavailable_reason": actual_null["lto_statistics"][e]["unavailable_reason"] if actual_null else reason}
                         for e in sorted(buckets)]
        _compare(artifact.get("entity_results"), expected_rows)
        expected_keys = set(meta) | {"null_artifact", "entity_results"}
    else:
        _compare(artifact.get("temporal_observations"), observations)
        rows = artifact.get("entity_results", [])
        if [r["entity_id"] for r in rows] != sorted(buckets):
            raise ValueError("Independent drift row coverage failure")
        for row in rows:
            if reason:
                values = [r["temporal_displacement"] for r in observations if r["entity_id"] == row["entity_id"]]
                _compare(row, {"entity_id": row["entity_id"], "drift_component_version": "saved_checkpoint_drift_row_v2",
                               "calibration_component_version": None,
                               "delta_time": float(np.median(values)) if values else None,
                               "signed_excess": None, "SED_plus": None,
                               "available": False, "unavailable_reason": reason})
            else:
                temporal = {r["seed"]: r["temporal_displacement"] for r in observations if r["entity_id"] == row["entity_id"]}
                if (set(row) != {"entity_id", "drift_component_version", "calibration_component_version", "delta_time",
                                "signed_excess", "SED_plus", "available", "unavailable_reason"}
                        or row["drift_component_version"] != "saved_checkpoint_drift_row_v2"
                        or row["calibration_component_version"] != "entity_reference_longitudinal_drift_v2"):
                    raise ValueError("Unexpected drift fields")
                calibrated = {**row, "drift_component_version": row["calibration_component_version"]}
                verify_entity_metric_row(calibrated, temporal, null_stage["null_artifact"]["lto_statistics"][row["entity_id"]],
                                         cfg["epsilon"], cfg["mad_threshold"], cfg["minimum_reference_entities"])
        expected_keys = set(meta) | {"null_stage_sha256", "temporal_observations", "entity_results"}
    if set(artifact) != expected_keys:
        raise ValueError("Unregistered or missing stage fields")
