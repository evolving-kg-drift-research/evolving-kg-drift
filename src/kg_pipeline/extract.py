"""Extraction job integrating LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .claims import extract_claims
from .llm_adapter import OfflineMockAdapter, LocalOpenAIAdapter
from .run import get_run_dir
from .storage import write_parquet_immutable, read_yaml

logger = logging.getLogger(__name__)

def run_extraction(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    body_variants_path = run_dir / "tables" / "body_variants.parquet"
    if not body_variants_path.is_file():
        raise FileNotFoundError(f"Missing {body_variants_path}")

    # Load configuration
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    ontology = config.get("ontology", ["CEO", "ACQUIRED", "LOCATED_IN"])

    # Determine adapter mode
    adapter_config = config.get("llm_adapter", {})
    if adapter_config.get("type") == "local":
        adapter = LocalOpenAIAdapter(
            base_url=adapter_config.get("base_url", "http://localhost:8000/v1"),
            model=adapter_config.get("model", "llama3"),
            temperature=adapter_config.get("temperature", 0.0)
        )
    else:
        adapter = OfflineMockAdapter({"claims": []})

    cache_dir = run_dir / "llm_cache"
    cache_dir.mkdir(exist_ok=True, parents=True)

    table = pq.read_table(body_variants_path)
    body_variant_ids = table.column("body_variant_id").to_pylist()
    body_blobs = table.column("body_blob_relative_path").to_pylist()

    extracted_claims = []

    for b_id, b_path in zip(body_variant_ids, body_blobs):
        full_path = run_dir / b_path
        if not full_path.is_file():
            continue

        text = full_path.read_text(encoding="utf-8")

        valid_claims, _ = extract_claims(
            text=text,
            source_id=b_id,
            cache_dir=cache_dir,
            ontology=ontology,
            adapter=adapter
        )

        for claim in valid_claims:
            extracted_claims.append({
                "claim_id": claim.claim_id,
                "source_id": claim.source_id,
                "subject_mention": claim.subject_mention,
                "relation_name": claim.relation_name,
                "object_mention": claim.object_mention,
                "evidence_span_start": claim.evidence_span_start,
                "evidence_span_end": claim.evidence_span_end,
                "evidence_text_hash": claim.evidence_text_hash,
                "valid_from_extracted": claim.valid_from_extracted,
                "valid_to_extracted": claim.valid_to_extracted,
                "is_negative": claim.is_negative,
                "is_speculative": claim.is_speculative
            })

    write_parquet_immutable(
        run_dir / "tables" / "extracted_claims.parquet",
        "extracted_claims",
        extracted_claims
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "extracted_claims_count": len(extracted_claims)
    }
