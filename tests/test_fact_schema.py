from datetime import datetime, timezone
import pytest
from temporal.schema import FactVersion, ContractError


def dt(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_fact_version_timezone_enforcement():
    with pytest.raises(ContractError, match="valid_from must be timezone-aware"):
        FactVersion(
            "fv1", "lf1", "A", "REL", "B",
            valid_from=datetime(2021, 1, 1),  # Naive
            valid_to=None,
            evidence_observed_at=dt(2021, 1, 1),
            ingested_at_real=dt(2021, 1, 1),
            supersedes_version_id=None, revision_type="creation",
            source_id="s1", source_url="", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h"
        )


def test_fact_version_valid_from_before_valid_to():
    with pytest.raises(ContractError, match="valid_from must be strictly before valid_to"):
        FactVersion(
            "fv1", "lf1", "A", "REL", "B",
            valid_from=dt(2022, 1, 1),
            valid_to=dt(2021, 1, 1),  # Invalid order
            evidence_observed_at=dt(2021, 1, 1),
            ingested_at_real=dt(2021, 1, 1),
            supersedes_version_id=None, revision_type="creation",
            source_id="s1", source_url="", evidence_span_start=0, evidence_span_end=10, evidence_text_hash="h"
        )


def test_fact_version_span_validation():
    with pytest.raises(ContractError, match="FactVersion requires evidence span offsets"):
        FactVersion(
            "fv1", "lf1", "A", "REL", "B",
            valid_from=dt(2021, 1, 1),
            valid_to=None,
            evidence_observed_at=dt(2021, 1, 1),
            ingested_at_real=dt(2021, 1, 1),
            supersedes_version_id=None, revision_type="creation",
            source_id="s1", source_url="",
            evidence_span_start=None, evidence_span_end=None,  # Missing spans
            evidence_text_hash="h"
        )
