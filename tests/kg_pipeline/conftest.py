from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def write_blob(repo_root: Path, body: str, *, filename_hash: str | None = None) -> tuple[Path, str]:
    payload = f"<!doctype html><html><body><article><p>{body}</p></article></body></html>".encode()
    digest = hashlib.sha256(payload).hexdigest()
    name = filename_hash or digest
    path = repo_root / "data" / "raw" / "stage_4_4" / "blobs" / "sha256" / name[:2] / f"{name}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, digest


def write_acquisition_log(repo_root: Path, digest: str, *, count: int = 2) -> None:
    log_path = repo_root / "logs" / "acquisition.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(count):
        records.append(
            {
                "event_id": f"retrieval-{index}",
                "payload_sha256": digest,
                "source_id": "fixture_source",
                "requested_url": f"https://example.test/requested/{index}",
                "final_url": f"https://example.test/final/{index}",
                "retrieved_at_real": f"2026-09-0{index + 1}T00:00:00+00:00",
            }
        )
    log_path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def write_missing_source_lock(repo_root: Path) -> None:
    lock_path = repo_root / "data" / "manifests" / "sources.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "proposal": {
                    "path": "sources/missing-proposal.pdf",
                    "sha256": "0" * 64,
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def blob_writer():
    return write_blob


@pytest.fixture
def acquisition_log_writer():
    return write_acquisition_log


@pytest.fixture
def source_lock_writer():
    return write_missing_source_lock
