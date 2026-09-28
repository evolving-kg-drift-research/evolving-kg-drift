import pytest

from kg_pipeline.evidence import (
    IDENTITY_NORMALIZATION_VERSION,
    NFC_NORMALIZATION_VERSION,
    EvidenceSpan,
    normalize_clean_text,
)
from temporal.schema import ContractError


def test_unicode_evidence_span_hash_references_exact_code_point_slice():
    text = "Cafe\u0301 hired Zoë."
    span_text = "Zoë"
    start = text.index(span_text)
    span = EvidenceSpan.from_text(text, start, start + len(span_text), IDENTITY_NORMALIZATION_VERSION)
    assert text[span.start:span.end] == span_text
    assert len(span.text_sha256) == 64
    assert span.clean_text_sha256


def test_nfc_is_explicit_and_rejects_text_not_stored_in_nfc():
    decomposed = "Cafe\u0301"
    assert normalize_clean_text(decomposed, NFC_NORMALIZATION_VERSION) == "Café"
    with pytest.raises(ContractError, match="does not match"):
        EvidenceSpan.from_text(decomposed, 0, len(decomposed), NFC_NORMALIZATION_VERSION)
    span = EvidenceSpan.from_text("Café", 0, 4, NFC_NORMALIZATION_VERSION)
    assert span.normalization_version == NFC_NORMALIZATION_VERSION
