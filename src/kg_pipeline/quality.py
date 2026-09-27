from typing import Iterable, Any
import math
from temporal.schema import FactVersion

def evaluate_quality(
    accepted_facts: Iterable[FactVersion],
    gold_standard: Iterable[dict[str, Any]],
    error_threshold: float = 0.0
) -> dict[str, Any]:
    """
    Evaluate the auto-accepted facts against a human-annotated gold standard.

    This is a span diagnostic on matched records, not a scientific G2 evaluator.
    """
    if not math.isfinite(error_threshold) or not 0 <= error_threshold <= 1:
        raise ValueError("error_threshold must be finite and between zero and one")
    gold_map = {}
    for gold in gold_standard:
        key = (gold["subject_id"], gold["relation_id"], gold["object_id"], gold["evidence_observed_at"])
        if key in gold_map:
            raise ValueError("Duplicate gold key would make the evaluation ambiguous")
        gold_map[key] = gold

    errors = []
    evaluated = 0

    predicted_count = 0
    matched_keys = set()
    for fact in accepted_facts:
        predicted_count += 1
        key = (fact.subject_id, fact.relation_id, fact.object_id, fact.evidence_observed_at.isoformat())
        if key in gold_map:
            if key in matched_keys:
                raise ValueError("Duplicate prediction key would inflate evaluation coverage")
            matched_keys.add(key)
            evaluated += 1
            gold = gold_map[key]

            # Check span validity
            if gold.get("evidence_span_start") != fact.evidence_span_start or gold.get("evidence_span_end") != fact.evidence_span_end:
                errors.append({
                    "fact_id": fact.fact_version_id,
                    "type": "SPAN_MISMATCH",
                    "expected": [gold.get("evidence_span_start"), gold.get("evidence_span_end")],
                    "actual": [fact.evidence_span_start, fact.evidence_span_end]
                })

    error_rate = len(errors) / evaluated if evaluated > 0 else None
    complete_coverage = evaluated == predicted_count == len(gold_map)
    status = "BLOCKED"
    reason = "NO_EVALUATED_RECORDS" if evaluated == 0 else "INCOMPLETE_GOLD_COVERAGE"
    if evaluated and error_rate > error_threshold:
        status, reason = "FAIL", "SPAN_ERROR_THRESHOLD_EXCEEDED"
    elif evaluated and complete_coverage:
        status, reason = "PASS", "SPAN_DIAGNOSTIC_ONLY"

    return {
        "status": status,
        "reason": reason,
        "scope": "span_diagnostic_only",
        "prediction_count": predicted_count,
        "gold_count": len(gold_map),
        "unmatched_predictions": predicted_count - evaluated,
        "unmatched_gold": len(gold_map) - len(matched_keys),
        "evaluated_count": evaluated,
        "error_count": len(errors),
        "error_rate": error_rate,
        "errors": errors
    }
