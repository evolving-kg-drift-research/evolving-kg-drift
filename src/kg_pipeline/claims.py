from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from temporal.schema import ClaimCandidate, ClaimProvenance, ContractError
from .llm_cache import (
    CACHE_FORMAT_VERSION,
    CacheIntegrityError,
    get_cache_key,
    get_cached_response,
    set_cached_response,
)
from .hashing import canonical_json, sha256_text
from .evidence import EvidenceSpan

from .llm_adapter import generate_extraction_prompt, LLMAdapter

EXTRACTOR_VERSION = "claim-extractor-v2"
PROMPT_TEMPLATE_VERSION = "claim-prompt-v2"
CLAIM_RESPONSE_SCHEMA_VERSION = "claim-response-v1"

def extract_claims(
    text: str,
    body_variant_id: str = "",
    cache_dir: Path | None = None,
    ontology: list[str] | dict[str, Any] | None = None,
    adapter: LLMAdapter | None = None,
    source_id: str = "",
    locked_replay: bool = False,
    body_parser_version: str | None = None,
    body_parser_fingerprint: str | None = None,
    normalization_version: str | None = None,
    dependency_lock_sha256: str | None = None,
) -> tuple[list[ClaimCandidate], list[dict[str, Any]]]:
    """
    Extract claim candidates from text representation.
    Returns a tuple of (valid_claim_candidates, dead_letter_queue_entries).
    """
    bv_id = body_variant_id or source_id
    if not bv_id:
        raise ContractError("body_variant_id is required for claim extraction.")

    if ontology is None:
        raise ContractError("Claim extraction requires an explicit versioned ontology.")
    if cache_dir is None:
        raise ContractError("Claim extraction requires an explicit run-scoped cache directory.")
    if adapter is None:
        raise ContractError("Claim extraction requires an explicitly configured adapter.")

    if isinstance(ontology, dict):
        relations_val = ontology.get("relations")
        if isinstance(relations_val, dict):
            prompt_ontology = list(relations_val.keys())
        elif isinstance(relations_val, (list, set, tuple)):
            prompt_ontology = list(relations_val)
        else:
            prompt_ontology = list(ontology.keys())
    else:
        prompt_ontology = list(ontology)
    if not prompt_ontology or any(not isinstance(name, str) or not name.strip() for name in prompt_ontology):
        raise ContractError("Claim extraction ontology must contain non-empty relation identifiers.")

    prompt = generate_extraction_prompt(text, prompt_ontology)
    adapter_metadata = adapter.cache_metadata()
    request_fingerprints = {
        "input_text_sha256": sha256_text(text),
        "body_parser_version": body_parser_version,
        "body_parser_fingerprint": body_parser_fingerprint,
        "normalization_version": normalization_version,
        "dependency_lock_sha256": dependency_lock_sha256,
        "ontology_sha256": sha256_text(canonical_json(prompt_ontology)),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "response_schema_version": CLAIM_RESPONSE_SCHEMA_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "cache_format_version": CACHE_FORMAT_VERSION,
        "adapter": adapter_metadata,
        "runtime": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
        },
    }
    if locked_replay and (
        not adapter_metadata.get("model_revision")
        or not adapter_metadata.get("tokenizer_revision")
        or not body_parser_version
        or not body_parser_fingerprint
        or not normalization_version
    ):
        raise ContractError(
            "Locked extraction replay requires pinned model/tokenizer revisions "
        "and the parser/normalization fingerprints."
        )
    decoding_config = adapter_metadata.get("decoding_config")
    if not isinstance(decoding_config, dict):
        raise ContractError("Extractor adapter must provide a decoding configuration.")
    cache_key = get_cache_key(prompt, adapter.model, decoding_config, request_fingerprints)

    response = get_cached_response(cache_dir, cache_key, request_fingerprints)
    if response is None:
        if locked_replay:
            raise CacheIntegrityError(
                f"Locked extraction replay requires an immutable cached response for {cache_key}."
            )
        response = adapter(prompt)
        if not isinstance(response, dict):
            raise ContractError("Extractor adapter response must be a JSON object.")
        set_cached_response(cache_dir, cache_key, response, request_fingerprints)

    if not isinstance(response, dict):
        raise ContractError("Cached extractor response must be a JSON object.")

    # Response should have a "claims" list
    raw_claims = response.get("claims", [])
    if not isinstance(raw_claims, list):
        raw_claims = []

    valid_claims = []
    dlq = []
    valid_relations = set(prompt_ontology)

    for i, rc in enumerate(raw_claims):
        try:
            if not isinstance(rc, dict):
                raise ContractError("Claim is not a dictionary.")

            relation_name = rc.get("relation_name", "")
            if relation_name not in valid_relations:
                raise ContractError(f"Relation '{relation_name}' is not in the ontology.")

            start_idx = rc.get("evidence_span_start")
            end_idx = rc.get("evidence_span_end")

            if type(start_idx) is not int or type(end_idx) is not int:
                raise ContractError("Evidence span offsets are mandatory.")

            if not normalization_version:
                if locked_replay:
                    raise ContractError("Evidence span requires an explicit normalization version.")
                span = EvidenceSpan.from_text(
                    text, start_idx, end_idx, "clean-text-identity-v1"
                )
            else:
                span = EvidenceSpan.from_text(text, start_idx, end_idx, normalization_version)

            extracted_text = text[start_idx:end_idx].strip()
            if not extracted_text:
                raise ContractError("Extracted evidence span is empty or whitespace.")

            subject_mention = rc.get("subject_mention", "")
            object_mention = rc.get("object_mention", "")
            if not isinstance(subject_mention, str) or not subject_mention.strip():
                raise ContractError("Subject mention is missing from the candidate.")
            if not isinstance(object_mention, str) or not object_mention.strip():
                raise ContractError("Object mention is missing from the candidate.")

            # Both entity roles must be grounded in the exact referenced slice.
            folded_span = extracted_text.casefold()
            if subject_mention.strip().casefold() not in folded_span:
                raise ContractError("Subject mention is not grounded in the evidence span.")
            if object_mention.strip().casefold() not in folded_span:
                raise ContractError("Object mention is not grounded in the evidence span.")

            provided_hash = rc.get("evidence_text_hash")
            if provided_hash in ("placeholder_hash", "placeholder"):
                raise ContractError("Fabricated placeholder evidence text hash.")

            span_hash = span.text_sha256

            claim = ClaimCandidate(
                claim_id=f"{cache_key}_{i}",
                body_variant_id=bv_id,
                subject_mention=subject_mention,
                relation_name=relation_name,
                object_mention=object_mention,
                evidence_span_start=start_idx,
                evidence_span_end=end_idx,
                evidence_text_hash=span_hash,
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
