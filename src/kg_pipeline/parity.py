from datetime import datetime, timezone
from typing import Iterable, Any
from collections import Counter
from temporal.schema import FactVersion

class ParityError(Exception):
    pass

def _normalize_time(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc).isoformat()
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            return val
    return str(val)

def verify_neo4j_parity(parquet_facts: Iterable[FactVersion], neo4j_edges: Iterable[dict]) -> dict:
    """
    Verify exact parity between canonical Parquet facts and Neo4j materialized edges.
    """
    parquet_list = []
    for f in parquet_facts:
        parquet_list.append((
            f.subject_id, f.relation_id, f.object_id,
            _normalize_time(f.valid_from),
            _normalize_time(f.valid_to),
            f.fact_version_id
        ))

    neo4j_list = []
    for e in neo4j_edges:
        neo4j_list.append((
            e.get("subject_id"), e.get("relation_id"), e.get("object_id"),
            _normalize_time(e.get("valid_from")),
            _normalize_time(e.get("valid_to")),
            e.get("fact_version_id")
        ))

    parquet_counts = Counter(parquet_list)
    neo4j_counts = Counter(neo4j_list)

    missing_in_neo4j = parquet_counts - neo4j_counts
    extra_in_neo4j = neo4j_counts - parquet_counts

    if missing_in_neo4j or extra_in_neo4j:
        raise ParityError(
            f"Parity mismatch! "
            f"Missing in Neo4j (incl. duplicates): {sum(missing_in_neo4j.values())}. "
            f"Extra in Neo4j (incl. duplicates): {sum(extra_in_neo4j.values())}."
        )

    return {"status": "PASS", "edges_verified": len(parquet_list)}
