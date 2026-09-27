# C0 — M1 baseline and finding map

Date: 2026-09-28
Audited baseline: `reconcile/pipeline-drift-compliance` at `7dac5d3d97268c17560c79def8e509272c73a5e9`
Status: **C0 COMPLETE; M1 SCIENTIFIC GATES NOT VERIFIED; PRODUCTION BLOCKED**

## Purpose and evidence boundary

C0 fixes the code and evidence baseline for the M1 remediation checkpoints. The attached audit was checked against the current checkout and authoritative `docs/data_pipeline_spec.md` and `docs/PROGRESS.md`. Audit conclusions were not promoted to scientific PASS based on test names, remediation status, or fixtures. Every M1-001 through M1-020 item below is either corroborated by current source/repository state or explicitly left for targeted verification in its owning checkpoint.

At the start of C0, the working tree was clean. HEAD matched the audited commit. No local `runs/` directory exists; `data/raw/` contains only `.gitkeep`; the tracked tree contains only `data/raw/.gitkeep` and `sources/README.md` for those paths. `docs/PROGRESS.md` records Gate A as BLOCKED. These facts establish that production lineage cannot be verified from this checkout; they do not prove that ignored artifacts do not exist elsewhere.

## Baseline checks

| Check | Result | Evidence and limit |
|---|---|---|
| Checkout identity | PASS | Branch and HEAD match the audit target; initially clean working tree. |
| `python -m pytest -q --tb=no` | PASS as code tests | 161 passed, 10 skipped, one `pytz` deprecation warning; Python 3.12. This does not certify G1, G2, production data, or scientific readiness. CI specifies Python 3.11. |
| `python -m ruff check .` | FAIL | `scripts/verify_g2.py:12` E402 (`kg_pipeline.gates` import follows `sys.path` mutation). Track with C1. |
| Production Gate A / G1 / G2 evidence | NOT VERIFIED / BLOCKED | No production run or run artifacts in this checkout; progress state says Gate A BLOCKED. |
| Network/hosted services | NOT USED | No acquisition, hosted API, LLM, or Neo4j action was run. |

## Finding-to-checkpoint matrix

“Confirmed” means the stated implementation gap is visible in the current source or checkout. “Verify” means the audit identified a credible issue, but C0 did not treat its narrative as sufficient proof; the named checkpoint must establish it with focused code-path evidence. Rebuild entries describe the downstream artifacts that would require a new run after an approved fix; immutable or historical artifacts must not be overwritten.

| Audit finding | C0 assessment / current evidence | Owning checkpoint; invariant and stage | Rebuild or production consequence |
|---|---|---|---|
| M1-001 Future entity mapping enters facts before as-of availability | **Confirmed.** `adjudicate.py` resolves against the configured catalog while making accepted facts, then emits mapping rows; snapshot resolution looks up the fact IDs as mentions in `temporal/snapshot.py`. | C4; no future mapping, component versioning; Stages 4.8, 4.11, 4.17. | Rebuild adjudication decisions, FactVersions, and snapshots in a new run after identity policy is approved. |
| M1-002 Fixture suite can print G2 PASS without a production run | **Confirmed.** `scripts/verify_g2.py` invokes `test_vertical_slice_m1.py` when it cannot select a run and prints `[PASS] Gate G2`. | C1; evidence-based gate; G2 after Stage 4.13. | Replace any affected gate report with a new artifact-backed evaluation; fixtures remain code-test evidence only. |
| M1-003 Stage manifests are not enforced as a completed artifact chain | **Partially confirmed.** Stage manifests record status and paths in `run.py`; table resolution may accept a table without a sidecar, and the M2 adapter verifies a snapshot manifest only when one exists. Full producer-consumer coverage remains for C2. | C2; deterministic rebuild and canonical Parquet; Stages 4.4–4.18. | Revalidate parent/child lineage and regenerate affected stage artifacts in new runs. |
| M1-004 Evidence-time basis is collapsed | **Confirmed.** Inventory preserves `recorded_event_time_field`, but adjudication consumes `recorded_event_at`/`archive_datetime` without persisting that basis. | C3; no future evidence and temporal provenance; Stages 4.4, 4.10–4.12, 4.17. | Rebuild adjudication decisions, FactVersions, and dependent snapshots when a permitted basis contract exists. |
| M1-005 `ingested_at_real` has a non-provenance fallback | **Confirmed.** `adjudicate.py` falls back to `2020-01-01T00:00:00Z` when no retrieval timestamp exists. | C3; temporal provenance and determinism; Stages 4.11–4.12. | Block affected FactVersions; rebuild downstream only from evidenced ingestion inputs. |
| M1-006 SourceClaim/conflict-decision layer is absent | **Verify in C6.** No production contract/table was established by C0 as an independent SourceClaim/conflict object. | C6; append-only provenance and versioned adjudication; Stages 4.11–4.13. | Add versioned decision artifacts only after the conflict policy is approved; rebuild decisions and facts. |
| M1-007 Revisions are not connected across runs | **Verify in C6.** Current adjudication path was inspected, but C0 did not establish a verified parent FactVersion input chain. | C6; append-only provenance and deterministic revisions; Stage 4.12. | New FactVersion chain and dependent snapshots; retain previous runs. |
| M1-008 Snapshot manifest omits dependency hashes | **Confirmed.** `create_snapshot_manifest` defaults entity-map, config, and code hashes to `"none"`; `snapshot_runner.py` calls it without supplying those dependencies. | C7; deterministic rebuild and component versioning; Stage 4.17. | Rebuild snapshot Parquet and manifests from verified dependencies in a new run. |
| M1-009 Schema authorities diverge | **Confirmed.** The YAML schema includes fields absent from runtime PyArrow schemas, including temporal/adjudication fields; `FactVersion` also carries basis fields not in the Parquet contract. | C3; version all semantics-affecting components; Stages 4.9–4.12. | Version contracts and rebuild affected tables and downstream snapshots; do not rewrite old Parquet. |
| M1-010 Extraction cache lacks locked replay provenance | **Confirmed as a contract gap.** Cache key uses prompt/model/config and stores a response JSON; C0 found no immutable request manifest binding tokenizer, schema, runtime, and all replay inputs. | C5; deterministic rebuild and component versioning; Stage 4.9. | New cache/extraction artifacts after cache contract is frozen; no hosted LLM/API. |
| M1-011 Evidence grounding is insufficient for accepted triples | **Partially confirmed.** Runtime claim contract exposes one span and text hash; broader subject/relation/object grounding needs targeted producer tests in C5. | C5; no unsupported evidence; Stages 4.9–4.10. | Rebuild claims, adjudication, FactVersions, and snapshots after grounding behavior is versioned. |
| M1-012 Clean text lacks NFC/normalization version | **Confirmed as implementation gap.** Inventory body extraction has no normalization-version field in its contract. Any normalization change is blocked pending a versioned policy; Stage 4.4 forbids changing normalization in production by assumption. | C5; immutable raw and deterministic rebuild; Stages 4.4, 4.9. | Preserve raw bytes; create new body variants and dependent artifacts only under approved normalization policy. |
| M1-013 Configuration parsing can fail open | **Verify in C9.** C0 did not complete adversarial review of every config-loading/fallback path. | C9; locked inputs and deterministic rebuild; all stages consuming config. | Reject unlocked configs; invalidate dependent outputs and create a new run when approved config changes. |
| M1-014 Gate A enforcement is inconsistent for staged parent runs | **Partially confirmed.** Runners expose optional `enforce_gate_a=False`; parent-table resolution validates some run manifests but does not itself prove the required stage gate passed. | C2; stage-gate discipline and provenance; Stages 4.4, 4.9, 4.11, 4.17. | Re-evaluate gate-linked lineage before publishing downstream artifacts. |
| M1-015 Source acquisition/versioning is incomplete in this M1 checkout | **Confirmed for this checkout.** Inventory recovers provenance from existing evidence; no production acquisition outputs or run are available here. | Production input restoration, then Stages 4.4–4.5; preserve append-only provenance. | Recover and validate original acquisition evidence; do not infer it from derived reports or rerun the locked Stage 4.3 history. |
| M1-016 Acquisition evidence scan trust boundary is too broad | **Verify at production Stage 4.4.** C0 did not finish enumerating all accepted roots and evidence types. | Input restoration / Stage 4.4; provenance and no future evidence. | Only eligible, verified acquisition records may populate retrieval/source-version artifacts. |
| M1-017 Neo4j parity is not implemented against a real store | **Confirmed as not verified.** Current parity helper compares supplied Python collections; no Neo4j materialization/database evidence exists in this checkout. | C8; canonical Parquet source of truth and Stage 4.18 set equality. | Materialize from frozen Parquet and read back all nodes/edges; rebuild materialization from Parquet if parity fails. |
| M1-018 Production input readiness remains blocked | **Confirmed.** `runs/` is absent locally, `data/raw/` has only `.gitkeep`, and progress records Gate A BLOCKED. | Input restoration; Gate A before downstream stages. | No downstream production artifacts can be certified until exact approved source inputs and provenance are available. |
| M1-019 Provisional snapshot boundaries are used operationally | **Verify in C7/C9.** Audit evidence is retained as a blocker; C0 did not certify whether current execution path bypasses boundary freeze requirements. | C7/C9; no downstream leakage; Stages 4.15–4.17. | Do not freeze or rebuild production snapshots until outcome-blind boundaries are registered and locked. |
| M1-020 Helper snapshot API permits fabricated provenance | **Verify in C7.** C0 did not establish the complete helper-to-production call surface. | C7; provenance and no future evidence; Stage 4.17. | Keep any test-only fixture path out of locked production execution; rebuild snapshots after production validation. |

The audit's listed false positives (immutable raw/CAS behavior, persisted extraction DLQ, strict claim provenance resolution, fail-closed snapshot runner fields, and per-snapshot edge identity) are not promoted to new defects by C0. The baseline suite passed, but this is not a separate production verification of those behaviors.

## C0 report and stop

- **Purpose:** establish the current M1 implementation and evidence baseline.
- **Inputs:** current source at the commit above; `docs/data_pipeline_spec.md`; `docs/PROGRESS.md`; user-provided M1 audit.
- **Code changed:** none. This report is the sole C0 artifact. No decision-log entry was made because C0 changes no scientific semantics.
- **Commands:** `git status --short`; `git branch --show-current`; `git rev-parse HEAD`; `git ls-files runs data/raw sources`; `python -m pytest -q --tb=no`; `python -m ruff check .`.
- **Validation:** repository identity PASS; baseline pytest PASS (161 passed, 10 skipped); Ruff FAIL (one E402); production artifact readiness BLOCKED; scientific invariants/G1/G2 NOT VERIFIED.
- **Scientific semantics changed:** NO.
- **Next checkpoint:** C1 — make G2 verification fail closed. **C1 was not started.**

Stop here. Test fixtures and this report do not certify a pipeline stage or grant authority to execute the next checkpoint.
