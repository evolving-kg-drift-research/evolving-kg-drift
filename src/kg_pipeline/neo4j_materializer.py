"""Materialize verified canonical snapshots and read them back from Neo4j."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Protocol

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .hashing import sha256_json, utc_now_iso
from .parity import verify_snapshot_set_parity
from .run import (
    _producer_ref_for_manifest,
    _producer_ref_for_table,
    get_run_dir,
    resolve_run_table_path,
)
from .storage import ArtifactConflict


class Neo4jTransaction(Protocol):
    def run(self, query: str, **parameters: Any) -> Iterable[Any]: ...


class Neo4jSession(Protocol):
    def execute_read(self, transaction, *args: Any, **kwargs: Any) -> Any: ...

    def execute_write(self, transaction, *args: Any, **kwargs: Any) -> Any: ...


class Neo4jDriver(Protocol):
    def session(self, *, database: str) -> Neo4jSession: ...


_OWNER_CONSTRAINT = """
CREATE CONSTRAINT kg_materialization_owner IF NOT EXISTS
FOR (owner:KGMaterializationOwner) REQUIRE owner.key IS UNIQUE
"""

_CLAIM_DATABASE = """
OPTIONAL MATCH (existing:KGEntity)
WITH count(existing) AS existing_nodes
MERGE (owner:KGMaterializationOwner {key: 'canonical'})
ON CREATE SET owner.run_id = $run_id, owner.run_binding = $run_binding,
              owner.unowned_nodes = existing_nodes
RETURN owner.run_id AS run_id, owner.run_binding AS run_binding,
       owner.unowned_nodes AS unowned_nodes
"""


_WRITE_NODES = """
UNWIND $rows AS row
MERGE (node:KGEntity {entity_id: row.entity_id})
ON CREATE SET node.snapshot_ids = [row.snapshot_id]
ON MATCH SET node.snapshot_ids = CASE
    WHEN row.snapshot_id IN coalesce(node.snapshot_ids, []) THEN node.snapshot_ids
    ELSE coalesce(node.snapshot_ids, []) + [row.snapshot_id]
END
"""

_WRITE_EDGES = """
UNWIND $rows AS row
MATCH (subject:KGEntity {entity_id: row.subject_id})
MATCH (object:KGEntity {entity_id: row.object_id})
MERGE (subject)-[edge:KG_EDGE {snapshot_id: row.snapshot_id, edge_id: row.edge_id}]->(object)
ON CREATE SET
    edge.relation_id = row.relation_id,
    edge.temporal_support_json = row.temporal_support_json
"""

_READ_NODES = """
MATCH (node:KGEntity)
WHERE $snapshot_id IN coalesce(node.snapshot_ids, [])
RETURN node.entity_id AS entity_id
ORDER BY entity_id
"""

_READ_EDGES = """
MATCH (subject:KGEntity)-[edge:KG_EDGE {snapshot_id: $snapshot_id}]->(object:KGEntity)
RETURN subject.entity_id AS subject_id,
       edge.relation_id AS relation_id,
       object.entity_id AS object_id,
       edge.snapshot_id AS snapshot_id,
       edge.edge_id AS edge_id,
       edge.temporal_support_json AS temporal_support_json
ORDER BY subject_id, relation_id, object_id, edge_id
"""


def _consume(result: Iterable[Any]) -> None:
    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()
    else:
        list(result)


def _record_dict(record: Any) -> dict[str, Any]:
    data = getattr(record, "data", None)
    if callable(data):
        return data()
    return dict(record)


def _write_snapshot_tx(
    tx: Neo4jTransaction,
    node_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]],
    run_id: str,
    run_binding: str,
) -> None:
    owners = [_record_dict(row) for row in tx.run(
        _CLAIM_DATABASE, run_id=run_id, run_binding=run_binding
    )]
    if len(owners) != 1 or owners[0] != {
        "run_id": run_id, "run_binding": run_binding, "unowned_nodes": 0,
    }:
        raise ArtifactConflict("Neo4j database belongs to a different run or contains unowned KG data")
    _consume(tx.run(_WRITE_NODES, rows=node_rows))
    _consume(tx.run(_WRITE_EDGES, rows=edge_rows))


def _read_nodes_tx(tx: Neo4jTransaction, snapshot_id: str) -> list[dict[str, Any]]:
    return [_record_dict(row) for row in tx.run(_READ_NODES, snapshot_id=snapshot_id)]


def _read_edges_tx(tx: Neo4jTransaction, snapshot_id: str) -> list[dict[str, Any]]:
    return [_record_dict(row) for row in tx.run(_READ_EDGES, snapshot_id=snapshot_id)]


def _iso_aware(value: Any, *, field: str, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"FactVersion is missing required temporal metadata {field}.")
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"FactVersion has invalid temporal metadata {field}.") from exc
    else:
        raise ValueError(f"FactVersion has invalid temporal metadata type for {field}.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"FactVersion temporal metadata {field} must include a timezone.")
    return parsed.isoformat()


def _read_verified_parquet_rows(path: Path, ref: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    payload = path.read_bytes()
    physical_sha256 = hashlib.sha256(payload).hexdigest()
    if physical_sha256 != ref.get("physical_sha256"):
        raise ArtifactConflict(f"Canonical Parquet changed after canonical verification: {path}")
    return pq.read_table(pa.BufferReader(payload)).to_pylist(), physical_sha256


def _canonical_snapshot_rows(
    repo_root: Path,
    run_id: str,
    snapshot_id: str,
) -> tuple[list[str], list[dict[str, Any]], dict[str, str]]:
    """Read only producer-bound canonical Parquet after internal canonical validation."""
    from .canonical_validation import validate_canonical_snapshots

    snapshots = validate_canonical_snapshots(repo_root, run_id, [snapshot_id], verify_manifest=True)
    if snapshot_id not in snapshots:
        raise ValueError(f"Verified run loader did not return requested snapshot {snapshot_id}.")

    run_dir = get_run_dir(repo_root, run_id)
    snapshot_dir = run_dir / "snapshots" / snapshot_id
    edges_path = snapshot_dir / "snapshot_edges.parquet"
    supports_path = snapshot_dir / "snapshot_edge_support.parquet"
    manifest_path = snapshot_dir / "snapshot_manifest.yaml"
    for path in (edges_path, supports_path, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(f"Verified snapshot package is missing {path}.")

    edges_ref = _producer_ref_for_table(repo_root, edges_path, "snapshot_edges")
    supports_ref = _producer_ref_for_table(repo_root, supports_path, "snapshot_edge_support")
    manifest_ref = _producer_ref_for_manifest(repo_root, manifest_path)
    fact_path = resolve_run_table_path(repo_root, run_id, "fact_versions")
    fact_ref = _producer_ref_for_table(repo_root, fact_path, "fact_versions")
    edges, edges_physical_sha256 = _read_verified_parquet_rows(edges_path, edges_ref)
    supports, supports_physical_sha256 = _read_verified_parquet_rows(supports_path, supports_ref)
    fact_rows, facts_physical_sha256 = _read_verified_parquet_rows(fact_path, fact_ref)
    if (
        manifest_ref.get("artifact_kind") != "yaml"
        or manifest_ref.get("contract_version") != "snapshot-manifest-v2"
    ):
        raise ArtifactConflict("Snapshot manifest is not bound with the supported producer contract.")
    manifest_payload = manifest_path.read_bytes()
    manifest_physical_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_physical_sha256 != manifest_ref.get("physical_sha256"):
        raise ArtifactConflict(f"Snapshot manifest changed after canonical verification: {manifest_path}")
    manifest_data = yaml.safe_load(manifest_payload.decode("utf-8"))

    loaded_triples = sorted(
        (triple.subject_id, triple.relation_id, triple.object_id)
        for triple in snapshots[snapshot_id].triples
    )
    parquet_triples = sorted(
        (row.get("subject_id"), row.get("relation_id"), row.get("object_id"))
        for row in edges
    )
    if loaded_triples != parquet_triples:
        raise ArtifactConflict("Canonical snapshot Parquet changed after canonical validation.")
    facts_by_id: dict[str, dict[str, Any]] = {}
    for fact in fact_rows:
        fact_id = fact.get("fact_version_id")
        if not isinstance(fact_id, str) or not fact_id or fact_id in facts_by_id:
            raise ValueError("FactVersion store contains a duplicate or missing FactVersionID.")
        facts_by_id[fact_id] = fact

    support_by_edge: dict[str, set[str]] = {}
    for support in supports:
        edge_id = support.get("edge_id")
        fact_id = support.get("fact_version_id")
        if not isinstance(edge_id, str) or not edge_id or fact_id not in facts_by_id:
            raise ValueError("Snapshot support has a missing edge or unknown FactVersion reference.")
        support_by_edge.setdefault(edge_id, set()).add(fact_id)

    edge_rows: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    seen_edge_ids: set[str] = set()
    for edge in edges:
        edge_id = edge.get("edge_id")
        subject_id = edge.get("subject_id")
        relation_id = edge.get("relation_id")
        object_id = edge.get("object_id")
        if not all(isinstance(value, str) and value for value in (edge_id, subject_id, relation_id, object_id)):
            raise ValueError("Canonical snapshot edge has a missing identity field.")
        if edge_id in seen_edge_ids:
            raise ValueError(f"Canonical snapshot contains duplicate edge_id {edge_id}.")
        seen_edge_ids.add(edge_id)
        fact_ids = sorted(support_by_edge.get(edge_id, set()))
        if not fact_ids:
            raise ValueError(f"Snapshot edge {edge_id} has no FactVersion support.")

        temporal_support = []
        for fact_id in fact_ids:
            fact = facts_by_id[fact_id]
            temporal_support.append({
                "fact_version_id": fact_id,
                "valid_from": _iso_aware(fact.get("valid_from"), field="valid_from", required=False),
                "valid_to": _iso_aware(fact.get("valid_to"), field="valid_to", required=False),
                "evidence_observed_at": _iso_aware(
                    fact.get("evidence_observed_at"), field="evidence_observed_at", required=True
                ),
                "accepted_into_kg_at": _iso_aware(
                    fact.get("accepted_into_kg_at"), field="accepted_into_kg_at", required=True
                ),
            })
        row = {
            "subject_id": subject_id,
            "relation_id": relation_id,
            "object_id": object_id,
            "snapshot_id": snapshot_id,
            "edge_id": edge_id,
            "temporal_support_json": json.dumps(
                temporal_support, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        }
        edge_rows.append(row)
        node_ids.update((subject_id, object_id))

    node_rows = [
        {"entity_id": entity_id, "snapshot_id": snapshot_id}
        for entity_id in sorted(node_ids)
    ]
    if not isinstance(manifest_data, dict):
        raise ValueError("Snapshot manifest must be a mapping before Neo4j materialization.")
    bindings = {
        "snapshot_manifest_hash": manifest_data.get("snapshot_manifest_hash"),
        "graph_semantic_hash": manifest_data.get("graph_semantic_hash"),
        "support_semantic_hash": manifest_data.get("support_semantic_hash"),
        "exclusion_semantic_hash": manifest_data.get("exclusion_semantic_hash"),
        "accepted_clock_hash": manifest_data.get("accepted_clock_hash"),
        "entity_mapping_hash": manifest_data.get("entity_mapping_hash"),
        "resolved_config_hash": manifest_data.get("resolved_config_hash"),
        "boundary_hash": manifest_data.get("boundary_hash"),
        "code_fingerprint": manifest_data.get("code_fingerprint"),
        "snapshot_manifest_physical_sha256": manifest_physical_sha256,
        "snapshot_edges_physical_sha256": edges_physical_sha256,
        "snapshot_edge_support_physical_sha256": supports_physical_sha256,
        "fact_versions_physical_sha256": facts_physical_sha256,
    }
    if any(not isinstance(value, str) or not value for value in bindings.values()):
        raise ValueError("Verified snapshot package lacks a physical or semantic hash binding.")
    return node_rows, edge_rows, bindings


def materialize_verified_snapshot_to_neo4j(
    repo_root: Path,
    run_id: str,
    snapshot_id: str,
    *,
    driver: Neo4jDriver,
    database: str,
) -> dict[str, Any]:
    """Write a verified canonical snapshot, then compare it with a Neo4j read-back.

    The caller must pass a driver already connected to the intended isolated
    test database. Writes are additive: existing relationship metadata is never
    overwritten, and stale or conflicting records cause exact-set parity to fail.
    """
    if (
        not isinstance(database, str) or not database.strip() or database != database.strip()
        or database.lower() in {"neo4j", "system"}
    ):
        raise ValueError("An explicit isolated Neo4j database is required; default/system databases are forbidden.")
    node_rows, edge_rows, bindings = _canonical_snapshot_rows(repo_root, run_id, snapshot_id)
    canonical_nodes = [row["entity_id"] for row in node_rows]
    run_binding = sha256_json({
        "run_id": run_id, "config": bindings["resolved_config_hash"],
        "code": bindings["code_fingerprint"],
    })
    with driver.session(database=database) as session:
        session.execute_write(lambda tx: _consume(tx.run(_OWNER_CONSTRAINT)))
        session.execute_write(_write_snapshot_tx, node_rows, edge_rows, run_id, run_binding)
        materialized_nodes = session.execute_read(_read_nodes_tx, snapshot_id)
        materialized_edges = session.execute_read(_read_edges_tx, snapshot_id)

    parity = verify_snapshot_set_parity(
        canonical_nodes,
        edge_rows,
        materialized_nodes,
        materialized_edges,
    )
    semantic = {
        "report_version": "neo4j-readback-parity-v1",
        "scope": "technical_integration_only",
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "database": database,
        "run_binding": run_binding,
        "input_bindings": bindings,
        "nodes_verified": parity["nodes_verified"],
        "edges_verified": parity["edges_verified"],
        "status": "PASS",
    }
    return {
        **semantic,
        "created_at_real": utc_now_iso(),
        "semantic_sha256": sha256_json(semantic),
    }
