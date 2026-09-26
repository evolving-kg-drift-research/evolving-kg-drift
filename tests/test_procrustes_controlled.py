"""Controlled mathematical tests for Centered Orthogonal Procrustes alignment.

Verifies:
  1. Recovery of known orthogonal rotation R (Y = X R).
  2. Orthogonality: Q^T Q ~ I.
  3. Cosine displacement ~ 0 after alignment.
  4. Disjointness and determinism of anchor fit / holdout split.
"""

import math
import random

from src.drift.anchors import AnchorSplit, deterministic_hash_split, select_persistent_anchors
from src.drift.procrustes import align_embeddings_procrustes, compute_orthogonality_error
from src.kge.math_utils import one_minus_cosine


def generate_known_rotation_2d_blocks(dimension: int, angle: float = 0.785398) -> list[list[float]]:
    """Constructs a block-diagonal orthogonal rotation matrix in R^d."""
    R = [[1.0 if i == j else 0.0 for j in range(dimension)] for i in range(dimension)]
    c = math.cos(angle)
    s = math.sin(angle)
    for i in range(0, dimension - 1, 2):
        R[i][i] = c
        R[i][i + 1] = -s
        R[i + 1][i] = s
        R[i + 1][i + 1] = c
    return R


def test_anchor_split_disjoint_and_deterministic():
    entities = [f"entity_{i:03d}" for i in range(20)]
    split1 = deterministic_hash_split(entities, fit_ratio=0.6, salt="test_salt")
    split2 = deterministic_hash_split(entities, fit_ratio=0.6, salt="test_salt")

    # Disjointness
    split1.verify_disjoint()
    assert len(set(split1.fit_anchors).intersection(set(split1.holdout_anchors))) == 0

    # Determinism
    assert split1.fit_anchors == split2.fit_anchors
    assert split1.holdout_anchors == split2.holdout_anchors
    assert split1.fit_hash == split2.fit_hash
    assert split1.holdout_hash == split2.holdout_hash


def test_known_orthogonal_rotation_recovery():
    """Mathematical controlled test: X -> Y = X @ R."""
    dimension = 8
    num_entities = 16
    rng = random.Random(42)

    # 1. Create known orthogonal rotation matrix R
    R = generate_known_rotation_2d_blocks(dimension, angle=0.523598)  # 30 degrees
    err_R = compute_orthogonality_error(R)
    assert err_R < 1e-12

    # 2. Create synthetic entity points X
    source_embeddings = {}
    target_embeddings = {}
    entity_ids = [f"E_{i:02d}" for i in range(num_entities)]

    translation = [rng.uniform(-1.0, 1.0) for _ in range(dimension)]

    for e in entity_ids:
        x = [rng.uniform(-2.0, 2.0) for _ in range(dimension)]
        source_embeddings[e] = x
        # y = x @ R + translation
        y = [
            sum(x[i] * R[i][j] for i in range(dimension)) + translation[j]
            for j in range(dimension)
        ]
        target_embeddings[e] = y

    # 3. Split anchors into fit and holdout
    anchor_split = deterministic_hash_split(entity_ids, fit_ratio=0.6, salt="controlled_rot")

    # 4. Perform alignment
    result = align_embeddings_procrustes(
        source_embeddings,
        target_embeddings,
        anchor_split,
        alignment_type="cross_time",
    )

    # 5. Check orthogonality of Q
    assert result.diagnostics.orthogonality_error < 1e-10

    # 6. Check fit and holdout residuals are near zero
    assert result.diagnostics.fit_residual < 1e-7
    assert result.diagnostics.holdout_residual < 1e-7
    assert result.diagnostics.fit_holdout_gap < 1e-7

    # 7. Check 1 - cos(aligned(x), y) ~ 0 for ALL entities
    aligned_all = result.align_all_entities(source_embeddings)
    for e in entity_ids:
        cos_disp = one_minus_cosine(aligned_all[e], target_embeddings[e])
        assert cos_disp < 1e-7, f"Entity {e} had non-zero cosine displacement: {cos_disp}"


def test_identical_embeddings_give_identity_alignment():
    """If source and target embeddings are identical, Q should be identity and displacement 0."""
    dimension = 4
    num_entities = 10
    rng = random.Random(123)

    embeddings = {
        f"E_{i}": [rng.uniform(-1.0, 1.0) for _ in range(dimension)]
        for i in range(num_entities)
    }

    anchor_split = deterministic_hash_split(list(embeddings.keys()), fit_ratio=0.7)
    result = align_embeddings_procrustes(
        embeddings,
        embeddings,
        anchor_split,
        alignment_type="cross_time",
    )

    assert result.diagnostics.fit_residual < 1e-10
    assert result.diagnostics.holdout_residual < 1e-10

    aligned = result.align_all_entities(embeddings)
    for e in embeddings:
        disp = one_minus_cosine(aligned[e], embeddings[e])
        assert disp < 1e-10
