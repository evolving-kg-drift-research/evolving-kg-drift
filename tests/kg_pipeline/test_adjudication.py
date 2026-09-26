from datetime import datetime, timezone

from temporal.schema import Claim
from kg_pipeline.adjudication import adjudicate_claims

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
        subject_mention="apple inc", relation_name="CEO", object_mention="tim cook",
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
        "apple inc": "org_apple",
        "Tim Cook": "per_tim_cook"
        # Unknown Corp is not in catalog
    }

    accepted, review = adjudicate_claims(
        claims=[c1, c2, c3, c4, c5],
        observation_times=observation_times,
        ingested_at=dt(2025, 1, 1),
        entity_catalog=catalog
    )

    # c1 and c4 should be accepted (trusted + known entities/fuzzy matched)
    assert len(accepted) == 2
    assert accepted[0].subject_id == "org_apple"
    assert accepted[0].adjudication_status == "AUTO_ACCEPTED"
    assert accepted[0].valid_from == datetime(2011, 8, 24, tzinfo=timezone.utc)
    assert accepted[0].confidence == 0.9

    assert accepted[1].subject_id == "org_apple"

    # c2, c3, c5 should be in review
    assert len(review) == 3
    reasons = [r["reason"] for r in review]
    assert "NON_WHITELIST_SOURCE" in reasons # c2
    assert "UNRESOLVED_ENTITY" in reasons # c3
    assert "SPECULATIVE_OR_NEGATIVE" in reasons # c5
