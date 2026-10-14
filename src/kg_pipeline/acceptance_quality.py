"""Independent document-level gold metrics; thresholds are inputs, never defaults."""
from __future__ import annotations

from collections import Counter
import math
from typing import Any

from .hashing import sha256_json
from .rebuild_artifacts import RebuildBlocked

METRICS = ("entity_accuracy", "relation_precision", "relation_recall", "temporal_accuracy",
           "span_accuracy", "decision_accuracy", "source_copy_accuracy")
FACT_FIELDS = ("article_id", "subject_id", "relation_id", "object_id", "object_value", "scope")
TEMPORAL_FIELDS = ("valid_from", "valid_to", "evidence_observed_at", "evidence_time_basis")


def _index(rows: list[dict[str, Any]], fields: tuple[str, ...], label: str) -> dict[tuple, dict[str, Any]]:
    indexed = {}
    for row in rows:
        if not set(fields) <= set(row):
            raise RebuildBlocked(f"Missing {label} identity fields")
        key = tuple(row[f] for f in fields)
        if key in indexed:
            raise RebuildBlocked(f"Duplicate {label} identity")
        indexed[key] = row
    return indexed


def evaluate_independent_quality(
    predictions: dict[str, Any], gold: dict[str, Any], annex: dict[str, Any], *, phase: str,
) -> dict[str, Any]:
    """Evaluate whole annotated documents, including facts absent from predictions.

    Annotation and threshold approvals are verified by the artifact-backed caller.
    This pure evaluator alone cannot issue a scientific certificate.
    """
    if phase not in {"pilot", "main"} or gold.get("phase") != phase or predictions.get("phase") != phase:
        raise RebuildBlocked("Pilot/main evaluation inputs cannot be mixed")
    articles = gold.get("articles")
    if not isinstance(articles, list) or not articles:
        raise RebuildBlocked("Independent document gold is empty")
    selected = gold.get("selected_article_ids")
    if (not isinstance(selected, list) or len(set(selected)) != len(selected) or len(articles) != len(selected)
            or set(selected) != {a["article_id"] for a in articles}):
        raise RebuildBlocked("Missing or duplicate gold document units")
    if predictions.get("processed_article_ids") != sorted(selected):
        raise RebuildBlocked("Predictions do not cover every selected document")
    if gold.get("prediction_blind") is not True or gold.get("sampling_locked_before_scoring") is not True:
        raise RebuildBlocked("Gold annotation must be independent and sampling locked")
    if not gold.get("guideline_sha256") or not gold.get("sampling_plan_sha256"):
        raise RebuildBlocked("Gold guideline and sampling hashes required")
    for article in articles:
        annotators = article.get("annotator_ids")
        if (not isinstance(annotators, list) or len(annotators) != 2 or len(set(annotators)) != 2
                or any(not isinstance(a, str) or not a for a in annotators)
                or not article.get("adjudicator_id") or not article.get("annotation_refs")):
            raise RebuildBlocked("Two independent annotators and adjudication references required")
    forbidden = set(gold.get("excluded_development_article_ids", []))
    if phase == "main" and (not forbidden or set(selected) & forbidden):
        raise RebuildBlocked("Final gold must be separate from development/pilot documents")
    required = annex.get("metrics")
    if not isinstance(required, dict) or set(required) != set(METRICS):
        raise RebuildBlocked("Complete approved threshold/coverage annex required")
    strata = Counter((a["source_id"], a["time_stratum"]) for a in articles)
    coverage = annex.get("strata_minimums")
    if not isinstance(coverage, list) or not coverage:
        raise RebuildBlocked("Explicit strata coverage requirements required")
    for rule in coverage:
        minimum = rule.get("minimum_documents")
        if type(minimum) is not int or minimum <= 0:
            raise RebuildBlocked("Invalid strata minimum")
        if strata[(rule["source_id"], rule["time_stratum"])] < minimum:
            raise RebuildBlocked("Missing required gold stratum coverage")
    gold_facts = _index(gold.get("facts", []), FACT_FIELDS, "gold fact")
    predicted_facts = _index(predictions.get("facts", []), FACT_FIELDS, "predicted fact")
    if any(row["article_id"] not in selected for row in [*gold_facts.values(), *predicted_facts.values()]):
        raise RebuildBlocked("Fact outside locked evaluation documents")
    gold_entities = _index(gold.get("entities", []), ("mention_id",), "gold mention")
    predicted_entities = _index(predictions.get("entities", []), ("mention_id",), "predicted mention")
    if not set(predicted_entities) <= set(gold_entities):
        raise RebuildBlocked("Unannotated predicted mention requires gold completion")
    matched = set(gold_facts) & set(predicted_facts)
    counts = {
        "entity_accuracy": [sum(k in predicted_entities and
            predicted_entities[k]["canonical_entity_id"] == r["canonical_entity_id"] for k, r in gold_entities.items()), len(gold_entities)],
        "relation_precision": [len(matched), len(predicted_facts)],
        "relation_recall": [len(matched), len(gold_facts)],
        "temporal_accuracy": [0, len(gold_facts) * len(TEMPORAL_FIELDS)],
        "span_accuracy": [0, len(gold_facts)],
        "decision_accuracy": [0, 0], "source_copy_accuracy": [0, 0],
    }
    for key in matched:
        actual, expected = predicted_facts[key], gold_facts[key]
        if not set(TEMPORAL_FIELDS) <= set(actual) or not set(TEMPORAL_FIELDS) <= set(expected):
            raise RebuildBlocked("Temporal annotation fields missing")
        counts["temporal_accuracy"][0] += sum(actual[f] == expected[f] for f in TEMPORAL_FIELDS)
        span_fields = ("evidence_span_start", "evidence_span_end", "evidence_text_hash")
        if not set(span_fields) <= set(actual) or not set(span_fields) <= set(expected):
            raise RebuildBlocked("Span annotation fields missing")
        counts["span_accuracy"][0] += int(all(actual[f] == expected[f] for f in span_fields))
    for metric, table, key_field, label in (
        ("decision_accuracy", "decisions", "review_unit_id", "decision"),
        ("source_copy_accuracy", "source_groups", "provenance_unit_id", "origin_group_id"),
    ):
        expected = _index(gold.get(table, []), (key_field,), f"gold {table}")
        actual = _index(predictions.get(table, []), (key_field,), f"predicted {table}")
        if not set(actual) <= set(expected):
            raise RebuildBlocked(f"Unannotated {table} evaluation unit")
        counts[metric] = [sum(k in actual and actual[k].get(label) == v[label] for k, v in expected.items()), len(expected)]
    report = {}
    for metric, (numerator, denominator) in counts.items():
        rule = required[metric]
        threshold, minimum = rule.get("minimum_value"), rule.get("minimum_denominator")
        if (type(threshold) not in {int, float} or not math.isfinite(threshold) or not 0 <= threshold <= 1
                or type(minimum) is not int or minimum <= 0 or not rule.get("selection_basis")):
            raise RebuildBlocked(f"Invalid approved quality criterion: {metric}")
        if denominator < minimum:
            raise RebuildBlocked(f"Insufficient denominator for {metric}")
        value = numerator / denominator
        report[metric] = {"numerator": numerator, "denominator": denominator, "value": value,
                          "threshold": threshold, "status": "PASS" if value >= threshold else "FAIL"}
    return {"status": "PASS" if all(r["status"] == "PASS" for r in report.values()) else "FAIL",
            "scope": "independent_quality_metrics_only", "phase": phase, "metrics": report,
            "evaluated_count": len(articles), "false_positives": len(set(predicted_facts) - set(gold_facts)),
            "false_negatives": len(set(gold_facts) - set(predicted_facts)),
            "gold_semantic_sha256": sha256_json(gold), "predictions_semantic_sha256": sha256_json(predictions),
            "annex_semantic_sha256": sha256_json(annex),
            "limitations": ["Sample estimates only; no claim that every corpus fact is correct"]}
