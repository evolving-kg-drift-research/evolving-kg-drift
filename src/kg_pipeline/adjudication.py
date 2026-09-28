from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Iterable

from temporal.schema import Claim, FactVersion
from temporal.schema import EntityMappingVersion
from temporal.snapshot import compute_logical_fact_id, resolve_entity_mapping_at_cutoff
from .hashing import stable_id

WHITELIST_SOURCES = {"trusted_registry_1", "official_feed"}


@dataclass(frozen=True)
class SourceClaim:
    """A claim occurrence attached to one independently traceable source path."""

    source_claim_id: str
    claim_id: str
    provenance_id: str
    membership_id: str
    source_version_id: str
    retrieval_id: str
    raw_blob_sha256: str
    publisher_source_id: str
    source_url: str


def build_source_claims(
    claims: Iterable[Claim], provenance_rows: Iterable[dict[str, Any]]
) -> list[SourceClaim]:
    """Split claim occurrences by provenance path without collapsing source lineage."""
    claim_ids = {claim.claim_id for claim in claims}
    result: list[SourceClaim] = []
    seen: set[str] = set()
    required = (
        "claim_id", "provenance_id", "membership_id", "source_version_id",
        "retrieval_id", "raw_blob_sha256", "publisher_source_id", "source_url",
    )
    for row in provenance_rows:
        missing = [field for field in required if not row.get(field)]
        if missing:
            raise ValueError(f"SourceClaim provenance is incomplete: {missing}")
        if row["claim_id"] not in claim_ids:
            raise ValueError(f"SourceClaim references unknown claim {row['claim_id']}")
        source_claim_id = stable_id("sourceclaim", {key: row[key] for key in required})
        if source_claim_id in seen:
            raise ValueError(f"Duplicate SourceClaim provenance identity: {source_claim_id}")
        seen.add(source_claim_id)
        result.append(SourceClaim(
            source_claim_id=source_claim_id,
            claim_id=row["claim_id"],
            provenance_id=row["provenance_id"],
            membership_id=row["membership_id"],
            source_version_id=row["source_version_id"],
            retrieval_id=row["retrieval_id"],
            raw_blob_sha256=row["raw_blob_sha256"],
            publisher_source_id=row["publisher_source_id"],
            source_url=row["source_url"],
        ))
    return sorted(result, key=lambda item: (item.claim_id, item.source_version_id, item.source_claim_id))


def validate_append_only_fact_versions(
    previous: Iterable[FactVersion], current: Iterable[FactVersion]
) -> None:
    """Reject changed historical versions and invalid cross-run supersession links."""
    previous_rows = list(previous)
    current_rows = list(current)
    previous_by_id = {fact.fact_version_id: fact for fact in previous_rows}
    current_by_id = {fact.fact_version_id: fact for fact in current_rows}
    if len(previous_by_id) != len(previous_rows):
        raise ValueError("Previous FactVersion store has duplicate IDs")
    if len(current_by_id) != len(current_rows):
        raise ValueError("Current FactVersion store has duplicate IDs")
    for fact_id, fact in previous_by_id.items():
        if current_by_id.get(fact_id) != fact:
            raise ValueError(f"Append-only FactVersion changed historical record {fact_id}")
    all_ids = set(previous_by_id) | set(current_by_id)
    for fact in current_by_id.values():
        if fact.supersedes_version_id and fact.supersedes_version_id not in all_ids:
            raise ValueError(
                f"FactVersion {fact.fact_version_id} supersedes missing version "
                f"{fact.supersedes_version_id}"
            )

def parse_extracted_date(date_str: str | None, default: datetime | None = None) -> datetime | None:
    if not date_str:
        return default
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid extracted validity timestamp: {date_str}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Extracted validity timestamp requires an explicit timezone")
    return dt

def fuzzy_match_entity(mention: str, catalog: dict[str, str]) -> str | None:
    """Legacy in-memory catalog matcher; locked runners must use versioned mappings."""
    if not mention or not isinstance(mention, str) or not mention.strip():
        return None

    mention_clean = mention.strip()
    if mention_clean in catalog:
        return catalog[mention_clean]

    mention_lower = mention_clean.lower()
    for k, v in catalog.items():
        if k.lower() == mention_lower:
            return v

    if len(mention_lower) >= 3:
        for k, v in catalog.items():
            if len(k) >= 3 and (mention_lower in k.lower() or k.lower() in mention_lower):
                return v
    return None

def adjudicate_claims(
    claims: Iterable[Claim],
    observation_times: dict[str, datetime], # Map from claim_id to evidence_observed_at
    ingested_at: datetime,
    entity_catalog: dict[str, str], # Maps raw mentions to canonical IDs
    extractor_version: str = "v1",
    entity_map_version: str = "v1",
    body_to_sources: dict[str, list[dict[str, Any]]] | None = None,
    ontology_rules: dict[str, Any] | None = None,
    existing_facts: Iterable[FactVersion] | None = None,
    entity_mappings: Iterable[EntityMappingVersion] | None = None,
) -> tuple[list[FactVersion], list[dict[str, Any]]]:
    """
    Adjudicate extracted claims into FactVersions.
    Returns (accepted_facts, queued_for_review)
    """
    accepted = []
    review_queue = []
    if ingested_at.tzinfo is None or ingested_at.utcoffset() is None:
        raise ValueError("ingested_at_real requires an independent timezone-aware event")
    for claim_id, observed_at in observation_times.items():
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError(f"evidence_observed_at requires an explicit timezone: {claim_id}")

    latest_by_logical_id: dict[str, FactVersion] = {}
    if existing_facts:
        for ef in existing_facts:
            curr = latest_by_logical_id.get(ef.logical_fact_id)
            if curr is None or (ef.evidence_observed_at, ef.fact_version_id) > (curr.evidence_observed_at, curr.fact_version_id):
                latest_by_logical_id[ef.logical_fact_id] = ef

    mapping_history = list(entity_mappings or ())

    # Process claims chronologically by observation time so revision chains are ordered
    sorted_claims = sorted(
        claims,
        key=lambda c: (
            observation_times.get(c.claim_id, datetime.min.replace(tzinfo=timezone.utc)),
            c.claim_id,
        )
    )

    for claim in sorted_claims:
        # Prefer append-only mapping decisions when available. Their availability
        # is checked against the evidence observation time; a current catalog is
        # only retained for non-locked compatibility callers.
        observed_at = observation_times.get(claim.claim_id)
        if observed_at is None:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "EVIDENCE_TIME_UNAVAILABLE",
                "claim": claim,
            })
            continue
        if mapping_history and observed_at is not None:
            subject_mapping = resolve_entity_mapping_at_cutoff(
                claim.subject_mention, mapping_history, observed_at
            )
            object_mapping = resolve_entity_mapping_at_cutoff(
                claim.object_mention, mapping_history, observed_at
            )
            subject_id = subject_mapping.canonical_entity_id if subject_mapping else None
            object_id = object_mapping.canonical_entity_id if object_mapping else None
            resolved_map_version = entity_map_version
            if subject_mapping is not None and object_mapping is not None:
                map_versions = {
                    subject_mapping.entity_map_version,
                    object_mapping.entity_map_version,
                }
                if len(map_versions) != 1:
                    review_queue.append({
                        "claim_id": claim.claim_id,
                        "reason": "MAPPING_VERSION_CONFLICT_PENDING_POLICY",
                        "claim": claim,
                    })
                    continue
                resolved_map_version = next(iter(map_versions))
        else:
            subject_id = fuzzy_match_entity(claim.subject_mention, entity_catalog)
            object_id = fuzzy_match_entity(claim.object_mention, entity_catalog)
            resolved_map_version = entity_map_version

        if not subject_id or not object_id:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "UNRESOLVED_ENTITY",
                "claim": claim
            })
            continue

        # Use extracted dates if available - strictly decoupled from observation time (A07)
        valid_from = parse_extracted_date(claim.valid_from_extracted, None) if claim.valid_from_extracted else None
        valid_to = parse_extracted_date(claim.valid_to_extracted, None) if claim.valid_to_extracted else None

        # Ignore speculative claims for auto-accept
        if claim.is_speculative:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "SPECULATIVE_OR_NEGATIVE",
                "claim": claim
            })
            continue

        # Deterministic IDs respecting relation-specific functional dependency (A10)
        logical_fact_id = compute_logical_fact_id(subject_id, claim.relation_name, object_id, ontology_rules)
        prior_fact = latest_by_logical_id.get(logical_fact_id)

        source_rows = body_to_sources.get(
            getattr(claim, "body_variant_id", claim.source_id), []
        ) if body_to_sources else []
        has_trusted_source = (
            any(row.get("publisher_source_id") in WHITELIST_SOURCES for row in source_rows)
            if source_rows else claim.source_id in WHITELIST_SOURCES
        )

        if claim.is_negative:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": (
                    "REVISION_CONFLICT_PENDING_APPROVED_POLICY"
                    if prior_fact is not None else "NEGATIVE_WITHOUT_PRIOR_FACT"
                ),
                "claim": claim,
            })
            continue

        if prior_fact is not None and (
            prior_fact.subject_id,
            prior_fact.relation_id,
            prior_fact.object_id,
        ) == (subject_id, claim.relation_name, object_id):
            # Same proposition from another claim is additional support, not a
            # correction. Persisting cross-run support still needs its own schema.
            if not has_trusted_source:
                source = source_rows[0] if source_rows else {}
                provisional_source_id = source.get("publisher_source_id") or claim.source_id
                provisional_source_url = source.get("source_url") or f"internal://{provisional_source_id}"
                provisional_fact = FactVersion(
                    fact_version_id=f"{logical_fact_id}_{claim.claim_id}",
                    logical_fact_id=logical_fact_id,
                    subject_id=subject_id,
                    relation_id=claim.relation_name,
                    object_id=object_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    evidence_observed_at=observed_at,
                    ingested_at_real=ingested_at,
                    supersedes_version_id=None,
                    revision_type="creation",
                    source_id=provisional_source_id,
                    source_url=provisional_source_url,
                    evidence_span_start=claim.evidence_span_start,
                    evidence_span_end=claim.evidence_span_end,
                    evidence_text_hash=claim.evidence_text_hash,
                    extractor_version=extractor_version,
                    entity_map_version=resolved_map_version,
                    confidence=0.5,
                    adjudication_status="PENDING_REVIEW",
                    supporting_claim_ids=(claim.claim_id,),
                )
                review_queue.append({
                    "claim_id": claim.claim_id,
                    "reason": "NON_WHITELIST_SOURCE",
                    "claim": claim,
                    "provisional_fact": provisional_fact,
                })
            elif any(prior_fact.fact_version_id == item.fact_version_id for item in accepted):
                merged = replace(
                    prior_fact,
                    supporting_claim_ids=tuple(sorted(set(prior_fact.supporting_claim_ids) | {claim.claim_id})),
                )
                accepted = [merged if item.fact_version_id == prior_fact.fact_version_id else item for item in accepted]
                latest_by_logical_id[logical_fact_id] = merged
            else:
                review_queue.append({
                    "claim_id": claim.claim_id,
                    "reason": "SUPPORT_FOR_EXISTING_FACT_REQUIRES_SUPPORT_ARTIFACT",
                    "claim": claim,
                })
            continue

        if prior_fact is not None:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "REVISION_CONFLICT_PENDING_APPROVED_POLICY",
                "claim": claim,
            })
            continue

        fact_version_id = f"{logical_fact_id}_{claim.claim_id}"

        # Resolve publisher sources and trust via body_to_sources if available
        bv_id = getattr(claim, "body_variant_id", claim.source_id)
        sources = body_to_sources.get(bv_id, []) if body_to_sources else []
        if sources:
            trusted_src = next((s for s in sources if s.get("publisher_source_id") in WHITELIST_SOURCES), None)
            is_trusted = trusted_src is not None
            primary_src = trusted_src or sources[0]
            resolved_source_id = primary_src.get("publisher_source_id") or bv_id
            resolved_source_url = primary_src.get("source_url") or f"internal://{bv_id}"

            fact_ingested_at = ingested_at
        else:
            is_trusted = claim.source_id in WHITELIST_SOURCES
            resolved_source_id = claim.source_id
            resolved_source_url = f"internal://{claim.source_id}"
            fact_ingested_at = ingested_at

        confidence = 0.9 if is_trusted else 0.5
        adjudication_status = "AUTO_ACCEPTED" if is_trusted else "PENDING_REVIEW"

        # No revision or retraction rule is approved yet. Conflicts were queued
        # above; only initial positive claims can create a FactVersion here.
        supersedes_version_id = None
        revision_type = "creation"

        fact = FactVersion(
            fact_version_id=fact_version_id,
            logical_fact_id=logical_fact_id,
            subject_id=subject_id,
            relation_id=claim.relation_name,
            object_id=object_id,
            valid_from=valid_from,
            valid_to=valid_to,
            evidence_observed_at=observed_at,
            ingested_at_real=fact_ingested_at,
            supersedes_version_id=supersedes_version_id,
            revision_type=revision_type,
            source_id=resolved_source_id,
            source_url=resolved_source_url,
            evidence_span_start=claim.evidence_span_start,
            evidence_span_end=claim.evidence_span_end,
            evidence_text_hash=claim.evidence_text_hash,
            extractor_version=extractor_version,
            entity_map_version=resolved_map_version,
            confidence=confidence,
            adjudication_status=adjudication_status,
            supporting_claim_ids=(claim.claim_id,),
        )

        if fact.adjudication_status == "AUTO_ACCEPTED":
            accepted.append(fact)
            latest_by_logical_id[logical_fact_id] = fact
        else:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "NON_WHITELIST_SOURCE",
                "claim": claim,
                "provisional_fact": fact
            })

    return accepted, review_queue
