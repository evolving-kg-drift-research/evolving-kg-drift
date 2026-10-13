# M1-001–M1-020 status after C4–C9 code work

Date: 2026-09-28. This matrix separates code status from production evidence.
`EXECUTED` means a production artifact-backed stage or gate ran; fixture tests
never count. `VERIFIED` records only the scope actually checked.

| Finding | IMPLEMENTED | TESTED | EXECUTED | VERIFIED |
|---|---|---|---|---|
| M1-001 Future mapping | Partial: as-of resolver and no current-catalog fallback in adjudication runner | 48 focused fixtures pass, including the real adjudication and snapshot runner functions | No | Fixture/code behavior only; missing stable MentionID/decision lineage and schema drift block production |
| M1-002 False G2 PASS | Yes: explicit run and blocked fallback | Fixture pass | No | Guard only; G2 blocked |
| M1-003 Artifact chain | Yes: recursive ArtifactRef checks | Fixture pass | No | Artifact-chain fixtures only |
| M1-004 Evidence-time basis | Partial: runner fail-closed | Fixture pass | No | Guard only; clock policy absent |
| M1-005 Ingestion fallback | Yes: no 2020/retrieval substitution | Fixture pass | No | Guard only; no real temporal input |
| M1-006 SourceClaim/conflicts | Partial: adjudication writes sorted `source-claims-v1` JSON and binds it by physical/semantic hash; conflicts/retractions stay pending | 25 focused fixtures and 176 `tests/kg_pipeline/` tests pass, including runner output and support/conflict behavior | No | Fixture-only; no approved source-independence/support-aggregation or conflict policy; schema drift remains |
| M1-007 Cross-run revisions | Partial: verified parent FactVersion store is loaded; declared parent with missing store now fails closed; prior facts remain append-only | 25 focused fixtures and 176 `tests/kg_pipeline/` tests pass, including missing-parent-store and cross-run support/conflict behavior | No | No real parent-run adjudication chain executed or independently verified; temporal inputs/Gate A block production |
| M1-008 Snapshot dependency hashes | Partial: `snapshot-manifest-v2` binds exclusion semantics; per-snapshot YAML manifest is a completed-stage output with physical/semantic ArtifactRef; M2 rechecks run/config/code/mapping/boundary bindings | C7 suite: 204 passed | No | Fixture manifest and lineage checks only; no production certificate |
| M1-009 Schema drift | Partial: exact YAML/runtime audit blocks consumers | Audit pass as BLOCKED | No | 9/17 tables blocked |
| M1-010 Locked cache replay | Partial: immutable cache plus input/model/tokenizer/prompt/schema/decoding/runtime/dependency fingerprints; locked mode pins local runtime | 52 focused fixtures pass, including cache replay, tampering, JSON ArtifactRef tampering | No | Fixture behavior only; local runtime fingerprint is asserted, not independently attested |
| M1-011 Evidence grounding | Partial: exact code-point span hash, body clean-text hash and normalization version linked by body variant manifest; extraction blocks missing version | 52 focused fixtures pass, including Unicode/grounding and extraction-runner blockers | No | Fixture/code behavior only; production source text and spans absent |
| M1-012 Text normalization | Partial: explicit identity version; runner refuses missing or unapproved NFC version | 52 focused fixtures pass | No | NFC policy and contract migration unapproved; 9/17 schema drift remains |
| M1-013 Config fail-open | Partial: locked mode validates frozen config, exact runtime/build dependency pins, authoritative protocol only, and rejects implicit ontology/mock defaults | C9-focused suite: 82 passed; full regression: 278 passed, 10 skipped | No | Guard behavior only; current `openai>=1.0.0` is not exactly pinned in lock; config baseline remains unapproved |
| M1-014 Gate A on lineage | Yes: gate bound through stage artifacts | Fixture pass | No | Gate-chain fixtures only |
| M1-015 Source acquisition/versioning | No production recovery | Existing readiness evidence | No | Production inputs remain blocked |
| M1-016 Acquisition scan boundary | Not yet production-audited | No new test | No | Not verified |
| M1-017 Neo4j parity | Partial: verified-run materializer reads canonical Parquet, writes append-only Neo4j entities/edges, reads back and compares exact sets plus temporal support | C8 fixture suite: 210 passed | No | Driver-double only; no Neo4j service/read-back or production Parquet |
| M1-018 Production readiness | No: inputs remain absent | Gate guards tested | No | BLOCKED in recorded progress; not re-evaluated here |
| M1-019 Frozen boundaries | Partial: snapshot runner requires run-bound config/code fingerprints and hashes the selected cutoff with its versioned boundary policy; M2 recomputes these bindings | C7 suite: 204 passed | No | Fixture checks only; no approved or production-locked boundary policy |
| M1-020 Snapshot provenance helper | Partial: canonical runner applies knowledge/acceptance → validity → revision → tombstone → mapping-as-of; hashes and cross-checks edge support/exclusion lineage into claims, facts, and provenance | C7 suite: 204 passed; targeted Ruff passes | No | Fixture/code behavior only; FactVersion-only helper is non-certifying; production stage and independent validation absent |

Before the final C9 hardening patches, full regression was **230 passed, 10
skipped**, with one existing pytz deprecation warning. After those patches,
focused tests were **25 passed, 4 deselected**, Ruff and `git diff --check` passed; a full
rerun could not complete because pytest temporary-directory access was denied
(`WinError 5`). The machine schema audit remains
**BLOCKED: 9 of 17 tables**. No production run, scientific gate, Stage 4.3
acquisition, Neo4j write, or M2 handoff was executed or verified.

## Follow-up on `codex/m1-thu-huong-remediation` — 2026-10-03

The new branch starts from `6000f38` and preserves the working-tree edits. The
legacy FactVersion snapshot view now applies world validity before revision
resolution, matching Stage 4.17. Both snapshot views validate duplicate IDs,
missing/not-yet-known or cross-LogicalFactID parents, cycles, and competing
effective children; ambiguous branches stop for adjudication rather than
selecting a timestamp/ID winner. This is IMPLEMENTED and TESTED at fixture tier:
35 focused snapshot/provenance tests passed, and targeted Ruff passed. Production
EXECUTED and independent VERIFIED remain No. See the
[package review](m1_thu_huong_package_review_20261003.md) and
[remediation plan](m1_thu_huong_remediation_plan_20261003.md).

## C4 follow-up — 2026-10-03

Added fixture regressions that call `run_adjudication` and `run_snapshot`:
adjudication leaves an alias unresolved when its mapping is available only
after evidence observation, and snapshots use the prior mapping before the
superseding decision's availability cutoff. The focused suite passed **48
tests** and targeted Ruff passed. The runner tests isolate policy/gate and
artifact I/O dependencies; they are not production execution or gate evidence.
Stable `MentionID`/`MappingDecisionID` lineage remains unavailable in runtime
contracts, `config/schema.yaml` still differs, and identity policy is not
approved. C4 is therefore only fixture-tested in part; production
EXECUTED/VERIFIED remain No.

## C5 follow-up — 2026-10-03

Focused extraction/evidence/cache/artifact-chain/locked-mode suite: **52 passed**;
targeted Ruff, full `ruff check .` (exit 0; filesystem warnings on inaccessible
temporary test directories), and C5 `git diff --check` passed. Runner rejects
missing normalization versions and NFC pending approval; locked replay now
requires a SHA-256 local runtime, dependency-lock, and parser fingerprint. The
extractor JSON manifest is physically and semantically bound by its producer
stage manifest. C5 is fixture-tested only: schema has no normalization field,
runtime attestation is still external, and production EXECUTED/VERIFIED remain
No. See [C5 report](m1_c5_text_provenance_20261003.md).

## C6 follow-up — 2026-10-03

Adjudication now persists source-level claim provenance in a deterministic
`source-claims-v1` JSON artifact and requests physical/semantic output binding
in the stage manifest. A declared parent without a verified FactVersion store
fails closed; same-proposition cross-run support does not create a new version,
and conflict/retraction remains pending. The focused suite passed **25 tests**;
all `tests/kg_pipeline/` passed (**176**) with one existing pytz warning.
Ruff reported no errors; the full-repository walk emitted access-denied
warnings for stale pytest temporary directories. C6 remains partial: source
independence and support aggregation lack approved policy/schema, production
adjudication was not executed, and no parent-run production chain was verified.
See [C6 report](m1_c6_claim_revision_20261003.md).

## C7 follow-up — 2026-10-03

Snapshot manifests now bind exclusion semantics and each per-snapshot YAML
manifest is bound to the completed snapshot producer stage. M2 verifies the
manifest/artifact chain, support and exclusion lineage, current Gate A binding,
and persisted artifact-backed G1/G2 certificates before returning datasets.
The public single-snapshot loader requires run context and delegates to this
verified path, closing direct Parquet loading around stage/gates. The relevant
suite (`tests/kg_pipeline/`, snapshot temporal tests, and M2 adapter tests)
passed **204 tests**; targeted Ruff passed. This establishes
fixture/code behavior only. `accepted_into_kg_at` remains absent from the
authoritative contract, schema drift remains 9/17, boundary policy is not
approved, and no production snapshot or M2 handoff was executed or verified.
See [C7 report](m1_c7_snapshot_certification_20261003.md).

## C8 follow-up — 2026-10-03

Added a verified-run Neo4j materializer that binds canonical Parquet and
FactVersion temporal support, performs additive writes, reads through a
separate transaction, and compares exact node/edge sets including temporal
support JSON. Relevant suite: **210 passed**, targeted Ruff passed. This uses an
in-memory driver double. No Neo4j Python driver or reachable Docker Engine is
available; Stage 4.10, `accepted_into_kg_at`, Gate A/G1/G2 and frozen producer
artifacts also block the real runner path. C8 is partial and not database-
verified. See [C8 report](m1_c8_neo4j_readback_20261003.md).

## C9 follow-up — 2026-10-03

Locked initialization now validates exact pins for both `project.dependencies`
and `build-system.requires`, and wraps an unlocked dependency declaration as a
run-initialization blocker before creating the run directory. Config bundling
uses only `configs/protocol_v1.yaml` as protocol authority; a locked run fails
closed when it is absent or malformed, even when `config/protocol.yaml` exists.
The CI workflow is explicitly code-only for gate helpers and does not invoke
artifact-backed G1/G2 certification; a contract test prevents accidental
scientific-gate invocation from the default workflow. C9 tests include draft
config, dependency pins, cache tampering, gate bypass, report/run binding, and
lineage checks.

The focused C9 suite passed **82 tests**. Full repository regression passed
**278 tests, 10 skipped**, with one existing `pytz` deprecation warning; all ten
skips are future M2/M3/M4 or locked-test workflow placeholders in
`tests/test_hard_invariants.py`. `ruff check src tests scripts` and scoped
`git diff --check` passed. No scientific locked production run or gate was
executed. C9 remains partial/blocked for production because the approved config
baseline is absent, `openai>=1.0.0` is not exactly pinned in the dependency
lock, production artifacts and Gate A/G1/G2 are unavailable, and C8 has no
real Neo4j read-back. See [C9 report](m1_c9_locked_ci_20261003.md).
