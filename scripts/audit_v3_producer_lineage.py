"""Diagnose producer fingerprints and ID rules; never certify reconstructed mappings."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pyarrow.parquet as pq
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_legacy_transe_t01 import encode, sha, write_json  # noqa: E402

PACKAGE=ROOT/"data/KG_lan2/evolving_kg_downstream_v3"


def byte_variants_match(payload: bytes, expected_hash: str) -> dict[str, bool]:
    lf=payload.replace(b"\r\n",b"\n")
    return {"exact_blob":sha(payload)==expected_hash,
            "lf_hypothesis":sha(lf)==expected_hash,
            "crlf_hypothesis":sha(lf.replace(b"\n",b"\r\n"))==expected_hash}


def candidate_id(mention: str) -> str:
    """The historical producer's diagnostic rule, not approved canonical identity."""
    return "ent_"+sha(mention.strip().lower().encode())[:8]


def main() -> None:
    bundle_path=PACKAGE/"inputs/proposed_config_bundle.yaml"
    bundle=yaml.safe_load(bundle_path.read_bytes())
    now=datetime.now(timezone.utc)
    out=ROOT/"outputs/v3_producer_lineage"/(now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid4().hex[:8])
    out.mkdir(parents=True,exist_ok=False)
    commits=subprocess.check_output(["git","rev-list","--all"],cwd=ROOT,text=True).splitlines()
    paths=[r["path"] for r in bundle["candidate_files"]]
    blob_cache={}
    comparisons=[]
    for commit in commits:
        tree=subprocess.check_output(["git","ls-tree","-r",commit,"--",*paths],cwd=ROOT,text=True)
        by_path={}
        for line in tree.splitlines():
            metadata,path=line.split("\t",1)
            _,kind,oid=metadata.split()
            if kind=="blob":
                by_path[path]=oid
        rows=[]
        for item in bundle["candidate_files"]:
            oid=by_path.get(item["path"])
            if oid and oid not in blob_cache:
                blob_cache[oid]=subprocess.check_output(["git","cat-file","blob",oid],cwd=ROOT)
            matches=byte_variants_match(blob_cache[oid],item["sha256"]) if oid else {}
            rows.append({"path":item["path"],"expected_sha256":item["sha256"],"blob_oid":oid,"matches":matches})
        comparisons.append({"commit":commit,"exact_count":sum(r["matches"].get("exact_blob",False) for r in rows),
                            "compatible_count":sum(any(r["matches"].values()) for r in rows),"files":rows})
    facts_path=PACKAGE/"tables/fact_versions.parquet"
    claims_path=PACKAGE/"tables/extracted_claims.parquet"
    input_hashes={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in (facts_path,claims_path,bundle_path)}
    facts=pq.read_table(facts_path).to_pylist()
    claims={r["claim_id"]:r for r in pq.read_table(claims_path).to_pylist()}
    links=[]
    mentions=defaultdict(lambda:{"mentions":set(),"claims":set()})
    for fact in facts:
        cid=fact["fact_version_id"].split("_",1)[1]
        claim=claims.get(cid)
        link={"fact_version_id":fact["fact_version_id"],"claim_id_candidate":cid,"claim_exists":claim is not None}
        if claim:
            link["metadata_match"]=all(fact[k]==claim[k] for k in ("source_id","evidence_span_start","evidence_span_end","evidence_text_hash")) and fact["relation_id"]==claim["relation_name"]
            link["subject_rule_matches"]=candidate_id(claim["subject_mention"])==fact["subject_id"]
            link["object_rule_matches"]=candidate_id(claim["object_mention"])==fact["object_id"]
            logical=sha(f"{fact['subject_id']}|{fact['relation_id']}|{fact['object_id']}".encode())[:16]
            link["logical_fact_rule_matches"]=logical==fact["logical_fact_id"]
            for role in ("subject","object"):
                target=mentions[fact[role+"_id"]]
                target["mentions"].add(claim[role+"_mention"])
                target["claims"].add(cid)
        links.append(link)
    readable=[{"legacy_entity_id":eid,"observed_mentions":sorted(value["mentions"]),"claim_ids":sorted(value["claims"]),
               "status":"DIAGNOSTIC_ONLY_NOT_REGISTERED_CANONICAL_MAPPING","mapping_available_at":None}
              for eid,value in sorted(mentions.items())]
    best=max(r["compatible_count"] for r in comparisons)
    summary={"reachable_commits_examined":len(commits),"candidate_config_files":len(paths),
        "maximum_exact_blob_matches":max(r["exact_count"] for r in comparisons),
        "maximum_diagnostic_compatible_matches":best,
        "best_compatible_commits":[r["commit"] for r in comparisons if r["compatible_count"]==best],
        "producer_commit_verified":False,"reason":"No v3 run/code manifest; CRLF hypotheses are not originals and multiple commits are compatible",
        "fact_rows":len(facts),"id_rule_checks":{k:sum(r.get(k,False) for r in links) for k in
            ("claim_exists","metadata_match","subject_rule_matches","object_rule_matches","logical_fact_rule_matches")},
        "diagnostic_entities":len(readable),"scientific_certification":False}
    write_json(out/"config_comparisons.json",comparisons)
    write_json(out/"fact_claim_rule_diagnostics.json",links)
    write_json(out/"mention_links_DIAGNOSTIC_ONLY.json",readable)
    write_json(out/"summary.json",summary)
    sources={}
    for ref in ("origin/fix/data-pipeline-compliance-cont","origin/feature/remediation-and-parity"):
        for name in ("src/kg_pipeline/claims.py","src/kg_pipeline/adjudicate.py","src/kg_pipeline/adjudication.py"):
            payload=subprocess.check_output(["git","show",f"{ref}:{name}"],cwd=ROOT)
            path=out/"reference_sources"/ref.replace("/","_")/(name.replace("/","_")+".txt")
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("xb") as handle:
                handle.write(payload)
            sources[f"{ref}:{name}"]=sha(payload)
    with (out/"audit_code.py").open("xb") as handle:
        handle.write(Path(__file__).read_bytes())
    if any(sha((ROOT/p).read_bytes())!=h for p,h in input_hashes.items()):
        raise ValueError("Inputs changed")
    manifest={"experiment_id":out.name,"protocol_version":"v1-draft","seed":None,
        "git":{"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
               "dirty_state":bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=normal"],cwd=ROOT).strip())},
        "inputs":{"data_hash":input_hashes[facts_path.relative_to(ROOT).as_posix()],"snapshot_hash":None,"query_hash":None,
                  "entity_map_hash":None,"relation_map_hash":None,"config_hash":sha(encode({"mode":"diagnostic","candidate_files":paths})),
                  "hashes":input_hashes,"reference_code_hashes":sources},
        "environment":{"python":platform.python_version(),"os":platform.platform()},"hardware":{"cpu":platform.processor(),"ram":None},
        "artifacts":{"hashes":{p.relative_to(out).as_posix():sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}},
        "access":{"state":"dev","timestamp":now.isoformat(),"actor_or_runner":"scripts/audit_v3_producer_lineage.py"},
        "scientific_certification":False,"null_fields":"No QA/model snapshot or registered canonical mapping in this audit"}
    write_json(out/"experiment_manifest.json",manifest)
    print(json.dumps({"output":str(out),**summary},indent=2))


if __name__=="__main__":
    main()
