import pytest
import yaml

from kg_pipeline.locked_mode import (
    scientific_locked_flag,
    validate_dependency_lock_content,
    validate_scientific_locked_run,
)
from kg_pipeline.run import init_run, load_run_manifest
from kg_pipeline.storage import read_yaml, ArtifactConflict
from temporal.schema import ContractError


def _locked_config():
    return {
        "scientific_locked": True,
        "resolved_config": {
            "llm_adapter": {
                "type": "local",
                "base_url": "http://127.0.0.1:8000/v1",
            "model": "model-v1",
            "model_revision": "sha256:model-pin",
            "tokenizer_revision": "sha256:tokenizer-pin",
            "temperature": 0.0,
            "top_p": None,
            "max_tokens": None,
            }
        },
    }


def _run_manifest(status="FROZEN"):
    return {
        "scientific_locked": True,
        "config_approval": {"status": status},
        "config_candidates": [
            {"path": "pyproject.toml", "exists": True, "sha256": "b" * 64},
            {"path": "requirements.lock.txt", "exists": True, "sha256": "a" * 64},
        ],
    }


def test_locked_mode_requires_frozen_baseline_and_pinned_local_adapter():
    config = _locked_config()
    metadata = config["resolved_config"]["llm_adapter"]
    validate_scientific_locked_run(config, _run_manifest(), adapter_metadata=metadata)


def test_locked_dependency_validation_rejects_unpinned_or_unlocked_dependencies():
    project = {"project": {"dependencies": ["example-pkg==1.2.3"]}}
    validate_dependency_lock_content(project, "example_pkg==1.2.3\ntransitive==4.5.6\n")
    with pytest.raises(ContractError, match="exact package==version pins"):
        validate_dependency_lock_content(
            {"project": {"dependencies": ["example-pkg>=1.2.3"]}},
            "example-pkg==1.2.3\n",
        )
    with pytest.raises(ContractError, match="not exactly pinned"):
        validate_dependency_lock_content(project, "example-pkg==1.2.2\n")


@pytest.mark.parametrize("value", ["false", 1, None])
def test_locked_flag_rejects_truthy_or_ambiguous_config_values(value):
    with pytest.raises(ContractError, match="YAML boolean"):
        scientific_locked_flag({"scientific_locked": value})


def test_locked_mode_rejects_draft_baseline_and_remote_endpoint():
    config = _locked_config()
    with pytest.raises(ContractError, match="frozen configuration"):
        validate_scientific_locked_run(config, _run_manifest("PROPOSED_UNFROZEN"))

    config["resolved_config"]["llm_adapter"]["base_url"] = "https://hosted.example/v1"
    with pytest.raises(ContractError, match="local inference endpoint"):
        validate_scientific_locked_run(config, _run_manifest())


def test_run_manifest_binds_locked_mode_and_cannot_be_downgraded(tmp_path, monkeypatch):
    from kg_pipeline import run as run_module

    frozen_approval = {
        "status": "FROZEN", "approval_blockers": [], "baseline_id": "fixture-baseline",
        "baseline_sha256": "a" * 64, "approval_file_sha256": "b" * 64,
    }
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.0.1"\ndependencies=["fixture==1.0.0"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.lock.txt").write_text("fixture==1.0.0\n", encoding="utf-8")
    monkeypatch.setattr(run_module, "inspect_config_approval", lambda *args, **kwargs: frozen_approval)
    adapter_path = tmp_path / "config" / "llm_adapter.yaml"
    adapter_path.parent.mkdir(parents=True)
    adapter_path.write_text(yaml.safe_dump(_locked_config()["resolved_config"]["llm_adapter"]), encoding="utf-8")
    init_run(tmp_path, "locked_fixture", mode="extraction", scientific_locked=True)
    manifest = load_run_manifest(tmp_path, "locked_fixture")
    bundle = read_yaml(tmp_path / "runs/locked_fixture/inputs/proposed_config_bundle.yaml")
    assert manifest["scientific_locked"] is True
    assert bundle["scientific_locked"] is True
    assert bundle["resolved_config"]["llm_adapter"]["type"] == "local"
    assert any(item["path"] == "config/llm_adapter.yaml" for item in manifest["config_candidates"])
    with pytest.raises(ArtifactConflict, match="cannot be changed in place"):
        init_run(tmp_path, "locked_fixture", mode="extraction", scientific_locked=False)


def test_locked_extraction_requires_explicit_local_adapter_before_creating_run(tmp_path, monkeypatch):
    from kg_pipeline import run as run_module

    frozen_approval = {
        "status": "FROZEN", "approval_blockers": [], "baseline_id": "fixture-baseline",
        "baseline_sha256": "a" * 64, "approval_file_sha256": "b" * 64,
    }
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.0.1"\ndependencies=["fixture==1.0.0"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.lock.txt").write_text("fixture==1.0.0\n", encoding="utf-8")
    monkeypatch.setattr(run_module, "inspect_config_approval", lambda *args, **kwargs: frozen_approval)
    with pytest.raises(ArtifactConflict, match="pinned local adapter"):
        init_run(tmp_path, "locked_missing_adapter", mode="extraction", scientific_locked=True)
    assert not (tmp_path / "runs" / "locked_missing_adapter").exists()


def test_locked_run_rejects_unapproved_baseline(tmp_path):
    with pytest.raises(ArtifactConflict, match="draft or unapproved"):
        init_run(tmp_path, "locked_draft", mode="extraction", scientific_locked=True)


def test_run_bundle_tampering_invalidates_run_manifest(tmp_path):
    init_run(tmp_path, "bundle_fixture", mode="inventory")
    bundle_path = tmp_path / "runs/bundle_fixture/inputs/proposed_config_bundle.yaml"
    bundle = read_yaml(bundle_path)
    bundle["scientific_locked"] = True
    bundle_path.write_text(yaml.safe_dump(bundle), encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="bundle semantic hash mismatch"):
        load_run_manifest(tmp_path, "bundle_fixture")
