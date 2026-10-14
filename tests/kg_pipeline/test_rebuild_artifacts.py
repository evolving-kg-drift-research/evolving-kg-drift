from __future__ import annotations

import json

import pytest

from kg_pipeline.hashing import sha256_file
from kg_pipeline.rebuild_artifacts import RebuildBlocked, artifact_path, read_verified, require_decision


@pytest.mark.parametrize("path", ["../secret", "/tmp/a", "C:/a", "data/locked_test/a", ".git/config", "a\\b"])
def test_forbidden_inputs_rejected_before_read(tmp_path, path):
    with pytest.raises(RebuildBlocked):
        artifact_path(tmp_path, path)


def test_exact_hash_checked_before_content_read(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('{"a":1}', encoding="utf-8")
    ref = {"path": "a.json", "sha256": sha256_file(p)}
    assert read_verified(tmp_path, ref) == {"a": 1}
    p.write_text('{"a":2}', encoding="utf-8")
    with pytest.raises(RebuildBlocked, match="changed"):
        read_verified(tmp_path, ref)


def test_draft_status_is_not_exact_approval(tmp_path):
    p = tmp_path / "decisions/decision_log.jsonl"
    p.parent.mkdir()
    record = {"decision_id": "d", "action": "approve_hosted_extraction", "approved_by": "fixture-reviewer",
              "date_real": "2026-10-14", "bindings": {"config": "a" * 64}}
    p.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert require_decision(tmp_path, "d", action=record["action"], bindings=record["bindings"]) == record
    with pytest.raises(RebuildBlocked):
        require_decision(tmp_path, "d", action=record["action"], bindings={"config": "b" * 64})
