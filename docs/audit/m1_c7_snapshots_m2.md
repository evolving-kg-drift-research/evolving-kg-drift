# C7 — Snapshot certification and M2 handoff

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

Snapshot selection now follows known/accepted time, world validity, revision,
tombstone and cutoff-specific entity mapping. Locked snapshot runs require an
explicit acceptance clock, a versioned boundary policy, mapping history and
frozen dependency hashes. Snapshot manifests bind fact-store and acceptance
clock, entity mappings, resolved configuration, boundary policy and code.
M2 checks a locked run, frozen configuration, completed producer lineage, Gate
A and artifact-backed G1/G2 certificates before loading the requested frozen
snapshot.

Focused snapshot/manifest/adapter/vertical-slice tests: **34 passed**. The
vertical slice currently proves that absent acceptance-time contract blocks
the real snapshot runner; it does not certify a snapshot.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: fixture tests pass. EXECUTED: no production
snapshot or M2 handoff. VERIFIED: code behavior only.** `accepted_into_kg_at`
is absent from `FactVersion` and the authoritative Parquet contract. The
boundary/identity policies and final G1/G2 certificates are unavailable. M2
therefore remains blocked, and no prior snapshot certificate was reused.
