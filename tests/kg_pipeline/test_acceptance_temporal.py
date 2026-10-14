from __future__ import annotations

from copy import deepcopy

import pytest

from kg_pipeline.acceptance_temporal import acceptance_at, event_boundaries, observed_at, occurrence_id, snapshot_triples
from kg_pipeline.hashing import sha256_text
from kg_pipeline.rebuild_artifacts import RebuildBlocked

POLICY = {"revision_types": ["creation", "correction", "retraction"], "tombstone_types": ["retraction"]}
T1, T2, T3 = (f"2025-0{i}-01T00:00:00+00:00" for i in (1, 2, 3))


def fixture():
    fact = {"FactVersionID": "f1", "LogicalFactID": "logical", "subject_id": "a", "relation_id": "r",
            "object_id": "b", "object_value": None, "valid_from": T1, "valid_to": None,
            "evidence_observed_at": T1, "accepted_into_kg_at": T1, "revision_type": "creation",
            "supersedes_version_id": None, "subject_mapping_id": "ma", "object_mapping_id": "mb"}
    mappings = [{"entity_mapping_id": f"m{eid}", "canonical_entity_id": eid,
                 "mapping_available_at": T1, "availability_basis_ref": "fixture-proof"} for eid in ("a", "b")]
    return fact, mappings


def test_occurrence_identity_changes_with_span_body_or_version():
    text = "Alpha and Alpha"
    def identifier(start, end, version="v1"):
        return occurrence_id("body", text, start, end, normalization_version="clean-text-identity-v1",
                             mention_rule_version=version)
    assert identifier(0, 5) != identifier(10, 15)
    assert identifier(0, 5) != identifier(0, 5, "v2")
    assert identifier(0, 5) == identifier(0, 5)


def test_observation_needs_exact_public_content_proof():
    proof = {"body_sha256": sha256_text("body"), "proof_ref": "proof", "original_url": "https://example.test",
             "content_version_id": "version", "basis": "public_capture", "observed_at": T1}
    assert observed_at(proof, body_sha256=proof["body_sha256"], policy={"observation_basis": ["public_capture"]}) == T1
    proof["basis"] = "retrieved_at_real"
    with pytest.raises(RebuildBlocked):
        observed_at(proof, body_sha256=proof["body_sha256"], policy={"observation_basis": ["public_capture"]})


def test_acceptance_is_last_required_support_or_mapping_not_review_time():
    supports = [{"claim_id": "c1", "independent_origin_id": "origin", "proof_ref": "p",
                 "origin_basis_ref": "o", "observed_at": T1}]
    mappings = [{"mapping_available_at": T2, "availability_basis_ref": "p"}]
    review = {"decision": "accept", "reviewer_id": "human", "basis_ref": "review",
              "sufficient_support_claim_ids": ["c1"], "accepted_into_kg_at": T2, "adjudicated_at_real": T3}
    assert acceptance_at(supports, mappings, review) == T2
    review["accepted_into_kg_at"] = T1
    with pytest.raises(RebuildBlocked, match="differs"):
        acceptance_at(supports, mappings, review)


def test_future_effective_correction_does_not_erase_old_fact():
    fact, mappings = fixture()
    child = {**fact, "FactVersionID": "f2", "revision_type": "correction", "supersedes_version_id": "f1",
             "valid_from": T3, "evidence_observed_at": T2, "accepted_into_kg_at": T2, "object_id": "c",
             "object_mapping_id": "mc"}
    mappings.append({"entity_mapping_id": "mc", "canonical_entity_id": "c", "mapping_available_at": T2,
                     "availability_basis_ref": "p"})
    triples, exclusions = snapshot_triples([child, fact], mappings, T2, policy=POLICY)
    assert triples == [("a", "r", "b")]
    assert exclusions == [{"FactVersionID": "f2", "reason_code": "NOT_WORLD_VALID_AS_OF"}]
    assert snapshot_triples([fact, child], mappings, T3, policy=POLICY)[0] == [("a", "r", "c")]


def test_retract_is_append_only_and_as_of():
    fact, mappings = fixture()
    child = {**fact, "FactVersionID": "f2", "revision_type": "retraction", "supersedes_version_id": "f1",
             "evidence_observed_at": T2, "accepted_into_kg_at": T2}
    assert snapshot_triples([fact, child], mappings, T1, policy=POLICY)[0] == [("a", "r", "b")]
    assert snapshot_triples([fact, child], mappings, T2, policy=POLICY)[0] == []
    assert fact["supersedes_version_id"] is None


@pytest.mark.parametrize("mutation", ["parent", "cycle", "competing", "clock", "missing_mapping"])
def test_bad_lineage_or_clocks_fail_closed(mutation):
    fact, mappings = fixture()
    facts = [fact]
    if mutation == "parent":
        fact["supersedes_version_id"] = "unknown"
    elif mutation == "cycle":
        fact["supersedes_version_id"] = "f1"
    elif mutation == "competing":
        facts.append({**deepcopy(fact), "FactVersionID": "f2"})
    elif mutation == "clock":
        fact["accepted_into_kg_at"] = "2020-01-01T00:00:00+00:00"
    else:
        mappings.pop()
    with pytest.raises(RebuildBlocked):
        snapshot_triples(facts, mappings, T2, policy=POLICY)


def test_boundaries_keep_atomic_ties_and_input_permutation():
    events = [{"event_id": f"e{i}", "graph_effective_at": t, "time_basis_ref": "p"}
              for i, t in enumerate((T1, T1, T2, T3))]
    result = event_boundaries(events, target=2, allowed=(2, 3))
    assert result["cutoffs"] == [T1, T3]
    assert result == event_boundaries(list(reversed(events)), target=2, allowed=(2, 3))
    with pytest.raises(RebuildBlocked, match="INSUFFICIENT"):
        event_boundaries(events[:2], target=2, allowed=(2, 3))
