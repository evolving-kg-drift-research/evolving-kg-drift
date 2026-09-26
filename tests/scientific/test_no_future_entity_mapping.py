"""Scientific conformance tests for A09:
- A09: Point-in-time versioned entity mappings (mapping_available_at <= cutoff).
       No future alias decisions or canonical mappings may leak into historical snapshots.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from temporal.schema import FactVersion, EntityMappingVersion
from temporal.snapshot import build_snapshot_edges_and_support


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
        adjudication_status="AUTO_ACCEPTED"
    )

    # Snapshot 2025: Cutoff is before M2 becomes available. Must strictly resolve to M1!
    cutoff_2025 = dt(2025, 1, 1)
    edges_2025, _, _ = build_snapshot_edges_and_support(
        fact_versions=[fact],
        cutoff=cutoff_2025,
        entity_mappings=all_mappings,
        snapshot_id="S_2025"
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
        snapshot_id="S_2026"
    )
    assert len(edges_2026) == 1
    assert edges_2026[0].subject_id == "org_openai_canonical"
