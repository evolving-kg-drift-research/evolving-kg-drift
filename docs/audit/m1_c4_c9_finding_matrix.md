# M1-001–M1-020 status after C4–C9 code work

Date: 2026-09-28. This matrix separates code status from production evidence.
`EXECUTED` means a production artifact-backed stage or gate ran; fixture tests
never count. `VERIFIED` records only the scope actually checked.

| Finding | IMPLEMENTED | TESTED | EXECUTED | VERIFIED |
|---|---|---|---|---|
| M1-001 Future mapping | Partial: as-of resolver and no catalog in runner | Fixture pass | No | Code behavior only; schema blocks runner |
| M1-002 False G2 PASS | Yes: explicit run and blocked fallback | Fixture pass | No | Guard only; G2 blocked |
| M1-003 Artifact chain | Yes: recursive ArtifactRef checks | Fixture pass | No | Artifact-chain fixtures only |
| M1-004 Evidence-time basis | Partial: runner fail-closed | Fixture pass | No | Guard only; clock policy absent |
| M1-005 Ingestion fallback | Yes: no 2020/retrieval substitution | Fixture pass | No | Guard only; no real temporal input |
| M1-006 SourceClaim/conflicts | Partial: helper and pending conflicts | Fixture pass | No | Code behavior only; no persistence contract |
| M1-007 Cross-run revisions | Partial: verified parent store loader and append-only merge | Helper pass | No | No production parent chain exercised |
| M1-008 Snapshot dependency hashes | Yes: required manifest bindings | Fixture pass | No | Manifest fixtures only |
| M1-009 Schema drift | Partial: exact YAML/runtime audit blocks consumers | Audit pass as BLOCKED | No | 9/17 tables blocked |
| M1-010 Locked cache replay | Partial: request/runtime fingerprints and immutable sidecar | Fixture pass | No | Code behavior only; no locked production cache |
| M1-011 Evidence grounding | Partial: cited span and subject/object grounding | Fixture pass | No | Code behavior only |
| M1-012 Text normalization | Partial: versioned identity/NFC utilities | Fixture pass | No | NFC not approved or activated |
| M1-013 Config fail-open | Partial: locked mode validates frozen config and direct dependency pins; extraction rejects implicit ontology/mock defaults | Focused pass; full rerun blocked by workspace temp permissions | No | Guard behavior only; current `openai>=1.0.0` is not exactly pinned in lock |
| M1-014 Gate A on lineage | Yes: gate bound through stage artifacts | Fixture pass | No | Gate-chain fixtures only |
| M1-015 Source acquisition/versioning | No production recovery | Existing readiness evidence | No | Production inputs remain blocked |
| M1-016 Acquisition scan boundary | Not yet production-audited | No new test | No | Not verified |
| M1-017 Neo4j parity | Partial: exact-set helper | Fixture pass | No | No Neo4j read-back |
| M1-018 Production readiness | No: inputs remain absent | Gate guards tested | No | BLOCKED in recorded progress; not re-evaluated here |
| M1-019 Frozen boundaries | Partial: locked snapshot rejects provisional policy | Fixture pass | No | Guard only; policy not approved |
| M1-020 Snapshot provenance helper | Partial: cutoff and lineage guards | Fixture pass | No | Fixture behavior only |

Before the final C9 hardening patches, full regression was **230 passed, 10
skipped**, with one existing pytz deprecation warning. After those patches,
focused tests were **25 passed, 4 deselected**, Ruff and `git diff --check` passed; a full
rerun could not complete because pytest temporary-directory access was denied
(`WinError 5`). The machine schema audit remains
**BLOCKED: 9 of 17 tables**. No production run, scientific gate, Stage 4.3
acquisition, Neo4j write, or M2 handoff was executed or verified.
