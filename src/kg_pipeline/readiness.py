"""Shared fail-closed raw-input eligibility checks."""

from typing import Any


def raw_input_blockers(raw_rows: list[dict[str, Any]], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers = []
    if not raw_rows:
        blockers.append({"id": "EMPTY_RAW_INPUT", "detail": "No raw input is available"})
    non_strict = sum(row.get("strict_input_eligible") is not True for row in raw_rows)
    if non_strict:
        blockers.append({"id": "NON_STRICT_RAW_INPUT", "detail": f"{non_strict} raw paths are not strict eligible"})
    blocking_issues = [issue for issue in issues if issue.get("blocks_strict_input")]
    if len(blocking_issues) > 10:
        blockers.append({"id": "MULTIPLE_INPUT_ISSUES", "detail": f"{len(blocking_issues)} blocking issues found. First: {blocking_issues[0].get('reason')}"})
    else:
        for issue in blocking_issues:
            blockers.append({"id": issue.get("issue_id") or issue.get("issue_type") or "INPUT_ISSUE", "detail": issue.get("reason") or "Blocking input issue"})
    return blockers
