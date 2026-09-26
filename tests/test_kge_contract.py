"""Tests for KGE Input Contract and mapping invariants."""

import pytest
from src.kge.contract import SnapshotDataset


def test_snapshot_dataset_creation_and_canonical_sorting():
    raw_triples = [
        ("entity_c", "rel_x", "entity_a"),
        ("entity_a", "rel_x", "entity_b"),
        ("entity_b", "rel_y", "entity_c"),
    ]
    ds = SnapshotDataset.create("S1", raw_triples)

    assert ds.snapshot_id == "S1"
    assert len(ds.triples) == 3
    # Check canonical sorting
    assert ds.triples[0].subject_id == "entity_a"
    assert ds.triples[1].subject_id == "entity_b"
    assert ds.triples[2].subject_id == "entity_c"

    assert ds.entities == ["entity_a", "entity_b", "entity_c"]
    assert ds.relations == ["rel_x", "rel_y"]
    assert len(ds.snapshot_hash) == 64


def test_mapping_consistency_invariant():
    """Mapping for identical entities MUST be strictly identical and deterministic."""
    raw1 = [("b", "r", "c"), ("a", "r", "b")]
    raw2 = [("a", "r", "b"), ("b", "r", "c")]

    ds1 = SnapshotDataset.create("S1", raw1)
    ds2 = SnapshotDataset.create("S1", raw2)

    assert ds1.get_entity_mapping() == ds2.get_entity_mapping()
    assert ds1.compute_mapping_hash() == ds2.compute_mapping_hash()
    assert ds1.snapshot_hash == ds2.snapshot_hash


def test_validation_rejects_empty_ids():
    with pytest.raises(ValueError):
        SnapshotDataset.create("S1", [("", "rel", "obj")])
    with pytest.raises(ValueError):
        SnapshotDataset.create("S1", [("sub", " ", "obj")])
    with pytest.raises(ValueError):
        SnapshotDataset.create("S1", [("sub", "rel", "")])


def test_entity_metadata_degree_calculation():
    triples = [
        ("e1", "rel", "e2"),
        ("e2", "rel", "e3"),
        ("e1", "rel", "e3"),
    ]
    ds = SnapshotDataset.create("S1", triples)
    assert ds.entity_metadata["e1"].degree == 2
    assert ds.entity_metadata["e2"].degree == 2
    assert ds.entity_metadata["e3"].degree == 2
