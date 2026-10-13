from __future__ import annotations

from scripts.audit_v3_producer_lineage import byte_variants_match, candidate_id
from scripts.run_legacy_transe_t01 import sha


def test_crlf_hypothesis_does_not_claim_exact_git_blob() -> None:
    observed=byte_variants_match(b"a\nb\n",sha(b"a\r\nb\r\n"))
    assert observed["exact_blob"] is False
    assert observed["crlf_hypothesis"] is True


def test_id_rule_is_only_a_surface_form_diagnostic() -> None:
    assert candidate_id(" X ")==candidate_id("x")
    assert candidate_id("Company A")!=candidate_id("A Incorporated")
