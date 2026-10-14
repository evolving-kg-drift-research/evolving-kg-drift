from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.inspect_m2_inputs import sha
from scripts.run_m2_backbone import PROPOSAL_SHA256, ROOT, model_config, validate_design
from scripts.run_m2_pilot import train_replayed
from scripts.verify_m2_backbone import verify_saved_job
from kge.contract import SnapshotDataset


def approved_design() -> tuple[dict[str, Any], dict[str, Any]]:
    return (yaml.safe_load((ROOT / "configs/m2_external_dev_v1.yaml").read_bytes()),
            yaml.safe_load((ROOT / "configs/m2_run_proposal.yaml").read_bytes()))


def test_design_is_hash_bound_to_approved_proposal() -> None:
    design, proposal = approved_design()
    actual_hash = sha((ROOT / "configs/m2_run_proposal.yaml").read_bytes())
    assert actual_hash == PROPOSAL_SHA256
    assert None in proposal  # Historical unquoted YAML key; preserve original bytes/hash.
    assert "null" in design
    assert design["null"] == proposal[None]
    validate_design(design, proposal, actual_hash)


def test_ambiguous_yaml_null_sections_are_rejected() -> None:
    design, proposal = approved_design()
    proposal["null"] = proposal[None]
    with pytest.raises(ValueError, match="ambiguous"):
        validate_design(design, proposal, PROPOSAL_SHA256)


@pytest.mark.parametrize("change", ["approval", "dimension", "seed", "epochs", "snapshot", "stage", "certification"])
def test_backbone_rejects_unapproved_scope_changes(change: str) -> None:
    design, proposal = approved_design()
    if change == "approval":
        design["approval"]["proposal_sha256"] = "0" * 64
    elif change == "dimension":
        design["kge"]["dimension"] = 32
    elif change == "seed":
        design["kge"]["seeds"] = [13, 37]
    elif change == "epochs":
        design["kge"]["epochs"] = 500
    elif change == "snapshot":
        design["snapshots"].append("T11")
    elif change == "stage":
        design["execution"]["next_stage_only"] = "drift"
    elif change == "certification":
        design["scientific_certification"] = True
    with pytest.raises((ValueError, PermissionError)):
        validate_design(design, proposal, PROPOSAL_SHA256)


def fixture_run(tmp_path: Path) -> tuple[SnapshotDataset, dict[str, Any], dict[str, Any], dict[str, Any]]:
    design, _ = approved_design()
    design["kge"]["epochs"] = 2  # Synthetic fixture only; execution guard forbids changing approved epochs.
    cfg = model_config(design, 13)
    ds = SnapshotDataset.create("T01", [(f"e{i}", "r", f"e{(i + 1) % 8}") for i in range(8)])
    git = {"commit": "fixture_commit", "dirty_state": True}
    ckpt, record = train_replayed(ds, cfg, tmp_path, git)
    record.update(path="seed_13_repeat_1.json", snapshot_hash=ds.snapshot_hash,
                  triples=len(ds.triples), entities=len(ds.entities), relations=len(ds.relations),
                  num_epochs=2, first_loss=ckpt.training_metrics["epoch_losses"][0],
                  final_loss=ckpt.training_metrics["final_loss"])
    return ds, asdict(cfg), record, git


def test_independent_saved_backbone_checks_full_mappings(tmp_path: Path) -> None:
    ds, cfg, record, git = fixture_run(tmp_path)
    maps = {"entities": ds.get_entity_mapping(), "relations": ds.get_relation_mapping()}
    checked = verify_saved_job(tmp_path, ds, cfg, record, maps, git)
    assert checked["snapshot_id"] == "T01"
    assert checked["seed"] == 13
    maps["entities"]["e0"], maps["entities"]["e1"] = maps["entities"]["e1"], maps["entities"]["e0"]
    with pytest.raises(ValueError, match="lineage"):
        verify_saved_job(tmp_path, ds, cfg, record, maps, git)


@pytest.mark.parametrize("mutation", ["snapshot", "config", "git", "sidecar", "loss", "dimension", "nonfinite"])
def test_saved_backbone_verifier_fails_closed_on_tampering(tmp_path: Path, mutation: str) -> None:
    ds, cfg, record, git = fixture_run(tmp_path)
    maps = {"entities": ds.get_entity_mapping(), "relations": ds.get_relation_mapping()}
    if mutation == "snapshot":
        record["snapshot_hash"] = "0" * 64
    elif mutation == "config":
        cfg["learning_rate"] = 0.02
    elif mutation == "git":
        git["commit"] = "another_commit"
    elif mutation == "sidecar":
        (tmp_path / "seed_13_repeat_2.json.sha256").write_text("0" * 64, encoding="utf-8")
    else:
        raw = json.loads((tmp_path / record["path"]).read_bytes())
        if mutation == "loss":
            raw["training_metrics"]["final_loss"] = -1.0
        elif mutation == "dimension":
            raw["entity_embeddings"]["e0"].pop()
        elif mutation == "nonfinite":
            raw["entity_embeddings"]["e0"][0] = float("nan")
        payload = json.dumps(raw, sort_keys=True).encode()
        for repeat in (1, 2):
            path = tmp_path / f"seed_13_repeat_{repeat}.json"
            path.write_bytes(payload)
            path.with_name(path.name + ".sha256").write_text(f"{sha(payload)}  {path.name}\n", encoding="utf-8")
        record = copy.deepcopy(record)
        record["checkpoint_sha256"] = sha(payload)
    with pytest.raises(ValueError):
        verify_saved_job(tmp_path, ds, cfg, record, maps, git)
