"""Post-evaluation diagnostics from immutable artifacts; no training or tuning."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any
import hashlib

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "outputs/legacy_evaluation/20261013T170623Z_e7a3592e"


def load(name: str) -> Any:
    return json.loads((RUN / name).read_bytes())


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"queries": len(rows), "MRR": mean(1/r["rank"] for r in rows),
            "median_rank": median(r["rank"] for r in rows),
            "Hits@10": mean(r["rank"] <= 10 for r in rows)}


def main() -> None:
    inventory = load("artifact_hashes.json")
    if not all(hashlib.sha256((RUN/k).read_bytes()).hexdigest() == v for k,v in inventory.items()):
        raise ValueError("Evaluation artifacts changed")
    split = load("split.json")
    train = split["train"]
    pairs = {frozenset((h,t)) for h,_,t in train}
    frequency = Counter(e for h,_,t in train for e in (h,t))
    baseline = load("baseline_ranks.json")
    runs = {str(seed): load(f"seed_{seed}_ranks.json") for seed in (13,37,101)}
    report: dict[str, Any] = {"input_run": str(RUN.relative_to(ROOT)),
                             "scientific_certification": False, "groups": {}, "queries": []}
    for label, rows in {"baseline": baseline, **runs}.items():
        groups = {}
        for side in ("head", "tail"):
            groups[side] = summarize([r for r in rows if r["side"] == side])
        for relation in sorted({r["triple"][1] for r in rows}):
            groups[relation] = summarize([r for r in rows if r["triple"][1] == relation])
        for seen in (True, False):
            group = [r for r in rows if (frozenset((r["triple"][0],r["triple"][2])) in pairs) == seen]
            groups["seen_pair" if seen else "unseen_pair"] = summarize(group)
        report["groups"][label] = groups
    for i, base in enumerate(baseline):
        triple, side = base["triple"], base["side"]
        target = triple[0] if side == "head" else triple[2]
        fixed = triple[2] if side == "head" else triple[0]
        ranks = {}
        tops = {}
        for seed, rows in runs.items():
            row = rows[i]
            if row["triple"] != triple or row["side"] != side:
                raise ValueError("Query ordering mismatch")
            scores = sorted(row["candidate_scores"], key=lambda x:(-x[1],x[0]))
            ranks[seed] = row["rank"]
            tops[seed] = {"top3": scores[:3], "top1_is_self_loop": scores[0][0] == fixed,
                          "top_score_tie_count": sum(x[1] == scores[0][1] for x in scores),
                          "target_score_gap": scores[0][1] - row["target_score"]}
        report["queries"].append({"query_index": i, "triple": triple, "side": side,
             "target_training_frequency": frequency[target], "baseline_rank": base["rank"],
             "seen_pair": frozenset((triple[0],triple[2])) in pairs, "ranks": ranks,
             "rank_range": max(ranks.values())-min(ranks.values()), "top_predictions": tops,
             "in_top10_all_seeds": all(r<=10 for r in ranks.values()),
             "outside_top10_all_seeds": all(r>10 for r in ranks.values()),
             "better_than_baseline_all_seeds": all(r<base["rank"] for r in ranks.values())})
    queries = report["queries"]
    report["stability"] = {
        "queries": len(queries),
        "in_top10_all_seeds": sum(q["in_top10_all_seeds"] for q in queries),
        "outside_top10_all_seeds": sum(q["outside_top10_all_seeds"] for q in queries),
        "better_than_baseline_all_seeds": sum(q["better_than_baseline_all_seeds"] for q in queries),
        "median_rank_range": median(q["rank_range"] for q in queries),
        "same_top1_all_seeds": sum(len({v["top3"][0][0] for v in q["top_predictions"].values()})==1 for q in queries),
        "top1_self_loop_by_seed": {s:sum(q["top_predictions"][s]["top1_is_self_loop"] for q in queries) for s in runs},
        "top1_ties_by_seed": {s:sum(q["top_predictions"][s]["top_score_tie_count"]>1 for q in queries) for s in runs},
    }
    report["artifacts_unchanged"] = all(hashlib.sha256((RUN/k).read_bytes()).hexdigest() == v for k,v in inventory.items())
    out = ROOT / "outputs/legacy_error_analysis_20261014"
    out.mkdir(exist_ok=False)
    with (out / "report.json").open("x", encoding="utf-8") as handle:
        json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!="queries"},indent=2))


if __name__ == "__main__":
    main()
