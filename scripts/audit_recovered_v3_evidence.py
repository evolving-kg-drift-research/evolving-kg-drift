"""Verify recovered audit-only release payloads against v3, without repairing history."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_legacy_transe_t01 import encode, sha, write_json  # noqa: E402

PACKAGE=ROOT/"data/KG_lan2/evolving_kg_downstream_v3"
RECOVERY=ROOT/"outputs/upstream_recovery_release_20261014"
RESTORED=RECOVERY/"recovered"
PLAN=ROOT/"outputs/v3_content_readiness/20261013T173633Z_fb877e13/sample_plan.json"


def file_hash(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_span(text: str, start: int, end: int, expected: str) -> dict[str, Any]:
    valid=type(start) is int and type(end) is int and 0<=start<end<=len(text)
    return {"offsets_valid":valid,
            "span_hash_match":valid and sha(text[start:end].encode())==expected,
            "whole_body_hash_match":sha(text.encode())==expected}


def main() -> None:
    archive=RECOVERY/"kg-data-pre-gate-a-audit-v1.tar.zst"
    expected="9d72dfce30a63a1048e4e20cc08784a900e3de5d22401f6fe51af96cbedb5184"
    if file_hash(archive)!=expected:
        raise ValueError("Release archive checksum mismatch")
    out=RECOVERY/("review_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    tables={n:pq.read_table(PACKAGE/"tables"/(n+".parquet")).to_pylist() for n in
            ("fact_versions","body_variants","retrievals","document_memberships")}
    plan=json.loads(PLAN.read_bytes())
    if file_hash(PACKAGE/"tables/fact_versions.parquet")!=plan["input_sha256"]:
        raise ValueError("Sample population changed")
    input_hashes={str((PACKAGE/"tables"/(n+".parquet")).relative_to(ROOT)):file_hash(PACKAGE/"tables"/(n+".parquet")) for n in tables}
    text_by_body={}
    body_hashes={}
    for row in tables["body_variants"]:
        path=RESTORED/"runs/llm_rebuild_v2_audit_01"/row["body_blob_relative_path"]
        payload=path.read_bytes()
        body_hashes[path.relative_to(RESTORED).as_posix()]=sha(payload)
        if sha(payload)!=row["body_text_sha256"]:
            raise ValueError("Recovered body differs from v3 bytes")
        text_by_body[row["body_variant_id"]]=payload.decode("utf-8")
    log_cache={}
    strict=[r for r in tables["retrievals"] if r["strict_source_input_eligible"]]
    receipt_rows=[]
    for row in strict:
        name=row["evidence_path"]
        path=RESTORED/name
        if name not in log_cache:
            log_cache[name]=(file_hash(path),path.read_text(encoding="utf-8").splitlines())
        digest,lines=log_cache[name]
        line_number=int(row["evidence_locator"].split(":")[-1])
        receipt=json.loads(lines[line_number-1])
        receipt_rows.append({"retrieval_id":row["retrieval_id"],
            "file_hash_match":digest==row["evidence_file_sha256"],
            "record_hash_match":sha(json.dumps(receipt,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode())==row["evidence_record_sha256"],
            "raw_hash_match":receipt.get("content_hash_sha256")==row["raw_blob_sha256"],
            "retrieved_at_match":receipt.get("retrieved_at_real")==row["retrieved_at_real"],
            "url_match":receipt.get("requested_url")==row["requested_url"] and receipt.get("final_url")==row["final_url"]})
    receipts_summary={k:sum(r[k] for r in receipt_rows) for k in receipt_rows[0] if k!="retrieval_id"}
    sample_ids=set(plan["selected_ids"])
    sampled_sources={r["source_id"] for r in tables["fact_versions"] if r["fact_version_id"] in sample_ids}
    raw_hashes={r["raw_blob_sha256"] for r in tables["document_memberships"] if r["body_variant_id"] in sampled_sources}
    raw_paths={p.stem:p for p in (RESTORED/"data/raw").rglob("*.bin")}
    raw_verified={h:raw_paths[h].relative_to(RESTORED).as_posix() for h in raw_hashes if h in raw_paths and file_hash(raw_paths[h])==h}
    all_checks=[]
    sample=[]
    for row in tables["fact_versions"]:
        text=text_by_body[row["source_id"]]
        check=inspect_span(text,row["evidence_span_start"],row["evidence_span_end"],row["evidence_text_hash"])
        all_checks.append(check)
        if row["fact_version_id"] in sample_ids:
            sample.append({"fact_version_id":row["fact_version_id"],"relation_id":row["relation_id"],**check,
                "evidence_observed_at":row["evidence_observed_at"],
                "source_excerpt":text[row["evidence_span_start"]:row["evidence_span_end"]],
                "mapping":"NOT_VERIFIABLE_REGISTERED_MAPPING_MISSING",
                "temporal_basis":"NOT_VERIFIABLE_ACQUISITION_TIME_IS_NOT_PUBLIC_OBSERVATION_BASIS",
                "semantic_correctness":"NOT_CERTIFIED_NO_CANONICAL_MAPPING_AND_SPAN_BINDING"})
    summary={"release_status":"AUDIT_ONLY, not the v3 producer run", "archive_sha256":expected,
        "body_hashes_verified":len(body_hashes),"strict_retrievals":len(strict),"strict_log_files":len(log_cache),
        "receipt_checks":receipts_summary,"sample_raw_blobs_requested":len(raw_hashes),"sample_raw_blobs_verified":len(raw_verified),
        "all_fact_checks":{k:sum(r[k] for r in all_checks) for k in all_checks[0]},
        "sample_checks":{k:sum(r[k] for r in sample) for k in all_checks[0]},
        "sample_size":len(sample),"mapping_manifest_bytes":(RESTORED/"data/manifests/entity_map_v1.json").stat().st_size,
        "scientific_certification":False,"semantic_quality":"BLOCKED_NOT_VERIFIED"}
    write_json(out/"summary.json",summary)
    write_json(out/"sample_review.json",sample)
    write_json(out/"strict_receipt_checks.json",receipt_rows)
    write_json(out/"recovered_body_hashes.json",body_hashes)
    write_json(out/"sample_raw_verified.json",raw_verified)
    write_json(out/"sample_plan.json",plan)
    if any(file_hash(ROOT/p)!=h for p,h in input_hashes.items()):
        raise ValueError("v3 input changed")
    code=Path(__file__).read_bytes()
    with (out/"audit_code.py").open("xb") as handle:
        handle.write(code)
    manifest={"experiment_id":out.name,"protocol_version":"v1-draft","seed":None,
        "git":{"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),"dirty_state":True},
        "inputs":{"data_hash":expected,"snapshot_hash":None,"query_hash":None,"entity_map_hash":None,"relation_map_hash":None,
                  "config_hash":sha(encode({"sample_plan":plan,"scope":"restored archive audit only"})),
                  "v3_hashes":input_hashes,"code_hash":sha(code)},
        "environment":{"python":platform.python_version(),"os":platform.platform()},"hardware":{"cpu":platform.processor(),"ram":None},
        "artifacts":{"hashes":{p.name:file_hash(p) for p in out.iterdir() if p.is_file()}},
        "access":{"state":"dev","timestamp":datetime.now(timezone.utc).isoformat(),"actor_or_runner":"scripts/audit_recovered_v3_evidence.py"},
        "scientific_certification":False,"null_fields":"No model/query or verified canonical mapping in this audit"}
    write_json(out/"experiment_manifest.json",manifest)
    print(json.dumps({"output":str(out),**summary},indent=2))


if __name__=="__main__":
    main()
