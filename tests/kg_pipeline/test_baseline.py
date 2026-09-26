import json

import pytest
from kg_pipeline.baseline import inspect_config_approval
from kg_pipeline.hashing import sha256_file, sha256_json


def test_missing_approval_is_blocked(tmp_path):
    assert inspect_config_approval(tmp_path, [])["status"] == "PROPOSED_UNFROZEN"


def test_exact_decision_binding_and_changed_hash(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/example.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "data/manifests").mkdir(parents=True)
    (tmp_path / "decisions").mkdir()
    relative = "config/example.yaml"
    digest = sha256_file(tmp_path / relative)
    candidates = [{"path": relative, "exists": True, "sha256": digest}]
    files = {relative: digest}
    approval = {"status": "APPROVED", "baseline_id": "synthetic_fixture", "decision_id": "fixture_decision", "files": files}
    (tmp_path / "data/manifests/config_baseline.json").write_text(json.dumps(approval), encoding="utf-8")
    decision = {"decision_id": "fixture_decision", "action": "approve_config_baseline", "baseline_sha256": sha256_json({"baseline_id": "synthetic_fixture", "files": files}), "approved_by": "synthetic-test-reviewer", "date_real": "2026-09-20"}
    log = tmp_path / "decisions/decision_log.jsonl"
    log.write_text(json.dumps(decision) + "\n", encoding="utf-8")
    assert inspect_config_approval(tmp_path, candidates)["status"] == "FROZEN"
    candidates[0]["sha256"] = "0" * 64
    assert inspect_config_approval(tmp_path, candidates)["status"] == "PROPOSED_UNFROZEN"
    candidates[0]["sha256"] = digest
    decision["baseline_sha256"] = "wrong"
    log.write_text(json.dumps(decision) + "\n", encoding="utf-8")
    assert inspect_config_approval(tmp_path, candidates)["status"] == "PROPOSED_UNFROZEN"


@pytest.mark.parametrize("relative,content,expected_error", [
    ("configs/protocol_v1.yaml", "version: 1\n", "Protocol configuration lacks valid 'sources' mapping"),
    ("config/ontology.yaml", "version: 1\n", "Ontology configuration lacks 'relations'"),
    ("config/corpus_scope.yaml", "version: 1\n", "Corpus scope lacks date boundaries"),
])
def test_component_specific_validation(tmp_path, relative, content, expected_error):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    digest = sha256_file(path)
    candidates = [{"path": relative, "exists": True, "sha256": digest}]
    files = {relative: digest}

    (tmp_path / "data/manifests").mkdir(parents=True, exist_ok=True)
    approval = {"status": "APPROVED", "baseline_id": "synthetic_fixture", "decision_id": "fixture_decision", "files": files}
    (tmp_path / "data/manifests/config_baseline.json").write_text(json.dumps(approval), encoding="utf-8")

    (tmp_path / "decisions").mkdir(exist_ok=True)
    decision = {
        "decision_id": "fixture_decision",
        "action": "approve_config_baseline",
        "baseline_sha256": sha256_json({"baseline_id": "synthetic_fixture", "files": files}),
        "approved_by": "reviewer",
        "date_real": "2026-09-20"
    }
    (tmp_path / "decisions/decision_log.jsonl").write_text(json.dumps(decision) + "\n", encoding="utf-8")

    result = inspect_config_approval(tmp_path, candidates)
    assert result["status"] == "PROPOSED_UNFROZEN"
    assert any(expected_error in blocker for blocker in result["approval_blockers"])
