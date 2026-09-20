from typing import Iterable, Any
from temporal.schema import FactVersion

def evaluate_quality(
    accepted_facts: Iterable[FactVersion],
    gold_standard: Iterable[dict[str, Any]],
    error_threshold: float = 0.0
) -> dict[str, Any]:
    """
    Evaluate the auto-accepted facts against a human-annotated gold standard.
    """
    gold_map = {}
    for gold in gold_standard:
        key = (gold["subject_id"], gold["relation_id"], gold["object_id"], gold["evidence_observed_at"])
        gold_map[key] = gold

    errors = []
    evaluated = 0

    for fact in accepted_facts:
        key = (fact.subject_id, fact.relation_id, fact.object_id, fact.evidence_observed_at.isoformat())
        if key in gold_map:
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

    error_rate = len(errors) / evaluated if evaluated > 0 else 0.0

    return {
        "status": "PASS" if error_rate <= error_threshold else "FAIL",
        "evaluated_count": evaluated,
        "error_count": len(errors),
        "error_rate": error_rate,
        "errors": errors
    }