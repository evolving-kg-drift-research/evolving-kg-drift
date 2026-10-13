# Data pipeline compliance — checkpoint 0

Date: 2026-09-20. Reviewed baseline: `4c24da2` (`origin/feature/data_try`).

This is an implementation/evidence map, not certification of production data. Runtime repairs and downstream implementation remain pending. The master operational specification is `docs/data_pipeline_spec.md`; numbering in the 24-step diagram does not replace operational stage gates.

## Authority

ADR 0007 supersedes ADR 0006's placeholder/re-anchoring permission following the user's explicit choice to preserve original source bytes. `configs/protocol_v1.yaml` and `data/manifests/sources.lock.json` currently agree on all three source hashes. No hash, ontology or time policy is changed in this checkpoint. A technical configuration label `FROZEN` does not certify pilot/scientific freeze.

## Coverage map

`Partial` means some code/config exists, not production PASS. `Unverified` means evidence has not been established in this checkout. `Scaffold` means required execution is not implemented on this branch.

| Diagram step | Operational scope | Existing reference / required output | Status and remaining validation |
| --- | --- | --- | --- |
| 01 Protocol / cutoff | 4.1, 4.16 | `configs/protocol_v1.yaml`, `config/protocol.yaml`; frozen protocol/boundaries | Partial: original authority retained; reconcile distinct baseline and boundary freezes. |
| 02 Source registry | 4.2 | `config/sources.yaml`, `config/corpus_scope.yaml` | Config present; actual source eligibility and acquisition evidence unverified. |
| 03 Article selection | 4.6 | `config/filter_policy_v1.yaml`; corpus/filter decisions/audit | Config is not an executable validated filtering stage. |
| 04 Pilot | 4.7 | 30–50 articles, independent annotations, pilot report | Unverified; do not infer completion from ontology config. |
| 05 Ontology freeze | 4.7 | `config/ontology.yaml`, relation contracts, LogicalFactID rules | Partial: ADR 0005/config exists; pilot-based scientific freeze still requires evidence. |
| 06 Preflight tests | Cross-stage, 4.13 | `tests/kg_pipeline/`, `tests/test_hard_invariants.py` | Partial: Ticket A tests exist; temporal/parity invariant tests skipped; fingerprint/gate repairs required. |
| 07 URL discovery | 4.3 | Upstream discovered URLs, archive candidates, discovery log | Historical PASS recorded in `docs/PROGRESS.md`; not independently re-certified here; do not rerun acquisition. |
| 08 Historical recovery | 4.3–4.4 | `inventory.py`, `reconcile.py`; acquisition/recovery ledger | Partial: strict acquisition origins need enforcement; downstream reports cannot substitute original evidence. |
| 09 Immutable source | 4.4 | `storage.py`, raw inventory/hash audit | Partial: concurrency, integrity verification and retry repair required. |
| 10 Time fields | 4.4, 4.10 | `contracts.py`, `config/schema.yaml` | Partial: strict timestamp parsing and basis needed; publication/observation/retrieval/ingestion remain distinct. |
| 11 News lineage | 4.4–4.5 | source_versions, retrievals, lineage_edges schemas | Partial: event/content identity and evidence-backed edges need correction. |
| 12 Dedup/filter | 4.5–4.6 | body variants, clusters, memberships; filtered corpus | Exact clustering exists; preserve temporal states, validate PK/FK, add filter evidence; no unapproved fuzzy inference. |
| 13 Entity identity | 4.8 | entity mentions/catalog/mapping versions | Downstream implementation required; enforce mapping_available_at as-of. |
| 14 Claim candidates | 4.9 | claims, extractor manifest | Downstream implementation required; candidates must not auto-become accepted facts. |
| 15 Evidence spans | 4.9 | claim_evidence and immutable body refs | Downstream implementation required; exact offsets/text/hash and claim support validation. |
| 16 Validity | 4.10 | claims_temporal, evidence_time_provenance | Downstream implementation required; no invented historical known-time. |
| 17 Adjudication | 4.11 | decisions, accepted claims, pending conflicts | Downstream implementation required; independent provenance groups, reasons, acceptance known-time and real review time. |
| 18 FactVersion store | 4.12 | `src/temporal/schema.py`; fact versions/lineage/manifest | Dataclass scaffold; append-only store and full contract required. |
| 19 As-of rules | 4.17 | `src/temporal/snapshot.py` | Scaffold (`NotImplementedError`): known/acceptance filter, validity, revision resolution, retract, mapping as-of. |
| 20 Build slices | 4.15–4.17 | events, boundaries, snapshot manifests | Implementation required; deterministic outcome-blind boundaries and stable IDs. |
| 21 Canonical Parquet | 4.17–4.18 | `storage.py`, `contracts.py`; nodes/edges/provenance | Inventory tables exist, not final snapshots; verify complete schema and physical/semantic hashes. |
| 22 Neo4j | 4.18 | Derived graph import/materialization | Implementation/integration required; never edit graph to fix canonical data. |
| 23 Parity / QA | 4.13, 4.18 | `gates.py`, invariant test scaffolds; parity report | Ticket A is not final QA; require real node/edge set equality, not counts or mock-only tests. |
| 24 Handoff | 4.14, 4.18 | pipeline/environment/lineage/hash manifests | Partial run metadata exists; final handoff remains blocked pending full gates. |

## Immediate remediation order

1. Enforce original source/config baseline and execution fingerprints.
2. Fail closed for partial/unresolved/invalid provenance; validate acquisition origin and timestamps.
3. Repair event/content identity, PK/FK, concurrency-safe immutable writes and deterministic scientific hashes.
4. Verify actual artifacts and append gate evaluations without overwriting prior reports.
5. Validate a new inventory run only with real available inputs; stop if BLOCKED.
6. Proceed stage by stage through pilot, extraction, adjudication, facts, quality, main corpus, boundaries, snapshots and real parity; each transition requires an explicit continuation request.

## Production evidence boundary

Tracked input listing at this checkpoint includes only `sources/README.md` and `data/raw/.gitkeep` for the inspected source/raw paths. A tracked listing alone does not establish whether ignored artifacts exist. The historical report is retained as historical evidence, not treated as a new audit of absent local files. No network fetch, acquisition, extraction or database write is performed by checkpoint 0.

## Checkpoint acceptance

- ADR 0007 and append-only decision establish authority without changing original hashes.
- This matrix separates implementation from scientific certification.
- Runtime false-PASS issues are deliberately still open until the next checkpoint.
- Validation outcomes are recorded in `docs/checkpoint_0_report.md`; no production gate PASS is issued here.
