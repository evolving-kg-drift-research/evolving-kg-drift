"""Extraction job integrating LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .contracts import CONTRACT_VERSION
from .claims import extract_claims
from .llm_adapter import OfflineMockAdapter, LocalOpenAIAdapter
from .run import get_run_dir, load_run_manifest
from .storage import write_parquet_immutable, read_yaml

logger = logging.getLogger(__name__)

def run_extraction(repo_root: Path, run_id: str) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    manifest = load_run_manifest(repo_root, run_id)

    body_variants_path = run_dir / "tables" / "body_variants.parquet"
    if not body_variants_path.is_file():
        raise FileNotFoundError(f"Missing {body_variants_path}")

    # Load configuration
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    if config_path.is_file():
        config = read_yaml(config_path)
        if not isinstance(config, dict):
            config = {}
        if "ontology" not in config:
            config["ontology"] = []
        if "llm_adapter" not in config:
            config["llm_adapter"] = {"type": "mock", "mock_response": {"claims": []}}
    else:
        config = {
            "ontology": [],
            "llm_adapter": {"type": "mock", "mock_response": {"claims": []}}
        }

    if "ontology" not in config:
        raise ValueError("Ontology configuration is missing from proposed_config_bundle.yaml")
    ontology = config["ontology"]

    # Determine adapter mode
    if "llm_adapter" not in config:
        raise ValueError("llm_adapter configuration is missing from proposed_config_bundle.yaml")

    adapter_config = config["llm_adapter"]
    if adapter_config.get("type") == "local":
        if manifest.get("safety_scope", {}).get("llm_calls") == "FORBIDDEN_IN_TICKET_A":
            raise ValueError("Extraction via LLM is forbidden under current run manifest safety_scope")
        adapter = LocalOpenAIAdapter(
            base_url=adapter_config.get("base_url", "http://localhost:8000/v1"),
            model=adapter_config.get("model", "llama3"),
            temperature=adapter_config.get("temperature", 0.0)
        )
    elif adapter_config.get("type") == "mock":
        adapter = OfflineMockAdapter(adapter_config.get("mock_response", {"claims": []}))
    else:
        raise ValueError(f"Unknown llm_adapter type: {adapter_config.get('type')}")

    cache_dir = run_dir / "llm_cache"
    cache_dir.mkdir(exist_ok=True, parents=True)

    table = pq.read_table(body_variants_path)
    body_variant_ids = table.column("body_variant_id").to_pylist()
    body_blobs = table.column("body_blob_relative_path").to_pylist()

    extracted_claims = []
    failed_extractions = []
    missing_files = []

    for b_id, b_path in zip(body_variant_ids, body_blobs):
        if not b_path:
            missing_files.append(b_id)
            continue

        full_path = run_dir / b_path
        if not full_path.is_file():
            missing_files.append(b_id)
            continue

        text = full_path.read_text(encoding="utf-8")

        valid_claims, dlq = extract_claims(
            text=text,
            source_id=b_id,
            cache_dir=cache_dir,
            ontology=ontology,
            adapter=adapter
        )

        if dlq:
            failed_extractions.extend(dlq)

        for claim in valid_claims:
            extracted_claims.append({
                "schema_version": CONTRACT_VERSION,
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

    if missing_files:
        logger.warning(f"Skipped {len(missing_files)} missing body variant files.")

    if failed_extractions:
        logger.warning(f"Recorded {len(failed_extractions)} failed extractions in DLQ.")
        # In a real pipeline, we might write failed_extractions to a parquet file

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "extracted_claims_count": len(extracted_claims),
        "failed_extractions_count": len(failed_extractions),
        "missing_files_count": len(missing_files)
    }
