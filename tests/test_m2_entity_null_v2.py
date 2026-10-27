from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from drift.artifact_drift import calibrated_metrics_v2
from drift.artifact_null import (
    ENTITY_NULL_VERSION,
    ENTITY_REFERENCE_VERSION,
    build_entity_level_null,
)
from scripts.run_m2_drift import DRIFT_SCHEMA_V2
from scripts.run_m2_null import LTO_SCHEMA_V2, parquet_bytes
from scripts.verify_m2_entity_null_v2 import verify_entity_metric_row, verify_entity_null_artifact


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def config(minimum: int = 2) -> dict:
    return {"minimum_reference_entities": minimum, "mad_threshold": 1e-12,
            "cosine_estimand": "centered"}


def observations(values: dict[str, list[float]]) -> list[dict]:
    rows = []
    for entity, distances in values.items():
        pairs = [(endpoint, a, b) for endpoint in ("T01", "T02")
                 for a, b in ((13, 37), (13, 101), (37, 101))]
        for distance, (endpoint, a, b) in zip(distances, pairs):
            rows.append({"transition_id": "T01->T02", "entity_id": entity,
                         "endpoint_snapshot": endpoint, "source_seed": a, "target_seed": b,
                         "noise_displacement": distance, "alignment_sha256": fingerprint((endpoint, a, b)),
                         "anchor_plan_hash": fingerprint("anchors"),
                         "source_checkpoint_sha256": fingerprint((endpoint, a)),
                         "target_checkpoint_sha256": fingerprint((endpoint, b))})
    return rows


def fixture() -> tuple[list[dict], dict[str, str]]:
    values = {"target": [1.8] * 6, "A": [0.1, 0.1, 0.1, 0.9, 0.9, 0.9],
              "B": [0.1, 0.1, 0.1, 0.1, 0.1, 0.9]}
    return observations(values), dict.fromkeys(values, "registered_bucket")


def build(raw: list[dict], buckets: dict[str, str], cfg: dict | None = None) -> dict:
    return build_entity_level_null("T01->T02", raw, buckets, config() if cfg is None else cfg)


def test_entity_medians_replace_pooled_distances_without_losing_raw_provenance() -> None:
    raw, buckets = fixture()
    artifact = build(raw, buckets)
    row = artifact["lto_statistics"]["target"]
    assert artifact["component_version"] == ENTITY_NULL_VERSION
    assert row["reference_schema_version"] == ENTITY_REFERENCE_VERSION
    assert row["reference_entity_ids"] == ["A", "B"]
    assert row["median"] == pytest.approx(0.3)
    assert row["mad"] == pytest.approx(0.2)
    assert row["reference_sample_count"] == row["reference_entity_count"] == 2
    assert row["raw_noise_observation_count"] == 12
    assert row["removed_target_raw_observation_count"] == 6
    assert "observation_count" not in row
    assert len(artifact["raw_observations"]) == len(raw)
    assert len(artifact["entity_noise_statistics"]["A"]["raw_observation_sha256s"]) == 6
    verify_entity_null_artifact(artifact, raw, buckets, config())


def test_target_exclusion_and_input_order_are_deterministic() -> None:
    raw, buckets = fixture()
    original = build(raw, buckets)
    changed = copy.deepcopy(raw)
    for row in changed:
        if row["entity_id"] == "target":
            row["noise_displacement"] = 0.02
    assert build(changed, buckets)["lto_statistics"]["target"] == original["lto_statistics"]["target"]
    assert build(list(reversed(raw)), dict(reversed(list(buckets.items())))) == original


@pytest.mark.parametrize("reference_count,sufficient", [(49, False), (50, True)])
def test_minimum_support_counts_entities_after_lto(reference_count: int, sufficient: bool) -> None:
    values = {f"e{i:03}": [0.01 * i] * 6 for i in range(reference_count + 1)}
    raw = observations(values)
    buckets = dict.fromkeys(values, "fixed")
    artifact = build(raw, buckets, config(50))
    row = artifact["lto_statistics"]["e000"]
    assert row["reference_entity_count"] == reference_count
    assert row["raw_noise_observation_count"] == 6 * reference_count
    assert row["available"] is sufficient
    assert row["unavailable_reason"] == ("" if sufficient else "INSUFFICIENT_REFERENCE_ENTITIES")
    verify_entity_null_artifact(artifact, raw, buckets, config(50))


def test_empty_and_entity_level_zero_mad_are_unavailable() -> None:
    artifact = build(observations({"only": [0.2] * 6}), {"only": "fixed"}, config(1))
    empty = artifact["lto_statistics"]["only"]
    assert empty["median"] is empty["mad"] is empty["robust_scale"] is None
    assert empty["unavailable_reason"] == "LTO_EMPTY_REFERENCE"
    # Raw distances vary, but each entity median is identical.
    raw = observations({e: [0.1, 0.2, 0.3, 0.5, 0.6, 0.7] for e in ("A", "B", "C")})
    artifact = build(raw, dict.fromkeys(("A", "B", "C"), "fixed"))
    row = artifact["lto_statistics"]["A"]
    assert row["unavailable_reason"] == "ZERO_MAD"
    assert row["available"] is False


@pytest.mark.parametrize("case", ["missing_pair", "duplicate_pair", "nonfinite", "bad_hash",
                                 "wrong_endpoint", "wrong_transition", "bad_seed", "unknown_field",
                                 "conflicting_alignment", "conflicting_checkpoint"])
def test_raw_pair_identity_and_lineage_fail_closed(case: str) -> None:
    raw, buckets = fixture()
    if case == "missing_pair":
        raw.pop()
    elif case == "duplicate_pair":
        raw.append(copy.deepcopy(raw[0]))
    elif case == "nonfinite":
        raw[0]["noise_displacement"] = float("nan")
    elif case == "bad_hash":
        raw[0]["alignment_sha256"] = "missing"
    elif case == "wrong_endpoint":
        raw[0]["endpoint_snapshot"] = "T03"
    elif case == "wrong_transition":
        raw[0]["transition_id"] = "T02->T03"
    elif case == "bad_seed":
        raw[0]["source_seed"] = True
    elif case == "conflicting_alignment":
        raw[0]["alignment_sha256"] = fingerprint("different_alignment")
    elif case == "conflicting_checkpoint":
        raw[0]["source_checkpoint_sha256"] = fingerprint("different_checkpoint")
    else:
        raw[0]["unregistered_field"] = 3
    with pytest.raises(ValueError):
        build(raw, buckets)
    # The verifier must reject malformed raw inputs even if an earlier, valid
    # artifact is supplied; it cannot rely only on production input validation.
    valid_raw, valid_buckets = fixture()
    with pytest.raises(ValueError):
        verify_entity_null_artifact(build(valid_raw, valid_buckets), raw, buckets, config())


@pytest.mark.parametrize("case", ["missing_bucket", "extra_entity", "missing_minimum", "old_count_key",
                                 "boolean_minimum", "missing_cosine", "invalid_floor"])
def test_no_inferred_bucket_policy_or_configuration_defaults(case: str) -> None:
    raw, buckets = fixture()
    cfg = config()
    if case == "missing_bucket":
        buckets.pop("A")
    elif case == "extra_entity":
        buckets["absent"] = "fixed"
    elif case == "missing_minimum":
        cfg.pop("minimum_reference_entities")
    elif case == "old_count_key":
        cfg["min_reference_observations"] = cfg.pop("minimum_reference_entities")
    elif case == "boolean_minimum":
        cfg["minimum_reference_entities"] = True
    elif case == "missing_cosine":
        cfg.pop("cosine_estimand")
    else:
        cfg["mad_threshold"] = 0
    with pytest.raises(ValueError):
        build(raw, buckets, cfg)


@pytest.mark.parametrize("field", ["median", "mad", "reference_sample_count", "raw_noise_observation_count",
                                  "reference_entity_ids", "raw_observation_sha256s", "configuration"])
def test_independent_verifier_rejects_corrupt_statistics_and_lineage(field: str) -> None:
    raw, buckets = fixture()
    artifact = build(raw, buckets)
    if field == "raw_observation_sha256s":
        artifact["entity_noise_statistics"]["A"][field][0] = fingerprint("tampered")
    elif field == "configuration":
        artifact[field]["minimum_reference_entities"] = 1
    elif field == "reference_entity_ids":
        artifact["lto_statistics"]["target"][field] = ["A", "target"]
    else:
        artifact["lto_statistics"]["target"][field] = 999
    with pytest.raises(ValueError):
        verify_entity_null_artifact(artifact, raw, buckets, config())


def test_v2_calibration_uses_entity_support_and_preserves_signed_excess() -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets)["lto_statistics"]["target"]
    temporal = {13: 0.1, 37: 0.2, 101: 1.7}
    metric = calibrated_metrics_v2(temporal, reference, 1e-4, 1e-12, 2)
    assert metric["delta_time"] == pytest.approx(0.2)
    assert metric["signed_excess"] == pytest.approx(-0.1)
    assert metric["SED_plus"] == 0
    verify_entity_metric_row(metric, temporal, reference, 1e-4, 1e-12, 2)
    positive = calibrated_metrics_v2({13: 0.8, 37: 0.7, 101: 1.5}, reference, 1e-4, 1e-12, 2)
    assert positive["SED_plus"] == pytest.approx(0.5 / (1.4826 * 0.2 + 1e-4))


def test_insufficient_support_cannot_be_rescued_by_raw_distances_or_epsilon() -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets, config(3))["lto_statistics"]["target"]
    metric = calibrated_metrics_v2({13: 0.8, 37: 0.7, 101: 1.5}, reference, 100, 1e-12, 3)
    assert metric["SED_plus"] is None and metric["available"] is False
    assert metric["signed_excess"] == pytest.approx(0.5)
    verify_entity_metric_row(metric, {13: 0.8, 37: 0.7, 101: 1.5}, reference, 100, 1e-12, 3)


@pytest.mark.parametrize("case", ["v1", "legacy_count", "bad_count", "fake_available", "duplicate_ids",
                                 "target_in_reference", "missing_seed", "bad_policy"])
def test_calibration_rejects_version_and_reference_contract_mismatch(case: str) -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets)["lto_statistics"]["target"]
    temporal = {13: 0.1, 37: 0.2, 101: 1.7}
    minimum = 2
    if case == "v1":
        reference["reference_schema_version"] = "v1"
    elif case == "legacy_count":
        reference["observation_count"] = 12
    elif case == "bad_count":
        reference["reference_sample_count"] = 12
    elif case == "fake_available":
        reference["available"] = False
    elif case == "duplicate_ids":
        reference["reference_entity_ids"] = ["A", "A"]
    elif case == "target_in_reference":
        reference["reference_entity_ids"] = ["A", "target"]
    elif case == "missing_seed":
        temporal.pop(101)
    else:
        minimum = 1
    with pytest.raises(ValueError):
        calibrated_metrics_v2(temporal, reference, 1e-4, 1e-12, minimum)


def test_parquet_and_yaml_contracts_preserve_count_units_and_unavailable_values() -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets, config(3))["lto_statistics"]["target"]
    row = {**reference, "null_artifact_sha256": fingerprint("artifact")}
    payload = parquet_bytes([row], LTO_SCHEMA_V2)
    assert payload == parquet_bytes([row], LTO_SCHEMA_V2)
    assert pq.read_table(pa.BufferReader(payload)).to_pylist() == [row]
    metrics = calibrated_metrics_v2({13: 0.8, 37: 0.7, 101: 1.5}, reference, 1e-4, 1e-12, 3)
    drift_row = {**row, **metrics}
    drift_payload = parquet_bytes([drift_row], DRIFT_SCHEMA_V2)
    assert pq.read_table(pa.BufferReader(drift_payload)).to_pylist() == [drift_row]
    spec = yaml.safe_load(Path("configs/schemas/m2_entity_null_v2.schema.yaml").read_bytes())
    assert spec["schema_version"] == ENTITY_REFERENCE_VERSION
    assert set(spec["reference_fields"]) == set(LTO_SCHEMA_V2.names) - {"null_artifact_sha256"}
    with pytest.raises(ValueError):
        parquet_bytes([{**row, "reference_sample_count": None}], LTO_SCHEMA_V2)


@pytest.mark.parametrize("estimand", ["centered", "affine"])
def test_estimand_is_declared_and_preserved_without_selecting_a_default(estimand: str) -> None:
    raw, buckets = fixture()
    cfg = {**config(), "cosine_estimand": estimand}
    artifact = build(raw, buckets, cfg)
    assert artifact["configuration"]["cosine_estimand"] == estimand
    assert artifact["scientific_certification"] is False
    assert json.loads(json.dumps(artifact, allow_nan=False)) == artifact
    verify_entity_null_artifact(artifact, raw, buckets, cfg)


@pytest.mark.parametrize("field", ["delta_time", "signed_excess", "SED_plus", "available"])
def test_independent_metric_verifier_rejects_corrupt_results(field: str) -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets)["lto_statistics"]["target"]
    temporal = {13: 0.1, 37: 0.2, 101: 1.7}
    row = calibrated_metrics_v2(temporal, reference, 1e-4, 1e-12, 2)
    row[field] = False if field == "available" else 100
    with pytest.raises(ValueError):
        verify_entity_metric_row(row, temporal, reference, 1e-4, 1e-12, 2)


@pytest.mark.parametrize("case", ["legacy_field", "wrong_version", "bad_count_units"])
def test_v2_parquet_rejects_rows_instead_of_silently_coercing_them(case: str) -> None:
    raw, buckets = fixture()
    reference = build(raw, buckets)["lto_statistics"]["target"]
    row = {**reference, "null_artifact_sha256": fingerprint("artifact")}
    if case == "legacy_field":
        row["observation_count"] = 12
    elif case == "wrong_version":
        row["reference_schema_version"] = "v1"
    else:
        row["reference_sample_count"] = 12
    with pytest.raises(ValueError):
        parquet_bytes([row], LTO_SCHEMA_V2)
