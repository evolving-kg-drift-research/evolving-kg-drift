from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from kg_pipeline.parity import ParityError, verify_snapshot_set_parity
from kg_pipeline.neo4j_materializer import materialize_verified_snapshot_to_neo4j
from kg_pipeline.storage import ArtifactConflict
from kge.contract import SnapshotDataset, Triple


class _Result(list):
    def consume(self):
        return None


class _FakeNeo4j:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str], dict] = {}
        self.session_calls = 0
        self.write_calls = 0
        self.read_calls = 0
        self.owner = None

    def session(self, *, database: str):
        self.session_calls += 1
        self.database = database
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute_write(self, callback, *args):
        self.write_calls += 1
        return callback(self, *args)

    def execute_read(self, callback, *args):
        self.read_calls += 1
        return callback(self, *args)

    def run(self, query: str, **parameters):
        if "CREATE CONSTRAINT kg_materialization_owner" in query:
            return _Result()
        if "MERGE (owner:KGMaterializationOwner" in query:
            if self.owner is None:
                self.owner = {**parameters, "unowned_nodes": len(self.nodes)}
            return _Result([self.owner])
        if "MERGE (node:KGEntity" in query:
            for row in parameters["rows"]:
                current = self.nodes.setdefault(row["entity_id"], {"entity_id": row["entity_id"], "snapshot_ids": []})
                if row["snapshot_id"] not in current["snapshot_ids"]:
                    current["snapshot_ids"].append(row["snapshot_id"])
            return _Result()
        if "MERGE (subject)-[edge:KG_EDGE" in query:
            for row in parameters["rows"]:
                key = (row["snapshot_id"], row["edge_id"])
                self.edges.setdefault(key, {
                    **row,
                    "subject_id": row["subject_id"],
                    "object_id": row["object_id"],
                })
            return _Result()
        if "RETURN node.entity_id AS entity_id" in query:
            snapshot_id = parameters["snapshot_id"]
            return _Result(
                {"entity_id": node["entity_id"]}
                for node in self.nodes.values()
                if snapshot_id in node["snapshot_ids"]
            )
        if "RETURN subject.entity_id AS subject_id" in query:
            snapshot_id = parameters["snapshot_id"]
            return _Result(
                {
                    field: edge.get(field)
                    for field in (
                        "subject_id", "relation_id", "object_id", "snapshot_id",
                        "edge_id", "temporal_support_json",
                    )
                }
                for (edge_snapshot_id, _edge_id), edge in self.edges.items()
                if edge_snapshot_id == snapshot_id
            )
        raise AssertionError(f"Unexpected Cypher query: {query}")


def _write_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def _materializer_fixture(
    tmp_path: Path,
    monkeypatch,
    *,
    run_id: str = "m1_c8_fixture",
    include_acceptance: bool = True,
):
    snapshot_id = "S1"
    run_dir = tmp_path / "runs" / run_id
    snapshot_dir = run_dir / "snapshots" / snapshot_id
    edge_path = snapshot_dir / "snapshot_edges.parquet"
    support_path = snapshot_dir / "snapshot_edge_support.parquet"
    fact_path = run_dir / "tables" / "fact_versions.parquet"
    _write_parquet(edge_path, [{
        "edge_id": "edge_1", "subject_id": "entity_a", "relation_id": "REL",
        "object_id": "entity_b", "snapshot_id": snapshot_id,
    }])
    _write_parquet(support_path, [{"edge_id": "edge_1", "fact_version_id": "fv_1"}])
    fact = {
        "fact_version_id": "fv_1",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None,
        "evidence_observed_at": "2020-01-02T00:00:00+00:00",
    }
    if include_acceptance:
        fact["accepted_into_kg_at"] = "2020-01-03T00:00:00+00:00"
    _write_parquet(fact_path, [fact])
    (snapshot_dir / "snapshot_manifest.yaml").write_text(
        yaml.safe_dump({
            "snapshot_manifest_hash": "a" * 64,
            "graph_semantic_hash": "b" * 64,
            "support_semantic_hash": "c" * 64,
            "exclusion_semantic_hash": "d" * 64,
            "accepted_clock_hash": "e" * 64,
            "entity_mapping_hash": "f" * 64,
            "resolved_config_hash": "1" * 64,
            "boundary_hash": "2" * 64,
            "code_fingerprint": "3" * 64,
        }), encoding="utf-8"
    )
    verified: list[tuple[Path, str, list[str]]] = []
    monkeypatch.setattr(
        "kg_pipeline.canonical_validation.validate_canonical_snapshots",
        lambda root, requested_run, ids, verify_manifest: verified.append((root, requested_run, ids))
        or {snapshot_id: SnapshotDataset.create(snapshot_id, [Triple("entity_a", "REL", "entity_b")])},
    )
    monkeypatch.setattr(
        "kg_pipeline.neo4j_materializer.resolve_run_table_path",
        lambda _root, _run, _table: fact_path,
    )
    monkeypatch.setattr(
        "kg_pipeline.neo4j_materializer._producer_ref_for_table",
        lambda _root, path, table: {
            "table_name": table,
            "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    )
    monkeypatch.setattr(
        "kg_pipeline.neo4j_materializer._producer_ref_for_manifest",
        lambda _root, path: {
            "artifact_kind": "yaml",
            "contract_version": "snapshot-manifest-v2",
            "physical_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    )
    return run_id, snapshot_id, verified


def test_materializer_reads_back_canonical_parquet_with_temporal_support(tmp_path, monkeypatch):
    run_id, snapshot_id, verified = _materializer_fixture(tmp_path, monkeypatch)
    database = _FakeNeo4j()

    report = materialize_verified_snapshot_to_neo4j(
        tmp_path, run_id, snapshot_id, driver=database, database="m1_test"
    )

    assert report["status"] == "PASS"
    assert report["scope"] == "technical_integration_only"
    assert report["nodes_verified"] == 2
    assert report["edges_verified"] == 1
    assert verified == [(tmp_path, run_id, [snapshot_id])]
    assert database.database == "m1_test"
    assert database.write_calls == 2
    assert database.read_calls == 2
    temporal_support = json.loads(database.edges[(snapshot_id, "edge_1")]["temporal_support_json"])
    assert temporal_support == [{
        "fact_version_id": "fv_1",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None,
        "evidence_observed_at": "2020-01-02T00:00:00+00:00",
        "accepted_into_kg_at": "2020-01-03T00:00:00+00:00",
    }]


def test_two_independent_fixture_runs_bind_the_same_semantic_inputs(tmp_path, monkeypatch):
    first_run, snapshot_id, _ = _materializer_fixture(
        tmp_path, monkeypatch, run_id="m1_c8_fixture_a"
    )
    first = materialize_verified_snapshot_to_neo4j(
        tmp_path, first_run, snapshot_id, driver=_FakeNeo4j(), database="m1_test_a"
    )
    second_run, _, _ = _materializer_fixture(
        tmp_path, monkeypatch, run_id="m1_c8_fixture_b"
    )
    second = materialize_verified_snapshot_to_neo4j(
        tmp_path, second_run, snapshot_id, driver=_FakeNeo4j(), database="m1_test_b"
    )

    assert first["input_bindings"] == second["input_bindings"]
    assert first["input_bindings"]["snapshot_manifest_hash"] == "a" * 64
    assert first["nodes_verified"] == second["nodes_verified"] == 2
    assert first["edges_verified"] == second["edges_verified"] == 1


def test_materializer_requires_explicit_acceptance_time_before_database_write(tmp_path, monkeypatch):
    run_id, snapshot_id, _ = _materializer_fixture(
        tmp_path, monkeypatch, include_acceptance=False
    )
    database = _FakeNeo4j()

    with pytest.raises(ValueError, match="accepted_into_kg_at"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, run_id, snapshot_id, driver=database, database="m1_test"
        )

    assert database.write_calls == 0
    assert database.nodes == {}
    assert database.edges == {}


def test_materializer_refuses_unverified_snapshot_before_opening_database(tmp_path, monkeypatch):
    run_id, snapshot_id, _ = _materializer_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "kg_pipeline.canonical_validation.validate_canonical_snapshots",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("canonical input blocked")),
    )
    database = _FakeNeo4j()

    with pytest.raises(PermissionError, match="canonical input blocked"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, run_id, snapshot_id, driver=database, database="m1_test"
        )

    assert database.session_calls == 0
    assert database.write_calls == 0


def test_materializer_detects_snapshot_change_after_canonical_validation(tmp_path, monkeypatch):
    run_id, snapshot_id, _ = _materializer_fixture(tmp_path, monkeypatch)
    edge_path = tmp_path / "runs" / run_id / "snapshots" / snapshot_id / "snapshot_edges.parquet"
    verified_edge_hash = hashlib.sha256(edge_path.read_bytes()).hexdigest()

    def validate_then_tamper(*_args, **_kwargs):
        edge_path.write_bytes(edge_path.read_bytes() + b"tampered")
        return {snapshot_id: SnapshotDataset.create(snapshot_id, [Triple("entity_a", "REL", "entity_b")])}

    monkeypatch.setattr(
        "kg_pipeline.canonical_validation.validate_canonical_snapshots",
        validate_then_tamper,
    )
    monkeypatch.setattr(
        "kg_pipeline.neo4j_materializer._producer_ref_for_table",
        lambda _root, path, table: {
            "table_name": table,
            "physical_sha256": (
                verified_edge_hash
                if path == edge_path
                else hashlib.sha256(path.read_bytes()).hexdigest()
            ),
        },
    )
    database = _FakeNeo4j()

    with pytest.raises(ArtifactConflict, match="changed after canonical verification"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, run_id, snapshot_id, driver=database, database="m1_test"
        )

    assert database.session_calls == 0
    assert database.write_calls == 0


def test_set_parity_detects_same_count_wrong_temporal_support():
    canonical_edge = {
        "subject_id": "entity_a", "relation_id": "REL", "object_id": "entity_b",
        "snapshot_id": "S1", "edge_id": "edge_1", "valid_from": "2020-01-01T00:00:00+00:00",
        "temporal_support_json": '[{"fact_version_id":"fv_1"}]',
    }
    changed_edge = {
        **canonical_edge,
        "temporal_support_json": '[{"fact_version_id":"fv_future"}]',
    }

    with pytest.raises(ParityError, match="set parity mismatch"):
        verify_snapshot_set_parity(
            ["entity_a", "entity_b"], [canonical_edge],
            ["entity_a", "entity_b"], [changed_edge],
        )


def test_materializer_can_produce_readback_before_m2_certification(tmp_path, monkeypatch):
    """P8: producing G1 evidence must not require the M2 G1 certificate first."""
    run_id, snapshot_id, _ = _materializer_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "kge.adapter.load_snapshots_from_run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            PermissionError("M2 certification awaits Neo4j read-back")
        ),
    )
    database = _FakeNeo4j()
    report = materialize_verified_snapshot_to_neo4j(
        tmp_path, run_id, snapshot_id, driver=database, database="m1_test"
    )
    assert report["scope"] == "technical_integration_only"
    assert report["status"] == "PASS"
    assert database.read_calls == 2


def test_same_database_refuses_different_runs_even_with_identical_snapshot_labels(tmp_path, monkeypatch):
    first, sid, _ = _materializer_fixture(tmp_path, monkeypatch, run_id="run_a")
    database = _FakeNeo4j()
    materialize_verified_snapshot_to_neo4j(
        tmp_path, first, sid, driver=database, database="isolated"
    )
    second, _, _ = _materializer_fixture(tmp_path, monkeypatch, run_id="run_b")
    with pytest.raises(ArtifactConflict, match="different run"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, second, sid, driver=database, database="isolated"
        )


@pytest.mark.parametrize("database_name", ["", "neo4j", "system", " neo4j "])
def test_materializer_refuses_default_or_ambiguous_database(tmp_path, database_name):
    database = _FakeNeo4j()
    with pytest.raises(ValueError, match="isolated"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, "run_id", "S1", driver=database, database=database_name
        )
    assert database.session_calls == 0


def test_materializer_refuses_adopting_unowned_graph(tmp_path, monkeypatch):
    run_id, sid, _ = _materializer_fixture(tmp_path, monkeypatch)
    database = _FakeNeo4j()
    database.nodes["historical"] = {"entity_id": "historical", "snapshot_ids": ["S1"]}
    with pytest.raises(ArtifactConflict, match="unowned"):
        materialize_verified_snapshot_to_neo4j(
            tmp_path, run_id, sid, driver=database, database="isolated"
        )
    assert set(database.nodes) == {"historical"}
    assert database.edges == {}
