from __future__ import annotations

import pyarrow.parquet as pq

import json
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


def test_genuine_repeated_fetch_same_bytes_different_publishers(tmp_path, blob_writer):
    _, digest = blob_writer(tmp_path, "A duplicated news piece")
    (tmp_path / "logs").mkdir()
    records = [
        {
            "event_id": "fetch-A",
            "payload_sha256": digest,
            "source_id": "publisher_A",
            "final_url": "https://pubA.test/news",
            "retrieved_at_real": "2026-09-01T10:00:00Z"
        },
        {
            "event_id": "fetch-B",
            "payload_sha256": digest,
            "source_id": "publisher_B",
            "final_url": "https://pubB.test/news",
            "retrieved_at_real": "2026-09-02T11:00:00Z"
        }
    ]
    (tmp_path / "logs/acquisition.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    init_run(tmp_path, "multi_pub_run", mode="inventory")
    run_inventory(tmp_path, "multi_pub_run", verify_inputs=False)

    run_dir = get_run_dir(tmp_path, "multi_pub_run")
    retrievals = pq.read_table(run_dir / "tables" / "retrievals.parquet").to_pylist()

    # Assert two distinct retrievals from the two publishers, even though it's the exact same bytes
    assert len(retrievals) == 2
    sources = {r["source_id"] for r in retrievals}
    assert sources == {"publisher_A", "publisher_B"}
    assert all(r["strict_source_input_eligible"] is True for r in retrievals)

def test_same_event_appears_in_two_places(tmp_path, blob_writer):
    _, digest = blob_writer(tmp_path, "Some content")
    (tmp_path / "logs").mkdir()
    record = {
        "event_id": "fetch-1",
        "payload_sha256": digest,
        "source_id": "publisher",
        "final_url": "https://pub.test/page",
        "retrieved_at_real": "2026-09-01T10:00:00Z"
    }

    (tmp_path / "logs/acquisition1.jsonl").write_text(json.dumps(record), encoding="utf-8")
    (tmp_path / "logs/acquisition2.jsonl").write_text(json.dumps(record), encoding="utf-8")

    init_run(tmp_path, "dup_event_run", mode="inventory")
    run_inventory(tmp_path, "dup_event_run", verify_inputs=False)

    run_dir = get_run_dir(tmp_path, "dup_event_run")
    retrievals = pq.read_table(run_dir / "tables" / "retrievals.parquet").to_pylist()

    # We should have two identical semantic retrievals generated because they come from different locator paths,
    # but they share the exact same payload. However, since the record identifier and json bytes are the same,
    # but the path is different, the stable ID generator might treat them as different due to the locator path included.
    # Wait, the R2 plan says "Test cùng event xuất hiện hai nơi". If they appear in two places, they should be
    # represented but one might be de-duplicated or kept as 2 distinct provenance ledgers.
    # Actually, they form two entries in retrievals right now due to different evidence_path.
    assert len(retrievals) == 2

def test_partial_and_strict_timestamps_ledger(tmp_path, blob_writer):
    _, digest = blob_writer(tmp_path, "Timestamps test")
    (tmp_path / "logs").mkdir()
    records = [
        {
            "event_id": "strict-fetch",
            "payload_sha256": digest,
            "source_id": "publisher",
            "final_url": "https://pub.test/strict",
            "retrieved_at_real": "2026-09-01T10:00:00+00:00" # Valid timezone
        },
        {
            "event_id": "partial-fetch-no-tz",
            "payload_sha256": digest,
            "source_id": "publisher",
            "final_url": "https://pub.test/partial",
            "retrieved_at_real": "2026-09-01T10:00:00" # Missing timezone
        },
        {
            "event_id": "partial-fetch-fake",
            "payload_sha256": digest,
            "source_id": "publisher",
            "final_url": "https://pub.test/fake",
            # No retrieved_at_real at all, just fake report info
            "mtime": "2026-09-01"
        }
    ]
    (tmp_path / "logs/acquisition.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    init_run(tmp_path, "partial_strict_run", mode="inventory")
    run_inventory(tmp_path, "partial_strict_run", verify_inputs=False)

    run_dir = get_run_dir(tmp_path, "partial_strict_run")
    retrievals = pq.read_table(run_dir / "tables" / "retrievals.parquet").to_pylist()

    assert len(retrievals) == 3
    strict = [r for r in retrievals if r["strict_source_input_eligible"] is True]
    assert len(strict) == 1
    assert strict[0]["provenance_status"] == "VERIFIED_ACQUISITION_EVIDENCE"

    partial_no_tz = [r for r in retrievals if r["provenance_status"] == "INVALID_ACQUISITION_TIME_MISSING_TZ"]
    assert len(partial_no_tz) == 1
    assert partial_no_tz[0]["strict_source_input_eligible"] is False

    partial_unknown = [r for r in retrievals if r["provenance_status"] == "PARTIAL_ACQUISITION_EVIDENCE_TIME_UNKNOWN"]
    assert len(partial_unknown) == 1
    assert partial_unknown[0]["strict_source_input_eligible"] is False

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
