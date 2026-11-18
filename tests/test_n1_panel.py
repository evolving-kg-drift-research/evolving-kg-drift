"""Hand-checked path selection and filtered ranking examples for the N1 panel."""
from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from evaluation.n1_panel import (
    Triple,
    cap_per_head,
    eligible_paths,
    path_answers,
    path_relations,
    reciprocal_rank_path,
    support_entities,
)


@pytest.mark.parametrize("eligible", [{"a", "c"}, {"a", "b"}, {"b", "c"}])
def test_eligible_paths_requires_every_entity(eligible: set[str]) -> None:
    triples = [("a", "r", "b"), ("b", "s", "c")]
    assert eligible_paths(triples, {"a", "b", "c"}) == {2: [("a", "r", "b", "s", "c")], 3: []}
    assert eligible_paths(triples, eligible) == {2: [], 3: []}


@pytest.mark.parametrize("shortcut", [("a", "unrelated", "c"), ("c", "unrelated", "a")])
def test_eligible_paths_rejects_shortcuts_in_either_direction(shortcut: Triple) -> None:
    triples = [("a", "r", "b"), ("b", "s", "c"), shortcut]
    assert eligible_paths(triples, {"a", "b", "c"}, hops=(2,)) == {2: []}


def test_eligible_paths_rejects_three_hop_reverse_shortcut() -> None:
    triples = [("a", "r", "b"), ("b", "s", "c"), ("c", "t", "d"), ("d", "other", "a")]
    assert eligible_paths(triples, {"a", "b", "c", "d"}, hops=(3,)) == {3: []}


@pytest.mark.parametrize(
    ("triples", "hop"),
    [
        ([("a", "r", "b"), ("b", "s", "a")], 2),
        ([("a", "r", "b"), ("b", "s", "c"), ("c", "t", "a")], 3),
        ([("a", "r", "a"), ("a", "s", "b"), ("b", "t", "c")], 3),
    ],
)
def test_eligible_paths_rejects_repeated_entities(triples: list[Triple], hop: int) -> None:
    assert eligible_paths(triples, {"a", "b", "c"}, hops=(hop,)) == {hop: []}


@pytest.mark.parametrize("hops", [(2,), (3,), (3, 2), ()])
def test_eligible_paths_keeps_requested_empty_keys(hops: tuple[int, ...]) -> None:
    assert eligible_paths([], {"a"}, hops=hops) == {hop: [] for hop in hops}


def test_eligible_paths_distinguishes_parallel_relations_and_deduplicates_triples() -> None:
    triples = [("a", "r", "b"), ("a", "p", "b"), ("b", "s", "c"), ("a", "r", "b")]
    assert eligible_paths(triples, {"a", "b", "c"}) == {
        2: [("a", "p", "b", "s", "c"), ("a", "r", "b", "s", "c")],
        3: [],
    }


def test_eligible_paths_finds_sorted_directed_two_and_three_hop_paths() -> None:
    triples = [("c", "t", "d"), ("b", "s", "c"), ("a", "r", "b")]
    expected = {
        2: [("a", "r", "b", "s", "c"), ("b", "s", "c", "t", "d")],
        3: [("a", "r", "b", "s", "c", "t", "d")],
    }
    assert eligible_paths(triples, {"d", "c", "b", "a"}) == expected
    assert eligible_paths(list(reversed(triples)), {"a", "b", "c", "d"}, hops=(3, 2)) == expected


def test_eligible_paths_rejects_unsupported_hops() -> None:
    with pytest.raises(ValueError):
        eligible_paths([], set(), hops=(2, 4))


def test_cap_per_head_respects_cap_hash_order_and_small_groups() -> None:
    paths = [("a", f"r{i}", f"m{i}", "s", f"z{i}") for i in range(6)]
    short_group = ("b", "r", "n", "s", "u")
    inputs = paths + [short_group]
    kept = cap_per_head(inputs, cap=2)
    assert kept == [paths[1], paths[2], short_group]
    assert Counter(path[0] for path in kept) == {"a": 2, "b": 1}
    assert cap_per_head(list(reversed(inputs)), cap=2) == kept
    assert cap_per_head(inputs, cap=2, salt="alternate") == [paths[0], paths[4], short_group]
    assert cap_per_head(inputs, cap=10) == sorted(inputs)
    assert cap_per_head([], cap=1) == []


@pytest.mark.parametrize("cap", [0, -1])
def test_cap_per_head_rejects_nonpositive_cap(cap: int) -> None:
    with pytest.raises(ValueError):
        cap_per_head([], cap=cap)


@pytest.mark.parametrize(
    ("path", "entities", "relations"),
    [
        (("z", "r2", "b", "r1", "a"), ("z", "b", "a"), ("r2", "r1")),
        (("z", "r2", "b", "r1", "a", "r3", "c"), ("z", "b", "a", "c"), ("r2", "r1", "r3")),
        (("z", "r2", "b", "r1", "z", "r2", "a"), ("z", "b", "a"), ("r2", "r1", "r2")),
    ],
)
def test_support_entities_and_path_relations_preserve_order(
    path: tuple[str, ...], entities: tuple[str, ...], relations: tuple[str, ...]
) -> None:
    assert support_entities(path) == entities
    assert path_relations(path) == relations


def test_path_answers_follows_exact_relation_order_and_collects_all_answers() -> None:
    triples = [
        ("a", "r", "b"),
        ("a", "r", "c"),
        ("b", "s", "d"),
        ("c", "s", "d"),
        ("c", "s", "e"),
        ("a", "s", "z"),
        ("z", "r", "x"),
    ]
    assert path_answers(triples, "a", ("r", "s")) == {"d", "e"}
    assert path_answers(triples, "a", ("s", "r")) == {"x"}
    assert path_answers(triples, "a", ("r", "r")) == set()
    assert path_answers(triples, "a", ("missing",)) == set()
    assert path_answers(triples, "d", ("s",)) == set()


def test_path_answers_allows_revisits_and_zero_hops() -> None:
    triples = [("a", "r", "b"), ("b", "s", "a"), ("a", "t", "c")]
    assert path_answers(triples, "a", ("r", "s", "t")) == {"c"}
    assert path_answers(triples, "a", ()) == {"a"}


def test_reciprocal_rank_path_perfect_embedding_and_no_input_mutation() -> None:
    entity = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 2.0], [3.0, 3.0]])
    relation = np.array([[1.0, 0.0], [0.0, 2.0]])
    original_entity = entity.copy()
    original_relation = relation.copy()
    rank = reciprocal_rank_path(
        entity, relation, {"head": 0, "bridge": 1, "gold": 2, "far": 3}, {"r": 0, "s": 1},
        "head", ("r", "s"), "gold", (),
    )
    assert rank == 1.0
    np.testing.assert_array_equal(entity, original_entity)
    np.testing.assert_array_equal(relation, original_relation)


@pytest.mark.parametrize(
    ("others", "expected"),
    [((), 0.5), (("true",), 1.0), (("gold",), 0.5), (("true", "gold"), 1.0)],
)
def test_reciprocal_rank_path_filters_other_answers_but_keeps_gold(
    others: tuple[str, ...], expected: float
) -> None:
    entity = np.array([[0.0, 0.0], [2.0, 1.0], [2.0, 0.0], [9.0, 9.0]])
    relation = np.array([[1.0, 0.0]])
    assert reciprocal_rank_path(
        entity, relation, {"head": 0, "gold": 1, "true": 2, "far": 3}, {"r": 0},
        "head", ("r", "r"), "gold", others,
    ) == expected


def test_reciprocal_rank_path_uses_half_credit_for_exact_ties() -> None:
    entity = np.array([[0.0, 0.0], [2.0, 1.0], [2.0, -1.0], [2.0, 0.0]])
    relation = np.array([[2.0, 0.0]])
    e2i = {"head": 0, "gold": 1, "tie": 2, "closer": 3}
    assert reciprocal_rank_path(entity, relation, e2i, {"r": 0}, "head", ("r",), "gold", ()) == 0.4
    assert reciprocal_rank_path(
        entity, relation, e2i, {"r": 0}, "head", ("r",), "gold", ("closer",)
    ) == pytest.approx(2.0 / 3.0)


def test_reciprocal_rank_path_does_not_treat_near_ties_as_exact() -> None:
    entity = np.array([[0.0, 0.0], [2.0, 1.0], [2.0, -1.0000000001]])
    relation = np.array([[2.0, 0.0]])
    assert reciprocal_rank_path(
        entity, relation, {"head": 0, "gold": 1, "near": 2}, {"r": 0}, "head", ("r",), "gold", ()
    ) == 1.0


def test_reciprocal_rank_path_ranks_every_embedding_row() -> None:
    entity = np.array([[0.0, 0.0], [2.0, 1.0], [2.0, 0.0]])
    relation = np.array([[2.0, 0.0]])
    assert reciprocal_rank_path(
        entity, relation, {"head": 0, "gold": 1}, {"r": 0}, "head", ("r",), "gold", ()
    ) == 0.5
