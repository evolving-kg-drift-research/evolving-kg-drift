#!/usr/bin/env bash
set -euo pipefail

# ===== EDIT THESE 7 VALUES =====
ORG_NAME="YOUR_GITHUB_ORG"
REPO_NAME="evolving-kg-drift"
VISIBILITY="private"   # private | public
M1_OWNER="M1_OWNER"
M2_OWNER="M2_OWNER"
M3_OWNER="M3_OWNER"
M4_OWNER="M4_OWNER"
# ===============================

git init
git branch -M main

python - <<PY
from pathlib import Path
p = Path(".github/CODEOWNERS")
text = p.read_text(encoding="utf-8")
for old, new in {
    "@M1_OWNER": "@${M1_OWNER}",
    "@M2_OWNER": "@${M2_OWNER}",
    "@M3_OWNER": "@${M3_OWNER}",
    "@M4_OWNER": "@${M4_OWNER}",
}.items():
    text = text.replace(old, new)
p.write_text(text, encoding="utf-8")
PY

python -m venv .venv
if [[ "${OS:-}" == "Windows_NT" ]]; then
  PY=".venv/Scripts/python.exe"
else
  PY=".venv/bin/python"
fi

"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.lock.txt
"$PY" -m ruff check .
"$PY" -m pytest -q
"$PY" scripts/verify_w1.py --ci
"$PY" scripts/verify_g1.py --ci
"$PY" scripts/verify_w7.py --ci
"$PY" scripts/check_freeze.py

git add -A
git commit -m "chore: bootstrap research repository"

if command -v gh >/dev/null 2>&1; then
  gh repo create "$ORG_NAME/$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --push
  echo "Created: $ORG_NAME/$REPO_NAME"
else
  echo "gh CLI not found. Local repo initialized only."
fi

echo
echo "No source-lock tag was created."
echo "Before Week-1 freeze, put exact authoritative sources under sources/."
echo "Then run:"
echo "  $PY scripts/freeze_w1.py"
echo "  git push origin v0.1-source-lock"
