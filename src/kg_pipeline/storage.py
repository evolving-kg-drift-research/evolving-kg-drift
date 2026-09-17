"""Append-safe artifact writes for new run namespaces only."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from .contracts import CONTRACT_VERSION, table_from_rows
from .hashing import canonical_json, sha256_file, sha256_json, utc_now_iso


class ArtifactConflict(RuntimeError):
    """Raised rather than overwriting an immutable run artifact."""


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _semantic_from_payload(payload: dict[str, Any]) -> str:
    return payload.get("semantic_sha256") or sha256_json(payload)


def write_json_immutable(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Write once; an equivalent semantic record is safely reused on a retry."""

    semantic_sha256 = _semantic_from_payload(payload)
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if _semantic_from_payload(existing) == semantic_sha256:
            return {"status": "REUSED", "semantic_sha256": semantic_sha256}
        raise ArtifactConflict(f"Refusing to overwrite immutable artifact: {path}")
    _atomic_write_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return {"status": "CREATED", "semantic_sha256": semantic_sha256}


def write_yaml_immutable(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    semantic_sha256 = _semantic_from_payload(payload)
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8"))
        if _semantic_from_payload(existing) == semantic_sha256:
            return {"status": "REUSED", "semantic_sha256": semantic_sha256}
        raise ArtifactConflict(f"Refusing to overwrite immutable artifact: {path}")
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=True)
    _atomic_write_bytes(path, rendered.encode("utf-8"))
    return {"status": "CREATED", "semantic_sha256": semantic_sha256}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_parquet_immutable(path: Path, table_name: str, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Commit a canonical Parquet part and its semantic manifest without replacement."""

    rows_list = list(rows)
    semantic_sha256 = sha256_json(
        {"table_name": table_name, "contract_version": CONTRACT_VERSION, "rows": rows_list}
    )
    manifest_path = path.with_suffix(path.suffix + ".manifest.json")
    if path.exists() and manifest_path.exists():
        existing_manifest = read_json(manifest_path)
        if existing_manifest.get("semantic_sha256") == semantic_sha256:
            return {**existing_manifest, "write_status": "REUSED"}
        raise ArtifactConflict(f"Refusing to overwrite immutable Parquet artifact: {path}")
    if path.exists() and not manifest_path.exists():
        existing_rows = pq.read_table(path).to_pylist()
        existing_semantic = sha256_json(
            {"table_name": table_name, "contract_version": CONTRACT_VERSION, "rows": existing_rows}
        )
        if existing_semantic != semantic_sha256:
            raise ArtifactConflict(f"Existing uncommitted Parquet content conflicts with {path}")
    else:
        table = table_from_rows(table_name, rows_list)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            pq.write_table(table, temporary, compression="zstd")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    manifest = {
        "artifact_type": "canonical_parquet_part",
        "table_name": table_name,
        "contract_version": CONTRACT_VERSION,
        "row_count": len(rows_list),
        "semantic_sha256": semantic_sha256,
        "physical_sha256_computed_at_real": sha256_file(path),
        "created_at_real": utc_now_iso(),
    }
    write_json_immutable(manifest_path, manifest)
    return {**manifest, "write_status": "CREATED"}


def write_text_cas(path: Path, text: str, expected_sha256: str) -> str:
    """Store normalized body text by content hash; existing content is never replaced."""

    if path.exists():
        if sha256_file(path) != expected_sha256:
            raise ArtifactConflict(f"Body CAS hash conflict at {path}")
        return "REUSED"
    _atomic_write_bytes(path, text.encode("utf-8"))
    if sha256_file(path) != expected_sha256:
        raise RuntimeError(f"Body CAS verification failed after write: {path}")
    return "CREATED"


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Operational log only; tables/manifests remain the scientific artifacts."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(payload) + "\n")
