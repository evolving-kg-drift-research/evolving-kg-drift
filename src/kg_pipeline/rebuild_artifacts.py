"""Bounded artifact reads and exact decision bindings for acceptance rebuilds."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
from typing import Any

import pyarrow.parquet as pq

from .hashing import sha256_file


class RebuildBlocked(ValueError):
    """A required, verifiable input to a rebuild is unavailable."""


class RebuildViolation(ValueError):
    """Verified inputs exhibit a concrete scientific invariant violation."""


def artifact_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise RebuildBlocked("Artifact path must be a nonempty relative POSIX path")
    parts = PurePosixPath(relative).parts
    if (PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).drive
            or any(p in {"..", ".git", ".agents", ".codex", "locked_test"} for p in parts)):
        raise RebuildBlocked("Forbidden artifact path")
    base = root.resolve()
    path = base.joinpath(*parts)
    for parent in (path, *path.parents):
        if parent == base:
            break
        try:
            attributes = getattr(parent.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            attributes = 0
        if (parent.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
                or getattr(parent, "is_junction", lambda: False)()):
            raise RebuildBlocked("Artifact paths cannot traverse links")
    resolved = path.resolve()
    if base not in resolved.parents:
        raise RebuildBlocked("Artifact escapes workspace")
    if any(part in {".git", ".agents", ".codex", "locked_test"} for part in resolved.relative_to(base).parts):
        raise RebuildBlocked("Resolved artifact path is forbidden")
    return path


def verified_path(root: Path, ref: dict[str, Any]) -> Path:
    digest = ref.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RebuildBlocked("Artifact reference requires exact SHA-256")
    path = artifact_path(root, ref.get("path"))
    if not path.is_file() or sha256_file(path) != digest:
        raise RebuildBlocked(f"Missing or changed artifact: {ref.get('path')}")
    return path


def read_verified(root: Path, ref: dict[str, Any]) -> Any:
    path = verified_path(root, ref)
    if path.suffix == ".parquet":
        return pq.read_table(path).to_pylist()
    return json.loads(path.read_text(encoding="utf-8"))


def require_decision(root: Path, decision_id: str, *, action: str,
                     bindings: dict[str, str]) -> dict[str, Any]:
    """Never infer approval from a draft's status or a report claiming PASS."""
    path = root / "decisions/decision_log.jsonl"
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise RebuildBlocked("Approval decision ledger unavailable") from exc
    matches = [r for r in records if r.get("decision_id") == decision_id]
    if len(matches) != 1:
        raise RebuildBlocked("Exactly one referenced approval decision required")
    record = matches[0]
    if (record.get("action") != action or not record.get("approved_by") or not record.get("date_real")
            or record.get("bindings") != bindings):
        raise RebuildBlocked("Decision does not approve these exact dependencies")
    return record
