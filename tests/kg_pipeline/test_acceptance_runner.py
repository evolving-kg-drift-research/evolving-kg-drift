from __future__ import annotations

import pytest

from kg_pipeline.acceptance_runner import STAGES, readiness, run_one_stage
from kg_pipeline.cli import main


def test_missing_authority_does_not_create_or_execute_any_stage(tmp_path):
    for stage in STAGES:
        report = run_one_stage(tmp_path, "not_created", stage, "pilot", {"path": "missing.json", "sha256": "a" * 64})
        assert report["status"] == "BLOCKED"
        assert report["next_stage_executed"] is False
    assert not (tmp_path / "runs").exists()


def test_stage_cli_requires_single_stage_and_phase(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["run-stage", "--run", "r", "--stage", "all"])
    assert main(["--repo-root", str(tmp_path), "run-stage", "--run", "not_created", "--stage", "4.9",
                 "--phase", "pilot", "--inputs", "missing.json", "--inputs-sha256", "a" * 64]) == 2
    assert "BLOCKED" in capsys.readouterr().out


def test_registry_never_combines_adjudication_and_fact_publication():
    assert STAGES["4.11"].outputs == ("adjudication_decisions", "pending_conflicts")
    assert STAGES["4.12"].previous == "4.11"
    assert "fact_versions" in STAGES["4.12"].outputs


def test_readiness_reports_candidate_without_activating_current_schema():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    before = (root / "config/schema.yaml").read_bytes()
    report = readiness(root)
    assert report["status"] == "BLOCKED"
    assert report["candidate_table_count"] == 25
    assert report["runtime_schema"]["status"] == "BLOCKED"
    assert all(c["status"] == "PASS" for c in report["candidate_hash_checks"])
    assert before == (root / "config/schema.yaml").read_bytes()
