from __future__ import annotations

import pytest

from scripts.evaluate_legacy_t01 import metrics, rank_query


def test_filtered_tail_keeps_target_and_removes_other_positive() -> None:
    row = ("a", "r", "b")
    result = rank_query(row, "tail", ["a", "b", "c"], {row, ("a", "r", "c")},
                        lambda t: {"a": 0.0, "b": 1.0, "c": 2.0}[t[2]])
    assert result["rank"] == 1
    assert result["filtered_count"] == 1
    assert result["candidate_count"] == 2


def test_head_scores_and_average_ties() -> None:
    result = rank_query(("a", "r", "b"), "head", ["a", "b", "c", "d"], set(),
                        lambda t: 2.0 if t[0] == "d" else 1.0)
    assert result["rank"] == 3
    assert result["tied_including_target"] == 3
    assert metrics([result]) == {"queries": 1, "MRR": 1/3, "Hits@1": 0, "Hits@3": 1, "Hits@10": 1}


def test_average_rank_not_optimistic_hits() -> None:
    result = rank_query(("a", "r", "b"), "head", ["a", "b"], set(), lambda _: 1.0)
    assert result["rank"] == 1.5
    assert metrics([result])["Hits@1"] == 0


def test_missing_target_rejected() -> None:
    with pytest.raises(ValueError, match="Missing target"):
        rank_query(("a", "r", "b"), "tail", ["a"], set(), lambda _: 0.0)
