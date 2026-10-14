from __future__ import annotations

import copy
import json
import random
from dataclasses import asdict
from typing import Any

import pytest

from scripts.run_m2_alignment import align_one, comparison_jobs
from scripts.verify_m2_alignment import verify_anchor_plan, verify_record
from drift.fixed_anchors import largest_remainder_allocation, select_fixed_stratified_anchors
from kge.checkpoint import CheckpointProvenance, KGECheckpoint


def population() -> tuple[list[str], dict[str, int]]:
    ids = [f"e{i:03d}" for i in range(300)]
    return ids, {e: 1 if i < 200 else 3 if i < 280 else 6 for i, e in enumerate(ids)}


def test_fixed_count_allocation_preserves_quotas_and_is_order_independent() -> None:
    ids, degrees = population()
    plan = select_fixed_stratified_anchors(ids, degrees, 101, 66, "fixture:T01->T02")
    assert plan == select_fixed_stratified_anchors(list(reversed(ids)), dict(reversed(list(degrees.items()))),
                                                   101, 66, "fixture:T01->T02")
    assert len(plan.split.fit_anchors) == 101
    assert len(plan.split.holdout_anchors) == 66
    assert not set(plan.split.fit_anchors) & set(plan.split.holdout_anchors)
    assert {a.degree: a.selected for a in plan.allocations} == {1: 111, 3: 45, 6: 11}
    assert {a.degree: a.fit for a in plan.allocations} == {1: 67, 3: 27, 6: 7}
    saved = json.loads(json.dumps(asdict(plan)))
    verify_anchor_plan(saved, ids, degrees, {"salt": "fixture", "fit_count": 101, "holdout_count": 66}, "T01->T02")


def test_largest_remainder_tie_and_zero_stratum_are_deterministic() -> None:
    assert largest_remainder_allocation({3: 1, 1: 1, 2: 1}, 2) == {1: 1, 2: 1, 3: 0}
    assert largest_remainder_allocation({0: 0, 1: 3}, 2) == {0: 0, 1: 2}


@pytest.mark.parametrize("case", ["insufficient", "duplicate", "missing_degree", "negative_degree", "bool_degree"])
def test_invalid_anchor_populations_fail_closed(case: str) -> None:
    ids, degrees = population()
    if case == "insufficient":
        ids = ids[:100]
    elif case == "duplicate":
        ids.append(ids[0])
    elif case == "missing_degree":
        degrees.pop(ids[0])
    elif case == "negative_degree":
        degrees[ids[0]] = -1
    elif case == "bool_degree":
        degrees[ids[0]] = True
    with pytest.raises(ValueError):
        select_fixed_stratified_anchors(ids, degrees, 101, 66, "fixture")


def test_independent_anchor_verifier_rejects_swapped_roles_and_future_degrees() -> None:
    ids, degrees = population()
    criteria = {"salt": "fixture", "fit_count": 101, "holdout_count": 66}
    plan = asdict(select_fixed_stratified_anchors(ids, degrees, 101, 66, "fixture:T01->T02"))
    plan = json.loads(json.dumps(plan))
    a, b = plan["split"]["fit_anchors"][0], plan["split"]["holdout_anchors"][0]
    plan["split"]["fit_anchors"][0], plan["split"]["holdout_anchors"][0] = b, a
    with pytest.raises(ValueError, match="allocation"):
        verify_anchor_plan(plan, ids, degrees, criteria, "T01->T02")
    good = json.loads(json.dumps(asdict(select_fixed_stratified_anchors(ids, degrees, 101, 66, "fixture:T01->T02"))))
    future = {e: 2 for e in ids}
    with pytest.raises(ValueError, match="pretransition"):
        verify_anchor_plan(good, ids, future, criteria, "T01->T02")


def test_all_nine_comparisons_are_registered_without_missing_seeds() -> None:
    jobs = comparison_jobs("T01", "T02", [13, 37, 101])
    assert len(jobs) == 9
    assert sum(j["alignment_type"] == "cross_time" for j in jobs) == 3
    assert sum(j["alignment_type"] == "same_snapshot_cross_seed" for j in jobs) == 6
    with pytest.raises(ValueError):
        comparison_jobs("T01", "T02", [13, 37])


def synthetic_alignment(degenerate: bool = False) -> tuple[KGECheckpoint, KGECheckpoint, Any, dict, dict]:
    rng = random.Random(13)
    ids = [f"e{i}" for i in range(12)]
    vectors = {e: [float(i), 0.0, 0.0, 0.0] if degenerate else [rng.uniform(-1, 1) for _ in range(4)]
               for i, e in enumerate(ids)}
    target_vectors = {e: [-v[1] + 10, v[0] - 5, v[2] + 3, v[3] + 1] for e, v in vectors.items()}

    def checkpoint(sid: str, embeddings: dict) -> KGECheckpoint:
        prov = CheckpointProvenance(sid, "fixture", 13, "TransE", 4, 2, "fixture", "fixture", "fixture", "fixture", True)
        return KGECheckpoint(prov, embeddings, {"r": [0.0] * 4}, {})

    source, target = checkpoint("T01", vectors), checkpoint("T02", target_vectors)
    plan = select_fixed_stratified_anchors(ids, {e: 1 for e in ids}, 8, 4, "fixture:T01->T02")
    criteria = {"fit_count": 8, "holdout_count": 4, "minimum_numerical_rank": 4,
                "max_fit_holdout_gap": 1.0, "max_holdout_residual": 2.0, "max_orthogonality_error": 1e-4}
    job = {"transition_id": "T01->T02", **comparison_jobs("T01", "T02", [13, 37, 101])[0]}
    return source, target, plan, criteria, job


def test_known_rotation_translation_is_independently_verified() -> None:
    source, target, plan, criteria, job = synthetic_alignment()
    record = align_one(source, target, plan.split, criteria, job)
    assert record["available"] is True
    assert record["diagnostics"]["holdout_residual"] < 1e-10
    verify_record(record, asdict(source), asdict(target), asdict(plan), criteria, job)
    assert record == align_one(source, target, plan.split, criteria, job)


def test_degenerate_rank_is_unavailable_without_forcing_validity() -> None:
    source, target, plan, criteria, job = synthetic_alignment(True)
    record = align_one(source, target, plan.split, criteria, job)
    assert record["available"] is False
    assert record["unavailable_reason"] == "RANK_DEFICIENT:1<4"
    verify_record(record, asdict(source), asdict(target), asdict(plan), criteria, job)


def test_missing_holdout_is_fatal_instead_of_silently_scoring_zero() -> None:
    source, target, plan, criteria, job = synthetic_alignment()
    del target.entity_embeddings[plan.split.holdout_anchors[0]]
    with pytest.raises(ValueError, match="Missing"):
        align_one(source, target, plan.split, criteria, job)


def test_large_holdout_gap_is_unavailable_and_holdout_does_not_change_fit_means() -> None:
    source, target, plan, criteria, job = synthetic_alignment()
    original = align_one(source, target, plan.split, criteria, job)
    for entity in plan.split.holdout_anchors:
        target.entity_embeddings[entity] = [v + 10 for v in target.entity_embeddings[entity]]
    target.artifact_hash = target.compute_artifact_hash()
    changed = align_one(source, target, plan.split, criteria, job)
    assert changed["source_mean"] == original["source_mean"]
    assert changed["target_mean"] == original["target_mean"]
    assert changed["Q"] == original["Q"]
    assert changed["available"] is False
    assert changed["unavailable_reason"].startswith("EXCESSIVE_FIT_HOLDOUT_GAP:")
    verify_record(changed, asdict(source), asdict(target), asdict(plan), criteria, job)


@pytest.mark.parametrize("mutation", ["Q", "mean", "availability", "rank", "identity"])
def test_independent_svd_verifier_rejects_saved_result_tampering(mutation: str) -> None:
    source, target, plan, criteria, job = synthetic_alignment()
    record = copy.deepcopy(align_one(source, target, plan.split, criteria, job))
    if mutation == "Q":
        record["Q"][0][0] += 0.1
    elif mutation == "mean":
        record["source_mean"][0] += 0.1
    elif mutation == "availability":
        record["available"] = False
    elif mutation == "rank":
        record["diagnostics"]["numerical_rank"] = 3
    elif mutation == "identity":
        record["source_seed"] = 37
    with pytest.raises(ValueError):
        verify_record(record, asdict(source), asdict(target), asdict(plan), criteria, job)
