from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from kg_pipeline import adjudicate
from kg_pipeline.adjudicate import run_adjudication
from kg_pipeline.contracts import make_row
from kg_pipeline.hashing import stable_id
from kg_pipeline.storage import write_parquet_immutable
from temporal.schema import ContractError

RUN_ID = "adjudication_test_run"


@pytest.fixture(autouse=True)
def isolated_provenance_logic(monkeypatch: pytest.MonkeyPatch):
    """These unit cases exercise provenance rules; artifact-chain cases live separately."""
    monkeypatch.setattr(
        adjudicate, "resolve_run_table_path",
        lambda repo_root, run_id, name: repo_root / "runs" / run_id / "tables" / f"{name}.parquet",
    )
    monkeypatch.setattr(adjudicate, "create_stage_manifest", lambda *args, **kwargs: {})
    from kg_pipeline import gates
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: {"gate": "A"})
    from kg_pipeline import contract_authority
    monkeypatch.setattr(contract_authority, "require_schema_compatible", lambda *args, **kwargs: {})


def _setup_run(tmp_path: Path, *, with_provenance: bool = True) -> Path:
    run_dir = tmp_path / "runs" / RUN_ID
    tables = run_dir / "tables"
    tables.mkdir(parents=True)
    write_parquet_immutable(
        tables / "extracted_claims.parquet",
        "extracted_claims",
        [make_row(
            "extracted_claims",
            claim_id="claim_test",
            body_variant_id="bv_test",
            source_id="bv_test",
            subject_mention="Alpha",
            relation_name="is_CEO_of",
            object_mention="Beta",
            evidence_span_start=0,
            evidence_span_end=10,
            evidence_text_hash="evidence-hash",
            valid_from_extracted=None,
            valid_to_extracted=None,
            is_negative=False,
            is_speculative=False,
        )],
    )
    if not with_provenance:
        return run_dir

    digest = "c" * 64
    write_parquet_immutable(
        tables / "document_memberships.parquet",
        "document_memberships",
        [make_row(
            "document_memberships",
            membership_id="mem_test",
            raw_blob_sha256=digest,
            raw_candidate_id="raw_test",
            body_variant_id="bv_test",
            exact_cluster_id="cluster_test",
            retrieval_ids_json=json.dumps(["ret_test"]),
            source_provenance_status="STRICT",
            strict_input_eligible=True,
            membership_status="INCLUDED",
            reason=None,
        )],
    )
    write_parquet_immutable(
        tables / "retrievals.parquet",
        "retrievals",
        [make_row(
            "retrievals",
            retrieval_id="ret_test",
            raw_blob_sha256=digest,
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
        )],
    )
    write_parquet_immutable(
        tables / "source_versions.parquet",
        "source_versions",
        [make_row(
            "source_versions",
            source_version_id="sv_test",
            raw_blob_sha256=digest,
            retrieval_id="ret_test",
            source_id="publisher_test",
            canonical_or_final_url="https://example.test/article",
            retrieved_at_real="2025-01-01T00:00:00Z",
            archive_datetime=None,
            source_version_status="STRICT",
            strict_source_input_eligible=True,
            evidence_path=None,
            evidence_locator=None,
        )],
    )
    write_parquet_immutable(
        tables / "claim_provenance.parquet",
        "claim_provenance",
        [make_row(
            "claim_provenance",
            provenance_id=stable_id("claimprovenance", {
                "claim_id": "claim_test",
                "membership_id": "mem_test",
                "source_version_id": "sv_test",
                "retrieval_id": "ret_test",
                "raw_blob_sha256": digest,
            }),
            claim_id="claim_test",
            membership_id="mem_test",
            source_version_id="sv_test",
            retrieval_id="ret_test",
            raw_blob_sha256=digest,
            publisher_source_id="publisher_test",
            source_url="https://example.test/article",
        )],
    )
    return run_dir


def test_adjudication_requires_canonical_claim_provenance(tmp_path: Path):
    run_dir = _setup_run(tmp_path, with_provenance=False)

    with pytest.raises(FileNotFoundError, match="claim_provenance"):
        run_adjudication(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "fact_versions.parquet").exists()


def test_adjudication_blocks_unapproved_retrieval_to_evidence_time_substitution(tmp_path: Path):
    run_dir = _setup_run(tmp_path)

    with pytest.raises(ContractError, match="approved evidence_observed_at"):
        run_adjudication(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "fact_versions.parquet").exists()


def test_adjudication_rejects_orphaned_claim_provenance_before_time_gate(tmp_path: Path):
    run_dir = _setup_run(tmp_path)
    path = run_dir / "tables" / "claim_provenance.parquet"
    path.unlink()
    path.with_suffix(path.suffix + ".manifest.json").unlink()
    write_parquet_immutable(
        path,
        "claim_provenance",
        [make_row(
            "claim_provenance",
            provenance_id="prov_orphan",
            claim_id="claim_orphan",
            membership_id="mem_test",
            source_version_id="sv_test",
            retrieval_id="ret_test",
            raw_blob_sha256="c" * 64,
            publisher_source_id="publisher_test",
            source_url="https://example.test/article",
        )],
    )

    with pytest.raises(ContractError, match="does not match extracted claim IDs"):
        run_adjudication(tmp_path, RUN_ID)

    assert not (run_dir / "tables" / "fact_versions.parquet").exists()


def test_adjudication_runner_does_not_use_mapping_available_after_evidence_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    run_dir = _setup_run(tmp_path)
    published_stage: dict[str, object] = {}
    monkeypatch.setattr(
        adjudicate,
        "create_stage_manifest",
        lambda _root, _run_id, _stage, **kwargs: published_stage.update(kwargs),
    )
    mapping_path = run_dir / "tables" / "entity_mapping_versions.parquet"
    write_parquet_immutable(
        mapping_path,
        "entity_mapping_versions",
        [
            make_row(
                "entity_mapping_versions",
                entity_mapping_id="alpha-late",
                mention="Alpha",
                canonical_entity_id="canonical_alpha_current",
                mapping_available_at="2026-01-01T00:00:00Z",
                entity_map_version="mapping-v2",
                supersedes_mapping_id=None,
                mapping_basis="fixture",
                mapping_confidence=1.0,
            ),
            make_row(
                "entity_mapping_versions",
                entity_mapping_id="beta-known",
                mention="Beta",
                canonical_entity_id="canonical_beta",
                mapping_available_at="2024-01-01T00:00:00Z",
                entity_map_version="mapping-v1",
                supersedes_mapping_id=None,
                mapping_basis="fixture",
                mapping_confidence=1.0,
            ),
        ],
    )
    monkeypatch.setattr(
        adjudicate,
        "_approved_temporal_inputs",
        lambda _run_dir, claims: (
            {claim.claim_id: datetime(2025, 1, 1, tzinfo=timezone.utc) for claim in claims},
            datetime(2025, 1, 2, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr(adjudicate, "load_run_manifest", lambda *args, **kwargs: {"parent_run_id": None})

    result = run_adjudication(tmp_path, RUN_ID)

    assert result["adjudicated_facts_count"] == 0
    assert result["source_claims_count"] == 1
    assert result["review_queue_count"] == 1
    facts = pq.read_table(run_dir / "tables" / "fact_versions.parquet").to_pylist()
    assert facts == []
    source_claim_manifest = json.loads(
        (run_dir / "reports" / "source_claims.json").read_text(encoding="utf-8")
    )
    assert source_claim_manifest["manifest_version"] == "source-claims-v1"
    assert source_claim_manifest["run_id"] == RUN_ID
    assert len(source_claim_manifest["source_claims"]) == 1
    source_claim = source_claim_manifest["source_claims"][0]
    assert source_claim["claim_id"] == "claim_test"
    assert source_claim["source_version_id"] == "sv_test"
    assert source_claim["retrieval_id"] == "ret_test"
    assert source_claim["raw_blob_sha256"] == "c" * 64
    assert source_claim["source_claim_id"].startswith("sourceclaim_")
    assert published_stage["output_manifests"] == [{
        "path": str(run_dir / "reports" / "source_claims.json"),
        "contract_version": "source-claims-v1",
    }]
    review = json.loads((run_dir / "reports" / "adjudication_review_queue.json").read_text(encoding="utf-8"))
    assert review["review_records"] == [{"claim_id": "claim_test", "reason": "UNRESOLVED_ENTITY"}]
