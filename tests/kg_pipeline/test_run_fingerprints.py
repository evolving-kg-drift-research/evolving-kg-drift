import pytest
import yaml

from kg_pipeline.inventory import run_inventory
from kg_pipeline.run import init_run, load_run_manifest
from kg_pipeline.storage import ArtifactConflict


@pytest.mark.parametrize("relative", ["config/sources.yaml", "config/filter_policy_v1.yaml", "requirements.lock.txt", "src/kg_pipeline/example.py"])
def test_changed_dependency_prevents_resume(tmp_path, relative):
    init_run(tmp_path, "fingerprint_fixture", mode="inventory")
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="differs"):
        load_run_manifest(tmp_path, "fingerprint_fixture")
    with pytest.raises(ArtifactConflict, match="differs"):
        init_run(tmp_path, "fingerprint_fixture", mode="inventory")
    with pytest.raises(ArtifactConflict, match="differs"):
        run_inventory(tmp_path, "fingerprint_fixture", verify_inputs=False)
    assert not list((tmp_path / "runs/fingerprint_fixture/tables").glob("*.parquet"))


def test_unchanged_run_can_be_reused(tmp_path):
    init_run(tmp_path, "unchanged_fixture", mode="inventory")
    assert init_run(tmp_path, "unchanged_fixture", mode="inventory")["manifest"]["status"] == "REUSED"


@pytest.mark.parametrize("field,value", [("code_fingerprint_sha256", "changed"), ("raw_input_roots", ["other"]), ("run_id", "other_run")])
def test_manifest_mutation_detected(tmp_path, field, value):
    init_run(tmp_path, "manifest_fixture", mode="inventory")
    path = tmp_path / "runs/manifest_fixture/run_manifest.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="semantic hash mismatch"):
        load_run_manifest(tmp_path, "manifest_fixture")


def test_missing_configuration_never_automatically_frozen(tmp_path):
    init_run(tmp_path, "unapproved_fixture", mode="inventory")
    bundle = yaml.safe_load((tmp_path / "runs/unapproved_fixture/inputs/proposed_config_bundle.yaml").read_text(encoding="utf-8"))
    assert bundle["status"] == "PROPOSED_UNFROZEN"
    assert bundle["approval_blockers"]


def test_changed_approval_prevents_resume(tmp_path, monkeypatch):
    import json
    from kg_pipeline.hashing import sha256_file, sha256_json
    from kg_pipeline import run

    (tmp_path / "config").mkdir()
    relative = "config/example.yaml"
    (tmp_path / relative).write_text("version: 1\n", encoding="utf-8")
    digest = sha256_file(tmp_path / relative)
    files = {relative: digest}

    monkeypatch.setattr(run, "config_fingerprints", lambda x: [{"path": relative, "exists": True, "sha256": digest}])

    (tmp_path / "data/manifests").mkdir(parents=True)
    approval = {"status": "APPROVED", "baseline_id": "synthetic_fixture", "decision_id": "fixture_decision", "files": files}
    (tmp_path / "data/manifests/config_baseline.json").write_text(json.dumps(approval), encoding="utf-8")

    (tmp_path / "decisions").mkdir()
    decision = {
        "decision_id": "fixture_decision",
        "action": "approve_config_baseline",
        "baseline_sha256": sha256_json({"baseline_id": "synthetic_fixture", "files": files}),
        "approved_by": "reviewer",
        "date_real": "2026-09-20"
    }
    log_path = tmp_path / "decisions/decision_log.jsonl"
    log_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")

    # Write a dummy protocol so it doesn't fail parsing, though config_candidates covers many
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/protocol_v1.yaml").write_text("sources: {}\n", encoding="utf-8")

    init_run(tmp_path, "approval_fixture", mode="inventory")

    # Change the decision log so approval is no longer FROZEN
    log_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ArtifactConflict, match="Configuration approval differs"):
        load_run_manifest(tmp_path, "approval_fixture")
