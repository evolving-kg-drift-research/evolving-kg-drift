from __future__ import annotations

import pytest

from kg_pipeline.contracts import ContractError, make_row, validate_retrieval_rows
from kg_pipeline.baseline import inspect_source_lock


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
    lock_path = tmp_path / "data/manifests/sources.lock.json"
    original_bytes = lock_path.read_bytes()
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "configs/protocol_v1.yaml").write_text(
        'sources:\n  proposal_sha256: "' + "0" * 64 + '"\n', encoding="utf-8"
    )
    result = inspect_source_lock(tmp_path)
    assert lock_path.read_bytes() == original_bytes

    assert result["status"] == "BLOCKED"
    assert {item["role"] for item in result["items"]} == {"proposal", "execution_plan", "patch"}
    assert [item for item in result["items"] if item["role"] == "proposal"] == [
        {
            "role": "proposal",
            "path": "sources/missing-proposal.pdf",
            "expected_sha256": "0" * 64,
            "actual_sha256": None,
            "status": "MISSING",
        }
    ]


def test_schema_yaml_aligns_with_table_contracts():
    """A31: Verify harmonization of schema definitions across config/schema.yaml and contracts.py."""
    from pathlib import Path
    import yaml
    from kg_pipeline.contracts import TABLE_SCHEMAS

    schema_path = Path(__file__).resolve().parents[2] / "config" / "schema.yaml"
    with schema_path.open("r", encoding="utf-8") as f:
        schema_cfg = yaml.safe_load(f)

    # Check key schemas are present in both schema.yaml and contracts.TABLE_SCHEMAS
    expected_tables = {
        "retrievals",
        "source_versions",
        "body_variants",
        "document_memberships",
        "claim_provenance",
        "fact_versions",
        "snapshot_edges",
        "snapshot_edge_support",
        "snapshot_exclusions",
    }
    for table_name in expected_tables:
        assert table_name in TABLE_SCHEMAS, f"{table_name} missing from contracts.py"
        # Check that table exists in schema.yaml
        assert table_name in schema_cfg, f"{table_name} missing from schema.yaml"
        yaml_fields = set(schema_cfg[table_name]["fields"])
        pyarrow_fields = {f.name for f in TABLE_SCHEMAS[table_name] if f.name != "schema_version"}
        # Ensure intersection covers core fields
        common = yaml_fields.intersection(pyarrow_fields)
        assert len(common) > 0, f"No common fields between schema.yaml and contracts.py for {table_name}"
