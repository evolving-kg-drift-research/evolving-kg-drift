from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
FREEZE_TAG = "protocol-v1-frozen"

# Git can enforce frozen tracked configuration/manifests. The locked-test payload is
# intentionally untracked, so pre-freeze access must be enforced by the W8 runner/access
# mechanism rather than pretending Git diff can protect local bytes.
SENSITIVE_PREFIXES = (
    "configs/",
    "data/manifests/",
)

ALLOWED_REASON_TYPES = {
    "engineering_failure",
    "implementation_bug",
    "documented_data_error",
    "upstream_integrity_failure",
}

PLACEHOLDERS = {
    "",
    "TODO",
    "TBD",
    "UNKNOWN",
    "AMEND-YYYY-NNN",
    "GITHUB_HANDLE",
}


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def tag_exists(tag: str) -> bool:
    return bool(git("tag", "--list", tag))


def resolve_diff_range() -> tuple[str, str]:
    # GitHub Actions passes these explicitly so we inspect THIS PR/push only,
    # not the entire history since the protocol freeze.
    base = os.getenv("FREEZE_BASE_SHA", "").strip()
    head = os.getenv("FREEZE_HEAD_SHA", "").strip()

    if base and head and set(base) != {"0"}:
        return base, head

    # Local fallback: inspect the current commit only.
    try:
        base = git("rev-parse", "HEAD^")
        head = git("rev-parse", "HEAD")
        return base, head
    except subprocess.CalledProcessError:
        return git("rev-list", "--max-parents=0", "HEAD"), git("rev-parse", "HEAD")


def changed_files(base: str, head: str) -> list[str]:
    output = git("diff", "--name-only", base, head)
    return [line.strip() for line in output.splitlines() if line.strip()]


def is_sensitive(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SENSITIVE_PREFIXES)


def nonempty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in PLACEHOLDERS
    if isinstance(value, list):
        return len(value) > 0
    return True


def path_covered(changed_path: str, affected_paths: list[str]) -> bool:
    for declared in affected_paths:
        declared = str(declared).strip()
        if not declared:
            continue
        if declared.endswith("/"):
            if changed_path.startswith(declared):
                return True
        elif changed_path == declared:
            return True
    return False


def validate_amendment(path: Path, sensitive_paths: list[str]) -> None:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"[FAIL] Cannot parse amendment {path}: {exc}")

    if not isinstance(data, dict):
        raise SystemExit(f"[FAIL] Amendment {path} must be a YAML mapping.")

    for key in ("amendment_id", "reason_type", "failure_reason", "affected_paths"):
        if not nonempty(data.get(key)):
            raise SystemExit(f"[FAIL] {path} has missing/placeholder field: {key}")

    if data["reason_type"] not in ALLOWED_REASON_TYPES:
        raise SystemExit(
            f"[FAIL] {path} reason_type={data['reason_type']!r} is not allowed after freeze. "
            f"Allowed: {sorted(ALLOWED_REASON_TYPES)}"
        )

    affected_paths = data["affected_paths"]
    if not isinstance(affected_paths, list):
        raise SystemExit(f"[FAIL] {path} affected_paths must be a list.")

    uncovered = [p for p in sensitive_paths if not path_covered(p, affected_paths)]
    if uncovered:
        raise SystemExit(
            f"[FAIL] Amendment {path} does not cover sensitive paths: {uncovered}"
        )

    evidence = data.get("evidence")
    change = data.get("change")
    audit = data.get("audit")

    if not isinstance(evidence, dict) or not nonempty(evidence.get("failing_test")):
        raise SystemExit(f"[FAIL] {path} must identify a failing/reproduction test.")
    if not isinstance(change, dict) or not nonempty(change.get("new_tests")):
        raise SystemExit(f"[FAIL] {path} must list test(s) added/updated for the fix.")
    if not isinstance(change, dict) or not nonempty(change.get("new_version")):
        raise SystemExit(f"[FAIL] {path} must specify a new protocol/output version.")
    if not isinstance(audit, dict) or audit.get("old_run_retained") is not True:
        raise SystemExit(f"[FAIL] {path} must retain the old/contaminated run for audit.")


def main() -> None:
    if not tag_exists(FREEZE_TAG):
        print("[OK] Protocol is not frozen yet; W7 freeze gate inactive.")
        return

    base, head = resolve_diff_range()
    changed = changed_files(base, head)
    sensitive = [p for p in changed if is_sensitive(p)]

    if not sensitive:
        print("[OK] Freeze active; this PR/push does not change frozen paths.")
        return

    amendment_paths = [
        p for p in changed
        if p.startswith("amendments/")
        and p.endswith((".yaml", ".yml"))
        and not p.endswith("TEMPLATE.yaml")
    ]
    if not amendment_paths:
        raise SystemExit(
            "[FAIL] Frozen paths changed in this PR/push without a new/updated amendment."
        )

    # Every sensitive change must be covered by at least one amendment changed in THIS diff.
    covered: set[str] = set()
    errors: list[str] = []

    for rel in amendment_paths:
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            affected = data.get("affected_paths", []) if isinstance(data, dict) else []
            matched = [p for p in sensitive if path_covered(p, affected)]
            if matched:
                validate_amendment(path, matched)
                covered.update(matched)
        except SystemExit as exc:
            errors.append(str(exc))

    if errors:
        raise SystemExit("\n".join(errors))

    uncovered = [p for p in sensitive if p not in covered]
    if uncovered:
        raise SystemExit(
            f"[FAIL] Sensitive changes not covered by a valid amendment in this PR/push: {uncovered}"
        )

    print("[OK] Freeze active; current sensitive changes have a valid amendment trail.")


if __name__ == "__main__":
    main()
