# C2 — Artifact chain and downstream handoff

Date: 2026-09-28. Base commit: `0db1fda` (C1).

## Result

IMPLEMENTED and TESTED at code level. Each canonical Parquet output now receives
an ArtifactRef recording producer run and stage, run-relative path, contract
version, physical SHA-256, semantic SHA-256 and row count. Stage manifests bind
their inputs to the producer manifest hash. Publication requires the inputs to
exist and verify, and outputs to match their sidecars and declared row counts.
Consumers verify the entire completed stage and run ancestry; missing sidecars,
missing or failed producer manifests, changed bytes, changed input bindings and
cycles block reads. A historical parent keeps its recorded code fingerprint;
only the active run must match the current workspace.

Inventory now publishes a producer stage manifest. Extraction, adjudication and
snapshot stages bind all canonical tables they read, including the per-snapshot
Parquet outputs. Gate A is checked against an intact report, run manifest, READY
input lock and inventory producer before these runners execute. Their stage
manifests bind the Gate A report. The CLI no longer offers an unverified Gate A
option. The M2 run adapter requires Gate A, a bound completed snapshot stage,
canonical Parquet integrity, a valid snapshot manifest, exact requested snapshot
IDs and nonempty snapshot selection. Direct single-file loading remains a
lower-level diagnostic interface.

Previously written runs without producer stage manifests cannot be silently
promoted to this contract. They require a new, independently validated run;
historical artifacts remain untouched. Fixture stubs in unit tests are local
test scaffolding and do not establish Gate A or scientific G1/G2 PASS.

## Validation

- Full regression suite after C2 code changes: **187 passed, 10 skipped**,
  one existing pytz deprecation warning.
- Final adversarial chain suite after adding the stage-cycle case: **11 passed**.
- Ruff (`src`, `scripts`, `tests`) and `git diff --check`: passed.
- Missing sidecar, edited bytes, missing/FAILED parent, changed producer binding,
  run and stage cycles, forged Gate A report, historical parent code version,
  missing snapshot manifest and missing requested snapshot all tested.

EXECUTED and VERIFIED here mean local fixture and code checks. No production
Stage 4.18, scientific gate or M2 artifact handoff was executed or certified.

## Blockers and deferred bindings

Gate A remains BLOCKED in the production workspace because locked originals,
acquisition evidence and approved input readiness are absent. G1/G2 remain
BLOCKED by their C1 guards. C2 does not certify scientific semantics.

The run manifests still do not bind every non-Parquet dependency (raw originals,
body blobs, resolved configuration, snapshot boundaries and per-snapshot YAML
manifests) to an externally frozen production certificate. These are explicit
C3/C5/C7/C9 work items. Source and temporal policy conflicts remain for those
checkpoints. Stage 4.3 historical acquisition, raw data, source-lock hashes and
the scientific decision log were not changed.
