"""Small deterministic hashing helpers shared by pipeline contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize a semantic value without operational timestamps or key-order noise."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, payload: Any) -> str:
    """Return a deterministic identifier; callers must exclude operational time."""

    return f"{prefix}_{sha256_json({'prefix': prefix, 'payload': payload})[:32]}"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() or (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"Could not find repository root from {current}")


def get_git_info(repo_root: Path | None = None) -> tuple[str, bool]:
    """Return (git_commit_sha, is_dirty). Falls back to ('unknown', False) on failure."""
    try:
        root = repo_root or find_repo_root()
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        commit = res.stdout.strip()
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        is_dirty = bool(status_res.stdout.strip())
        return commit, is_dirty
    except Exception:
        return "unknown", False
