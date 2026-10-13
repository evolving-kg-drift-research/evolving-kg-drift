from __future__ import annotations

import ast
from pathlib import Path

import pytest

from kg_pipeline.canonical_validation import CanonicalSnapshot, CanonicalTriple
from kge.contract import SnapshotDataset


def test_m1_validation_and_materialization_do_not_depend_on_kge():
    root = Path(__file__).resolve().parents[2] / "src/kg_pipeline"
    for filename in ("canonical_validation.py", "neo4j_materializer.py"):
        tree = ast.parse((root / filename).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("kge", "src.kge"))
            elif isinstance(node, ast.Import):
                assert all(not alias.name.startswith(("kge", "src.kge")) for alias in node.names)


def test_canonical_hash_preserves_m2_graph_identity_without_kge_dependency():
    triples = [CanonicalTriple("B", "r", "C"), CanonicalTriple("A", "r", "B")]
    canonical = CanonicalSnapshot.create("S1", triples)
    downstream = SnapshotDataset.create("S1", triples)
    assert canonical.snapshot_hash == downstream.snapshot_hash
    assert canonical.entities == downstream.entities
    assert canonical == CanonicalSnapshot.create("S1", list(reversed(triples)))


def test_duplicate_graph_triples_cannot_be_mistaken_for_support_multiplicity():
    triple = CanonicalTriple("A", "r", "B")
    with pytest.raises(ValueError, match="duplicate triples"):
        CanonicalSnapshot.create("S1", [triple, triple])
