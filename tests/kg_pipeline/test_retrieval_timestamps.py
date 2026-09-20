import pytest

from kg_pipeline.contracts import ContractError, make_row, validate_retrieval_rows


def retrieval(value, *, strict=True):
    return make_row(
        "retrievals",
        retrieval_id="fixture",
        raw_blob_sha256="a" * 64,
        source_id="fixture",
        final_url="https://example.test/article",
        retrieved_at_real=value,
        strict_source_input_eligible=strict,
    )


@pytest.mark.parametrize("value", ["UNKNOWN", "2025-02-30T12:00:00Z", "2025-01-01", "2025-01-01T12:00:00", 123])
def test_invalid_strict_timestamp_rejected(value):
    with pytest.raises(ContractError, match="timezone-aware ISO"):
        validate_retrieval_rows([retrieval(value)])


@pytest.mark.parametrize("value", ["2025-01-01T12:00:00Z", "2025-01-01T19:00:00+07:00"])
def test_explicit_timezone_preserved(value):
    row = retrieval(value)
    validate_retrieval_rows([row])
    assert row["retrieved_at_real"] == value


def test_non_strict_unknown_remains_auditable():
    row = retrieval("UNKNOWN", strict=False)
    validate_retrieval_rows([row])
    assert not row["strict_source_input_eligible"]
