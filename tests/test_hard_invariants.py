import pytest


# G1 / temporal integrity
def test_no_future_evidence():
    from temporal.schema import FactVersion
    from temporal.snapshot import build_snapshot
    from datetime import datetime, timezone
    
    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fact = FactVersion(
        fact_version_id="fv1", logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=cutoff, valid_to=None,
        evidence_observed_at=datetime(2021, 1, 1, tzinfo=timezone.utc), # Future
        ingested_at_real=cutoff, supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="", evidence_span_start=0, evidence_span_end=1, evidence_text_hash="h"
    )
    snap, _ = build_snapshot([fact], cutoff=cutoff)
    assert len(snap) == 0


def test_no_future_entity_mapping():
    from datetime import datetime, timezone
    from temporal.schema import EntityMappingVersion, FactVersion
    from temporal.snapshot import build_snapshot_edges_and_support

    cutoff_past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    cutoff_future = datetime(2022, 1, 1, tzinfo=timezone.utc)

    fact = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="MentionA",
        relation_id="REL",
        object_id="MentionB",
        valid_from=cutoff_past,
        valid_to=None,
        evidence_observed_at=cutoff_past,
        ingested_at_real=cutoff_past,
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="http://s1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
    )

    mapping = EntityMappingVersion(
        entity_mapping_id="em1",
        mention="MentionA",
        canonical_entity_id="CanonicalA",
        mapping_available_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )

    # In snapshot at cutoff_past (2020), mapping was not available yet
    edges_past, _, _ = build_snapshot_edges_and_support(
        [fact], cutoff=cutoff_past, entity_mappings=[mapping]
    )
    assert len(edges_past) == 1
    assert edges_past[0].subject_id == "MentionA"

    # In snapshot at cutoff_future (2022), mapping IS available
    edges_future, _, _ = build_snapshot_edges_and_support(
        [fact], cutoff=cutoff_future, entity_mappings=[mapping]
    )
    assert len(edges_future) == 1
    assert edges_future[0].subject_id == "CanonicalA"


def test_snapshot_reproducible():
    from datetime import datetime, timezone
    from temporal.schema import FactVersion
    from temporal.snapshot import build_snapshot_edges_and_support, compute_graph_semantic_hash

    cutoff = datetime(2020, 1, 1, tzinfo=timezone.utc)
    fact = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="A",
        relation_id="REL",
        object_id="B",
        valid_from=cutoff,
        valid_to=None,
        evidence_observed_at=cutoff,
        ingested_at_real=cutoff,
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
    )

    edges1, _, _ = build_snapshot_edges_and_support([fact], cutoff=cutoff)
    edges2, _, _ = build_snapshot_edges_and_support([fact], cutoff=cutoff)
    hash1 = compute_graph_semantic_hash(edges1)
    hash2 = compute_graph_semantic_hash(edges2)
    assert hash1 == hash2
    assert len(edges1) == 1


def test_canonical_parquet_neo4j_parity():
    from datetime import datetime, timezone
    from kg_pipeline.parity import ParityError, verify_neo4j_parity
    from temporal.schema import FactVersion

    dt = datetime(2021, 1, 1, tzinfo=timezone.utc)
    fact1 = FactVersion(
        fact_version_id="f1",
        logical_fact_id="lf1",
        subject_id="A",
        relation_id="REL",
        object_id="B",
        valid_from=dt,
        valid_to=None,
        evidence_observed_at=dt,
        ingested_at_real=dt,
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="u1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="h",
    )

    neo4j_edges = [
        {
            "subject_id": "A",
            "relation_id": "REL",
            "object_id": "B",
            "valid_from": dt.isoformat(),
            "valid_to": None,
            "fact_version_id": "f1",
        }
    ]
    report = verify_neo4j_parity([fact1], neo4j_edges)
    assert report["status"] == "PASS"
    assert report["edges_verified"] == 1

    with pytest.raises(ParityError, match="Missing in Neo4j"):
        verify_neo4j_parity([fact1], [])


# KGE / alignment / null
@pytest.mark.skip(reason="Implement when KGE checkpoints exist")
def test_embeddings_finite():
    pass


@pytest.mark.skip(reason="Implement when Procrustes alignment exists")
def test_procrustes_is_orthogonal():
    pass


@pytest.mark.skip(reason="Implement with deterministic anchor split")
def test_anchor_fit_holdout_disjoint():
    pass


@pytest.mark.skip(reason="Implement with alignment diagnostics")
def test_alignment_holdout_diagnostics_exist():
    pass


@pytest.mark.skip(reason="Implement with same-snapshot empirical null")
def test_null_excludes_target_entity_when_required():
    pass


@pytest.mark.skip(reason="Implement when drift artifacts exist")
def test_no_nan_inf_in_drift_artifacts():
    pass


# QA / H2 / H3a contracts
@pytest.mark.skip(reason="Implement when QA candidate universes exist")
def test_ab_same_primary_candidate_universe():
    pass


@pytest.mark.skip(reason="Implement when Frozen-KGE OOV scoring exists")
def test_frozen_oov_scoring_rule_exact():
    pass


@pytest.mark.skip(reason="Implement when path reranking exists")
def test_c_exact_b_fallback_when_no_path():
    pass


# Locked-run access
@pytest.mark.skip(reason="Enable before the locked-test workflow")
def test_locked_test_not_accessed_before_freeze():
    pass
