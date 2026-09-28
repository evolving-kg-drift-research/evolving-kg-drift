from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import pytest

from temporal.schema import Claim, EntityMappingVersion
from kg_pipeline import adjudicate as adjudicate_runner
from kg_pipeline.adjudication import (
    adjudicate_claims,
    build_source_claims,
    validate_append_only_fact_versions,
)

def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)

def test_adjudicate_claims():
    c1 = Claim(
        claim_id="c1", source_id="trusted_registry_1",
        subject_mention="Apple", relation_name="CEO", object_mention="Tim Cook",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash",
        valid_from_extracted="2011-08-24T00:00:00Z"
    )
    c2 = Claim(
        claim_id="c2", source_id="untrusted_blog",
        subject_mention="Apple", relation_name="CEO", object_mention="Tim Cook",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )
    c3 = Claim(
        claim_id="c3", source_id="trusted_registry_1",
        subject_mention="Unknown Corp", relation_name="CEO", object_mention="John Doe",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )
    c4 = Claim(
        claim_id="c4", source_id="trusted_registry_1",
        subject_mention="apple", relation_name="CEO", object_mention="tim cook",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )
    c5 = Claim(
        claim_id="c5", source_id="trusted_registry_1",
        subject_mention="Apple", relation_name="CEO", object_mention="Tim Cook",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash",
        is_speculative=True
    )

    observation_times = {
        "c1": dt(2021, 1, 1),
        "c2": dt(2021, 1, 2),
        "c3": dt(2021, 1, 1),
        "c4": dt(2021, 1, 1),
        "c5": dt(2021, 1, 1)
    }

    catalog = {
        "Apple": "org_apple",
        "Tim Cook": "per_tim_cook"
        # Unknown Corp is not in catalog
    }

    accepted, review = adjudicate_claims(
        claims=[c1, c2, c3, c4, c5],
        observation_times=observation_times,
        ingested_at=dt(2025, 1, 1),
        entity_catalog=catalog
    )

    # Two source claims for the same proposition are support for one FactVersion,
    # not a correction/revision.
    assert len(accepted) == 1
    assert accepted[0].subject_id == "org_apple"
    assert accepted[0].adjudication_status == "AUTO_ACCEPTED"
    assert accepted[0].valid_from == datetime(2011, 8, 24, tzinfo=timezone.utc)
    assert accepted[0].confidence == 0.9
    assert set(accepted[0].supporting_claim_ids) == {"c1", "c4"}

    # c2, c3, c5 should be in review
    assert len(review) == 3
    reasons = [r["reason"] for r in review]
    assert "NON_WHITELIST_SOURCE" in reasons # c2
    assert "UNRESOLVED_ENTITY" in reasons # c3
    assert "SPECULATIVE_OR_NEGATIVE" in reasons # c5


def test_versioned_mapping_does_not_use_current_catalog_substring_fallback():
    claim = Claim(
        claim_id="substring", source_id="trusted_registry_1",
        subject_mention="Acme", relation_name="CEO", object_mention="Jane Doe",
        evidence_span_start=0, evidence_span_end=8, evidence_text_hash="hash",
    )
    accepted, review = adjudicate_claims(
        claims=[claim],
        observation_times={"substring": dt(2025, 1, 1)},
        ingested_at=dt(2025, 1, 2),
        entity_catalog={"Acme Holdings": "org_holdings", "Jane Doe": "person_jane"},
        entity_mappings=[
            EntityMappingVersion(
                entity_mapping_id="mapping-acme-holdings", mention="Acme Holdings",
                canonical_entity_id="org_holdings", mapping_available_at=dt(2024, 1, 1),
            ),
            EntityMappingVersion(
                entity_mapping_id="mapping-jane", mention="Jane Doe",
                canonical_entity_id="person_jane", mapping_available_at=dt(2024, 1, 1),
            ),
        ],
    )
    assert accepted == []
    assert review[0]["reason"] == "UNRESOLVED_ENTITY"


def test_source_claims_preserve_each_provenance_path():
    claims = [Claim(
        claim_id="c1", source_id="body-1", subject_mention="Apple",
        relation_name="CEO", object_mention="Tim Cook", evidence_span_start=0,
        evidence_span_end=4, evidence_text_hash="hash",
    )]
    base = {
        "claim_id": "c1", "membership_id": "mem-1", "raw_blob_sha256": "a" * 64,
        "publisher_source_id": "publisher", "source_url": "https://example.test/a",
    }
    rows = [
        {**base, "provenance_id": "p1", "source_version_id": "sv1", "retrieval_id": "r1"},
        {**base, "provenance_id": "p2", "source_version_id": "sv2", "retrieval_id": "r2"},
    ]
    source_claims = build_source_claims(claims, rows)
    assert len(source_claims) == 2
    assert {item.source_version_id for item in source_claims} == {"sv1", "sv2"}


def test_append_only_validator_rejects_rewriting_a_prior_fact():
    accepted, _ = adjudicate_claims(
        claims=[Claim(
            claim_id="c1", source_id="trusted_registry_1", subject_mention="Apple",
            relation_name="CEO", object_mention="Tim Cook", evidence_span_start=0,
            evidence_span_end=4, evidence_text_hash="hash",
        )],
        observation_times={"c1": dt(2025, 1, 1)},
        ingested_at=dt(2025, 1, 2),
        entity_catalog={"Apple": "org_apple", "Tim Cook": "person_tim"},
    )
    validate_append_only_fact_versions(accepted, accepted)
    with pytest.raises(ValueError, match="changed historical record"):
        validate_append_only_fact_versions(accepted, [replace(accepted[0], source_url="changed")])


def test_previous_fact_store_load_uses_parent_run_artifact(monkeypatch):
    row = {
        "fact_version_id": "fv_prior",
        "logical_fact_id": "lf_prior",
        "subject_id": "org_apple",
        "relation_id": "CEO",
        "object_id": "person_tim",
        "valid_from": "2024-01-01T00:00:00Z",
        "valid_to": None,
        "evidence_observed_at": "2024-01-02T00:00:00Z",
        "ingested_at_real": "2024-01-03T00:00:00Z",
        "supersedes_version_id": None,
        "revision_type": "creation",
        "source_id": "trusted_registry_1",
        "source_url": "https://example.test/fact",
        "evidence_span_start": 0,
        "evidence_span_end": 5,
        "evidence_text_hash": "a" * 64,
        "extractor_version": "extractor-v1",
        "entity_map_version": "mapping-v1",
        "confidence": 0.9,
        "adjudication_status": "AUTO_ACCEPTED",
        "supporting_claim_ids": ["claim_prior"],
    }

    class FakeTable:
        def to_pylist(self):
            return [row]

    expected_path = object()
    monkeypatch.setattr(
        adjudicate_runner, "load_run_manifest", lambda *args, **kwargs: {"parent_run_id": "run_parent"}
    )
    monkeypatch.setattr(
        adjudicate_runner,
        "resolve_run_table_path",
        lambda root, run_id, table: expected_path
        if (run_id, table) == ("run_parent", "fact_versions")
        else pytest.fail("Previous FactVersion lookup must target the direct parent ancestry."),
    )
    monkeypatch.setattr(adjudicate_runner.pq, "read_table", lambda path: FakeTable())

    path, rows, facts = adjudicate_runner._load_previous_fact_store(Path("."), "run_child")

    assert path is expected_path
    assert rows == [row]
    assert len(facts) == 1
    assert facts[0].fact_version_id == "fv_prior"
    assert facts[0].evidence_observed_at == dt(2024, 1, 2)


def test_adjudication_mapping_history_blocks_alias_until_available():
    claim = Claim(
        claim_id="late-map", source_id="trusted_registry_1",
        subject_mention="Open AI", relation_name="released", object_mention="Model X",
        evidence_span_start=0, evidence_span_end=12, evidence_text_hash="hash",
    )
    maps = [
        EntityMappingVersion(
            entity_mapping_id="m1", mention="Open AI", canonical_entity_id="org_openai",
            mapping_available_at=dt(2026, 1, 1), entity_map_version="mapping-v1",
        ),
        EntityMappingVersion(
            entity_mapping_id="m2", mention="Model X", canonical_entity_id="model_x",
            mapping_available_at=dt(2024, 1, 1), entity_map_version="mapping-v1",
        ),
    ]
    accepted, review = adjudicate_claims(
        claims=[claim],
        observation_times={"late-map": dt(2025, 1, 1)},
        ingested_at=dt(2026, 2, 1),
        entity_catalog={"Open AI": "current_catalog_id", "Model X": "model_x"},
        entity_mappings=maps,
    )
    assert accepted == []
    assert review[0]["reason"] == "UNRESOLVED_ENTITY"


def test_conflicting_object_and_retraction_remain_pending_without_policy():
    claims = [
        Claim(
            claim_id="initial", source_id="trusted_registry_1", subject_mention="Apple",
            relation_name="CEO", object_mention="Person A", evidence_span_start=0,
            evidence_span_end=5, evidence_text_hash="hash-a",
        ),
        Claim(
            claim_id="conflict", source_id="trusted_registry_1", subject_mention="Apple",
            relation_name="CEO", object_mention="Person B", evidence_span_start=0,
            evidence_span_end=5, evidence_text_hash="hash-b",
        ),
        Claim(
            claim_id="retract", source_id="trusted_registry_1", subject_mention="Apple",
            relation_name="CEO", object_mention="Person A", evidence_span_start=0,
            evidence_span_end=5, evidence_text_hash="hash-c", is_negative=True,
        ),
    ]
    accepted, review = adjudicate_claims(
        claims=claims,
        observation_times={item.claim_id: dt(2025, 1, index + 1) for index, item in enumerate(claims)},
        ingested_at=dt(2025, 2, 1),
        entity_catalog={"Apple": "org_apple", "Person A": "person_a", "Person B": "person_b"},
        ontology_rules={"CEO": {"logical_key": ["subject", "relation"]}},
    )
    assert len(accepted) == 1
    assert {item["reason"] for item in review} == {"REVISION_CONFLICT_PENDING_APPROVED_POLICY"}
