# M1 snapshot revision guard checkpoint — 2026-10-03

## Status

| IMPLEMENTED | TESTED | EXECUTED | VERIFIED |
|---|---|---|---|
| Yes, on `codex/m1-thu-huong-remediation` | 35 focused tests passed; targeted Ruff passed | No production stage | Fixture behavior and code only; no production artifact certification |

Snapshot-code checkpoint is closed at the fixture-tested tier. Production
Stage 4.17 and G1 remain BLOCKED by temporal/identity evidence and unapproved
policy.

## Finding M1-SNAPSHOT-021 — validity, revisions and lineage integrity

- **Severity:** HIGH.
- **Affected component:** `src/temporal/snapshot.py`.
- **Expected behavior:** Stage 4.17 filters knowledge/acceptance, then world
  validity, then resolves revision chains, then applies retraction tombstones
  and mapping as-of. Invalid or ambiguous lineage cannot silently produce a
  snapshot.
- **Previous behavior:** the FactVersion-only `build_snapshot` selected a
  superseding version before checking `valid_from`. A correction known now but
  effective in the future removed the old fact too early. Both snapshot
  functions also selected a timestamp/ID winner among competing children;
  a missing parent in the compatibility view or a cycle could be ignored.
- **Evidence:** review report for Thu Huong commit `e19fe25` records the
  future-effective reproduction (expected old fact, actual empty). Source
  review of the current base confirms the compatibility function resolved
  supersession before validity and the production helper chose a tie winner.
- **Root cause:** confirmed ordering and lineage handling in code. This finding
  does not prove that the ZIP contains real late corrections; its FactVersion
  rows are all `creation`.
- **Change:** both snapshot functions filter valid versions before revision
  selection and call a shared revision graph validator. It stops on duplicate
  FactVersion IDs, missing/not-yet-known parent, cross-LogicalFactID parent,
  cycles and multiple effective children of one parent. Competing revisions
  are sent to adjudication rather than decided by lexical tie-breaking.
- **Reproduction/verification performed:** added cases in
  `tests/temporal/test_snapshot.py` for future-effective correction/retraction,
  acceptance after cutoff, missing acceptance, missing/cross-ID parents,
  cycles, duplicate FactVersion IDs and competing effective children; the
  correction/retraction cases call both snapshot paths. Ran
  `python -m pytest -q --tb=short tests/temporal/test_snapshot.py tests/kg_pipeline/test_snapshot_provenance.py`
  (**35 passed**) and
  `python -m ruff check --no-cache src/temporal/snapshot.py tests/temporal/test_snapshot.py`
  (passed). Pytest needed filesystem access beyond the default sandbox because
  unprivileged Windows runs got `WinError 5` while enumerating temporary paths.
  No production runner or artifact was used.
- **Regression required:** future-effective correction/retraction, late
  correction, acceptance after cutoff, missing/future parent, duplicate ID,
  cross-LogicalFactID link, cycle, competing effective revisions and exact
  runner/compatibility agreement. Existing fixtures executed before the patch
  do not count as evidence for this revision.
- **Remaining blockers:** quality policy must say whether ambiguous rows are
  persisted as pending/quarantine or fail the entire stage—the code currently
  raises `ContractError`; compatibility `build_snapshot` intentionally lacks
  acceptance/mapping clocks and must not certify production output. No
  production artifact-backed stage was executed or verified.
