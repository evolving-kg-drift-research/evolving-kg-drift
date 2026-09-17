"""Read-only Stage 4.3 evidence reconciliation; it never reruns acquisition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .hashing import repo_relative, sha256_file, sha256_json, utc_now_iso
from .run import get_run_dir
from .storage import write_json_immutable

STAGE_4_3_RELATIVE = Path("data/stage_4_3_runs/stage4_3_final_20260906T144016Z")


def _check(check_id: str, status: str, detail: str, evidence_path: str) -> dict[str, str]:
    return {"check_id": check_id, "status": status, "detail": detail, "evidence_path": evidence_path}


def reconcile_stage_4_3(repo_root: Path, run_id: str) -> dict[str, Any]:
    stage_dir = repo_root / STAGE_4_3_RELATIVE
    checks: list[dict[str, str]] = []
    manifest_path = stage_dir / "run_manifest.json"
    validation_path = stage_dir / "stage_4_3_validation_report.json"
    report_path = stage_dir / "STAGE_4_3_REPORT.md"

    if not all(path.is_file() for path in (manifest_path, validation_path, report_path)):
        missing = [repo_relative(path, repo_root) for path in (manifest_path, validation_path, report_path) if not path.is_file()]
        checks.append(_check("A-4.3-001", "FAIL", f"Missing Stage 4.3 evidence: {missing}", str(STAGE_4_3_RELATIVE)))
        manifest: dict[str, Any] = {}
        validation: dict[str, Any] = {}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        manifest_ok = manifest.get("status") == "PASS"
        validation_ok = validation.get("status") == "PASS" and validation.get("gate_result") == "PASS"
        checks.append(
            _check(
                "A-4.3-001",
                "PASS" if manifest_ok and validation_ok else "FAIL",
                f"manifest={manifest.get('status')}; validation={validation.get('status')}/{validation.get('gate_result')}",
                repo_relative(validation_path, repo_root),
            )
        )

    expected_hashes = manifest.get("outputs_sha256", {})
    hash_failures: list[str] = []
    for name, expected in expected_hashes.items():
        path = stage_dir / name
        if not path.is_file() or sha256_file(path) != expected:
            hash_failures.append(name)
    checks.append(
        _check(
            "A-4.3-002",
            "PASS" if expected_hashes and not hash_failures else "FAIL",
            "all manifest output hashes match" if not hash_failures else f"hash mismatch or absent: {hash_failures}",
            repo_relative(manifest_path, repo_root) if manifest_path.is_file() else str(STAGE_4_3_RELATIVE),
        )
    )

    discovered_path = stage_dir / "discovered_urls.parquet"
    archive_path = stage_dir / "archive_candidates.parquet"
    try:
        discovered = pq.read_table(discovered_path)
        archive = pq.read_table(archive_path)
        urls = discovered.column("url").to_pylist()
        observations_ok = discovered.num_rows == 4692 and len(set(urls)) == 3344 and archive.num_rows == 72
        checks.append(
            _check(
                "A-4.3-003",
                "PASS" if observations_ok else "FAIL",
                f"discovered_rows={discovered.num_rows}; unique_urls={len(set(urls))}; archive_rows={archive.num_rows}",
                repo_relative(discovered_path, repo_root),
            )
        )
    except Exception as exc:  # noqa: BLE001 - report a broken upstream artifact instead of silently accepting it
        checks.append(_check("A-4.3-003", "FAIL", f"Parquet readability/count check failed: {exc}", str(STAGE_4_3_RELATIVE)))

    log_path = stage_dir / "discovery_log.jsonl"
    valid_lines = 0
    invalid_lines = 0
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                    valid_lines += 1
                except json.JSONDecodeError:
                    invalid_lines += 1
        logs_ok = valid_lines == 245928 and invalid_lines == 0
        checks.append(
            _check(
                "A-4.3-004",
                "PASS" if logs_ok else "FAIL",
                f"valid_jsonl_lines={valid_lines}; invalid_jsonl_lines={invalid_lines}",
                repo_relative(log_path, repo_root),
            )
        )
    except OSError as exc:
        checks.append(_check("A-4.3-004", "FAIL", f"Cannot read discovery log: {exc}", str(STAGE_4_3_RELATIVE)))

    block_count = validation.get("tuoitre_historical", {}).get("block_count")
    checks.append(
        _check(
            "A-4.3-005",
            "PASS" if block_count == 108 else "FAIL",
            f"Tuoi Tre historical block_count={block_count}",
            repo_relative(validation_path, repo_root) if validation_path.is_file() else str(STAGE_4_3_RELATIVE),
        )
    )

    status = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    semantic = {
        "stage": "4.3",
        "source_run_id": manifest.get("run_id"),
        "status": status,
        "checks": checks,
        "counts": {
            "production_observations": validation.get("required_artifacts", {}).get("discovered_urls.parquet", {}).get("rows"),
            "unique_urls": validation.get("required_artifacts", {}).get("discovered_urls.parquet", {}).get("unique_urls"),
            "tuoitre_blocks": block_count,
        },
    }
    result = {**semantic, "reconciled_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}
    output_path = get_run_dir(repo_root, run_id) / "reports" / "stage_4_3_reconciliation.json"
    write_json_immutable(output_path, result)
    return result
