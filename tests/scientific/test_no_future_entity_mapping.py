"""Scientific conformance tests for A09:
- A09: Point-in-time versioned entity mappings (mapping_available_at <= cutoff).
       No future alias decisions or canonical mappings may leak into historical snapshots.
"""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace

import pytest

from temporal.schema import ContractError, FactVersion, EntityMappingVersion
from temporal.snapshot import (
    build_snapshot_edges_and_support,
    resolve_entity_mapping_at_cutoff,
)


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_no_future_entity_mapping_leakage():
    """A09: A correction to entity mapping available in 2026 must NOT affect 2025 snapshot."""
    # Mapping M1 available in 2024
    m1 = EntityMappingVersion(
        entity_mapping_id="map_m1",
        mention="OpenAI",
        canonical_entity_id="org_openai_legacy",
        mapping_available_at=dt(2024, 1, 1),
        entity_map_version="v1.0"
    )

    # Corrected mapping M2 available in 2026
    m2 = EntityMappingVersion(
        entity_mapping_id="map_m2",
        mention="OpenAI",
        canonical_entity_id="org_openai_canonical",
        mapping_available_at=dt(2026, 1, 1),
        entity_map_version="v2.0",
        supersedes_mapping_id="map_m1"
    )

    all_mappings = [m1, m2]

    # Fact observed in 2024
    fact = FactVersion(
        fact_version_id="fv_openai_01",
        logical_fact_id="lf_openai",
        subject_id="OpenAI",  # Raw mention
        relation_id="released_by",
        object_id="ChatGPT",
        valid_from=dt(2022, 11, 30),
        valid_to=None,
        evidence_observed_at=dt(2024, 1, 1),
        ingested_at_real=dt(2024, 1, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="tuoitre",
        source_url="https://tuoitre.vn/chatgpt",
        evidence_span_start=0,
        evidence_span_end=15,
        evidence_text_hash="hash_openai",
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_openai",)
    )

    # Snapshot 2025: Cutoff is before M2 becomes available. Must strictly resolve to M1!
    cutoff_2025 = dt(2025, 1, 1)
    edges_2025, _, _ = build_snapshot_edges_and_support(
        fact_versions=[fact],
        cutoff=cutoff_2025,
        entity_mappings=all_mappings,
        snapshot_id="S_2025",
        provenance_map={"fv_openai_01": [{
            "provenance_id": "prov_openai", "claim_id": "claim_openai",
            "membership_id": "mem_openai", "source_version_id": "sv_openai",
            "retrieval_id": "ret_openai", "raw_blob_sha256": "5" * 64,
        }]},
    )
    assert len(edges_2025) == 1
    assert edges_2025[0].subject_id == "org_openai_legacy", (
        f"Future mapping leak! At cutoff 2025, expected 'org_openai_legacy', got '{edges_2025[0].subject_id}'"
    )

    # Snapshot 2026: Cutoff is after M2 becomes available. May resolve to M2!
    cutoff_2026 = dt(2026, 6, 1)
    edges_2026, _, _ = build_snapshot_edges_and_support(
        fact_versions=[fact],
        cutoff=cutoff_2026,
        entity_mappings=all_mappings,
        snapshot_id="S_2026",
        provenance_map={"fv_openai_01": [{
            "provenance_id": "prov_openai", "claim_id": "claim_openai",
            "membership_id": "mem_openai", "source_version_id": "sv_openai",
            "retrieval_id": "ret_openai", "raw_blob_sha256": "5" * 64,
        }]},
    )
    assert len(edges_2026) == 1
    assert edges_2026[0].subject_id == "org_openai_canonical"


def test_late_alias_decision_is_unavailable_before_its_recorded_time():
    late = EntityMappingVersion(
        entity_mapping_id="map_late_alias",
        mention="Open AI",
        canonical_entity_id="org_openai",
        mapping_available_at=dt(2026, 1, 1),
    )

    assert resolve_entity_mapping_at_cutoff("Open AI", [late], dt(2025, 12, 31)) is None
    assert resolve_entity_mapping_at_cutoff("Open AI", [late], dt(2026, 1, 1)) == late


def test_competing_active_mapping_decisions_block_instead_of_using_version_sort():
    mappings = [
        EntityMappingVersion(
            entity_mapping_id="map_a",
            mention="Open AI",
            canonical_entity_id="org_openai_a",
            mapping_available_at=dt(2025, 1, 1),
            entity_map_version="v2",
        ),
        EntityMappingVersion(
            entity_mapping_id="map_b",
            mention="Open AI",
            canonical_entity_id="org_openai_b",
            mapping_available_at=dt(2025, 1, 1),
            entity_map_version="v1",
        ),
    ]

    with pytest.raises(ContractError, match="Ambiguous as-of entity mapping"):
        resolve_entity_mapping_at_cutoff("Open AI", mappings, dt(2025, 1, 2))


def test_mapping_supersession_must_reference_same_mention_and_real_parent():
    later = EntityMappingVersion(
        entity_mapping_id="map_later",
        mention="Open AI",
        canonical_entity_id="org_openai",
        mapping_available_at=dt(2026, 1, 1),
        supersedes_mapping_id="missing_parent",
    )

    with pytest.raises(ContractError, match="supersedes missing mapping"):
        resolve_entity_mapping_at_cutoff("Open AI", [later], dt(2025, 1, 1))


def test_future_kg_acceptance_is_excluded_and_missing_acceptance_can_be_required():
    fact = FactVersion(
        fact_version_id="accepted-late", logical_fact_id="logical-1",
        subject_id="OpenAI", relation_id="released_by", object_id="ChatGPT",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2024, 1, 1), ingested_at_real=dt(2024, 1, 2),
        supersedes_version_id=None, revision_type="creation", source_id="tuoitre",
        source_url="https://example.test/a", evidence_span_start=0, evidence_span_end=10,
        evidence_text_hash="a" * 64, supporting_claim_ids=("claim-1",),
    )
    edges, _, exclusions = build_snapshot_edges_and_support(
        [fact], cutoff=dt(2025, 1, 1), accepted_at_by_fact_id={"accepted-late": dt(2025, 2, 1)},
        require_accepted_clock=True,
    )
    assert edges == []
    assert any(item.reason_code == "FUTURE_KG_ACCEPTANCE" for item in exclusions)
    with pytest.raises(ContractError, match="Missing accepted_into_kg_at"):
        build_snapshot_edges_and_support(
            [fact], cutoff=dt(2025, 1, 1), accepted_at_by_fact_id={}, require_accepted_clock=True,
        )


def test_revision_cannot_reference_parent_that_is_not_known_by_cutoff():
    future_parent = FactVersion(
        fact_version_id="future-parent", logical_fact_id="same-logical-fact",
        subject_id="Company A", relation_id="employs", object_id="Person A",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2030, 1, 1), ingested_at_real=dt(2030, 1, 2),
        supersedes_version_id=None, revision_type="creation", source_id="source-a",
        source_url="https://example.test/a", evidence_span_start=0, evidence_span_end=5,
        evidence_text_hash="a" * 64, supporting_claim_ids=("claim-parent",),
    )
    revision = replace(
        future_parent,
        fact_version_id="revision-known-too-early",
        evidence_observed_at=dt(2024, 1, 1),
        ingested_at_real=dt(2024, 1, 2),
        supersedes_version_id="future-parent",
        revision_type="correction",
        supporting_claim_ids=("claim-revision",),
    )

    with pytest.raises(ContractError, match="missing or not known/accepted"):
        build_snapshot_edges_and_support(
            [future_parent, revision], cutoff=dt(2025, 1, 1)
        )


def test_world_validity_filter_precedes_revision_selection():
    base = FactVersion(
        fact_version_id="base", logical_fact_id="same-logical-fact",
        subject_id="Company A", relation_id="employs", object_id="Person A",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 1, 1), ingested_at_real=dt(2020, 1, 2),
        supersedes_version_id=None, revision_type="creation", source_id="source-a",
        source_url="https://example.test/a", evidence_span_start=0, evidence_span_end=5,
        evidence_text_hash="a" * 64, supporting_claim_ids=("claim-base",),
    )
    future_effective_correction = replace(
        base,
        fact_version_id="future-correction",
        object_id="Person B",
        valid_from=dt(2030, 1, 1),
        evidence_observed_at=dt(2024, 1, 1),
        ingested_at_real=dt(2024, 1, 2),
        supersedes_version_id="base",
        revision_type="correction",
        supporting_claim_ids=("claim-correction",),
    )
    edges, _, exclusions = build_snapshot_edges_and_support(
        [base, future_effective_correction], cutoff=dt(2025, 1, 1)
    )
    assert [(edge.subject_id, edge.relation_id, edge.object_id) for edge in edges] == [
        ("Company A", "employs", "Person A")
    ]
    assert any(item.reason_code == "FUTURE_WORLD_VALIDITY" for item in exclusions)
