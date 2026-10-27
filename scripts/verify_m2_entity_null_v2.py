"""Independent NumPy verification of v2 reductions, LTO units and calibration.

This checks supplied raw distances and an explicit bucket plan. It does not
certify their cosine estimand, upstream alignment, policy registration or G3.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _close(actual: Any, expected: Any) -> None:
    if expected is None:
        if actual is not None:
            raise ValueError("Fabricated empty-reference statistic")
    elif (type(actual) not in (int, float) or not math.isfinite(actual)
          or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)):
        raise ValueError("Independent entity-level numeric mismatch")


def _reference_units(reference: Mapping[str, Any], minimum: int, floor: float) -> str:
    """Independent checks; deliberately does not import production validators."""
    required = {"reference_schema_version", "transition_id", "entity_id", "bucket_id", "reference_entity_ids",
                "reference_sample_count", "reference_entity_count", "raw_noise_observation_count",
                "removed_target_raw_observation_count", "minimum_reference_entities", "mad_threshold",
                "median", "mad", "robust_scale", "available", "unavailable_reason"}
    if (not required.issubset(reference) or "observation_count" in reference
            or reference["reference_schema_version"] != "entity_null_reference_v2"
            or type(minimum) is not int or minimum <= 0
            or type(floor) not in (int, float) or not math.isfinite(floor) or floor <= 0
            or type(reference["minimum_reference_entities"]) is not int
            or reference["minimum_reference_entities"] != minimum
            or type(reference["mad_threshold"]) not in (int, float) or reference["mad_threshold"] != floor):
        raise ValueError("Independent v2 schema or support-policy mismatch")
    ids = reference["reference_entity_ids"]
    if (not isinstance(ids, list) or any(not isinstance(e, str) or not e.strip() for e in ids)
            or any(not isinstance(reference[k], str) or not reference[k].strip()
                   for k in ("transition_id", "entity_id", "bucket_id"))
            or len(ids) != len(set(ids)) or ids != sorted(ids) or reference["entity_id"] in ids):
        raise ValueError("Reference entity membership is invalid")
    n = len(ids)
    for key, value in (("reference_entity_count", n), ("reference_sample_count", n),
                       ("raw_noise_observation_count", 6 * n), ("removed_target_raw_observation_count", 6)):
        if type(reference[key]) is not int or reference[key] != value:
            raise ValueError("Reference sample units are invalid")
    if n == 0:
        if any(reference[k] is not None for k in ("median", "mad", "robust_scale")):
            raise ValueError("Empty reference statistics must be null")
        reason = "LTO_EMPTY_REFERENCE"
    else:
        center, mad, scale = (reference[k] for k in ("median", "mad", "robust_scale"))
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (center, mad, scale))
                or not 0 <= center <= 2 or not 0 <= mad <= 2):
            raise ValueError("Invalid reference center or scale")
        _close(scale, 1.4826 * mad)
        reason = ("INSUFFICIENT_REFERENCE_ENTITIES" if n < minimum else "ZERO_MAD" if mad < floor else "")
    if (type(reference["available"]) is not bool or reference["available"] != (reason == "")
            or reference["unavailable_reason"] != reason):
        raise ValueError("False availability declaration")
    return reason


def verify_entity_null_artifact(
    artifact: Mapping[str, Any], observations: Sequence[Mapping[str, Any]],
    buckets: Mapping[str, str], config: Mapping[str, Any],
) -> None:
    if (set(config) != {"minimum_reference_entities", "mad_threshold", "cosine_estimand"}
            or config["cosine_estimand"] not in ("centered", "affine")
            or artifact.get("component_version") != "saved_alignment_entity_null_v2"
            or artifact.get("reference_schema_version") != "entity_null_reference_v2"
            or artifact.get("scientific_certification") is not False
            or artifact.get("bucket_policy") != "explicit_external_plan_no_automatic_merge"
            or artifact.get("configuration") != dict(config)
            or artifact.get("configuration_sha256") != _sha(dict(config))
            or artifact.get("entity_to_bucket") != dict(buckets)
            or artifact.get("bucket_plan_sha256") != _sha(dict(buckets))):
        raise ValueError("Null v2 identity, policy or configuration mismatch")
    transition = artifact.get("transition_id")
    if (not isinstance(transition, str) or len(transition.split("->")) != 2
            or len(set(transition.split("->"))) != 2 or not all(p.strip() for p in transition.split("->"))):
        raise ValueError("Invalid transition")
    expected = {(sid, a, b) for sid in transition.split("->") for a, b in ((13, 37), (13, 101), (37, 101))}
    hashes = {"alignment_sha256", "anchor_plan_hash", "source_checkpoint_sha256", "target_checkpoint_sha256"}
    required = {"transition_id", "entity_id", "endpoint_snapshot", "source_seed", "target_seed",
                "noise_displacement", *hashes}
    raw: dict[str, dict[tuple[str, int, int], dict[str, Any]]] = {}
    comparison_fingerprints: dict[tuple[str, int, int], tuple[str, str]] = {}
    checkpoint_fingerprints: dict[tuple[str, int], str] = {}
    for observation in observations:
        if (not required.issubset(observation) or set(observation) - required - {"pretransition_degree", "bucket_id"}
                or observation["transition_id"] != transition
                or not isinstance(observation["entity_id"], str) or not observation["entity_id"].strip()
                or not isinstance(observation["endpoint_snapshot"], str)
                or type(observation["source_seed"]) is not int or type(observation["target_seed"]) is not int
                or type(observation["noise_displacement"]) not in (int, float)
                or not math.isfinite(observation["noise_displacement"]) or not 0 <= observation["noise_displacement"] <= 2):
            raise ValueError("Invalid independent raw input")
        if any(not isinstance(observation[k], str) or len(observation[k]) != 64
               or set(observation[k]) - set("0123456789abcdef") for k in hashes):
            raise ValueError("Invalid raw input fingerprints")
        entity = observation["entity_id"]
        key = observation["endpoint_snapshot"], observation["source_seed"], observation["target_seed"]
        pairs = raw.setdefault(entity, {})
        if key not in expected or key in pairs:
            raise ValueError("Duplicate or unexpected independent seed pair")
        identity = observation["alignment_sha256"], observation["anchor_plan_hash"]
        if key in comparison_fingerprints and comparison_fingerprints[key] != identity:
            raise ValueError("Independent alignment provenance conflict")
        comparison_fingerprints[key] = identity
        for seed, fingerprint in ((observation["source_seed"], observation["source_checkpoint_sha256"]),
                                  (observation["target_seed"], observation["target_checkpoint_sha256"])):
            checkpoint_key = observation["endpoint_snapshot"], seed
            if checkpoint_key in checkpoint_fingerprints and checkpoint_fingerprints[checkpoint_key] != fingerprint:
                raise ValueError("Independent checkpoint provenance conflict")
            checkpoint_fingerprints[checkpoint_key] = fingerprint
        if ("pretransition_degree" in observation
                and (type(observation["pretransition_degree"]) is not int or observation["pretransition_degree"] < 0)):
            raise ValueError("Invalid raw degree")
        if "bucket_id" in observation and observation["bucket_id"] != buckets.get(entity):
            raise ValueError("Inconsistent raw bucket annotation")
        pairs[key] = dict(observation)
    if (not raw or set(raw) != set(buckets) or any(set(v) != expected for v in raw.values())
            or any(not isinstance(b, str) or not b.strip() for b in buckets.values())):
        raise ValueError("Independent population/pair mismatch")
    canonical = [raw[e][pair] for e in sorted(raw) for pair in sorted(expected)]
    if artifact.get("raw_observations") != canonical or artifact.get("raw_observations_sha256") != _sha(canonical):
        raise ValueError("Raw observations were not preserved")
    statistics = artifact.get("entity_noise_statistics", {})
    lto = artifact.get("lto_statistics", {})
    if set(statistics) != set(raw) or set(lto) != set(raw):
        raise ValueError("Missing or unexpected entity statistics")
    medians = {}
    for entity in sorted(raw):
        rows = [raw[entity][pair] for pair in sorted(expected)]
        medians[entity] = float(np.median([r["noise_displacement"] for r in rows]))
        actual = statistics[entity]
        if (actual.get("entity_id") != entity or type(actual.get("raw_noise_observation_count")) is not int
                or actual["raw_noise_observation_count"] != 6
                or actual.get("raw_observation_sha256s") != [_sha(r) for r in rows]):
            raise ValueError("Broken per-entity raw provenance")
        _close(actual.get("noise_median"), medians[entity])
    for entity, bucket in buckets.items():
        ids = sorted(e for e in raw if buckets[e] == bucket and e != entity)
        row = lto[entity]
        if (row.get("entity_id") != entity or row.get("transition_id") != transition
                or row.get("bucket_id") != bucket or row.get("reference_entity_ids") != ids):
            raise ValueError("Target entered reference or reference membership was changed")
        _reference_units(row, config["minimum_reference_entities"], config["mad_threshold"])
        array = np.asarray([medians[e] for e in ids], dtype=float)
        center = float(np.median(array)) if len(array) else None
        mad = float(np.median(np.abs(array - center))) if len(array) else None
        _close(row["median"], center)
        _close(row["mad"], mad)
        _close(row["robust_scale"], None if mad is None else 1.4826 * mad)


def verify_entity_metric_row(
    row: Mapping[str, Any], temporal: Mapping[int, float], reference: Mapping[str, Any],
    epsilon: float, floor: float, minimum: int,
) -> None:
    if (set(temporal) != {13, 37, 101} or any(type(k) is not int for k in temporal)
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 2 for v in temporal.values())
            or type(epsilon) not in (int, float) or not math.isfinite(epsilon) or epsilon <= 0
            or row.get("drift_component_version") != "entity_reference_longitudinal_drift_v2"):
        raise ValueError("Invalid independent v2 temporal inputs")
    reason = _reference_units(reference, minimum, floor)
    delta = float(np.median(list(temporal.values())))
    excess = None if reference["median"] is None else delta - reference["median"]
    sed = None if reason else max(0.0, excess) / (1.4826 * reference["mad"] + epsilon)
    for key, expected in (("delta_time", delta), ("signed_excess", excess), ("SED_plus", sed)):
        _close(row.get(key), expected)
    if type(row.get("available")) is not bool or row["available"] != (not reason) or row.get("unavailable_reason") != reason:
        raise ValueError("Independent drift availability mismatch")
