"""Outcome-blind descriptive evidence review, never a G2 evaluator or mapping producer."""
from __future__ import annotations

import json
import os
import sys
import platform
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/"data/KG_lan2/evolving_kg_downstream_v3"
KNOWN_ROOTS = [ROOT, Path("C:/Users/ducan/orca/workspaces/evolving-kg-drift/main")]
sys.path.insert(0,str(ROOT))
from scripts.run_legacy_transe_t01 import encode, sha, write_json  # noqa: E402


def select_diagnostic_sample(rows: list[dict[str, Any]]) -> list[str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        groups[row["relation_id"]].append(row["fact_version_id"])
    if sum(map(len,groups.values())) != len({r["fact_version_id"] for r in rows}):
        raise ValueError("Duplicate fact IDs")
    return [fid for relation in sorted(groups) for fid in sorted(groups[relation],key=lambda fid:
        sha(encode(["v3-content-readiness-diagnostic-v1",relation,fid])))[:3]]


def safe_candidates(value: str | None, bases: list[Path]) -> list[Path]:
    if not value:
        return []
    token = PurePosixPath(value.replace("\\","/"))
    if token.is_absolute() or ".." in token.parts or "locked_test" in token.parts or ":" in value:
        raise ValueError("Unsafe or held-out evidence path")
    candidates=[]
    for base in bases:
        path = base.joinpath(*token.parts)
        if path.resolve() != path or not path.is_file():
            continue
        candidates.append(path)
    return candidates


def inventory() -> dict[str, Any]:
    skip = {"locked_test","outputs","tests","node_modules","venv","ENV","backups","__pycache__"}
    inventories=[]
    for root in KNOWN_ROOTS:
        files=[]
        candidates=[]
        for base, dirs, names in os.walk(root,followlinks=False):
            directory=Path(base)
            dirs[:]=sorted(d for d in dirs if not d.startswith(".") and d not in skip
                and not d.startswith("tmp-") and not (directory/d).is_symlink()
                and (directory/d).resolve()==directory/d)
            for name in sorted(names):
                path=directory/name
                if path.is_symlink() or path.resolve()!=path:
                    continue
                relative=path.relative_to(root).as_posix()
                files.append(relative)
                if relative.startswith(("src/","scripts/","config/","configs/","docs/","plan_context/")):
                    continue
                if any(t in relative.lower() for t in ("entity_map","entity_mention","mapping","body_blob","body_text","acquisition_log")):
                    candidates.append(relative)
        inventories.append({"root":str(root),"file_count":len(files),"indexed_paths":files,
                            "candidate_artifacts":candidates})
    return {"roots":inventories,"excluded":sorted(skip),"also_excluded":"hidden entries, temp fixture dirs, symlinks/reparse paths",
            "coverage":"known repository roots only, not entire drives"}


def read_verified(name: str) -> list[dict[str, Any]]:
    path=PACKAGE/"tables"/(name+".parquet")
    metadata=json.loads(path.with_suffix(".parquet.manifest.json").read_bytes())
    payload=path.read_bytes()
    if sha(payload)!=metadata["physical_sha256_computed_at_real"]:
        raise ValueError("Parquet sidecar mismatch")
    rows=pq.read_table(path).to_pylist()
    semantic=json.dumps({"table_name":metadata["table_name"],"contract_version":metadata["contract_version"],"rows":rows},
                        ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    if sha(semantic)!=metadata["semantic_sha256"] or len(rows)!=metadata["row_count"]:
        raise ValueError("Semantic hash or count mismatch")
    return rows


def main() -> None:
    now=datetime.now(timezone.utc)
    out=ROOT/"outputs/v3_content_readiness"/(now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    # Before loading content, save a deterministic descriptive sample plan.
    fact_path=PACKAGE/"tables/fact_versions.parquet"
    identity=pq.read_table(fact_path,columns=["fact_version_id","relation_id"]).to_pylist()
    sample_ids=select_diagnostic_sample(identity)
    plan={"version":"v3-content-readiness-diagnostic-v1","created_at_real":now.isoformat(),
          "purpose":"evidence availability and traceability; not gold or estimated fact accuracy",
          "selection":"first 3 fact IDs per relation sorted by SHA256 of fixed salt+relation+fact ID",
          "population":"all v3 FactVersion rows, not TransE held-out or error cases",
          "population_count":len(identity),"input_sha256":sha(fact_path.read_bytes()),"selected_ids":sample_ids,
          "scientific_certification":False,"sampling_policy_status":"diagnostic only; no scientific population amendment"}
    write_json(out/"sample_plan.json",plan)
    write_json(out/"sample_plan_sha256.json",{"sha256":sha(encode(plan))})
    files={p.relative_to(PACKAGE).as_posix():sha(p.read_bytes()) for p in (PACKAGE/"tables").glob("*.parquet")}
    scan=inventory()
    write_json(out/"inventory.json",scan)
    facts=read_verified("fact_versions")
    claims=read_verified("extracted_claims")
    bodies={r["body_variant_id"]:r for r in read_verified("body_variants")}
    memberships=read_verified("document_memberships")
    retrievals={r["retrieval_id"]:r for r in read_verified("retrievals")}
    by_fact={r["fact_version_id"]:r for r in facts}
    claim_index: dict[tuple, list[dict[str,Any]]] = defaultdict(list)
    for c in claims:
        claim_index[(c["source_id"],c["evidence_span_start"],c["evidence_span_end"],c["evidence_text_hash"],c["relation_name"])].append(c)
    member_index: dict[str, list[dict[str,Any]]] = defaultdict(list)
    for m in memberships:
        if m["body_variant_id"]:
            member_index[m["body_variant_id"]].append(m)
    reviews=[]
    for fid in sample_ids:
        fact=by_fact[fid]
        key=(fact["source_id"],fact["evidence_span_start"],fact["evidence_span_end"],fact["evidence_text_hash"],fact["relation_id"])
        candidates=claim_index.get(key,[])
        body=bodies.get(fact["source_id"])
        paths=safe_candidates(body["body_blob_relative_path"],[PACKAGE,*KNOWN_ROOTS]) if body else []
        candidates_retrievals=[retrievals[rid] for m in member_index.get(fact["source_id"],[])
                              for rid in json.loads(m["retrieval_ids_json"]) if rid in retrievals]
        evidence_paths={r["evidence_path"] for r in candidates_retrievals if r.get("evidence_path")}
        available=[str(p) for value in sorted(evidence_paths) for p in safe_candidates(value,[PACKAGE,*KNOWN_ROOTS])]
        span_status="NOT_VERIFIABLE_BODY_MISSING"
        if paths and body:
            text=paths[0].read_text(encoding="utf-8")
            if sha(text.encode())!=body["body_text_sha256"]:
                span_status="BODY_HASH_MISMATCH"
            else:
                start,end=fact["evidence_span_start"],fact["evidence_span_end"]
                span_status="SPAN_HASH_MATCH" if 0<=start<end<=len(text) and sha(text[start:end].encode())==fact["evidence_text_hash"] else "SPAN_HASH_MISMATCH"
        reviews.append({"fact_version_id":fid,"relation_id":fact["relation_id"],
            "subject_id":fact["subject_id"],"object_id":fact["object_id"],
            "mention_candidates":[{"claim_id":c["claim_id"],"subject_mention":c["subject_mention"],"object_mention":c["object_mention"]} for c in candidates],
            "exact_claim_candidates":len(candidates),"body_metadata_present":body is not None,
            "span_status":span_status,"mapping_status":"NOT_VERIFIABLE_NO_REGISTERED_MAPPING_ARTIFACT",
            "candidate_retrieval_records":len(candidates_retrievals),"declared_evidence_paths":len(evidence_paths),
            "available_evidence_paths":available,"evidence_time_status":"NOT_VERIFIABLE_BASIS_MISSING",
            "fact_correctness_status":"NOT_ASSESSED_NO_SOURCE_CONTENT",
            "notes":"Mention text is a traceability candidate, never a canonical mapping or gold label"})
    # Review all rows for exact join coverage; never judge correctness from joins alone.
    join_counts=Counter(len(claim_index.get((f["source_id"],f["evidence_span_start"],f["evidence_span_end"],f["evidence_text_hash"],f["relation_id"]),[])) for f in facts)
    summary={"plan_saved_before_content_review":True,"sample_size":len(reviews),"sample_relations":dict(Counter(r["relation_id"] for r in reviews)),
             "sample_claim_join_counts":dict(Counter(r["exact_claim_candidates"] for r in reviews)),
             "all_fact_claim_join_counts":dict(join_counts),"sample_span_status":dict(Counter(r["span_status"] for r in reviews)),
             "sample_available_evidence_paths":sum(len(r["available_evidence_paths"]) for r in reviews),
             "semantic_quality_status":"BLOCKED_NOT_VERIFIED","scientific_certification":False,
             "package_tables_unchanged":all(sha((PACKAGE/p).read_bytes())==h for p,h in files.items())}
    if not summary["package_tables_unchanged"]:
        raise ValueError("Input changed")
    write_json(out/"sample_reviews.json",reviews)
    write_json(out/"summary.json",summary)
    write_json(out/"input_hashes.json",files)
    code={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in
          [Path(__file__),ROOT/"scripts/run_legacy_transe_t01.py"]}
    for p in [Path(__file__),ROOT/"scripts/run_legacy_transe_t01.py"]:
        target=out/"code"/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as handle:
            handle.write(p.read_bytes())
    manifest={"experiment_id":out.name,"protocol_version":"v1-draft","seed":None,
        "git":{"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
               "dirty_state":bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=normal"],cwd=ROOT).strip())},
        "inputs":{"data_hash":plan["input_sha256"],"snapshot_hash":None,"query_hash":None,
                  "entity_map_hash":None,"relation_map_hash":None,"config_hash":sha(encode(plan)),
                  "hashes":files,"code_hashes":code},
        "environment":{"python":platform.python_version(),"os":platform.platform()},
        "hardware":{"cpu":platform.processor(),"ram":None},
        "artifacts":{"hashes":{p.name:sha(p.read_bytes()) for p in out.iterdir() if p.is_file()}},
        "access":{"state":"dev","timestamp":now.isoformat(),"actor_or_runner":"scripts/audit_v3_content_readiness.py"},
        "scientific_certification":False,"not_applicable_fields":"No model snapshot/query or certified mapping; corresponding hashes are null"}
    write_json(out/"experiment_manifest.json",manifest)
    write_json(out/"artifact_hashes.json",{p.relative_to(out).as_posix():sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()})
    print(json.dumps({"output":str(out),"summary":summary,"scan_candidates":[r["candidate_artifacts"] for r in scan["roots"]]},indent=2))


if __name__=="__main__":
    main()
