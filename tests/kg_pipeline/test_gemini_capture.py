from __future__ import annotations

from copy import deepcopy
import json

import pytest
import requests

from kg_pipeline.gemini_capture import capture_or_replay, request_payload, validate_response
from kg_pipeline.hashing import sha256_file, sha256_json
from kg_pipeline.llm_cache import CacheIntegrityError
from kg_pipeline.rebuild_artifacts import RebuildBlocked


@pytest.fixture(autouse=True)
def fixture_pipeline_guards(monkeypatch):
    # Only isolate already-tested upstream guards; no bypass argument exists in production.
    monkeypatch.setattr("kg_pipeline.run.load_run_manifest", lambda *args: {"scientific_locked": True})
    monkeypatch.setattr("kg_pipeline.gates.require_gate_a", lambda *args: {"gate": "A", "status": "PASS"})


def setup(tmp_path):
    body = tmp_path / "body.txt"
    body.write_text("Alpha works at Beta.", encoding="utf-8")
    item = {"article_id": "article", "public_content": True,
            "body_ref": {"path": "body.txt", "sha256": sha256_file(body)}}
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps([item]), encoding="utf-8")
    config = {"model": "gemini-3.8-flash", "api_version": "v1beta", "phase": "pilot",
              "payload_policy": "approved_public_clean_text_only", "relations": ["works_at"],
              "prompt_template": "Only extract {relations}, with exact spans, from:\n{text}",
              "max_input_chars": 1000, "max_output_tokens": 500, "temperature": 0,
              "budget_usd": "1.00", "attempt_cost_ceiling_usd": "0.25"}
    registration = {"decision_id": "fixture-approved", "inventory_ref": {
        "path": "inventory.json", "sha256": sha256_file(inventory)}}
    decision = {"decision_id": "fixture-approved", "approved_by": "fixture reviewer", "date_real": "2026-10-14",
                "action": "approve_hosted_extraction", "bindings": {"config_sha256": sha256_json(config),
                "inventory_sha256": registration["inventory_ref"]["sha256"], "phase": "pilot",
                "scope": "candidate_extraction_only"}}
    p = tmp_path / "decisions/decision_log.jsonl"
    p.parent.mkdir()
    p.write_text(json.dumps(decision) + "\n", encoding="utf-8")
    run = tmp_path / "runs/fixture-gemini"
    run.mkdir(parents=True)
    return run, config, registration, item


def response(claims=None):
    if claims is None:
        claims = [{"subject_mention": "Alpha", "relation_name": "works_at", "object_mention": "Beta",
                   "evidence_span_start": 0, "evidence_span_end": 20, "valid_from_extracted": None,
                   "valid_to_extracted": None, "is_negative": False, "is_speculative": False}]
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"claims": claims})}]}}],
            "modelVersion": "fixture-version-1", "usageMetadata": {"totalTokenCount": 35}}


def forbidden(*args):
    pytest.fail("Replay or blocked capture attempted network")


def test_capture_and_replay_preserve_response_and_never_send_credentials(tmp_path, monkeypatch):
    run, config, registration, item = setup(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-fixture-key")
    seen = []

    def transport(payload, settings):
        seen.append(payload)
        assert "tools" not in payload and "systemInstruction" not in payload
        assert "secret-fixture-key" not in json.dumps(payload)
        return 200, response()

    captured = capture_or_replay(tmp_path, run, config, registration, item, mode="capture", transport=transport)
    replay = capture_or_replay(tmp_path, run, config, registration, item, mode="replay", transport=forbidden)
    assert replay == captured and len(seen) == 1
    for p in run.rglob("*.json"):
        assert "secret-fixture-key" not in p.read_text(encoding="utf-8")


def test_replay_missing_cache_cannot_fall_back_to_api(tmp_path):
    run, config, registration, item = setup(tmp_path)
    with pytest.raises(CacheIntegrityError, match="network is forbidden"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="replay", transport=forbidden)


def test_registration_tampering_and_unapproved_article_block_before_call(tmp_path):
    run, config, registration, item = setup(tmp_path)
    config["max_output_tokens"] = 1000
    with pytest.raises(RebuildBlocked, match="exact dependencies"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="capture", transport=forbidden)


def test_whole_article_is_never_truncated(tmp_path):
    _, config, _, _ = setup(tmp_path)
    config["max_input_chars"] = 5
    with pytest.raises(RebuildBlocked, match="OVER_INPUT_LIMIT"):
        request_payload("Alpha works at Beta.", config)


@pytest.mark.parametrize("mutation", ["missing", "truncated", "blocked", "json", "incomplete", "offset_bool", "tools"])
def test_malformed_response_never_becomes_empty_claims(mutation):
    raw = response()
    candidate = raw["candidates"][0]
    if mutation == "missing":
        candidate["content"]["parts"][0]["text"] = "{}"
    elif mutation == "truncated":
        candidate["finishReason"] = "MAX_TOKENS"
    elif mutation == "blocked":
        raw["promptFeedback"] = {"blockReason": "SAFETY"}
    elif mutation == "json":
        candidate["content"]["parts"][0]["text"] = "invalid"
    elif mutation == "tools":
        candidate["content"]["parts"] = [{"functionCall": {}}]
    else:
        claims = json.loads(candidate["content"]["parts"][0]["text"])["claims"]
        if mutation == "incomplete":
            claims[0].pop("object_mention")
        else:
            claims[0]["evidence_span_start"] = True
        candidate["content"]["parts"][0]["text"] = json.dumps({"claims": claims})
    with pytest.raises(RebuildBlocked):
        validate_response(raw, ["works_at"])
    assert validate_response(response([]), ["works_at"]) == {"claims": []}


def test_retry_reserves_before_call_and_keeps_all_attempts(tmp_path):
    run, config, registration, item = setup(tmp_path)
    seen = []

    def transport(payload, settings):
        seen.append(len(list((run / "gemini_attempts").glob("*/reservation.json"))))
        return (429, {"error": "private-detail"}) if len(seen) == 1 else (200, response())

    capture_or_replay(tmp_path, run, config, registration, item, mode="capture", transport=transport, sleep=lambda _: None)
    assert seen == [1, 2]
    reservations = [json.loads(p.read_text()) for p in (run / "gemini_attempts").glob("*/reservation.json")]
    assert len(reservations) == 2 and all(r["reserved_usd"] == "0.25" for r in reservations)


def test_unknown_timeout_spend_is_reserved_and_interrupted_resume_blocks(tmp_path):
    run, config, registration, item = setup(tmp_path)

    def timeout(*args):
        raise requests.Timeout("Secret headers must not be copied")

    with pytest.raises(RebuildBlocked, match="TRANSPORT"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="capture", transport=timeout, sleep=lambda _: None)
    assert len(list((run / "gemini_attempts").glob("*/reservation.json"))) == 3
    with pytest.raises(RebuildBlocked, match="Interrupted"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="capture", transport=forbidden)


def test_budget_exhaustion_is_before_next_request(tmp_path):
    run, config, registration, item = setup(tmp_path)
    # Use a second approved article and a single-attempt budget.
    config["budget_usd"] = "0.25"
    p = tmp_path / "decisions/decision_log.jsonl"
    decision = json.loads(p.read_text())
    decision["bindings"]["config_sha256"] = sha256_json(config)
    p.write_text(json.dumps(decision) + "\n")
    calls = []
    with pytest.raises(RebuildBlocked, match="BUDGET"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="capture",
                          transport=lambda *args: (calls.append(1) or 429, {}), sleep=lambda _: None)
    assert calls == [1]


def test_provider_version_drift_is_not_cached(tmp_path):
    run, config, registration, item = setup(tmp_path)
    config["expected_model_version"] = "expected"
    p = tmp_path / "decisions/decision_log.jsonl"
    decision = json.loads(p.read_text())
    decision["bindings"]["config_sha256"] = sha256_json(config)
    p.write_text(json.dumps(decision) + "\n")
    with pytest.raises(RebuildBlocked, match="VERSION_CHANGED"):
        capture_or_replay(tmp_path, run, config, registration, item, mode="capture",
                          transport=lambda *args: (200, deepcopy(response())))
    assert not list((run / "gemini_cache").glob("*.json"))
