"""Comprehensive test verification script for evolving-kg-drift."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_command(cmd: list[str], desc: str) -> bool:
    print(f"\n{'='*70}\n[RUNNING] {desc}\n{' '.join(cmd)}\n{'='*70}")
    res = subprocess.run(cmd, cwd=ROOT)
    if res.returncode == 0:
        print(f"[PASS] {desc} succeeded.")
        return True
    else:
        print(f"[FAIL] {desc} failed with return code {res.returncode}.")
        return False


def main() -> int:
    print("Starting Comprehensive Test Suite Execution...")

    stages = [
        ([sys.executable, "scripts/verify_g1.py"], "Gate G1 Strict Verification"),
        ([sys.executable, "-m", "pytest", "tests/test_hard_invariants.py", "-v"], "10 Hard Invariants Suite"),
        ([sys.executable, "-m", "pytest", "tests/test_snapshot_runner.py", "-v"], "Snapshot Runner & Adapter Suite"),
        ([sys.executable, "-m", "pytest", "tests/temporal/", "-v"], "Temporal & Snapshot Logic Suite"),
        ([sys.executable, "-m", "pytest", "tests/kg_pipeline/", "-v"], "KG Pipeline Infrastructure Suite"),
        ([sys.executable, "-m", "pytest", "tests/", "-v"], "Full Repository Test Suite"),
    ]

    all_passed = True
    for cmd, desc in stages:
        success = run_command(cmd, desc)
        if not success:
            all_passed = False
            break

    print("\n" + "="*70)
    if all_passed:
        print("ALL VERIFICATIONS PASSED: 100% SUITE SUCCESS (0 ERRORS, 0 FAILURES)")
        print("="*70)
        return 0
    else:
        print("VERIFICATION FAILED: See details above.")
        print("="*70)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
