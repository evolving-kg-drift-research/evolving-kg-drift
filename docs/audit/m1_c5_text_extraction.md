# C5 — Text normalization and extraction provenance

Date: 2026-09-28. Scope: code and fixture validation only.

## Implementation and validation

Evidence spans are bound to the exact clean-text body hash, normalization
version, code-point offsets and span hash. Identity-preserving normalization is
the default; NFC exists as a separately named version and is not activated by
default. Extraction validates both subject and object grounding in the cited
span. Cache envelopes bind prompt, model, decoding, input, parser, tokenizer,
normalization, schema and runtime fingerprints. A physical-hash sidecar detects
cache edits, and an incomplete immutable cache pair cannot be repaired by
rewriting its manifest. Scientific locked extraction permits a pinned local
adapter only; no hosted API was added.

Focused text, cache and extraction tests: **16 passed**. Full regression also
passed. A pre-existing `pytz` deprecation warning was emitted.

## Blockers and status

**IMPLEMENTED: PARTIAL. TESTED: fixture tests pass. EXECUTED: no locked
production replay. VERIFIED: code behavior only.** The machine contract has no
persisted normalization-version or per-claim clean-text hash fields, and the
body manifest is not a standalone ArtifactRef. NFC activation, normalization
semantics and reprocessing scope require approval. There is no frozen
production model/runtime lock or cache to replay.
