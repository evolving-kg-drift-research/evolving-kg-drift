"""Immutable, fingerprinted extraction request/response cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hashing import canonical_json, sha256_file, sha256_text
from .storage import write_json_immutable

CACHE_FORMAT_VERSION = "extraction-cache-v2"


class CacheIntegrityError(ValueError):
    """A stored request/response cache entry is malformed or tampered with."""


def get_cache_key(
    prompt: str,
    model: str,
    config: dict[str, Any],
    request_fingerprints: dict[str, Any] | None = None,
) -> str:
    """Bind cache identity to every declared input and execution fingerprint."""
    payload = {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "prompt_sha256": sha256_text(prompt),
        "model": model,
        "decoding_config": config,
        "request_fingerprints": request_fingerprints or {},
    }
    return sha256_text(canonical_json(payload))


def get_cached_response(
    cache_dir: Path,
    cache_key: str,
    request_fingerprints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Read and verify a v2 envelope; corruption is an error, never a cache miss."""
    cache_path = cache_dir / f"{cache_key}.json"
    if not cache_path.exists():
        return None
    manifest_path = cache_dir / "manifests" / f"{cache_key}.json"
    if not manifest_path.is_file():
        raise CacheIntegrityError(f"Missing immutable extraction cache manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheIntegrityError(f"Unreadable extraction cache manifest: {manifest_path}") from exc
    if not isinstance(manifest, dict) or manifest.get("physical_sha256") != sha256_file(cache_path):
        raise CacheIntegrityError(f"Extraction cache physical hash mismatch: {cache_path}")
    if manifest.get("cache_key") != cache_key:
        raise CacheIntegrityError(f"Extraction cache manifest key mismatch: {manifest_path}")
    try:
        envelope = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheIntegrityError(f"Unreadable extraction cache entry: {cache_path}") from exc
    if not isinstance(envelope, dict):
        raise CacheIntegrityError(f"Invalid extraction cache envelope: {cache_path}")
    expected_fingerprints = request_fingerprints or {}
    response = envelope.get("response")
    if envelope.get("cache_format_version") != CACHE_FORMAT_VERSION:
        raise CacheIntegrityError(f"Unsupported extraction cache version: {cache_path}")
    if envelope.get("cache_key") != cache_key:
        raise CacheIntegrityError(f"Extraction cache key mismatch: {cache_path}")
    if envelope.get("request_fingerprints") != expected_fingerprints:
        raise CacheIntegrityError(f"Extraction cache request fingerprints mismatch: {cache_path}")
    if not isinstance(response, dict):
        raise CacheIntegrityError(f"Extraction cache response is not a JSON object: {cache_path}")
    if envelope.get("response_sha256") != sha256_text(canonical_json(response)):
        raise CacheIntegrityError(f"Extraction cache response hash mismatch: {cache_path}")
    return response


def set_cached_response(
    cache_dir: Path,
    cache_key: str,
    response: dict[str, Any],
    request_fingerprints: dict[str, Any] | None = None,
) -> None:
    """Publish an immutable response envelope bound to its request fingerprints."""
    if not isinstance(response, dict):
        raise CacheIntegrityError("Extraction response must be a JSON object.")
    fingerprints = request_fingerprints or {}
    envelope = {
        "cache_format_version": CACHE_FORMAT_VERSION,
        "cache_key": cache_key,
        "request_fingerprints": fingerprints,
        "response_sha256": sha256_text(canonical_json(response)),
        "response": response,
    }
    cache_path = cache_dir / f"{cache_key}.json"
    manifest_path = cache_dir / "manifests" / f"{cache_key}.json"
    cache_exists = cache_path.exists()
    manifest_exists = manifest_path.is_file()
    if cache_exists != manifest_exists:
        raise CacheIntegrityError(
            "Refusing to repair an incomplete immutable extraction cache pair: "
            f"{cache_path} / {manifest_path}"
        )
    if cache_exists:
        existing_response = get_cached_response(cache_dir, cache_key, fingerprints)
        if existing_response != response:
            raise CacheIntegrityError(f"Refusing to replace immutable extraction cache entry: {cache_path}")
        return

    cache_dir.mkdir(parents=True, exist_ok=True)
    write_json_immutable(cache_path, envelope)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_immutable(
        manifest_path,
        {"cache_format_version": CACHE_FORMAT_VERSION, "cache_key": cache_key,
         "physical_sha256": sha256_file(cache_path)},
    )
