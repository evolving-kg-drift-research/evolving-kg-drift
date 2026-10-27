from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from drift.measurement_v2 import collect_alignment_geometry_v2
from scripts.prepare_m2_alignment_pilot_v2 import build_inventory, source_candidates
from test_m2_measurement_v2 import inputs


def test_raw_geometry_needs_no_operating_range_or_gap_choice() -> None:
    cps, alignments, plan, _ = inputs()
    record = alignments["T01", "T02", 13, 13][0]
    stats = collect_alignment_geometry_v2(cps["T01", 13][0], cps["T02", 13][0], record, plan, None)
    assert "available" not in stats and "SED_plus" not in stats and "gap_statistic" not in stats
    assert stats["numerical_rank"] is None and stats["rank_fraction"] is None
    assert stats["relative_fit_residual"] is not None
    assert stats["absolute_holdout_minus_fit"] == abs(stats["signed_holdout_minus_fit"])
    q = np.asarray(record["Q"])
    fit, hold = plan["split"]["fit_anchors"], plan["split"]["holdout_anchors"]
    x, y = cps["T01", 13][0].entity_embeddings, cps["T02", 13][0].entity_embeddings
    ms, mt = np.array([x[e] for e in fit]).mean(0), np.array([y[e] for e in fit]).mean(0)
    for name, ids in (("fit", fit), ("holdout", hold)):
        xc, yc = np.array([x[e] for e in ids]) - ms, np.array([y[e] for e in ids]) - mt
        expected = np.linalg.norm(xc @ q - yc) / np.linalg.norm(yc)
        assert stats[f"relative_{name}_residual"] == pytest.approx(expected, abs=1e-12)
    singular = np.linalg.svd((np.array([x[e] for e in fit]) - ms).T @ (np.array([y[e] for e in fit]) - mt), compute_uv=False)
    assert stats["singular_values"] == pytest.approx(singular.tolist())
    assert stats["relative_singular_values"] == pytest.approx((singular / singular.max()).tolist())
    schema = yaml.safe_load(Path("configs/schemas/m2_alignment_geometry_statistics_v2.schema.yaml").read_bytes())
    assert set(stats) == set(schema["required"])
    assert not set(stats) & set(schema["forbidden_fields"])


def test_collection_does_not_filter_on_legacy_gate_status() -> None:
    cps, alignments, plan, _ = inputs()
    record = copy.deepcopy(alignments["T01", "T02", 13, 13][0])
    source, target = cps["T01", 13][0], cps["T02", 13][0]
    before = collect_alignment_geometry_v2(source, target, record, plan, None)
    record.update(available=False, unavailable_reason="legacy_RMSE_gate_failed")
    assert collect_alignment_geometry_v2(source, target, record, plan, None) == before


@pytest.mark.parametrize("tolerance", [None, 1e-6, 0.2])
def test_optional_numerical_rank_is_explicit_and_does_not_assign_gate_status(tolerance: float | None) -> None:
    cps, alignments, plan, _ = inputs()
    stats = collect_alignment_geometry_v2(cps["T01", 13][0], cps["T02", 13][0],
                                           alignments["T01", "T02", 13, 13][0], plan, tolerance)
    assert stats["rank_relative_tolerance"] == tolerance
    expected = None if tolerance is None else sum(v > tolerance * max(stats["singular_values"]) for v in stats["singular_values"])
    assert stats["numerical_rank"] == expected
    assert not {"available", "G3_pass", "maximum_relative_holdout_residual"} & set(stats)


@pytest.mark.parametrize("tolerance", [True, 0, -1, 1, float("nan")])
def test_invalid_rank_tolerance_is_not_silently_defaulted(tolerance: object) -> None:
    cps, alignments, plan, _ = inputs()
    with pytest.raises(ValueError):
        collect_alignment_geometry_v2(cps["T01", 13][0], cps["T02", 13][0],
                                       alignments["T01", "T02", 13, 13][0], plan, tolerance)


def test_zero_target_fit_norm_keeps_raw_numerator_and_undefined_ratio() -> None:
    cps, alignments, plan, _ = inputs()
    source, target = cps["T01", 13][0], cps["T02", 13][0]
    record = copy.deepcopy(alignments["T01", "T02", 13, 13][0])
    for entity in plan["split"]["fit_anchors"]:
        target.entity_embeddings[entity] = [3.0, 4.0]
    target.artifact_hash = target.compute_artifact_hash()
    record["target_mean"] = [3.0, 4.0]
    stats = collect_alignment_geometry_v2(source, target, record, plan, None)
    assert stats["fit_target_norm"] == 0 and stats["fit_error_norm"] > 0
    assert stats["relative_fit_residual"] is None and stats["signed_holdout_minus_fit"] is None
    assert "ZERO_TARGET_FIT_NORM" in stats["undefined_statistics"]
    assert stats["relative_singular_values"] == [None, None]


def inventory_fixture() -> tuple[dict, dict, list, dict]:
    config = {"snapshots": ["T01", "T02", "T03"], "seeds": [13, 37, 101],
              "backbone_run": "outputs/backbone_fixture", "alignment_run": "outputs/alignment_fixture"}
    manifests = {"backbone": {"artifacts": {"hashes": {}}}, "alignment": {"artifacts": {"hashes": {}}}}
    jobs, plans = [], {}
    for prev, nxt in zip(config["snapshots"], config["snapshots"][1:]):
        transition = prev + "->" + nxt
        plans[transition] = {"split": {"fit_anchors": ["A", "B", "C"], "holdout_anchors": ["D"]}}
        comparisons = [(prev, nxt, s, s, "cross_time") for s in config["seeds"]]
        comparisons += [(sid, sid, a, b, "same_snapshot_cross_seed") for sid in (prev, nxt)
                        for a, b in ((13, 37), (13, 101), (37, 101))]
        for src, tgt, a, b, kind in comparisons:
            cid = f"{src}_seed{a}__{tgt}_seed{b}"
            jobs.append({"transition_id": transition, "source_snapshot": src, "target_snapshot": tgt,
                         "source_seed": a, "target_seed": b, "alignment_type": kind, "comparison_id": cid})
            relative = f"alignments/{prev}__{nxt}/{cid}_repeat_1.json"
            manifests["alignment"]["artifacts"]["hashes"][relative] = hashlib.sha256(relative.encode()).hexdigest()
    for sid in config["snapshots"]:
        for seed in config["seeds"]:
            relative = f"checkpoints/{sid}/seed_{seed}_repeat_1.json"
            manifests["backbone"]["artifacts"]["hashes"][relative] = hashlib.sha256(relative.encode()).hexdigest()
    return config, manifests, jobs, plans


def test_inventory_uses_all_registered_jobs_without_reading_or_selecting_outcomes() -> None:
    config, manifests, jobs, plans = inventory_fixture()
    result = build_inventory(config, manifests, jobs, plans)
    assert len(result["jobs"]) == 18 and len(result["checkpoints"]) == 9
    assert result["measurement_executed"] is False and result["scientific_certification"] is False
    assert not {"residual", "SED_plus", "G3_pass"} & set(result)
    assert result == build_inventory(config, manifests, list(reversed(jobs)), dict(reversed(list(plans.items()))))


@pytest.mark.parametrize("change", ["missing", "duplicate", "seed", "outcome_field", "missing_file", "extra_plan", "overlapping_anchors"])
def test_inventory_rejects_incomplete_population_or_outcome_input(change: str) -> None:
    config, manifests, jobs, plans = inventory_fixture()
    if change == "missing":
        jobs.pop()
    elif change == "duplicate":
        jobs[-1] = dict(jobs[0])
    elif change == "seed":
        jobs[0]["source_seed"] = 999
    elif change == "outcome_field":
        jobs[0]["SED_plus"] = 1.0
    elif change == "missing_file":
        manifests["alignment"]["artifacts"]["hashes"].clear()
    elif change == "extra_plan":
        plans["T03->T04"] = plans["T01->T02"]
    else:
        plans["T01->T02"]["split"]["holdout_anchors"].append("A")
    with pytest.raises(ValueError):
        build_inventory(config, manifests, jobs, plans)


def test_source_candidate_search_checks_exact_bytes_without_writing_substitutes() -> None:
    original = b"fixture original\r\nsecond line\r\n"
    variants = source_candidates(b"fixture original\nsecond line\n", None)
    expected = hashlib.sha256(original).hexdigest()
    assert any(hashlib.sha256(value).hexdigest() == expected for value in variants.values())
    assert all(isinstance(value, bytes) for value in variants.values())
    assert not any(hashlib.sha256(value).hexdigest() == "0" * 64 for value in variants.values())
    json.dumps({name: hashlib.sha256(value).hexdigest() for name, value in variants.items()})
