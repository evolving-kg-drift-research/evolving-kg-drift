"""N1 step 2: S7 query panel, S8 RR outcome, S9 two-way FE with restricted wild cluster bootstrap (H1 on stratum S3).

Reads the output of scripts/n1_drift_s3.py. Settings: configs/n1_h1_deg3_v33.yaml (fixed before running). Dev mode.
H2 / Arm A / OOV are not run (see the registration).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from evaluation.n1_panel import (  # noqa: E402
    cap_per_head, eligible_paths, path_answers, path_relations, reciprocal_rank_path, support_entities,
)
from evaluation.qa_questions import format_qa_question  # noqa: E402
from inspect_m2_inputs import encode, provenance, sha, validate_manifest, write_json  # noqa: E402
from s3_backbone import load_package, triples_of  # noqa: E402
from s5_drift import clean  # noqa: E402
from statistics.two_way_fixed_effects import fit_two_way_fe, two_way_demean, wild_cluster_bootstrap  # noqa: E402

N1_CONFIG = ROOT / "configs/n1_h1_deg3_v33.yaml"
WORKERS = 11


def estimate_job(job: dict[str, Any]) -> dict[str, Any]:
    """TWFE (+ optional Frisch-Waugh control) with transition-clustered SE and restricted WCB-t."""
    y, x, q, t = job["y"], job["x"], job["q"], job["t"]
    out: dict[str, Any] = {"label": job["label"], "n_obs": int(len(y))}
    if len(y) < 10 or len(np.unique(t)) < 3:
        return {**out, "status": "TOO_FEW_OBSERVATIONS_OR_CLUSTERS"}
    try:
        if job["control"] is not None:
            y_t, xc = two_way_demean(y, np.column_stack([x, job["control"]]), q, t)
            xt, ct = xc[:, [0]], xc[:, [1]]
            gamma_y = np.linalg.lstsq(ct, y_t, rcond=None)[0]
            gamma_x = np.linalg.lstsq(ct, xt, rcond=None)[0]
            y, x = y_t - ct @ gamma_y, (xt - ct @ gamma_x).ravel()
        fit = fit_two_way_fe(y, x, q, t)
        p = wild_cluster_bootstrap(fit, t, job["draws"], job["seed"])
    except ValueError as exc:
        return {**out, "status": f"DEGENERATE: {exc}"}
    se = fit["se"][0]
    return {**out, "status": "OK", "beta": fit["beta"][0], "se": se, "t": fit["t_stat"][0], "p_wcb": p,
            "n_clusters": fit["n_clusters"], "n_queries": int(len(np.unique(q))), "mde80": 2.8 * se,
            "sd_exposure": float(np.std(job["x"]))}


def informative(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby("query_id").size()
    return df[df.query_id.map(counts) >= 2]


def make_job(label: str, df: pd.DataFrame, xcol: str, cfg: dict[str, Any], control: str | None = None) -> dict[str, Any] | None:
    d = informative(df.dropna(subset=[xcol, "rr"] + ([control] if control else [])))
    if d.empty:
        return None
    return {"label": label, "y": d.rr.to_numpy(float), "x": d[xcol].to_numpy(float),
            "q": pd.factorize(d.query_id)[0], "t": pd.factorize(d.transition)[0],
            "control": d[control].to_numpy(float).reshape(-1, 1) if control else None,
            "draws": cfg["h1"]["bootstrap_draws"], "seed": cfg["h1"]["bootstrap_seed"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drift-run", required=True, help="outputs/n1_h1_v33/<run> produced by n1_drift_s3.py")
    args = ap.parse_args()
    cfg = yaml.safe_load(N1_CONFIG.read_bytes())
    drift_run = Path(args.drift_run)
    drift = json.loads((drift_run / "n1_drift_report.json").read_text(encoding="utf-8"))
    usable = [tuple(k.split("->")) for k, v in drift["usable_transitions"]["usable"].items() if v]
    epochs, seeds, package = cfg["backbone"]["sensitivity_epochs"], cfg["backbone"]["seeds"], cfg["package"]
    ds = load_package(package)
    emb = np.load(drift_run / "embeddings.npz")
    run = drift_run / "h1"
    run.mkdir()
    cap = cfg["queries"]["per_head_cap"]

    # ---- S7 panel ----
    panel_rows: list[dict[str, Any]] = []
    pools: dict[tuple[str, str], dict[int, list[tuple[str, ...]]]] = {}
    for a, b in usable:
        ta = triples_of(ds[a])
        deg = Counter([h for h, _, _ in ta] + [t for _, _, t in ta])
        s3 = {e for e, d_ in deg.items() if d_ >= 3}
        pools[(a, b)] = eligible_paths(ta, s3, cfg["queries"]["hops"])
    mapping = pq.read_table(ROOT / "data/entity_map_v2/entity_map_v2.parquet").to_pandas()
    names = {r.v2_entity_id: r.primary_surface for r in mapping[mapping.v2_entity_id.notna()].sort_values("v1_entity_id").itertuples()}
    for (a, b), by_hop in pools.items():
        tb = triples_of(ds[b])
        degb = Counter([h for h, _, _ in tb] + [t for _, _, t in tb])
        for hop, paths in by_hop.items():
            capped = set(cap_per_head(paths, cap))
            for path in paths:
                qid = hashlib.sha256("|".join(path).encode()).hexdigest()[:12]
                panel_rows.append({"query_id": qid, "path": "|".join(path), "hop": hop, "transition": f"{a}->{b}", "a": a, "b": b,
                                   "capped": path in capped, "head": path[0], "gold": path[-1],
                                   "ctrl": float(np.mean([math.log1p(degb[e]) for e in support_entities(path)]))})
    panel = pd.DataFrame(panel_rows)
    print(f"panel: {len(panel)} (query,transition) rows; capped {int(panel.capped.sum())}; distinct queries {panel.query_id.nunique()} "
          f"(capped {panel[panel.capped].query_id.nunique()}); by hop {panel.groupby('hop').size().to_dict()}", flush=True)
    sample = panel.drop_duplicates("query_id").sample(n=min(35, panel.query_id.nunique()), random_state=20261118)
    questions = []
    for r in sample.itertuples():
        p = tuple(r.path.split("|"))
        try:
            text = format_qa_question(names.get(p[0], p[0]), list(path_relations(p)))
        except Exception as exc:  # template gaps are reported, not hidden
            text = f"TEMPLATE_ERROR: {exc}"
        questions.append({"query_id": r.query_id, "hop": r.hop, "head": names.get(p[0], p[0]), "relations": " > ".join(path_relations(p)),
                          "gold": names.get(p[-1], p[-1]), "bridges": " > ".join(names.get(e, e) for e in p[2:-1:2]), "question_vi": text})
    pd.DataFrame(questions).to_csv(run / "questions_review_sample.csv", index=False, encoding="utf-8-sig")

    # ---- S8 outcome + exposures per E ----
    results: dict[str, Any] = {"panel": {"rows": len(panel), "queries": int(panel.query_id.nunique()),
                                         "by_transition": panel.groupby("transition").size().to_dict(),
                                         "by_hop": {int(k): int(v) for k, v in panel.groupby("hop").size().items()}}}
    jobs: list[dict[str, Any]] = []
    frames: dict[int, pd.DataFrame] = {}
    for e in epochs:
        real = pd.read_parquet(drift_run / f"stratum_drift_E{e}.parquet")
        pseudo = pd.read_parquet(drift_run / f"pseudo_drift_E{e}.parquet")
        sed = {(r.transition, r.entity_id): (r.sed_plus, r.signed_excess) for r in real[real.available].itertuples()}
        sedp = {(r.transition, r.entity_id): r.sed_plus for r in pseudo[pseudo.available].itertuples()}
        rows = []
        for r in panel.itertuples():
            path = tuple(r.path.split("|"))
            supp = support_entities(path)
            ex = [sed.get((r.transition, s)) for s in supp]
            exp = [sedp.get((r.transition, s)) for s in supp]
            tb = triples_of(ds[r.b])
            e2i = {x: i for i, x in enumerate(sorted(ds[r.b].get_entity_mapping()))}
            r2i = {x: i for i, x in enumerate(sorted(ds[r.b].get_relation_mapping()))}
            others = path_answers(tb, path[0], path_relations(path)) - {r.gold}
            rr = [reciprocal_rank_path(emb[f"{r.b}_{s}_{e}_ent"], emb[f"{r.b}_{s}_{e}_rel"], e2i, r2i, path[0], path_relations(path),
                                       r.gold, others) for s in seeds]
            ok = all(v is not None for v in ex)
            okp = all(v is not None for v in exp)
            rows.append({"query_id": r.query_id, "transition": r.transition, "hop": r.hop, "capped": r.capped, "ctrl": r.ctrl,
                         "rr": float(np.median(rr)),
                         "d_sed": float(np.median([v[0] for v in ex])) if ok else np.nan,
                         "d_max": float(np.max([v[0] for v in ex])) if ok else np.nan,
                         "d_excess": float(np.median([v[1] for v in ex])) if ok else np.nan,
                         "d_pseudo": float(np.median(exp)) if okp else np.nan})
        df = pd.DataFrame(rows)
        frames[e] = df
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), run / f"panel_E{e}.parquet", compression="snappy")
        print(f"E={e}: panel rows with complete exposure {int(df.d_sed.notna().sum())}/{len(df)}; share d_sed>0 "
              f"{float((df.d_sed.dropna() > 0).mean()):.3f}; mean RR {df.rr.mean():.3f}", flush=True)
        cp = df[df.capped]
        jobs += [j for j in [
            make_job(f"E{e}|primary", cp, "d_sed", cfg), make_job(f"E{e}|falsification_pseudo", cp, "d_pseudo", cfg),
            make_job(f"E{e}|exposure_signed_excess", cp, "d_excess", cfg), make_job(f"E{e}|exposure_max", cp, "d_max", cfg),
            make_job(f"E{e}|control_log_degree", cp, "d_sed", cfg, "ctrl"), make_job(f"E{e}|uncapped", df, "d_sed", cfg),
            make_job(f"E{e}|hop2", cp[cp.hop == 2], "d_sed", cfg), make_job(f"E{e}|hop3", cp[cp.hop == 3], "d_sed", cfg)] if j]
        for t in sorted(cp.transition.unique()):
            j = make_job(f"E{e}|loto_without_{t}", cp[cp.transition != t], "d_sed", cfg)
            if j:
                jobs.append(j)
    with ProcessPoolExecutor(WORKERS) as pool:
        estimates = {r["label"]: r for r in pool.map(estimate_job, jobs, chunksize=1)}
    results["estimates"] = estimates

    # ---- decision rule ----
    pc = drift["positive_control"]
    large_all = all(pc[f"E{e}"]["testable_large"] for e in epochs)
    prim = {e: estimates.get(f"E{e}|primary", {}) for e in epochs}
    p400 = prim[400]
    informative_obs = int(p400.get("n_obs", 0))
    clusters = int(p400.get("n_clusters", 0))
    testable = bool(large_all and informative_obs >= 100 and clusters >= 5)
    ok = [prim[e] for e in epochs if prim[e].get("status") == "OK"]
    signs = {math.copysign(1, r["beta"]) for r in ok}
    classes = {r["p_wcb"] < 0.05 for r in ok}
    results["decision"] = {"positive_control_testable_large_all_E": large_all, "informative_observations_E400": informative_obs,
                           "clusters_E400": clusters, "H1_status": "TESTABLE" if testable else "NOT_TESTABLE",
                           "e_robust": bool(len(ok) == len(epochs) and len(signs) == 1 and len(classes) == 1)}
    write_json(run / "n1_h1_report.json", clean(results))
    print("\n=== estimates (beta per unit of exposure; RR_B outcome) ===")
    for label, r in sorted(estimates.items()):
        if r["status"] == "OK":
            print(f"{label:38} n={r['n_obs']:4} q={r['n_queries']:3} G={r['n_clusters']} beta={r['beta']:+.4f} se={r['se']:.4f} "
                  f"p_wcb={r['p_wcb']:.3f} MDE80={r['mde80']:.4f}")
        else:
            print(f"{label:38} {r['status']}")
    print("\ndecision:", json.dumps(results["decision"]))
    hashes = {str(N1_CONFIG.relative_to(ROOT)): sha(N1_CONFIG.read_bytes()), "scripts/n1_h1.py": sha(Path(__file__).read_bytes()),
              "src/evaluation/n1_panel.py": sha((ROOT / "src/evaluation/n1_panel.py").read_bytes()),
              "drift_report": sha((drift_run / "n1_drift_report.json").read_bytes())}
    manifest = {"experiment_id": f"n1_h1_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
                "protocol_version": "v1-draft", "mode": "n1_h1_estimation", "scientific_certification": False,
                "git": provenance(), "seed": cfg["h1"]["bootstrap_seed"],
                "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": sha((ROOT / package / "snapshot_boundaries.yaml").read_bytes()),
                           "query_hash": sha(encode(sorted(panel.query_id.unique().tolist()))), "entity_map_hash": "entity_map_v2",
                           "relation_map_hash": "unchanged", "config_hash": hashes[str(N1_CONFIG.relative_to(ROOT))], "hashes": hashes},
                "environment": {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.name: sha(p.read_bytes()) for p in sorted(run.iterdir())}},
                "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(), "actor_or_runner": "scripts/n1_h1.py"}}
    validate_manifest(manifest)
    write_json(run / "experiment_manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
