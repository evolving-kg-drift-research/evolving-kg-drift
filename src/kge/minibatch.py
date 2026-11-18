"""Deterministic mini-batch Adam training for TransE with L2 distances."""
from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


def margin_loss_and_grads(
    entity: FloatArray,
    relation: FloatArray,
    h: IntArray,
    r: IntArray,
    t: IntArray,
    nh: IntArray,
    nt: IntArray,
    margin: float,
) -> tuple[float, FloatArray, FloatArray, int]:
    """Return summed hinge loss and accumulated, unaveraged table gradients."""
    pos = entity[h] + relation[r] - entity[t]
    neg = entity[nh] + relation[r] - entity[nt]
    dp = np.linalg.norm(pos, axis=1)
    dn = np.linalg.norm(neg, axis=1)
    hinge = np.maximum(0.0, margin + dp - dn)
    active = hinge > 0.0
    gp = pos[active] / np.maximum(dp[active, None], 1e-12)
    gn = neg[active] / np.maximum(dn[active, None], 1e-12)
    grad_entity = np.zeros_like(entity)
    grad_relation = np.zeros_like(relation)
    np.add.at(grad_entity, h[active], gp)
    np.add.at(grad_entity, t[active], -gp)
    np.add.at(grad_relation, r[active], gp - gn)
    np.add.at(grad_entity, nh[active], -gn)
    np.add.at(grad_entity, nt[active], gn)
    return float(hinge.sum()), grad_entity, grad_relation, int(np.count_nonzero(active))


class MiniBatchTransE:
    """TransE-L2 embedding tables trained with filtered negatives and dense Adam."""

    def __init__(
        self,
        entity_to_id: dict[str, int],
        relation_to_id: dict[str, int],
        *,
        dimension: int,
        margin: float,
        learning_rate: float,
        seed: int,
        batch_size: int = 128,
        negative_sampling: str = "uniform",
        beta1: float = 0.9,
        beta2: float = 0.999,
        eps: float = 1e-8,
    ) -> None:
        if negative_sampling not in ("uniform", "bernoulli"):
            raise ValueError("negative_sampling must be 'uniform' or 'bernoulli'")
        if dimension <= 0 or batch_size <= 0:
            raise ValueError("dimension and batch_size must be positive")
        if not margin > 0.0 or not learning_rate > 0.0:
            raise ValueError("margin and learning_rate must be positive")
        self.entity_to_id = dict(entity_to_id)
        self.relation_to_id = dict(relation_to_id)
        self.dimension = dimension
        self.margin = margin
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.negative_sampling = negative_sampling
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.rng = np.random.default_rng(seed)

        bound = 6.0 / math.sqrt(dimension)
        self.entity_embeddings = self.rng.uniform(-bound, bound, (len(entity_to_id), dimension))
        self.entity_embeddings /= np.linalg.norm(self.entity_embeddings, axis=1, keepdims=True)
        self.relation_embeddings = self.rng.uniform(-bound, bound, (len(relation_to_id), dimension))
        self.relation_embeddings /= np.linalg.norm(self.relation_embeddings, axis=1, keepdims=True)
        self.m_entity = np.zeros_like(self.entity_embeddings)
        self.v_entity = np.zeros_like(self.entity_embeddings)
        self.m_relation = np.zeros_like(self.relation_embeddings)
        self.v_relation = np.zeros_like(self.relation_embeddings)
        self.t = 0

    def get_all_entity_embeddings(self) -> dict[str, list[float]]:
        """Return entity vectors keyed by their external identifiers."""
        return {name: self.entity_embeddings[index].tolist() for name, index in self.entity_to_id.items()}

    def get_all_relation_embeddings(self) -> dict[str, list[float]]:
        """Return relation vectors keyed by their external identifiers."""
        return {name: self.relation_embeddings[index].tolist() for name, index in self.relation_to_id.items()}

    def head_corruption_probability(self, triples: IntArray) -> FloatArray:
        """Compute uniform or relation-specific Bernoulli head probabilities."""
        probabilities = np.full(len(self.relation_to_id), 0.5, dtype=np.float64)
        if self.negative_sampling == "bernoulli":
            for relation_id in np.unique(triples[:, 1]):
                pairs = np.unique(triples[triples[:, 1] == relation_id][:, [0, 2]], axis=0)
                tph = len(pairs) / len(np.unique(pairs[:, 0]))
                hpt = len(pairs) / len(np.unique(pairs[:, 1]))
                probabilities[relation_id] = tph / (tph + hpt)
        return probabilities

    def sample_negatives(
        self,
        batch: IntArray,
        known: set[tuple[int, int, int]],
        p_head: FloatArray,
    ) -> tuple[IntArray, IntArray, BoolArray]:
        """Sample one filtered corruption per row, dropping exhausted rows."""
        neg_heads = batch[:, 0].copy()
        neg_tails = batch[:, 2].copy()
        keep_mask = np.zeros(len(batch), dtype=np.bool_)
        for index, (head, relation, tail) in enumerate(batch):
            corrupt_head = self.rng.random() < p_head[relation]
            original = head if corrupt_head else tail
            for _ in range(100):
                replacement = self.rng.integers(0, len(self.entity_to_id))
                if replacement == original:
                    continue
                neg_head = replacement if corrupt_head else head
                neg_tail = tail if corrupt_head else replacement
                if (neg_head, relation, neg_tail) in known:
                    continue
                neg_heads[index] = neg_head
                neg_tails[index] = neg_tail
                keep_mask[index] = True
                break
        return neg_heads, neg_tails, keep_mask

    def fit_epoch(self, triples: IntArray, known: set[tuple[int, int, int]]) -> float:
        """Train one shuffled epoch and return mean hinge loss over valid rows."""
        p_head = self.head_corruption_probability(triples)
        order = self.rng.permutation(len(triples))
        total_loss = 0.0
        total_valid = 0
        for start in range(0, len(triples), self.batch_size):
            batch = triples[order[start : start + self.batch_size]]
            neg_heads, neg_tails, keep = self.sample_negatives(batch, known, p_head)
            n_valid = int(np.count_nonzero(keep))
            if n_valid == 0:
                continue
            h, r, t = batch[keep].T
            nh, nt = neg_heads[keep], neg_tails[keep]
            loss, grad_entity, grad_relation, _ = margin_loss_and_grads(
                self.entity_embeddings, self.relation_embeddings, h, r, t, nh, nt, self.margin
            )
            grad_entity /= n_valid
            grad_relation /= n_valid
            self.t += 1
            for parameter, m, v, gradient in (
                (self.entity_embeddings, self.m_entity, self.v_entity, grad_entity),
                (self.relation_embeddings, self.m_relation, self.v_relation, grad_relation),
            ):
                m *= self.beta1
                m += (1.0 - self.beta1) * gradient
                v *= self.beta2
                v += (1.0 - self.beta2) * gradient**2
                m_hat = m / (1.0 - self.beta1**self.t)
                v_hat = v / (1.0 - self.beta2**self.t)
                parameter -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.eps)
            # Dense Adam moves every row through momentum, so project ALL entity rows back to the unit sphere.
            norms = np.linalg.norm(self.entity_embeddings, axis=1, keepdims=True)
            self.entity_embeddings /= np.maximum(norms, 1e-12)
            total_loss += loss
            total_valid += n_valid
        return total_loss / total_valid if total_valid else 0.0
