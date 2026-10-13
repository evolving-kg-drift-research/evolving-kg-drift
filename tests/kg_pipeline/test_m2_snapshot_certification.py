from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from kg_pipeline.contracts import make_row
from kg_pipeline.hashing import sha256_json
from kg_pipeline.storage import ArtifactConflict, write_parquet_immutable, write_yaml_immutable
from kge.adapter import load_snapshot_from_parquet, load_snapshots_from_run
from kge.contract import SnapshotDataset, Triple
from temporal.schema import FactVersion
from temporal.snapshot import (
    SnapshotEdge,
    SnapshotEdgeSupport,
    SnapshotExclusion,
    compute_entity_mapping_hash,
    create_snapshot_manifest,
)


def _dt(day: int) -> datetime:
    return datetime(2025, 1, day, tzinfo=timezone.utc)


@pytest.mark.parametrize("corrupt_provenance", [False, True])
def test_m2_checks_snapshot_support_and_exclusion_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt_provenance: bool
):
    run_id = "m2_certified_fixture"
    run_dir = tmp_path / "runs" / run_id
    snapshot_dir = run_dir / "snapshots" / "S1"
    snapshot_dir.mkdir(parents=True)
    (run_dir / "inputs").mkdir()

    boundary_config = {
        "policy_version": "fixture-boundary-v1",
        "snapshots": [{"id": "S1", "cutoff": _dt(10).isoformat()}],
    }
    bundle = {"resolved_config": {"snapshot_boundaries": boundary_config}}
    import yaml

    (run_dir / "inputs" / "proposed_config_bundle.yaml").write_text(
        yaml.safe_dump(bundle), encoding="utf-8"
    )
    run_manifest = {
        "run_id": run_id,
        "scientific_locked": True,
        "config_approval": {"status": "FROZEN"},
        "config_bundle_semantic_sha256": sha256_json(bundle),
        "config_candidates": [],
        "machine_schema": {},
        "code_fingerprint_sha256": "f" * 64,
        "semantic_sha256": "d" * 64,
    }

    fact = FactVersion(
        fact_version_id="fv_1",
        logical_fact_id="lf_1",
        subject_id="entity_a",
        relation_id="REL",
        object_id="entity_b",
        valid_from=_dt(1),
        valid_to=None,
        evidence_observed_at=_dt(2),
        ingested_at_real=_dt(3),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="publisher_1",
        source_url="https://publisher.test/item",
        evidence_span_start=4,
        evidence_span_end=12,
        evidence_text_hash="a" * 64,
        extractor_version="extractor-v1",
        entity_map_version="mapping-v1",
        confidence=0.9,
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_1",),
    )
    fact_row = make_row(
        "fact_versions",
        fact_version_id="fv_1",
        supporting_claim_ids=["claim_1"],
        logical_fact_id="lf_1",
        subject_id="entity_a",
        relation_id="REL",
        object_id="entity_b",
        valid_from=_dt(1).isoformat(),
        valid_to=None,
        evidence_observed_at=_dt(2).isoformat(),
        ingested_at_real=_dt(3).isoformat(),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="publisher_1",
        source_url="https://publisher.test/item",
        evidence_span_start=4,
        evidence_span_end=12,
        evidence_text_hash="a" * 64,
        extractor_version="extractor-v1",
        entity_map_version="mapping-v1",
        confidence=0.9,
        adjudication_status="AUTO_ACCEPTED",
    )
    excluded_fact = replace(fact, fact_version_id="fv_excluded", supporting_claim_ids=())
    excluded_fact_row = {**fact_row, "fact_version_id": "fv_excluded", "supporting_claim_ids": []}
    provenance_claim_id = "different_claim" if corrupt_provenance else "claim_1"
    provenance_row = make_row(
        "claim_provenance",
        provenance_id="prov_1",
        claim_id=provenance_claim_id,
        membership_id="membership_1",
        source_version_id="source_version_1",
        retrieval_id="retrieval_1",
        raw_blob_sha256="b" * 64,
        publisher_source_id="publisher_1",
        source_url="https://publisher.test/item",
    )
    mapping_path = run_dir / "tables" / "entity_mapping_versions.parquet"
    fact_path = run_dir / "tables" / "fact_versions.parquet"
    provenance_path = run_dir / "tables" / "claim_provenance.parquet"
    write_parquet_immutable(fact_path, "fact_versions", [fact_row, excluded_fact_row])
    write_parquet_immutable(provenance_path, "claim_provenance", [provenance_row])
    write_parquet_immutable(mapping_path, "entity_mapping_versions", [])

    edge = SnapshotEdge("edge_1", "entity_a", "REL", "entity_b", "S1")
    support = SnapshotEdgeSupport(
        "support_1", "prov_1", "edge_1", "fv_1", "claim_1", "source_version_1", "b" * 64
    )
    exclusion = SnapshotExclusion(
        "ex_future", "fv_excluded", "fv_excluded", "FUTURE_EVIDENCE_OBSERVED_AT",
        "INFO", "snapshot_builder", "evidence_observed_at", "Evidence is after cutoff",
    )
    edge_path = snapshot_dir / "snapshot_edges.parquet"
    support_path = snapshot_dir / "snapshot_edge_support.parquet"
    exclusion_path = snapshot_dir / "snapshot_exclusions.parquet"
    write_parquet_immutable(edge_path, "snapshot_edges", [make_row(
        "snapshot_edges", edge_id="edge_1", subject_id="entity_a", relation_id="REL",
        object_id="entity_b", snapshot_id="S1",
    )])
    write_parquet_immutable(support_path, "snapshot_edge_support", [make_row(
        "snapshot_edge_support", support_id="support_1", provenance_id="prov_1",
        edge_id="edge_1", fact_version_id="fv_1", claim_id="claim_1",
        source_version_id="source_version_1", raw_blob_sha256="b" * 64,
    )])
    write_parquet_immutable(exclusion_path, "snapshot_exclusions", [make_row(
        "snapshot_exclusions", exclusion_id="ex_future", record_id="fv_excluded",
        fact_version_id="fv_excluded", reason_code="FUTURE_EVIDENCE_OBSERVED_AT",
        severity="INFO", stage="snapshot_builder", field="evidence_observed_at",
        detail="Evidence is after cutoff",
    )])

    resolved_config_hash = sha256_json({
        "resolved_config_bundle_semantic_sha256": run_manifest["config_bundle_semantic_sha256"],
        "config_candidates": run_manifest["config_candidates"],
        "config_approval": run_manifest["config_approval"],
        "machine_schema": run_manifest["machine_schema"],
    })
    boundary_hash = sha256_json({
        "snapshot_id": "S1", "cutoff": _dt(10).isoformat(), "boundary_policy": boundary_config,
    })
    manifest = create_snapshot_manifest(
        snapshot_id="S1",
        cutoff=_dt(10),
        edges=[edge],
        support_records=[support],
        exclusions=[exclusion],
        fact_versions=[fact, excluded_fact],
        entity_mapping_hash=compute_entity_mapping_hash([]),
        resolved_config_hash=resolved_config_hash,
        boundary_hash=boundary_hash,
        code_fingerprint=run_manifest["code_fingerprint_sha256"],
        accepted_at_by_fact_id={"fv_1": _dt(4), "fv_excluded": _dt(5)},
    )
    manifest_path = snapshot_dir / "snapshot_manifest.yaml"
    write_yaml_immutable(manifest_path, asdict(manifest))

    gate_a_ref = {"gate": "A", "run_id": run_id, "semantic_sha256": "fixture-only"}
    input_refs = [
        {"table_name": "fact_versions", "producer_run_id": run_id, "path": "tables/fact_versions.parquet"},
        {"table_name": "claim_provenance", "producer_run_id": run_id, "path": "tables/claim_provenance.parquet"},
        {"table_name": "entity_mapping_versions", "producer_run_id": run_id, "path": "tables/entity_mapping_versions.parquet"},
    ]
    stage = {"gate_a_ref": gate_a_ref, "input_artifacts": input_refs}

    from kg_pipeline import contract_authority, gates, run

    monkeypatch.setattr(run, "load_run_manifest", lambda *args, **kwargs: run_manifest)
    monkeypatch.setattr(run, "verify_stage_manifest", lambda *args, **kwargs: stage)
    monkeypatch.setattr(
        run,
        "_producer_ref_for_table",
        lambda root, path, table: {
            "producer_run_id": run_id,
            "producer_stage": "snapshot_stage",
            "table_name": table,
            "path": path.relative_to(run_dir).as_posix(),
        },
    )
    monkeypatch.setattr(
        run,
        "_producer_ref_for_manifest",
        lambda root, path: {
            "producer_run_id": run_id,
            "producer_stage": "snapshot_stage",
            "contract_version": "snapshot-manifest-v2",
            "path": path.relative_to(run_dir).as_posix(),
        },
    )
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: gate_a_ref)

    def pass_gate_report(_root, requested_run, gate):
        semantic = {
            "gate": gate,
            "scope": "scientific",
            "evaluator_version": "fixture-evaluator-v1",
            "run_id": requested_run,
            "status": "PASS",
            "checks": [{"check_id": f"{gate}-fixture", "status": "PASS"}],
            "evaluated_count": 1,
            "run_manifest_semantic_sha256": run_manifest["semantic_sha256"],
        }
        report = {
            **semantic,
            "evaluated_at_real": _dt(10).isoformat(),
            "semantic_sha256": sha256_json(semantic),
        }
        report_path = run_dir / "gates" / gate / "fixture.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(gates, "evaluate_scientific_gate", pass_gate_report)
    monkeypatch.setattr(contract_authority, "require_schema_compatible", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "kg_pipeline.canonical_validation._load_snapshot_from_parquet",
        lambda *args, **kwargs: SnapshotDataset.create("S1", [Triple("entity_a", "REL", "entity_b")]),
    )

    if corrupt_provenance:
        with pytest.raises(ArtifactConflict, match="does not resolve to claim provenance"):
            load_snapshots_from_run(tmp_path, run_id, ["S1"])
    else:
        from kg_pipeline.canonical_validation import validate_canonical_snapshots

        # Read-back must be constructible before scientific G1 exists. The public
        # M2 interface must still refuse the very same canonical artifacts.
        with monkeypatch.context() as blocked:
            blocked.setattr(gates, "evaluate_scientific_gate", lambda *args: {"status": "BLOCKED"})
            canonical = validate_canonical_snapshots(tmp_path, run_id, ["S1"])
            assert list(canonical) == ["S1"]
            with pytest.raises(PermissionError, match="G1 and G2"):
                load_snapshots_from_run(tmp_path, run_id, ["S1"])
        snapshots = load_snapshots_from_run(tmp_path, run_id, ["S1"])
        assert list(snapshots) == ["S1"]
        assert snapshots["S1"].triples == (Triple("entity_a", "REL", "entity_b"),)
        direct = load_snapshot_from_parquet(
            edge_path, "S1", repo_root=tmp_path, run_id=run_id
        )
        assert direct.triples == snapshots["S1"].triples
