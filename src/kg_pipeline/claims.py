from pathlib import Path
from typing import Any

from temporal.schema import Claim, ContractError
from .llm_cache import get_cache_key, get_cached_response, set_cached_response
from .hashing import sha256_text

# In a real scenario, this would call an LLM API.
# For offline mode, it just raises an exception if not cached, or we can provide a mock callable.
def extract_claims(
    text: str, 
    source_id: str, 
    cache_dir: Path, 
    model: str = "offline-mock", 
    llm_callable=None
) -> tuple[list[Claim], list[dict[str, Any]]]:
    """
    Extract claims from text. 
    Returns a tuple of (valid_claims, dead_letter_queue_entries).
    """
    prompt = f"Extract claims from the following text:\n\n{text}"
    config = {"temperature": 0.0}
    cache_key = get_cache_key(prompt, model, config)
    
    response = get_cached_response(cache_dir, cache_key)
    if response is None:
        if llm_callable:
            response = llm_callable(prompt, model, config)
            set_cached_response(cache_dir, cache_key, response)
        else:
            raise RuntimeError(f"Offline mode: No cached response for {cache_key}")

    # Response should have a "claims" list
    raw_claims = response.get("claims", [])
    valid_claims = []
    dlq = []
    
    text_hash = sha256_text(text)
    
    for i, rc in enumerate(raw_claims):
        try:
            claim = Claim(
                claim_id=f"{cache_key}_{i}",
                source_id=source_id,
                subject_mention=rc.get("subject_mention", ""),
                relation_name=rc.get("relation_name", ""),
                object_mention=rc.get("object_mention", ""),
                evidence_span_start=rc.get("evidence_span_start"),
                evidence_span_end=rc.get("evidence_span_end"),
                evidence_text_hash=text_hash
            )
            
            # Additional validation: span bounds must be within text
            if claim.evidence_span_end > len(text):
                raise ContractError("Span end is out of bounds.")
            if claim.evidence_span_start < 0:
                raise ContractError("Span start is negative.")
                
            valid_claims.append(claim)
        except ContractError as e:
            dlq.append({
                "raw_claim": rc,
                "error": str(e),
                "source_id": source_id
            })
            
    return valid_claims, dlq

