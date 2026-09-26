"""Scientific conformance tests for A07 and A08:
- A07: World validity time (valid_from/valid_to) and evidence observation time (evidence_observed_at)
       must remain completely decoupled. valid_from must never fall back to evidence_observed_at,
       and unproven observation time must fail to EVIDENCE_TIME_UNAVAILABLE.
- A08: ingested_at_real must reflect actual acquisition event records rather than manifest creation time.
"""

from __future__ import annotations

from datetime import datetime, timezone

from temporal.schema import ClaimCandidate, FactVersion
from temporal.snapshot import build_snapshot
from kg_pipeline.adjudication import adjudicate_claims


def dt(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_temporal_axes_orthogonality():
    """A07: World validity (valid_from) and observation time (evidence_observed_at) must remain decoupled."""
    # Article retrieved and published in 2026
    # Article reports CEO appointment took effect in 2023
    claim = ClaimCandidate(
        claim_id="claim_2026_01",
        body_variant_id="bv_tuoitre_2026",
        subject_mention="Tech Corp",
        relation_name="CEO",
        object_mention="Alice",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_2026",
        valid_from_extracted="2023-03-15T00:00:00Z"
    )

    observation_time_2026 = dt(2026, 6, 1)
    ingestion_time_real = dt(2026, 6, 1, 10, 30)

    catalog = {"Tech Corp": "org_tech", "Alice": "per_alice"}
    body_to_sources = {
        "bv_tuoitre_2026": [{
            "publisher_source_id": "trusted_registry_1",
            "source_url": "https://trusted.test/article_2026.htm"
        }]
    }

    accepted, review = adjudicate_claims(
        claims=[claim],
        observation_times={"claim_2026_01": observation_time_2026},
        ingested_at=ingestion_time_real,
        entity_catalog=catalog,
        body_to_sources=body_to_sources
    )

    assert len(accepted) == 1
    fact = accepted[0]

    # Hard invariant: valid_from must be 2023, NOT 2026
    assert fact.valid_from == dt(2023, 3, 15)
    # Hard invariant: evidence_observed_at must be 2026, NOT 2023
    assert fact.evidence_observed_at == observation_time_2026
    assert fact.valid_from != fact.evidence_observed_at
    # Ingestion time must reflect real acquisition time
    assert fact.ingested_at_real == ingestion_time_real


def test_snapshot_cutoff_prevents_future_evidence_leakage():
    """A07: Evidence observed in 2026 reporting a 2023 event must NOT be visible at cutoff 2024."""
    observation_time_2026 = dt(2026, 6, 1)
    valid_from_2023 = dt(2023, 3, 15)
    ingestion_time = dt(2026, 6, 1, 10, 30)

    fact = FactVersion(
        fact_version_id="f_alpha_01",
        logical_fact_id="lf_alpha",
        subject_id="org_tech",
        relation_id="CEO",
        object_id="per_alice",
        valid_from=valid_from_2023,
        valid_to=None,
        evidence_observed_at=observation_time_2026,
        ingested_at_real=ingestion_time,
        supersedes_version_id=None,
        revision_type="creation",
        source_id="trusted_registry_1",
        source_url="https://trusted.test/article_2026.htm",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_2026",
        adjudication_status="AUTO_ACCEPTED"
    )

    # Cutoff 2024: The world event had already happened, but was NOT YET OBSERVED by the KG corpus.
    # Must NOT be visible in the 2024 snapshot.
    cutoff_2024 = dt(2024, 12, 31, 23, 59, 59)
    facts_2024, _ = build_snapshot([fact], cutoff=cutoff_2024)
    assert len(facts_2024) == 0, "Future evidence leak: Fact observed in 2026 leaked into 2024 snapshot!"

    # Cutoff 2026: Evidence has been observed by this cutoff, so fact should now appear.
    cutoff_2026 = dt(2026, 12, 31, 23, 59, 59)
    facts_2026, _ = build_snapshot([fact], cutoff=cutoff_2026)
    assert len(facts_2026) == 1
    assert facts_2026[0].fact_version_id == "f_alpha_01"


def test_missing_observation_time_routes_to_evidence_time_unavailable():
    """A07: Unproven observation time must fail to EVIDENCE_TIME_UNAVAILABLE and not auto-accept."""
    claim = ClaimCandidate(
        claim_id="claim_unproven",
        body_variant_id="bv_unproven",
        subject_mention="Tech Corp",
        relation_name="CEO",
        object_mention="Alice",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_unproven",
        valid_from_extracted="2023-03-15T00:00:00Z"
    )

    catalog = {"Tech Corp": "org_tech", "Alice": "per_alice"}

    accepted, review = adjudicate_claims(
        claims=[claim],
        observation_times={},  # Missing observation time!
        ingested_at=dt(2026, 1, 1),
        entity_catalog=catalog
    )

    assert len(accepted) == 0
    assert len(review) == 1
    assert review[0]["reason"] == "EVIDENCE_TIME_UNAVAILABLE"


def test_missing_valid_from_does_not_fallback_to_observation_time():
    """A07: When claim has no valid_from_extracted, valid_from must NOT be assigned evidence_observed_at."""
    claim = ClaimCandidate(
        claim_id="claim_no_valid_from",
        body_variant_id="bv_no_vf",
        subject_mention="Tech Corp",
        relation_name="CEO",
        object_mention="Alice",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_no_vf",
        valid_from_extracted=None  # No extracted validity date
    )

    observation_time = dt(2026, 6, 1)
    catalog = {"Tech Corp": "org_tech", "Alice": "per_alice"}
    body_to_sources = {
        "bv_no_vf": [{
            "publisher_source_id": "trusted_registry_1",
            "source_url": "https://trusted.test/article.htm"
        }]
    }

    accepted, review = adjudicate_claims(
        claims=[claim],
        observation_times={"claim_no_valid_from": observation_time},
        ingested_at=dt(2026, 6, 1, 12, 0),
        entity_catalog=catalog,
        body_to_sources=body_to_sources
    )

    # If accepted or in review, valid_from must NEVER be set to observation_time
    if accepted:
        assert accepted[0].valid_from != observation_time
        assert accepted[0].valid_from is None
    else:
        assert review[0]["reason"] in ("MISSING_VALID_FROM", "NON_WHITELIST_SOURCE")
