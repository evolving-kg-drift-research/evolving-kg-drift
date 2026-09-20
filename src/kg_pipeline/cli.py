"""CLI wiring for the implemented Ticket A surface only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .gates import evaluate_gate_a, latest_gate_a_report
from .hashing import find_repo_root
from .inventory import run_inventory
from .run import get_run_dir, init_run, load_run_manifest
from .storage import read_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kg_pipeline", description="Evidence-first Data/KG rebuild controls")
    parser.add_argument("--repo-root", type=Path, help="Repository root; defaults to the current repository")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-run", help="Create a new immutable run namespace")
    init.add_argument("--run", required=True)
    init.add_argument("--mode", required=True, choices=("inventory",))
    inventory = commands.add_parser("inventory", help="Read raw input and write Ticket A artifacts")
    inventory.add_argument("--run", required=True)
    inventory.add_argument("--verify-inputs", action="store_true", help="Reconcile the upstream Stage 4.3 evidence before inventory")
    verify = commands.add_parser("verify", help="Evaluate the persisted Ticket A readiness gate")
    verify.add_argument("--run", required=True)
    verify.add_argument("--gate", required=True, choices=("A",))
    status = commands.add_parser("status", help="Show persisted run/input/gate status")
    status.add_argument("--run", required=True)
    return parser


def _root(argument: Path | None) -> Path:
    return argument.resolve() if argument else find_repo_root()


def _status(repo_root: Path, run_id: str) -> dict[str, Any]:
    manifest = load_run_manifest(repo_root, run_id)
    run_dir = get_run_dir(repo_root, run_id)
    input_lock_path = run_dir / "inputs" / "input_lock.json"
    gate_report = latest_gate_a_report(run_dir)
    readiness_path = run_dir / "reports" / "input_readiness_report.json"
    return {
        "run_id": run_id,
        "run_manifest_semantic_sha256": manifest.get("semantic_sha256"),
        "input_lock_status": read_json(input_lock_path).get("status") if input_lock_path.is_file() else "NOT_RUN",
        "gate_A_status": gate_report.get("status") if gate_report else "NOT_RUN",
        "gate_A_status_basis": "LAST_RECORDED_EVALUATION_NOT_LIVE_VERIFICATION",
        "ticket_A_implementation_status": read_json(readiness_path).get("implementation_status") if readiness_path.is_file() else "NOT_RUN",
        "run_dir": str(run_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        repo_root = _root(args.repo_root)
        if args.command == "init-run":
            payload = init_run(repo_root, args.run, mode=args.mode)
            exit_code = 0
        elif args.command == "inventory":
            payload = run_inventory(repo_root, args.run, verify_inputs=args.verify_inputs)
            exit_code = 0
        elif args.command == "verify":
            payload = evaluate_gate_a(repo_root, args.run)
            exit_code = 0 if payload["status"] == "PASS" else 2
        elif args.command == "status":
            payload = _status(repo_root, args.run)
            exit_code = 0
        else:  # argparse makes this unreachable, but keeps the entrypoint total.
            raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:  # noqa: BLE001 - CLI must return a nonzero code for any persisted-artifact failure.
        print(f"kg_pipeline: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    # ASCII escaping keeps CLI reports usable in Windows consoles configured with a legacy code page.
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return exit_code
