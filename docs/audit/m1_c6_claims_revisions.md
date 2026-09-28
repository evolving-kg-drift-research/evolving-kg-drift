# C6 — Source claims, adjudication and append-only revisions

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

`SourceClaim` represents each claim-to-source provenance path independently.
Same-proposition support is not treated as a correction; unsupported conflicts
and negative claims remain pending policy. An untrusted duplicate retains a
provisional review candidate without entering the accepted FactVersion set.
The adjudication code can load a previous FactVersion store only through the
parent run's verified artifact resolver, passes those facts into adjudication,
validates historical rows as append-only, carries prior rows into the new store,
and binds the parent artifact in the child stage manifest. Snapshot lineage now
rejects missing, future/unaccepted, or cross-LogicalFactID revision parents.

Focused adjudication/provenance/revision tests: **14 passed** in the targeted
set; the final full suite passed after an additional future-parent test.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: helper and fixture tests pass. EXECUTED: no
production adjudication. VERIFIED: code behavior only.** `SourceClaim` and
conflict decisions are not persistable under the current machine schema. The
runner is blocked by the unapproved Stage 4.10 temporal input and schema drift,
so the parent-store path has not been exercised against real stage artifacts.
Conflict, support-independence and LogicalFactID policies remain unapproved.
No historical FactVersion or decision was rewritten.
