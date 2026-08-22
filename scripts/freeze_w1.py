from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAG = "v0.1-source-lock"


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def capture(*args: str) -> str:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


# Strict: actual authoritative source bytes must exist and match hashes.
run(sys.executable, "scripts/verify_w1.py")
run(sys.executable, "-m", "pytest", "-q")

if capture("git", "status", "--porcelain"):
    raise SystemExit("[FAIL] Working tree is not clean. Commit changes before W1 freeze.")

if capture("git", "tag", "--list", TAG):
    raise SystemExit(f"[FAIL] Tag {TAG} already exists.")

run("git", "tag", "-a", TAG, "-m", "Week 1 source and contract lock")
print(f"[OK] Created local tag {TAG}")
print(f"Push it with: git push origin {TAG}")
