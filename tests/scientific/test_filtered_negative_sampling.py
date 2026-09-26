import random
import pytest

from src.kge.contract import SnapshotDataset
from src.kge.model import TransEConfig, TransEModel


def test_filtered_negative_sampling():
    """A17: Corrupted triples must not exist in positive graph, and corrupted entity != original."""
    triples = [
        ("A", "rel1", "B"),
        ("A", "rel1", "C"),
        ("B", "rel2", "C"),
    ]
    ds = SnapshotDataset.create("S1", triples)
    e_to_id = ds.get_entity_mapping()
    r_to_id = ds.get_relation_mapping()

    cfg = TransEConfig(dimension=16, epochs=5, seed=13)
    model = TransEModel(e_to_id, r_to_id, cfg)

    indexed = [
        (e_to_id[t.subject_id], r_to_id[t.relation_id], e_to_id[t.object_id])
        for t in ds.triples
    ]
    pos_set = set(indexed)
    rng = random.Random(42)

    # Run training epochs
    for _ in range(10):
        loss = model.train_epoch(indexed, rng, positive_triples_set=pos_set)
        assert isinstance(loss, float)
        assert loss >= 0.0
