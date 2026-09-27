"""Extraction job integrating LLM."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .claims import extract_claims, resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id, utc_now_iso
from .llm_adapter import OfflineMockAdapter, LocalOpenAIAdapter
from .run import create_stage_manifest, get_run_dir, resolve_run_table_path
from .storage import read_yaml, write_json_immutable, write_parquet_immutable
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
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)

    # 1. Check and load required upstream provenance tables early (fail-closed)
    memberships_path = resolve_run_table_path(repo_root, run_id, "document_memberships")
    retrievals_path = resolve_run_table_path(repo_root, run_id, "retrievals")
    source_versions_path = resolve_run_table_path(repo_root, run_id, "source_versions")
    for table_name, path in (
        ("document_memberships", memberships_path),
        ("retrievals", retrievals_path),
        ("source_versions", source_versions_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Missing required {table_name} provenance table: {path}")

    memberships_rows = pq.read_table(memberships_path).to_pylist()
    retrievals_rows = pq.read_table(retrievals_path).to_pylist()
    source_versions_rows = pq.read_table(source_versions_path).to_pylist()

    import json
    retrieval_by_id = {r["retrieval_id"]: r for r in retrievals_rows if r.get("retrieval_id")}
    body_to_source: dict[str, str] = {}
    for m in memberships_rows:
        bv = m.get("body_variant_id")
        if not bv or bv in body_to_source:
            continue
        r_ids_raw = m.get("retrieval_ids_json")
        try:
            r_ids = json.loads(r_ids_raw) if isinstance(r_ids_raw, str) else r_ids_raw
        except Exception:
            r_ids = []
        if isinstance(r_ids, list):
            for r_id in r_ids:
                if r_id in retrieval_by_id and retrieval_by_id[r_id].get("source_id"):
                    body_to_source[bv] = retrieval_by_id[r_id]["source_id"]
                    break

    table = pq.read_table(body_variants_path)
    body_variant_ids = table.column("body_variant_id").to_pylist()
    body_blobs = table.column("body_blob_relative_path").to_pylist()

    extracted_claims = []
    all_candidates: list[ClaimCandidate] = []
    all_dlq: list[dict[str, Any]] = []

    for b_id, b_path in zip(body_variant_ids, body_blobs):
        full_path = run_dir / b_path
        if not full_path.is_file() and body_variants_path.parent.parent != run_dir:
            full_path = body_variants_path.parent.parent / b_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Missing referenced body blob for variant {b_id}: {b_path}")

        text = full_path.read_text(encoding="utf-8")

        valid_claims, dlq = extract_claims(
            text=text,
            body_variant_id=b_id,
            cache_dir=cache_dir,
            ontology=ontology,
            adapter=adapter
        )
        if dlq:
            all_dlq.extend(dlq)

        all_candidates.extend(valid_claims)
        for claim in valid_claims:
            resolved_source = body_to_source.get(claim.body_variant_id, claim.body_variant_id)
            extracted_claims.append({
                "schema_version": CONTRACT_VERSION,
                "claim_id": claim.claim_id,
                "body_variant_id": claim.body_variant_id,
                "source_id": resolved_source,
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

    # 2. Resolve the complete evidence chain before committing either extraction artifact.
    provenances = resolve_claim_provenance(
        claims=all_candidates,
        memberships=memberships_rows,
        retrievals=retrievals_rows,
        source_versions=source_versions_rows,
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

    # 3. Persist tables and DLQ
    claims_parquet = run_dir / "tables" / "extracted_claims.parquet"
    provenance_parquet = run_dir / "tables" / "claim_provenance.parquet"
    dlq_json = run_dir / "reports" / "extraction_dlq.json"

    write_parquet_immutable(
        claims_parquet,
        "extracted_claims",
        extracted_claims
    )
    write_parquet_immutable(
        provenance_parquet,
        "claim_provenance",
        claim_provenance_rows
    )
    write_json_immutable(
        dlq_json,
        {
            "schema_version": CONTRACT_VERSION,
            "run_id": run_id,
            "created_at_real": utc_now_iso(),
            "dlq_count": len(all_dlq),
            "dlq_records": all_dlq,
        },
    )

    provenance_count = len(claim_provenance_rows)

    # 4. Stage manifest & conservation metrics
    create_stage_manifest(
        repo_root,
        run_id,
        "extraction",
        input_artifacts=[
            {"table": "body_variants", "path": str(body_variants_path)},
            {"table": "document_memberships", "path": str(memberships_path)},
            {"table": "retrievals", "path": str(retrievals_path)},
            {"table": "source_versions", "path": str(source_versions_path)},
        ],
        output_artifacts=[
            {"table": "extracted_claims", "path": str(claims_parquet), "count": len(extracted_claims)},
            {"table": "claim_provenance", "path": str(provenance_parquet), "count": provenance_count},
        ],
        conservation_metrics={
            "body_variants_count": len(body_variant_ids),
            "extracted_claims_count": len(extracted_claims),
            "dlq_count": len(all_dlq),
        },
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "extracted_claims_count": len(extracted_claims),
        "claim_provenance_count": provenance_count,
        "dlq_count": len(all_dlq),
    }
