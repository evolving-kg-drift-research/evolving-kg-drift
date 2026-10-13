from datetime import datetime, timezone

import pytest
from temporal.schema import FactVersion, Claim, ContractError
from temporal.snapshot import build_snapshot, build_snapshot_edges_and_support


def dt(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_fact(
    fact_id,
    *,
    evidence_at,
    valid_from,
    valid_to=None,
    parent_id=None,
    revision_type="creation",
    logical_id="lf1",
    object_id="B",
):
    return FactVersion(
        fact_version_id=fact_id,
        logical_fact_id=logical_id,
        subject_id="A",
        relation_id="REL",
        object_id=object_id,
        valid_from=valid_from,
        valid_to=valid_to,
        evidence_observed_at=evidence_at,
        ingested_at_real=evidence_at,
        supersedes_version_id=parent_id,
        revision_type=revision_type,
        source_id="source-1",
        source_url="https://source.test/item",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="a" * 64,
    )


def build_edge_view(facts, cutoff, acceptance=None):
    if acceptance is None:
        acceptance = {
            fact.fact_version_id: fact.evidence_observed_at for fact in facts
        }
    return build_snapshot_edges_and_support(
        facts,
        cutoff,
        accepted_at_by_fact_id=acceptance,
        require_accepted_clock=True,
    )[0]

def test_claim_contract_requires_span():
    with pytest.raises(ContractError, match="Evidence span offsets are mandatory"):
        Claim("c1", "s1", "A", "REL", "B", None, None, "hash")

    with pytest.raises(ContractError, match="strictly less than end"):
        Claim("c1", "s1", "A", "REL", "B", 10, 10, "hash")


def test_fact_version_contract_timezone():
    with pytest.raises(ContractError, match="must be timezone-aware"):
        FactVersion(
            "fv1", "lf1", "A", "REL", "B",
            valid_from=dt(2021, 1, 1), valid_to=None,
            evidence_observed_at=datetime(2021, 1, 1), # Naive
            ingested_at_real=dt(2021, 1, 2),
            supersedes_version_id=None, revision_type="creation",
            source_id="s1", source_url="",
            evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
        )


def test_late_alias_does_not_rewrite_history():
    fact_v1 = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="CompanyA",
        relation_id="CEO",
        object_id="PersonAlias",
        valid_from=dt(2020, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2020, 1, 1),
        ingested_at_real=dt(2025, 1, 1),
        supersedes_version_id=None,
        revision_type="creation",
        source_id="s1",
        source_url="http://s1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
        entity_map_version="v1"
    )
    
    # We learn at 2021-01-01 that PersonAlias is canonical_person_1
    fact_v2 = FactVersion(
        fact_version_id="fv2",
        logical_fact_id="lf1",
        subject_id="CompanyA",
        relation_id="CEO",
        object_id="canonical_person_1",
        valid_from=dt(2020, 1, 1),
        valid_to=None,
        evidence_observed_at=dt(2021, 1, 1), # Learned later
        ingested_at_real=dt(2025, 1, 1),
        supersedes_version_id="fv1",
        revision_type="alias_resolution",
        source_id="s1",
        source_url="http://s1",
        evidence_span_start=0,
        evidence_span_end=10,
        evidence_text_hash="hash",
        entity_map_version="v2"
    )

    facts = [fact_v1, fact_v2]

    # Snapshot at 2020-06-01: fact_v2 is NOT known yet.
    snap_2020, _ = build_snapshot(facts, cutoff=dt(2020, 6, 1))
    assert len(snap_2020) == 1
    assert snap_2020[0].object_id == "PersonAlias"

    # Snapshot at 2021-06-01: fact_v2 IS known, supersedes fact_v1.
    snap_2021, _ = build_snapshot(facts, cutoff=dt(2021, 6, 1))
    assert len(snap_2021) == 1
    assert snap_2021[0].object_id == "canonical_person_1"


def test_retraction_closes_logical_fact():
    fact_v1 = FactVersion(
        fact_version_id="fv1",
        logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 1, 1), ingested_at_real=dt(2020, 1, 1),
        supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )

    fact_v2 = FactVersion(
        fact_version_id="fv2",
        logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 2, 1), ingested_at_real=dt(2020, 2, 1),
        supersedes_version_id="fv1", revision_type="retraction",
        source_id="s2", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )

    facts = [fact_v1, fact_v2]

    snap_jan, _ = build_snapshot(facts, cutoff=dt(2020, 1, 15))
    assert len(snap_jan) == 1

    snap_feb, _ = build_snapshot(facts, cutoff=dt(2020, 2, 15))
    assert len(snap_feb) == 0  # Retracted


def test_snapshot_canonical_determinism():
    fact = FactVersion(
        fact_version_id="fv1", logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2020, 1, 1), valid_to=None,
        evidence_observed_at=dt(2020, 1, 1), ingested_at_real=dt(2020, 1, 1),
        supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="",
        evidence_span_start=0, evidence_span_end=10, evidence_text_hash="hash"
    )
    
    snap1, hash1 = build_snapshot([fact], cutoff=dt(2025, 1, 1))
    snap2, hash2 = build_snapshot([fact], cutoff=dt(2025, 1, 1))
    
    assert hash1 == hash2


@pytest.mark.parametrize("builder", [build_snapshot, build_edge_view])
def test_future_effective_correction_keeps_old_fact_until_effective(builder):
    old = make_fact(
        "old",
        evidence_at=dt(2020, 1, 1),
        valid_from=dt(2020, 1, 1),
    )
    correction = make_fact(
        "correction",
        evidence_at=dt(2021, 1, 1),
        valid_from=dt(2022, 1, 1),
        parent_id="old",
        revision_type="correction",
        object_id="C",
    )

    before_effective = builder([old, correction], dt(2021, 6, 1))
    at_effective = builder([old, correction], dt(2022, 1, 1))

    if builder is build_snapshot:
        assert [fact.fact_version_id for fact in before_effective[0]] == ["old"]
        assert [fact.fact_version_id for fact in at_effective[0]] == ["correction"]
    else:
        assert [(edge.subject_id, edge.relation_id, edge.object_id) for edge in before_effective] == [
            ("A", "REL", "B")
        ]
        assert [(edge.subject_id, edge.relation_id, edge.object_id) for edge in at_effective] == [
            ("A", "REL", "C")
        ]


@pytest.mark.parametrize("builder", [build_snapshot, build_edge_view])
def test_future_effective_retraction_does_not_remove_old_fact_early(builder):
    old = make_fact(
        "old",
        evidence_at=dt(2020, 1, 1),
        valid_from=dt(2020, 1, 1),
    )
    retraction = make_fact(
        "retraction",
        evidence_at=dt(2021, 1, 1),
        valid_from=dt(2022, 1, 1),
        parent_id="old",
        revision_type="retraction",
    )

    before_effective = builder([old, retraction], dt(2021, 6, 1))
    at_effective = builder([old, retraction], dt(2022, 1, 1))

    if builder is build_snapshot:
        assert [fact.fact_version_id for fact in before_effective[0]] == ["old"]
        assert at_effective[0] == []
    else:
        assert len(before_effective) == 1
        assert at_effective == []


@pytest.mark.parametrize("builder", [build_snapshot, build_edge_view])
@pytest.mark.parametrize(
    "facts",
    [
        [
            make_fact("revision", evidence_at=dt(2021, 1, 1), valid_from=dt(2021, 1, 1), parent_id="missing", revision_type="correction"),
        ],
        [
            make_fact("old", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1)),
            make_fact("other-logical-id", evidence_at=dt(2021, 1, 1), valid_from=dt(2021, 1, 1), parent_id="old", revision_type="correction", logical_id="lf2"),
        ],
        [
            make_fact("first", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1), parent_id="second", revision_type="correction"),
            make_fact("second", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1), parent_id="first", revision_type="correction"),
        ],
        [
            make_fact("old", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1)),
            make_fact("correction-a", evidence_at=dt(2021, 1, 1), valid_from=dt(2021, 1, 1), parent_id="old", revision_type="correction"),
            make_fact("correction-b", evidence_at=dt(2021, 1, 2), valid_from=dt(2021, 1, 1), parent_id="old", revision_type="correction"),
        ],
        [
            make_fact("duplicate", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1)),
            make_fact("duplicate", evidence_at=dt(2020, 1, 1), valid_from=dt(2020, 1, 1), object_id="C"),
        ],
    ],
    ids=["missing-parent", "cross-logical-id", "cycle", "competing-revisions", "duplicate-id"],
)
def test_revision_graph_errors_are_rejected(builder, facts):
    with pytest.raises(ContractError):
        builder(facts, dt(2022, 1, 1))


def test_production_snapshot_excludes_future_accepted_revision():
    old = make_fact(
        "old",
        evidence_at=dt(2020, 1, 1),
        valid_from=dt(2020, 1, 1),
    )
    correction = make_fact(
        "correction",
        evidence_at=dt(2021, 1, 1),
        valid_from=dt(2021, 1, 1),
        parent_id="old",
        revision_type="correction",
        object_id="C",
    )
    edges = build_edge_view(
        [old, correction],
        dt(2022, 1, 1),
        acceptance={"old": dt(2020, 1, 2), "correction": dt(2023, 1, 1)},
    )

    assert [(edge.subject_id, edge.relation_id, edge.object_id) for edge in edges] == [
        ("A", "REL", "B")
    ]


def test_production_snapshot_requires_acceptance_clock():
    fact = make_fact(
        "fact",
        evidence_at=dt(2020, 1, 1),
        valid_from=dt(2020, 1, 1),
    )

    with pytest.raises(ContractError, match="Missing accepted_into_kg_at"):
        build_edge_view([fact], dt(2021, 1, 1), acceptance={})
