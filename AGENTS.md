# AGENTS.md — evolving-ai-kg

## Authority and current state

Before any Data/KG pipeline work, read both:

- `docs/data_pipeline_spec.md` — authoritative operational specification.
- `docs/PROGRESS.md` — mutable execution state and current stage gate.

Do not duplicate or weaken the master specification here. If repository state
conflicts with it, stop and report the conflict rather than changing scientific
semantics.

## Stage-gate discipline

- Work on exactly one stage at a time: inspect → plan → implement → test →
  execute → validate → Stage Report → stop.
- Do not skip stages or execute Stage N+1 automatically.
- Continue only when Stage N is validated as PASS, all required artifacts exist,
  the stage-specific gate and invariants pass, and the user explicitly requests
  the next stage.
- A successful command or exit code does not make a stage PASS.
- PASS requires validation of required inputs and artifacts, readability and
  schema, provenance, applicable integrity and reproducibility checks, all hard
  scientific invariants, and the stage-specific gate.

## Hard scientific invariants

Never violate:

1. No future evidence.
2. No future entity mapping.
3. Append-only provenance.
4. Zero overwrite of immutable raw content states.
5. Deterministic rebuild from frozen inputs, configuration, rules, mappings, and
   semantic component versions.
6. No downstream leakage into corpus filtering, anchor selection, snapshot
   boundaries, or other upstream scientific decisions.
7. Version every semantics-affecting component, including ontology,
   LogicalFactID rules, extractor, entity mapping, temporal parser,
   adjudication, snapshot builder, filtering, and deduplication.
8. Canonical Parquet is the source of truth; Neo4j is only a
   materialization/query layer.
9. Stage 4.18 requires verified Parquet–Neo4j node/edge set equality.

## No-API constraint

Do not introduce hosted/private APIs, `/api/...` endpoints, API pagination,
search APIs, external hosted data APIs, or hosted LLM APIs without an explicit
user-approved protocol change. Allowed collection mechanisms are public
`robots.txt`, sitemap XML, RSS, ordinary HTTP GET of public HTML/XML, parsing of
those payloads, and public archive/Wayback/Memento access when applicable.

## Repository-first rule

Before modifying a stage, inspect the repository tree, git status when
available, existing scripts and configs, actual input schemas, logs/state,
tests/helpers, and existing or partial outputs. Reuse stable code, discover real
columns and CLI behavior, and prefer minimal diffs.

## Immutable and append-only data safety

Never delete raw data, truncate append-only logs, overwrite immutable or frozen
artifacts, rewrite historical timestamps, silently patch production Parquet, or
manually patch snapshots/Neo4j to pass a gate. Rebuilds must create a new
version/run, preserve prior artifacts, and record supersession or invalidation.

Treat the completed Stage 4.3 historical acquisition recorded in
`docs/PROGRESS.md` as locked upstream work. Never rerun
`src/03b_run_tuoitre_historical_window.py` without explicit user approval.

## Decision log

`decisions/decision_log.jsonl` is append-only and is only for decisions affecting
scientific semantics, data population, identity, temporal behavior, filtering,
ontology, extraction, adjudication, versioning, or snapshot construction. It is
not a general execution log.

