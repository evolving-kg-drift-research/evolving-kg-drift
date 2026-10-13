"""Keep default CI code checks separate from artifact-backed certification."""

from pathlib import Path


def test_default_ci_invokes_only_non_certifying_gate_code_checks():
    repository = Path(__file__).resolve().parents[2]
    workflow = (repository / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    verification_commands = [
        line.strip()
        for line in workflow.splitlines()
        if "scripts/verify_g1.py" in line or "scripts/verify_g2.py" in line
    ]
    assert verification_commands == [
        "run: python scripts/verify_g1.py --ci --code-checks",
    ]
    assert "Verify temporal code conformance (not scientific G1)" in workflow
