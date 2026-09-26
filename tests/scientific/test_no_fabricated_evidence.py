"""Scientific conformance tests for A13 and A14:
- A13: No fabricated evidence spans ([0, 1)) or placeholder hashes.
- A14: Excluded records must be placed in snapshot_exclusions with structured reason codes rather than silently dropped.
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from temporal.schema import FactVersion, ContractError
from temporal.snapshot import build_snapshot_edges_and_support


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_invalid_evidence_span_is_quarantined_not_fabricated():
    """A13/A14: When span is missing or invalid, do NOT fabricate [0, 1) or 'placeholder_hash'.

    Record exclusion in snapshot_exclusions with structured reason.
    """
    # Valid fact
    valid_fact = FactVersion(
        fact_version_id="f_valid_01",
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
        evidence_text_hash="valid_hash_abc",
        adjudication_status="AUTO_ACCEPTED"
    )
    assert valid_fact.evidence_span_start == 10
    assert valid_fact.evidence_span_end == 35

    # Fact with fabricated [0, 1) span and placeholder hash should be rejected or quarantined!
    with pytest.raises(ContractError, match="fabricated|placeholder"):
        FactVersion(
            fact_version_id="f_fake_01",
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
            evidence_span_start=0,
            evidence_span_end=1,
            evidence_text_hash="placeholder_hash",
            adjudication_status="AUTO_ACCEPTED"
        )


def test_snapshot_exclusions_records_quarantine_reasons():
    """A14: Facts excluded during snapshot construction (e.g. unverified, retracted, future)

    must produce explicit SnapshotExclusion records.
    """
    cutoff = dt(2025, 1, 1)

    # Fact with future observation date (observed in 2026, cutoff is 2025)
    future_fact = FactVersion(
        fact_version_id="f_future_01",
        logical_fact_id="lf_future",
        subject_id="org_apple",
        relation_id="CEO",
        object_id="per_tim_cook",
        valid_from=dt(2023, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2026, 6, 1),
        ingested_at_real=dt(2026, 6, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="tuoitre",
        source_url="https://tuoitre.vn/future",
        evidence_span_start=5,
        evidence_span_end=25,
        evidence_text_hash="hash_future",
        adjudication_status="AUTO_ACCEPTED"
    )

    edges, support, exclusions = build_snapshot_edges_and_support(
        fact_versions=[future_fact],
        cutoff=cutoff,
        snapshot_id="S_2025_01"
    )

    assert len(edges) == 0
    assert len(support) == 0
    assert len(exclusions) == 1
    ex = exclusions[0]
    assert ex.fact_version_id == "f_future_01"
    assert ex.reason_code == "FUTURE_EVIDENCE_OBSERVED_AT"
    assert ex.stage == "snapshot_builder"
