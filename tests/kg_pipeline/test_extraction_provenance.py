from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from kg_pipeline import extract
from kg_pipeline.contracts import make_row
from kg_pipeline.storage import write_parquet_immutable
from temporal.schema import ClaimCandidate, ContractError


RUN_ID = "extract_test_run"


@pytest.fixture(autouse=True)
def isolated_provenance_logic(monkeypatch: pytest.MonkeyPatch):
    """These unit cases exercise provenance rules; artifact-chain cases live separately."""
    monkeypatch.setattr(
        extract, "resolve_run_table_path",
        lambda repo_root, run_id, name: repo_root / "runs" / run_id / "tables" / f"{name}.parquet",
    )
    monkeypatch.setattr(extract, "create_stage_manifest", lambda *args, **kwargs: {})
    from kg_pipeline import gates
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: {"gate": "A"})
    from kg_pipeline import contract_authority
    monkeypatch.setattr(contract_authority, "require_schema_compatible", lambda *args, **kwargs: {})


def _claim(body_variant_id: str = "bv_test") -> ClaimCandidate:
    return ClaimCandidate(
        claim_id="claim_test",
        body_variant_id=body_variant_id,
        subject_mention="Alpha",
        relation_name="is_CEO_of",
        object_mention="Beta",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="evidence-hash",
    )


def _setup_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, claims=None) -> Path:
    run_dir = tmp_path / "runs" / RUN_ID
    tables = run_dir / "tables"
    tables.mkdir(parents=True)
    body_path = run_dir / "body_blobs" / "body.txt"
    body_path.parent.mkdir()
    body_path.write_text("Alpha is CEO of Beta", encoding="utf-8")
    write_parquet_immutable(
        tables / "body_variants.parquet",
        "body_variants",
        [make_row(
            "body_variants",
            body_variant_id="bv_test",
            body_text_sha256="a" * 64,
            body_blob_relative_path="body_blobs/body.txt",
            parser_version="parser-v1",
            parser_fingerprint_sha256="b" * 64,
            decoder="utf-8",
            selector="article",
            text_char_count=20,
            extraction_status="OK",
            quality_flags_json="[]",
        )],
    )
    candidates = [_claim()] if claims is None else claims
    monkeypatch.setattr(extract, "extract_claims", lambda **_: (candidates, []))
    return run_dir


def _write_provenance_inputs(run_dir: Path, *, membership_rows=None, retrieval_rows=None, source_version_rows=None) -> None:
    tables = run_dir / "tables"
    if membership_rows is not None:
        write_parquet_immutable(tables / "document_memberships.parquet", "document_memberships", membership_rows)
    if retrieval_rows is not None:
        write_parquet_immutable(tables / "retrievals.parquet", "retrievals", retrieval_rows)
    if source_version_rows is not None:
        write_parquet_immutable(tables / "source_versions.parquet", "source_versions", source_version_rows)


def _valid_rows():
    membership = make_row(
        "document_memberships",
        membership_id="mem_test",
        raw_blob_sha256="c" * 64,
        raw_candidate_id="raw_test",
        body_variant_id="bv_test",
        exact_cluster_id="cluster_test",
        retrieval_ids_json=json.dumps(["ret_test"]),
        source_provenance_status="STRICT",
        strict_input_eligible=True,
        membership_status="INCLUDED",
        reason=None,
    )
    retrieval = make_row(
        "retrievals",
        retrieval_id="ret_test",
        raw_blob_sha256="c" * 64,
        source_id="publisher_test",
        requested_url="https://example.test/article",
        final_url="https://example.test/article",
        retrieved_at_real="2025-01-01T00:00:00Z",
        archive_datetime=None,
        recorded_event_at=None,
        recorded_event_time_field=None,
        provenance_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
        evidence_file_sha256=None,
        evidence_record_sha256=None,
    )
    source_version = make_row(
        "source_versions",
        source_version_id="sv_test",
        raw_blob_sha256="c" * 64,
        retrieval_id="ret_test",
        source_id="publisher_test",
        canonical_or_final_url="https://example.test/article",
        retrieved_at_real="2025-01-01T00:00:00Z",
        archive_datetime=None,
        source_version_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
    )
    return [membership], [retrieval], [source_version]


@pytest.mark.parametrize("missing_table", ["document_memberships", "retrievals", "source_versions"])
def test_extraction_requires_all_provenance_tables_before_writing_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_table: str
):
    run_dir = _setup_run(tmp_path, monkeypatch)
    memberships, retrievals, source_versions = _valid_rows()
    rows = {
        "document_memberships": memberships,
        "retrievals": retrievals,
        "source_versions": source_versions,
    }
    for name, table_rows in rows.items():
        if name != missing_table:
            _write_provenance_inputs(
                run_dir,
                **{f"{name.replace('document_memberships', 'membership').replace('source_versions', 'source_version').replace('retrievals', 'retrieval')}_rows": table_rows},
            )

    with pytest.raises(FileNotFoundError, match=missing_table):
        extract.run_extraction(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "extracted_claims.parquet").exists()
    assert not (run_dir / "tables" / "claim_provenance.parquet").exists()


def test_extraction_validates_provenance_before_writing_claims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_dir = _setup_run(tmp_path, monkeypatch)
    memberships, retrievals, source_versions = _valid_rows()
    memberships[0]["retrieval_ids_json"] = json.dumps(["missing_retrieval"])
    _write_provenance_inputs(
        run_dir,
        membership_rows=memberships,
        retrieval_rows=retrievals,
        source_version_rows=source_versions,
    )

    with pytest.raises(ContractError, match="unresolved retrieval/source-version link"):
        extract.run_extraction(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "extracted_claims.parquet").exists()
    assert not (run_dir / "tables" / "claim_provenance.parquet").exists()


def test_extraction_rejects_provenance_hash_mismatch_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_dir = _setup_run(tmp_path, monkeypatch)
    memberships, retrievals, source_versions = _valid_rows()
    retrievals[0]["raw_blob_sha256"] = "d" * 64
    _write_provenance_inputs(
        run_dir,
        membership_rows=memberships,
        retrieval_rows=retrievals,
        source_version_rows=source_versions,
    )

    with pytest.raises(ContractError, match="provenance hash mismatch"):
        extract.run_extraction(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "extracted_claims.parquet").exists()
    assert not (run_dir / "tables" / "claim_provenance.parquet").exists()


def test_extraction_writes_one_provenance_row_per_source_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_dir = _setup_run(tmp_path, monkeypatch)
    memberships, retrievals, source_versions = _valid_rows()
    memberships.append(make_row(
        "document_memberships",
        membership_id="mem_test_2",
        raw_blob_sha256="d" * 64,
        raw_candidate_id="raw_test_2",
        body_variant_id="bv_test",
        exact_cluster_id="cluster_test",
        retrieval_ids_json=json.dumps(["ret_test_2"]),
        source_provenance_status="STRICT",
        strict_input_eligible=True,
        membership_status="INCLUDED",
        reason=None,
    ))
    retrievals.append(make_row(
        "retrievals",
        retrieval_id="ret_test_2",
        raw_blob_sha256="d" * 64,
        source_id="publisher_test_2",
        requested_url="https://example.test/other",
        final_url="https://example.test/other",
        retrieved_at_real="2025-01-02T00:00:00Z",
        archive_datetime=None,
        recorded_event_at=None,
        recorded_event_time_field=None,
        provenance_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
        evidence_file_sha256=None,
        evidence_record_sha256=None,
    ))
    source_versions.append(make_row(
        "source_versions",
        source_version_id="sv_test_2",
        raw_blob_sha256="d" * 64,
        retrieval_id="ret_test_2",
        source_id="publisher_test_2",
        canonical_or_final_url="https://example.test/other",
        retrieved_at_real="2025-01-02T00:00:00Z",
        archive_datetime=None,
        source_version_status="STRICT",
        strict_source_input_eligible=True,
        evidence_path=None,
        evidence_locator=None,
    ))
    _write_provenance_inputs(
        run_dir,
        membership_rows=memberships,
        retrieval_rows=retrievals,
        source_version_rows=source_versions,
    )

    result = extract.run_extraction(tmp_path, RUN_ID)

    assert result["status"] == "COMPLETED"
    assert result["extracted_claims_count"] == 1
    assert result["claim_provenance_count"] == 2
    provenance = pq.read_table(run_dir / "tables" / "claim_provenance.parquet").to_pylist()
    assert {row["source_version_id"] for row in provenance} == {"sv_test", "sv_test_2"}
    assert len({row["provenance_id"] for row in provenance}) == 2
    assert pq.read_table(run_dir / "tables" / "extracted_claims.parquet").num_rows == 1


def test_zero_claims_still_write_empty_provenance_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_dir = _setup_run(tmp_path, monkeypatch, claims=[])
    memberships, retrievals, source_versions = _valid_rows()
    _write_provenance_inputs(
        run_dir,
        membership_rows=memberships,
        retrieval_rows=retrievals,
        source_version_rows=source_versions,
    )

    result = extract.run_extraction(tmp_path, RUN_ID)

    assert result["extracted_claims_count"] == 0
    assert result["claim_provenance_count"] == 0
    assert pq.read_table(run_dir / "tables" / "claim_provenance.parquet").num_rows == 0
