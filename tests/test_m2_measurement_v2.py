from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from drift.anchors import AnchorSplit, compute_anchor_hash
from drift.measurement_v2 import (
    build_drift_stage_v2, build_null_stage_v2, geometry_diagnostics_v2, saved_displacement_v2,
)
from drift.procrustes import align_embeddings_procrustes
from kge.checkpoint import CheckpointProvenance, KGECheckpoint
from kge.contract import SnapshotDataset
from scripts.run_m2_measurement_v2 import DEFAULT_CONFIG, ROOT, inspect_registration, load_stage_inputs, run
from scripts.verify_m2_measurement_v2 import verify_stage_v2


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     indent=2, allow_nan=False).encode()).hexdigest()


def settings(estimand: str = "affine") -> dict:
    return {"cosine_estimand": estimand, "norm_floor": 1e-12, "denominator_floor": 1e-12,
            "rank_relative_tolerance": 1e-6, "minimum_rank_fraction": 0.9,
            "maximum_normalized_orthogonality_error": 1e-6,
            "maximum_relative_holdout_residual": 10.0, "maximum_relative_fit_holdout_gap": 10.0,
            "gap_statistic": "absolute_holdout_minus_fit", "minimum_reference_entities": 2,
            "mad_threshold": 1e-12, "epsilon": 1e-4}


def inputs() -> tuple[dict, dict, dict, dict]:
    entities = [f"E{i}" for i in range(7)]
    checkpoints = {}
    for endpoint, time in (("T01", 0), ("T02", 1)):
        for index, seed in enumerate((13, 37, 101)):
            vectors = {e: [3.0 + i + index * 0.04 * (i % 3),
                           5.0 + i * i % 7 + time * (i % 2) * 0.3 + index * 0.07 * (i % 4)]
                       for i, e in enumerate(entities)}
            provenance = CheckpointProvenance(endpoint, digest(endpoint), seed, "TransE", 2, 2,
                                              digest(entities), digest(["r"]), digest(seed))
            cp = KGECheckpoint(provenance, vectors, {"r": [0.1, 0.2]}, {})
            checkpoints[endpoint, seed] = (cp, digest([endpoint, seed, cp.artifact_hash]))
    fit, holdout = entities[:4], entities[4:6]
    plan = {"split": {"fit_anchors": fit, "holdout_anchors": holdout}}
    split = AnchorSplit(tuple(fit), tuple(holdout), compute_anchor_hash(fit), compute_anchor_hash(holdout))
    jobs = [("T01", "T02", s, s, "cross_time") for s in (13, 37, 101)]
    jobs += [(sid, sid, a, b, "same_snapshot_cross_seed") for sid in ("T01", "T02")
             for a, b in ((13, 37), (13, 101), (37, 101))]
    alignments = {}
    for prev, nxt, a, b, kind in jobs:
        src, tgt = checkpoints[prev, a][0], checkpoints[nxt, b][0]
        result = align_embeddings_procrustes(src.entity_embeddings, tgt.entity_embeddings, split, kind)
        record = {"transition_id": "T01->T02", "alignment_type": kind,
                  "source_snapshot": prev, "target_snapshot": nxt, "source_seed": a, "target_seed": b,
                  "dimension": 2, "Q": result.Q, "source_mean": result.source_mean, "target_mean": result.target_mean,
                  "available": True, "unavailable_reason": "", "anchor_plan_hash": digest(plan),
                  "source_checkpoint_semantic_hash": src.artifact_hash,
                  "target_checkpoint_semantic_hash": tgt.artifact_hash,
                  "source_checkpoint_sha256": checkpoints[prev, a][1],
                  "target_checkpoint_sha256": checkpoints[nxt, b][1]}
        alignments[prev, nxt, a, b] = (record, digest(record), digest(record))
    return checkpoints, alignments, plan, dict.fromkeys(entities, "explicit_fixture_bucket")


def test_affine_and_centered_distances_are_distinct_and_explicit() -> None:
    q = [[1.0, 0.0], [0.0, 1.0]]
    assert saved_displacement_v2([11, 10], [10, 11], q, [10, 10], [10, 10], "centered", 1e-12) == pytest.approx(1.0)
    assert saved_displacement_v2([11, 10], [10, 11], q, [10, 10], [10, 10], "affine", 1e-12) == pytest.approx(1 - 220 / 221)


@pytest.mark.parametrize("estimand", ["affine", "centered"])
def test_both_stages_use_same_declared_geometry_and_independent_verifier(estimand: str) -> None:
    cps, alignments, plan, buckets = inputs()
    cfg = settings(estimand)
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg)
    assert null["alignment_available"] is True
    assert len(null["null_artifact"]["raw_observations"]) == 42
    assert null["null_artifact"]["configuration"]["cosine_estimand"] == estimand
    verify_stage_v2(null, cps, alignments, plan, buckets, cfg)
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg, null)
    assert len(drift["temporal_observations"]) == 21
    assert len(drift["entity_results"]) == 7
    assert drift["null_stage_sha256"] == digest(null)
    verify_stage_v2(drift, cps, alignments, plan, buckets, cfg, null)
    assert digest(null) == digest(build_null_stage_v2("T01->T02", cps, alignments, plan, dict(reversed(list(buckets.items()))), cfg))


def test_relative_residuals_use_fit_means_for_holdout_and_orthogonality_divides_by_dimension() -> None:
    cps, alignments, plan, _ = inputs()
    record = alignments["T01", "T02", 13, 13][0]
    result = geometry_diagnostics_v2(cps["T01", 13][0], cps["T02", 13][0], record, plan, settings())
    assert result["relative_holdout_residual"] > 0
    assert result["normalized_orthogonality_error"] == pytest.approx(result["raw_orthogonality_error"] / 2)
    assert result["relative_fit_holdout_gap"] == pytest.approx(abs(result["relative_holdout_residual"] - result["relative_fit_residual"]))


@pytest.mark.parametrize("field", ["norm_floor", "denominator_floor", "gap_statistic", "maximum_relative_holdout_residual", "epsilon"])
def test_missing_or_unregistered_settings_do_not_inherit_dev_defaults(field: str) -> None:
    cps, alignments, plan, buckets = inputs()
    cfg = settings()
    cfg[field] = None
    with pytest.raises(ValueError):
        build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg)


@pytest.mark.parametrize("change", ["missing_seed", "bad_alignment_digest", "physical_hash", "semantic_hash", "anchors", "mean", "rank_tolerance", "extra_entity"])
def test_saved_inputs_fail_closed_on_identity_and_lineage_corruption(change: str) -> None:
    cps, alignments, plan, buckets = inputs()
    cfg = settings()
    key = ("T01", "T01", 13, 37)
    record, physical, _ = alignments[key]
    if change == "missing_seed":
        cps.pop(("T01", 101))
    elif change == "bad_alignment_digest":
        alignments[key] = (record, physical, "0" * 64)
    elif change == "physical_hash":
        record["source_checkpoint_sha256"] = "0" * 64
    elif change == "semantic_hash":
        cps["T01", 13][0].entity_embeddings["E0"][0] += 1
    elif change == "anchors":
        plan["split"]["holdout_anchors"].append("E0")
    elif change == "mean":
        record["source_mean"][0] += 1
    elif change == "rank_tolerance":
        cfg["rank_relative_tolerance"] = True
    else:
        buckets["not_persistent"] = "explicit_fixture_bucket"
    if change in ("physical_hash", "mean"):
        alignments[key] = (record, physical, digest(record))
    with pytest.raises(ValueError):
        build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg)


def test_invalid_alignment_produces_unavailable_rows_without_sed_or_population_loss() -> None:
    cps, alignments, plan, buckets = inputs()
    cfg = settings()
    cfg["maximum_relative_holdout_residual"] = 1e-15
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg)
    assert null["alignment_available"] is False and null["null_artifact"] is None
    assert len(null["entity_results"]) == len(buckets)
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg, null)
    assert all(not row["available"] and row["SED_plus"] is None for row in drift["entity_results"])
    verify_stage_v2(null, cps, alignments, plan, buckets, cfg)
    verify_stage_v2(drift, cps, alignments, plan, buckets, cfg, null)


@pytest.mark.parametrize("change", ["distance", "diagnostic", "provenance", "calibration", "null_link", "population"])
def test_independent_verifier_rejects_corrupted_stage_results(change: str) -> None:
    cps, alignments, plan, buckets = inputs()
    cfg = settings()
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg)
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, cfg, null)
    altered = copy.deepcopy(drift)
    if change == "distance":
        altered["temporal_observations"][0]["temporal_displacement"] += 0.1
    elif change == "diagnostic":
        altered["diagnostics"][0]["relative_holdout_residual"] += 0.1
    elif change == "provenance":
        altered["temporal_observations"][0]["source_checkpoint_sha256"] = "0" * 64
    elif change == "calibration":
        altered["entity_results"][0]["signed_excess"] = 9.0
    elif change == "null_link":
        altered["null_stage_sha256"] = "0" * 64
    else:
        altered["entity_results"].pop()
    with pytest.raises(ValueError):
        verify_stage_v2(altered, cps, alignments, plan, buckets, cfg, null)


@pytest.mark.parametrize("estimand", ["affine", "centered"])
def test_undefined_cosine_raises_instead_of_fabricating_zero(estimand: str) -> None:
    with pytest.raises(ValueError):
        saved_displacement_v2([0, 0], [0, 0], [[1, 0], [0, 1]], [0, 0], [0, 0], estimand, 1e-12)


def test_current_candidate_reports_remaining_registration_without_execution() -> None:
    _, _, readiness, _ = inspect_registration(ROOT, DEFAULT_CONFIG)
    assert readiness["status"] == "BLOCKED"
    assert readiness["source_readiness"]["ready"] is True
    assert {"PROTOCOL_MEASUREMENT_V2_UNREGISTERED", "RUNNER_STAGE_NOT_REGISTERED"}.issubset(readiness["execution_blockers"])


def registered_fixture(root: Path) -> tuple[Path, dict]:
    """Synthetic registration and files confined to pytest tmp_path; never production defaults."""
    cps, alignments, anchors, buckets = inputs()
    parent = yaml.safe_load((ROOT / "configs/m2_data_3_1_candidate_v2.yaml").read_bytes())
    cfg = yaml.safe_load((ROOT / DEFAULT_CONFIG).read_bytes())

    def store(relative: str, value: object, yaml_format: bool = False) -> dict:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(value) if yaml_format else json.dumps(value, sort_keys=True, ensure_ascii=False,
                                                                          indent=2, allow_nan=False), encoding="utf-8")
        return {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    parent["status"] = "ACTIVE_REGISTERED"
    parent["snapshots"] = ["T01", "T02"]
    parent["kge"]["dimension"] = 2
    parent["reference"].update(frequency_definition="fixture_explicit_frequency", merge_order=["fixture_no_merge"],
                               minimum_entities_after_LTO=2, degree_bin_registration="scientifically_registered")
    parent["alignment"].update(fit_count=4, holdout_count=2, maximum_relative_holdout_residual=10.0,
                               maximum_relative_fit_holdout_gap=10.0, anchor_count_registration="scientifically_registered",
                               rank_tolerance_registration="scientifically_registered")
    for key in ("epsilon", "mad_threshold"):
        parent["measurement"][key]["registration"] = "scientifically_registered"
    parent["execution"].update(measurement_allowed=True, scientific_execution_allowed=True)
    specs = []
    for sid, cutoff in (("T01", "2025-01-01T00:00:00Z"), ("T02", "2025-02-01T00:00:00Z")):
        rows = [{"subject_id": f"E{i}", "relation_id": "r", "object_id": f"E{(i+1)%7}"} for i in range(7)]
        relative = f"{parent['package_root']}/snapshots/snapshot_{sid}_canonical.parquet"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), path)
        physical = hashlib.sha256(path.read_bytes()).hexdigest()
        semantic = {"table_name": "snapshot_facts_canonical", "contract_version": "fixture", "rows": rows}
        store(relative + ".manifest.json", {"table_name": semantic["table_name"], "contract_version": "fixture",
               "physical_sha256_computed_at_real": physical, "row_count": 7,
               "semantic_sha256": hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
        store(f"{parent['package_root']}/snapshots/snapshot_{sid}_manifest.yaml",
              {"snapshot_id": sid, "cutoff": cutoff, "canonical_triple_count": 7, "entity_count": 7,
               "canonical_physical_sha256": physical}, True)
        specs.append({"snapshot_id": sid, "cutoff": cutoff, "parquet_path": path.relative_to(root / parent["package_root"]).as_posix(),
                      "edges": 7, "entities": 7})
        dataset = SnapshotDataset.create(sid, [(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows])
        for seed in (13, 37, 101):
            old = cps[sid, seed][0]
            runtime = {k: parent["kge"][k] for k in ("dimension", "norm", "margin", "learning_rate", "epochs", "batch_size", "normalize_entities")}
            runtime["seed"] = seed
            prov = CheckpointProvenance(sid, dataset.snapshot_hash, seed, "TransE", 2, 2, dataset.compute_mapping_hash(),
                                        hashlib.sha256(json.dumps(dataset.get_relation_mapping(), sort_keys=True).encode()).hexdigest(),
                                        hashlib.sha256(json.dumps(runtime, sort_keys=True).encode()).hexdigest())
            cp = KGECheckpoint(prov, old.entity_embeddings, old.relation_embeddings, {})
            cp_path = root / f"fixtures/{sid}_seed{seed}.json"
            cp.save(cp_path)
            cps[sid, seed] = cp, hashlib.sha256(cp_path.read_bytes()).hexdigest()
    store(parent["package_root"] + "/config/downstream_transe_config.yaml", {"total_snapshots": 2, "snapshots": specs}, True)
    store(parent["package_root"] + "/snapshot_boundaries.yaml", {"n_snapshots": 2, "boundaries": specs}, True)
    release = store(parent["package_root"] + "/release_manifest.json", {"fixture": True})
    checkpoint_descriptors = [{"path": f"fixtures/{sid}_seed{seed}.json", "sha256": physical}
                              for (sid, seed), (_, physical) in cps.items()]
    alignment_descriptors = []
    for key, (record, _, _) in alignments.items():
        src, tgt, a, b = key
        record.update(source_checkpoint_semantic_hash=cps[src, a][0].artifact_hash,
                      target_checkpoint_semantic_hash=cps[tgt, b][0].artifact_hash,
                      source_checkpoint_sha256=cps[src, a][1], target_checkpoint_sha256=cps[tgt, b][1])
        alignment_descriptors.append(store(f"fixtures/{src}_{tgt}_{a}_{b}.json", record))
    plan = {"transition_id": "T01->T02", "anchor_plan": store("fixtures/anchors.json", anchors),
            "bucket_plan": store("fixtures/buckets.json", buckets), "checkpoints": checkpoint_descriptors,
            "alignments": alignment_descriptors}
    plan_descriptor = store("fixtures/input_plan.json", plan)
    sources = {}
    protocol = yaml.safe_load((ROOT / "configs/protocol_v1.yaml").read_bytes())
    for role in ("proposal", "execution_plan", "patch"):
        descriptor = store(f"fixtures/{role}.json", {"fixture_source_role": role})
        sources[role] = descriptor
        protocol["sources"][role + "_sha256"] = descriptor["sha256"]
    lock = store("data/manifests/sources.lock.json", sources)
    protocol["kge"]["dimension"] = 2
    protocol["alignment"].update(fit_count=4, holdout_count=2)
    protocol["drift"].update(mad_epsilon=settings()["epsilon"], measurement_v2={"settings": settings(),
                            "frequency_definition": parent["reference"]["frequency_definition"],
                            "merge_order": parent["reference"]["merge_order"], "approved_input_plan_sha256s": [plan_descriptor["sha256"]]})
    prot = store("configs/protocol_v1.yaml", protocol, True)
    parent["bindings"] = {d["path"]: d["sha256"] for d in (release, lock, prot)}
    cfg.update(status="REGISTERED_STAGE", settings=settings(), input_plan=plan_descriptor,
               parent_config=store("fixtures/parent.yaml", parent, True))
    cfg["execution"]["measurement_allowed"] = True
    store("fixtures/stage.yaml", cfg, True)
    return Path("fixtures/stage.yaml"), cfg


def test_file_backed_single_stage_runner_round_trip_and_drift_handoff(tmp_path: Path) -> None:
    relative, cfg = registered_fixture(tmp_path)
    null_out, ready = run(tmp_path, relative)
    assert ready is True and (null_out / "artifact.json").is_file()
    assert not (tmp_path / "outputs/m2_drift_v2").exists()
    artifact = json.loads((null_out / "artifact.json").read_bytes())
    assert artifact["component_version"] == "saved_checkpoint_null_stage_v2"
    cfg.update(stage="drift", null_stage={"path": (null_out / "artifact.json").relative_to(tmp_path).as_posix(),
                                         "sha256": hashlib.sha256((null_out / "artifact.json").read_bytes()).hexdigest()})
    (tmp_path / relative).write_text(yaml.safe_dump(cfg), encoding="utf-8")
    drift_out, ready = run(tmp_path, relative)
    assert ready is True and drift_out != null_out
    manifest = json.loads((drift_out / "experiment_manifest.json").read_bytes())
    assert manifest["inputs"]["snapshot_hash"] is not None
    assert manifest["inputs"]["entity_map_hash"] is not None
    assert manifest["scientific_certification"] is False
    assert json.loads((drift_out / "artifact.json").read_bytes())["null_stage_sha256"] == digest(artifact)


@pytest.mark.parametrize("change", ["source", "protocol", "parent_flag", "plan", "settings", "stage_flag", "auto_advance"])
def test_runner_registration_cannot_be_bypassed_by_status_flags(tmp_path: Path, change: str) -> None:
    relative, cfg = registered_fixture(tmp_path)
    if change == "source":
        (tmp_path / "fixtures/patch.json").write_text("substituted", encoding="utf-8")
    elif change == "protocol":
        cfg["settings"]["norm_floor"] *= 2
    elif change == "parent_flag":
        parent_path = tmp_path / cfg["parent_config"]["path"]
        parent = yaml.safe_load(parent_path.read_bytes())
        parent["execution"]["scientific_execution_allowed"] = False
        parent_path.write_text(yaml.safe_dump(parent), encoding="utf-8")
        cfg["parent_config"]["sha256"] = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    elif change == "plan":
        cfg["input_plan"]["sha256"] = "0" * 64
    elif change == "settings":
        cfg["settings"]["gap_statistic"] = None
    elif change == "stage_flag":
        cfg["execution"]["measurement_allowed"] = False
    else:
        cfg["execution"]["auto_execute_next_stage"] = True
    (tmp_path / relative).write_text(yaml.safe_dump(cfg), encoding="utf-8")
    if change == "auto_advance":
        with pytest.raises(ValueError):
            run(tmp_path, relative)
    else:
        out, ready = run(tmp_path, relative)
        assert ready is False and not (out / "artifact.json").exists()


@pytest.mark.parametrize("change", ["sidecar", "checkpoint", "mapping", "plan_hash"])
def test_file_loader_rejects_missing_or_tampered_real_files(tmp_path: Path, change: str) -> None:
    relative, _ = registered_fixture(tmp_path)
    cfg, parent, _, hashes = inspect_registration(tmp_path, relative)
    if change == "sidecar":
        (tmp_path / "fixtures/T01_seed13.json.sha256").unlink()
    elif change == "checkpoint":
        (tmp_path / "fixtures/T01_seed13.json").write_text("{}", encoding="utf-8")
    elif change == "mapping":
        parent["kge"]["dimension"] = 3
    else:
        cfg["input_plan"]["sha256"] = "0" * 64
    with pytest.raises((ValueError, FileNotFoundError)):
        load_stage_inputs(tmp_path, cfg, parent, hashes)


def test_degenerate_target_denominator_is_unavailable_not_epsilon_rescued() -> None:
    cps, alignments, plan, _ = inputs()
    source, target = cps["T01", 13][0], cps["T02", 13][0]
    record = copy.deepcopy(alignments["T01", "T02", 13, 13][0])
    for e in plan["split"]["fit_anchors"]:
        target.entity_embeddings[e] = [3.0, 4.0]
    target.artifact_hash = target.compute_artifact_hash()
    record["target_mean"] = [3.0, 4.0]
    diagnostic = geometry_diagnostics_v2(source, target, record, plan, settings())
    assert diagnostic["relative_fit_residual"] is None
    assert "DEGENERATE_TARGET_FIT_NORM" in diagnostic["unavailable_reasons"]
    assert diagnostic["available"] is False


def test_physical_alignment_hash_is_distinct_from_canonical_content_hash() -> None:
    cps, alignments, plan, buckets = inputs()
    for key, (record, _, semantic) in list(alignments.items()):
        serialized_bytes = (json.dumps(record) + "\r\n").encode()
        physical = hashlib.sha256(serialized_bytes).hexdigest()
        assert physical != semantic
        alignments[key] = record, physical, semantic
    artifact = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, settings())
    assert artifact["alignment_hashes"] != artifact["alignment_content_hashes"]
    verify_stage_v2(artifact, cps, alignments, plan, buckets, settings())


def test_invalid_temporal_alignment_does_not_invalidate_saved_null_or_force_sed() -> None:
    cps, alignments, plan, buckets = inputs()
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, settings())
    key = ("T01", "T02", 13, 13)
    record = copy.deepcopy(alignments[key][0])
    record.update(available=False, unavailable_reason="fixture_saved_alignment_invalid")
    alignments[key] = record, digest(record), digest(record)
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, settings(), null)
    assert drift["alignment_available"] is False and drift["temporal_observations"] == []
    assert all(r["unavailable_reason"] == "TEMPORAL_ALIGNMENT_UNAVAILABLE" and r["SED_plus"] is None
               for r in drift["entity_results"])
    verify_stage_v2(drift, cps, alignments, plan, buckets, settings(), null)


def test_stage_json_contract_matches_required_fields_and_versions() -> None:
    schema = yaml.safe_load((ROOT / "configs/schemas/m2_measurement_v2.schema.yaml").read_bytes())
    cps, alignments, plan, buckets = inputs()
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, settings())
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, settings(), null)
    for name, artifact in (("null", null), ("drift", drift)):
        assert set(artifact) == set(schema["common_required"]) | set(schema["stages"][name]["additional_required"])
        assert artifact["component_version"] == schema["stages"][name]["component_version"]
    assert set(settings()) == set(schema["settings_required"])
    assert all(r["drift_component_version"] == schema["stages"]["drift"]["row_version"] for r in drift["entity_results"])


def test_nonoptimal_orthogonal_q_is_rejected_even_if_orthogonality_passes() -> None:
    cps, alignments, plan, buckets = inputs()
    key = ("T01", "T01", 13, 37)
    record = copy.deepcopy(alignments[key][0])
    record["Q"] = [[-x for x in row] for row in record["Q"]]
    alignments[key] = record, digest(record), digest(record)
    with pytest.raises(ValueError, match="Procrustes"):
        build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, settings())


def test_null_alignment_failure_preserves_valid_raw_temporal_displacement() -> None:
    cps, alignments, plan, buckets = inputs()
    key = ("T01", "T01", 13, 37)
    record = copy.deepcopy(alignments[key][0])
    record.update(available=False, unavailable_reason="fixture_null_unavailable")
    alignments[key] = record, digest(record), digest(record)
    null = build_null_stage_v2("T01->T02", cps, alignments, plan, buckets, settings())
    drift = build_drift_stage_v2("T01->T02", cps, alignments, plan, buckets, settings(), null)
    assert len(drift["temporal_observations"]) == 21
    assert all(r["delta_time"] is not None and r["SED_plus"] is None
               and r["unavailable_reason"] == "NULL_ALIGNMENT_UNAVAILABLE" for r in drift["entity_results"])
    verify_stage_v2(drift, cps, alignments, plan, buckets, settings(), null)
