from __future__ import annotations

import pyarrow.parquet as pq

from kg_pipeline.inventory import run_inventory
from kg_pipeline.run import get_run_dir, init_run
from kg_pipeline.storage import read_json


def test_inventory_preserves_two_retrievals_for_one_blob_and_extracts_one_body_variant(tmp_path, blob_writer, acquisition_log_writer):
    _, digest = blob_writer(tmp_path, "A sufficiently long fixture article body. " * 12)
    acquisition_log_writer(tmp_path, digest, count=2)
    init_run(tmp_path, "fixture_inventory", mode="inventory")

    result = run_inventory(tmp_path, "fixture_inventory", verify_inputs=False)
    run_dir = get_run_dir(tmp_path, "fixture_inventory")
    retrievals = pq.read_table(run_dir / "tables" / "retrievals.parquet").to_pylist()
    bodies = pq.read_table(run_dir / "tables" / "body_variants.parquet").to_pylist()
    memberships = pq.read_table(run_dir / "tables" / "document_memberships.parquet").to_pylist()

    assert result["raw_summary"]["raw_paths"] == 1
    assert len(retrievals) == 2
    assert len({row["retrieval_id"] for row in retrievals}) == 2
    assert len(bodies) == 1
    assert len(memberships) == 1
    assert "retrieval_" in memberships[0]["retrieval_ids_json"]


def test_inventory_rerun_reuses_immutable_semantic_artifacts_and_never_changes_raw(tmp_path, blob_writer, acquisition_log_writer):
    raw_path, digest = blob_writer(tmp_path, "A sufficiently long fixture article body. " * 12)
    acquisition_log_writer(tmp_path, digest, count=1)
    original_bytes = raw_path.read_bytes()
    init_run(tmp_path, "fixture_rerun", mode="inventory")

    first = run_inventory(tmp_path, "fixture_rerun", verify_inputs=False)
    second = run_inventory(tmp_path, "fixture_rerun", verify_inputs=False)
    run_dir = get_run_dir(tmp_path, "fixture_rerun")
    manifest = read_json(run_dir / "tables" / "raw_inventory.parquet.manifest.json")

    assert raw_path.read_bytes() == original_bytes
    assert first["table_write_statuses"]["raw_inventory"] == "CREATED"
    assert second["table_write_statuses"]["raw_inventory"] == "REUSED"
    assert manifest["semantic_sha256"]
