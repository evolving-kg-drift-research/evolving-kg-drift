# R3 progress — storage + reproducibility

Date: 2026-09-20. Status: PARTIAL IMPLEMENTATION.

## Implemented

- Added an `exclusive_artifact_lock` in `storage.py` relying on `os.mkdir` atomic semantics to enforce multi-process safe cross-platform directory locking. This prevents concurrent overlapping artifact writes.
- Modified `write_json_immutable`, `write_yaml_immutable`, `write_parquet_immutable`, and `write_text_cas` to hold an exclusive lock during the complete check/verify/publish window.
- In `write_parquet_immutable`, crash-safe `ArtifactConflict` is raised if a file and sidecar mismatch or if someone manually tampers with both file and sidecar (semantic hash computation catches it during rerun).
- Updated semantic projection in `inventory.py` to drop the hard-coded `run_id` paths by computing the relative path from the `run_dir`, ensuring semantic hashes remain strictly scientific and deterministic across different execution runs.
- Added tests `test_tampered_table_and_manifest_rejected_during_write` and `test_concurrent_exclusive_lock_prevents_overwrite` in `tests/kg_pipeline/test_parquet_integrity.py`.

## Remaining work

- The tests successfully pass locally, but to declare R3 scientifically complete, we still need the tool classifier to be completely stable and the full regression suite to execute without interruptions, confirming all parts of the Ticket A inputs are uncorrupted.