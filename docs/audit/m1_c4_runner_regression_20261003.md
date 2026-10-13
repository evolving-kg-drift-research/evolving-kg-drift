# C4 — cutoff-aware mapping runner regression

Date: 2026-10-03. Branch: `codex/m1-thu-huong-remediation`.

## Finding M1-001 — late mappings must not alter earlier adjudication/snapshots

- **Severity:** HIGH.
- **Affected components:** `src/kg_pipeline/adjudicate.py`,
  `src/kg_pipeline/adjudication.py`, `src/kg_pipeline/snapshot_runner.py`,
  `src/temporal/snapshot.py`, and their focused tests.
- **Expected behavior / invariant:** A mapping may be used only when its
  `mapping_available_at` is at or before the applicable evidence or snapshot
  cutoff. A current catalog must not substitute for a historical mapping
  decision (INV-02).
- **Observed behavior:** The production functions load artifact-backed mapping
  history; adjudication passes an empty catalog, while the snapshot builder
  resolves mapping records as of each requested cutoff. The runtime mapping
  identity is still the mention string, however; stable `MentionID` and
  `MappingDecisionID` are not carried through Claim → FactVersion → snapshot.
  `config/schema.yaml` declares `mention_id`, while the runtime table declares
  `mention`. C3 remains blocked at 9/17 table mismatches.
- **Evidence:** New runner-level fixture regressions show (1) a future-only
  alias is left unresolved by `run_adjudication`, and (2) the real
  `run_snapshot` function uses the earlier mapping before a supersession cutoff
  and the newer decision afterward. Existing pure-helper tests continue to
  cover ambiguous mappings and invalid supersession links.
- **Confirmed root cause:** Mention identity and decision lineage are absent
  from current runtime contracts and FactVersion provenance. This is a schema
  and policy gap, not evidence that the current string-based fixture model is
  a valid production identity model.
- **Reproduction:**
  `python -m pytest -q --tb=short -p no:cacheprovider --basetemp=.pytest-c4-run-20261003b tests/kg_pipeline/test_adjudication_provenance.py tests/kg_pipeline/test_snapshot_runner_fail_closed.py tests/kg_pipeline/test_adjudication.py tests/temporal/test_snapshot.py`
- **Result:** **48 passed**, with one existing `pytz` deprecation warning.
  `python -m ruff check --no-cache src/kg_pipeline/adjudication.py
  src/kg_pipeline/adjudicate.py src/kg_pipeline/snapshot_runner.py
  src/temporal/snapshot.py tests/kg_pipeline/test_adjudication_provenance.py
  tests/kg_pipeline/test_snapshot_runner_fail_closed.py
  tests/temporal/test_snapshot.py` passed. The runner tests use fixtures and
  isolate Gate A, schema approval, temporal-policy inputs, and artifact I/O;
  this is not production execution or scientific gate evidence.
- **Status:** IMPLEMENTED: partial (existing as-of behavior plus regression
  coverage). TESTED: focused fixture suite passes. EXECUTED: no production
  stage. VERIFIED: fixture behavior only.
- **Remaining blockers:** Approved identity/LogicalFactID policy; contract
  migration that carries stable mention and mapping-decision IDs; proof that
  the mapping catalog fingerprint binds to the producer artifact and run;
  compatible YAML/PyArrow/dataclass schemas; Gate A and real Stage 4.10 temporal
  inputs. No production data was read or rebuilt.
- **Minimal next fix:** After the identity/schema decision is approved, add the
  stable mention and decision references to the agreed contract, enforce them
  in both runners, and add duplicate-name/late-alias tests over that contract.
  Do not infer IDs or change the scientific identity policy in code.
