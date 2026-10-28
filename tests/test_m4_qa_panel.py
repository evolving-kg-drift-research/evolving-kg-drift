"""Unit tests for QA panel construction and TransE multi-hop query evaluation."""
from __future__ import annotations

import numpy as np

from evaluation.qa_panel import (
    build_recurring_qa_panel,
    evaluate_query,
    rank_candidates,
    score_query_transe,
)
from kge.checkpoint import CheckpointProvenance, KGECheckpoint


def test_build_recurring_qa_panel_extracts_1hop_and_2hop() -> None:
    triples = {
        ("e0", "r1", "e1"),
        ("e1", "r2", "e2"),
        ("e0", "r3", "e3"),
    }
    snapshots = {"T01": triples, "T02": triples}
    panel = build_recurring_qa_panel(snapshots)

    assert len(panel) >= 3
    # Check 1-hop: support_entities must include gold entity t: [h, t]
    one_hops = [q for q in panel if q["hops"] == 1]
    assert len(one_hops) == 3
    assert one_hops[0]["support_entities"] == [one_hops[0]["head_entity"], one_hops[0]["gold_entity"]]

    # Check 2-hop: support_entities must include gold entity t: [h, m, t]
    two_hops = [q for q in panel if q["hops"] == 2]
    assert len(two_hops) == 1
    assert two_hops[0]["head_entity"] == "e0"
    assert two_hops[0]["relation_path"] == ["r1", "r2"]
    assert two_hops[0]["gold_entity"] == "e2"
    assert two_hops[0]["support_entities"] == ["e0", "e1", "e2"]


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


def _make_dummy_provenance() -> CheckpointProvenance:
    return CheckpointProvenance(
        snapshot_id="T01",
        snapshot_hash="hash01",
        seed=13,
        model="TransE-L2",
        dimension=2,
        norm=2,
        entity_mapping_hash="emap01",
        relation_mapping_hash="rmap01",
        config_hash="cfg01",
    )


def test_evaluate_query_handles_unseen_candidates_without_dropping() -> None:
    ckpt = KGECheckpoint(
        provenance=_make_dummy_provenance(),
        entity_embeddings={
            "e0": [1.0, 0.0],
            "c_seen": [3.0, 1.0],
            "gold": [2.0, 1.0],
        },
        relation_embeddings={
            "r1": [1.0, 1.0],
        },
        training_metrics={"loss": 0.1},
    )
    query = {
        "head_entity": "e0",
        "relation_path": ["r1"],
        "gold_entity": "gold",
    }
    # Target is e0 + r1 = [2.0, 1.0], matching gold exactly.
    # Candidates include unseen candidates not in checkpoint.
    candidates = ["c_seen", "gold", "unseen_1", "unseen_2"]

    rank, rr = evaluate_query(query, ckpt, candidates)
    # Gold matches exactly -> rank 1.0, RR 1.0; unseen candidates are preserved behind gold with score -inf
    assert rank == 1.0
    assert rr == 1.0

    # Query where gold is c_seen: dist = 1.0, while unseen have -inf
    query_c = {
        "head_entity": "e0",
        "relation_path": ["r1"],
        "gold_entity": "c_seen",
    }
    rank_c, rr_c = evaluate_query(query_c, ckpt, candidates)
    # Gold is behind "gold" (score 0.0 > -1.0) but ahead of unseen_1, unseen_2 (-inf)
    assert rank_c == 2.0
    assert rr_c == 0.5


def test_evaluate_query_oov_gold_returns_zero_rr() -> None:
    ckpt = KGECheckpoint(
        provenance=_make_dummy_provenance(),
        entity_embeddings={
            "e0": [1.0, 0.0],
            "c_seen": [3.0, 1.0],
        },
        relation_embeddings={
            "r1": [1.0, 1.0],
        },
        training_metrics={"loss": 0.1},
    )
    query = {
        "head_entity": "e0",
        "relation_path": ["r1"],
        "gold_entity": "oov_gold",
    }
    candidates = ["c_seen", "oov_gold"]
    rank, rr = evaluate_query(query, ckpt, candidates)
    assert rank == float("inf")
    assert rr == 0.0

