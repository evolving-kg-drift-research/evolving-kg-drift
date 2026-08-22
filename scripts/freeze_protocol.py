from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAG = "protocol-v1-frozen"


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


run(sys.executable, "scripts/verify_w7.py")
run(sys.executable, "-m", "pytest", "-q")

if capture("git", "status", "--porcelain"):
    raise SystemExit("[FAIL] Working tree is not clean. Commit the W7 frozen state first.")

if capture("git", "tag", "--list", TAG):
    raise SystemExit(f"[FAIL] Tag {TAG} already exists.")

run("git", "tag", "-a", TAG, "-m", "Protocol v1 frozen for locked experiment")
print(f"[OK] Created local tag {TAG}")
print(f"Push it with: git push origin {TAG}")
