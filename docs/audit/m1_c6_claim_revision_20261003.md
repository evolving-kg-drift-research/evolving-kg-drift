# M1 C6 — source claims and append-only revisions

Date: 2026-10-03. Scope: code and fixture validation only.

## Implementation

`run_adjudication` now writes a deterministic `source_claims-v1` JSON artifact.
Each record preserves a claim's provenance path through the claim, membership,
source version, retrieval, raw-blob hash, publisher and URL. Records are sorted
stably and the manifest carries a semantic hash; the adjudication stage binds
its physical and semantic hashes through `output_manifests`. This records
source paths without declaring that they are independent sources.

When a child run declares a parent, adjudication now stops if the verified
parent FactVersion artifact cannot be resolved. If present, the existing
append-only path loads and validates the prior records, carries them into the
new run, and does not rewrite them. New same-proposition support without a
support-artifact policy, competing propositions, and negative/retraction
claims remain pending. The code does not infer a correction rule.

## Verification

Focused adjudication, provenance and artifact-chain tests: **25 passed**; the
full `tests/kg_pipeline/` suite: **176 passed**, with one existing pytz
deprecation warning, on Python 3.12. Tests cover the runner's
SourceClaim output, stage-manifest binding request, unresolved late mapping,
missing parent-store failure, append-only FactVersion behavior,
same-proposition support, and pending conflict/retraction behavior. These are
fixtures; no production stage or independent artifact-chain verification was
executed.
Targeted Ruff and repository-wide `ruff check .` reported no lint errors; the
repository-wide walk emitted access-denied warnings for old pytest temp folders.
`git diff --check` passed for the C6 files.

## Status and blockers

**IMPLEMENTED: partial. TESTED: focused fixtures pass. EXECUTED: no production
adjudication. VERIFIED: fixture behavior only.** The source-level artifact has
a local `source-claims-v1` contract, but `config/schema.yaml` still has no
SourceClaim/support-aggregation contract, and the current code does not decide
source independence or persist an approved aggregation decision. Conflict,
correction, retraction and LogicalFactID policies remain unapproved. Stage 4.10
temporal inputs, Gate A and the 9/17 schema drift still block the production
runner. C6 is not a scientific gate PASS.
