"""Tests for TransE-L2 model, multi-seed training, mapping parity, and checkpoint reload."""

import tempfile
from pathlib import Path

from src.kge.checkpoint import KGECheckpoint
from src.kge.fixtures import create_synthetic_snapshots
from src.kge.model import TransEConfig, TransEModel
from src.kge.trainer import train_multi_seed, train_single_seed


def test_transe_single_seed_finite_and_dimensions():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]

    cfg = TransEConfig(dimension=32, norm=2, epochs=5, seed=13)
    ckpt = train_single_seed(s1, cfg)

    # Check finite
    ckpt.verify_finite()

    # Check dimensions
    assert len(ckpt.entity_embeddings) == len(s1.entities)
    assert len(ckpt.relation_embeddings) == len(s1.relations)
    for e, vec in ckpt.entity_embeddings.items():
        assert len(vec) == 32
    for r, vec in ckpt.relation_embeddings.items():
        assert len(vec) == 32

    # Check provenance
    assert ckpt.provenance.snapshot_id == "S1"
    assert ckpt.provenance.seed == 13
    assert ckpt.provenance.model == "TransE"
    assert ckpt.provenance.dimension == 32
    assert ckpt.provenance.norm == 2
    assert len(ckpt.artifact_hash) == 64


def test_mapping_parity_across_seeds():
    """Invariant 10: mapping(seed13) == mapping(seed37) == mapping(seed101)."""
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]

    seeds = (13, 37, 101)
    runs = train_multi_seed(s1, seeds=seeds, dimension=32, epochs=3)

    assert set(runs.keys()) == {13, 37, 101}
    mapping_hash_13 = runs[13].provenance.entity_mapping_hash
    mapping_hash_37 = runs[37].provenance.entity_mapping_hash
    mapping_hash_101 = runs[101].provenance.entity_mapping_hash

    assert mapping_hash_13 == mapping_hash_37 == mapping_hash_101
    assert set(runs[13].entity_embeddings.keys()) == set(runs[37].entity_embeddings.keys())
    assert set(runs[13].entity_embeddings.keys()) == set(runs[101].entity_embeddings.keys())


def test_checkpoint_save_and_reload():
    fixtures = create_synthetic_snapshots()
    s1 = fixtures["S1"]

    cfg = TransEConfig(dimension=32, norm=2, epochs=3, seed=13)
    ckpt = train_single_seed(s1, cfg)

    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "ckpt_test.json"
        ckpt.save(save_path)

        loaded = KGECheckpoint.load(save_path)
        assert loaded.provenance.snapshot_id == ckpt.provenance.snapshot_id
        assert loaded.provenance.seed == ckpt.provenance.seed
        assert loaded.provenance.entity_mapping_hash == ckpt.provenance.entity_mapping_hash
        assert loaded.artifact_hash == ckpt.artifact_hash

        # Verify vector values match exactly
        for e in ckpt.entity_embeddings:
            assert loaded.get_entity_vector(e) == ckpt.get_entity_vector(e)
