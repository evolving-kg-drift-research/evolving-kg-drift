"""Registered Gemini candidate capture with conservative spend accounting and offline replay."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

import requests

from .hashing import sha256_file, sha256_json, sha256_text, utc_now_iso
from .llm_cache import get_cached_response, set_cached_response, CacheIntegrityError
from .rebuild_artifacts import RebuildBlocked, read_verified, require_decision
from .storage import exclusive_artifact_lock, write_json_immutable

API_VERSION = "v1beta"
CAPTURE_VERSION = "gemini-capture-v1"
FIELDS = {"subject_mention": {"type": "string"}, "relation_name": {"type": "string"},
          "object_mention": {"type": "string"}, "evidence_span_start": {"type": "integer"},
          "evidence_span_end": {"type": "integer"},
          "valid_from_extracted": {"type": ["string", "null"]},
          "valid_to_extracted": {"type": ["string", "null"]},
          "is_negative": {"type": "boolean"}, "is_speculative": {"type": "boolean"}}
RESPONSE_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "items": {
    "type": "object", "properties": FIELDS, "required": list(FIELDS), "additionalProperties": False}}},
    "required": ["claims"], "additionalProperties": False}


def _money(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise RebuildBlocked("Budget values must be explicit decimal strings")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise RebuildBlocked("Invalid budget amount") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise RebuildBlocked("Budget amount must be finite and positive")
    return parsed


def request_payload(text: str, config: dict[str, Any]) -> dict[str, Any]:
    if (not isinstance(text, str) or not text or config.get("model") != "gemini-3.8-flash"
            or config.get("api_version") != API_VERSION or config.get("phase") not in {"pilot", "main"}
            or config.get("payload_policy") != "approved_public_clean_text_only"):
        raise RebuildBlocked("Explicit registered Gemini configuration required")
    relations = config.get("relations")
    prompt = config.get("prompt_template")
    if (not isinstance(relations, list) or not relations or len(set(relations)) != len(relations)
            or any(not isinstance(r, str) or not r for r in relations)
            or not isinstance(prompt, str) or prompt.count("{text}") != 1
            or prompt.count("{relations}") != 1):
        raise RebuildBlocked("Versioned prompt and ontology relations required")
    # Size is a registered whole-document bound; never truncate or silently chunk.
    if type(config.get("max_input_chars")) is not int or config["max_input_chars"] <= 0:
        raise RebuildBlocked("Explicit input bound required")
    if len(text) > config["max_input_chars"]:
        raise RebuildBlocked("WHOLE_ARTICLE_OVER_INPUT_LIMIT")
    if (type(config.get("max_output_tokens")) is not int or config["max_output_tokens"] <= 0
            or type(config.get("temperature")) not in {int, float} or config["temperature"] != 0):
        raise RebuildBlocked("Explicit max output tokens and temperature=0 required")
    content = prompt.replace("{relations}", json.dumps(relations, ensure_ascii=False)).replace("{text}", text)
    return {"contents": [{"role": "user", "parts": [{"text": content}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": config["max_output_tokens"],
                                 "candidateCount": 1, "responseMimeType": "application/json",
                                 "responseJsonSchema": RESPONSE_SCHEMA}}


def validate_response(raw: dict[str, Any], relations: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("promptFeedback", {}).get("blockReason"):
        raise RebuildBlocked("GEMINI_BLOCKED_RESPONSE")
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise RebuildBlocked("GEMINI_MISSING_CANDIDATE")
    candidate = candidates[0]
    if candidate.get("finishReason") != "STOP" or candidate.get("groundingMetadata"):
        raise RebuildBlocked("GEMINI_TRUNCATED_OR_GROUNDED_RESPONSE")
    parts = candidate.get("content", {}).get("parts")
    if (not isinstance(parts, list) or not parts or any(set(p) != {"text"} or not isinstance(p["text"], str)
                                                       for p in parts)):
        raise RebuildBlocked("GEMINI_NON_TEXT_RESPONSE")
    try:
        result = json.loads("".join(p["text"] for p in parts))
    except ValueError as exc:
        raise RebuildBlocked("GEMINI_MALFORMED_JSON") from exc
    if not isinstance(result, dict) or set(result) != {"claims"} or not isinstance(result["claims"], list):
        raise RebuildBlocked("GEMINI_MISSING_CLAIMS_FIELD")
    for claim in result["claims"]:
        if not isinstance(claim, dict) or set(claim) != set(FIELDS):
            raise RebuildBlocked("GEMINI_INCOMPLETE_CLAIM")
        if any(not isinstance(claim[f], str) or not claim[f].strip()
               for f in ("subject_mention", "object_mention", "relation_name")):
            raise RebuildBlocked("GEMINI_INVALID_MENTION")
        if claim["relation_name"] not in relations:
            raise RebuildBlocked("GEMINI_UNKNOWN_RELATION")
        if any(type(claim[f]) is not int for f in ("evidence_span_start", "evidence_span_end")):
            raise RebuildBlocked("GEMINI_INVALID_OFFSET")
        if any(type(claim[f]) is not bool for f in ("is_negative", "is_speculative")):
            raise RebuildBlocked("GEMINI_INVALID_FLAG")
        if any(claim[f] is not None and not isinstance(claim[f], str)
               for f in ("valid_from_extracted", "valid_to_extracted")):
            raise RebuildBlocked("GEMINI_INVALID_TEMPORAL_CANDIDATE")
    return result


def _transport(payload: dict[str, Any], config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RebuildBlocked("GEMINI_API_KEY is not configured")
    endpoint = f"https://generativelanguage.googleapis.com/{API_VERSION}/models/{config['model']}:generateContent"
    response = requests.post(endpoint, json=payload, headers={"x-goog-api-key": key}, timeout=120)
    try:
        raw = response.json()
    except ValueError:
        raw = {"response_parse_error": True}  # No provider error message can expose a key in artifacts.
    return response.status_code, raw


def capture_or_replay(
    root: Path, run_dir: Path, config: dict[str, Any], registration: dict[str, Any],
    item: dict[str, Any], *, mode: str,
    transport: Callable[[dict[str, Any], dict[str, Any]], tuple[int, dict[str, Any]]] = _transport,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Network is possible only with exact approval and a durable pre-attempt reservation.

    Every started attempt retains its full approved upper-bound reservation,
    including ambiguous timeouts. This overestimates spend rather than inventing
    a billing amount. One capture process owns the run-wide lock at a time.
    """
    if mode not in {"capture", "replay"}:
        raise RebuildBlocked("Explicit capture/replay mode required")
    if root.resolve() not in run_dir.resolve().parents or run_dir.parent.resolve() != (root / "runs").resolve():
        raise RebuildBlocked("Capture must use an explicit run namespace")
    from .gates import require_gate_a
    from .run import load_run_manifest
    manifest = load_run_manifest(root, run_dir.name)
    require_gate_a(root, run_dir.name)
    if manifest.get("scientific_locked") is not True:
        raise RebuildBlocked("Hosted capture/replay requires a frozen scientific run")
    inventory_ref = registration.get("inventory_ref", {})
    inventory = read_verified(root, inventory_ref)
    if not isinstance(inventory, list) or sum(entry == item for entry in inventory) != 1:
        raise RebuildBlocked("Article is not uniquely in the approved inventory")
    if item.get("public_content") is not True:
        raise RebuildBlocked("Only explicitly public content can be sent")
    from .rebuild_artifacts import verified_path
    body = verified_path(root, item["body_ref"]).read_bytes().decode("utf-8")
    payload = request_payload(body, config)
    bindings = {"config_sha256": sha256_json(config), "inventory_sha256": inventory_ref["sha256"],
                "phase": config["phase"], "scope": "candidate_extraction_only"}
    require_decision(root, registration.get("decision_id"), action="approve_hosted_extraction", bindings=bindings)
    fingerprints = {**bindings, "capture_version": CAPTURE_VERSION, "body_sha256": sha256_text(body),
                    "response_schema_sha256": sha256_json(RESPONSE_SCHEMA), "request_sha256": sha256_json(payload)}
    cache_key = sha256_json(fingerprints)
    cache = run_dir / "gemini_cache"
    cached = get_cached_response(cache, cache_key, fingerprints)
    if cached is not None:
        validated = validate_response(cached["provider_response"], config["relations"])
        if validated != cached["validated_response"]:
            raise CacheIntegrityError("Cached provider/validated response mismatch")
        return cached
    if mode == "replay":
        raise CacheIntegrityError("Locked Gemini replay cache is missing; network is forbidden")
    ceiling = _money(config.get("attempt_cost_ceiling_usd"))
    budget = _money(config.get("budget_usd"))
    if ceiling > budget:
        raise RebuildBlocked("Attempt cost bound exceeds approved budget")
    expected_version = config.get("expected_model_version")
    attempts_dir = run_dir / "gemini_attempts"
    with exclusive_artifact_lock(run_dir / "gemini_capture"):
        # Recheck after acquiring the run-wide writer lock.
        existing = get_cached_response(cache, cache_key, fingerprints)
        if existing is not None:
            return existing
        reservations = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(attempts_dir.glob("*/reservation.json"))]
        spent = Decimal(0)
        for record in reservations:
            if record.get("bindings") != bindings:
                raise RebuildBlocked("Attempt ledger belongs to changed capture dependencies")
            spent += _money(record["reserved_usd"])
            if record["request_key"] == cache_key:
                raise RebuildBlocked("Interrupted/failed capture exists; review it before a new attempt namespace")
        observed_versions = set()
        for path in attempts_dir.glob("*/result.json"):
            version = json.loads(path.read_text(encoding="utf-8")).get("model_version")
            if version:
                observed_versions.add(version)
        if expected_version:
            observed_versions.add(expected_version)
        for number in range(1, 4):
            if spent + ceiling > budget:
                raise RebuildBlocked("GEMINI_BUDGET_EXHAUSTED")
            attempt = attempts_dir / f"{cache_key}_{number}"
            write_json_immutable(attempt / "reservation.json", {
                "bindings": bindings, "request_key": cache_key, "reserved_usd": str(ceiling),
                "created_at_real": utc_now_iso(), "attempt": number,
            })
            spent += ceiling
            write_json_immutable(attempt / "request.json", {"request": payload, "fingerprints": fingerprints})
            try:
                status, raw = transport(payload, config)
            except requests.RequestException:
                write_json_immutable(attempt / "result.json", {
                    "status": "TRANSPORT_ERROR", "billing_status": "UNKNOWN_RESERVED", "usage": None,
                    "model_version": None, "completed_at_real": utc_now_iso(),
                })
                if number < 3:
                    sleep(2 ** number)
                    continue
                raise RebuildBlocked("GEMINI_TRANSPORT_ERROR") from None
            version = raw.get("modelVersion") if isinstance(raw, dict) else None
            usage = raw.get("usageMetadata") if isinstance(raw, dict) else None
            # Error payloads are omitted: they may include request headers or secrets.
            write_json_immutable(attempt / "result.json", {
                "status": status, "model_version": version, "usage": usage,
                "provider_response": raw if status == 200 else None,
                "completed_at_real": utc_now_iso(), "billing_status": "RESERVED_UPPER_BOUND",
            })
            if status == 429 or 500 <= status < 600:
                if number < 3:
                    sleep(2 ** number)
                    continue
                raise RebuildBlocked("GEMINI_RETRY_LIMIT")
            if status != 200:
                raise RebuildBlocked(f"GEMINI_HTTP_{status}")
            if not isinstance(version, str) or not version:
                raise RebuildBlocked("GEMINI_MODEL_VERSION_UNAVAILABLE")
            if observed_versions and observed_versions != {version}:
                raise RebuildBlocked("GEMINI_MODEL_VERSION_CHANGED")
            response = validate_response(raw, config["relations"])
            saved = {"provider_response": raw, "validated_response": response, "model_version": version,
                     "usage": usage, "attempt_result_sha256": sha256_file(attempt / "result.json")}
            set_cached_response(cache, cache_key, saved, fingerprints)
            return saved
    raise RebuildBlocked("Gemini capture did not complete")
