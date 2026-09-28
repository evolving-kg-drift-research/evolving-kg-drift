# C8 — Integration parity and Neo4j read-back

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

The parity helper rejects duplicate node/edge identities and compares exact
node and edge sets, including snapshot and temporal metadata when supplied.
It detects same-count set mismatches. Focused parity tests: **3 passed**.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: parity helper fixtures pass. EXECUTED: no
Neo4j materialization. VERIFIED: fixture set comparison only.** This checkout
has no isolated Neo4j test database, locked driver/runtime, or canonical frozen
Parquet set. No production runner vertical slice or read-back was executed;
counts or helper results do not certify Stage 4.18 set equality. M1 remains
blocked at Gate A and earlier schema/policy gates.
