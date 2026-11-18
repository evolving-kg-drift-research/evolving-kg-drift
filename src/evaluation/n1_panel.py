"""Pure path selection and filtered embedding ranking helpers for the N1 panel."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence

import numpy as np

Triple = tuple[str, str, str]


def eligible_paths(
    triples: Sequence[Triple], eligible: Collection[str], hops: Sequence[int] = (2, 3)
) -> dict[int, list[tuple[str, ...]]]:
    """Enumerate eligible simple directed paths without endpoint shortcuts in either direction."""
    result: dict[int, list[tuple[str, ...]]] = {hop: [] for hop in hops}
    if any(hop not in (2, 3) for hop in result):
        raise ValueError("Only two-hop and three-hop paths are supported")
    if not result:
        return result

    eligible_set = set(eligible)
    direct_links = {(head, tail) for head, _, tail in triples}
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for head, relation, tail in sorted(set(triples)):
        if head in eligible_set and tail in eligible_set:
            adjacency[head].append((relation, tail))

    for head in sorted(adjacency):
        frontier: list[tuple[str, ...]] = [(head,)]
        for hop in range(1, max(result) + 1):
            frontier = [
                path + (relation, tail)
                for path in frontier
                for relation, tail in adjacency.get(path[-1], [])
                if tail not in path[::2]
            ]
            if hop in result:
                result[hop].extend(
                    path for path in frontier
                    if (path[0], path[-1]) not in direct_links and (path[-1], path[0]) not in direct_links
                )

    return {hop: sorted(paths) for hop, paths in result.items()}


def cap_per_head(paths: Sequence[tuple[str, ...]], cap: int, salt: str = "n1-cap") -> list[tuple[str, ...]]:
    """Keep up to cap paths per head using the salted SHA-256 ordering."""
    if cap < 1:
        raise ValueError("cap must be at least one")
    by_head: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for path in paths:
        by_head[path[0]].append(path)

    kept: list[tuple[str, ...]] = []
    for group in by_head.values():
        ordered = sorted(
            group,
            key=lambda path: (
                hashlib.sha256((salt + "|" + path[0] + "|" + "|".join(path)).encode()).hexdigest(),
                path,
            ),
        )
        kept.extend(ordered[:cap])
    return sorted(kept)


def support_entities(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return entities in path order, retaining only the first occurrence of each."""
    return tuple(dict.fromkeys(path[::2]))


def path_relations(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return relations in path order."""
    return path[1::2]


def path_answers(triples: Sequence[Triple], head: str, relations: Sequence[str]) -> set[str]:
    """Follow exactly the given directed relation sequence, allowing entity revisits."""
    adjacency: dict[tuple[str, str], set[str]] = defaultdict(set)
    for source, relation, tail in triples:
        adjacency[source, relation].add(tail)
    answers = {head}
    for relation in relations:
        answers = {tail for source in answers for tail in adjacency.get((source, relation), set())}
    return answers


def reciprocal_rank_path(
    entity: np.ndarray,
    relation: np.ndarray,
    e2i: Mapping[str, int],
    r2i: Mapping[str, int],
    head: str,
    relations: Sequence[str],
    gold: str,
    others: Collection[str],
) -> float:
    """Rank gold over all entity rows with filtered answers and exact midrank ties."""
    query = entity[e2i[head]] + sum(relation[r2i[name]] for name in relations)
    scores = -np.linalg.norm(entity - query, axis=1)
    gold_score = scores[e2i[gold]]
    keep = np.ones(entity.shape[0], dtype=bool)
    for other in others:
        if other != gold:
            keep[e2i[other]] = False
    better = int(np.count_nonzero(keep & (scores > gold_score)))
    tied_others = int(np.count_nonzero(keep & (scores == gold_score))) - 1
    return 1.0 / (1.0 + better + 0.5 * tied_others)
