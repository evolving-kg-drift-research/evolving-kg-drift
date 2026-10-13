# AGENTS.md — Operational Rules for AI Agents

> Repository: `evolving-kg-drift`
> Research Project: **Noise-Calibrated Representation Drift Quantification for Multi-Hop Reasoning on Evolving Knowledge Graphs**
> Operational Scope: Universal operational and safety rules for AI coding and audit agents (Claude Code, Codex, Cursor, and equivalents).

---

## 1. Project Context & Module Scope

### 1.1 Research Objective
The project quantifies genuine representation drift over retraining noise in evolving Knowledge Graph Embeddings (KGE) and evaluates its impact on multi-hop question answering (QA). The project does **not** invent a new KGE architecture.

**Critical Path Priority:**
$$\text{temporal integrity} \longrightarrow \text{measurement validity} \longrightarrow \text{locked experiment}$$

### 1.2 The 9-Stage Research Pipeline
1. **Temporal evidence ingestion** & provenance tracking.
2. **Append-only FactVersion store** across revisions.
3. **Deterministic as-of snapshot construction** at registered cutoffs.
4. **Controlled TransE-L2 backbone training** across fixed seeds (13, 37, 101).
5. **Centered Orthogonal Procrustes SVD alignment** on persistent anchor entities.
6. **Same-snapshot empirical null** estimation across degree buckets.
7. **Representation drift quantification** ($\delta_{time}$, signed excess $r$, $SED^+$).
8. **Recurring multi-hop QA panel evaluation** (Arms A, B, C; Seen-at-T1; OOV scoring).
9. **Two-Way Fixed Effects estimation** ($H_1: \beta_d$, $H_2$) and pseudo-drift falsification.

### 1.3 Module Ownership Matrix
| Module | Source Directories | Primary Config | Core Responsibilities | Gates |
|---|---|---|---|---|
| **M1 — Data/KG** | `src/ingestion/`<br>`src/extraction/`<br>`src/temporal/`<br>`src/kg_pipeline/` | `configs/data.yaml`<br>`config/schema.yaml` | Ingest public news sources; preserve source provenance; extract FactVersion records append-only; build deterministic as-of snapshots by cutoff; verify Parquet–Neo4j parity. | **W1** (Source Lock)<br>**G1** (Temporal Integrity)<br>**G2** (Entity/Evidence Quality) |
| **M2 — Drift** | `src/kge/`<br>`src/drift/` | `configs/kge.yaml` | Controlled TransE-L2 training (seeds 13, 37, 101); Centered Procrustes SVD alignment; 6-pair same-snapshot empirical null with Leave-Target-Out; compute $\delta_{time}$, signed excess $r$, and $SED^+$. | **G3** (Backbone & Alignment Diagnostics) |
| **M3 — Auditor/Path** | `src/paths/`<br>`src/auditor/` | `configs/protocol_v1.yaml` | Simple bounded path features for Arm C with exact-B fallback; evidence-constrained semantic audit (`RETAIN/REPLACE/DECAY`). | **G5** (Support Modules Gate) |
| **M4 — Eval/Stats** | `src/evaluation/`<br>`src/statistics/` | `configs/statistics.yaml` | Recurring QA panel; Seen-at-T1 universe; Arm A/B/C rankings; OOV scoring; Two-Way Fixed Effects ($H_1$); Wild Cluster Bootstrap (WCB); pseudo-drift falsification. | **G4** (QA Panel & Power)<br>**G6 / W7** (Protocol Freeze) |

### 1.4 Track Prioritization
- **CORE (Strict Priority):** M1 (temporal integrity), M2 (alignment and drift over noise), M4 (QA and statistical estimation). Must never be blocked by secondary features.
- **SUPPORT:** M3 `paths` (Arm C simple paths; if no valid path exists, execute exact-B fallback) and `auditor` (semantic audit).
- **STRETCH:** QLoRA in auditor workflow (strictly optional; must never delay CORE deliverables).

### 1.5 Inter-Module Handoff Contracts
- `ingestion → extraction`: Raw immutable source records + acquisition metadata; no interpreted KG state.
- `extraction → temporal`: Structured evidence spans + candidate facts with source span hashes, extractor version, observation timestamps.
- `temporal → kge`: Canonical Parquet snapshots + entity/relation mappings + snapshot manifest/hash. KGE never constructs private snapshots.
- `kge → drift`: Model checkpoints, mapping hashes, seed identifiers, resolved config hash.
- `drift → evaluation/statistics`: Alignment/null/drift artifacts with complete diagnostics and hashes; no unprovenanced local dataframes.
- `evaluation → statistics`: Immutable RR/ranking rows and Query×Transition panels according to locked population and candidate universes.

---

## 2. Authority & Conflict Resolution

### 2.1 Source-of-Truth Hierarchy
When resolving requirements, schemas, or behaviors, consult sources in this strict order:
1. **Scientific Protocol & Authoritative Sources:** `configs/protocol_v1.yaml` and sources locked in `data/manifests/sources.lock.json` override all other documents on scientific parameters, populations, and estimands.
2. **Operational Data Pipeline Specification:** `docs/data_pipeline_spec.md` is the authoritative operational specification for M1 Stages 4.3 through 4.18.
3. **Architecture & Module Contracts:** `docs/architecture.md` and `docs/modules.md` govern software architecture, dependency rules, and handoffs.
4. **Runtime Schemas & Domain Implementations:** `config/schema.yaml` and `config/protocol.yaml` provide machine-readable contracts and runtime domain mappings; they must strictly conform to `configs/protocol_v1.yaml`.
5. **Execution Progress & Stage Gates:** `docs/PROGRESS.md` records mutable execution state, current gate status, and blockers. It reflects status only and does **not** grant authority to alter scientific semantics.
6. **Audit Reports & Remediation Records:** `docs/audit/` provide evidence, findings, and diagnostic logs. Audit reports do not supersede protocol.
7. **Decision Log & Formal Amendments:** `decisions/decision_log.jsonl` (append-only, reserved exclusively for scientific/semantic decisions) and `amendments/*.yaml` (formal post-freeze changes with failure reason, repro evidence, regression test).

### 2.2 Fail-Closed Conflict Resolution
- If two authoritative sources conflict: **STOP**, report the conflict, and do not make an unauthorized semantic decision.
- If information is insufficient for an issue affecting scientific semantics, data population, or temporal behavior: **STOP** and request user clarification.
- If missing engineering detail does not affect semantics: implement the minimal, deterministic, auditable solution and document the assumption in the execution report.

---

## 3. Architecture Rules & Hard Scientific Invariants

Never violate the following hard scientific invariants under any circumstance:

1. **No Future Evidence (INV-01):** `evidence_observed_at <= snapshot_cutoff`. No fact, claim, or revision observed after the cutoff may enter the snapshot.
2. **No Future Entity Mapping (INV-02):** `mapping_available_at <= snapshot_cutoff`. Entity resolution must not use future identity merges or catalogs.
3. **Three-Way Temporal Axis Separation:**
   - *World validity (`valid_from`, `valid_to`):* When the fact held in reality.
   - *Evidence observation (`evidence_observed_at`):* The scientific as-of timeline when evidence became publicly available.
   - *Project acquisition (`retrieved_at_real`, `ingested_at_real`):* Engineering timestamp when the crawler fetched the payload.
   *Rule: Never interchange or substitute these three axes.*
4. **Append-Only Provenance (INV-03):** Raw content, retrievals, and the `FactVersion` store are append-only. Zero deletion, truncation, or in-place modification of historical records.
5. **Zero Overwrite of Immutable States:** Rebuilds must produce new versions/runs, preserve prior artifacts, and log supersession.
6. **Deterministic Rebuild (INV-04):** Identical inputs + frozen config + mappings + component versions must yield identical outputs (exact SHA-256 match).
7. **Outcome Blindness (No Downstream Leakage, INV-06):** Downstream results (drift magnitude, $SED^+$, RR, MRR, QA scores, H1 effect) must **never** influence upstream decisions (corpus filtering, snapshot cutoffs, anchor selection, degree-bucket boundaries, null rules).
8. **Component Versioning:** Every semantics-affecting component must be explicitly versioned (ontology, LogicalFactID rules, extractor, entity mapping, temporal parser, adjudication, snapshot builder, filtering, deduplication).
9. **Canonical Parquet as Ground Truth:** Parquet is the sole source of truth; Neo4j is purely a materialization/query layer.
10. **Parquet–Neo4j Parity (INV-05):** Stage 4.18 requires verified node/edge set equality between canonical Parquet and Neo4j.
11. **Hash-Addressable Artifact Lineage:** Every analysis artifact must record `git_commit`, `dirty_state`, resolved `config_hash`, input hashes, seed, and output hash via experiment manifests matching `configs/schemas/experiment_manifest.schema.yaml`.

---

## 4. Coding Rules & Implementation Standards

1. **Repository-First Inspection:**
   - Always inspect real file paths, schemas (`config/schema.yaml`), CLI flags, configs, tests, and outputs before modifying code.
   - Discover actual behavior from code; never guess column names, types, or CLI options.
2. **Scope-Limited Changes & Minimal Diffs:**
   - Touch only files directly required for the task.
   - Avoid sweeping stylistic refactoring, unsolicited reformatting, or extraneous file creation.
3. **Zero Synthetic Defaults in Production:**
   - Never hardcode mock embeddings, dummy spans `[0, 1)`, synthetic hashes, or fallback timestamps (e.g., year 2020) into production paths. Synthetic defaults belong strictly in unit test fixtures.
4. **No Threshold or Metric Tampering:**
   - Never alter validation thresholds, alpha levels, epsilon values, or metric definitions to force a failing test to pass.
5. **Fail-Closed on Missing Data:**
   - Missing evidence, missing timestamps, unresolved entities, unapproved schemas, or missing manifests must raise fatal errors or divert to structured quarantine (`snapshot_exclusions.parquet`). Never fail open or silently drop invalid data.
6. **Preserve Historical Immutability:**
   - Never rewrite historical timestamps or overwrite raw data to mask upstream bugs.
7. **Backward Compatibility & Downstream Impact:**
   - When interface changes are necessary and approved, identify downstream consumers (e.g., M1 snapshot changes affecting M2 KGE adapter) and update regression coverage within permitted task scope.
8. **Code Quality & Tooling Consistency:**
   - Target Python 3.10 and 3.11 compatibility.
   - Use strict type annotations (`from __future__ import annotations`).
   - All code must pass `ruff check .` with zero errors.

---

## 5. Testing Rules & Verification Tiers

### 5.1 The Four Verification Tiers
Agents must strictly distinguish and report the exact verification tier achieved:
1. `IMPLEMENTED`: Code patch, schema, or guard is written.
2. `TESTED`: Unit, fixture, or contract tests pass in local test environment.
3. `EXECUTED`: Production pipeline stage has run on real artifact-backed data.
4. `VERIFIED`: Independent validation against real artifacts, manifests, and scientific invariants has passed.

**CRITICAL WARNING:** CI green, fixture PASS, exit code 0, or mock test execution **NEVER** equals scientific gate PASS.

### 5.2 Testing Discipline
- **Reproduce First:** Write a reproducing test before fixing an issue whenever feasible.
- **Targeted Unit Tests:** Verify isolated functions, temporal edge cases, and error handling.
- **Contract Tests:** Validate runtime schemas against `config/schema.yaml` and manifest schemas.
- **Temporal Invariant Tests:** Maintain strict coverage of the 4 hard temporal invariants (`tests/test_hard_invariants.py`, `scripts/verify_g1.py`).
- **Integration & Parity Tests:** Verify inter-module handoffs and Parquet–Neo4j parity.
- **Determinism Checks:** Verify that identical seeds and inputs produce bit-identical outputs.
- **Static Analysis:** Zero ruff warnings or errors.

---

## 6. Review & Audit Finding Rules

### 6.1 Structured Finding Schema
Every audit finding must be reported with the following structured schema:
- **Finding ID:** Standard slug (e.g., `M1-001`, `A01`).
- **Severity:** `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `GOVERNANCE`.
- **Affected Components/Files:** Exact repo-relative file paths.
- **Expected Behavior / Invariant:** The scientific rule or contract expected.
- **Actual Behavior:** The observed defect or failure.
- **Evidence:** Concrete command, log snippet, stack trace, or schema diff.
- **Root Cause vs. Hypothesis:** Clearly distinguish confirmed root cause from unverified hypotheses.
- **Reproduction Steps:** Minimal command or script to trigger the defect.
- **Proposed Minimal Fix:** Scope-limited change addressing root cause.
- **Regression Tests:** Specific test added or updated to prevent recurrence.
- **Remaining Blockers:** Any dependencies or decisions pending resolution.

### 6.2 Resolution Criteria
- Never mark an issue `RESOLVED` if only code was patched without verifying the necessary scope.
- Explicitly record status across: `IMPLEMENTED`, `TESTED`, `EXECUTED`, `VERIFIED`.

---

## 7. Multi-Agent Handoff Protocol

### 7.1 Audit Agent Obligations
- Provide structured findings with concrete evidence (file, line, input, command, invariant).
- Do not issue vague or speculative critiques without reproducibility.
- Re-verify fixes independently against raw data and invariants.

### 7.2 Coding Agent Obligations
- Read findings carefully; load **only** the targeted context relevant to the specific finding.
- Never accept a proposal that alters scientific semantics without formal approval.
- After fixing, deliver a compact, structured summary:
  1. Modified files list.
  2. Tests added / executed.
  3. Git diff reference.
  4. Explicit list of unverified scopes or remaining blockers.

### 7.3 Communication Efficiency
- Keep handoffs compact, structured, and cross-referenced by Finding ID.
- Avoid dumping full conversation transcripts, raw logs, or entire source files into prompts.

---

## 8. Execution Modes & Permissions

### 8.1 Development Mode (Code & Scaffold)
- **Permitted:** Code inspection, refactoring, fixture testing, unit testing, synthetic dry-runs within task boundaries.
- **Prohibited:** Treating synthetic results as production certification; bypassing gate guards; modifying production artifacts or locked test sets.

### 8.2 Scientific Execution Mode (Production Stages)
- **Strict Stage Discipline:** Exactly one stage at a time:
  $$\text{inspect} \longrightarrow \text{plan} \longrightarrow \text{implement} \longrightarrow \text{test} \longrightarrow \text{execute} \longrightarrow \text{validate} \longrightarrow \text{Stage Report} \longrightarrow \text{STOP}$$
- **No Auto-Advancing:** Never run Stage N+1 automatically.
- **Advance Prerequisites:** Stage N validated as PASS, all artifacts exist, stage gate passes, all invariants hold, explicit user request.
- **High-Risk Operations (Prohibited without explicit approval):**
  - **Never rerun `src/03b_run_tuoitre_historical_window.py`** (Stage 4.3 is locked upstream work with 108 blocks complete).
  - **Never access `data/locked_test/` before W8.**
  - **Never modify `configs/protocol_v1.yaml` or `data/manifests/sources.lock.json` without an approved amendment.**
  - **Never run unconstrained full-corpus acquisition or reprocessing.**

---

## 9. Data Acquisition & API Safety

### 9.1 No-API Constraint for Research Data
- **Applicability:** Applies strictly to research data collection and processing.
- **Allowed Mechanisms:** Public `robots.txt`, public sitemap XML, public RSS, standard HTTP GET of public HTML/XML, HTML/XML parsing, public archive/Wayback/Memento.
- **Prohibited Mechanisms:** Hosted/private APIs, `/api/...` endpoints, API pagination, search APIs, external hosted data APIs.
- **Developer Tooling Distinction:** Development tooling (Git, GitHub CLI, local linters, package managers) are **not** research data APIs and are permitted for repo operations.
- **Hosted LLM Guard:** Hosted LLMs must never act as autonomous scientific decision-makers without explicit, approved protocol registration. Local LLM adapters must follow frozen configurations with reproducible caching.

---

## 10. Current Status Awareness & Known Blockers

Before beginning any task, every agent must inspect `docs/PROGRESS.md` and `docs/audit/` to recognize the current operational state:
- **M1 Schema Drift:** Currently **BLOCKED** (9 of 17 tables deviate from `config/schema.yaml`).
- **Production Stage & Gates:** Gate A, G1/G2, production stages, and M2 handoff are **BLOCKED**.
- **C4–C9 Remediation:** Implemented and fixture-tested only; **not** certified for production.
- **Stage 4.3 Acquisition:** **LOCKED upstream work** (108 blocks complete; do not rerun).
- **Rule:** Never treat stale audit reports as current when newer evidence is present. Never unilaterally remove blockers or declare gates passed without verified production evidence.

---

## 11. Context Trigger Matrix (Demand-Driven Reading)

To avoid context window bloat, agents must only read documents triggered by their specific task:

| Task / Module | Primary Context to Read | Permitted Actions | Prohibited Actions | Verification Commands | Stop & Report Conditions |
|---|---|---|---|---|---|
| **M1: Data / Ingestion / KG** | `docs/data_pipeline_spec.md`<br>`config/schema.yaml`<br>`docs/PROGRESS.md`<br>`docs/audit/m1_c3_contract_time.md` | Inspect pipelines, fix schema mismatches, run fixture tests. | Rerun Stage 4.3 historical script; run production stages while schema is blocked; fabricate timestamps. | `pytest tests/kg_pipeline/`<br>`ruff check src/kg_pipeline/` | Schema mismatch persists; Gate A fails; missing temporal evidence. |
| **M2: KGE / Drift** | `configs/kge.yaml`<br>`docs/modules.md` (M2 section)<br>`tests/scientific/test_centered_cosine_estimand.py` | Implement backbone training, alignment, null estimation, drift metrics. | Use downstream outcomes for anchor selection; change seeds (must be 13, 37, 101); force SED+ when alignment is invalid. | `pytest tests/scientific/ -k "procrustes or drift or null or kge"` | Degenerate rank in Procrustes; holdout gap exceeds threshold; missing seeds. |
| **M3: Paths / Auditor** | `docs/modules.md` (M3 section)<br>`configs/protocol_v1.yaml` | Implement bounded simple path features; implement exact-B fallback; semantic audit labels. | Alter primary H3a population; allow path search to block CORE; use QLoRA without prerequisite check. | `pytest tests/ -k "path or auditor"` | Path search diverges; exact-B fallback missing. |
| **M4: Eval / Stats** | `configs/statistics.yaml`<br>`docs/modules.md` (M4 section)<br>`tests/scientific/test_temporal_three_seed_median.py` | Implement QA panel ranking, OOV scoring, Two-Way Fixed Effects, WCB inference. | Drop hard queries post-hoc; mix primary and open-world universes; claim causal inference from observational panel. | `pytest tests/scientific/ -k "evaluation or statistics or wcb"` | Panel balance violated; WCB cluster degenerate. |
| **Audit / Code Review** | `docs/audit/AUDIT_REMEDIATION_MATRIX.md`<br>`docs/audit/m1_c4_c9_finding_matrix.md`<br>`docs/PROGRESS.md` | Audit code against invariants, file structured findings, verify fixes. | Mark issues RESOLVED without verification; suggest protocol changes without amendment trail. | `python scripts/verify_g1.py --ci --code-checks`<br>`ruff check .` | Unresolved invariant violation; conflicting source of truth. |
| **Gate / Freeze Verification** | `docs/gates_and_freeze.md`<br>`scripts/verify_w1.py`<br>`scripts/verify_g1.py`<br>`scripts/verify_w7.py` | Check freeze readiness, inspect manifests, verify gate scripts. | Run freeze script with dirty tree; bypass `--ci` strict checks; tag without clean tree. | `python scripts/verify_w1.py --ci`<br>`python scripts/verify_g1.py --ci --code-checks`<br>`python scripts/verify_w7.py --ci` | Any required test skipped; placeholder remaining in freeze manifest. |
