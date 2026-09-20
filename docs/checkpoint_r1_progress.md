# R1 progress — baseline and execution guards

Date: 2026-09-20. Status: PARTIAL IMPLEMENTATION, not scientific PASS.

## Implemented and tested

- Source lock requires three original roles and protocol/lock/file hash agreement.
- Configuration fingerprints now include source/scope/filter/stage/snapshot configs and dependency/package files.
- Loading or resuming an existing run rejects changed code/config fingerprints before inventory writes tables.
- Run manifest semantic hash is recomputed and run identity checked; editing a field while retaining its old digest is rejected.
- New configuration bundles are PROPOSED_UNFROZEN with an explicit approval blocker, not unconditionally FROZEN. ADR 0007 replaces the stale source-reanchoring claim.
- Run manifests also capture `config_approval`, and `load_run_manifest` rejects a changed approval assessment on resume.
- Component-specific config validation implemented (protocol sources, ontology relations, corpus scope boundaries).
- Decoupled `inspect_source_lock` to `baseline.py` to prevent `verify_w1.py` from importing heavy storage/PyArrow dependencies.

## Latest verification

`python -m pytest -q`: 52 passed, 14 skipped, one third-party pytz deprecation warning. Python 3.12 in this environment; Python 3.11 not yet verified.

`python -m ruff check src/kg_pipeline tests/kg_pipeline`: PASS.

`git diff --check`: PASS before this new report was written.

## Limits and remaining work

A self-contained digest is corruption detection, not authentication: a rewritten manifest plus recomputed digest requires an independent approved baseline/input lock to detect. Do not interpret these guards as signed provenance or approval.

Follow-up: verify_w1 now calls the same inspect_source_lock validator. baseline.py checks an exact config file/hash manifest in data/manifests/config_baseline.json against a uniquely referenced decision with action=approve_config_baseline, baseline_sha256, approved_by and date_real. Gate A recomputes approval and compares it with the run bundle. This checks recorded approval consistency, not signer authentication; reviewed decision provenance remains a governance prerequisite. No approval file or production decision was created.

Latest follow-up verification: 54 passed, 14 skipped, one pytz warning; scoped Ruff including scripts/verify_w1.py PASS; diff check PASS. verify_w1.py --ci PASS checks scaffold/contracts only because the source-lock tag is absent, not original source bytes. No production baseline was fabricated or approved by the implementation. Original source files and historical input package remain missing in this checkout.

Other partial repairs currently in the working tree include strict timestamp contracts, shared raw-readiness blockers, Parquet sidecar verification, and append-only gate history. Their tests do not certify acquisition origin, complete reference integrity, concurrency safety, stable content/event identity, or downstream temporal/Neo4j readiness. Fourteen skipped tests remain outstanding rather than PASS.

Subsequent additions of approval-change resume regressions and component-specific config validation test coverage were made. The attempt to rerun pytest/Ruff/diff after these final changes was blocked by a tool safety-classifier outage. Therefore the 54-pass result above predates these final changes; the current working tree is NOT fully revalidated yet.

No acquisition, production inventory, hosted API, Neo4j operation, commit or push was performed.
