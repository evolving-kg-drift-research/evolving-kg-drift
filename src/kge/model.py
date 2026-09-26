"""TransE-L2 Knowledge Graph Embedding Model.

Implements the TransE model with L2 distance scoring:
    E(h, r, o) = ||h + r - o||_2

Adheres strictly to the scientific constraints:
  - Model: TransE
  - Norm: L2
  - Seeds: 13, 37, 101
  - Dimension: 32 or 64
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from .contract import SnapshotDataset, Triple
from .math_utils import l2_distance, l2_norm, normalize_vector


@dataclass
class TransEConfig:
    """Configuration for TransE-L2 training."""

    dimension: int = 32
    norm: int = 2
    margin: float = 1.0
    learning_rate: float = 0.01
    epochs: int = 50
    batch_size: int = 32
    seed: int = 13
    normalize_entities: bool = True


class TransEModel:
    """TransE-L2 model holding entity and relation embedding tables."""

    def __init__(
        self,
        entity_to_id: dict[str, int],
        relation_to_id: dict[str, int],
        config: TransEConfig,
    ) -> None:
        self.entity_to_id = dict(entity_to_id)
        self.relation_to_id = dict(relation_to_id)
        self.id_to_entity = {idx: e for e, idx in self.entity_to_id.items()}
        self.id_to_relation = {idx: r for r, idx in self.relation_to_id.items()}
        self.config = config
        self.num_entities = len(entity_to_id)
        self.num_relations = len(relation_to_id)
        self.dimension = config.dimension

        # Deterministic initialization based on seed
        self.entity_embeddings: list[list[float]] = []
        self.relation_embeddings: list[list[float]] = []
        self._init_embeddings()

    def _init_embeddings(self) -> None:
        """Initializes embeddings using uniform bounds ±6/sqrt(d) following Bordes et al. (2013).

        Note: This is the TransE-specific initialization (not standard Glorot).
        Embeddings are subsequently L2-normalized when normalize_entities is True.
        """
        rng = random.Random(self.config.seed)
        bound = 6.0 / math.sqrt(self.dimension)

        self.entity_embeddings = [
            [rng.uniform(-bound, bound) for _ in range(self.dimension)]
            for _ in range(self.num_entities)
        ]
        if self.config.normalize_entities:
            self.entity_embeddings = [
                normalize_vector(vec) for vec in self.entity_embeddings
            ]

        self.relation_embeddings = [
            [rng.uniform(-bound, bound) for _ in range(self.dimension)]
            for _ in range(self.num_relations)
        ]
        # Relations normalized as per Bordes et al.
        self.relation_embeddings = [
            normalize_vector(vec) for vec in self.relation_embeddings
        ]

    def score_triple(self, h_idx: int, r_idx: int, o_idx: int) -> float:
        """Computes TransE-L2 energy: ||h + r - o||_2."""
        h = self.entity_embeddings[h_idx]
        r = self.relation_embeddings[r_idx]
        o = self.entity_embeddings[o_idx]
        diff = [h[i] + r[i] - o[i] for i in range(self.dimension)]
        return l2_norm(diff)

    def get_entity_embedding(self, entity_id: str) -> list[float]:
        """Returns embedding vector for the given entity ID."""
        if entity_id not in self.entity_to_id:
            raise KeyError(f"Entity '{entity_id}' not found in model mapping.")
        return list(self.entity_embeddings[self.entity_to_id[entity_id]])

    def get_relation_embedding(self, relation_id: str) -> list[float]:
        """Returns embedding vector for the given relation ID."""
        if relation_id not in self.relation_to_id:
            raise KeyError(f"Relation '{relation_id}' not found in model mapping.")
        return list(self.relation_embeddings[self.relation_to_id[relation_id]])

    def get_all_entity_embeddings(self) -> dict[str, list[float]]:
        """Returns map of entity_id -> embedding vector."""
        return {e: self.get_entity_embedding(e) for e in self.entity_to_id}

    def get_all_relation_embeddings(self) -> dict[str, list[float]]:
        """Returns map of relation_id -> embedding vector."""
        return {r: self.get_relation_embedding(r) for r in self.relation_to_id}

    def train_epoch(
        self,
        indexed_triples: Sequence[tuple[int, int, int]],
        rng: random.Random,
        positive_triples_set: set[tuple[int, int, int]] | None = None,
    ) -> float:
        """Trains one epoch using stochastic gradient descent with margin-ranking loss."""
        total_loss = 0.0
        shuffled = list(indexed_triples)
        rng.shuffle(shuffled)

        if positive_triples_set is None:
            positive_triples_set = set(indexed_triples)

        lr = self.config.learning_rate
        margin = self.config.margin
        d = self.dimension
        n_ents = self.num_entities

        for h_idx, r_idx, o_idx in shuffled:
            # Filtered negative sampling (A17):
            # Candidate corrupted entity must not equal original entity,
            # and corrupted triple must not exist in positive graph.
            corrupt_head = rng.random() < 0.5
            max_attempts = 100
            corrupt_h = h_idx
            corrupt_o = o_idx

            if corrupt_head:
                for _ in range(max_attempts):
                    cand_h = rng.randint(0, n_ents - 1)
                    if cand_h != h_idx and (cand_h, r_idx, o_idx) not in positive_triples_set:
                        corrupt_h = cand_h
                        break
            else:
                for _ in range(max_attempts):
                    cand_o = rng.randint(0, n_ents - 1)
                    if cand_o != o_idx and (h_idx, r_idx, cand_o) not in positive_triples_set:
                        corrupt_o = cand_o
                        break

            # If no valid negative sample found, skip this triple
            if corrupt_h == h_idx and corrupt_o == o_idx:
                continue

            pos_diff = [
                self.entity_embeddings[h_idx][i] + self.relation_embeddings[r_idx][i] - self.entity_embeddings[o_idx][i]
                for i in range(d)
            ]
            pos_dist = l2_norm(pos_diff)

            neg_diff = [
                self.entity_embeddings[corrupt_h][i] + self.relation_embeddings[r_idx][i] - self.entity_embeddings[corrupt_o][i]
                for i in range(d)
            ]
            neg_dist = l2_norm(neg_diff)

            loss = margin + pos_dist - neg_dist
            if loss > 0.0:
                total_loss += loss

                # Gradient step: d(dist)/dx = diff / dist
                eps = 1e-12
                pos_grad_factor = 1.0 / max(pos_dist, eps)
                neg_grad_factor = 1.0 / max(neg_dist, eps)

                # Positive gradients:
                # dL/dh_pos = pos_diff / pos_dist
                # dL/dr = pos_diff / pos_dist - neg_diff / neg_dist
                # dL/do_pos = -pos_diff / pos_dist
                for i in range(d):
                    pos_g = pos_diff[i] * pos_grad_factor
                    neg_g = neg_diff[i] * neg_grad_factor

                    # Update relation
                    self.relation_embeddings[r_idx][i] -= lr * (pos_g - neg_g)

                    # Update entities
                    if corrupt_head:
                        self.entity_embeddings[h_idx][i] -= lr * pos_g
                        self.entity_embeddings[corrupt_h][i] += lr * neg_g
                        self.entity_embeddings[o_idx][i] += lr * pos_g
                        self.entity_embeddings[corrupt_o][i] -= lr * neg_g
                    else:
                        self.entity_embeddings[h_idx][i] -= lr * (pos_g - neg_g)
                        self.entity_embeddings[o_idx][i] += lr * pos_g
                        self.entity_embeddings[corrupt_o][i] -= lr * neg_g

                # Re-normalize updated entity vectors if configured
                if self.config.normalize_entities:
                    self.entity_embeddings[h_idx] = normalize_vector(self.entity_embeddings[h_idx])
                    self.entity_embeddings[o_idx] = normalize_vector(self.entity_embeddings[o_idx])
                    if corrupt_head:
                        self.entity_embeddings[corrupt_h] = normalize_vector(self.entity_embeddings[corrupt_h])
                    else:
                        self.entity_embeddings[corrupt_o] = normalize_vector(self.entity_embeddings[corrupt_o])

        return total_loss / max(1, len(shuffled))

    def evaluate_loss(
        self,
        indexed_triples: Sequence[tuple[int, int, int]],
        rng: random.Random,
        positive_triples_set: set[tuple[int, int, int]] | None = None,
    ) -> float:
        """Evaluates margin-ranking loss on validation triples without performing gradient updates."""
        if not indexed_triples:
            return 0.0

        if positive_triples_set is None:
            positive_triples_set = set(indexed_triples)

        margin = self.config.margin
        d = self.dimension
        n_ents = self.num_entities
        total_loss = 0.0
        eval_count = 0

        for h_idx, r_idx, o_idx in indexed_triples:
            corrupt_head = rng.random() < 0.5
            max_attempts = 100
            corrupt_h = h_idx
            corrupt_o = o_idx

            if corrupt_head:
                for _ in range(max_attempts):
                    cand_h = rng.randint(0, n_ents - 1)
                    if cand_h != h_idx and (cand_h, r_idx, o_idx) not in positive_triples_set:
                        corrupt_h = cand_h
                        break
            else:
                for _ in range(max_attempts):
                    cand_o = rng.randint(0, n_ents - 1)
                    if cand_o != o_idx and (h_idx, r_idx, cand_o) not in positive_triples_set:
                        corrupt_o = cand_o
                        break

            if corrupt_h == h_idx and corrupt_o == o_idx:
                continue

            pos_diff = [
                self.entity_embeddings[h_idx][i] + self.relation_embeddings[r_idx][i] - self.entity_embeddings[o_idx][i]
                for i in range(d)
            ]
            pos_dist = l2_norm(pos_diff)

            neg_diff = [
                self.entity_embeddings[corrupt_h][i] + self.relation_embeddings[r_idx][i] - self.entity_embeddings[corrupt_o][i]
                for i in range(d)
            ]
            neg_dist = l2_norm(neg_diff)

            loss = max(0.0, margin + pos_dist - neg_dist)
            total_loss += loss
            eval_count += 1

        return total_loss / max(1, eval_count)
