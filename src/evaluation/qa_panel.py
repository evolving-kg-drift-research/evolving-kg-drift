"""Recurring multi-hop QA panel construction, TransE path scoring, and Arm A/B evaluation."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

import numpy as np

from kge.checkpoint import KGECheckpoint


def build_recurring_qa_panel(
    canonical_snapshots: dict[str, set[tuple[str, str, str]]],
) -> list[dict[str, Any]]:
    """Build persistent 1-hop and 2-hop multi-hop reasoning queries from T01 triples."""
    snapshots = sorted(canonical_snapshots.keys())
    # Persistent triples in T01 that remain in all snapshots:
    persistent = set.intersection(*(canonical_snapshots[sid] for sid in snapshots))

    queries: list[dict[str, Any]] = []
    query_idx = 0

    # 1-hop queries from persistent triples
    for h, r, t in sorted(persistent):
        queries.append({
            "query_id": f"q_1hop_{query_idx:04d}",
            "query_type": "1hop",
            "hops": 1,
            "head_entity": h,
            "relation_path": [r],
            "gold_entity": t,
            "support_entities": [h],
        })
        query_idx += 1

    # 2-hop queries: (h, r1, m) and (m, r2, t) in persistent triples
    adj = defaultdict(list)
    for h, r, t in sorted(persistent):
        adj[h].append((r, t))

    for h in sorted(adj):
        for r1, m in sorted(adj[h]):
            if m in adj:
                for r2, t in sorted(adj[m]):
                    if t != h:  # Non-trivial cycle avoidance
                        queries.append({
                            "query_id": f"q_2hop_{query_idx:04d}",
                            "query_type": "2hop",
                            "hops": 2,
                            "head_entity": h,
                            "relation_path": [r1, r2],
                            "gold_entity": t,
                            "support_entities": [h, m],
                        })
                        query_idx += 1

    return queries


def score_query_transe(
    head_vec: np.ndarray,
    relation_vecs: list[np.ndarray],
    candidate_vecs: np.ndarray,
) -> np.ndarray:
    """TransE L2 scoring for multi-hop path query: -||h + sum(r_i) - c||_2."""
    target_pred = head_vec + sum(relation_vecs)
    # L2 distances
    diff = candidate_vecs - target_pred
    dists = np.linalg.norm(diff, axis=1)
    # Higher score is better: -distance
    return -dists


def rank_candidates(
    gold_entity: str,
    candidates: list[str],
    candidate_scores: np.ndarray,
) -> tuple[float, float]:
    """Rank candidates with average tie-breaking. Returns (rank, reciprocal_rank)."""
    if gold_entity not in candidates:
        return float("inf"), 0.0

    target_idx = candidates.index(gold_entity)
    target_score = candidate_scores[target_idx]

    better = int(np.sum(candidate_scores > target_score))
    tied = int(np.sum(candidate_scores == target_score))
    rank = 1.0 + better + (tied - 1) / 2.0
    reciprocal_rank = 1.0 / rank
    return rank, reciprocal_rank


def evaluate_query(
    query: dict[str, Any],
    checkpoint: KGECheckpoint,
    candidates: list[str],
) -> tuple[float, float]:
    """Evaluate a single query on a checkpoint within a candidate universe."""
    h = query["head_entity"]
    gold = query["gold_entity"]
    relations = query["relation_path"]

    # Check if head and relations exist in checkpoint
    if h not in checkpoint.entity_embeddings:
        return float("inf"), 0.0
    for r in relations:
        if r not in checkpoint.relation_embeddings:
            return float("inf"), 0.0

    # Filter candidates present in checkpoint
    admissible_candidates = [c for c in candidates if c in checkpoint.entity_embeddings]
    if gold not in admissible_candidates:
        return float("inf"), 0.0

    head_vec = np.asarray(checkpoint.entity_embeddings[h], dtype=float)
    rel_vecs = [np.asarray(checkpoint.relation_embeddings[r], dtype=float) for r in relations]
    cand_vecs = np.asarray([checkpoint.entity_embeddings[c] for c in admissible_candidates], dtype=float)

    scores = score_query_transe(head_vec, rel_vecs, cand_vecs)
    return rank_candidates(gold, admissible_candidates, scores)


def evaluate_query_three_seeds(
    query: dict[str, Any],
    checkpoints: Sequence[KGECheckpoint],
    candidates: list[str],
) -> tuple[float, float]:
    """Evaluate query across 3 seeds and take median RR."""
    rrs = []
    ranks = []
    for cp in checkpoints:
        rank, rr = evaluate_query(query, cp, candidates)
        ranks.append(rank)
        rrs.append(rr)

    return float(np.median(ranks)), float(np.median(rrs))
