# M1 input readiness recovery — 2026-10-03

Scope: read-only search of current paths and Git history, followed by restoration
of one authoritative source blob whose bytes matched the existing source lock.
No production stage was run.

## Source-lock originals

`sources/README.md` requires exact bytes listed in
`data/manifests/sources.lock.json`; an exported or similar document with a
different hash is not an acceptable substitute.

| Role | Locked path | Result |
|---|---|---|
| proposal | `sources/huce_evolving_kg_modular_proposal(8).pdf` | Restored from Git commit `6779bf48809ad761167366e71e1f229bd41d3870`; 399,801 bytes; SHA-256 `d9e6d74b84fabdff880698eb6a5774bed8445897539b3713ba1e0594a446ea6f`, exact match |
| execution_plan | `sources/Research_Execution_Plan_v1.0.md` | Missing; only Git-history blob found has SHA-256 `12e492387dc562e623fba098ae3956c65411f4420fdb3c368848b72521f24bc5`, not the locked hash |
| patch | `sources/Research_Execution_Plan_v1.1_Patch.md` | Missing; only Git-history blob found has SHA-256 `faae34f40f6380fe6222374f682335bedbe69ba5779b9d00b6222875080e1611`, not the locked hash |

The source blob commit is reachable from `origin/fix/data-pipeline-compliance-cont`
and is authored by Huong. The Markdown blobs do not match even after testing
plain LF/CRLF conversion. They were not restored. Exact-name checks in the
downstream ZIP and Codex attachments found no additional copies.

After restoring the proposal, `inspect_source_lock()` reports `proposal=MATCH`,
`execution_plan=MISSING`, `patch=MISSING`, overall **BLOCKED**. The lock file,
protocol and decision log were not edited.

`python scripts/verify_w1.py --ci` reports only scaffold/contracts as PASS
because the W1 source-lock tag does not exist; its output explicitly states
that source-byte verification was not performed. Strict
`python scripts/verify_w1.py` exits nonzero and reports the two missing
Markdown originals. The CI scaffold PASS is not W1 source-lock PASS or Gate A.

## Other production artifacts

- `data/raw/`, `data/event_store/`, and `data/snapshots/` contain only
  `.gitkeep`; `runs/` and `data/stage_4_3_runs/` are absent.
- Git object-path inspection found no tracked `data/stage_4_3_runs/` or
  `data/raw/stage_4_4/` files on available refs. Stage 4.3 was not rerun.
- The registered secondary checkout (`C:/Users/ducan/orca/workspaces/evolving-kg-drift/main`)
  also lacks all three source originals, Stage 4.3 artifacts, and raw inputs.
  Its only two run folders are `pilot-test-run` and `pilot-test-run-2`, both
  `inventory` runs with `PROPOSED_UNFROZEN` config and
  `source_lock_status_at_init: BLOCKED`; the recorded Gate A report is
  `BLOCKED`. These are pilot fixtures, not production recovery evidence.
- `data/evolving_kg_downstream_v2.zip` remains at SHA-256
  `de9b273cec9ca13ba6d629017f83a8d00e4471ff8843d00898e5980c7c2b1161`, matching
  the prior audit. It remains a downstream export without source acquisition,
  stage lineage or gate evidence.

## Status

This improves source-lock readiness by one exact original, but Gate A remains
**BLOCKED**. Required next inputs are the exact locked execution plan and patch,
raw acquisition evidence and the already completed Stage 4.3 artifacts. No
mtime-derived provenance, source-lock rewrite, historical acquisition rerun,
Gate A pass, or downstream stage execution occurred.
