"""Independent numerical and controlled-sampling checks; synthetic fixtures only."""
from __future__ import annotations

import copy
import math
import random

import pytest

from src.kge.model import TransEConfig, TransEModel


class ControlledRandom(random.Random):
    def __init__(self, head: bool, choices: list[int]) -> None:
        super().__init__(13)
        self.head = head
        self.choices = choices
        self.calls = 0

    def shuffle(self, x: list[tuple[int, int, int]]) -> None:
        pass

    def random(self) -> float:
        return 0.0 if self.head else 0.9

    def randint(self, a: int, b: int) -> int:
        value = self.choices[min(self.calls, len(self.choices) - 1)]
        self.calls += 1
        assert a <= value <= b
        return value


def fixture_model() -> TransEModel:
    model = TransEModel({"a": 0, "b": 1, "c": 2, "d": 3}, {"r": 0},
                       TransEConfig(dimension=2, margin=10, learning_rate=0.01,
                                    normalize_entities=False, seed=13))
    model.entity_embeddings = [[0.2, -0.3], [0.8, 0.4], [-0.7, 0.6], [0.5, -0.9]]
    model.relation_embeddings = [[0.3, 0.2]]
    return model


def objective(model: TransEModel, positive: tuple[int, int, int], negative: tuple[int, int, int]) -> float:
    def energy(row: tuple[int, int, int]) -> float:
        h, r, t = row
        return math.sqrt(sum((a+b-c)**2 for a, b, c in zip(
            model.entity_embeddings[h], model.relation_embeddings[r], model.entity_embeddings[t])))
    return max(0.0, model.config.margin + energy(positive) - energy(negative))


@pytest.mark.parametrize("head,candidate,positive", [
    (True, 2, (0, 0, 1)), (False, 2, (0, 0, 1)),
    (True, 1, (0, 0, 1)), (False, 0, (0, 0, 1)),
    (True, 2, (0, 0, 0)), (False, 2, (0, 0, 0)),
])
def test_sgd_matches_numerical_gradient_including_shared_entities(
    head: bool, candidate: int, positive: tuple[int, int, int],
) -> None:
    model = fixture_model()
    negative = (candidate, 0, positive[2]) if head else (positive[0], 0, candidate)
    before = copy.deepcopy(model)
    epsilon = 1e-6
    expected = copy.deepcopy(model)
    for name in ("entity_embeddings", "relation_embeddings"):
        matrix = getattr(before, name)
        for row in range(len(matrix)):
            for column in range(2):
                plus, minus = copy.deepcopy(before), copy.deepcopy(before)
                getattr(plus, name)[row][column] += epsilon
                getattr(minus, name)[row][column] -= epsilon
                gradient = (objective(plus, positive, negative) - objective(minus, positive, negative)) / (2 * epsilon)
                getattr(expected, name)[row][column] -= model.config.learning_rate * gradient
    observed = model.train_epoch([positive], ControlledRandom(head, [candidate]), {positive})
    assert observed == pytest.approx(objective(before, positive, negative))
    for name in ("entity_embeddings", "relation_embeddings"):
        for actual, wanted in zip(getattr(model, name), getattr(expected, name)):
            assert actual == pytest.approx(wanted, abs=1e-9)


@pytest.mark.parametrize("head", [True, False])
def test_sampler_rejects_original_and_known_positive_before_update(head: bool) -> None:
    positive = (0, 0, 1)
    original = 0 if head else 1
    known = (2, 0, 1) if head else (0, 0, 2)
    model, reference = fixture_model(), fixture_model()
    rng = ControlledRandom(head, [original, 2, 3])
    model.train_epoch([positive], rng, {positive, known})
    reference.train_epoch([positive], ControlledRandom(head, [3]), {positive, known})
    assert rng.calls == 3
    assert model.entity_embeddings == reference.entity_embeddings
    assert model.relation_embeddings == reference.relation_embeddings


@pytest.mark.parametrize("head", [True, False])
def test_saturated_corruption_side_skips_without_false_negative(head: bool) -> None:
    positive = (0, 0, 1)
    known = {(i, 0, 1) if head else (0, 0, i) for i in range(4)}
    model = fixture_model()
    before = copy.deepcopy(model)
    rng = ControlledRandom(head, [2])
    assert model.train_epoch([positive], rng, known) == 0
    assert rng.calls == 100
    assert model.entity_embeddings == before.entity_embeddings
    assert model.relation_embeddings == before.relation_embeddings


def test_inactive_hinge_leaves_weights_unchanged() -> None:
    model = fixture_model()
    model.config = TransEConfig(dimension=2, margin=1, normalize_entities=False)
    model.entity_embeddings = [[0.0, 0.0], [1.0, 0.0], [10.0, 0.0], [0.0, 10.0]]
    model.relation_embeddings = [[1.0, 0.0]]
    before = copy.deepcopy(model)
    assert model.train_epoch([(0, 0, 1)], ControlledRandom(False, [2])) == 0
    assert model.entity_embeddings == before.entity_embeddings
    assert model.relation_embeddings == before.relation_embeddings


@pytest.mark.parametrize("head", [True, False])
def test_retry_budget_can_skip_even_when_valid_negative_exists(head: bool) -> None:
    positive = (0, 0, 1)
    original = 0 if head else 1
    model = fixture_model()
    before = copy.deepcopy(model)
    # Controlled repeated draws make the rejection budget observable. This is
    # not an estimate of its probability under the production random sampler.
    rng = ControlledRandom(head, [original])
    assert model.train_epoch([positive], rng, {positive}) == 0
    assert rng.calls == 100
    assert model.entity_embeddings == before.entity_embeddings
    assert model.relation_embeddings == before.relation_embeddings
    reference = copy.deepcopy(before)
    assert reference.train_epoch([positive], ControlledRandom(head, [2]), {positive}) > 0
    assert reference.entity_embeddings != before.entity_embeddings


def test_self_loop_energy_is_relation_norm() -> None:
    model = fixture_model()
    expected = math.sqrt(sum(x*x for x in model.relation_embeddings[0]))
    for entity in range(4):
        assert model.score_triple(entity, 0, entity) == pytest.approx(expected)


def test_projection_and_evaluate_loss_do_not_mutate_unexpectedly() -> None:
    model = fixture_model()
    model.config = TransEConfig(dimension=2, margin=10, normalize_entities=True)
    positive = (0, 0, 1)
    model.train_epoch([positive], ControlledRandom(True, [2]))
    for index in (0, 1, 2):
        assert math.sqrt(sum(x*x for x in model.entity_embeddings[index])) == pytest.approx(1.0)
    before = copy.deepcopy(model)
    loss = model.evaluate_loss([positive], ControlledRandom(False, [3]))
    assert loss == pytest.approx(objective(before, positive, (0, 0, 3)))
    assert model.entity_embeddings == before.entity_embeddings
    assert model.relation_embeddings == before.relation_embeddings
