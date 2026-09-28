# C3 schema and temporal decision package

**Status: REVIEW REQUIRED — this is a proposal, not an approved scientific decision.**

Date: 2026-09-28

Branch: `reconcile/pipeline-drift-compliance`
Baseline: `922e319bfca1066ad42577cbd5f4ff8c9c87433e`

This package records the decisions required to complete C3. It does not change
`decisions/decision_log.jsonl`, schema/configuration, timestamps, or production
artifacts. The master specification remains authoritative. No C3 semantic
choice is treated as approved until the responsible scientific authority accepts
it and the approved decision is appended to the decision log.

## Evidence from the current checkout

The read-only `audit-schema` command returned **BLOCKED** for 9 of 17 declared
tables. The schema file is version `1.0.0`, with physical SHA-256
`48ad42f86088ae0e9ca8b8cbb158017bf8ec14e0d450fdeff523bf59e6902840`.

The nine mismatches are `source_registry`, `raw_source_versions`,
`document_clusters`, `corpus_filtered`, `entity_mentions`,
`entity_mapping_versions`, `claims`, `adjudication_decisions`, and
`fact_versions`. Several contracts have no same-named runtime table. Existing
runtime names such as `extracted_claims` and `entity_mappings` are not assumed
to be lossless replacements for `claims` and `entity_mapping_versions`.

For `fact_versions`, the YAML requires `FactVersionID`, `LogicalFactID`,
`accepted_into_kg_at`, `adjudicated_at_real`, `adjudication_rule_version`,
`object_value`, `ontology_version`, `raw_source_id`, `retrieved_at_real`,
`scope`, and `url`, which are absent from the PyArrow schema and dataclass.
The runtime instead includes fields such as `fact_version_id`,
`logical_fact_id`, `ingested_at_real`, span fields, `evidence_text_hash`, and
`source_url`. The current checker compares field names; `schema.yaml` does not
yet declare physical types or nullability.

The master specification requires both
`evidence_observed_at <= known_at` and
`accepted_into_kg_at <= known_at`, followed by validity, revision, tombstone,
and mapping-as-of handling. It separates those scientific known-time fields
from project provenance (`retrieved_at_real`, ingestion, adjudication). The
current runtime has no `accepted_into_kg_at` field and the adjudication runner
deliberately blocks without a verified Stage 4.10 temporal input artifact.

## Decisions requiring approval

1. **Public schema and version.** Confirm that `config/schema.yaml` remains the
   public contract authority and specify the next contract version. Decide
   whether its declared field names remain the canonical Parquet names, with
   explicit serializer mappings where Python names differ, or whether a
   versioned rename is required. Define Arrow physical types and nullability
   for every field. No implicit aliases or dropped fields are permitted.

2. **FactVersion clock placement.** Preserve the distinct meanings of
   `valid_from`/`valid_to`, `evidence_observed_at`, `accepted_into_kg_at`,
   `retrieved_at_real`, `ingested_at_real`, and `adjudicated_at_real`. Confirm
   which record stores each clock and its evidence reference. In particular,
   decide whether `ingested_at_real` is part of the versioned FactVersion
   contract or remains in a separately linked project-provenance artifact.
   It must never substitute for either known-time field.

3. **Evidence-observation basis.** Specify which Stage 4.10 evidence types can
   establish when information was publicly observable, how basis and confidence
   are represented, and what review/eligibility result applies when evidence
   cannot establish that time. The master specification forbids substituting
   retrieval time, declared publication time, or event validity without an
   approved basis rule.

4. **KG-acceptance clock.** Specify the event that supplies
   `accepted_into_kg_at`, how it is independently recorded, and how it relates
   to (but remains distinguishable from) `adjudicated_at_real`. Missing
   acceptance evidence must block publication or follow an expressly approved
   review policy; no default timestamp is proposed.

5. **Migration and reprocessing.** Approve the affected stage range and
   invalidation plan for a new schema version. The candidate impact set is
   claims/temporal claims, adjudication decisions, FactVersions, quality
   certification, main-corpus freeze, KG events, boundaries, snapshots, and
   M2 manifests as applicable. Existing artifacts remain immutable; any
   rebuild uses a new run and records supersession/invalidation.

## Recommended implementation boundary

Once the above decisions are approved, implement the approved contract as a
typed machine-readable schema, validate exact names/types/nullability against
PyArrow and serializers, and add lossless round-trip tests. Keep the current
fail-closed temporal input guard until Stage 4.10 supplies an artifact with the
approved basis, confidence, source/proof reference, and independent project
clock evidence. Then run the schema audit and relevant contract tests before
considering C3 complete.

Until approval and the required Stage 4.10 artifact exist, C3 remains
**BLOCKED**, production adjudication/snapshot work remains blocked, and no
scientific decision-log entry should be added for this proposal.
