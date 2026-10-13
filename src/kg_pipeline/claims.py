from pathlib import Path
from typing import Any

from temporal.schema import Claim, ContractError
from .llm_cache import get_cache_key, get_cached_response, set_cached_response
from .hashing import sha256_text

from .llm_adapter import generate_extraction_prompt, LLMAdapter

def extract_claims(
    text: str,
    source_id: str,
    cache_dir: Path,
    ontology: list[str],
    adapter: LLMAdapter
) -> tuple[list[Claim], list[dict[str, Any]]]:
    """
    Extract claims from text.
    Returns a tuple of (valid_claims, dead_letter_queue_entries).
    """
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

            claim = Claim(
                claim_id=f"{cache_key}_{i}",
                source_id=source_id,
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
                "source_id": source_id
            })

    return valid_claims, dlq


