"""Extraction job integrating LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .claims import extract_claims, resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id
from .llm_adapter import OfflineMockAdapter, LocalOpenAIAdapter
from .run import get_run_dir, resolve_run_table_path
from .storage import write_parquet_immutable, read_yaml
from temporal.schema import ClaimCandidate

logger = logging.getLogger(__name__)

def run_extraction(repo_root: Path, run_id: str, *, enforce_gate_a: bool = False) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)

    if enforce_gate_a:
        from .gates import latest_gate_a_report
        gate_report = latest_gate_a_report(run_dir)
        if not gate_report:
            raise PermissionError(f"Extraction blocked: Gate A has not been evaluated for run {run_id}")
        if gate_report.get("status") != "PASS":
            raise PermissionError(f"Extraction blocked: Gate A status is {gate_report.get('status')}, expected PASS")

    body_variants_path = resolve_run_table_path(repo_root, run_id, "body_variants")
    if not body_variants_path.is_file():
        raise FileNotFoundError(f"Missing {body_variants_path}")

    # Load configuration
    config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
    config = read_yaml(config_path) if config_path.is_file() else {}
    res_cfg = config.get("resolved_config", {})
    raw_ont = res_cfg.get("ontology") or config.get("ontology")
    if isinstance(raw_ont, dict) and "relations" in raw_ont:
        ontology = list(raw_ont["relations"].keys())
    elif isinstance(raw_ont, (list, set, tuple)):
        ontology = list(raw_ont)
    else:
        ontology = ["is_CEO_of", "acquired_by", "released_by", "headquartered_in"]

    # Determine adapter mode
    adapter_config = res_cfg.get("llm_adapter") or config.get("llm_adapter", {})
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
    all_candidates: list[ClaimCandidate] = []

    for b_id, b_path in zip(body_variant_ids, body_blobs):
        full_path = run_dir / b_path
        if not full_path.is_file() and body_variants_path.parent.parent != run_dir:
            full_path = body_variants_path.parent.parent / b_path
        if not full_path.is_file():
            continue

        text = full_path.read_text(encoding="utf-8")

        valid_claims, _ = extract_claims(
            text=text,
            body_variant_id=b_id,
            cache_dir=cache_dir,
            ontology=ontology,
            adapter=adapter
        )

        all_candidates.extend(valid_claims)
        for claim in valid_claims:
            extracted_claims.append({
                "schema_version": CONTRACT_VERSION,
                "claim_id": claim.claim_id,
                "body_variant_id": claim.body_variant_id,
                "source_id": claim.body_variant_id,
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

    # Resolve multi-hop claim provenance if document memberships & retrievals exist
    memberships_path = resolve_run_table_path(repo_root, run_id, "document_memberships")
    retrievals_path = resolve_run_table_path(repo_root, run_id, "retrievals")
    source_versions_path = resolve_run_table_path(repo_root, run_id, "source_versions")
    provenance_count = 0

    if memberships_path.is_file() and retrievals_path.is_file():
        m_table = pq.read_table(memberships_path)
        r_table = pq.read_table(retrievals_path)
        s_list = pq.read_table(source_versions_path).to_pylist() if source_versions_path.is_file() else None
        provenances = resolve_claim_provenance(
            claims=all_candidates,
            memberships=m_table.to_pylist(),
            retrievals=r_table.to_pylist(),
            source_versions=s_list,
        )
        claim_provenance_rows = []
        for prov in provenances:
            provenance_id = stable_id(
                "claimprovenance",
                {
                    "claim_id": prov.claim_id,
                    "membership_id": prov.membership_id,
                    "source_version_id": prov.source_version_id,
                    "retrieval_id": prov.retrieval_id,
                    "raw_blob_sha256": prov.raw_blob_sha256,
                },
            )
            claim_provenance_rows.append({
                "schema_version": CONTRACT_VERSION,
                "provenance_id": provenance_id,
                "claim_id": prov.claim_id,
                "membership_id": prov.membership_id,
                "source_version_id": prov.source_version_id,
                "retrieval_id": prov.retrieval_id,
                "raw_blob_sha256": prov.raw_blob_sha256,
                "publisher_source_id": prov.publisher_source_id,
                "source_url": prov.source_url,
            })

        write_parquet_immutable(
            run_dir / "tables" / "claim_provenance.parquet",
            "claim_provenance",
            claim_provenance_rows
        )
        provenance_count = len(claim_provenance_rows)

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "extracted_claims_count": len(extracted_claims),
        "claim_provenance_count": provenance_count,
    }
