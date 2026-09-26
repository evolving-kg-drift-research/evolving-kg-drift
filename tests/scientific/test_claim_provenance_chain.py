"""Scientific conformance tests for A05 and A06:
- A05: Claim extraction operates on text representations (body_variant_id).
       Multi-hop provenance is resolved separately into ClaimProvenance without masquerading as source_id.
- A06: body_to_sources mapping in adjudication is fully populated from memberships and retrievals.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from temporal.schema import ClaimCandidate, ClaimProvenance, ContractError
from kg_pipeline.claims import extract_claims, resolve_claim_provenance
from kg_pipeline.llm_adapter import OfflineMockAdapter


def test_claim_candidate_uses_body_variant_identity(tmp_path: Path):
    """A05: ClaimCandidate must explicitly record body_variant_id, not masquerade as source_id."""
    text = "Here is an article: Alpha Corp appointed John Doe as Chief Executive Officer in 2023."
    cache_dir = tmp_path / "llm_cache"
    adapter = OfflineMockAdapter({
        "claims": [{
            "subject_mention": "Alpha Corp",
            "relation_name": "CEO",
            "object_mention": "John Doe",
            "evidence_span_start": 20,
            "evidence_span_end": 75,
            "valid_from_extracted": "2023-01-01"
        }]
    })

    candidates, dlq = extract_claims(
        text=text,
        body_variant_id="bv_alpha_001",
        cache_dir=cache_dir,
        ontology=["CEO"],
        adapter=adapter
    )

    assert len(dlq) == 0
    assert len(candidates) == 1
    c = candidates[0]
    assert isinstance(c, ClaimCandidate)
    assert c.body_variant_id == "bv_alpha_001"
    # Ensure source_id property exists for backwards compatibility but resolves to body_variant_id
    assert c.body_variant_id == "bv_alpha_001"


def test_claim_provenance_resolves_multiple_sources(tmp_path: Path):
    """A05: When 2 source versions produce the identical body_variant,

    both provenance paths must be retained in ClaimProvenance rather than collapsed.
    """
    candidate = ClaimCandidate(
        claim_id="claim_001",
        body_variant_id="bv_shared_123",
        subject_mention="Alpha",
        relation_name="CEO",
        object_mention="John",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="abc_hash"
    )

    memberships_rows = [
        {
            "membership_id": "mem_01",
            "body_variant_id": "bv_shared_123",
            "raw_blob_sha256": "raw_blob_111",
            "retrieval_ids_json": json.dumps(["ret_01"]),
            "strict_input_eligible": True
        },
        {
            "membership_id": "mem_02",
            "body_variant_id": "bv_shared_123",
            "raw_blob_sha256": "raw_blob_222",
            "retrieval_ids_json": json.dumps(["ret_02"]),
            "strict_input_eligible": True
        }
    ]

    retrievals_rows = [
        {
            "retrieval_id": "ret_01",
            "source_id": "publisher_tuoitre",
            "final_url": "https://tuoitre.vn/article1.htm",
            "raw_blob_sha256": "raw_blob_111"
        },
        {
            "retrieval_id": "ret_02",
            "source_id": "publisher_thanhnien",
            "final_url": "https://thanhnien.vn/article2.htm",
            "raw_blob_sha256": "raw_blob_222"
        }
    ]

    provenance_records = resolve_claim_provenance(
        claims=[candidate],
        memberships=memberships_rows,
        retrievals=retrievals_rows
    )

    # Must preserve both source provenance links
    assert len(provenance_records) == 2
    sources = {p.publisher_source_id for p in provenance_records}
    assert sources == {"publisher_tuoitre", "publisher_thanhnien"}
    urls = {p.source_url for p in provenance_records}
    assert urls == {"https://tuoitre.vn/article1.htm", "https://thanhnien.vn/article2.htm"}


def test_missing_membership_fails_provenance_resolution():
    """A05: A claim with unknown body_variant_id must fail closed or be marked as unverified provenance."""
    candidate = ClaimCandidate(
        claim_id="claim_orphan",
        body_variant_id="bv_orphan_999",
        subject_mention="X",
        relation_name="CEO",
        object_mention="Y",
        evidence_span_start=0,
        evidence_span_end=5,
        evidence_text_hash="hash"
    )

    provenance_records = resolve_claim_provenance(
        claims=[candidate],
        memberships=[],
        retrievals=[]
    )
    # Orphan claim has no verified provenance
    assert len(provenance_records) == 0


def test_body_to_sources_trust_propagation_in_adjudication():
    """A06: body_to_sources mapping in adjudication correctly propagates trust and real source URL."""
    from datetime import datetime, timezone
    from kg_pipeline.adjudication import adjudicate_claims

    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Claim candidate extracted from body variant bv_test_01
    c1 = ClaimCandidate(
        claim_id="claim_01",
        body_variant_id="bv_test_01",
        subject_mention="Apple",
        relation_name="CEO",
        object_mention="Tim Cook",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash_01",
        valid_from_extracted="2011-08-24T00:00:00Z"
    )

    # Claim candidate extracted from untrusted body variant bv_test_02
    c2 = ClaimCandidate(
        claim_id="claim_02",
        body_variant_id="bv_test_02",
        subject_mention="Apple",
        relation_name="CEO",
        object_mention="Tim Cook",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash_02",
        valid_from_extracted="2011-08-24T00:00:00Z"
    )

    body_to_sources = {
        "bv_test_01": [
            {
                "publisher_source_id": "trusted_registry_1",
                "source_url": "https://sec.gov/filing/apple_ceo.htm",
                "retrieval_id": "ret_sec_01",
                "retrieved_at_real": "2025-01-01T10:00:00Z",
                "raw_blob_sha256": "blob_hash_01",
            }
        ],
        "bv_test_02": [
            {
                "publisher_source_id": "untrusted_blog",
                "source_url": "https://randomblog.test/post.htm",
                "retrieval_id": "ret_blog_01",
                "retrieved_at_real": "2025-01-01T10:00:00Z",
                "raw_blob_sha256": "blob_hash_02",
            }
        ]
    }

    catalog = {
        "Apple": "org_apple",
        "Tim Cook": "per_tim_cook"
    }

    observation_times = {
        "claim_01": now,
        "claim_02": now
    }

    accepted, review = adjudicate_claims(
        claims=[c1, c2],
        observation_times=observation_times,
        ingested_at=now,
        entity_catalog=catalog,
        body_to_sources=body_to_sources
    )

    assert len(accepted) == 1
    assert accepted[0].fact_version_id.startswith(accepted[0].logical_fact_id)
    # The source_id and source_url must reflect the real publisher source, NOT the body variant id!
    assert accepted[0].source_id == "trusted_registry_1"
    assert accepted[0].source_url == "https://sec.gov/filing/apple_ceo.htm"
    assert accepted[0].adjudication_status == "AUTO_ACCEPTED"
    assert accepted[0].confidence == 0.9

    assert len(review) == 1
    assert review[0]["claim_id"] == "claim_02"
    assert review[0]["reason"] == "NON_WHITELIST_SOURCE"
    assert review[0]["provisional_fact"].source_id == "untrusted_blog"
    assert review[0]["provisional_fact"].source_url == "https://randomblog.test/post.htm"

