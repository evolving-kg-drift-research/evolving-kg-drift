# C9 — Scientific locked mode and CI separation

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

Runs can be explicitly initialized in `scientific_locked` mode. Locked runs
require a frozen baseline, a complete dependency lock, pinned local
model/tokenizer and matching adapter fingerprints; an existing run cannot be
downgraded in place. The local adapter now comes from optional
`config/llm_adapter.yaml`, which is included in the run fingerprint. Locked
initialization checks that every direct `pyproject.toml` dependency has an exact
matching pin in `requirements.lock.txt`. Locked extraction rejects a missing,
mock, unpinned, or non-local adapter before creating the run. The runner also
rejects an absent ontology instead of supplying hard-coded relations; an
offline mock must be declared explicitly and remains unavailable to locked
runs. Direct extraction calls require an explicit ontology, adapter, and
run-scoped cache directory.
The `verify-scientific` CLI requires an explicit run and returns a nonzero
status when evidence is missing. CI names code checks separately from scientific
G1/G2 certification. After the adapter hardening, **25 focused code tests
passed and 4 filesystem-dependent tests were deselected**; Ruff and
`git diff --check` passed. Direct checks also verified that implicit extraction
config is rejected and that missing, remote, and incomplete locked adapters do
not pass validation.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: code checks pass. EXECUTED: no locked
production run. VERIFIED: guard behavior only.** Artifact-backed G1/G2
evaluators and certificates are unavailable, so CI has no production
certification job and M2 cannot open. The current baseline is not FROZEN, and
the current dependency declarations also fail the new lock check:
`pyproject.toml` contains `openai>=1.0.0`, while `requirements.lock.txt` has no
exact `openai` pin. Branch protection is outside this repository's permissions.
No scientific PASS is emitted by this checkpoint. A full regression rerun after the latest
adapter hardening remains unverified: this Windows workspace denied access to
pytest's temporary directories (`WinError 5`), so the earlier 230-pass count
does not certify the newest code revision.
