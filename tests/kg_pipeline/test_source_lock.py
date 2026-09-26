import hashlib
import json

import pytest
import yaml

from kg_pipeline.baseline import inspect_source_lock


@pytest.fixture
def source_repo(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "data/manifests").mkdir(parents=True)
    lock = {}
    sources = {}
    for role in ("proposal", "execution_plan", "patch"):
        payload = f"Synthetic test source: {role}".encode()
        relative = f"sources/{role}.txt"
        (tmp_path / relative).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        lock[role] = {"path": relative, "sha256": digest}
        sources[f"{role}_sha256"] = digest
    (tmp_path / "configs/protocol_v1.yaml").write_text(yaml.safe_dump({"sources": sources}), encoding="utf-8")
    (tmp_path / "data/manifests/sources.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return tmp_path, lock


def test_complete_source_baseline_passes(source_repo):
    root, _ = source_repo
    assert inspect_source_lock(root)["status"] == "PASS"


@pytest.mark.parametrize("role", ["proposal", "execution_plan", "patch"])
def test_missing_required_role_blocks(source_repo, role):
    root, lock = source_repo
    del lock[role]
    (root / "data/manifests/sources.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    assert inspect_source_lock(root)["status"] == "BLOCKED"


def test_reanchored_lock_does_not_replace_protocol(source_repo):
    root, lock = source_repo
    payload = b"Unapproved replacement"
    (root / lock["proposal"]["path"]).write_bytes(payload)
    lock["proposal"]["sha256"] = hashlib.sha256(payload).hexdigest()
    (root / "data/manifests/sources.lock.json").write_text(json.dumps(lock), encoding="utf-8")
    assert inspect_source_lock(root)["status"] == "BLOCKED"


def test_missing_original_blocks(source_repo):
    root, lock = source_repo
    (root / lock["patch"]["path"]).unlink()
    assert inspect_source_lock(root)["status"] == "BLOCKED"


def test_changed_original_blocks(source_repo):
    root, lock = source_repo
    (root / lock["patch"]["path"]).write_bytes(b"changed")
    assert inspect_source_lock(root)["status"] == "BLOCKED"


def test_malformed_protocol_blocks(source_repo):
    root, _ = source_repo
    (root / "configs/protocol_v1.yaml").write_text("[", encoding="utf-8")
    assert inspect_source_lock(root)["status"] == "BLOCKED"
