"""Strict empirical null from persisted valid alignments; no training or re-alignment."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from kge.checkpoint import KGECheckpoint
from kge.math_utils import l2_norm, one_minus_cosine

from .null import compute_median

ARTIFACT_NULL_VERSION = "saved_alignment_empirical_null_v1"
ENTITY_NULL_VERSION = "saved_alignment_entity_null_v2"
ENTITY_REFERENCE_VERSION = "entity_null_reference_v2"
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


def _entity_null_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_entity_reference(
    reference: Mapping[str, Any], minimum: int, mad_threshold: float,
) -> None:
    """Validate v2 units and availability without inferring a scientific policy."""
    required = {"reference_schema_version", "transition_id", "entity_id", "bucket_id", "reference_entity_ids",
                "removed_target_raw_observation_count", "raw_noise_observation_count", "reference_entity_count",
                "reference_sample_count", "minimum_reference_entities", "mad_threshold",
                "median", "mad", "robust_scale", "available", "unavailable_reason"}
    if (not required.issubset(reference) or "observation_count" in reference
            or reference["reference_schema_version"] != ENTITY_REFERENCE_VERSION
            or type(minimum) is not int or minimum <= 0
            or not _finite_number(mad_threshold) or mad_threshold <= 0
            or type(reference["minimum_reference_entities"]) is not int
            or reference["minimum_reference_entities"] != minimum
            or not _finite_number(reference["mad_threshold"]) or reference["mad_threshold"] != mad_threshold):
        raise ValueError("Entity reference requires explicit v2 schema and matching support policy")
    ids = reference["reference_entity_ids"]
    if (not isinstance(ids, list) or any(not isinstance(e, str) or not e.strip() for e in ids)
            or len(set(ids)) != len(ids) or ids != sorted(ids)
            or any(not isinstance(reference[k], str) or not reference[k].strip()
                   for k in ("entity_id", "transition_id", "bucket_id"))
            or reference["entity_id"] in ids):
        raise ValueError("Reference must contain distinct other entity IDs")
    count = len(ids)
    counts = {"reference_entity_count": count, "reference_sample_count": count,
              "raw_noise_observation_count": 6 * count, "removed_target_raw_observation_count": 6}
    if any(type(reference[k]) is not int or reference[k] != expected for k, expected in counts.items()):
        raise ValueError("Raw distances and entity-level reference samples have incompatible units")
    center, mad, scale = reference["median"], reference["mad"], reference["robust_scale"]
    if count == 0:
        if any(value is not None for value in (center, mad, scale)):
            raise ValueError("Empty reference cannot have fabricated statistics")
        reason = "LTO_EMPTY_REFERENCE"
    else:
        if (not all(_finite_number(v) for v in (center, mad, scale))
                or not 0 <= center <= 2 or not 0 <= mad <= 2
                or not math.isclose(scale, 1.4826 * mad, rel_tol=1e-12, abs_tol=1e-12)):
            raise ValueError("Invalid entity-level median/MAD/scale")
        reason = ("INSUFFICIENT_REFERENCE_ENTITIES" if count < minimum
                  else "ZERO_MAD" if mad < mad_threshold else "")
    if (type(reference["available"]) is not bool or reference["available"] != (not reason)
            or reference["unavailable_reason"] != reason):
        raise ValueError("Entity-level support and availability are inconsistent")


def build_entity_level_null(
    transition: str, observations: Sequence[Mapping[str, Any]],
    entity_to_bucket: Mapping[str, str], config: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce six raw rows/entity before LTO, with an explicitly supplied bucket plan.

    This component neither chooses/merges buckets nor certifies the declared
    cosine estimand. No scientific defaults or protocol activation occur here.
    The v1 builder remains available only for its historical Dev consumers.
    """
    if (not isinstance(transition, str) or len(transition.split("->")) != 2
            or not all(part.strip() for part in transition.split("->"))
            or len(set(transition.split("->"))) != 2 or not observations
            or set(config) != {"minimum_reference_entities", "mad_threshold", "cosine_estimand"}):
        raise ValueError("Explicit transition, raw observations and v2 configuration are required")
    minimum, tolerance = config["minimum_reference_entities"], config["mad_threshold"]
    if (type(minimum) is not int or minimum <= 0 or not _finite_number(tolerance) or tolerance <= 0
            or config["cosine_estimand"] not in ("centered", "affine")):
        raise ValueError("Invalid explicit entity-level support or declared cosine parameters")
    expected_pairs = {(sid, a, b) for sid in transition.split("->") for a, b in SEED_PAIRS}
    hash_fields = {"alignment_sha256", "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256"}
    required = {"transition_id", "entity_id", "endpoint_snapshot", "source_seed", "target_seed",
                "noise_displacement", *hash_fields}
    grouped: dict[str, dict[tuple[str, int, int], dict[str, Any]]] = {}
    comparison_lineage: dict[tuple[str, int, int], tuple[str, str]] = {}
    checkpoint_lineage: dict[tuple[str, int], str] = {}
    for raw in observations:
        if (not required.issubset(raw) or set(raw) - required - {"pretransition_degree", "bucket_id"}
                or raw["transition_id"] != transition or not isinstance(raw["entity_id"], str)
                or not raw["entity_id"].strip() or type(raw["source_seed"]) is not int
                or type(raw["target_seed"]) is not int or not isinstance(raw["endpoint_snapshot"], str)
                or not _finite_number(raw["noise_displacement"]) or not 0 <= raw["noise_displacement"] <= 2):
            raise ValueError("Invalid raw noise identity, distance or unregistered field")
        if any(not isinstance(raw[field], str) or len(raw[field]) != 64
               or any(c not in "0123456789abcdef" for c in raw[field]) for field in hash_fields):
            raise ValueError("Raw noise provenance requires SHA-256 fingerprints")
        entity = raw["entity_id"]
        key = raw["endpoint_snapshot"], raw["source_seed"], raw["target_seed"]
        pairs = grouped.setdefault(entity, {})
        if key not in expected_pairs or key in pairs:
            raise ValueError("Missing or duplicate registered endpoint/seed pair identity")
        lineage = raw["alignment_sha256"], raw["anchor_plan_hash"]
        if key in comparison_lineage and comparison_lineage[key] != lineage:
            raise ValueError("One endpoint/seed comparison declares conflicting alignment lineage")
        comparison_lineage[key] = lineage
        for seed_field, hash_field in (("source_seed", "source_checkpoint_sha256"),
                                       ("target_seed", "target_checkpoint_sha256")):
            checkpoint_key = raw["endpoint_snapshot"], raw[seed_field]
            fingerprint = raw[hash_field]
            if checkpoint_key in checkpoint_lineage and checkpoint_lineage[checkpoint_key] != fingerprint:
                raise ValueError("One endpoint/seed declares conflicting checkpoint lineage")
            checkpoint_lineage[checkpoint_key] = fingerprint
        if ("pretransition_degree" in raw
                and (type(raw["pretransition_degree"]) is not int or raw["pretransition_degree"] < 0)):
            raise ValueError("Invalid supplied pretransition degree")
        if "bucket_id" in raw and raw["bucket_id"] != entity_to_bucket.get(entity):
            raise ValueError("Raw bucket annotation disagrees with the supplied reference plan")
        pairs[key] = dict(raw)
    if (set(grouped) != set(entity_to_bucket)
            or any(not isinstance(b, str) or not b.strip() for b in entity_to_bucket.values())
            or any(set(pairs) != expected_pairs for pairs in grouped.values())):
        raise ValueError("Bucket plan population and complete six-pair entity observations must agree")
    canonical = [grouped[e][key] for e in sorted(grouped) for key in sorted(expected_pairs)]
    entity_stats = {}
    for entity in sorted(grouped):
        rows = [grouped[entity][key] for key in sorted(expected_pairs)]
        entity_stats[entity] = {"entity_id": entity,
                                "noise_median": compute_median([r["noise_displacement"] for r in rows]),
                                "raw_noise_observation_count": 6,
                                "raw_observation_sha256s": [_entity_null_hash(r) for r in rows]}
    lto = {}
    for target, bucket in sorted(entity_to_bucket.items()):
        ids = sorted(e for e, b in entity_to_bucket.items() if b == bucket and e != target)
        samples = [entity_stats[e]["noise_median"] for e in ids]
        center = compute_median(samples) if samples else None
        mad = compute_median([abs(value - center) for value in samples]) if samples else None
        reason = ("LTO_EMPTY_REFERENCE" if not ids else "INSUFFICIENT_REFERENCE_ENTITIES" if len(ids) < minimum
                  else "ZERO_MAD" if mad < tolerance else "")
        row = {"reference_schema_version": ENTITY_REFERENCE_VERSION, "transition_id": transition,
               "entity_id": target, "bucket_id": bucket, "reference_entity_ids": ids,
               "removed_target_raw_observation_count": 6, "raw_noise_observation_count": 6 * len(ids),
               "reference_entity_count": len(ids), "reference_sample_count": len(ids),
               "minimum_reference_entities": minimum, "mad_threshold": tolerance,
               "median": center, "mad": mad, "robust_scale": None if mad is None else 1.4826 * mad,
               "available": not reason, "unavailable_reason": reason}
        validate_entity_reference(row, minimum, tolerance)
        lto[target] = row
    return {"component_version": ENTITY_NULL_VERSION, "transition_id": transition,
            "reference_schema_version": ENTITY_REFERENCE_VERSION, "configuration": dict(config),
            "configuration_sha256": _entity_null_hash(dict(config)),
            "entity_to_bucket": dict(sorted(entity_to_bucket.items())),
            "bucket_plan_sha256": _entity_null_hash(dict(entity_to_bucket)),
            "raw_observations": canonical, "raw_observations_sha256": _entity_null_hash(canonical),
            "entity_noise_statistics": entity_stats, "lto_statistics": lto,
            "scientific_certification": False, "bucket_policy": "explicit_external_plan_no_automatic_merge"}
