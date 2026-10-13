# Checkpoint 1 — source-lock repair slice

Date: 2026-09-20. Scope: source-lock validation only, not all Ticket A repairs.

## Implemented

`src/kg_pipeline/run.py::inspect_source_lock` now requires proposal, execution_plan and patch, reads authoritative protocol hashes, rejects missing roles, invalid baseline hashes, re-anchored locks, malformed authority and source paths outside the repository. Existing missing-file, content-hash and placeholder checks remain. No original source hashes or source documents were changed.

The role mapping mirrors `scripts/verify_w1.py`; shared-helper extraction remains pending. Source lock changes do not yet fix Gate A trusting a stale persisted lock status. Configuration FROZEN validation, provenance, immutable concurrency, artifact integrity, IDs and gate history remain pending.

## Verification actually performed

- Checkpoint 0 follow-up: JSONL parse, unique decision IDs and historical byte-prefix preservation PASS; `git diff --check` completed without output.
- New focused source-lock tests: 8 passed.
- First complete Ticket A run: 14 passed, 1 failed because the old fixture assumed a single-role lock without protocol authority. Fixture updated to provide a protocol, assert all required roles, preserve its missing-file assertion and verify lock bytes unchanged.
- Final `python -m pytest tests/kg_pipeline -q`: **15 passed**, one third-party pytz deprecation warning.
- `python -m ruff check src/kg_pipeline/run.py tests/kg_pipeline`: PASS.
- `git diff --check`: PASS.

Execution used the available Python 3.12 installation, not the project's Python 3.11 CI target. Python 3.11 validation and full repository suite remain pending. No production readiness assertion follows from these fixture tests. No acquisition, source replacement, production inventory, hosted API, Neo4j write, commit or push performed.
