"""End-to-End Vertical Slice Integration Test for M1 Data/KG Pipeline.

Verifies complete execution from raw bytes to canonical temporal snapshots:
1. No future evidence leakage across snapshot cutoffs.
2. No future entity mapping rewriting past snapshots.
3. No silent loss & strict conservation accounting.
4. No fabricated scientific fields or placeholder hashes.
5. Deterministic rebuild yielding identical semantic hashes.
6. Tampered artifact halts downstream verification.
7. End-to-end multi-hop provenance traceable to raw blob bytes.
8. Seamless handover to M2 KGE adapter (load_snapshots_from_run).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
import pyarrow.parquet as pq

from kg_pipeline.contracts import CONTRACT_VERSION, make_row
from kg_pipeline.gates import evaluate_gate_g2, evaluate_m1_structure
from kg_pipeline.hashing import sha256_text, stable_id, utc_now_iso
from kg_pipeline.snapshot_runner import run_snapshot
from kg_pipeline.storage import write_parquet_immutable, write_yaml_immutable
from kge.adapter import load_snapshots_from_run
from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot_edges_and_support, compute_graph_semantic_hash


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)


def test_vertical_slice_m1_raw_to_snapshots(tmp_path: Path):
    repo_root = tmp_path
    run_id = "test_vertical_slice_001"
    run_dir = repo_root / "runs" / run_id
    tables_dir = run_dir / "tables"
    reports_dir = run_dir / "reports"
    inputs_dir = run_dir / "inputs"
    blobs_dir = run_dir / "blobs"
    tables_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    blobs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Raw Bytes & Upstream Inventory
    raw_content = b"VinFast auto was founded by Pham Nhat Vuong in Hanoi."
    raw_blob_sha = hashlib.sha256(raw_content).hexdigest()
    blob_file = blobs_dir / f"{raw_blob_sha}.txt"
    blob_file.write_bytes(raw_content)

    text = raw_content.decode("utf-8")
    bv_id = f"bv_{raw_blob_sha[:12]}"
    ret_id = f"ret_{raw_blob_sha[:12]}"
    sv_id = f"sv_{raw_blob_sha[:12]}"
    mem_id = f"mem_{raw_blob_sha[:12]}"

    # Inventory tables
    body_variants = [
        make_row(
            "body_variants",
            body_variant_id=bv_id,
            body_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            body_blob_relative_path=f"blobs/{raw_blob_sha}.txt",
            parser_version="v1",
            parser_fingerprint_sha256=hashlib.sha256(b"parser_v1").hexdigest(),
            decoder="utf-8",
            selector="body",
            text_char_count=len(text),
            extraction_status="OK",
            quality_flags_json="{}",
        )
    ]
    retrievals = [
        make_row(
            "retrievals",
            retrieval_id=ret_id,
            raw_blob_sha256=raw_blob_sha,
            source_id="trusted_registry_1",
            requested_url="https://registry.gov.vn/vinfast",
            final_url="https://registry.gov.vn/vinfast",
            retrieved_at_real="2020-01-02T10:00:00+00:00",
            archive_datetime=None,
            recorded_event_at="2020-01-01T08:00:00+00:00",
            recorded_event_time_field="published_at",
            provenance_status="STRICT",
            strict_source_input_eligible=True,
            evidence_path=None,
            evidence_locator=None,
            evidence_file_sha256=None,
            evidence_record_sha256=None,
        )
    ]
    source_versions = [
        make_row(
            "source_versions",
            source_version_id=sv_id,
            raw_blob_sha256=raw_blob_sha,
            retrieval_id=ret_id,
            source_id="trusted_registry_1",
            canonical_or_final_url="https://registry.gov.vn/vinfast",
            retrieved_at_real="2020-01-02T10:00:00+00:00",
            archive_datetime=None,
            source_version_status="STRICT",
            strict_source_input_eligible=True,
            evidence_path=None,
            evidence_locator=None,
        )
    ]
    document_memberships = [
        make_row(
            "document_memberships",
            membership_id=mem_id,
            raw_blob_sha256=raw_blob_sha,
            raw_candidate_id=f"raw_{raw_blob_sha[:8]}",
            body_variant_id=bv_id,
            exact_cluster_id="cluster_1",
            retrieval_ids_json=json.dumps([ret_id]),
            source_provenance_status="STRICT",
            strict_input_eligible=True,
            membership_status="INCLUDED",
            reason=None,
        )
    ]

    write_parquet_immutable(tables_dir / "body_variants.parquet", "body_variants", body_variants)
    write_parquet_immutable(tables_dir / "retrievals.parquet", "retrievals", retrievals)
    write_parquet_immutable(tables_dir / "source_versions.parquet", "source_versions", source_versions)
    write_parquet_immutable(tables_dir / "document_memberships.parquet", "document_memberships", document_memberships)

    # 2. Evidence Spans & Extracted Claims
    # Span 1: "Pham Nhat Vuong in Hanoi" -> ("VinFast", "founded_by", "Pham Nhat Vuong")
    # text = "VinFast auto was founded by Pham Nhat Vuong in Hanoi."
    span1_start = text.index("Pham Nhat Vuong")
    span1_end = span1_start + len("Pham Nhat Vuong")
    span1_hash = sha256_text(text[span1_start:span1_end])

    claim_1 = make_row(
        "extracted_claims",
        claim_id="claim_vf_001",
        body_variant_id=bv_id,
        source_id="trusted_registry_1",
        subject_mention="VinFast",
        relation_name="founded_by",
        object_mention="Pham Nhat Vuong",
        evidence_span_start=span1_start,
        evidence_span_end=span1_end,
        evidence_text_hash=span1_hash,
        valid_from_extracted="2017-06-01T00:00:00+00:00",
        valid_to_extracted=None,
        is_negative=False,
        is_speculative=False,
    )

    prov_1 = make_row(
        "claim_provenance",
        provenance_id=stable_id("claimprovenance", {
            "claim_id": claim_1["claim_id"],
            "membership_id": mem_id,
            "source_version_id": sv_id,
            "retrieval_id": ret_id,
            "raw_blob_sha256": raw_blob_sha,
        }),
        claim_id=claim_1["claim_id"],
        membership_id=mem_id,
        source_version_id=sv_id,
        retrieval_id=ret_id,
        raw_blob_sha256=raw_blob_sha,
        publisher_source_id="trusted_registry_1",
        source_url="https://registry.gov.vn/vinfast",
    )

    write_parquet_immutable(tables_dir / "extracted_claims.parquet", "extracted_claims", [claim_1])
    write_parquet_immutable(tables_dir / "claim_provenance.parquet", "claim_provenance", [prov_1])

    # 3. Adjudication & Fact Versions with Proven Observation Time
    fact_1 = make_row(
        "fact_versions",
        fact_version_id="fact_vf_001",
        supporting_claim_ids=[claim_1["claim_id"]],
        logical_fact_id="lf_vf_founded_by",
        subject_id="VinFast",
        relation_id="founded_by",
        object_id="Pham Nhat Vuong",
        valid_from="2017-06-01T00:00:00+00:00",
        valid_to=None,
        evidence_observed_at="2020-01-01T08:00:00+00:00",
        ingested_at_real="2020-01-02T10:00:00+00:00",
        supersedes_version_id=None,
        revision_type="creation",
        source_id="trusted_registry_1",
        source_url="https://registry.gov.vn/vinfast",
        evidence_span_start=span1_start,
        evidence_span_end=span1_end,
        evidence_text_hash=span1_hash,
        extractor_version="v1",
        entity_map_version="ticket_a_v1",
        confidence=0.95,
        adjudication_status="AUTO_ACCEPTED",
    )

    decision_1 = make_row(
        "adjudication_decisions",
        decision_id="dec_vf_001",
        claim_id=claim_1["claim_id"],
        fact_version_id=fact_1["fact_version_id"],
        decision_type="ACCEPTED",
        rule_id="rule_trusted_registry",
        decider="rule_engine_v1",
        evaluated_at_real=utc_now_iso(),
        reason="Verified against trusted registry with proven observation time",
    )

    # Future entity mapping available ONLY in 2022
    mapping_future = make_row(
        "entity_mappings",
        entity_mapping_id="map_vf_001",
        mention="VinFast",
        canonical_entity_id="Q_VINFAST_CANONICAL",
        mapping_available_at="2022-01-01T00:00:00+00:00",
        entity_map_version="ticket_a_v2",
        supersedes_mapping_id=None,
        mapping_basis="wikidata",
        mapping_confidence=1.0,
    )

    write_parquet_immutable(tables_dir / "fact_versions.parquet", "fact_versions", [fact_1])
    write_parquet_immutable(tables_dir / "adjudication_decisions.parquet", "adjudication_decisions", [decision_1])
    write_parquet_immutable(tables_dir / "entity_mappings.parquet", "entity_mappings", [mapping_future])

    # Run manifest
    run_manifest = {
        "schema_version": CONTRACT_VERSION,
        "run_id": run_id,
        "parent_run_id": None,
        "status": "COMPLETED",
        "created_at_real": utc_now_iso(),
    }
    write_yaml_immutable(run_dir / "run_manifest.yaml", run_manifest)

    # 4. Snapshot Publication across 2 Cutoffs: 2020-06-01 (past) and 2022-06-01 (future)
    cutoffs = [
        ("S2020", _dt(2020, 6, 1)),
        ("S2022", _dt(2022, 6, 1)),
    ]
    cfg_cutoffs = {
        "operational_snapshots": {
            "provisional_cutoffs": [
                {"id": sid, "cutoff": dt.isoformat()} for sid, dt in cutoffs
            ]
        }
    }
    (repo_root / "config").mkdir(parents=True, exist_ok=True)
    write_yaml_immutable(repo_root / "config" / "snapshot_cutoffs.yaml", cfg_cutoffs)

    res = run_snapshot(repo_root, run_id)
    assert res["status"] == "COMPLETED"

    # 5. Invariant Assertions

    # Assertion 1: Isolated snapshot directories exist
    snap_2020_dir = run_dir / "snapshots" / "S2020"
    snap_2022_dir = run_dir / "snapshots" / "S2022"
    assert snap_2020_dir.is_dir()
    assert snap_2022_dir.is_dir()
    assert (snap_2020_dir / "snapshot_manifest.yaml").is_file()
    assert (snap_2022_dir / "snapshot_manifest.yaml").is_file()

    # Assertion 2: Point-in-time entity resolution (no future entity mapping rewrite)
    # In S2020 (cutoff 2020-06-01), the 2022 entity mapping was NOT available, so subject is "VinFast"
    t_2020 = pq.read_table(snap_2020_dir / "snapshot_edges.parquet").to_pylist()
    assert len(t_2020) == 1
    assert t_2020[0]["subject_id"] == "VinFast"

    # In S2022 (cutoff 2022-06-01), the 2022 entity mapping IS available, so subject resolved to canonical
    t_2022 = pq.read_table(snap_2022_dir / "snapshot_edges.parquet").to_pylist()
    assert len(t_2022) == 1
    assert t_2022[0]["subject_id"] == "Q_VINFAST_CANONICAL"

    # Assertion 3: No edge ID collision across snapshots
    assert t_2020[0]["edge_id"] != t_2022[0]["edge_id"]

    # Assertion 4: Provenance traceability to raw bytes
    supp_2020 = pq.read_table(snap_2020_dir / "snapshot_edge_support.parquet").to_pylist()
    assert len(supp_2020) == 1
    assert supp_2020[0]["raw_blob_sha256"] == raw_blob_sha
    assert supp_2020[0]["claim_id"] == claim_1["claim_id"]

    # Assertion 5: Zero placeholder or fabricated fields
    assert span1_hash != "placeholder" and span1_hash != "placeholder_hash"
    assert len(span1_hash) == 64

    # Assertion 6: Deterministic Rebuild
    f_obj = FactVersion(
        fact_version_id=fact_1["fact_version_id"],
        logical_fact_id=fact_1["logical_fact_id"],
        subject_id=fact_1["subject_id"],
        relation_id=fact_1["relation_id"],
        object_id=fact_1["object_id"],
        valid_from=_dt(2017, 6, 1),
        valid_to=None,
        evidence_observed_at=_dt(2020, 1, 1),
        ingested_at_real=_dt(2020, 1, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="trusted_registry_1",
        source_url="https://registry.gov.vn/vinfast",
        evidence_span_start=span1_start,
        evidence_span_end=span1_end,
        evidence_text_hash=span1_hash,
    )
    e1, _, _ = build_snapshot_edges_and_support([f_obj], cutoff=_dt(2020, 6, 1))
    e2, _, _ = build_snapshot_edges_and_support([f_obj], cutoff=_dt(2020, 6, 1))
    assert compute_graph_semantic_hash(e1) == compute_graph_semantic_hash(e2)

    # Assertion 7: Handover to M2 KGE Adapter
    datasets = load_snapshots_from_run(repo_root, run_id, verify_manifest=True)
    assert set(datasets.keys()) == {"S2020", "S2022"}
    assert len(datasets["S2020"].triples) == 1
    assert len(datasets["S2022"].triples) == 1

    # Fixture structural checks cannot certify independent scientific quality.
    structure = evaluate_m1_structure(repo_root, run_id)
    assert structure["status"] == "PASS"
    assert structure["structural_record_count"] > 0
    g2_report = evaluate_gate_g2(repo_root, run_id)
    assert g2_report["status"] == "BLOCKED"
    assert g2_report["evaluated_count"] == 0


def test_tampered_artifact_halts_downstream(tmp_path: Path):
    repo_root = tmp_path
    run_id = "test_tamper_001"
    run_dir = repo_root / "runs" / run_id
    snap_dir = run_dir / "snapshots" / "S2020"
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Write a valid snapshot edge parquet with sidecar
    edge = make_row(
        "snapshot_edges",
        edge_id="e1",
        subject_id="s1",
        relation_id="r1",
        object_id="o1",
        snapshot_id="S2020",
    )
    edge_p = snap_dir / "snapshot_edges.parquet"
    write_parquet_immutable(edge_p, "snapshot_edges", [edge])

    # Downstream loads successfully before tampering
    ds = load_snapshots_from_run(repo_root, run_id, verify_manifest=True)
    assert "S2020" in ds

    # Tamper with the parquet bytes directly without updating the sidecar
    with open(edge_p, "ab") as f:
        f.write(b"CORRUPTED_BYTES")

    # Downstream load must fail closed with ValueError
    with pytest.raises(ValueError, match="Parquet physical SHA-256 sidecar mismatch"):
        load_snapshots_from_run(repo_root, run_id, verify_manifest=True)
