from datetime import datetime, timezone
from temporal.schema import FactVersion
from kg_pipeline.quality import evaluate_quality

def dt(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)

def test_evaluate_quality():
    fact1 = FactVersion(
        fact_version_id="f1", logical_fact_id="lf1",
        subject_id="A", relation_id="REL", object_id="B",
        valid_from=dt(2021,1,1), valid_to=None, evidence_observed_at=dt(2021,1,1),
        ingested_at_real=dt(2021,1,1), supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="u1", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h"
    )

    fact2 = FactVersion(
        fact_version_id="f2", logical_fact_id="lf2",
        subject_id="C", relation_id="REL", object_id="D",
        valid_from=dt(2021,1,1), valid_to=None, evidence_observed_at=dt(2021,1,1),
        ingested_at_real=dt(2021,1,1), supersedes_version_id=None, revision_type="creation",
        source_id="s1", source_url="u1", evidence_span_start=20, evidence_span_end=30, evidence_text_hash="h"
    )

    gold_standard = [
        {
            "subject_id": "A", "relation_id": "REL", "object_id": "B",
            "evidence_observed_at": dt(2021,1,1).isoformat(),
            "evidence_span_start": 0, "evidence_span_end": 10
        },
        {
            "subject_id": "C", "relation_id": "REL", "object_id": "D",
            "evidence_observed_at": dt(2021,1,1).isoformat(),
            "evidence_span_start": 21, "evidence_span_end": 30 # Off by one error!
        }
    ]

    report = evaluate_quality([fact1, fact2], gold_standard, error_threshold=0.0)
    assert report["status"] == "FAIL"
    assert report["evaluated_count"] == 2
    assert report["error_count"] == 1
    assert report["errors"][0]["type"] == "SPAN_MISMATCH"