"""Code-test results must never masquerade as scientific gates."""

import pytest

from kg_pipeline.gates import evaluate_scientific_gate
from kg_pipeline.cli import main as cli_main
from kg_pipeline.quality import evaluate_quality
from kg_pipeline.run import init_run
from kg_pipeline.storage import write_json_immutable
from scripts import verify_g1, verify_g2


@pytest.mark.parametrize("gate", ["G1", "G2"])
@pytest.mark.parametrize("run_id", [None, "missing_run"])
def test_missing_run_cannot_certify_or_create_run(tmp_path, gate, run_id):
    report = evaluate_scientific_gate(tmp_path, run_id, gate)
    assert report["status"] == "BLOCKED"
    assert report["evaluated_count"] == 0
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("script", [verify_g1, verify_g2])
def test_ci_without_run_is_not_scientific_pass(monkeypatch, tmp_path, capsys, script):
    monkeypatch.setattr(script, "ROOT", tmp_path)
    assert script.main(["--ci"]) == 2
    assert "PASS" not in capsys.readouterr().out


def test_report_claiming_pass_cannot_replace_missing_evaluator(tmp_path):
    init_run(tmp_path, "fixture_run", mode="inventory")
    write_json_immutable(tmp_path / "runs/fixture_run/reports/quality_gate_report.json", {
        "status": "PASS", "evaluated_count": 500,
    })
    report = evaluate_scientific_gate(tmp_path, "fixture_run", "G2")
    assert report["status"] == "BLOCKED"
    assert any(c["check_id"] == "SCIENTIFIC_EVALUATOR_UNAVAILABLE" for c in report["checks"])


def test_empty_quality_is_unavailable():
    report = evaluate_quality([], [])
    assert report["status"] == "BLOCKED"
    assert report["error_rate"] is None
    assert report["reason"] == "NO_EVALUATED_RECORDS"


@pytest.mark.parametrize("gate", ["G1", "G2"])
def test_scientific_cli_requires_explicit_run_and_keeps_blocked_exit(tmp_path, capsys, gate):
    assert cli_main(["--repo-root", str(tmp_path), "verify-scientific", "--run", "missing_run", "--gate", gate]) == 2
    assert '"status": "BLOCKED"' in capsys.readouterr().out


def test_unmatched_gold_does_not_disappear():
    report = evaluate_quality([], [{
        "subject_id": "a", "relation_id": "r", "object_id": "b", "evidence_observed_at": "2020-01-01",
    }])
    assert report["status"] == "BLOCKED"
    assert report["unmatched_gold"] == 1


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -1, 2])
def test_invalid_quality_threshold(threshold):
    with pytest.raises(ValueError, match="error_threshold"):
        evaluate_quality([], [], error_threshold=threshold)


def test_skipped_helpers_cannot_pass_code_conformance(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    def skipped_report(command, **kwargs):
        report = next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml="))
        Path(report).write_text(
            '<testsuite tests="4" skipped="1" failures="0" errors="0"/>', encoding="utf-8"
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(verify_g1.subprocess, "run", skipped_report)
    with pytest.raises(SystemExit, match="still skipped"):
        verify_g1.main(["--code-checks"])


@pytest.mark.parametrize("script", [verify_g1, verify_g2])
def test_scientific_check_never_invokes_git_or_fixture_tests(monkeypatch, tmp_path, script):
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail("Scientific verification must not use git tags or fixture subprocesses")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(script, "ROOT", tmp_path)
    assert script.main(["--ci"]) == 2
