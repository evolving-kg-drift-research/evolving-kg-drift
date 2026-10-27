"""Unit tests for QA panel construction and TransE multi-hop query evaluation."""
from __future__ import annotations

import numpy as np

from evaluation.qa_panel import build_recurring_qa_panel, rank_candidates, score_query_transe


def test_build_recurring_qa_panel_extracts_1hop_and_2hop() -> None:
    triples = {
        ("e0", "r1", "e1"),
        ("e1", "r2", "e2"),
        ("e0", "r3", "e3"),
    }
    snapshots = {"T01": triples, "T02": triples}
    panel = build_recurring_qa_panel(snapshots)

    assert len(panel) >= 3
    # Check 1-hop
    one_hops = [q for q in panel if q["hops"] == 1]
    assert len(one_hops) == 3

    # Check 2-hop
    two_hops = [q for q in panel if q["hops"] == 2]
    assert len(two_hops) == 1
    assert two_hops[0]["head_entity"] == "e0"
    assert two_hops[0]["relation_path"] == ["r1", "r2"]
    assert two_hops[0]["gold_entity"] == "e2"
    assert two_hops[0]["support_entities"] == ["e0", "e1"]


def test_score_query_transe_and_rank_candidates() -> None:
    h = np.array([1.0, 0.0])
    r1 = np.array([0.0, 1.0])
    r2 = np.array([1.0, 0.0])
    # Target prediction: h + r1 + r2 = [2.0, 1.0]

    candidates = ["c0", "c1", "gold"]
    cand_vecs = np.array([
        [0.0, 0.0],  # dist to [2,1] = sqrt(4+1) = sqrt(5)
        [3.0, 1.0],  # dist to [2,1] = 1.0
        [2.0, 1.0],  # dist to [2,1] = 0.0 (exact match)
    ])

    scores = score_query_transe(h, [r1, r2], cand_vecs)
    assert scores[2] > scores[1] > scores[0]

    rank, rr = rank_candidates("gold", candidates, scores)
    assert rank == 1.0
    assert rr == 1.0

    rank_c1, rr_c1 = rank_candidates("c1", candidates, scores)
    assert rank_c1 == 2.0
    assert rr_c1 == 0.5
