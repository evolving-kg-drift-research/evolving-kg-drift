from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
FREEZE_TAG = "protocol-v1-frozen"
PROTOCOL_PATH = ROOT / "configs" / "protocol_v1.yaml"
STATS_PATH = ROOT / "configs" / "statistics.yaml"
W7_MANIFEST_PATH = ROOT / "data" / "manifests" / "w7_freeze.yaml"
W7_TEMPLATE_PATH = ROOT / "data" / "manifests" / "W7_FREEZE_TEMPLATE.yaml"


def fail(message: str) -> None:
    raise SystemExit(f"[FAIL] {message}")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def tag_exists(tag: str) -> bool:
    try:
        return bool(git("tag", "--list", tag))
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"Missing required file: {path.relative_to(ROOT)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return data


def contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        text = value.strip()
        return "TO_BE_FROZEN" in text or text in {"TODO", "TBD", "UNKNOWN", "TO_BE_SET"}
    if isinstance(value, dict):
        return any(contains_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_placeholder(v) for v in value)
    return False


def require_nonplaceholder(value: Any, name: str) -> None:
    if value is None or value == "" or contains_placeholder(value):
        fail(f"Unresolved W7 field: {name}")


def verify_configs() -> tuple[dict[str, Any], dict[str, Any]]:
    protocol = load_yaml(PROTOCOL_PATH)
    stats = load_yaml(STATS_PATH)

    for path in sorted((ROOT / "configs").glob("*.yaml")):
        data = load_yaml(path)
        if contains_placeholder(data):
            fail(f"Unresolved TO_BE_FROZEN/TODO value remains in {path.relative_to(ROOT)}")

    protocol_version = str(protocol.get("protocol_version", ""))
    if not protocol_version or "draft" in protocol_version.lower():
        fail("protocol_version must be a frozen/non-draft version before W7 tag")

    require_nonplaceholder(stats.get("primary_inference"), "statistics.primary_inference")
    wcb = stats.get("wcb")
    if not isinstance(wcb, dict):
        fail("configs/statistics.yaml must contain wcb.seed and wcb.draws")
    require_nonplaceholder(wcb.get("seed"), "statistics.wcb.seed")
    require_nonplaceholder(wcb.get("draws"), "statistics.wcb.draws")
    return protocol, stats


def verify_manifest(protocol: dict[str, Any], stats: dict[str, Any]) -> None:
    manifest = load_yaml(W7_MANIFEST_PATH)
    if contains_placeholder(manifest):
        fail("data/manifests/w7_freeze.yaml still contains unresolved placeholders")

    for key in (
        "protocol_version",
        "protocol_sha256",
        "git_commit",
        "data_hash",
        "snapshot_manifest_hash",
        "query_hash",
        "candidate_universe_hashes",
        "pseudo_hash",
        "wcb",
        "locked_access_state",
        "dry_run",
    ):
        require_nonplaceholder(manifest.get(key), f"w7_freeze.{key}")

    actual_protocol_hash = hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()
    if manifest["protocol_sha256"] != actual_protocol_hash:
        fail(
            "w7_freeze.protocol_sha256 does not match configs/protocol_v1.yaml: "
            f"manifest={manifest['protocol_sha256']} actual={actual_protocol_hash}"
        )

    if manifest["protocol_version"] != protocol.get("protocol_version"):
        fail("w7_freeze.protocol_version does not match protocol_v1.yaml")

    source_hashes = manifest.get("source_hashes")
    if not isinstance(source_hashes, dict):
        fail("w7_freeze.source_hashes must be a mapping")
    for key, expected in protocol.get("sources", {}).items():
        if source_hashes.get(key) != expected:
            fail(f"w7_freeze.source_hashes.{key} does not match protocol source hash")

    candidate_hashes = manifest.get("candidate_universe_hashes")
    if not isinstance(candidate_hashes, dict):
        fail("w7_freeze.candidate_universe_hashes must be a mapping")
    require_nonplaceholder(candidate_hashes.get("primary"), "candidate_universe_hashes.primary")
    require_nonplaceholder(candidate_hashes.get("secondary"), "candidate_universe_hashes.secondary")

    manifest_wcb = manifest.get("wcb")
    stats_wcb = stats.get("wcb", {})
    if not isinstance(manifest_wcb, dict):
        fail("w7_freeze.wcb must be a mapping")
    if manifest_wcb.get("seed") != stats_wcb.get("seed"):
        fail("w7_freeze.wcb.seed does not match configs/statistics.yaml")
    if manifest_wcb.get("draws") != stats_wcb.get("draws"):
        fail("w7_freeze.wcb.draws does not match configs/statistics.yaml")

    dry_run = manifest.get("dry_run")
    if not isinstance(dry_run, dict) or dry_run.get("completed") is not True:
        fail("W7 Dev dry-run must be completed before protocol freeze")
    require_nonplaceholder(dry_run.get("run_id"), "w7_freeze.dry_run.run_id")
    require_nonplaceholder(dry_run.get("manifest_sha256"), "w7_freeze.dry_run.manifest_sha256")

    commit = str(manifest.get("git_commit", ""))
    try:
        git("cat-file", "-e", f"{commit}^{{commit}}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail("w7_freeze.git_commit does not resolve to a commit in this repository")

    if manifest.get("dirty_state") is not False:
        fail("W7 frozen state must record dirty_state: false")


def verify_scaffold_only() -> None:
    required = [
        PROTOCOL_PATH,
        STATS_PATH,
        W7_TEMPLATE_PATH,
        ROOT / "scripts" / "freeze_protocol.py",
        ROOT / "docs" / "gates_and_freeze.md",
    ]
    for path in required:
        if not path.is_file():
            fail(f"Missing W7 scaffold file: {path.relative_to(ROOT)}")
    print("[INFO] W7 freeze tag not present; strict W7 state is not active yet.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ci",
        action="store_true",
        help=(
            "Before protocol-v1-frozen exists, validate only the W7 scaffold. After the tag "
            "exists, enforce the full frozen config/manifest state."
        ),
    )
    args = parser.parse_args()

    if args.ci and not tag_exists(FREEZE_TAG):
        verify_scaffold_only()
        return

    protocol, stats = verify_configs()
    verify_manifest(protocol, stats)
    print("W7 verification: PASS")


if __name__ == "__main__":
    main()
