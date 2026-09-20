import re
from datetime import datetime, timezone
from typing import Any, Iterable

from temporal.schema import Claim, FactVersion
from .hashing import sha256_text

WHITELIST_SOURCES = {"trusted_registry_1", "official_feed"}

def parse_extracted_date(date_str: str | None, default: datetime) -> datetime:
    if not date_str:
        return default
    try:
        # Assuming date_str is in ISO format
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return default

def fuzzy_match_entity(mention: str, catalog: dict[str, str]) -> str | None:
    """Simple fuzzy matching to find entities in the catalog."""
    if mention in catalog:
        return catalog[mention]

    # Simple lowercase exact match
    mention_lower = mention.lower()
    for k, v in catalog.items():
        if k.lower() == mention_lower:
            return v

    # Simple substring match (naive)
    for k, v in catalog.items():
        if mention_lower in k.lower() or k.lower() in mention_lower:
            return v

    return None

def adjudicate_claims(
    claims: Iterable[Claim],
    observation_times: dict[str, datetime], # Map from claim_id to evidence_observed_at
    ingested_at: datetime,
    entity_catalog: dict[str, str], # Maps raw mentions to canonical IDs
    extractor_version: str = "v1",
    entity_map_version: str = "v1"
) -> tuple[list[FactVersion], list[dict[str, Any]]]:
    """
    Adjudicate extracted claims into FactVersions.
    Returns (accepted_facts, queued_for_review)
    """
    accepted = []
    review_queue = []

    for claim in claims:
        # Resolve entities with fuzzy matching
        subject_id = fuzzy_match_entity(claim.subject_mention, entity_catalog)
        object_id = fuzzy_match_entity(claim.object_mention, entity_catalog)

        if not subject_id or not object_id:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "UNRESOLVED_ENTITY",
                "claim": claim
            })
            continue

        observed_at = observation_times.get(claim.claim_id)
        if not observed_at:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "MISSING_OBSERVATION_TIME",
                "claim": claim
            })
            continue

        # Use extracted dates if available
        valid_from = parse_extracted_date(claim.valid_from_extracted, observed_at)
        valid_to = parse_extracted_date(claim.valid_to_extracted, None) if claim.valid_to_extracted else None

        # Upper-bound verification
        if valid_from > observed_at:
            valid_from = observed_at

        if valid_to and valid_to > observed_at:
            valid_to = observed_at

        # Ignore speculative or negative claims for auto-accept
        if claim.is_speculative or claim.is_negative:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "SPECULATIVE_OR_NEGATIVE",
                "claim": claim
            })
            continue

        # Deterministic IDs
        logical_fact_id = sha256_text(f"{subject_id}|{claim.relation_name}|{object_id}")[:16]
        fact_version_id = f"{logical_fact_id}_{claim.claim_id}"

        # Mapping confidence based on source trust and extraction details
        confidence = 0.9 if claim.source_id in WHITELIST_SOURCES else 0.5

        fact = FactVersion(
            fact_version_id=fact_version_id,
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
            source_id=claim.source_id,
            source_url=f"internal://{claim.source_id}", # Placeholder
            evidence_span_start=claim.evidence_span_start,
            evidence_span_end=claim.evidence_span_end,
            evidence_text_hash=claim.evidence_text_hash,
            extractor_version=extractor_version,
            entity_map_version=entity_map_version,
            confidence=confidence,
            adjudication_status="AUTO_ACCEPTED" if claim.source_id in WHITELIST_SOURCES else "PENDING_REVIEW"
        )

        if fact.adjudication_status == "AUTO_ACCEPTED":
            accepted.append(fact)
        else:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "NON_WHITELIST_SOURCE",
                "claim": claim,
                "provisional_fact": fact
            })

    return accepted, review_queue
