import pytest
from datetime import datetime, timezone
from temporal.schema import FactVersion
from kg_pipeline.parity import verify_neo4j_parity, ParityError

def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)

def test_verify_neo4j_parity():
    fact1 = FactVersion(
        fact_version_id="f1", logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2021,1,1), valid_to=None, evidence_observed_at=dt(2021,1,1),
        ingested_at_real=dt(2021,1,1), supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="u1", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h"
    )

    # 1. Exact match
    neo4j_edges = [
        {
            "subject_id": "A",
            "relation_id": "REL",
            "object_id": "B",
            "valid_from": dt(2021,1,1).isoformat(),
            "valid_to": None,
            "fact_version_id": "f1"
        }
    ]
    report = verify_neo4j_parity([fact1], neo4j_edges)
    assert report["status"] == "PASS"
    assert report["edges_verified"] == 1

    # 2. Missing in Neo4j
    with pytest.raises(ParityError, match="Missing in Neo4j"):
        verify_neo4j_parity([fact1], [])

    # 3. Extra in Neo4j
    neo4j_edges.append(
        {
            "subject_id": "A",
            "relation_id": "REL",
            "object_id": "C",
            "valid_from": dt(2021,1,1).isoformat(),
            "valid_to": None,
            "fact_version_id": "f2"
        }
    )
    with pytest.raises(ParityError, match="Extra in Neo4j"):
        verify_neo4j_parity([fact1], neo4j_edges)
