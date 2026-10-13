from __future__ import annotations

from scripts.audit_recovered_v3_evidence import inspect_span
from scripts.run_legacy_transe_t01 import sha


def test_whole_body_hash_does_not_certify_subspan() -> None:
    text="first sentence; second sentence"
    result=inspect_span(text,0,14,sha(text.encode()))
    assert result["whole_body_hash_match"] is True
    assert result["span_hash_match"] is False
    assert result["offsets_valid"] is True


def test_exact_span_hash_and_out_of_bounds() -> None:
    text="abc def"
    assert inspect_span(text,4,7,sha(b"def"))["span_hash_match"] is True
    assert inspect_span(text,4,99,sha(b"def"))["span_hash_match"] is False
