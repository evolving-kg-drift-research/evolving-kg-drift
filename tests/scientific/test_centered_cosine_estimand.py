import math
import pytest

from src.drift.anchors import deterministic_hash_split
from src.drift.procrustes import (
    align_embeddings_procrustes,
    compute_orthogonality_error,
)
from src.kge.math_utils import one_minus_cosine


def test_centered_cosine_invariance_to_target_translation():
    """A19: Centered Procrustes drift estimand must measure 1 - cos((x - mu_s)Q, y - mu_t).

    Adding an arbitrary translation shift to target embeddings should NOT alter
    the centered cosine displacement between (x - mu_s)Q and y - mu_t.
    """
    dimension = 4
    entity_ids = [f"E_{i}" for i in range(10)]

    # Source embeddings centered around origin with some spread
    source_embeddings = {
        f"E_{i}": [float(i + 1), float((i + 1) ** 2 % 5), float(i - 2), 1.0]
        for i in range(10)
    }

    # Target 1: Identity rotation + shift T1
    shift_1 = [10.0, -5.0, 3.0, 20.0]
    target_embeddings_1 = {
        e: [source_embeddings[e][j] + shift_1[j] for j in range(dimension)]
        for e in entity_ids
    }

    # Target 2: Same points + massive shift T2 = shift_1 + 1000.0
    shift_2 = [s + 1000.0 for s in shift_1]
    target_embeddings_2 = {
        e: [source_embeddings[e][j] + shift_2[j] for j in range(dimension)]
        for e in entity_ids
    }

    split = deterministic_hash_split(entity_ids, fit_ratio=0.6, salt="a19_test")

    res_1 = align_embeddings_procrustes(source_embeddings, target_embeddings_1, split)
    res_2 = align_embeddings_procrustes(source_embeddings, target_embeddings_2, split)

    # Both should have zero orthogonality error
    assert compute_orthogonality_error(res_1.Q) < 1e-10
    assert compute_orthogonality_error(res_2.Q) < 1e-10

    # Under centered alignment, displacements for all entities must match exactly between T1 and T2
    for e in entity_ids:
        c_aligned_1 = res_1.align_entity_vector_centered(source_embeddings[e])
        c_target_1 = res_1.center_target_vector(target_embeddings_1[e])
        disp_1 = one_minus_cosine(c_aligned_1, c_target_1)

        c_aligned_2 = res_2.align_entity_vector_centered(source_embeddings[e])
        c_target_2 = res_2.center_target_vector(target_embeddings_2[e])
        disp_2 = one_minus_cosine(c_aligned_2, c_target_2)

        # Both centered displacements should be identical (and near 0 since target is pure translation)
        assert abs(disp_1 - disp_2) < 1e-10
        assert disp_1 < 1e-10
        assert disp_2 < 1e-10

        # Contrast with uncentered translated cosine:
        # 1 - cos(x' + mu_t, y) is heavily distorted by adding 1000.0 to all coords!
        uncentered_1 = res_1.align_entity_vector(source_embeddings[e])
        uncentered_2 = res_2.align_entity_vector(source_embeddings[e])
        raw_disp_unc_1 = one_minus_cosine(uncentered_1, target_embeddings_1[e])
        raw_disp_unc_2 = one_minus_cosine(uncentered_2, target_embeddings_2[e])
        # If target points are shifted by 1000, uncentered cosine distance shrinks toward 0 due to dominant mean
        # but centered cosine accurately compares relative orientations in the centered manifold.
