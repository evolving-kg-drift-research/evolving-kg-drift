# C1 — Scientific gate guards

Date: 2026-09-28. Parent baseline: `6ed5a1a` (C0 report), runtime baseline `7dac5d3`.

## Scope and outcome

IMPLEMENTED and TESTED: G1/G2 command-line verification requires an explicit run.
Missing or unverified runs return BLOCKED with exit code 2. G2 no longer selects
runs by modification time or substitutes synthetic tests. G1 no longer uses a
Git tag to exempt scientific verification. CI runs explicitly named code checks.

The former structural G2 evaluator is now `evaluate_m1_structure`, writes reports
under `gates/M1_STRUCTURE`, and labels counts as structural records. Its PASS is
not scientific certification. The fixture integration test asserts this separation.

Quality span diagnostics reject invalid thresholds and duplicate matching keys.
Zero evaluated records and incomplete gold coverage cannot PASS; undefined error
rates are null. This diagnostic is not the approved pilot quality protocol.

EXECUTED: code tests and lint only. VERIFIED: guard behavior within those tests.
No production run or scientific gate has been verified in this checkpoint.

## Validation evidence

- Full regression suite: **174 passed, 10 skipped**, one existing pytz deprecation
  warning (before three additional guard tests were added).
- Final guard suite: **16 passed**, including skipped helper tests, missing run,
  forged PASS report, and prohibition of Git/fixture subprocess fallback.
- `python -m ruff check src scripts tests`: passed.
- `git diff --check`: passed.

Tests ran with normal Windows temporary-directory access because sandboxed pytest
previously failed on directory permissions. Skipped tests are not gate evidence.

## Remaining blockers and next checkpoint

G1/G2 deliberately remain BLOCKED: artifact-backed scientific evaluators have not
yet been implemented. This guard is an interim fail-closed boundary, not completion
of the scientific verification system. Production remains blocked by Gate A and
missing locked originals, acquisition evidence, production artifacts and independent
human pilot annotations. No new scientific policy was inferred or approved.

C2 remains pending: producer stage manifests, immutable ArtifactRef bindings,
recursive lineage verification and mandatory M2 snapshot verification. C3–C9 and
production stages remain uncompleted. Historical Stage 4.3, raw data, source-lock
hashes and the scientific decision log were not changed.
