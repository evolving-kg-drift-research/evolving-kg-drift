import re
from datetime import datetime, timezone
from typing import Any, Iterable

from temporal.schema import Claim, FactVersion, ContractError
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

def resolve_entity(mention: str, catalog: dict[str, str], lower_catalog: dict[str, str] = None) -> str | None:
    """Exact matching or alias mapping to find entities in the catalog."""
    if not mention or not mention.strip():
        return None

    # Exact match
    if mention in catalog:
        return catalog[mention]

    # Simple lowercase exact match for approved aliases
    mention_lower = mention.lower().strip()
    if lower_catalog and mention_lower in lower_catalog:
        return lower_catalog[mention_lower]

    for k, v in catalog.items():
        if k.lower().strip() == mention_lower:
            return v

    return None

def adjudicate_claims(
    claims: Iterable[Claim],
    observation_times: dict[str, datetime], # Map from claim_id to evidence_observed_at
    ingested_at: datetime,
    entity_catalog: dict[str, str], # Maps raw mentions to canonical IDs
    extractor_version: str = "v1",
    entity_map_version: str = "v1",
    trusted_sources: set[str] | None = None,
) -> tuple[list[FactVersion], list[dict[str, Any]]]:
    """
    Adjudicate extracted claims into FactVersions.
    Returns (accepted_facts, queued_for_review)
    """
    accepted = []
    review_queue = []

    active_trusted = set(trusted_sources) if trusted_sources is not None else set(WHITELIST_SOURCES)
    lower_catalog = {k.lower().strip(): v for k, v in entity_catalog.items()}

    for claim in claims:
        # Resolve entities with exact/alias matching
        subject_id = resolve_entity(claim.subject_mention, entity_catalog, lower_catalog)
        object_id = resolve_entity(claim.object_mention, entity_catalog, lower_catalog)

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

        # Use extracted dates if available (do not truncate future dates)
        valid_from = parse_extracted_date(claim.valid_from_extracted, observed_at)
        valid_to = parse_extracted_date(claim.valid_to_extracted, None) if claim.valid_to_extracted else None

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
        is_trusted = (claim.source_id in active_trusted) or ("*" in active_trusted)
        confidence = 0.9 if is_trusted else 0.5

        # In a complete implementation, this would look up prior FactVersions for this logical_fact_id
        # and assign "correction", "state_change", or "retract" based on temporal overlap and rules.
        # For this initial fix, we will keep it simple but ensure it's structurally ready for supersedes.
        # We assume fresh facts are "creation" unless specified by the claim logic.
        revision_type = "creation"
        supersedes_version_id = None

        # If the claim was explicitly marked as a retraction (in a real pipeline, via NLP classification)
        # revision_type = "retract"

        try:
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
                supersedes_version_id=supersedes_version_id,
                revision_type=revision_type,
                source_id=claim.source_id,
                source_url=f"internal://{claim.source_id}", # Placeholder
                evidence_span_start=claim.evidence_span_start,
                evidence_span_end=claim.evidence_span_end,
                evidence_text_hash=claim.evidence_text_hash,
                extractor_version=extractor_version,
                entity_map_version=entity_map_version,
                confidence=confidence,
                adjudication_status="AUTO_ACCEPTED" if is_trusted else "PENDING_REVIEW"
            )
        except ContractError as e:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "CONTRACT_ERROR",
                "claim": claim,
                "error": str(e)
            })
            continue

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
