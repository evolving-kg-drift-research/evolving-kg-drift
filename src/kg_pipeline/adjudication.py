from datetime import datetime
from typing import Any, Iterable

from temporal.schema import Claim, FactVersion
from .hashing import sha256_text

WHITELIST_SOURCES = {"trusted_registry_1", "official_feed"}

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
    
    # Very simple adjudication:
    # 1. Map entities
    # 2. Check source whitelist -> auto-accept
    # 3. Else -> manual review queue
    
    for claim in claims:
        # Resolve entities
        subject_id = entity_catalog.get(claim.subject_mention)
        object_id = entity_catalog.get(claim.object_mention)
        
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

        # Deterministic IDs
        logical_fact_id = sha256_text(f"{subject_id}|{claim.relation_name}|{object_id}")[:16]
        fact_version_id = f"{logical_fact_id}_{claim.claim_id}"

        fact = FactVersion(
            fact_version_id=fact_version_id,
            logical_fact_id=logical_fact_id,
            subject_id=subject_id,
            relation_id=claim.relation_name,
            object_id=object_id,
            valid_from=observed_at, # Default to observed_at if not explicitly temporal
            valid_to=None,
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
            confidence=1.0,
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
