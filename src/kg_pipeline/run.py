"""New-run creation and immutable input/config lock inspection."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .hashing import repo_relative, sha256_file, sha256_json, utc_now_iso
from .storage import ArtifactConflict, read_yaml, write_yaml_immutable

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,80}$")

CONFIG_CANDIDATES = (
    "config/protocol.yaml",
    "config/ontology.yaml",
    "config/schema.yaml",
    "configs/protocol_v1.yaml",
    "configs/data.yaml",
    "data/manifests/sources.lock.json",
)


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("Run IDs must be 3-81 characters of letters, digits, _ or -, with no path separators")
    return run_id


def get_run_dir(repo_root: Path, run_id: str) -> Path:
    validate_run_id(run_id)
    candidate = (repo_root / "runs" / run_id).resolve()
    runs_root = (repo_root / "runs").resolve()
    if runs_root not in (candidate, *candidate.parents):
        raise ValueError("Run path escapes the runs directory")
    return candidate


def package_fingerprint(repo_root: Path) -> str:
    package_root = repo_root / "src" / "kg_pipeline"
    file_hashes = {
        repo_relative(path, repo_root): sha256_file(path)
        for path in sorted(package_root.rglob("*.py"))
        if path.is_file()
    }
    return sha256_json(file_hashes)


def config_fingerprints(repo_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in CONFIG_CANDIDATES:
        path = repo_root / relative
        records.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return records


def inspect_source_lock(repo_root: Path) -> dict[str, Any]:
    lock_path = repo_root / "data" / "manifests" / "sources.lock.json"
    if not lock_path.is_file():
        return {
            "status": "BLOCKED",
            "reason": "source lock file is missing",
            "lock_path": "data/manifests/sources.lock.json",
            "items": [],
        }
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "BLOCKED",
            "reason": f"source lock is unreadable: {exc}",
            "lock_path": "data/manifests/sources.lock.json",
            "items": [],
        }

    items: list[dict[str, Any]] = []
    for role, specification in sorted(lock.items()):
        if not isinstance(specification, dict) or not specification.get("path") or not specification.get("sha256"):
            items.append({"role": role, "status": "INVALID_LOCK_ENTRY", "path": None, "expected_sha256": None})
            continue
        path = repo_root / specification["path"]
        if not path.is_file():
            status = "MISSING"
            actual = None
        else:
            actual = sha256_file(path)
            status = "MATCH" if actual == specification["sha256"] else "HASH_MISMATCH"
            with path.open("rb") as handle:
                if handle.read(256).startswith(b"Placeholder content for "):
                    status = "INVALID_PLACEHOLDER_SOURCE"
        items.append(
            {
                "role": role,
                "path": specification["path"],
                "expected_sha256": specification["sha256"],
                "actual_sha256": actual,
                "status": status,
            }
        )
    status = "PASS" if items and all(item["status"] == "MATCH" for item in items) else "BLOCKED"
    return {
        "status": status,
        "reason": None if status == "PASS" else "One or more required source artifacts are absent, invalid, or hash-mismatched",
        "lock_path": "data/manifests/sources.lock.json",
        "lock_sha256": sha256_file(lock_path),
        "items": items,
    }


def _bundle_payload(repo_root: Path) -> dict[str, Any]:
    candidate_files = config_fingerprints(repo_root)
    semantic = {
        "bundle_version": "ticket_a_frozen_baseline_v2",
        "status": "FROZEN",
        "candidate_files": candidate_files,
        "resolved_semantic_decisions": [
            "ADR 0005: Time fields retrieved_at_real and ingested_at_real remain completely separated.",
            "ADR 0005: Ontology is frozen at 10 strictly defined active relations.",
            "ADR 0005: Exact-body CAS deduplication policy is approved and frozen for Stage A.",
            "ADR 0006: Source locks updated to reflect authentic document hashes."
        ],
    }
    return {**semantic, "created_at_real": utc_now_iso(), "semantic_sha256": sha256_json(semantic)}


def init_run(repo_root: Path, run_id: str, *, mode: str) -> dict[str, Any]:
    if mode != "inventory":
        raise ValueError(f"Ticket A supports only --mode inventory (got {mode})")
    run_dir = get_run_dir(repo_root, run_id)
    for relative in ("inputs", "tables", "body_blobs", "reports", "gates", "logs"):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)

    source_lock = inspect_source_lock(repo_root)

    safety_scope = {
        "legacy_decision_inputs": "EXCLUDED",
        "raw_input_mutation": "FORBIDDEN",
        "llm_calls": "FORBIDDEN_IN_TICKET_A",
        "network_collection": "FORBIDDEN_IN_TICKET_A",
        "neo4j_writes": "FORBIDDEN_IN_TICKET_A",
    }

    semantic = {
        "run_id": run_id,
        "mode": mode,
        "pipeline_contract_version": "ticket_a_v1",
        "raw_input_roots": ["data/raw/stage_4_4"],
        "upstream_stage_4_3_run": "data/stage_4_3_runs/stage4_3_final_20260906T144016Z",
        "code_fingerprint_sha256": package_fingerprint(repo_root),
        "config_candidates": config_fingerprints(repo_root),
        "source_lock_status_at_init": source_lock["status"],
        "input_lock_path": "inputs/input_lock.json",
        "safety_scope": safety_scope,
    }
    manifest = {
        **semantic,
        "created_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(semantic),
    }
    manifest_path = run_dir / "run_manifest.yaml"
    if manifest_path.is_file():
        existing_manifest = read_yaml(manifest_path)
        if existing_manifest.get("run_id") != run_id or existing_manifest.get("mode") != mode:
            raise ArtifactConflict(f"Existing run manifest has incompatible identity: {manifest_path}")
        manifest_result = {
            "status": "REUSED",
            "semantic_sha256": existing_manifest.get("semantic_sha256"),
        }
    else:
        manifest_result = write_yaml_immutable(manifest_path, manifest)
    bundle_result = write_yaml_immutable(run_dir / "inputs" / "proposed_config_bundle.yaml", _bundle_payload(repo_root))
    return {
        "run_dir": str(run_dir),
        "manifest": manifest_result,
        "proposed_bundle": bundle_result,
        "source_lock_status": source_lock["status"],
    }


def load_run_manifest(repo_root: Path, run_id: str) -> dict[str, Any]:
    path = get_run_dir(repo_root, run_id) / "run_manifest.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Run has not been initialized: {path}")
    return read_yaml(path)
