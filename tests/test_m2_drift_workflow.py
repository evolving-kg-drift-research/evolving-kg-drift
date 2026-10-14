from __future__ import annotations

import copy
import math
from dataclasses import asdict

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from drift.artifact_drift import calibrated_metrics, saved_temporal_observations
from kge.checkpoint import CheckpointProvenance, KGECheckpoint
from scripts.inspect_m2_inputs import encode, sha
from scripts.run_m2_drift import DRIFT_SCHEMA, TEMPORAL_SCHEMA
from scripts.run_m2_null import parquet_bytes
from scripts.verify_m2_drift import verify_metric_row


def fixture_temporal(shift: float = 0.0) -> tuple[dict, dict]:
    checkpoints, records = {}, {}
    for seed, cosine in zip((13, 37, 101), (0.9, 0.8, -0.7)):
        for sid, vector in (("T01", [1.0, 0.0]), ("T02", [cosine + shift, math.sqrt(1 - cosine**2) + shift])):
            prov = CheckpointProvenance(sid, "fixture", seed, "TransE", 2, 2, "fixture", "fixture", "fixture")
            checkpoints[sid, seed] = KGECheckpoint(prov, {"e": vector}, {"r": [0.0, 0.0]}, {})
        source, target = checkpoints["T01", seed], checkpoints["T02", seed]
        record = {"transition_id": "T01->T02", "alignment_type": "cross_time", "source_snapshot": "T01",
                  "target_snapshot": "T02", "source_seed": seed, "target_seed": seed,
                  "dimension": 2, "available": True, "unavailable_reason": "", "Q": [[1.0, 0.0], [0.0, 1.0]],
                  "source_mean": [0.0, 0.0], "target_mean": [shift, shift],
                  "source_checkpoint_semantic_hash": source.artifact_hash,
                  "target_checkpoint_semantic_hash": target.artifact_hash,
                  "source_checkpoint_sha256": sha(encode(asdict(source))),
                  "target_checkpoint_sha256": sha(encode(asdict(target))), "anchor_plan_hash": sha(b"fixture")}
        records[seed] = record, sha(encode(record))
    return records, checkpoints


def stats(median: float | None = 0.3, mad: float | None = 0.1, reason: str = "") -> dict:
    return {"median": median, "mad": mad, "robust_scale": None if mad is None else 1.4826 * mad,
            "available": not reason, "unavailable_reason": reason, "removed_target_observations": 6,
            "observation_count": 0 if median is None else 12, "reference_entity_count": 0 if median is None else 2}


def test_three_parallel_seeds_use_median_and_preserve_negative_excess() -> None:
    records, checkpoints = fixture_temporal()
    rows = saved_temporal_observations("T01->T02", ["e"], ("T01", "T02"), records, checkpoints, 1e-12)
    assert [r["seed"] for r in rows] == [13, 37, 101]
    assert [r["temporal_displacement"] for r in rows] == pytest.approx([0.1, 0.2, 1.7])
    values = [r["temporal_displacement"] for r in rows]
    metric = calibrated_metrics(values, stats(), 1e-4, 1e-12, 5)
    assert metric["delta_time"] == pytest.approx(0.2)
    assert metric["signed_excess"] == pytest.approx(-0.1)
    assert metric["SED_plus"] == 0
    verify_metric_row(metric, values, stats(), 1e-4, 1e-12, 5)


def test_centering_removes_translation_in_saved_temporal_route() -> None:
    first, cp1 = fixture_temporal()
    shifted, cp2 = fixture_temporal(1000)
    rows1 = saved_temporal_observations("T01->T02", ["e"], ("T01", "T02"), first, cp1, 1e-12)
    rows2 = saved_temporal_observations("T01->T02", ["e"], ("T01", "T02"), shifted, cp2, 1e-12)
    assert [r["temporal_displacement"] for r in rows1] == pytest.approx([r["temporal_displacement"] for r in rows2])


def test_positive_excess_uses_registered_mad_scale_and_epsilon() -> None:
    metric = calibrated_metrics([0.8, 0.7, 1.5], stats(), 1e-4, 1e-12, 5)
    assert metric["signed_excess"] == pytest.approx(0.5)
    assert metric["SED_plus"] == pytest.approx(0.5 / (1.4826 * 0.1 + 1e-4))


def test_insufficient_null_keeps_signed_excess_without_calibrated_sed() -> None:
    reference = stats(0.2, 0.1, "INSUFFICIENT_LTO_SAMPLES")
    reference.update(reference_entity_count=1, observation_count=6)
    metric = calibrated_metrics([0.5, 0.6, 0.7], reference, 1e-4, 1e-12, 7)
    assert metric["signed_excess"] == pytest.approx(0.4) and metric["SED_plus"] is None


def test_parquet_preserves_unavailable_nulls_and_signed_excess() -> None:
    metric = calibrated_metrics([0.5, 0.6, 0.7], stats(None, None, "LTO_EMPTY_BUCKET"), 1e-4, 1e-12, 5)
    row = {"transition_id": "T01->T02", "entity_id": "e", **metric, "pretransition_degree": 1,
           "bucket_id": "low", "null_median": None, "null_mad": None, "null_robust_scale": None,
           "removed_target_observations": 6, "reference_entity_count": 0, "observation_count": 0,
           "null_artifact_sha256": sha(b"fixture")}
    payload = parquet_bytes([row], DRIFT_SCHEMA)
    assert payload == parquet_bytes([row], DRIFT_SCHEMA)
    table = pq.read_table(pa.BufferReader(payload))
    assert table.to_pylist() == [row]
    assert table.schema.field("signed_excess").nullable is True
    with pytest.raises(ValueError):
        parquet_bytes([{**row, "delta_time": None}], DRIFT_SCHEMA)
    records, checkpoints = fixture_temporal()
    temporal = saved_temporal_observations("T01->T02", ["e"], ("T01", "T02"), records, checkpoints, 1e-12)
    assert pq.read_table(pa.BufferReader(parquet_bytes(temporal, TEMPORAL_SCHEMA))).to_pylist() == temporal


@pytest.mark.parametrize("reference", [stats(0.2, 0.0, "ZERO_MAD"), stats(None, None, "LTO_EMPTY_BUCKET")])
def test_unavailable_null_is_never_rescued_by_epsilon(reference: dict) -> None:
    metric = calibrated_metrics([0.5, 0.6, 0.7], reference, 1e-4, 1e-12, 5)
    assert metric["SED_plus"] is None and metric["available"] is False
    assert metric["signed_excess"] == (None if reference["median"] is None else pytest.approx(0.4))
    verify_metric_row(metric, [0.5, 0.6, 0.7], reference, 1e-4, 1e-12, 5)


@pytest.mark.parametrize("case", ["missing_seed", "cross_seed", "missing_entity", "unavailable", "zero_norm", "wrong_snapshot", "hash", "nan"])
def test_invalid_saved_temporal_input_is_fatal(case: str) -> None:
    records, checkpoints = fixture_temporal()
    record = records[13][0]
    if case == "missing_seed":
        records.pop(101)
    elif case == "cross_seed":
        record["target_seed"] = 37
    elif case == "missing_entity":
        checkpoints["T02", 13].entity_embeddings.clear()
    elif case == "unavailable":
        record.update(available=False, unavailable_reason="RANK_DEFICIENT")
    elif case == "zero_norm":
        record["source_mean"] = [1.0, 0.0]
    elif case == "wrong_snapshot":
        record["target_snapshot"] = "T03"
    elif case == "hash":
        record["target_checkpoint_semantic_hash"] = "x" * 64
    else:
        record["Q"][0][0] = float("nan")
    with pytest.raises(ValueError):
        saved_temporal_observations("T01->T02", ["e"], ("T01", "T02"), records, checkpoints, 1e-12)


@pytest.mark.parametrize("case", ["missing_seed", "nan", "negative_mad", "false_available", "wrong_scale", "wrong_exclusion", "support", "fabricated_empty"])
def test_calibration_rejects_inconsistent_reference_or_temporal_data(case: str) -> None:
    values, reference = [0.1, 0.2, 0.8], stats()
    if case == "missing_seed":
        values.pop()
    elif case == "nan":
        values[0] = float("nan")
    elif case == "negative_mad":
        reference["mad"] = -1
    elif case == "false_available":
        reference.update(mad=0, robust_scale=0)
    elif case == "wrong_scale":
        reference["robust_scale"] = 5
    elif case == "wrong_exclusion":
        reference["removed_target_observations"] = 1
    elif case == "support":
        reference["observation_count"] = 13
    else:
        reference.update(reference_entity_count=0, observation_count=0)
    with pytest.raises(ValueError):
        calibrated_metrics(values, reference, 1e-4, 1e-12, 5)


@pytest.mark.parametrize("case", ["clip_signed", "mean", "fake_sed"])
def test_independent_metric_verifier_detects_semantic_corruption(case: str) -> None:
    values, reference = [0.1, 0.2, 1.7], stats()
    row = copy.deepcopy(calibrated_metrics(values, reference, 1e-4, 1e-12, 5))
    row[{"clip_signed": "signed_excess", "mean": "delta_time", "fake_sed": "SED_plus"}[case]] = 0.5
    with pytest.raises(ValueError):
        verify_metric_row(row, values, reference, 1e-4, 1e-12, 5)
