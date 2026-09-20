# ADR 0007: Preserve the original authoritative source baseline

Status: Accepted (explicit user decision, 2026-09-20)

Supersedes: ADR 0006's permission to use placeholders or re-anchor source hashes.

## Context

ADR 0006 permits equivalent placeholders and recalculating the source lock. This conflicts with the master specification's evidence and gate discipline. During remediation planning, the user explicitly selected preserving the original baseline. ADR 0006 remains in the repository as historical context; it is not permission to bypass this decision.

## Decision

- Preserve the three authoritative source hashes in `configs/protocol_v1.yaml` and `data/manifests/sources.lock.json`.
- Restore the exact original bytes for proposal, execution plan and patch. Missing, substituted, malformed or mismatched originals keep source readiness BLOCKED.
- Do not manufacture placeholder originals or change the expected hashes to match available substitutes.
- Any future replacement requires a separate explicit scientific amendment, a new baseline version and impact/reprocessing assessment; it must preserve the old baseline.
- ADR 0005's technical Ticket A configuration baseline is not evidence of completed ontology pilot or full pipeline freeze. Those require their own stage artifacts and validation under the master specification.

## Consequences

The present source lock already matches the protocol hashes; no lock/config edit is required by this decision. Runtime enforcement still needs the planned Ticket A repair: all three roles and actual bytes must be compared against both lock and protocol. Documentation acceptance is not runtime validation and does not turn any existing run into PASS.

Keep historical Stage 4.3 and Ticket A reports intact. Validate future work in a new run namespace. No historical acquisition, extraction or Neo4j write is authorized by this ADR.
