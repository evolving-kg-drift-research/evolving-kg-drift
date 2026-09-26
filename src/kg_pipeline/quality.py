"""Stage 4.13 Pilot Quality Gate evaluator and report generator."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable
import pyarrow.parquet as pq

from temporal.schema import FactVersion
from .run import get_run_dir
from .storage import write_json_immutable, read_json, utc_now_iso

logger = logging.getLogger(__name__)


def evaluate_quality(
    accepted_facts: Iterable[FactVersion],
    gold_standard: Iterable[dict[str, Any]],
    error_threshold: float = 0.0
) -> dict[str, Any]:
    """Evaluate auto-accepted facts against a human-annotated gold standard."""
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


def run_quality_gate(repo_root: Path, run_id: str, gold_standard_path: Path | None = None) -> dict[str, Any]:
    """Evaluate Stage 4.13 Pilot Quality Gate for a run and generate immutable report."""
    run_dir = get_run_dir(repo_root, run_id)
    fact_versions_path = run_dir / "tables" / "fact_versions.parquet"
    if not fact_versions_path.is_file():
        raise FileNotFoundError(f"Missing {fact_versions_path}")

    filter_decisions_path = run_dir / "tables" / "filter_decisions.parquet"
    if not filter_decisions_path.is_file():
        raise FileNotFoundError(f"Missing {filter_decisions_path}")

    extracted_claims_path = run_dir / "tables" / "extracted_claims.parquet"
    if not extracted_claims_path.is_file():
        raise FileNotFoundError(f"Missing {extracted_claims_path}")

    filter_table = pq.read_table(filter_decisions_path).to_pylist()
    claims_table = pq.read_table(extracted_claims_path).to_pylist()
    fact_table = pq.read_table(fact_versions_path).to_pylist()

    gold_standard = []
    if gold_standard_path and gold_standard_path.is_file():
        gold_standard = read_json(gold_standard_path)

    filter_summary = {
        "total_documents": len(filter_table),
        "included_count": len([d for d in filter_table if d["decision"] == "include"]),
        "excluded_count": len([d for d in filter_table if d["decision"] == "exclude"]),
        "review_count": len([d for d in filter_table if d["decision"] == "review"]),
        "include_ratio": len([d for d in filter_table if d["decision"] == "include"]) / max(1, len(filter_table))
    }

    invariants_passed = True
    invariant_checks = []

    # Check 1: Span validity (start < end, non-null)
    invalid_spans = [
        c for c in claims_table
        if c.get("evidence_span_start") is None or c.get("evidence_span_end") is None or c["evidence_span_start"] >= c["evidence_span_end"]
    ]
    check_spans = {
        "check_id": "STRICT_SPAN_VALIDITY",
        "status": "PASS" if len(invalid_spans) == 0 else "FAIL",
        "invalid_count": len(invalid_spans)
    }
    invariant_checks.append(check_spans)
    if check_spans["status"] == "FAIL":
        invariants_passed = False

    # Check 2: Provenance integrity (source_id format)
    non_provenance_facts = [
        f for f in fact_table
        if not f["source_id"].startswith("bodyvariant_") and not f["source_id"].startswith("src_")
    ]
    check_provenance = {
        "check_id": "STRICT_PROVENANCE_INTEGRITY",
        "status": "PASS" if len(non_provenance_facts) == 0 else "FAIL",
        "invalid_count": len(non_provenance_facts)
    }
    invariant_checks.append(check_provenance)
    if check_provenance["status"] == "FAIL":
        invariants_passed = False

    # Check 3: Zero Mock Fallback Contamination
    mock_claims = [
        c for c in claims_table
        if c.get("subject_mention") == "Mock Subject" or (c.get("relation_name") == "LOCATED_IN" and "Mock" in c.get("object_mention", ""))
    ]
    check_mock = {
        "check_id": "ZERO_MOCK_CONTAMINATION",
        "status": "PASS" if len(mock_claims) == 0 else "FAIL",
        "mock_claims_found": len(mock_claims)
    }
    invariant_checks.append(check_mock)
    if check_mock["status"] == "FAIL":
        invariants_passed = False

    report = {
        "schema_version": "ticket_a_v1",
        "stage": "4.13_pilot_quality_gate",
        "run_id": run_id,
        "status": "PASS" if invariants_passed else "FAIL",
        "filter_summary": filter_summary,
        "extracted_claims_count": len(claims_table),
        "fact_versions_count": len(fact_table),
        "invariant_checks": invariant_checks,
        "evaluated_at_real": utc_now_iso()
    }

    report_path = run_dir / "reports" / "quality_gate_report.json"
    write_json_immutable(report_path, report)

    return report