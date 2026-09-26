"""Ticket A readiness gate. A blocked inventory is evidence, never a passing gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow.parquet as pq

from .baseline import inspect_config_approval, inspect_source_lock
from .contracts import TABLE_SCHEMAS, FOREIGN_KEYS, validate_retrieval_rows
from .hashing import sha256_json, utc_now_iso
from .readiness import raw_input_blockers
from .run import config_fingerprints, get_run_dir, load_run_manifest
from .storage import read_json, read_yaml, verify_parquet_artifact, write_json_immutable

REQUIRED_TABLES = (
    "raw_inventory",
    "raw_hash_audit",
    "retrievals",
    "source_versions",
    "provenance_recovery_ledger",
    "body_variants",
    "document_memberships",
    "document_clusters",
    "lineage_edges",
    "near_duplicate_candidates",
    "missing_coverage_ledger",
    "coverage_ledger",
)


def _check(check_id: str, status: str, detail: str, evidence_path: str) -> dict[str, str]:
    return {"check_id": check_id, "status": status, "detail": detail, "evidence_path": evidence_path}


def _read_table(run_dir: Path, table_name: str) -> list[dict[str, Any]]:
    return pq.read_table(run_dir / "tables" / f"{table_name}.parquet").to_pylist()


def _persist_evaluation(run_dir: Path, result: dict[str, Any]) -> None:
    stamp = result["evaluated_at_real"].replace(":", "-")
    path = run_dir / "gates" / "A" / f"{stamp}_{uuid4().hex}.json"
    write_json_immutable(path, result)


def latest_gate_a_report(run_dir: Path) -> dict[str, Any] | None:
    paths = list((run_dir / "gates" / "A").glob("*.json"))
    if paths:
        reports = [read_json(p) for p in paths]
        reports.sort(key=lambda r: r.get("evaluated_at_real", ""))
        return reports[-1]
    legacy = run_dir / "gates" / "gate_A.json"
    return read_json(legacy) if legacy.is_file() else None


def evaluate_gate_a(repo_root: Path, run_id: str) -> dict[str, Any]:
    """Evaluate readiness using persisted evidence; returns non-PASS rather than masking blockers."""

    run_dir = get_run_dir(repo_root, run_id)
    manifest = load_run_manifest(repo_root, run_id)
    input_lock_path = run_dir / "inputs" / "input_lock.json"
    checks: list[dict[str, str]] = []
    if not input_lock_path.is_file():
        checks.append(_check("A-001", "NOT_RUN", "Inventory input_lock.json is absent", "inputs/input_lock.json"))
        semantic = {"gate": "A", "run_id": run_id, "status": "NOT_RUN", "checks": checks}
        result = {**semantic, "evaluated_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}
        _persist_evaluation(run_dir, result)
        return result

    input_lock = read_json(input_lock_path)
    stage_report_path = run_dir / "reports" / "stage_4_3_reconciliation.json"
    stage_status = read_json(stage_report_path).get("status") if stage_report_path.is_file() else "NOT_RUN"
    checks.append(
        _check(
            "A-001",
            "PASS" if stage_status == "PASS" else "FAIL" if stage_status == "FAIL" else "BLOCKED",
            f"Stage 4.3 reconciliation={stage_status}",
            "reports/stage_4_3_reconciliation.json",
        )
    )

    table_rows: dict[str, list[dict[str, Any]]] = {}
    table_errors: list[str] = []
    for table_name in REQUIRED_TABLES:
        path = run_dir / "tables" / f"{table_name}.parquet"
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        try:
            verify_parquet_artifact(path, table_name)
            table = pq.read_table(path)
            if table.schema.names != TABLE_SCHEMAS[table_name].names:
                raise ValueError("schema field names do not match contract")
            if not manifest_path.is_file():
                raise ValueError("immutable Parquet manifest is absent")
            table_rows[table_name] = table.to_pylist()
        except Exception as exc:  # noqa: BLE001 - a gate must report every unreadable artifact as FAIL.
            table_errors.append(f"{table_name}: {type(exc).__name__}: {exc}")
    checks.append(
        _check(
            "A-002",
            "PASS" if not table_errors else "FAIL",
            "all required Ticket A tables are readable and match the contract" if not table_errors else "; ".join(table_errors),
            "tables/",
        )
    )

    raw_rows = table_rows.get("raw_inventory", [])
    read_errors = [row for row in raw_rows if row.get("read_status") != "OK"]
    filename_mismatches = [row for row in raw_rows if row.get("filename_hash_status") == "MISMATCH"]
    checks.append(
        _check(
            "A-003",
            "FAIL" if read_errors or filename_mismatches else "PASS",
            f"read_errors={len(read_errors)}; filename_hash_mismatches={len(filename_mismatches)}",
            "tables/raw_inventory.parquet",
        )
    )

    retrieval_rows = table_rows.get("retrievals", [])
    try:
        validate_retrieval_rows(retrieval_rows)
        duplicate_ids = len({row["retrieval_id"] for row in retrieval_rows}) != len(retrieval_rows)
        checks.append(
            _check(
                "A-004",
                "FAIL" if duplicate_ids else "PASS",
                f"retrieval_records={len(retrieval_rows)}; unique_retrieval_ids={len({row['retrieval_id'] for row in retrieval_rows})}",
                "tables/retrievals.parquet",
            )
        )
    except Exception as exc:  # noqa: BLE001 - a gate must report every contract failure as FAIL.
        checks.append(_check("A-004", "FAIL", f"retrieval contract violation: {exc}", "tables/retrievals.parquet"))

    strict_raw_paths = sum(bool(row.get("strict_input_eligible")) for row in raw_rows)
    unresolved_raw_paths = sum(row.get("source_provenance_status") == "UNRESOLVED_NO_ACQUISITION_EVIDENCE" for row in raw_rows)
    checks.append(
        _check(
            "A-005",
            "BLOCKED" if raw_input_blockers(raw_rows, table_rows.get("missing_coverage_ledger", [])) else "PASS",
            f"strict_raw_paths={strict_raw_paths}; unresolved_raw_paths={unresolved_raw_paths}",
            "tables/raw_inventory.parquet",
        )
    )

    source_lock = inspect_source_lock(repo_root)
    checks.append(
        _check(
            "A-006",
            "PASS" if source_lock.get("status") == "PASS" else "BLOCKED",
            source_lock.get("reason") or "source lock satisfied",
            "inputs/input_lock.json",
        )
    )
    bundle_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    bundle = read_yaml(bundle_path) if bundle_path.is_file() else {}
    current_approval = inspect_config_approval(repo_root, config_fingerprints(repo_root))
    approval_matches = current_approval["status"] == "FROZEN" and all(bundle.get(key) == value for key, value in current_approval.items())
    checks.append(
        _check(
            "A-007",
            "PASS" if approval_matches else "BLOCKED",
            f"config bundle status={bundle.get('status', 'MISSING')}",
            "inputs/proposed_config_bundle.yaml",
        )
    )
    near_policy_rows = table_rows.get("near_duplicate_candidates", [])
    near_policy_blocked = any(row.get("policy_status") == "BLOCKED_UNFROZEN_SEMANTIC_POLICY" for row in near_policy_rows)
    checks.append(
        _check(
            "A-008",
            "BLOCKED" if near_policy_blocked else "PASS",
            "near-duplicate/copy/lineage policy remains unfrozen" if near_policy_blocked else "near-duplicate policy is versioned",
            "tables/near_duplicate_candidates.parquet",
        )
    )
    safety_scope = manifest.get("safety_scope", {})
    raw_roots = manifest.get("raw_input_roots", [])
    legacy_safe = safety_scope.get("legacy_decision_inputs") == "EXCLUDED" and raw_roots == ["data/raw/stage_4_4"]
    checks.append(
        _check(
            "A-009",
            "PASS" if legacy_safe else "FAIL",
            "new run consumes the declared raw root only; legacy decision artifacts are excluded" if legacy_safe else "run manifest safety scope is not intact",
            "run_manifest.yaml",
        )
    )
    lock_status = input_lock.get("status")
    checks.append(
        _check(
            "A-010",
            "PASS" if lock_status == "READY" else "BLOCKED",
            f"input lock status={lock_status}",
            "inputs/input_lock.json",
        )
    )

    fk_errors = []
    for child_table, fks in FOREIGN_KEYS.items():
        if child_table not in table_rows:
            continue
        for child_col, (parent_table, parent_col) in fks.items():
            if parent_table not in table_rows:
                fk_errors.append(f"Missing parent table {parent_table} required by {child_table}.{child_col}")
                continue
            parent_keys = {row.get(parent_col) for row in table_rows[parent_table] if row.get(parent_col) is not None}
            for index, row in enumerate(table_rows[child_table]):
                val = row.get(child_col)
                if val is not None and val not in parent_keys:
                    fk_errors.append(f"{child_table}[{index}].{child_col}='{val}' not found in {parent_table}.{parent_col}")

    checks.append(
        _check(
            "A-011",
            "PASS" if not fk_errors else "FAIL",
            "all foreign keys resolve" if not fk_errors else f"{len(fk_errors)} FK violations; first: {fk_errors[0]}",
            "tables/",
        )
    )

    statuses = {check["status"] for check in checks}
    status = "FAIL" if "FAIL" in statuses else "BLOCKED" if "BLOCKED" in statuses else "NOT_RUN" if "NOT_RUN" in statuses else "PASS"
    semantic = {
        "gate": "A",
        "run_id": run_id,
        "status": status,
        "checks": checks,
        "input_lock_semantic_sha256": input_lock.get("semantic_sha256"),
        "run_manifest_semantic_sha256": manifest.get("semantic_sha256"),
        "commands": [
            f"python -m kg_pipeline inventory --run {run_id} --verify-inputs",
            f"python -m kg_pipeline verify --run {run_id} --gate A",
        ],
    }
    result = {**semantic, "evaluated_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}
    _persist_evaluation(run_dir, result)
    return result
