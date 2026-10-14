from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any

import pyarrow.parquet as pq
import pyarrow as pa
import pytest

from scripts.inspect_m2_inputs import encode, sha
from scripts.run_m2_null import LTO_SCHEMA, OBSERVATION_SCHEMA, parquet_bytes
from scripts.verify_m2_null import verify_null_artifact
from drift.artifact_null import SEED_PAIRS, build_artifact_null, saved_noise_observations
from kge.checkpoint import CheckpointProvenance, KGECheckpoint


def cfg(minimum: int = 5) -> dict[str, Any]:
    return {"degree_bin_edges": [3, 6], "min_reference_observations": minimum, "degeneracy_mad_threshold": 1e-12}


def test_lto_removes_all_six_target_observations_and_is_target_blind() -> None:
    values = {"target": [1.7, 1.8, 1.9, 1.91, 1.92, 1.93],
              "other1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "other2": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]}
    degrees = {e: 1 for e in values}
    original = build_artifact_null("T01->T02", values, degrees, cfg())
    changed = copy.deepcopy(values)
    changed["target"] = [0.9] * 6
    alternate = build_artifact_null("T01->T02", changed, degrees, cfg())
    stats = original["lto_statistics"]["target"]
    assert stats == alternate["lto_statistics"]["target"]
    assert stats["reference_entity_count"] == 2 and stats["observation_count"] == 12
    assert stats["removed_target_observations"] == 6
    assert stats["median"] == pytest.approx(0.4)
    assert stats["mad"] == pytest.approx(0.15)
    verify_null_artifact(original, values, degrees, cfg())


def test_lto_empty_and_zero_mad_are_unavailable_without_fake_defaults() -> None:
    empty = build_artifact_null("T01->T02", {"e": [0.1] * 6}, {"e": 1}, cfg())
    row = empty["lto_statistics"]["e"]
    assert row["available"] is False and row["unavailable_reason"] == "LTO_EMPTY_BUCKET"
    assert row["median"] is None and row["mad"] is None and row["robust_scale"] is None
    values = {"a": [0.2] * 6, "b": [0.2] * 6}
    flat = build_artifact_null("T01->T02", values, {"a": 1, "b": 1}, cfg())
    assert flat["lto_statistics"]["a"]["unavailable_reason"] == "ZERO_MAD"
    verify_null_artifact(flat, values, {"a": 1, "b": 1}, cfg())


def test_sparse_merge_is_strictly_adjacent_and_tie_prefers_left() -> None:
    degrees = {**{f"low{i}": 1 for i in range(6)}, "mid": 3, **{f"high{i}": 6 for i in range(6)}}
    values = {e: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6] for e in degrees}
    artifact = build_artifact_null("T01->T02", values, degrees, cfg(17))
    assert artifact["bucket_merge_log"][0]["sparse_bucket"] == "medium"
    assert artifact["bucket_merge_log"][0]["partner_bucket"] == "low"
    assert artifact["entity_to_bucket"]["mid"] == "low+medium"
    verify_null_artifact(artifact, values, degrees, cfg(17))


def test_empty_middle_bucket_is_not_skipped_for_nonadjacent_merge() -> None:
    degrees = {"low": 1, **{f"high{i}": 6 for i in range(6)}}
    values = {e: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6] for e in degrees}
    artifact = build_artifact_null("T01->T02", values, degrees, cfg(7))
    assert [r["merged_bucket"] for r in artifact["bucket_merge_log"]] == ["low+medium", "low+medium+high"]
    verify_null_artifact(artifact, values, degrees, cfg(7))


def test_lto_insufficiency_does_not_trigger_target_specific_remerge() -> None:
    values = {"a": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "b": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]}
    degrees = {"a": 1, "b": 1}
    artifact = build_artifact_null("T01->T02", values, degrees, cfg(7))
    assert artifact["bucket_merge_log"] == []
    row = artifact["lto_statistics"]["a"]
    assert row["observation_count"] == 6
    assert row["unavailable_reason"] == "INSUFFICIENT_LTO_SAMPLES"
    assert row["median"] == pytest.approx(0.45)
    verify_null_artifact(artifact, values, degrees, cfg(7))


@pytest.mark.parametrize("case", ["missing_degree", "missing_pair", "nonfinite", "out_of_range"])
def test_incomplete_null_reference_data_is_fatal(case: str) -> None:
    values = {"a": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "b": [0.2] * 6}
    degrees = {"a": 1, "b": 3}
    if case == "missing_degree":
        degrees.pop("a")
    elif case == "missing_pair":
        values["a"].pop()
    elif case == "nonfinite":
        values["a"][0] = float("nan")
    else:
        values["a"][0] = 2.1
    with pytest.raises(ValueError):
        build_artifact_null("T01->T02", values, degrees, cfg())


def fixture_saved_pairs(zero: bool = False) -> tuple[list[str], dict, dict]:
    entities = ["e1", "e2", "e3"]
    checkpoints = {}
    for sid in ("T01", "T02"):
        for seed in (13, 37, 101):
            vectors = {e: [float(i + 1), seed / 100, float(i) / 3, 1.0] for i, e in enumerate(entities)}
            if zero:
                vectors["e1"] = [0.0] * 4
            prov = CheckpointProvenance(sid, "fixture", seed, "TransE", 4, 2, "fixture", "fixture", "fixture")
            checkpoints[sid, seed] = KGECheckpoint(prov, vectors, {"r": [0.0] * 4}, {})
    records = {}
    for sid in ("T01", "T02"):
        for a, b in SEED_PAIRS:
            source, target = checkpoints[sid, a], checkpoints[sid, b]
            record = {"available": True, "unavailable_reason": "", "alignment_type": "same_snapshot_cross_seed",
                      "transition_id": "T01->T02", "source_snapshot": sid, "target_snapshot": sid,
                      "source_seed": a, "target_seed": b, "dimension": 4,
                      "Q": [[float(i == j) for j in range(4)] for i in range(4)], "source_mean": [0.0] * 4,
                      "target_mean": [0.0] * 4, "source_checkpoint_semantic_hash": source.artifact_hash,
                      "target_checkpoint_semantic_hash": target.artifact_hash, "anchor_plan_hash": sha(b"fixture anchors"),
                      "source_checkpoint_sha256": sha(encode(asdict(source))), "target_checkpoint_sha256": sha(encode(asdict(target)))}
            records[sid, a, b] = (record, sha(encode(record)))
    return entities, records, checkpoints


def test_saved_null_observations_preserve_endpoint_pair_identity() -> None:
    entities, records, checkpoints = fixture_saved_pairs()
    rows = saved_noise_observations("T01->T02", entities, ("T01", "T02"), records, checkpoints, 1e-12)
    assert len(rows) == 18
    assert rows == saved_noise_observations("T01->T02", list(reversed(entities)), ("T01", "T02"), records, checkpoints, 1e-12)
    assert len({(r["entity_id"], r["endpoint_snapshot"], r["source_seed"], r["target_seed"]) for r in rows}) == 18


@pytest.mark.parametrize("case", ["missing_pair", "unavailable", "wrong_endpoint", "missing_entity", "zero_centered_norm"])
def test_saved_noise_rejects_invalid_input(case: str) -> None:
    entities, records, checkpoints = fixture_saved_pairs(case == "zero_centered_norm")
    key = ("T01", 13, 37)
    if case == "missing_pair":
        records.pop(key)
    elif case == "unavailable":
        records[key][0]["available"] = False
    elif case == "wrong_endpoint":
        records[key][0]["target_snapshot"] = "T02"
    elif case == "missing_entity":
        del checkpoints["T01", 13].entity_embeddings["e1"]
    with pytest.raises(ValueError):
        saved_noise_observations("T01->T02", entities, ("T01", "T02"), records, checkpoints, 1e-12)


def test_parquet_serialization_is_exact_and_unavailable_floats_remain_null() -> None:
    artifact = build_artifact_null("T01->T02", {"e": [0.1] * 6}, {"e": 1}, cfg())
    rows = [{"transition_id": "T01->T02", **artifact["lto_statistics"]["e"], "null_artifact_sha256": sha(encode(artifact))}]
    payload = parquet_bytes(rows, LTO_SCHEMA)
    assert payload == parquet_bytes(rows, LTO_SCHEMA)
    assert pq.read_table(pa.BufferReader(payload)).to_pylist()[0]["median"] is None
    entities, records, checkpoints = fixture_saved_pairs()
    observations = saved_noise_observations("T01->T02", entities, ("T01", "T02"), records, checkpoints, 1e-12)
    for row in observations:
        row.update(pretransition_degree=1, bucket_id="low")
    assert parquet_bytes(observations, OBSERVATION_SCHEMA) == parquet_bytes(observations, OBSERVATION_SCHEMA)


def test_independent_verifier_detects_target_inclusion_and_fake_empty_median() -> None:
    values = {"a": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "b": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2]}
    artifact = build_artifact_null("T01->T02", values, {"a": 1, "b": 1}, cfg())
    artifact["lto_statistics"]["a"]["median"] = artifact["bucket_statistics"]["low"]["median"]
    with pytest.raises(ValueError):
        verify_null_artifact(artifact, values, {"a": 1, "b": 1}, cfg())
    singleton = build_artifact_null("T01->T02", {"a": values["a"]}, {"a": 1}, cfg())
    singleton["lto_statistics"]["a"]["median"] = 0.0
    with pytest.raises(ValueError, match="fabricated"):
        verify_null_artifact(singleton, {"a": values["a"]}, {"a": 1}, cfg())
