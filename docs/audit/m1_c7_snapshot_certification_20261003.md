# M1 C7 — Snapshot certification and M2 handoff

Date: 2026-10-03. Scope: code remediation and fixture verification only on
`codex/m1-thu-huong-remediation`, based on `6000f38`. No production stage,
scientific gate, Neo4j write, or M2 production handoff was run.

## Implemented

- Snapshot manifest contract `snapshot-manifest-v2` now includes an exclusion
  semantic hash alongside graph, support, fact-store, acceptance-clock,
  mapping, resolved-config, boundary, and code fingerprints. The manifest hash
  covers semantic fields, and unsupported versions or unbound hashes fail
  closed.
- Snapshot runner requires run-bound config-bundle and code fingerprints,
  includes the config-bundle fingerprint in the resolved-config hash, and
  binds each per-snapshot YAML manifest as an output of the completed snapshot
  stage.
- YAML ArtifactRefs check producer run/stage, relative path containment,
  contract version, physical bytes, and semantic hash. Stage verification
  requires `COMPLETED`, verifies all declared output artifacts/manifests and
  recursively checks parent stage bindings.
- M2 run loading requires current Gate A binding, a frozen scientific run,
  supported snapshot manifests, matching code/config/boundary/mapping hashes,
  producer-bound edge/support/exclusion artifacts, verified sidecars, and
  support/exclusion lineage back to the FactVersion and claim-provenance
  inputs. G1/G2 must each have a persisted, current, artifact-backed PASS
  certificate before datasets are returned.
- The public single-snapshot M2 loader now requires run context and delegates
  to the same verified run loader. Its standalone local-Parquet reader is
  private and used internally only after producer lineage and gates are
  checked, closing the direct-load bypass.
- The canonical runner path applies knowledge and acceptance, world validity,
  revision resolution, retraction tombstones, then cutoff-specific entity
  mapping. Ambiguous revisions remain a blocker; the code does not invent a
  winner. The FactVersion-only helper is non-certifying and cannot be consumed
  through the public M2 loader.

## Verification

- `tests/kg_pipeline/`, `tests/temporal/test_snapshot.py`, and
  `tests/scientific/test_snapshot_manifest_and_adapter.py`: **204 passed** on
  Python 3.12; one existing `pytz` deprecation warning.
- Targeted Ruff checks for the changed snapshot, run-manifest, adapter, and
  related test files: **passed**.
- The tests cover fixture behavior, including YAML manifest tampering,
  output-manifest binding, M2 support/exclusion lineage, and snapshot
  manifest/config/mapping/boundary checks, the public-loader bypass, and the
  verified-run route. They do not certify real artifacts.

## Status and blockers

**IMPLEMENTED: partial. TESTED: 204 fixtures. EXECUTED: no production stage.
VERIFIED: fixture/code behavior only.**

- The authoritative FactVersion contract still lacks
  `accepted_into_kg_at`; the machine-schema audit remains blocked at 9 of 17
  tables. The snapshot runner must keep refusing production inputs without the
  approved clock contract.
- Boundary, identity/mapping, and acceptance-time policies are not approved or
  locked for a production run.
- Gate A and G1/G2 have no verified production PASS certificates. The M2
  loader's fixture certificates are test-only.
- No real frozen snapshot package, source-to-snapshot lineage sample, or
  Neo4j database read-back has been verified. C7 therefore does not authorize
  a production M2 handoff.

The next code checkpoint is C8, the production-runner vertical slice and
Neo4j read-back integration tests; production execution remains separately
blocked by the evidence and policy requirements above.
