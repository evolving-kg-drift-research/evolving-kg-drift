# C5 — text normalization, evidence spans, and extraction replay

Date: 2026-10-03. Branch: `codex/m1-thu-huong-remediation`.

## Findings M1-010–M1-012

- **Severity:** HIGH.
- **Affected components:** `src/kg_pipeline/evidence.py`,
  `src/kg_pipeline/claims.py`, `src/kg_pipeline/extract.py`,
  `src/kg_pipeline/llm_adapter.py`, `src/kg_pipeline/locked_mode.py`, and
  stage-manifest verification in `src/kg_pipeline/run.py`.
- **Expected behavior:** Evidence offsets and hashes identify the exact stored
  clean-text representation; normalization is explicitly versioned; cache
  replay is immutable and bound to every result-affecting input and runtime
  fingerprint; a locked replay without a complete matching cache fails closed.
- **Observed behavior before this patch:** The helper silently treated an
  omitted normalization version as identity in unlocked calls. The body-variant
  schema has no `normalization_version`, so the extraction runner supplied
  `None`; the extractor report recorded `None` while span hashing used identity.
  The local adapter/cache fingerprint also lacked an explicit inference-runtime
  pin. The extractor manifest was written but was not a physically bound stage
  output.
- **Changes:**
  - Extraction now requires an explicit normalization version and verifies the
    stored text already conforms to it. The runner refuses a missing version
    and accepts only the existing identity version. NFC remains available as a
    versioned utility for tests, but the runner blocks its activation pending
    semantic approval; raw and existing body bytes are untouched.
  - Evidence spans retain Python code-point offsets and hash the exact span and
    full clean text. `extractor_manifest.json` records the clean-text hash and
    normalization version per body variant; the claim's body-variant reference
    links it to this record.
  - Stage manifests can now bind versioned JSON outputs with physical and
    semantic SHA-256 values. Verification rejects a changed extractor manifest.
  - Cache requests bind input text, parser version/hash, normalization version,
    dependency lock, ontology, prompt template, response schema, extractor and
    cache versions, model/tokenizer revisions, decoding settings, local
    endpoint hash, Python/platform/machine, and the configured local inference
    runtime fingerprint. Locked replay requires 64-character SHA-256 values
    for parser, dependency lock, and local runtime and requires an existing
    immutable cache entry.
- **Confirmed root cause:** The missing normalization field in
  `config/schema.yaml` and runtime `body_variants` contract caused the runner to
  fall back to identity without persisting that fact. The adapter did not have
  a required locked-mode field for the local inference runtime identity.
- **Regression tests:** Unicode/code-point EvidenceSpan tests, explicit and
  unapproved normalization checks, absent-version runner rejection, locked
  cache replay without adapter invocation, missing/tampered cache checks,
  local endpoint/runtime fingerprint checks, and JSON ArtifactRef tampering.
- **Reproduction:**
  `python -m pytest -q --tb=short -p no:cacheprovider --basetemp=.pytest-c5-retry-20261003 tests/kg_pipeline/test_claims.py tests/kg_pipeline/test_evidence.py tests/kg_pipeline/test_extraction_provenance.py tests/kg_pipeline/test_artifact_chain.py tests/kg_pipeline/test_locked_mode.py tests/scientific/test_claim_provenance_chain.py`
- **Result:** **52 passed**, one existing `pytz` deprecation warning.
  Targeted Ruff and `git diff --check` on the C5 code/tests passed. These are
  fixture tests; Gate A, local inference, production source text and production
  cache were not executed.
- **Status:** IMPLEMENTED: partial. TESTED: focused fixture suite passes.
  EXECUTED: no production extraction. VERIFIED: fixture behavior and stage
  manifest tamper rejection only.
- **Remaining blockers:** `config/schema.yaml` and runtime schema do not yet
  carry `body_variants.normalization_version`; the C3 audit remains blocked at
  9/17 tables. Activating NFC requires approved semantic policy, a versioned
  contract migration and reprocess review. The runtime fingerprint is presently
  an approved-config assertion passed into the adapter; the local inference
  engine has not independently attested that its running build matches it.
  Gate A, source provenance, human gold and all production extraction evidence
  remain unavailable.
- **Minimal next fix:** After the schema and normalization decisions are
  approved, add the version field to a new contract version, bind it in body
  producer artifacts and extracted-claim lineage, and make the local inference
  runtime report a verifiable build/container digest before locked replay.
  Rebuild only into a new run; retain prior raw/body artifacts.
