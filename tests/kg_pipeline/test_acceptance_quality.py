from __future__ import annotations

from copy import deepcopy

import pytest

from kg_pipeline.acceptance_quality import METRICS, evaluate_independent_quality
from kg_pipeline.rebuild_artifacts import RebuildBlocked


def inputs():
    fact = {"article_id": "a", "subject_id": "s", "relation_id": "r", "object_id": "o", "object_value": None,
            "scope": "scope", "valid_from": "2025-01-01T00:00:00+00:00", "valid_to": None,
            "evidence_observed_at": "2025-01-02T00:00:00+00:00", "evidence_time_basis": "public_capture",
            "evidence_span_start": 0, "evidence_span_end": 10, "evidence_text_hash": "a" * 64}
    gold = {"phase": "pilot", "prediction_blind": True, "sampling_locked_before_scoring": True,
            "guideline_sha256": "b" * 64, "sampling_plan_sha256": "c" * 64, "selected_article_ids": ["a"],
            "articles": [{"article_id": "a", "source_id": "source", "time_stratum": "2025-01",
                          "annotator_ids": ["reviewer1", "reviewer2"], "adjudicator_id": "reviewer3",
                          "annotation_refs": ["annotation1", "annotation2"]}], "facts": [fact],
            "entities": [{"mention_id": "m", "canonical_entity_id": "s"}],
            "decisions": [{"review_unit_id": "u", "decision": "pending"}],
            "source_groups": [{"provenance_unit_id": "p", "origin_group_id": "origin"}]}
    predicted = {k: deepcopy(gold[k]) for k in ("phase", "facts", "entities", "decisions", "source_groups")}
    predicted["processed_article_ids"] = ["a"]
    annex = {"metrics": {m: {"minimum_value": 0.9, "minimum_denominator": 1,
                            "selection_basis": "fixture criterion"} for m in METRICS},
             "strata_minimums": [{"source_id": "source", "time_stratum": "2025-01", "minimum_documents": 1}]}
    return predicted, gold, annex


def test_document_gold_counts_missing_facts_as_false_negatives():
    predicted, gold, annex = inputs()
    second = deepcopy(gold["facts"][0])
    second["object_id"] = "other"
    gold["facts"].append(second)
    report = evaluate_independent_quality(predicted, gold, annex, phase="pilot")
    assert report["status"] == "FAIL"
    assert report["false_negatives"] == 1
    assert report["metrics"]["relation_recall"]["value"] == 0.5
    assert report["metrics"]["temporal_accuracy"]["denominator"] == 8


def test_correct_records_pass_metrics_but_are_not_scientific_certificate():
    report = evaluate_independent_quality(*inputs(), phase="pilot")
    assert report["status"] == "PASS" and report["scope"] == "independent_quality_metrics_only"
    assert report["evaluated_count"] == 1


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "duplicate_article", "coverage", "threshold", "nan", "unprocessed", "blind", "reviewer"])
def test_missing_or_ambiguous_inputs_cannot_pass(mutation):
    p, g, a = inputs()
    if mutation == "empty":
        g["articles"] = []
    elif mutation == "duplicate":
        g["facts"].append(deepcopy(g["facts"][0]))
    elif mutation == "duplicate_article":
        g["articles"].append(deepcopy(g["articles"][0]))
    elif mutation == "coverage":
        a["strata_minimums"][0]["minimum_documents"] = 2
    elif mutation == "threshold":
        del a["metrics"][METRICS[0]]
    elif mutation == "nan":
        a["metrics"][METRICS[0]]["minimum_value"] = float("nan")
    elif mutation == "unprocessed":
        p["processed_article_ids"] = []
    elif mutation == "blind":
        g["prediction_blind"] = False
    else:
        g["articles"][0]["annotator_ids"] = ["same", "same"]
    with pytest.raises(RebuildBlocked):
        evaluate_independent_quality(p, g, a, phase="pilot")


def test_main_gold_cannot_reuse_development_articles():
    p, g, a = inputs()
    p["phase"] = g["phase"] = "main"
    g["excluded_development_article_ids"] = ["a"]
    with pytest.raises(RebuildBlocked, match="separate"):
        evaluate_independent_quality(p, g, a, phase="main")
