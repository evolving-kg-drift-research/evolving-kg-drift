"""Export human-readable Vietnamese QA benchmark queries with entity names."""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kg_pipeline.hashing import sha256_text  # noqa: E402

df_claims = pd.read_parquet(ROOT / "data/evolving_kg_downstream_v3_1/tables/extracted_claims.parquet")
mapping = {}
for _, row in df_claims.iterrows():
    s_m = str(row["subject_mention"]).strip()
    o_m = str(row["object_mention"]).strip()
    if s_m and s_m != "None":
        eid = f"ent_{sha256_text(s_m.lower())[:8]}"
        mapping[eid] = s_m
    if o_m and o_m != "None":
        eid = f"ent_{sha256_text(o_m.lower())[:8]}"
        mapping[eid] = o_m

eval_matches = sorted(ROOT.glob("outputs/m4_eval/*/recurring_qa_panel_evaluation.parquet"))
if not eval_matches:
    raise FileNotFoundError("No recurring_qa_panel_evaluation.parquet found in outputs/m4_eval/")
eval_df = pd.read_parquet(eval_matches[-1])
queries = eval_df.drop_duplicates(subset=["query_id"])

benchmark = []
for _, q in queries.iterrows():
    h_id = q["head_entity"]
    g_id = q["gold_entity"]
    h_name = mapping.get(h_id, h_id)
    g_name = mapping.get(g_id, g_id)
    hops = int(q["hops"])

    if hops == 1:
        support_names = [h_name, g_name]
        nl_prompt = f"Thực thể \"{h_name}\" có mối liên kết tri thức trực tiếp với thực thể nào?"
        m_name = None
    else:
        support = q["support_entities"]
        m_id = support[1] if len(support) > 1 else "unknown"
        m_name = mapping.get(m_id, m_id)
        support_names = [h_name, m_name, g_name]
        nl_prompt = f"Bắt đầu từ \"{h_name}\", qua mắt xích trung gian \"{m_name}\", thực thể đích cần suy luận tới là gì?"

    benchmark.append({
        "query_id": q["query_id"],
        "hops": hops,
        "natural_language_question": nl_prompt,
        "head_entity_name": h_name,
        "head_entity_id": h_id,
        "intermediate_entity_name": m_name,
        "gold_answer_name": g_name,
        "gold_answer_id": g_id,
        "support_entities_names": support_names,
    })

out_json = ROOT / "reports/qa_benchmark_147_human_readable.json"
out_csv = ROOT / "reports/qa_benchmark_147_human_readable.csv"

with out_json.open("w", encoding="utf-8") as f:
    json.dump(benchmark, f, ensure_ascii=False, indent=2)

df_bench = pd.DataFrame(benchmark)
df_bench.to_csv(out_csv, index=False, encoding="utf-8-sig")
print(f"Exported {len(benchmark)} benchmark queries to {out_json} and {out_csv}")
