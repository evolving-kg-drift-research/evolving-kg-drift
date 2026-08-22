from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
G1_TAG = "v0.2-vertical-slice"
G1_TESTS = (
    "tests/test_hard_invariants.py::test_no_future_evidence",
    "tests/test_hard_invariants.py::test_no_future_entity_mapping",
    "tests/test_hard_invariants.py::test_snapshot_reproducible",
    "tests/test_hard_invariants.py::test_canonical_parquet_neo4j_parity",
)


def git_tag_exists(tag: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "tag", "--list", tag],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return result.stdout.strip() == tag


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

    print("[OK] G1 temporal integrity tests run and pass without skips.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            f"Before {G1_TAG} exists, keep bootstrap CI non-strict. After the tag exists, "
            "the four G1 tests must run and pass without skips."
        ),
    )
    args = parser.parse_args()

    if args.ci and not git_tag_exists(G1_TAG):
        print(f"[INFO] {G1_TAG} not present; G1 strict gate is not active yet.")
        return

    run_selected_tests()
    print("G1 verification: PASS")


if __name__ == "__main__":
    main()
