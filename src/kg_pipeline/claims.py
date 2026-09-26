from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from temporal.schema import ClaimCandidate, ClaimProvenance, ContractError
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

    valid_relations: set[str]
    if isinstance(ontology, dict):
        if "relations" in ontology and isinstance(ontology["relations"], dict):
            valid_relations = set(ontology["relations"].keys())
        else:
            valid_relations = set(ontology.keys())
    elif isinstance(ontology, (list, set, tuple)):
        valid_relations = set(ontology)
    else:
        valid_relations = set()

    for i, rc in enumerate(raw_claims):
        try:
            if not isinstance(rc, dict):
                raise ContractError("Claim is not a dictionary.")

            relation_name = rc.get("relation_name", "")
            if relation_name not in valid_relations:
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
    source_versions: list[dict[str, Any]] | None = None,
) -> list[ClaimProvenance]:
    """
    Resolve multi-hop provenance from ClaimCandidate to its true source version and retrieval.
    Prevents provenance collapse when identical body variants originate from multiple sources.
    """
    memberships_by_body: dict[str, list[dict[str, Any]]] = {}
    membership_ids: set[str] = set()
    for m in memberships:
        mem_id = m.get("membership_id")
        bv_id = m.get("body_variant_id")
        if not mem_id:
            raise ContractError("Membership provenance requires membership_id.")
        if mem_id in membership_ids:
            raise ContractError(f"Duplicate membership_id in provenance inputs: {mem_id}.")
        membership_ids.add(mem_id)
        if bv_id:
            memberships_by_body.setdefault(bv_id, []).append(m)

    retrievals_by_id: dict[str, dict[str, Any]] = {}
    for r in retrievals:
        r_id = r.get("retrieval_id")
        if not r_id:
            raise ContractError("Retrieval provenance requires retrieval_id.")
        if r_id in retrievals_by_id:
            raise ContractError(f"Duplicate retrieval_id in provenance inputs: {r_id}.")
        retrievals_by_id[r_id] = r

    sv_by_retrieval: dict[str, dict[str, Any]] = {}
    if source_versions:
        for sv in source_versions:
            s_vid = sv.get("source_version_id")
            r_id = sv.get("retrieval_id")
            if not s_vid or not r_id:
                raise ContractError("Source-version provenance requires source_version_id and retrieval_id.")
            if r_id in sv_by_retrieval:
                raise ContractError(f"Multiple source versions resolve to retrieval {r_id}.")
            sv_by_retrieval[r_id] = sv

    provenance_records: list[ClaimProvenance] = []

    for claim in claims:
        matching_memberships = memberships_by_body.get(claim.body_variant_id, [])
        if not matching_memberships:
            raise ContractError(f"Claim {claim.claim_id} has no document-membership provenance.")
        for mem in matching_memberships:
            mem_id = mem.get("membership_id")
            raw_blob_sha = mem.get("raw_blob_sha256")
            if not mem_id or not raw_blob_sha:
                raise ContractError(
                    f"Membership for claim {claim.claim_id} requires membership_id and raw_blob_sha256."
                )

            r_ids_raw = mem.get("retrieval_ids_json")
            try:
                r_ids = json.loads(r_ids_raw) if isinstance(r_ids_raw, str) else r_ids_raw
            except (json.JSONDecodeError, TypeError) as exc:
                raise ContractError(f"Invalid retrieval_ids_json for membership {mem_id}.") from exc
            if not isinstance(r_ids, list) or not r_ids:
                raise ContractError(f"Membership {mem_id} has no valid retrieval ID links.")

            for r_id in r_ids:
                retrieval = retrievals_by_id.get(r_id)
                source_version = sv_by_retrieval.get(r_id)
                if retrieval is None or source_version is None:
                    raise ContractError(
                        f"Claim {claim.claim_id} has unresolved retrieval/source-version link {r_id}."
                    )
                if retrieval.get("raw_blob_sha256") != raw_blob_sha or source_version.get("raw_blob_sha256") != raw_blob_sha:
                    raise ContractError(
                        f"Claim {claim.claim_id} provenance hash mismatch for retrieval {r_id}."
                    )
                pub_source_id = retrieval.get("source_id")
                source_url = retrieval.get("final_url") or retrieval.get("requested_url")
                if not pub_source_id or not source_url:
                    raise ContractError(f"Retrieval {r_id} lacks source identity or URL.")

                provenance_records.append(
                    ClaimProvenance(
                        claim_id=claim.claim_id,
                        membership_id=mem_id,
                        source_version_id=source_version["source_version_id"],
                        retrieval_id=r_id,
                        raw_blob_sha256=raw_blob_sha,
                        publisher_source_id=pub_source_id,
                        source_url=source_url,
                    )
                )

    return provenance_records


