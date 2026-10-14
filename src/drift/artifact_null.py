"""Strict empirical null from persisted valid alignments; no training or re-alignment."""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from kge.checkpoint import KGECheckpoint
from kge.math_utils import l2_norm, one_minus_cosine

from .null import compute_median

ARTIFACT_NULL_VERSION = "saved_alignment_empirical_null_v1"
SEED_PAIRS = ((13, 37), (13, 101), (37, 101))
PairKey = tuple[str, int, int]
SavedAlignment = tuple[dict[str, Any], str]


def saved_noise_observations(
    transition: str, entities: Sequence[str], endpoints: tuple[str, str],
    alignments: Mapping[PairKey, SavedAlignment],
    checkpoints: Mapping[tuple[str, int], KGECheckpoint], centered_norm_floor: float,
) -> list[dict[str, Any]]:
    expected = [(sid, a, b) for sid in endpoints for a, b in SEED_PAIRS]
    if (len(set(entities)) != len(entities) or not entities or len(set(endpoints)) != 2
            or any(not isinstance(e, str) or not e.strip() for e in entities)
            or set(alignments) != set(expected) or len(alignments) != 6
            or not math.isfinite(centered_norm_floor) or centered_norm_floor <= 0):
        raise ValueError("Null requires distinct entities and exactly six registered endpoint pairs")
    pair_values: dict[PairKey, dict[str, float]] = {}
    for sid, a, b in expected:
        record, digest = alignments[sid, a, b]
        if (record["available"] is not True or record["unavailable_reason"]
                or record["alignment_type"] != "same_snapshot_cross_seed"
                or record["transition_id"] != transition
                or record["source_snapshot"] != sid or record["target_snapshot"] != sid
                or record["source_seed"] != a or record["target_seed"] != b
                or not isinstance(digest, str) or len(digest) != 64):
            raise ValueError("Null input alignment unavailable or endpoint/pair identity mismatched")
        if (sid, a) not in checkpoints or (sid, b) not in checkpoints:
            raise ValueError("Null input checkpoint seed is missing")
        source, target = checkpoints[sid, a], checkpoints[sid, b]
        dimension = record["dimension"]
        for cp, seed, field in ((source, a, "source_checkpoint_semantic_hash"),
                                (target, b, "target_checkpoint_semantic_hash")):
            cp.verify_finite()
            if (cp.provenance.snapshot_id != sid or cp.provenance.seed != seed
                    or cp.provenance.dimension != dimension or cp.artifact_hash != record[field]):
                raise ValueError("Null checkpoint identity/dimension/hash mismatch")
        q, mu_s, mu_t = record["Q"], record["source_mean"], record["target_mean"]
        if (len(q) != dimension or any(len(v) != dimension for v in q)
                or len(mu_s) != dimension or len(mu_t) != dimension
                or not all(math.isfinite(x) for row in [*q, mu_s, mu_t] for x in row)):
            raise ValueError("Invalid saved alignment transformation")
        values = {}
        for entity in sorted(entities):
            if entity not in source.entity_embeddings or entity not in target.entity_embeddings:
                raise ValueError("Missing persistent entity in null checkpoint")
            x, y = source.entity_embeddings[entity], target.entity_embeddings[entity]
            if len(x) != dimension or len(y) != dimension:
                raise ValueError("Inconsistent null input vector dimension")
            xc = [x[i] - mu_s[i] for i in range(dimension)]
            yc = [y[i] - mu_t[i] for i in range(dimension)]
            rotated = [sum(xc[i] * q[i][j] for i in range(dimension)) for j in range(dimension)]
            # The existing cosine helper returns a synthetic cos=0 for small
            # norms. Fail closed instead of storing a fabricated noise value.
            if l2_norm(rotated) < centered_norm_floor or l2_norm(yc) < centered_norm_floor:
                raise ValueError("Undefined centered cosine: zero or near-zero vector norm")
            value = one_minus_cosine(rotated, yc)
            if not math.isfinite(value) or not 0 <= value <= 2:
                raise ValueError("Invalid centered noise observation")
            values[entity] = value
        pair_values[sid, a, b] = values
    rows = []
    for entity in sorted(entities):
        for sid, a, b in expected:
            record, digest = alignments[sid, a, b]
            rows.append({"transition_id": transition, "entity_id": entity, "endpoint_snapshot": sid,
                         "source_seed": a, "target_seed": b, "noise_displacement": pair_values[sid, a, b][entity],
                         "alignment_sha256": digest, "anchor_plan_hash": record["anchor_plan_hash"],
                         "source_checkpoint_sha256": record["source_checkpoint_sha256"],
                         "target_checkpoint_sha256": record["target_checkpoint_sha256"]})
    return rows


def merge_degree_buckets(
    values: Mapping[str, Sequence[float]], degrees: Mapping[str, int],
    bin_edges: Sequence[int], min_observations: int,
) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
    labels = ("low", "medium", "high")
    groups: list[dict[str, Any]] = [{"labels": [label], "entities": [], "count": 0} for label in labels]
    for entity in sorted(values):
        degree = degrees[entity]
        index = 0 if degree < bin_edges[0] else 1 if degree < bin_edges[1] else 2
        groups[index]["entities"].append(entity)
        groups[index]["count"] += len(values[entity])
    log = []
    while len(groups) > 1:
        sparse = next((i for i, g in enumerate(groups) if 0 < g["count"] < min_observations), None)
        if sparse is None:
            break
        neighbors = [i for i in (sparse - 1, sparse + 1) if 0 <= i < len(groups)]
        partner = min(neighbors, key=lambda i: (-groups[i]["count"], i))
        first, second = sorted((sparse, partner))
        current, neighbor = groups[sparse], groups[partner]
        merged = {"labels": groups[first]["labels"] + groups[second]["labels"],
                  "entities": sorted(groups[first]["entities"] + groups[second]["entities"]),
                  "count": current["count"] + neighbor["count"]}
        log.append({"sparse_bucket": "+".join(current["labels"]), "sparse_observations": current["count"],
                    "partner_bucket": "+".join(neighbor["labels"]), "partner_observations": neighbor["count"],
                    "merged_bucket": "+".join(merged["labels"]), "merged_observations": merged["count"],
                    "reason": "INSUFFICIENT_POOLED_SAMPLES"})
        groups[first:second + 1] = [merged]
    assignments = {e: "+".join(g["labels"]) for g in groups for e in g["entities"]}
    return assignments, log, ["+".join(g["labels"]) for g in groups]


def reference_statistics(
    observations: Sequence[float], entity_count: int, min_observations: int, mad_threshold: float,
    empty_reason: str, insufficient_reason: str,
) -> dict[str, Any]:
    count = len(observations)
    if not count:
        return {"reference_entity_count": entity_count, "observation_count": 0, "median": None,
                "mad": None, "robust_scale": None, "available": False, "unavailable_reason": empty_reason}
    med = compute_median(observations)
    mad = compute_median([abs(v - med) for v in observations])
    reason = insufficient_reason if count < min_observations else "ZERO_MAD" if mad < mad_threshold else ""
    return {"reference_entity_count": entity_count, "observation_count": count, "median": med, "mad": mad,
            "robust_scale": 1.4826 * mad, "available": not reason, "unavailable_reason": reason}


def build_artifact_null(
    transition: str, values: Mapping[str, Sequence[float]], degrees: Mapping[str, int],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    if not values or set(values) != set(degrees):
        raise ValueError("Null population and pretransition degree metadata must match exactly")
    edges, minimum, tolerance = config["degree_bin_edges"], config["min_reference_observations"], config["degeneracy_mad_threshold"]
    if (len(edges) != 2 or any(type(e) is not int or e < 0 for e in edges) or edges[0] >= edges[1]
            or type(minimum) is not int or minimum <= 0 or not math.isfinite(tolerance) or tolerance <= 0):
        raise ValueError("Invalid registered null bucket/statistics parameters")
    for entity, observations in values.items():
        if (not isinstance(entity, str) or not entity.strip() or type(degrees[entity]) is not int or degrees[entity] < 0
                or len(observations) != 6 or any(not math.isfinite(v) or not 0 <= v <= 2 for v in observations)):
            raise ValueError("Null requires complete six-pair observations and explicit pretransition degrees")
    assignments, log, bucket_ids = merge_degree_buckets(values, degrees, edges, minimum)
    bucket_stats = {}
    lto = {}
    for bucket in bucket_ids:
        entities = sorted(e for e, b in assignments.items() if b == bucket)
        pool = [v for e in entities for v in values[e]]
        bucket_stats[bucket] = {"bucket_id": bucket, **reference_statistics(
            pool, len(entities), minimum, tolerance, "EMPTY_BUCKET", "INSUFFICIENT_SAMPLES")}
        for target in entities:
            reference = [v for e in entities if e != target for v in values[e]]
            lto[target] = {"entity_id": target, "pretransition_degree": degrees[target], "bucket_id": bucket,
                           "removed_target_observations": 6, **reference_statistics(
                               reference, len(entities) - 1, minimum, tolerance,
                               "LTO_EMPTY_BUCKET", "INSUFFICIENT_LTO_SAMPLES")}
    return {"component_version": ARTIFACT_NULL_VERSION, "transition_id": transition,
            "pretransition_degrees": dict(sorted(degrees.items())),
            "entity_observations": {e: list(values[e]) for e in sorted(values)},
            "entity_to_bucket": dict(sorted(assignments.items())), "bucket_merge_log": log,
            "bucket_statistics": bucket_stats, "lto_statistics": dict(sorted(lto.items())),
            "reference_bucket_merging_stage": "pooled_before_LTO", "no_target_specific_remerge": True}
