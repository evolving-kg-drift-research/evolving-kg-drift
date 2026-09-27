from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Gate G2 for M1 pipeline run")
    parser.add_argument("--run", type=str, help="Pipeline run ID to evaluate")
    parser.add_argument("--ci", action="store_true", help="CI verification mode")
    parser.add_argument("--code-checks", action="store_true", help="Structural diagnostics only; never certify G2")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "src"))
    from kg_pipeline.gates import evaluate_gate_g2, evaluate_m1_structure
    try:
        if args.code_checks:
            if not args.run:
                parser.error("--code-checks requires --run")
            report = evaluate_m1_structure(ROOT, args.run)
            label = f"CODE_CONFORMANCE_{report['status']}"
        else:
            report = evaluate_gate_g2(ROOT, args.run)
            label = f"{report['status']} G2"
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"gate": "G2", "status": "BLOCKED", "reason": str(exc)}))
        return 2
    print(json.dumps(report, indent=2))

    print(f"[{label}]")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
