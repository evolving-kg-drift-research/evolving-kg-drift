from __future__ import annotations

import pytest

from kg_pipeline.contracts import ContractError, make_row, validate_retrieval_rows
from kg_pipeline.run import inspect_source_lock


def test_strict_retrieval_requires_real_retrieval_time_and_final_url():
    row = make_row(
        "retrievals",
        retrieval_id="retrieval_fixture",
        raw_blob_sha256="a" * 64,
        source_id="fixture",
        requested_url="https://example.test/requested",
        final_url="https://example.test/final",
        retrieved_at_real=None,
        strict_source_input_eligible=True,
    )
    with pytest.raises(ContractError, match="retrieved_at_real"):
        validate_retrieval_rows([row])


def test_file_mtime_and_article_metadata_are_rejected_as_acquisition_times():
    row = make_row(
        "retrievals",
        retrieval_id="retrieval_fixture",
        raw_blob_sha256="a" * 64,
        source_id="fixture",
        final_url="https://example.test/final",
        strict_source_input_eligible=False,
        recorded_event_time_field="file_mtime",
    )
    with pytest.raises(ContractError, match="must not use"):
        validate_retrieval_rows([row])


def test_missing_locked_source_artifact_is_blocked_and_lock_is_not_rewritten(tmp_path, source_lock_writer):
    source_lock_writer(tmp_path)
    result = inspect_source_lock(tmp_path)

    assert result["status"] == "BLOCKED"
    assert result["items"] == [
        {
            "role": "proposal",
            "path": "sources/missing-proposal.pdf",
            "expected_sha256": "0" * 64,
            "actual_sha256": None,
            "status": "MISSING",
        }
    ]
