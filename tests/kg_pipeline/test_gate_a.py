from __future__ import annotations

from kg_pipeline.cli import main
from kg_pipeline.gates import evaluate_gate_a
from kg_pipeline.inventory import run_inventory
from kg_pipeline.run import init_run


def test_gate_a_is_blocked_not_pass_when_source_lock_and_provenance_are_missing(tmp_path, blob_writer, source_lock_writer):
    blob_writer(tmp_path, "A sufficiently long fixture article body. " * 12)
    source_lock_writer(tmp_path)
    init_run(tmp_path, "fixture_blocked", mode="inventory")
    run_inventory(tmp_path, "fixture_blocked", verify_inputs=False)

    gate = evaluate_gate_a(tmp_path, "fixture_blocked")

    assert gate["status"] == "BLOCKED"
    assert next(check for check in gate["checks"] if check["check_id"] == "A-006")["status"] == "BLOCKED"
    assert main(["--repo-root", str(tmp_path), "verify", "--run", "fixture_blocked", "--gate", "A"]) != 0


def test_gate_a_fails_when_hash_named_blob_does_not_match_its_bytes(tmp_path, blob_writer):
    blob_writer(tmp_path, "A sufficiently long fixture article body. " * 12, filename_hash="f" * 64)
    init_run(tmp_path, "fixture_hash_failure", mode="inventory")
    run_inventory(tmp_path, "fixture_hash_failure", verify_inputs=False)

    gate = evaluate_gate_a(tmp_path, "fixture_hash_failure")

    assert gate["status"] == "FAIL"
    assert next(check for check in gate["checks"] if check["check_id"] == "A-003")["status"] == "FAIL"
