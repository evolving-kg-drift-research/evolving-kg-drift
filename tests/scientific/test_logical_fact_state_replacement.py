"""Scientific conformance tests for A10 and A11:
- A10: Relation-specific logical keys (e.g. state relation is_CEO_of keys on [relation, object] to support functional replacement).
- A11: Explicit revision chains (creation, state_change, correction, retraction) with populated supersedes_version_id.
"""

from __future__ import annotations

from datetime import datetime, timezone

from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot_edges_and_support, compute_logical_fact_id


def dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_relation_specific_logical_key_and_state_replacement():
    """A10/A11: is_CEO_of is a state relation with functional dependency [relation, object].

    When Tim Cook replaces Steve Jobs, they share the logical fact ID, and state_change replaces prior state.
    """
    # 1. Verify relation-specific logical key
    ontology_rules = {
        "is_CEO_of": {
            "temporal_semantics": "state",
            "logical_key": ["relation", "object"]
        },
        "released_by": {
            "temporal_semantics": "event",
            "logical_key": ["subject", "relation", "object"]
        }
    }

    key_steve = compute_logical_fact_id("Steve Jobs", "is_CEO_of", "Apple", ontology_rules)
    key_tim = compute_logical_fact_id("Tim Cook", "is_CEO_of", "Apple", ontology_rules)

    # For state relation is_CEO_of: the key depends on [relation, object] (who is Apple's CEO?),
    # so both versions share the identical logical fact ID!
    assert key_steve == key_tim, "State relation must share logical_fact_id across successors"

    # For event relation released_by: different subjects produce different logical keys
    key_event1 = compute_logical_fact_id("ChatGPT", "released_by", "OpenAI", ontology_rules)
    key_event2 = compute_logical_fact_id("Claude", "released_by", "Anthropic", ontology_rules)
    assert key_event1 != key_event2

    # 2. Build revision chain
    fv_steve = FactVersion(
        fact_version_id="fv_ceo_steve",
        logical_fact_id=key_steve,
        subject_id="Steve Jobs",
        relation_id="is_CEO_of",
        object_id="Apple",
        valid_from=dt(1997, 9, 16),
        valid_to=dt(2011, 8, 24),
        evidence_observed_at=dt(2000, 1, 1),
        ingested_at_real=dt(2000, 1, 2),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="sec_filing",
        source_url="https://sec.gov/steve_ceo",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_steve",
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_steve",)
    )

    fv_tim = FactVersion(
        fact_version_id="fv_ceo_tim",
        logical_fact_id=key_tim,
        subject_id="Tim Cook",
        relation_id="is_CEO_of",
        object_id="Apple",
        valid_from=dt(2011, 8, 24),
        valid_to=None,
        evidence_observed_at=dt(2011, 8, 25),
        ingested_at_real=dt(2011, 8, 26),
        supersedes_version_id="fv_ceo_steve",
        revision_type="state_change",
        source_id="sec_filing",
        source_url="https://sec.gov/tim_ceo",
        evidence_span_start=0,
        evidence_span_end=20,
        evidence_text_hash="hash_tim",
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_tim",)
    )

    # Cutoff 2005: Steve Jobs is the active CEO
    edges_2005, _, _ = build_snapshot_edges_and_support(
        [fv_steve, fv_tim],
        cutoff=dt(2005, 1, 1),
        snapshot_id="S_2005",
        provenance_map={"fv_ceo_steve": [{
            "provenance_id": "prov_steve", "claim_id": "claim_steve",
            "membership_id": "mem_steve", "source_version_id": "sv_steve",
            "retrieval_id": "ret_steve", "raw_blob_sha256": "1" * 64,
        }]},
    )
    assert len(edges_2005) == 1
    assert edges_2005[0].subject_id == "Steve Jobs"

    # Cutoff 2015: Tim Cook is the active CEO (state change replaces prior state)
    edges_2015, _, _ = build_snapshot_edges_and_support(
        [fv_steve, fv_tim],
        cutoff=dt(2015, 1, 1),
        snapshot_id="S_2015",
        provenance_map={
            "fv_ceo_steve": [{
                "provenance_id": "prov_steve", "claim_id": "claim_steve",
                "membership_id": "mem_steve", "source_version_id": "sv_steve",
                "retrieval_id": "ret_steve", "raw_blob_sha256": "1" * 64,
            }],
            "fv_ceo_tim": [{
                "provenance_id": "prov_tim", "claim_id": "claim_tim",
                "membership_id": "mem_tim", "source_version_id": "sv_tim",
                "retrieval_id": "ret_tim", "raw_blob_sha256": "2" * 64,
            }],
        },
    )
    assert len(edges_2015) == 1
    assert edges_2015[0].subject_id == "Tim Cook"


def test_retraction_removes_fact_from_subsequent_snapshots():
    """A11: A retraction revision removes the fact from future snapshots while preserving prior ones."""
    key = "lf_rumor"
    fv_rumor = FactVersion(
        fact_version_id="fv_rumor_01",
        logical_fact_id=key,
        subject_id="Alpha",
        relation_id="acquired_by",
        object_id="Beta",
        valid_from=dt(2024, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2024, 1, 2),
        ingested_at_real=dt(2024, 1, 3),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="news",
        source_url="https://news.test/rumor",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash_rumor",
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_rumor",)
    )

    fv_retract = FactVersion(
        fact_version_id="fv_retract_01",
        logical_fact_id=key,
        subject_id="Alpha",
        relation_id="acquired_by",
        object_id="Beta",
        valid_from=dt(2024, 1, 1),
        valid_to=dt(2024, 1, 10),
        evidence_observed_at=dt(2024, 1, 10),
        ingested_at_real=dt(2024, 1, 11),
        supersedes_version_id="fv_rumor_01",
        revision_type="retraction",
        source_id="news",
        source_url="https://news.test/correction",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash_correction",
        adjudication_status="AUTO_ACCEPTED",
        supporting_claim_ids=("claim_correction",)
    )

    # Cutoff Jan 5 (before retraction): fact is visible
    edges_pre, _, _ = build_snapshot_edges_and_support(
        [fv_rumor, fv_retract],
        cutoff=dt(2024, 1, 5),
        snapshot_id="S_pre",
        provenance_map={"fv_rumor_01": [{
            "provenance_id": "prov_rumor", "claim_id": "claim_rumor",
            "membership_id": "mem_rumor", "source_version_id": "sv_rumor",
            "retrieval_id": "ret_rumor", "raw_blob_sha256": "3" * 64,
        }]},
    )
    assert len(edges_pre) == 1

    # Cutoff Jan 15 (after retraction observed): fact is retracted and gone
    edges_post, _, _ = build_snapshot_edges_and_support(
        [fv_rumor, fv_retract],
        cutoff=dt(2024, 1, 15),
        snapshot_id="S_post",
        provenance_map={
            "fv_rumor_01": [{
                "provenance_id": "prov_rumor", "claim_id": "claim_rumor",
                "membership_id": "mem_rumor", "source_version_id": "sv_rumor",
                "retrieval_id": "ret_rumor", "raw_blob_sha256": "3" * 64,
            }],
            "fv_retract_01": [{
                "provenance_id": "prov_correction", "claim_id": "claim_correction",
                "membership_id": "mem_correction", "source_version_id": "sv_correction",
                "retrieval_id": "ret_correction", "raw_blob_sha256": "4" * 64,
            }],
        },
    )
    assert len(edges_post) == 0
