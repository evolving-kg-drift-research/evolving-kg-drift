from datetime import datetime, timezone

import pytest
from temporal.schema import FactVersion, Claim, ContractError
from temporal.snapshot import build_snapshot


def dt(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)

def test_claim_contract_requires_span():
    with pytest.raises(ContractError, match="Evidence span offsets are mandatory"):
        Claim("c1", "s1", "A", "REL", "B", None, None, "hash")

    with pytest.raises(ContractError, match="strictly less than end"):
        Claim("c1", "s1", "A", "REL", "B", 10, 10, "hash")


def test_fact_version_contract_timezone():
    with pytest.raises(ContractError, match="must be timezone-aware"):
        FactVersion(
            "fv1", "lf1", "A", "REL", "B",
            valid_from=dt(2021, 1, 1), valid_to=None,
            evidence_observed_at=datetime(2021, 1, 1), # Naive
            ingested_at_real=dt(2021, 1, 2),
            supersedes_version_id=None, revision_type="creation",
            source_id="s1", source_url="",
            evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
        )


def test_late_alias_does_not_rewrite_history():
    fact_v1 = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="CompanyA",
        relation_id="CEO",
        object_id="PersonAlias",
        valid_from=dt(2020, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2020, 1, 1),
        ingested_at_real=dt(2025, 1, 1),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="http://s1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
        entity_map_version="v1"
    )
    
    # We learn at 2021-01-01 that PersonAlias is canonical_person_1
    fact_v2 = FactVersion(
        fact_version_id="fv2",
        logical_fact_id="lf1",
        subject_id="CompanyA",
        relation_id="CEO",
        object_id="canonical_person_1",
        valid_from=dt(2020, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2021, 1, 1), # Learned later
        ingested_at_real=dt(2025, 1, 1),
        supersedes_version_id="fv1",
        revision_type="alias_resolution",
        source_id="s1",
        source_url="http://s1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
        entity_map_version="v2"
    )

    facts = [fact_v1, fact_v2]

    # Snapshot at 2020-06-01: fact_v2 is NOT known yet.
    snap_2020, _ = build_snapshot(facts, cutoff=dt(2020, 6, 1))
    assert len(snap_2020) == 1
    assert snap_2020[0].object_id == "PersonAlias"

    # Snapshot at 2021-06-01: fact_v2 IS known, supersedes fact_v1.
    snap_2021, _ = build_snapshot(facts, cutoff=dt(2021, 6, 1))
    assert len(snap_2021) == 1
    assert snap_2021[0].object_id == "canonical_person_1"


def test_retraction_closes_logical_fact():
    fact_v1 = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 1, 1), ingested_at_real=dt(2020, 1, 1),
        supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )

    fact_v2 = FactVersion(
        fact_version_id="fv2",
        logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 2, 1), ingested_at_real=dt(2020, 2, 1),
        supersedes_version_id="fv1", revision_type="retraction",
        source_id="s2", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )

    facts = [fact_v1, fact_v2]

    snap_jan, _ = build_snapshot(facts, cutoff=dt(2020, 1, 15))
    assert len(snap_jan) == 1

    snap_feb, _ = build_snapshot(facts, cutoff=dt(2020, 2, 15))
    assert len(snap_feb) == 0  # Retracted


def test_snapshot_canonical_determinism():
    fact = FactVersion(
        fact_version_id="fv1", logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 1, 1), ingested_at_real=dt(2020, 1, 1),
        supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )
    
    snap1, hash1 = build_snapshot([fact], cutoff=dt(2025, 1, 1))
    snap2, hash2 = build_snapshot([fact], cutoff=dt(2025, 1, 1))
    
    assert hash1 == hash2
