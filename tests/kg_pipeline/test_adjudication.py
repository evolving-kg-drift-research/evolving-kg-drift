from datetime import datetime, timezone

from temporal.schema import Claim
from kg_pipeline.adjudication import adjudicate_claims

def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)

def test_adjudicate_claims():
    c1 = Claim(
        claim_id="c1", source_id="trusted_registry_1", 
        subject_mention="Apple", relation_name="CEO", object_mention="Tim Cook",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
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

    observation_times = {
        "c1": dt(2021, 1, 1),
        "c2": dt(2021, 1, 2),
        "c3": dt(2021, 1, 1)
    }

    catalog = {
        "Apple": "org_apple",
        "Tim Cook": "per_tim_cook"
        # Unknown Corp is not in catalog
    }

    accepted, review = adjudicate_claims(
        claims=[c1, c2, c3],
        observation_times=observation_times,
        ingested_at=dt(2025, 1, 1),
        entity_catalog=catalog
    )

    # c1 should be accepted (trusted + known entities)
    assert len(accepted) == 1
    assert accepted[0].subject_id == "org_apple"
    assert accepted[0].adjudication_status == "AUTO_ACCEPTED"
    
    # c2 and c3 should be in review
    assert len(review) == 2
    reasons = [r["reason"] for r in review]
    assert "NON_WHITELIST_SOURCE" in reasons # c2
    assert "UNRESOLVED_ENTITY" in reasons # c3
