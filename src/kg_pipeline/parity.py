from typing import Iterable
from temporal.schema import FactVersion

class ParityError(Exception):
    pass


def _snapshot_edge_key(edge: dict) -> tuple:
    required = ("subject_id", "relation_id", "object_id")
    missing = [field for field in required if not edge.get(field)]
    if missing:
        raise ParityError(f"Snapshot edge is missing required fields: {missing}")
    return (
        edge["subject_id"],
        edge["relation_id"],
        edge["object_id"],
        edge.get("snapshot_id"),
        edge.get("valid_from"),
        edge.get("valid_to"),
        edge.get("fact_version_id"),
    )


def verify_snapshot_set_parity(
    canonical_nodes: Iterable[dict | str],
    canonical_edges: Iterable[dict],
    materialized_nodes: Iterable[dict | str],
    materialized_edges: Iterable[dict],
) -> dict:
    """Compare exact snapshot node, edge, and temporal-metadata sets.

    This function is storage-agnostic so a real Neo4j readback can be supplied;
    callers must pass the rows read from the materialized store, not just counts.
    """
    def node_id(row: dict | str) -> str:
        value = row if isinstance(row, str) else row.get("entity_id", row.get("id"))
        if not isinstance(value, str) or not value:
            raise ParityError(f"Invalid node identity: {row!r}")
        return value

    canonical_node_rows = [node_id(row) for row in canonical_nodes]
    materialized_node_rows = [node_id(row) for row in materialized_nodes]
    if len(canonical_node_rows) != len(set(canonical_node_rows)):
        raise ParityError("Canonical snapshot contains duplicate node identities")
    if len(materialized_node_rows) != len(set(materialized_node_rows)):
        raise ParityError("Materialized graph contains duplicate node identities")
    canonical_node_set = set(canonical_node_rows)
    materialized_node_set = set(materialized_node_rows)

    canonical_edge_rows = [_snapshot_edge_key(edge) for edge in canonical_edges]
    materialized_edge_rows = [_snapshot_edge_key(edge) for edge in materialized_edges]
    if len(canonical_edge_rows) != len(set(canonical_edge_rows)):
        raise ParityError("Canonical snapshot contains duplicate edge identities")
    if len(materialized_edge_rows) != len(set(materialized_edge_rows)):
        raise ParityError("Materialized graph contains duplicate edge identities")
    canonical_edge_set = set(canonical_edge_rows)
    materialized_edge_set = set(materialized_edge_rows)

    missing_nodes = canonical_node_set - materialized_node_set
    extra_nodes = materialized_node_set - canonical_node_set
    missing_edges = canonical_edge_set - materialized_edge_set
    extra_edges = materialized_edge_set - canonical_edge_set
    if missing_nodes or extra_nodes or missing_edges or extra_edges:
        raise ParityError(
            "Snapshot set parity mismatch: "
            f"missing_nodes={len(missing_nodes)}, extra_nodes={len(extra_nodes)}, "
            f"missing_edges={len(missing_edges)}, extra_edges={len(extra_edges)}"
        )
    return {
        "status": "PASS",
        "nodes_verified": len(canonical_node_set),
        "edges_verified": len(canonical_edge_set),
    }

def verify_neo4j_parity(parquet_facts: Iterable[FactVersion], neo4j_edges: Iterable[dict]) -> dict:
    """
    Verify exact parity between canonical Parquet facts and Neo4j materialized edges.
    """
    parquet_set = set()
    for f in parquet_facts:
        parquet_set.add((
            f.subject_id, f.relation_id, f.object_id,
            f.valid_from.isoformat(),
            f.valid_to.isoformat() if f.valid_to else None,
            f.fact_version_id
        ))

    neo4j_set = set()
    for e in neo4j_edges:
        neo4j_set.add((
            e.get("subject_id"), e.get("relation_id"), e.get("object_id"),
            e.get("valid_from"), e.get("valid_to"), e.get("fact_version_id")
        ))

    missing_in_neo4j = parquet_set - neo4j_set
    extra_in_neo4j = neo4j_set - parquet_set

    if missing_in_neo4j or extra_in_neo4j:
        raise ParityError(
            f"Parity mismatch! "
            f"Missing in Neo4j: {len(missing_in_neo4j)}. "
            f"Extra in Neo4j: {len(extra_in_neo4j)}."
        )

    return {"status": "PASS", "edges_verified": len(parquet_set)}
