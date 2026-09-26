"""Scientific conformance tests for A12:
- A12: Snapshot edges must contain unique (subject, relation, object) triples.
       Multiple supporting FactVersions must be stored in snapshot_edge_support.parquet,
       preventing KGE training bias from provenance multiplicity.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot_edges_and_support, SnapshotEdge, SnapshotEdgeSupport


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_multiple_supporting_facts_produce_single_snapshot_edge():
    """A12: When 3 distinct sources support the identical triple,

    snapshot_edges must contain exactly 1 unique edge, while snapshot_edge_support contains 3 rows.
    """
    cutoff = dt(2025, 1, 1)

    # 3 distinct FactVersions from 3 sources for the identical canonical triple
    fact1 = FactVersion(
        fact_version_id="fv_source_tuoitre_01",
        logical_fact_id="lf_apple_ceo",
        subject_id="org_apple",
        relation_id="CEO",
        object_id="per_tim_cook",
        valid_from=dt(2011, 8, 24),
        valid_to=None,
        evidence_observed_at=dt(2024, 1, 1),
        ingested_at_real=dt(2024, 1, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="tuoitre",
        source_url="https://tuoitre.vn/apple_ceo",
        evidence_span_start=10,
        evidence_span_end=35,
        evidence_text_hash="hash_tt",
        adjudication_status="AUTO_ACCEPTED"
    )

    fact2 = FactVersion(
        fact_version_id="fv_source_thanhnien_01",
        logical_fact_id="lf_apple_ceo",
        subject_id="org_apple",
        relation_id="CEO",
        object_id="per_tim_cook",
        valid_from=dt(2011, 8, 24),
        valid_to=None,
        evidence_observed_at=dt(2024, 2, 1),
        ingested_at_real=dt(2024, 2, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="thanhnien",
        source_url="https://thanhnien.vn/apple_ceo",
        evidence_span_start=5,
        evidence_span_end=30,
        evidence_text_hash="hash_tn",
        adjudication_status="AUTO_ACCEPTED"
    )

    fact3 = FactVersion(
        fact_version_id="fv_source_reuters_01",
        logical_fact_id="lf_apple_ceo",
        subject_id="org_apple",
        relation_id="CEO",
        object_id="per_tim_cook",
        valid_from=dt(2011, 8, 24),
        valid_to=None,
        evidence_observed_at=dt(2024, 3, 1),
        ingested_at_real=dt(2024, 3, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="reuters",
        source_url="https://reuters.com/apple_ceo",
        evidence_span_start=20,
        evidence_span_end=45,
        evidence_text_hash="hash_reuters",
        adjudication_status="AUTO_ACCEPTED"
    )

    edges, support, exclusions = build_snapshot_edges_and_support(
        fact_versions=[fact1, fact2, fact3],
        cutoff=cutoff,
        snapshot_id="S_2025_01"
    )

    # Invariant: Snapshot edges for KGE must have exactly 1 unique triple
    assert len(edges) == 1, f"Expected 1 unique edge, got {len(edges)}"
    edge = edges[0]
    assert edge.subject_id == "org_apple"
    assert edge.relation_id == "CEO"
    assert edge.object_id == "per_tim_cook"
    assert edge.snapshot_id == "S_2025_01"

    # Invariant: All 3 supporting sources are preserved in support table
    assert len(support) == 3, f"Expected 3 support rows, got {len(support)}"
    supporting_fact_ids = {s.fact_version_id for s in support}
    assert supporting_fact_ids == {
        "fv_source_tuoitre_01",
        "fv_source_thanhnien_01",
        "fv_source_reuters_01"
    }
    # All support rows must point to the unique edge_id
    for s in support:
        assert s.edge_id == edge.edge_id

    # No exclusions
    assert len(exclusions) == 0
