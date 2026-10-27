from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts.inspect_m2_reuse import (
    execution_blockers,
    model_configs_for_candidate,
    source_readiness,
    validate_candidate,
    validate_job_inventory,
    validate_saved_model_configs,
)


def candidate() -> dict:
    return yaml.safe_load(Path("configs/m2_data_3_1_candidate_v2.yaml").read_bytes())


def test_candidate_has_explicit_training_values_and_cannot_activate_scientific_execution() -> None:
    cfg = candidate()
    validate_candidate(cfg)
    assert cfg["measurement"]["cosine_estimand"] == "affine"
    assert cfg["reference"]["minimum_entities_after_LTO"] == 50
    assert cfg["alignment"]["minimum_rank_fraction"] == 0.9
    assert model_configs_for_candidate(cfg)["13"]["dimension"] == 64
    reasons = execution_blockers(cfg, {"ready": False})
    assert "SOURCE_BASELINE_INCOMPLETE" in reasons
    assert "CANDIDATE_NOT_ACTIVE" in reasons
    assert "STRUCTURAL_FREQUENCY_UNREGISTERED" in reasons


@pytest.mark.parametrize("change", ["status", "training", "measurement", "source_replacement", "seed", "missing_batch",
                                   "missing_manifest_binding", "invalid_binding_hash", "release_scope"])
def test_reuse_inspection_rejects_silent_scope_changes(change: str) -> None:
    cfg = candidate()
    if change == "status":
        cfg["status"] = "APPROVED"
    elif change == "training":
        cfg["execution"]["training_allowed"] = True
    elif change == "measurement":
        cfg["execution"]["measurement_allowed"] = True
    elif change == "source_replacement":
        cfg["source_baseline"]["replacement_authorized"] = True
    elif change == "seed":
        cfg["kge"]["seeds"] = [13, 37, 201]
    elif change == "missing_batch":
        cfg["kge"].pop("batch_size")
    elif change == "missing_manifest_binding":
        cfg["bindings"].pop(cfg["backbone"]["run"] + "/experiment_manifest.json")
    elif change == "invalid_binding_hash":
        cfg["bindings"]["configs/protocol_v1.yaml"] = "missing"
    else:
        cfg["release_id"] = "other_release"
    with pytest.raises(ValueError):
        validate_candidate(cfg)


def test_checkpoint_reuse_requires_exact_model_configuration() -> None:
    cfg = candidate()
    saved = model_configs_for_candidate(cfg)
    validate_saved_model_configs(cfg, saved)
    altered = copy.deepcopy(saved)
    altered["37"]["learning_rate"] = 0.02
    with pytest.raises(ValueError):
        validate_saved_model_configs(cfg, altered)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra_seed", "boolean_seed"])
def test_job_inventory_requires_exact_snapshot_seed_coverage(change: str) -> None:
    records = [{"snapshot_id": sid, "seed": seed} for sid in ("T01", "T02") for seed in (13, 37, 101)]
    if change == "missing":
        records.pop()
    elif change == "duplicate":
        records[-1] = dict(records[0])
    elif change == "extra_seed":
        records[-1]["seed"] = 201
    else:
        records[-1]["seed"] = True
    with pytest.raises(ValueError):
        validate_job_inventory(records, ["T01", "T02"], [13, 37, 101])


@pytest.mark.parametrize("condition", ["exact", "missing", "substituted", "protocol_conflict"])
def test_source_readiness_requires_exact_originals_and_protocol_agreement(tmp_path: Path, condition: str) -> None:
    lock = {}
    protocol = {"sources": {}}
    for role in ("proposal", "execution_plan", "patch"):
        data = (role + " fixture original").encode()
        file = tmp_path / f"{role}.txt"
        file.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        lock[role] = {"path": file.name, "sha256": digest}
        protocol["sources"][role + "_sha256"] = digest
    if condition == "missing":
        (tmp_path / "patch.txt").unlink()
    elif condition == "substituted":
        (tmp_path / "patch.txt").write_bytes(b"substitute")
    elif condition == "protocol_conflict":
        protocol["sources"]["patch_sha256"] = hashlib.sha256(b"other version").hexdigest()
    (tmp_path / "lock.json").write_text(json.dumps(lock), encoding="utf-8")
    (tmp_path / "protocol.yaml").write_text(yaml.safe_dump(protocol), encoding="utf-8")
    cfg = {"source_baseline": {"lock_path": "lock.json", "protocol_path": "protocol.yaml"}}
    result = source_readiness(tmp_path, cfg)
    assert result["ready"] is (condition == "exact")


def test_registry_completion_flags_cannot_remove_unregistered_numeric_choices() -> None:
    cfg = candidate()
    reasons = execution_blockers(cfg, {"ready": True})
    assert "CANDIDATE_NOT_ACTIVE" in reasons
    assert "EPSILON_NOT_SCIENTIFICALLY_REGISTERED" in reasons
    assert "STRUCTURAL_MERGE_ORDER_UNREGISTERED" in reasons
