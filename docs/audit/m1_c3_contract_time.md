# C3 — Machine contract and temporal separation

Date: 2026-09-28. Base commit: `7f865a7` (C2).

## Implementation and validation

`config/schema.yaml` is now read as a machine contract. The `audit-schema` CLI
compares each declared field with the PyArrow schema and, for FactVersion, its
dataclass. The audit is exact: it does not silently identify `FactVersionID`
with `fact_version_id` or `claims` with `extracted_claims`. Production extraction,
adjudication, snapshot building and M2 run loading stop on relevant drift. A new
run records the YAML schema version and physical hash in its manifest and
proposed config bundle. Reusing a run after schema bytes change is rejected.

The actual repository audit is **BLOCKED: 9 of 17 declared tables differ**.
`retrievals` and `snapshot_edges` match; `claims` and
`entity_mapping_versions` have no corresponding runtime table;
`adjudication_decisions` and `fact_versions` omit required fields. In
`fact_versions`, `accepted_into_kg_at` is absent from both PyArrow and the
dataclass, while runtime `ingested_at_real` is not declared in the YAML table.
There is no approved lossless mapping or new contract version that permits
publication of those tables.

The pure adjudication helper now requires explicit timezones and preserves the
independent `ingested_at_real` argument even when a source has
`retrieved_at_real`. Invalid or naive extracted validity dates fail instead of
being converted to UTC or silently dropped. The runner no longer derives
observation from `recorded_event_at`/archive dates or ingestion from retrieval;
the 2020 fallback is gone. Until Stage 4.10 supplies a verified temporal input
with basis, confidence and an independent ingestion event, adjudication raises
an explicit blocker. A catalog without an independently evidenced mapping
availability time is also blocked. Structural snapshot diagnostics reject
naive cutoffs, observation and mapping times.

IMPLEMENTED and TESTED: these code guards and the machine audit. EXECUTED:
local fixture tests and a read-only audit of the current config. VERIFIED:
matching `retrievals` field round-trip, schema fingerprint invalidation, drift
blocking, strict timezone handling and separate ingestion/retrieval clocks.
The full regression suite after the code changes was **194 passed, 10 skipped**;
the final C3-specific suite after fingerprint, runner and CLI guard tests was
**9 passed**. Ruff and `git diff --check` passed. The single pytz deprecation
warning remains from the existing dependency. No fixture result is a scientific
gate PASS.

## Blocking specification and approval questions

The master spec and `config/protocol.yaml` require separate validity, public
evidence, KG acceptance, retrieval and adjudication clocks. Current runtime
Parquet collapses or lacks those fields. `docs/modules.md` additionally says to
use `ingested_at_real` as a scientific as-of axis, which conflicts with the
master spec's `evidence_observed_at` plus `accepted_into_kg_at` cutoff rule.
The master spec controls; this document was not edited to ratify code.

The approved schema migration must decide exact field names and types, the
source and admissible basis of each required clock, component versions and
which upstream tables require reprocessing. C3 cannot receive a production
PASS or a lossless FactVersion round-trip until that approval and Stage 4.10
input artifact exist. Gate A, G1/G2 and all production downstream stages remain
BLOCKED. No historical Stage 4.3 acquisition, raw bytes, source-lock hashes,
frozen artifacts or scientific decision log were changed.
