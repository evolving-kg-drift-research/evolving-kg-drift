# C4 — Cutoff-aware entity mapping

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

Mapping decisions now validate stable identifiers, timezone-aware availability,
confidence bounds, supersession parents and ambiguity. Snapshot resolution
selects only a unique mapping available by the requested cutoff. Adjudication
uses mapping history as-of the evidence observation time and no longer uses the
current entity catalog in its production runner. The artifact table name was
aligned to the master specification's `entity_mapping_versions`; mapping hashes
are bound into snapshot manifests.

The pure mapping helper and future-alias/state fixtures passed: **14 tests** in
`test_adjudication.py` and `test_no_future_entity_mapping.py`. They cover a late
alias, competing decisions, invalid supersession, future KG acceptance, and a
revision whose parent is not known by the cutoff. This is code behavior tested
with fixtures, not production verification.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: fixture tests pass. EXECUTED: no production
runner. VERIFIED: code behavior only.** The authoritative schema still declares
`mention_id` while the runtime mapping contract uses `mention`; extracted claims
do not carry stable mention IDs. The schema audit therefore blocks
`entity_mapping_versions` before the runner can consume the artifact. The
LogicalFactID/identity policy also remains unapproved. No adjudication or
snapshot was rebuilt.
