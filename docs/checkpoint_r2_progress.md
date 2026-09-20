# R2 progress — acquisition trust and identity

Date: 2026-09-20. Status: PARTIAL IMPLEMENTATION.

## Implemented

- Added Primary Key (PK) and Foreign Key (FK) schemas to `contracts.py` for cross-table reference integrity.
- PK format, presence, and uniqueness validation added directly into `validate_rows` to prevent duplicates and nulls at write-time.
- FK cross-table resolution validation added into Gate A (`A-011` check), ensuring all foreign keys resolve before PASS.
- Reworked `_recovery_row` in `inventory.py` to evaluate timestamp strictness during acquisition scanning. The timezone-aware parser properly identifies and downgrades missing/invalid timestamps (`INVALID_ACQUISITION_TIME_MISSING_TZ`, `INVALID_ACQUISITION_TIME_FORMAT`) to `strict=False` and preserves the rows as ledgers instead of throwing an abort error.
- Expanded `test_inventory.py` to include:
  - `test_genuine_repeated_fetch_same_bytes_different_publishers`: proves same bytes can be correctly registered as different acquisition sources if they come from separate publishers.
  - `test_same_event_appears_in_two_places`: proves identical records replicated in multiple log lines/files do not crash and are recorded cleanly (though as distinct retrievals due to different locator provenance).
  - `test_partial_and_strict_timestamps_ledger`: verifies missing timezones or missing retrieved_at metrics correctly demote the evidence while maintaining their existence in the inventory table.

## Remaining work

- Same as R1, safety-classifier outage prevents us from successfully executing unit test pipelines. We cannot claim scientific passing for R2 yet.
- More specific origin chain adapter verification logic based on approved schemas (beyond just checking if fields are present).
