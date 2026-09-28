import pytest
from datetime import datetime, timezone
from temporal.schema import FactVersion
from kg_pipeline.parity import (
    verify_neo4j_parity,
    verify_snapshot_set_parity,
    ParityError,
)

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
            "valid_from": dt(2021, 1, 1).isoformat(),
            "valid_to": None,
            "fact_version_id": "f1",
        }
    ]
    report = verify_neo4j_parity([fact1], neo4j_edges)
    assert report["status"] == "PASS"
    assert report["edges_verified"] == 1

    # 2. Missing in Neo4j
    with pytest.raises(ParityError, match="Missing in Neo4j: 1"):
        verify_neo4j_parity([fact1], [])

    # 3. Extra in Neo4j
    neo4j_edges.append(
        {
            "subject_id": "A",
            "relation_id": "REL",
            "object_id": "C",
            "valid_from": dt(2021, 1, 1).isoformat(),
            "valid_to": None,
            "fact_version_id": "f2",
        }
    )
    with pytest.raises(ParityError, match="Extra in Neo4j: 1"):
        verify_neo4j_parity([fact1], neo4j_edges)


def test_snapshot_set_parity_detects_same_count_wrong_edge():
    nodes = ["alice", "acme"]
    canonical = [{
        "subject_id": "alice", "relation_id": "works_at", "object_id": "acme",
        "snapshot_id": "s1", "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None, "fact_version_id": "fv1",
    }]
    wrong_but_same_count = [{**canonical[0], "object_id": "other", "fact_version_id": "fv2"}]
    with pytest.raises(ParityError, match="set parity mismatch"):
        verify_snapshot_set_parity(nodes, canonical, ["alice", "other"], wrong_but_same_count)


def test_snapshot_set_parity_checks_temporal_metadata():
    nodes = ["alice", "acme"]
    canonical = [{
        "subject_id": "alice", "relation_id": "works_at", "object_id": "acme",
        "snapshot_id": "s1", "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None, "fact_version_id": "fv1",
    }]
    materialized = [{**canonical[0], "valid_from": "2021-01-01T00:00:00+00:00"}]
    with pytest.raises(ParityError, match="set parity mismatch"):
        verify_snapshot_set_parity(nodes, canonical, nodes, materialized)
