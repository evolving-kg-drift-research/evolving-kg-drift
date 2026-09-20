from typing import Iterable
from temporal.schema import FactVersion

class ParityError(Exception):
    pass

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