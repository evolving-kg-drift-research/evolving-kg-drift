from __future__ import annotations

import json
import copy
from dataclasses import asdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from scripts.inspect_m2_inputs import inspect_package, inspect_snapshot, safe_file, sha
from scripts.run_m2_pilot import select_dimension, stratified_anchors, train_replayed, validation_split
from scripts.verify_m2_pilot import verify_alignment, verify_ranks
from drift.procrustes import align_embeddings_procrustes
from kge.contract import SnapshotDataset
from kge.model import TransEConfig


def package_fixture(tmp_path: Path) -> tuple[Path, list[dict]]:
    package = tmp_path / "package"
    (package / "snapshots").mkdir(parents=True)
    (package / "config").mkdir()
    specs = []
    for sid, cutoff in (("T01", "2025-01-01T00:00:00Z"), ("T02", "2025-02-01T00:00:00Z")):
        rows = [{"subject_id": "a", "relation_id": "r", "object_id": "b"}]
        path = package / f"snapshots/snapshot_{sid}_canonical.parquet"
        pq.write_table(pa.Table.from_pylist(rows), path)
        digest = sha(path.read_bytes())
        content = {"table_name": "snapshot_facts_canonical", "contract_version": "fixture", "rows": rows}
        semantic = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        path.with_suffix(".parquet.manifest.json").write_text(json.dumps({
            "table_name": content["table_name"], "contract_version": "fixture",
            "semantic_sha256": sha(semantic), "physical_sha256_computed_at_real": digest, "row_count": 1,
        }), encoding="utf-8")
        (package / f"snapshots/snapshot_{sid}_manifest.yaml").write_text(yaml.safe_dump({
            "snapshot_id": sid, "cutoff": cutoff, "canonical_triple_count": 1,
            "entity_count": 2, "canonical_physical_sha256": digest,
        }), encoding="utf-8")
        specs.append({"snapshot_id": sid, "cutoff": cutoff,
                      "parquet_path": path.relative_to(package).as_posix(), "edges": 1, "entities": 2})
    (package / "config/downstream_transe_config.yaml").write_text(yaml.safe_dump({
        "total_snapshots": 2, "snapshots": specs}), encoding="utf-8")
    (package / "snapshot_boundaries.yaml").write_text(yaml.safe_dump({
        "n_snapshots": 2, "boundaries": [{"snapshot_id": s["snapshot_id"], "cutoff": s["cutoff"]}
                                          for s in specs]}), encoding="utf-8")
    return package, specs


def test_package_inspection_checks_real_bytes_without_certifying(tmp_path: Path) -> None:
    package, _ = package_fixture(tmp_path)
    datasets, report = inspect_package(package)
    assert list(datasets) == ["T01", "T02"]
    assert report["status"] == "PACKAGE_TECHNICAL_CHECKS_PASS"
    assert report["scientific_certification"] is False
    assert report["transitions"][0]["persistent_entities"] == 2
    assert len(report["input_hashes"]) == 8


def test_canonical_export_can_retain_provenance_columns(tmp_path: Path) -> None:
    package, specs = package_fixture(tmp_path)
    path = package / specs[0]["parquet_path"]
    rows = [{"subject_id": "a", "relation_id": "r", "object_id": "b",
             "schema_version": "fixture", "fact_version_id": "fixture-fact",
             "logical_fact_id": "fixture-logical", "valid_from": "2025-01-01T00:00:00Z",
             "valid_to": None, "evidence_observed_at": "2025-01-01T00:00:00Z", "source_id": "fixture-source"}]
    pq.write_table(pa.Table.from_pylist(rows), path)
    sidecar = json.loads(path.with_suffix(".parquet.manifest.json").read_bytes())
    semantic = json.dumps({"table_name": sidecar["table_name"], "contract_version": sidecar["contract_version"],
                           "rows": rows}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    sidecar.update(physical_sha256_computed_at_real=sha(path.read_bytes()), semantic_sha256=sha(semantic))
    path.with_suffix(".parquet.manifest.json").write_text(json.dumps(sidecar), encoding="utf-8")
    manifest_path = package / "snapshots/snapshot_T01_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_bytes())
    manifest["canonical_physical_sha256"] = sha(path.read_bytes())
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    dataset, record, _ = inspect_snapshot(package, specs[0])
    assert dataset.triples[0].to_tuple() == ("a", "r", "b")
    assert record["source_columns"] == list(rows[0])


@pytest.mark.parametrize("field,value", [("edges", 3), ("entities", 3), ("cutoff", "2025-01-02T00:00:00Z")])
def test_snapshot_metadata_mismatch_fails_closed(tmp_path: Path, field: str, value: object) -> None:
    package, specs = package_fixture(tmp_path)
    with pytest.raises(ValueError, match="mismatch"):
        inspect_snapshot(package, {**specs[0], field: value})


@pytest.mark.parametrize("part", ["physical", "semantic", "rows"])
def test_snapshot_sidecar_tampering_rejected(tmp_path: Path, part: str) -> None:
    package, specs = package_fixture(tmp_path)
    path = package / (specs[0]["parquet_path"] + ".manifest.json")
    metadata = json.loads(path.read_bytes())
    field = {"physical": "physical_sha256_computed_at_real", "semantic": "semantic_sha256", "rows": "row_count"}[part]
    metadata[field] = 999 if part == "rows" else "0" * 64
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        inspect_snapshot(package, specs[0])


def test_cutoff_order_is_explicit_not_inferred(tmp_path: Path) -> None:
    package, specs = package_fixture(tmp_path)
    specs[1]["cutoff"] = specs[0]["cutoff"]
    (package / "config/downstream_transe_config.yaml").write_text(yaml.safe_dump({
        "total_snapshots": 2, "snapshots": specs}), encoding="utf-8")
    with pytest.raises(ValueError, match="strictly increasing"):
        inspect_package(package)


@pytest.mark.parametrize("relative", ["../outside.txt", "data/locked_test/payload.txt"])
def test_package_path_cannot_escape_or_access_locked_test(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError):
        safe_file(tmp_path, relative)


def ring() -> list[tuple[str, str, str]]:
    return [(f"e{i}", "r", f"e{(i + 1) % 12}") for i in range(12)]


def test_validation_split_preserves_coverage_and_is_outcome_blind() -> None:
    rows = ring() + [("singleton", "rare", "e0")]
    train, validation = validation_split(rows, 0.2, "fixture-v1")
    assert (train, validation) == validation_split(list(reversed(rows)), 0.2, "fixture-v1")
    assert not set(train) & set(validation)
    assert set(train) | set(validation) == set(rows)
    assert ("singleton", "rare", "e0") in train
    ds = SnapshotDataset.create("fixture", train)
    assert all(h in ds.entities and t in ds.entities and r in ds.relations for h, r, t in validation)


def test_validation_split_does_not_fake_empty_validation() -> None:
    with pytest.raises(ValueError, match="No coverage"):
        validation_split([("a", "r", "b")], 0.2, "fixture")


def test_pretransition_stratification_disjoint_and_deterministic() -> None:
    ds = SnapshotDataset.create("fixture", ring())
    a = stratified_anchors(ds, ds.entities, "fixture-v1", 0.6)
    b = stratified_anchors(ds, list(reversed(ds.entities)), "fixture-v1", 0.6)
    assert a == b
    assert not set(a.fit_anchors) & set(a.holdout_anchors)
    assert set(a.fit_anchors) | set(a.holdout_anchors) == set(ds.entities)


def test_infeasible_alignment_cannot_win_selection_by_validation() -> None:
    results = {"32": {"alignment_feasible": True, "mean_validation_MRR": 0.1},
               "64": {"alignment_feasible": False, "mean_validation_MRR": 1.0}}
    assert select_dimension(results) == 32
    results["32"]["alignment_feasible"] = False
    assert select_dimension(results) is None


def test_selection_tiebreak_is_declared_smaller_dimension() -> None:
    results = {str(d): {"alignment_feasible": True, "mean_validation_MRR": 0.1} for d in (64, 32)}
    assert select_dimension(results) == 32


def test_pilot_replays_exact_checkpoint_bytes_and_records_provenance(tmp_path: Path) -> None:
    ds = SnapshotDataset.create("fixture", ring())
    checkpoint, record = train_replayed(ds, TransEConfig(dimension=32, epochs=2, seed=13),
                                        tmp_path, {"commit": "fixture_commit", "dirty_state": True})
    assert record["exact_replay"] is True
    assert checkpoint.provenance.git_dirty is True
    assert checkpoint.provenance.snapshot_hash == ds.snapshot_hash
    assert (tmp_path / "seed_13_repeat_1.json").read_bytes() == (tmp_path / "seed_13_repeat_2.json").read_bytes()


def test_independent_verifier_rejects_changed_alignment_matrix(tmp_path: Path) -> None:
    ds = SnapshotDataset.create("fixture", ring())
    cp, _ = train_replayed(ds, TransEConfig(dimension=2, epochs=1, seed=13), tmp_path,
                           {"commit": "fixture", "dirty_state": True})
    split = stratified_anchors(ds, ds.entities, "fixture", 0.6)
    alignment = align_embeddings_procrustes(cp.entity_embeddings, cp.entity_embeddings, split)
    valid, _ = alignment.diagnostics.check_alignment_validity()
    record = {"dimension": 2, "Q": alignment.Q, "source_mean": alignment.source_mean,
              "target_mean": alignment.target_mean, "diagnostics": asdict(alignment.diagnostics),
              "full_rank": True, "operational_valid": valid}
    verify_alignment(record, cp, cp, asdict(split))
    changed = copy.deepcopy(record)
    changed["Q"][0][0] += 0.1
    with pytest.raises(ValueError, match="Q"):
        verify_alignment(changed, cp, cp, asdict(split))


def test_independent_verifier_rejects_changed_saved_rank(tmp_path: Path) -> None:
    from scripts.evaluate_legacy_t01 import evaluate
    import math

    ds = SnapshotDataset.create("fixture", ring())
    cp, _ = train_replayed(ds, TransEConfig(dimension=2, epochs=1, seed=13), tmp_path,
                           {"commit": "fixture", "dirty_state": True})
    positives = {t.to_tuple() for t in ds.triples}

    def score(triple: tuple[str, str, str]) -> float:
        h, r, t = triple
        return -math.sqrt(sum((a + b - c) ** 2 for a, b, c in zip(
            cp.entity_embeddings[h], cp.relation_embeddings[r], cp.entity_embeddings[t])))

    ranks = evaluate([ds.triples[0].to_tuple()], ds.entities, positives, score)
    assert verify_ranks(ranks, cp, positives) > 0
    ranks[0]["rank"] += 1
    with pytest.raises(ValueError, match="rank"):
        verify_ranks(ranks, cp, positives)
