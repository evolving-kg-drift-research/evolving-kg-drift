from __future__ import annotations

import pytest

from scripts.audit_legacy_split_t01 import audit, diagnostics


def test_unique_entities_cannot_be_held_out_with_coverage() -> None:
    report = audit([("a", "r", "b"), ("c", "r", "d")])
    assert report["individually_holdout_eligible"] == 0
    assert report["witness_heldout"] == []


def test_simultaneous_removal_preserves_coverage_and_partition() -> None:
    rows = [("a", "r", "b"), ("b", "r", "c"), ("c", "r", "a")]
    report = audit(rows)
    assert report == audit(list(reversed(rows)))
    assert report["individually_holdout_eligible"] == 3
    assert len(report["witness_heldout"]) == 1
    assert report["coverage_preserving_greedy_witness"]["unseen_entities"] == []
    assert set(report["witness_train"] + report["witness_heldout"]) == set(rows)


def test_diagnostics_counts_oov_and_parallel_pairs_separately() -> None:
    report = diagnostics([("a", "r", "b")], [("b", "s", "a"), ("c", "r", "a")])
    assert report["entity_oov_triples"] == 1
    assert report["relation_oov_triples"] == 1
    assert report["fully_seen_heldout_triples"] == 0
    assert report["heldout_pairs_also_in_training"] == 1


def test_audit_rejects_duplicate_triples() -> None:
    with pytest.raises(ValueError, match="unique"):
        audit([("a", "r", "b"), ("a", "r", "b")])
