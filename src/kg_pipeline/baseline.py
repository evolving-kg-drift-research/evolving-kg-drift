"""Check exact configuration approval and source lock without manufacturing scientific decisions."""

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .hashing import sha256_file, sha256_json


def inspect_config_approval(repo_root: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    path = repo_root / "data/manifests/config_baseline.json"
    blocked = {"status": "PROPOSED_UNFROZEN", "approval_blockers": []}
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(approval, dict) or approval.get("status") != "APPROVED":
            raise ValueError("Missing approved baseline record")
        if not isinstance(approval.get("baseline_id"), str) or not approval["baseline_id"].strip():
            raise ValueError("Missing baseline identity")
        if any(not item["exists"] for item in candidates):
            raise ValueError("Required baseline files are missing")
        files = {item["path"]: item["sha256"] for item in candidates}
        if approval.get("files") != files:
            raise ValueError("Approved file hashes differ from current dependencies")
        for relative in files:
            if relative.endswith((".yaml", ".yml")):
                payload = yaml.safe_load((repo_root / relative).read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or not payload:
                    raise ValueError(f"Configuration must be a nonempty mapping: {relative}")
                if relative == "configs/protocol_v1.yaml":
                    if not isinstance(payload.get("sources"), dict):
                        raise ValueError(f"Protocol configuration lacks valid 'sources' mapping: {relative}")
                elif relative.endswith("ontology.yaml"):
                    if "relations" not in payload:
                        raise ValueError(f"Ontology configuration lacks 'relations': {relative}")
                elif relative.endswith("corpus_scope.yaml"):
                    if "start_date" not in payload or "end_date" not in payload:
                        raise ValueError(f"Corpus scope lacks date boundaries: {relative}")
        digest = sha256_json({"baseline_id": approval["baseline_id"], "files": files})
        decisions = [json.loads(line) for line in (repo_root / "decisions/decision_log.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        matches = [row for row in decisions if row.get("decision_id") == approval.get("decision_id")]
        if len(matches) != 1:
            raise ValueError("Approval requires exactly one referenced decision")
        decision = matches[0]
        if decision.get("action") != "approve_config_baseline" or decision.get("baseline_sha256") != digest:
            raise ValueError("Decision does not approve this exact baseline")
        if not decision.get("approved_by") or not decision.get("date_real"):
            raise ValueError("Approval decision lacks reviewer or date")
        return {"status": "FROZEN", "approval_blockers": [], "baseline_id": approval["baseline_id"], "baseline_sha256": digest, "approval_file_sha256": sha256_file(path)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, yaml.YAMLError) as exc:
        blocked["approval_blockers"] = [str(exc)]
        return blocked


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

    protocol_path = repo_root / "configs" / "protocol_v1.yaml"
    try:
        protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - missing or malformed authority must block readiness.
        return {
            "status": "BLOCKED",
            "reason": f"authoritative protocol is unreadable: {exc}",
            "lock_path": "data/manifests/sources.lock.json",
            "items": [],
        }
    protocol_sources = protocol.get("sources") if isinstance(protocol, dict) else None
    if not isinstance(lock, dict) or not isinstance(protocol_sources, dict):
        return {
            "status": "BLOCKED",
            "reason": "source lock and protocol sources must be mappings",
            "lock_path": "data/manifests/sources.lock.json",
            "items": [],
        }

    required_roles = {"proposal": "execution_plan", "patch": "patch_sha256"}
    # Need to keep the exact same required_roles dict as original
    required_roles = {"proposal": "proposal_sha256", "execution_plan": "execution_plan_sha256", "patch": "patch_sha256"}
    items: list[dict[str, Any]] = []
    for role in sorted(set(lock) | set(required_roles)):
        specification = lock.get(role)
        if not isinstance(specification, dict) or not specification.get("path") or not specification.get("sha256"):
            items.append({"role": role, "status": "INVALID_LOCK_ENTRY", "path": None, "expected_sha256": None})
            continue
        expected = specification["sha256"]
        if (
            role not in required_roles
            or not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or protocol_sources.get(required_roles[role]) != expected
            or not isinstance(specification["path"], str)
        ):
            items.append({"role": role, "status": "INVALID_BASELINE", "path": specification.get("path"), "expected_sha256": expected})
            continue
        path = (repo_root / specification["path"]).resolve()
        if repo_root.resolve() not in path.parents:
            items.append({"role": role, "status": "INVALID_SOURCE_PATH", "path": specification["path"], "expected_sha256": expected})
            continue
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
