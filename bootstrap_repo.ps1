$ErrorActionPreference = "Stop"

# ===== EDIT THESE 7 VALUES =====
$ORG_NAME   = "YOUR_GITHUB_ORG"
$REPO_NAME  = "evolving-kg-drift"
$VISIBILITY = "private"   # private | public
$M1_OWNER   = "M1_OWNER"
$M2_OWNER   = "M2_OWNER"
$M3_OWNER   = "M3_OWNER"
$M4_OWNER   = "M4_OWNER"
# ===============================

git init
git branch -M main

$codeowners = Get-Content ".github/CODEOWNERS" -Raw
$codeowners = $codeowners.Replace("@M1_OWNER", "@$M1_OWNER")
$codeowners = $codeowners.Replace("@M2_OWNER", "@$M2_OWNER")
$codeowners = $codeowners.Replace("@M3_OWNER", "@$M3_OWNER")
$codeowners = $codeowners.Replace("@M4_OWNER", "@$M4_OWNER")
Set-Content ".github/CODEOWNERS" $codeowners -Encoding UTF8

python -m venv .venv
$PY = ".\.venv\Scripts\python.exe"

& $PY -m pip install --upgrade pip
& $PY -m pip install -r requirements.lock.txt
& $PY -m ruff check .
& $PY -m pytest -q
& $PY scripts/verify_w1.py --ci
& $PY scripts/verify_g1.py --ci
& $PY scripts/verify_w7.py --ci
& $PY scripts/check_freeze.py

git add -A
git commit -m "chore: bootstrap research repository"

if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh repo create "$ORG_NAME/$REPO_NAME" "--$VISIBILITY" --source=. --remote=origin --push
    Write-Host "Created: $ORG_NAME/$REPO_NAME"
}
else {
    Write-Host "gh CLI not found. Local repo initialized only."
}

Write-Host ""
Write-Host "No source-lock tag was created."
Write-Host "Before Week-1 freeze, put exact authoritative sources under sources/."
Write-Host "Then run:"
Write-Host "  $PY scripts/freeze_w1.py"
Write-Host "  git push origin v0.1-source-lock"
