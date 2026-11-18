"""Synthetic checks for mini-batch TransE-L2 training."""
from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from kge.minibatch import MiniBatchTransE, margin_loss_and_grads


def _model(seed: int = 13, n_entities: int = 6, negative_sampling: str = "uniform") -> MiniBatchTransE:
    return MiniBatchTransE(
        {f"e{i}": i for i in range(n_entities)},
        {"r": 0},
        dimension=16,
        margin=1.0,
        learning_rate=0.05,
        seed=seed,
        batch_size=4,
        negative_sampling=negative_sampling,
    )


def _chain(n_entities: int = 6) -> NDArray[np.int64]:
    return np.array([(i, 0, i + 1) for i in range(n_entities - 1)], dtype=np.int64)


def test_margin_gradients_match_central_finite_differences() -> None:
    rng = np.random.default_rng(13)
    entity = rng.normal(size=(6, 4))
    relation = rng.normal(size=(2, 4))
    h = np.array([0, 0, 1, 2, 4], dtype=np.int64)
    r = np.array([0, 1, 0, 1, 0], dtype=np.int64)
    t = np.array([1, 2, 3, 4, 5], dtype=np.int64)
    nh = np.array([3, 4, 1, 0, 4], dtype=np.int64)
    nt = np.array([1, 2, 0, 4, 0], dtype=np.int64)
    margin = 20.0
    loss, grad_entity, grad_relation, n_active = margin_loss_and_grads(entity, relation, h, r, t, nh, nt, margin)
    assert loss > 0.0
    assert n_active == 5

    epsilon = 1e-6
    for parameter, gradient in ((entity, grad_entity), (relation, grad_relation)):
        numerical = np.zeros_like(parameter)
        for index in np.ndindex(parameter.shape):
            original = parameter[index]
            parameter[index] = original + epsilon
            plus = margin_loss_and_grads(entity, relation, h, r, t, nh, nt, margin)[0]
            parameter[index] = original - epsilon
            minus = margin_loss_and_grads(entity, relation, h, r, t, nh, nt, margin)[0]
            parameter[index] = original
            numerical[index] = (plus - minus) / (2 * epsilon)
        assert np.max(np.abs(gradient - numerical)) < 1e-5


def test_initialization_draw_order_normalization_and_exports() -> None:
    entity_to_id = {"e2": 2, "e0": 0, "e1": 1}
    relation_to_id = {"r1": 1, "r0": 0}
    model = MiniBatchTransE(entity_to_id, relation_to_id, dimension=4, margin=1.0, learning_rate=0.01, seed=13)
    rng = np.random.default_rng(13)
    expected_entity = rng.uniform(-3.0, 3.0, (3, 4))
    expected_entity /= np.linalg.norm(expected_entity, axis=1, keepdims=True)
    expected_relation = rng.uniform(-3.0, 3.0, (2, 4))
    expected_relation /= np.linalg.norm(expected_relation, axis=1, keepdims=True)
    np.testing.assert_array_equal(model.entity_embeddings, expected_entity)
    np.testing.assert_array_equal(model.relation_embeddings, expected_relation)
    assert model.entity_embeddings.dtype == np.float64
    assert model.relation_embeddings.dtype == np.float64
    assert model.dimension == 4
    assert model.entity_to_id == entity_to_id
    assert model.relation_to_id == relation_to_id
    assert model.get_all_entity_embeddings() == {
        name: expected_entity[index].tolist() for name, index in entity_to_id.items()
    }
    assert model.get_all_relation_embeddings() == {
        name: expected_relation[index].tolist() for name, index in relation_to_id.items()
    }


def test_same_seed_training_is_identical_and_different_seeds_diverge() -> None:
    triples = _chain()
    known = set(map(tuple, triples.tolist()))
    first, second, different = _model(), _model(), _model(seed=37)
    for _ in range(3):
        assert first.fit_epoch(triples, known) == second.fit_epoch(triples, known)
        different.fit_epoch(triples, known)
    np.testing.assert_array_equal(first.entity_embeddings, second.entity_embeddings)
    np.testing.assert_array_equal(first.relation_embeddings, second.relation_embeddings)
    assert not np.array_equal(first.entity_embeddings, different.entity_embeddings)
    assert not np.array_equal(first.relation_embeddings, different.relation_embeddings)


def test_fit_epoch_normalizes_all_touched_entity_rows() -> None:
    triples = _chain(4)
    model = _model(n_entities=4)
    model.fit_epoch(triples, set(map(tuple, triples.tolist())))
    np.testing.assert_allclose(np.linalg.norm(model.entity_embeddings, axis=1), 1.0, rtol=0.0, atol=1e-12)


def test_sample_negatives_filters_original_and_known_triples() -> None:
    triples = _chain()
    known = set(map(tuple, triples.tolist()))
    model = _model()
    for probability in (0.0, 0.5, 1.0):
        nh, nt, keep = model.sample_negatives(triples, known, np.array([probability]))
        assert nh.shape == nt.shape == keep.shape == (len(triples),)
        assert keep.dtype == np.bool_
        assert keep.all()
        for index in np.flatnonzero(keep):
            h, r, t = triples[index]
            negative = (int(nh[index]), int(r), int(nt[index]))
            assert negative != (h, r, t)
            assert negative not in known
            assert (nh[index] != h) != (nt[index] != t)
            assert 0 <= nh[index] < 6 and 0 <= nt[index] < 6
            if probability == 0.0:
                assert nh[index] == h
            elif probability == 1.0:
                assert nt[index] == t


def test_saturated_graph_drops_negatives_and_skips_adam() -> None:
    model = _model(n_entities=2)
    triples = np.array([(0, 0, 1)], dtype=np.int64)
    known = {(h, 0, t) for h in range(2) for t in range(2)}
    nh, nt, keep = model.sample_negatives(triples, known, np.array([0.5]))
    assert nh.shape == nt.shape == keep.shape == (1,)
    assert not keep.any()
    entity, relation = model.entity_embeddings.copy(), model.relation_embeddings.copy()
    assert model.fit_epoch(triples, known) == 0.0
    assert model.t == 0
    np.testing.assert_array_equal(model.entity_embeddings, entity)
    np.testing.assert_array_equal(model.relation_embeddings, relation)


def test_bernoulli_corrupts_heads_more_for_one_to_many_relations() -> None:
    triples = np.array([(0, 0, i) for i in range(1, 5)] + [(0, 0, 1)], dtype=np.int64)
    for sampling, expected in (("bernoulli", 0.8), ("uniform", 0.5)):
        model = MiniBatchTransE(
            {f"e{i}": i for i in range(5)},
            {"one_to_many": 0, "absent": 1},
            dimension=4,
            margin=1.0,
            learning_rate=0.01,
            seed=13,
            negative_sampling=sampling,
        )
        np.testing.assert_array_equal(model.head_corruption_probability(triples), [expected, 0.5])
        np.testing.assert_array_equal(model.head_corruption_probability(np.empty((0, 3), dtype=np.int64)), [0.5, 0.5])


def test_learning_reduces_chain_loss_by_more_than_half() -> None:
    triples = _chain(20)
    known = set(map(tuple, triples.tolist()))
    model = _model(n_entities=20)
    losses = [model.fit_epoch(triples, known) for _ in range(60)]
    assert np.isfinite(losses).all()
    assert losses[-1] < losses[0] * 0.5


def test_invalid_negative_sampling_raises_value_error() -> None:
    with np.testing.assert_raises(ValueError):
        _model(negative_sampling="invalid")


def test_constructor_rejects_nonpositive_training_parameters() -> None:
    for dimension, batch_size, margin, rate in (
        (0, 4, 1.0, 0.01),
        (-1, 4, 1.0, 0.01),
        (4, 0, 1.0, 0.01),
        (4, -1, 1.0, 0.01),
        (4, 4, 0.0, 0.01),
        (4, 4, -1.0, 0.01),
        (4, 4, 1.0, 0.0),
        (4, 4, 1.0, -0.01),
    ):
        with np.testing.assert_raises(ValueError):
            MiniBatchTransE(
                {"e": 0},
                {"r": 0},
                dimension=dimension,
                batch_size=batch_size,
                margin=margin,
                learning_rate=rate,
                seed=13,
            )


def test_empty_epoch_returns_zero_without_updating_parameters() -> None:
    model = _model()
    entity, relation = model.entity_embeddings.copy(), model.relation_embeddings.copy()
    assert model.fit_epoch(np.empty((0, 3), dtype=np.int64), set()) == 0.0
    assert model.t == 0
    np.testing.assert_array_equal(model.entity_embeddings, entity)
    np.testing.assert_array_equal(model.relation_embeddings, relation)


def test_zero_distances_and_inactive_hinges_have_finite_zero_gradients() -> None:
    entity = np.zeros((3, 2), dtype=np.float64)
    relation = np.zeros((1, 2), dtype=np.float64)
    h, r, t, nh, nt = (np.array([i], dtype=np.int64) for i in (0, 0, 1, 2, 1))
    loss, ge, gr, active = margin_loss_and_grads(entity, relation, h, r, t, nh, nt, 1.0)
    assert loss == 1.0 and active == 1
    np.testing.assert_array_equal(ge, np.zeros_like(entity))
    np.testing.assert_array_equal(gr, np.zeros_like(relation))
    entity[2] = [3.0, 4.0]
    loss, ge, gr, active = margin_loss_and_grads(entity, relation, h, r, t, nh, nt, 1.0)
    assert loss == 0.0 and active == 0
    np.testing.assert_array_equal(ge, np.zeros_like(entity))
    np.testing.assert_array_equal(gr, np.zeros_like(relation))


def test_all_entities_stay_on_unit_sphere_across_many_batches() -> None:
    """Dense Adam keeps moving rows absent from a batch; all rows must still be unit norm after the epoch."""
    entities = {f"e{i}": i for i in range(30)}
    triples = np.array([[i, 0, (i + 1) % 30] for i in range(30)], dtype=np.int64)
    model = MiniBatchTransE(entities, {"r": 0}, dimension=8, margin=1.0, learning_rate=0.05, seed=3, batch_size=4)
    known = {tuple(int(x) for x in row) for row in triples}
    for _ in range(3):
        model.fit_epoch(triples, known)
    assert np.allclose(np.linalg.norm(model.entity_embeddings, axis=1), 1.0)
