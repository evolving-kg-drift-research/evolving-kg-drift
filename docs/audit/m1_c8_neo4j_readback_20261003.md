# M1 C8 — Neo4j materialization and read-back parity

Date: 2026-10-03. Scope: code remediation and fixture verification on
`codex/m1-thu-huong-remediation`, based on working-tree state at `6000f38`.
No production runner, scientific gate, or real Neo4j database was executed.

## Implemented

- Added `materialize_verified_snapshot_to_neo4j`. It first calls the verified
  M2 run loader, then reads canonical snapshot edges/support and the producer-
  bound FactVersion Parquet. It refuses missing support or temporal metadata,
  including `accepted_into_kg_at`, before opening the database session.
- The materializer writes with parameterized Cypher through one write
  transaction and reads the graph back in separate read transactions. Writes
  use `MERGE` and set relationship properties only on creation; existing
  conflicting or stale records remain visible and make exact parity fail.
- Per-edge temporal support is stored as a deterministic JSON string containing
  each supporting FactVersionID and its world-validity, evidence-observation,
  and KG-acceptance clocks. The parity key now includes `edge_id`, snapshot,
  temporal support and the individual time fields when supplied. It checks full
  node/edge sets and rejects duplicate identities, including same-count
  temporal/support mismatches.
- The returned report binds snapshot manifest and Parquet physical hashes plus
  manifest semantic dependencies. Its scope is `technical_integration_only`;
  it is not a scientific gate certificate.

## Verification

- `tests/kg_pipeline/`, `tests/temporal/test_snapshot.py`, and
  `tests/scientific/test_snapshot_manifest_and_adapter.py`: **210 passed** on
  Python 3.12; one existing `pytz` deprecation warning.
- Targeted Ruff checks for `src/kg_pipeline/` and relevant parity/materializer
  tests: **passed**.
- Fixtures verify the materializer calls the verified-run loader before DB
  access, reads temporal support from Parquet, refuses missing acceptance time,
  detects Parquet mutation after loader validation, compares two independent
  same-content fixture runs, and catches same-count wrong temporal support.
  These use an in-memory driver double, not Neo4j.
- Environment inspection found no installed Neo4j Python driver and no
  reachable Docker Engine. No database was started and no image was pulled.

## Status and blockers

**IMPLEMENTED: partial. TESTED: 210 fixtures. EXECUTED: no real Neo4j or
production vertical slice. VERIFIED: fixture behavior only.**

- The required vertical slice cannot pass current production guards. Stage 4.10
  `_approved_temporal_inputs` deliberately blocks until approved temporal
  evidence exists; the authoritative FactVersion contract still lacks
  `accepted_into_kg_at`, and the machine-schema audit remains blocked at 9/17.
- Gate A and G1/G2 remain BLOCKED, so the verified M2 loader refuses real-run
  handoff. No frozen production Parquet package is available to materialize.
- A real Neo4j read-back, two independent runner-created run hashes, and
  Parquet-to-Neo4j set equality remain unverified. No fixture result in this
  report certifies Stage 4.18 or M1 completion.

C8 therefore remains partial and blocked on C3/policy/evidence and a separate
Neo4j test service. The helper is ready to exercise once those prerequisites
are supplied; it does not bypass them.
