from datetime import datetime, timezone
from typing import Iterable, Any
from temporal.schema import FactVersion

def _normalize_iso(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc).isoformat()
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            return val
    return str(val)

def evaluate_quality(
    accepted_facts: Iterable[FactVersion],
    gold_standard: Iterable[dict[str, Any]],
    error_threshold: float = 0.0
) -> dict[str, Any]:
    """
    Evaluate the auto-accepted facts against a human-annotated gold standard.
    """
    accepted_facts_list = list(accepted_facts)
    gold_standard_list = list(gold_standard)

    gold_map: dict[tuple, list[dict[str, Any]]] = {}
    for gold in gold_standard_list:
        norm_obs = _normalize_iso(gold.get("evidence_observed_at"))
        key = (gold.get("subject_id"), gold.get("relation_id"), gold.get("object_id"), norm_obs)
        gold_map.setdefault(key, []).append(gold)

    errors = []
    evaluated = 0

    for fact in accepted_facts_list:
        norm_fact_obs = _normalize_iso(fact.evidence_observed_at)
        key = (fact.subject_id, fact.relation_id, fact.object_id, norm_fact_obs)
        if key in gold_map:
            evaluated += 1
            golds_for_key = gold_map[key]
            span_matched = False
            for gold in golds_for_key:
                if gold.get("evidence_span_start") == fact.evidence_span_start and gold.get("evidence_span_end") == fact.evidence_span_end:
                    span_matched = True
                    break
            if not span_matched:
                errors.append({
                    "fact_id": fact.fact_version_id,
                    "type": "SPAN_MISMATCH",
                    "expected": [golds_for_key[0].get("evidence_span_start"), golds_for_key[0].get("evidence_span_end")],
                    "actual": [fact.evidence_span_start, fact.evidence_span_end]
                })
        else:
            # Predict a relation that is not in gold -> FALSE POSITIVE
            errors.append({
                "fact_id": fact.fact_version_id,
                "type": "FALSE_POSITIVE",
                "actual": key
            })

    # Missing from prediction -> FALSE NEGATIVE
    predicted_keys = {(f.subject_id, f.relation_id, f.object_id, _normalize_iso(f.evidence_observed_at)) for f in accepted_facts_list}
    for g_key, g_list in gold_map.items():
        if g_key not in predicted_keys:
            for _ in g_list:
                errors.append({
                    "fact_id": None,
                    "type": "FALSE_NEGATIVE",
                    "expected": g_key
                })

    total_gold = len(gold_standard_list)
    error_rate = len(errors) / total_gold if total_gold > 0 else 1.0

    if total_gold == 0:
        return {
            "status": "FAIL",
            "evaluated_count": 0,
            "error_count": len(errors) if len(errors) > 0 else 1,
            "error_rate": 1.0,
            "errors": errors,
            "reason": "Gold standard is empty"
        }

    return {
        "status": "PASS" if error_rate <= error_threshold else "FAIL",
        "evaluated_count": evaluated,
        "error_count": len(errors),
        "error_rate": error_rate,
        "errors": errors
    }
