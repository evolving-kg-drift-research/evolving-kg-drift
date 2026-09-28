"""Stage 4.14: Main Corpus Processing Pipeline (Filtering, Extraction, Adjudication, Quality Gate).

Supports resuming via LLM cache and intermediate checkpoint parquet files.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from kg_pipeline.claims import extract_claims
from kg_pipeline.filter import filter_content
from kg_pipeline.llm_adapter import get_llm_adapter
from kg_pipeline.run import get_run_dir
from kg_pipeline.storage import read_yaml, write_parquet_immutable
from kg_pipeline.adjudicate import run_adjudication
from kg_pipeline.quality import run_quality_gate

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("production_pipeline")


def run_production_pipeline(
    repo_root: Path,
    run_id: str = "production_v2",
    llm_mode: str = "local",
    model_name: str = "ag/gemini-3.7-flash-low",
    limit: int | None = None,
    checkpoint_interval: int = 50,
) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    tables_dir = run_dir / "tables"
    cache_dir = run_dir / "llm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # File log handler
    fh = logging.FileHandler(logs_dir / "production_pipeline.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)

    body_variants_path = tables_dir / "body_variants.parquet"
    if not body_variants_path.is_file():
        raise FileNotFoundError(f"Missing {body_variants_path}")

    bv_table = pq.read_table(body_variants_path)
    all_b_ids = bv_table.column("body_variant_id").to_pylist()
    all_b_blobs = bv_table.column("body_blob_relative_path").to_pylist()

    total_docs = len(all_b_ids)
    if limit is not None and limit > 0:
        all_b_ids = all_b_ids[:limit]
        all_b_blobs = all_b_blobs[:limit]
        logger.info(f"Limiting processing to {len(all_b_ids)}/{total_docs} documents.")
    else:
        logger.info(f"Processing all {total_docs} documents in {run_id}.")

    # 1. Load Filter Policy Guidelines
    scope_path = repo_root / "config" / "corpus_scope.yaml"
    if scope_path.exists():
        scope_config = read_yaml(scope_path)
        policy_guidelines = f"Tập trung vào miền: {scope_config.get('domain', {}).get('name', 'AI & Technology')}.\n"
        policy_guidelines += f"Chủ đề chấp nhận (Included): {', '.join(scope_config.get('included_topics', []))}\n"
        policy_guidelines += f"Chủ đề loại trừ (Excluded): {', '.join(scope_config.get('excluded_topics', []))}\n"
        policy_guidelines += scope_config.get('scope_notes', '')
    else:
        policy_guidelines = "Chỉ giữ các nội dung liên quan tới AI & Technology. Bỏ qua thể thao, giải trí."

    # 2. Load Canonical Ontology
    ontology_path = repo_root / "config" / "ontology.yaml"
    if ontology_path.is_file():
        ontology_data = read_yaml(ontology_path)
        ontology = list(ontology_data.get("relations", {}).keys())
    else:
        config_path = run_dir / "inputs" / "proposed_config_bundle.yaml"
        config = read_yaml(config_path) if config_path.is_file() else {}
        ontology = config.get("ontology", [
            "is_CEO_of", "acquired_by", "released_by", "version_of",
            "succeeded_by", "partners_with", "invested_in",
            "integrated_into", "based_on", "works_at"
        ])
    logger.info(f"Loaded ontology with {len(ontology)} relations: {ontology}")

    adapter = get_llm_adapter(mode=llm_mode, model=model_name)

    # ---------------------------------------------------------
    # STEP 4: FILTERING
    # ---------------------------------------------------------
    filter_decisions_path = tables_dir / "filter_decisions.parquet"
    filter_checkpoint_path = tables_dir / "filter_decisions_partial.parquet"
    
    filter_decisions: list[dict[str, Any]] = []
    processed_b_ids = set()

    if filter_decisions_path.is_file():
        logger.info(f"Found completed filter_decisions.parquet ({filter_decisions_path}). Skipping filter loop.")
        filter_decisions = pq.read_table(filter_decisions_path).to_pylist()
    else:
        if filter_checkpoint_path.is_file():
            filter_decisions = pq.read_table(filter_checkpoint_path).to_pylist()
            processed_b_ids = {d["body_variant_id"] for d in filter_decisions}
            logger.info(f"Resuming filtering from checkpoint: {len(processed_b_ids)} documents already processed.")

        logger.info(f"Starting LLM Filtering on remaining {len(all_b_ids) - len(processed_b_ids)} documents...")
        count = len(filter_decisions)

        for b_id, b_path in zip(all_b_ids, all_b_blobs):
            if b_id in processed_b_ids:
                continue

            full_path = run_dir / b_path
            if not full_path.is_file():
                logger.warning(f"Blob file missing for {b_id}: {full_path}")
                continue

            text = full_path.read_text(encoding="utf-8")
            result = filter_content(text, b_id, cache_dir, adapter, policy_guidelines)

            import uuid
            filter_decisions.append({
                "schema_version": "ticket_a_v1",
                "decision_id": f"dec_{uuid.uuid4().hex}",
                "body_variant_id": b_id,
                "decision": result["decision"],
                "reason_code": result["reason_code"],
                "evidence_snippet": result["evidence_snippet"],
                "filter_version": "v1.0"
            })
            processed_b_ids.add(b_id)
            count += 1

            if count % checkpoint_interval == 0:
                logger.info(f"Filtering progress: {count}/{len(all_b_ids)} completed.")
                pq.write_table(pa.Table.from_pylist(filter_decisions), filter_checkpoint_path)

        # Write final immutable table
        write_parquet_immutable(filter_decisions_path, "filter_decisions", filter_decisions)
        if filter_checkpoint_path.is_file():
            filter_checkpoint_path.unlink()
        logger.info(f"Filter stage completed and written to {filter_decisions_path}")

    # Determine accepted documents
    accepted_b_ids = {d["body_variant_id"] for d in filter_decisions if d["decision"] == "include"}
    logger.info(f"Filtering summary: {len(accepted_b_ids)}/{len(filter_decisions)} accepted (include).")

    # ---------------------------------------------------------
    # STEP 5: EXTRACTION
    # ---------------------------------------------------------
    extracted_claims_path = tables_dir / "extracted_claims.parquet"
    claims_checkpoint_path = tables_dir / "extracted_claims_partial.parquet"

    extracted_claims: list[dict[str, Any]] = []
    extracted_doc_ids = set()

    if extracted_claims_path.is_file():
        logger.info(f"Found completed extracted_claims.parquet. Skipping extraction loop.")
        extracted_claims = pq.read_table(extracted_claims_path).to_pylist()
    else:
        if claims_checkpoint_path.is_file():
            extracted_claims = pq.read_table(claims_checkpoint_path).to_pylist()
            extracted_doc_ids = {c["source_id"] for c in extracted_claims}
            logger.info(f"Resuming extraction from checkpoint: {len(extracted_doc_ids)} docs already extracted, {len(extracted_claims)} claims.")

        logger.info(f"Starting LLM Extraction on accepted documents...")
        extract_count = 0
        total_to_extract = len(accepted_b_ids)

        for b_id, b_path in zip(all_b_ids, all_b_blobs):
            if b_id not in accepted_b_ids:
                continue
            if b_id in extracted_doc_ids:
                continue

            full_path = run_dir / b_path
            if not full_path.is_file():
                continue

            text = full_path.read_text(encoding="utf-8")
            valid_claims, dlq_entries = extract_claims(
                text=text,
                source_id=b_id,
                cache_dir=cache_dir,
                ontology=ontology,
                adapter=adapter
            )

            for claim in valid_claims:
                extracted_claims.append({
                    "schema_version": "ticket_a_v1",
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

            extracted_doc_ids.add(b_id)
            extract_count += 1

            if extract_count % checkpoint_interval == 0:
                logger.info(f"Extraction progress: {len(extracted_doc_ids)}/{total_to_extract} accepted docs processed ({len(extracted_claims)} claims).")
                pq.write_table(pa.Table.from_pylist(extracted_claims), claims_checkpoint_path)

        # Write final immutable table
        write_parquet_immutable(extracted_claims_path, "extracted_claims", extracted_claims)
        if claims_checkpoint_path.is_file():
            claims_checkpoint_path.unlink()
        logger.info(f"Extraction stage completed and written to {extracted_claims_path} ({len(extracted_claims)} total claims).")

    # ---------------------------------------------------------
    # STEP 6: ADJUDICATION
    # ---------------------------------------------------------
    logger.info("Starting Adjudication...")
    adjudication_res = run_adjudication(repo_root, run_id)
    logger.info(f"Adjudication completed: {adjudication_res}")

    # ---------------------------------------------------------
    # STEP 7: QUALITY GATE EVALUATION
    # ---------------------------------------------------------
    logger.info("Evaluating Stage 4.14 Quality Gate...")
    qg_res = run_quality_gate(repo_root, run_id)
    logger.info(f"Quality Gate Status: {qg_res.get('status')} | Invariants: {qg_res.get('invariants_passed')}")

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "total_documents": len(filter_decisions),
        "included_documents": len(accepted_b_ids),
        "extracted_claims": len(extracted_claims),
        "adjudication": adjudication_res,
        "quality_gate": qg_res
    }


def main():
    parser = argparse.ArgumentParser(description="Run Stage 4.14 Main Corpus Processing Pipeline.")
    parser.add_argument("--run", default="production_v2", help="Run ID (default: production_v2)")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--llm-mode", default="local", choices=["hosted", "local", "mock"])
    parser.add_argument("--model-name", default="ag/gemini-3.7-flash-low")
    parser.add_argument("--limit", type=int, default=None, help="Optional document limit for testing/dry-run")
    parser.add_argument("--checkpoint-interval", type=int, default=50)

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    res = run_production_pipeline(
        repo_root=repo_root,
        run_id=args.run,
        llm_mode=args.llm_mode,
        model_name=args.model_name,
        limit=args.limit,
        checkpoint_interval=args.checkpoint_interval
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
