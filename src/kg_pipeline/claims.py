from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from temporal.schema import Claim, ClaimCandidate, ClaimProvenance, ContractError
from .llm_cache import get_cache_key, get_cached_response, set_cached_response
from .hashing import sha256_text

from .llm_adapter import generate_extraction_prompt, LLMAdapter

def extract_claims(
    text: str,
    body_variant_id: str = "",
    cache_dir: Path | None = None,
    ontology: list[str] | None = None,
    adapter: LLMAdapter | None = None,
    source_id: str = "",
) -> tuple[list[ClaimCandidate], list[dict[str, Any]]]:
    """
    Extract claim candidates from text representation.
    Returns a tuple of (valid_claim_candidates, dead_letter_queue_entries).
    """
    bv_id = body_variant_id or source_id
    if not bv_id:
        raise ContractError("body_variant_id is required for claim extraction.")

    if ontology is None:
        ontology = []
    if cache_dir is None:
        cache_dir = Path("runs/default/llm_cache")
    if adapter is None:
        from .llm_adapter import OfflineMockAdapter
        adapter = OfflineMockAdapter({"claims": []})

    prompt = generate_extraction_prompt(text, ontology)
    config = {"temperature": adapter.temperature}
    cache_key = get_cache_key(prompt, adapter.model, config)

    response = get_cached_response(cache_dir, cache_key)
    if response is None:
        response = adapter(prompt)
        set_cached_response(cache_dir, cache_key, response)

    if not isinstance(response, dict):
        response = {}

    # Response should have a "claims" list
    raw_claims = response.get("claims", [])
    if not isinstance(raw_claims, list):
        raw_claims = []

    valid_claims = []
    dlq = []

    text_hash = sha256_text(text)

    for i, rc in enumerate(raw_claims):
        try:
            if not isinstance(rc, dict):
                raise ContractError("Claim is not a dictionary.")

            relation_name = rc.get("relation_name", "")
            if relation_name not in ontology:
                raise ContractError(f"Relation '{relation_name}' is not in the ontology.")

            start_idx = rc.get("evidence_span_start")
            end_idx = rc.get("evidence_span_end")

            if start_idx is None or end_idx is None:
                raise ContractError("Evidence span offsets are mandatory.")

            if start_idx < 0 or end_idx > len(text):
                raise ContractError("Span offsets are out of bounds.")

            extracted_text = text[start_idx:end_idx].strip()
            if not extracted_text:
                raise ContractError("Extracted evidence span is empty or whitespace.")

            subject_mention = rc.get("subject_mention", "")
            object_mention = rc.get("object_mention", "")

            # Sub-string match validation (naive but better than nothing)
            if subject_mention.lower() not in extracted_text.lower() and object_mention.lower() not in extracted_text.lower():
                 raise ContractError("Neither subject nor object mention found in the extracted evidence span.")

            claim = ClaimCandidate(
                claim_id=f"{cache_key}_{i}",
                body_variant_id=bv_id,
                subject_mention=subject_mention,
                relation_name=relation_name,
                object_mention=object_mention,
                evidence_span_start=start_idx,
                evidence_span_end=end_idx,
                evidence_text_hash=text_hash,
                valid_from_extracted=rc.get("valid_from_extracted"),
                valid_to_extracted=rc.get("valid_to_extracted"),
                is_negative=rc.get("is_negative", False),
                is_speculative=rc.get("is_speculative", False)
            )

            valid_claims.append(claim)
        except ContractError as e:
            dlq.append({
                "raw_claim": rc,
                "error": str(e),
                "source_id": bv_id
            })

    return valid_claims, dlq


def resolve_claim_provenance(
    claims: list[ClaimCandidate],
    memberships: list[dict[str, Any]],
    retrievals: list[dict[str, Any]],
) -> list[ClaimProvenance]:
    """
    Resolve multi-hop provenance from ClaimCandidate to its true source version and retrieval.
    Prevents provenance collapse when identical body variants originate from multiple sources.
    """
    memberships_by_body: dict[str, list[dict[str, Any]]] = {}
    for m in memberships:
        bv_id = m.get("body_variant_id")
        if bv_id:
            memberships_by_body.setdefault(bv_id, []).append(m)

    retrievals_by_id: dict[str, dict[str, Any]] = {}
    for r in retrievals:
        r_id = r.get("retrieval_id")
        if r_id:
            retrievals_by_id[r_id] = r

    provenance_records: list[ClaimProvenance] = []

    for claim in claims:
        matching_memberships = memberships_by_body.get(claim.body_variant_id, [])
        for mem in matching_memberships:
            mem_id = mem.get("membership_id", "")
            raw_blob_sha = mem.get("raw_blob_sha256", "")
            source_version_id = mem.get("source_version_id") or mem.get("raw_candidate_id", "")

            r_ids_raw = mem.get("retrieval_ids_json", "[]")
            try:
                r_ids = json.loads(r_ids_raw) if isinstance(r_ids_raw, str) else (r_ids_raw or [])
            except (json.JSONDecodeError, TypeError):
                r_ids = []

            for r_id in r_ids:
                retrieval = retrievals_by_id.get(r_id, {})
                pub_source_id = retrieval.get("source_id", "unknown_source")
                source_url = retrieval.get("final_url") or retrieval.get("requested_url", "")

                provenance_records.append(
                    ClaimProvenance(
                        claim_id=claim.claim_id,
                        membership_id=mem_id,
                        source_version_id=source_version_id,
                        retrieval_id=r_id,
                        raw_blob_sha256=raw_blob_sha,
                        publisher_source_id=pub_source_id,
                        source_url=source_url,
                    )
                )

    return provenance_records


