from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
G1_TESTS = (
    "tests/test_hard_invariants.py::test_no_future_evidence",
    "tests/test_hard_invariants.py::test_no_future_entity_mapping",
    "tests/test_hard_invariants.py::test_snapshot_reproducible",
    "tests/test_hard_invariants.py::test_canonical_parquet_neo4j_parity",
)


def run_selected_tests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "g1.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            *G1_TESTS,
            f"--junitxml={report}",
        ]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode != 0:
            raise SystemExit("[FAIL] One or more G1 temporal tests failed.")

        tree = ET.parse(report)
        root = tree.getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        skipped = sum(int(s.attrib.get("skipped", "0")) for s in suites)
        failures = sum(int(s.attrib.get("failures", "0")) for s in suites)
        errors = sum(int(s.attrib.get("errors", "0")) for s in suites)
        tests = max((int(s.attrib.get("tests", "0")) for s in suites), default=0)

        if tests < len(G1_TESTS):
            raise SystemExit(
                f"[FAIL] Expected {len(G1_TESTS)} G1 tests but pytest reported {tests}."
            )
        if skipped:
            raise SystemExit(
                f"[FAIL] G1 is not satisfied: {skipped} required temporal test(s) are still skipped."
            )
        if failures or errors:
            raise SystemExit("[FAIL] G1 test report contains failures/errors.")

    print("[CODE_CONFORMANCE_PASS] Temporal helper tests passed; scientific G1 is not certified.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", help="Exact scientific run to verify")
    parser.add_argument("--ci", action="store_true", help="Scientific checks remain strict in CI")
    parser.add_argument("--code-checks", action="store_true", help="Run helper tests only; never certify G1")
    args = parser.parse_args(argv)
    if args.code_checks:
        if args.run:
            parser.error("--run and --code-checks are separate verification scopes")
        run_selected_tests()
        return 0
    sys.path.insert(0, str(ROOT / "src"))
    from kg_pipeline.gates import evaluate_scientific_gate
    report = evaluate_scientific_gate(ROOT, args.run, "G1")
    print(json.dumps(report, indent=2))
    print(f"[{report['status']}] Scientific G1")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
