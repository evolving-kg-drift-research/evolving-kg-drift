from datetime import datetime, timezone
from typing import Any, Iterable

from temporal.schema import Claim, FactVersion
from temporal.snapshot import compute_logical_fact_id

WHITELIST_SOURCES = {"trusted_registry_1", "official_feed"}

def parse_extracted_date(date_str: str | None, default: datetime | None = None) -> datetime | None:
    if not date_str:
        return default
    try:
        # Assuming date_str is in ISO format
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return default

def fuzzy_match_entity(mention: str, catalog: dict[str, str]) -> str | None:
    """Fuzzy matching to find entities in the catalog."""
    if not mention or not isinstance(mention, str) or not mention.strip():
        return None

    mention_clean = mention.strip()
    if mention_clean in catalog:
        return catalog[mention_clean]

    # Lowercase exact match
    mention_lower = mention_clean.lower()
    for k, v in catalog.items():
        if k.lower() == mention_lower:
            return v

    # Substring match only for meaningful mentions (at least 3 characters)
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
) -> tuple[list[FactVersion], list[dict[str, Any]]]:
    """
    Adjudicate extracted claims into FactVersions.
    Returns (accepted_facts, queued_for_review)
    """
    accepted = []
    review_queue = []

    latest_by_logical_id: dict[str, FactVersion] = {}
    if existing_facts:
        for ef in existing_facts:
            curr = latest_by_logical_id.get(ef.logical_fact_id)
            if curr is None or (ef.evidence_observed_at, ef.fact_version_id) > (curr.evidence_observed_at, curr.fact_version_id):
                latest_by_logical_id[ef.logical_fact_id] = ef

    # Process claims chronologically by observation time so revision chains are ordered
    sorted_claims = sorted(
        claims,
        key=lambda c: (
            observation_times.get(c.claim_id, datetime.min.replace(tzinfo=timezone.utc)),
            c.claim_id,
        )
    )

    for claim in sorted_claims:
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
                "reason": "EVIDENCE_TIME_UNAVAILABLE",
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

        # Negative claim without an existing fact to retract cannot be applied
        if claim.is_negative and prior_fact is None:
            review_queue.append({
                "claim_id": claim.claim_id,
                "reason": "NEGATIVE_WITHOUT_PRIOR_FACT",
                "claim": claim
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

            # Resolve actual acquisition timestamp (A08)
            fact_ingested_at = ingested_at
            if primary_src.get("retrieved_at_real"):
                try:
                    dt_ing = datetime.fromisoformat(primary_src["retrieved_at_real"])
                    fact_ingested_at = dt_ing if dt_ing.tzinfo else dt_ing.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
        else:
            is_trusted = claim.source_id in WHITELIST_SOURCES
            resolved_source_id = claim.source_id
            resolved_source_url = f"internal://{claim.source_id}"
            fact_ingested_at = ingested_at

        confidence = 0.9 if is_trusted else 0.5
        adjudication_status = "AUTO_ACCEPTED" if is_trusted else "PENDING_REVIEW"

        # Determine revision chain
        prior_fact = latest_by_logical_id.get(logical_fact_id)
        if prior_fact is not None:
            supersedes_version_id = prior_fact.fact_version_id
            if claim.is_negative:
                revision_type = "retraction"
            elif prior_fact.subject_id != subject_id or prior_fact.object_id != object_id:
                revision_type = "state_change"
            else:
                revision_type = "correction"
        else:
            supersedes_version_id = None
            revision_type = "retraction" if claim.is_negative else "creation"

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
            entity_map_version=entity_map_version,
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
