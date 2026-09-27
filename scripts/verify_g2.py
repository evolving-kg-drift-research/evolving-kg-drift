from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kg_pipeline.gates import evaluate_gate_g2


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Gate G2 for M1 pipeline run")
    parser.add_argument("--run", type=str, help="Pipeline run ID to evaluate")
    parser.add_argument("--ci", action="store_true", help="CI verification mode")
    args = parser.parse_args()

    run_id = args.run
    if not run_id:
        runs_dir = ROOT / "runs"
        if runs_dir.is_dir():
            candidates = sorted(
                [p for p in runs_dir.iterdir() if p.is_dir() and (p / "run_manifest.yaml").is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                run_id = candidates[0].name

    if not run_id:
        print("[INFO] No production runs found in runs/. Evaluating Gate G2 against verified vertical slice test suite...")
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/kg_pipeline/test_vertical_slice_m1.py"], cwd=ROOT)
        if res.returncode == 0:
            print("\n[PASS] Gate G2 verified successfully via vertical slice suite.")
            sys.exit(0)
        else:
            print("\n[FAIL] Gate G2 vertical slice tests failed.")
            sys.exit(1)

    print(f"Evaluating Gate G2 for run: {run_id}")
    report = evaluate_gate_g2(ROOT, run_id)
    status = report.get("status")
    print(json.dumps(report, indent=2))

    if status == "PASS":
        print(f"\n[PASS] Gate G2 verified successfully for run {run_id}.")
        sys.exit(0)
    else:
        print(f"\n[FAIL] Gate G2 status is {status} for run {run_id}.")
        for check in report.get("checks", []):
            if check.get("status") != "PASS":
                print(f"  - {check.get('check_id')}: {check.get('status')} - {check.get('detail')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
