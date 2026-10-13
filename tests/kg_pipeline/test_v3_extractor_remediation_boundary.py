"""Reproduce old body-hash and one-role grounding defects using fixtures only."""
from __future__ import annotations

from pathlib import Path

import pytest

from kg_pipeline.claims import extract_claims
from kg_pipeline.evidence import IDENTITY_NORMALIZATION_VERSION
from kg_pipeline.hashing import sha256_text
from kg_pipeline.llm_adapter import OfflineMockAdapter


@pytest.mark.parametrize("prefix", ["Context before. ", "Bối cảnh trước. "])
def test_extractor_binds_exact_subspan_not_legacy_body_hash(tmp_path: Path, prefix: str) -> None:
    evidence="Company A partners with Company B."
    text=prefix+evidence+" Context after."
    start=len(prefix)
    adapter=OfflineMockAdapter({"claims":[{
        "subject_mention":"Company A","object_mention":"Company B","relation_name":"partners_with",
        "evidence_span_start":start,"evidence_span_end":start+len(evidence),
        "evidence_text_hash":sha256_text(text),
    }]})
    valid,review=extract_claims(text,body_variant_id="fixture-body",cache_dir=tmp_path,
                              ontology=["partners_with"],adapter=adapter,
                              normalization_version=IDENTITY_NORMALIZATION_VERSION)
    assert not review
    assert len(valid)==1
    assert valid[0].evidence_text_hash==sha256_text(evidence)
    assert valid[0].evidence_text_hash!=sha256_text(text)
    assert (valid[0].evidence_span_start,valid[0].evidence_span_end)==(start,start+len(evidence))


def test_extractor_quarantines_claim_with_only_one_grounded_role(tmp_path: Path) -> None:
    text="Company A announces a product."
    adapter=OfflineMockAdapter({"claims":[{
        "subject_mention":"Company A","object_mention":"Company B","relation_name":"partners_with",
        "evidence_span_start":0,"evidence_span_end":len(text),
    }]})
    valid,review=extract_claims(text,body_variant_id="fixture-body",cache_dir=tmp_path,
                              ontology=["partners_with"],adapter=adapter,
                              normalization_version=IDENTITY_NORMALIZATION_VERSION)
    assert not valid
    assert len(review)==1
    assert "Object mention is not grounded" in review[0]["error"]
