from kg_pipeline.cli import _status
from kg_pipeline.gates import evaluate_gate_a, latest_gate_a_report
from kg_pipeline.inventory import run_inventory
from kg_pipeline.run import get_run_dir, init_run
from kg_pipeline.storage import write_json_immutable


def test_verify_before_inventory_does_not_poison_report_path(tmp_path, blob_writer):
    run_id = "gate_history_fixture"
    blob_writer(tmp_path, "A fixture article body. " * 30)
    init_run(tmp_path, run_id, mode="inventory")
    first = evaluate_gate_a(tmp_path, run_id)
    assert first["status"] == "NOT_RUN"
    run_dir = get_run_dir(tmp_path, run_id)
    originals = {path: path.read_bytes() for path in (run_dir / "gates/A").glob("*.json")}
    run_inventory(tmp_path, run_id, verify_inputs=False)
    second = evaluate_gate_a(tmp_path, run_id)
    assert second["status"] == "BLOCKED"
    assert len(list((run_dir / "gates/A").glob("*.json"))) == 2
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert latest_gate_a_report(run_dir) == second
    assert _status(tmp_path, run_id)["gate_A_status"] == "BLOCKED"


def test_legacy_report_remains_readable(tmp_path):
    report = {"status": "BLOCKED"}
    write_json_immutable(tmp_path / "gates/gate_A.json", report)
    assert latest_gate_a_report(tmp_path) == report

def test_input_mutation_invalidates_gate(tmp_path, blob_writer):
    # This tests the requirement: "kiểm chứng mới chặn stale PASS; test thay input sau PASS"
    run_id = "stale_pass_fixture"
    raw_path, digest = blob_writer(tmp_path, "A fixture article body.")
    init_run(tmp_path, run_id, mode="inventory")

    # Run inventory to generate inputs, but we will mock evaluate_gate_a internally by directly writing a fake PASS report
    run_inventory(tmp_path, run_id, verify_inputs=False)
    run_dir = get_run_dir(tmp_path, run_id)

    # 1. We mock a PASS report for this run
    pass_report = {"evaluated_at_real": "2026-09-20T00:00:00Z", "status": "PASS", "checks": []}
    from kg_pipeline.storage import write_json_immutable
    import json

    (run_dir / "gates" / "A").mkdir(parents=True, exist_ok=True)
    (run_dir / "gates" / "A" / "2026-09-20T00-00-00Z_fake123.json").write_text(json.dumps(pass_report))

    # Validate the status is PASS right now
    assert latest_gate_a_report(run_dir)["status"] == "PASS"

    # 2. We now mutate the raw input
    raw_path.write_text("Mutated body")

    # 3. We re-run evaluate_gate_a, it MUST detect the read_error / hash_mismatch and return FAIL
    new_report = evaluate_gate_a(tmp_path, run_id)
    assert new_report["status"] != "PASS"

    # We should see the new report as the latest one
    assert latest_gate_a_report(run_dir) == new_report
    report = {"status": "BLOCKED"}
    write_json_immutable(tmp_path / "gates/gate_A.json", report)
    assert latest_gate_a_report(tmp_path) == report
