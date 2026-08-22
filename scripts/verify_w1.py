from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "configs" / "protocol_v1.yaml"
SOURCE_MANIFEST_PATH = ROOT / "data" / "manifests" / "sources.lock.json"
W1_TAG = "v0.1-source-lock"

SOURCE_TO_PROTOCOL_KEY = {
    "proposal": "proposal_sha256",
    "execution_plan": "execution_plan_sha256",
    "patch": "patch_sha256",
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"[OK] {message}")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_protocol() -> dict:
    if not PROTOCOL_PATH.exists():
        fail("configs/protocol_v1.yaml is missing")
    with PROTOCOL_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def verify_repository_contract(protocol: dict) -> None:
    required_day1_paths = [
        ("temporal", "as_of_axis"),
        ("temporal", "revision_policy"),
        ("alignment", "anchor_policy"),
        ("drift", "query_aggregator_primary"),
        ("drift", "missing_support_primary"),
        ("h1", "population"),
        ("h1", "outcome"),
        ("h2", "primary_population"),
        ("h2", "primary_candidate_universe"),
        ("h2", "secondary_population"),
        ("h2", "secondary_candidate_universe"),
        ("h2", "frozen_unseen_candidate_score"),
        ("h2", "frozen_OOV_gold_RR"),
        ("h3a", "primary_population"),
        ("h3a", "no_path_handling"),
    ]

    for section, key in required_day1_paths:
        if section not in protocol or key not in protocol[section]:
            fail(f"Missing Day-1 contract: {section}.{key}")
        value = protocol[section][key]
        if value is None or value == "":
            fail(f"Empty Day-1 contract: {section}.{key}")
        if isinstance(value, str) and value.startswith("TO_BE_FROZEN"):
            fail(f"Day-1 contract unresolved: {section}.{key}")
        ok(f"{section}.{key}")

    required_files = [
        "configs/data.yaml",
        "configs/kge.yaml",
        "configs/statistics.yaml",
        "data/manifests/sources.lock.json",
        "tests/test_hard_invariants.py",
        "tests/test_config_consistency.py",
        "src/temporal/schema.py",
        "docs/architecture.md",
        "docs/modules.md",
        "docs/data_and_artifacts.md",
        "docs/gates_and_freeze.md",
        "docs/team_handoff.md",
        "CONTRIBUTING.md",
        ".github/pull_request_template.md",
        "configs/schemas/experiment_manifest.schema.yaml",
        "experiments/MANIFEST_TEMPLATE.yaml",
        "scripts/verify_g1.py",
        "scripts/verify_w7.py",
        "scripts/freeze_protocol.py",
        ".github/workflows/ci.yml",
        ".gitattributes",
    ]
    for relative in required_files:
        if not (ROOT / relative).exists():
            fail(f"Missing required file: {relative}")
        ok(relative)


def verify_source_bytes(protocol: dict) -> None:
    if not SOURCE_MANIFEST_PATH.exists():
        fail("data/manifests/sources.lock.json is missing")

    manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    protocol_sources = protocol.get("sources", {})

    for source_name, protocol_key in SOURCE_TO_PROTOCOL_KEY.items():
        entry = manifest.get(source_name)
        if not isinstance(entry, dict):
            fail(f"Missing source manifest entry: {source_name}")

        relative_path = entry.get("path")
        expected = entry.get("sha256")
        if not relative_path or not expected:
            fail(f"Incomplete source manifest entry: {source_name}")

        source_path = ROOT / relative_path
        if not source_path.is_file():
            fail(
                f"Authoritative source file missing: {relative_path}. "
                "Place the exact source bytes before Week-1 freeze."
            )

        actual = sha256_file(source_path)
        if actual != expected:
            fail(
                f"Source hash mismatch for {source_name}: "
                f"manifest={expected}, actual={actual}"
            )

        protocol_hash = protocol_sources.get(protocol_key)
        if protocol_hash != expected:
            fail(
                f"Protocol/manifest hash mismatch for {source_name}: "
                f"protocol={protocol_hash}, manifest={expected}"
            )

        ok(f"verified source bytes: {source_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            "Before v0.1-source-lock exists, verify the scaffold/contracts but do not "
            "pretend source bytes are locked. After the tag exists, source-byte "
            "verification becomes mandatory."
        ),
    )
    args = parser.parse_args()

    protocol = load_protocol()
    verify_repository_contract(protocol)

    strict_sources = not args.ci or git_tag_exists(W1_TAG)
    if strict_sources:
        verify_source_bytes(protocol)
    else:
        print(
            "[INFO] W1 source tag does not exist yet; CI is checking scaffold/contracts only. "
            "Source-byte verification is mandatory in freeze_w1.py."
        )

    protocol_hash = hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()
    print(f"[INFO] protocol_v1.yaml sha256={protocol_hash}")
    print("Week-1 verification: PASS")


if __name__ == "__main__":
    main()
