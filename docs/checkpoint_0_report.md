# Checkpoint 0 — authority and compliance mapping

Date: 2026-09-20. Branch: `fix/data-pipeline-compliance`, created from `origin/feature/data_try` at `4c24da2028a53e54f992ea0b52ae1e4e9d857e52`.

Status: **DOCUMENTATION PREPARED; VALIDATION INCOMPLETE**. No scientific readiness or production stage is certified.

## Changes

- ADR 0007 records the user's explicit choice of original baseline and supersedes ADR 0006's placeholder/re-anchoring permission without deleting historical ADRs.
- A new decision is appended after existing decision records; no prior decision text is intentionally changed.
- `data_pipeline_compliance.md` maps all 24 diagram steps to operational stages and distinguishes code/config/scaffold from production evidence.
- `config_reconciliation.md` labels its old table historical and explains current hard-coded FROZEN versus unproven scientific freeze.
- Original source hashes and production artifacts remain unchanged. No pipeline code has been repaired in this checkpoint.

## Observations

- Working tree was clean before branch creation; no local main/KGE commit was merged.
- Direct inspection of protocol and source lock found the same three expected hashes.
- `git ls-files sources data/raw data/stage_4_3_runs runs` returned only `sources/README.md` and `data/raw/.gitkeep`. This is tracked-file evidence only, not a check for ignored/local production artifacts.
- The prior Stage 4.3 PASS and Ticket A BLOCKED report is preserved; its production files were not independently audited in this checkpoint.

## Verification

A command to parse decision JSONL, check unique decision IDs, inspect local artifact presence and run `git diff --check` was attempted but did not execute: the tool safety classifier was temporarily unavailable. Therefore JSONL validation, local ignored-file presence and diff whitespace checks remain **NOT RUN**, not PASS. Test suite not run; this checkpoint changes documentation/decision records only.

## Follow-up inspection

On the user's continuation request, the verification command was attempted again but the safety classifier remained unavailable; it did not execute. Dedicated file discovery returned only `sources/README.md` under `sources/`, and only `.gitkeep` under `data/raw/`; no Stage 4.3 production files were returned under `data/`. This narrows local availability but is not a hash audit or a search of other workspaces. `docs/PROGRESS.md` now distinguishes this incomplete checkpoint from its historical PASS/test results. No held-out payload was read.

## User-executed whitespace check

The user ran `git diff --check` in this session after the follow-up edits; it completed with no output or stderr. This verifies whitespace for the tracked diff at that point, not new untracked files, JSONL parsing, historical-byte preservation or runtime correctness. A subsequent assistant attempt to check git status and validate JSONL/prefix was blocked before execution by the same classifier outage. Those checks remain NOT RUN. This report update itself follows the user's whitespace check.

## Next action / stop

Complete read-only checkpoint verification once tools are available, including byte-prefix preservation of the original decision log and protocol/lock comparison. Then report the result. Ticket A runtime repairs remain the next checkpoint, not an implied completion of the 24-step pipeline. Do not rerun historical acquisition or start downstream processing to work around missing evidence.
