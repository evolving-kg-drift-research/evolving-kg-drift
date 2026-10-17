# R4 progress — gates and integration

Date: 2026-09-20. Status: PARTIAL IMPLEMENTATION.

## Implemented

- Changed `latest_gate_a_report` to explicitly read all evaluation JSON files and sort them by `evaluated_at_real`, resolving concurrent evaluation order explicitly rather than trusting UUID-based lexicographical filename sorting.
- `evaluate_gate_a` automatically rejects stale evaluations because `load_run_manifest` verifies that current `config_fingerprints` exactly match the fingerprints originally committed during the run initialization; if any config drifts, evaluating the gate fails immediately.
- Added test `test_input_mutation_invalidates_gate` in `test_gate_history.py` to prove that manually patching inputs or bypassing inventory after a PASS report will correctly invalidate the LIVE gate evaluation and reject the inputs.
- Restored the `.gitignore` policy for `data/locked_test/*`, maintaining allowlist exceptions for `README.md` and `.gitkeep`.
- Added test `test_locked_test_payload_ignored` in `test_repository_contract.py` which executes `git check-ignore` to ensure held-out data cannot be accidentally discovered, staged, or evaluated.
- Verified that the `verify` CLI command exits with `0` ONLY on `PASS` and with `2` on `BLOCKED`, `FAIL`, `NOT_RUN`, or exception.

## Remaining work

- The environment currently runs Python 3.12. Running the full repository tests on Python 3.11 across Windows/Linux CI pipelines is necessary to scientifically certify R4.
