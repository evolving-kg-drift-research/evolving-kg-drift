"""N1 step 1: drift for the degree>=3 stratum (S3) with its own null, pseudo drift, and the stratum positive control.

Settings: configs/n1_h1_deg3_v33.yaml (fixed before running); alignment settings come from configs/s5_drift_v33.yaml.
Writes entity-level tables and the embeddings (entity + relation) used later by the query/H1 stage. Dev mode, not certified.
"""
from __future__ import annotations

import hashlib
import math
import platform
import sys
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
from drift.crossfit import entity_scores  # noqa: E402
from inspect_m2_inputs import encode, provenance, sha, validate_manifest, write_json  # noqa: E402
from s3_backbone import load_package, train_model, triples_of  # noqa: E402
from s5_drift import Geometry, clean, perturbed_task  # noqa: E402

N1_CONFIG = ROOT / "configs/n1_h1_deg3_v33.yaml"
S5_CONFIG = ROOT / "configs/s5_drift_v33.yaml"
OUT_ROOT = ROOT / "outputs/n1_h1_v33"
WORKERS = 11


def hkey(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def embedding_task(task: tuple[Any, ...]) -> dict[str, Any]:
    """Full-snapshot run recording entity rows (sorted ids) and relation rows (sorted ids) at the requested epochs."""
    package, sid, seed, d, lr, margin, epochs = task
    ds = load_package(package)[sid]
    e2i, r2i = ds.get_entity_mapping(), ds.get_relation_mapping()
    erows, rrows = [e2i[e] for e in sorted(e2i)], [r2i[r] for r in sorted(r2i)]
    _, _, probes, _ = train_model(package, sid, triples_of(ds), d, lr, margin, seed, max(epochs), set(epochs),
                                  lambda m: (np.array(m.entity_embeddings)[erows], np.array(m.relation_embeddings)[rrows]))
    return {"sid": sid, "seed": seed, "emb": probes}


def inject_s3(geo: Geometry, a: str, b: str, strength: float, fraction: float, minimum: int):
    """Rewire incident edges of a registered share of S3 entities (rule keys 'n1-*')."""
    ents, _, _, buckets, _ = geo.prepare(a, b)
    s3 = sorted((e for e, k in zip(ents, buckets) if k >= 1), key=lambda e: hkey("n1-inject", f"{a}->{b}", e))
    chosen = set(s3[:max(minimum, math.ceil(fraction * len(s3)))])
    triples = triples_of(geo.ds[b])
    triple_set, all_ents = set(triples), geo.ents[b]
    removed: set[tuple[str, str, str]] = set()
    added: set[tuple[str, str, str]] = set()
    collateral: set[str] = set()
    for e in sorted(chosen):
        incident = sorted((t for t in triples if e in (t[0], t[2])), key=lambda t: hkey("n1-rewire-pick", f"{a}->{b}", t))
        for h, r, t in incident[:math.ceil(strength * len(incident))]:
            other = t if e == h else h
            for cand in sorted(all_ents, key=lambda c: hkey("n1-rewire", f"{a}->{b}", strength, h, r, t, c)):
                new = (e, r, cand) if e == h else (cand, r, e)
                if cand in (e, other) or new in triple_set or new in added:
                    continue
                removed.add((h, r, t))
                added.add(new)
                collateral.update({other, cand})
                break
    return [t for t in triples if t not in removed] + sorted(added), chosen, collateral - chosen


def stratum_scores(geo: Geometry, delta: np.ndarray, null: np.ndarray, buckets: np.ndarray, support: int, eps: float):
    mask = buckets >= 1
    sub = entity_scores(delta[mask], null[mask], np.zeros(int(mask.sum()), dtype=int), support, eps)
    return mask, sub


def frame(ents, deg, buckets, mask, delta, null, sub, a, b, e_epoch, usable) -> pd.DataFrame:
    idx = np.where(mask)[0]
    return pd.DataFrame({
        "entity_id": [ents[i] for i in idx], "transition": f"{a}->{b}", "epochs": e_epoch,
        "pre_degree": [deg[ents[i]] for i in idx], "bucket": buckets[idx], "delta_time": delta[idx], "null_value": null[idx],
        "reference_median": sub["reference_median"], "reference_mad": sub["reference_mad"],
        "signed_excess": sub["signed_excess"], "sed_plus": sub["sed_plus"],
        "available": np.isfinite(sub["sed_plus"]) & usable})


def main() -> int:
    n1 = yaml.safe_load(N1_CONFIG.read_bytes())
    s5 = yaml.safe_load(S5_CONFIG.read_bytes())
    st, pc, bb = n1["stratum"], n1["positive_control"], n1["backbone"]
    epochs, support, eps, call = bb["sensitivity_epochs"], st["support_minimum"], st["mad_epsilon"], st["detection_threshold"]
    run = OUT_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    run.mkdir(parents=True)
    print("run dir:", run, flush=True)

    package = n1["package"]
    ids = list(load_package(package))
    tasks = [(package, sid, seed, bb["dimension"], bb["learning_rate"], bb["margin"], epochs) for sid in ids for seed in bb["seeds"]]
    with ProcessPoolExecutor(WORKERS) as pool:
        runs = list(pool.map(embedding_task, tasks, chunksize=1))
    ent_emb = {(r["sid"], r["seed"], e): v[0] for r in runs for e, v in r["emb"].items()}
    np.savez_compressed(run / "embeddings.npz", **{f"{r['sid']}_{r['seed']}_{e}_{kind}": v[i]
                                                   for r in runs for e, v in r["emb"].items()
                                                   for i, kind in enumerate(("ent", "rel"))})
    geo = Geometry({**s5, "package": package}, ent_emb)
    geo.support, geo.eps = support, eps

    report: dict[str, Any] = {"scientific_certification": False, "n1_config_sha256": sha(N1_CONFIG.read_bytes()),
                              "usable_transitions": {}, "positive_control": {}}
    transitions = list(zip(ids, ids[1:]))
    prepared = {t: geo.prepare(*t) for t in transitions}
    s3_counts = {f"{a}->{b}": int((prepared[(a, b)][3] >= 1).sum()) for a, b in transitions}
    usable = {t: s3_counts[f"{t[0]}->{t[1]}"] >= support + 1 for t in transitions}
    report["usable_transitions"] = {"s3_entities": s3_counts, "usable": {f"{a}->{b}": u for (a, b), u in usable.items()}}
    print("S3 entities per transition:", s3_counts, "| usable:", [f"{a}->{b}" for (a, b), u in usable.items() if u], flush=True)

    nulls: dict[tuple[int, tuple[str, str]], np.ndarray] = {}
    for e_epoch in epochs:
        real, pseudo = [], []
        for a, b in transitions:
            ents, idx_b, deg, buckets, folds = prepared[(a, b)]
            delta = geo.delta_time(a, b, e_epoch, folds, idx_b)
            at_a, at_b = geo.null_pairs(a, b, e_epoch, folds, idx_b)
            null = np.median(np.stack(at_a + at_b), axis=0)
            nulls[(e_epoch, (a, b))] = null
            mask, sub = stratum_scores(geo, delta, null, buckets, support, eps)
            real.append(frame(ents, deg, buckets, mask, delta, null, sub, a, b, e_epoch, usable[(a, b)]))
            p_delta, p_null = np.median(np.stack(at_a), axis=0), np.median(np.stack(at_b), axis=0)
            mask, sub = stratum_scores(geo, p_delta, p_null, buckets, support, eps)
            pseudo.append(frame(ents, deg, buckets, mask, p_delta, p_null, sub, a, b, e_epoch, usable[(a, b)]))
        for name, frames in (("stratum_drift", real), ("pseudo_drift", pseudo)):
            df = pd.concat(frames, ignore_index=True)
            pq.write_table(pa.Table.from_pandas(df, preserve_index=False), run / f"{name}_E{e_epoch}.parquet", compression="snappy")
            av = df[df.available]
            print(f"E={e_epoch} {name}: available {len(av)}/{len(df)} share excess>0 {(av.signed_excess > 0).mean():.3f} "
                  f"share SED+>=2 {(av.sed_plus >= call).mean():.3f}", flush=True)
            report[f"E{e_epoch}_{name}"] = {"n": len(df), "available": len(av),
                                            "share_excess_pos": float((av.signed_excess > 0).mean()),
                                            "share_sed_ge2": float((av.sed_plus >= call).mean())}

    # stratum positive control, every usable transition x strength x seed, for every E
    for e_epoch in epochs:
        jobs, plans = [], {}
        for (a, b), ok in usable.items():
            if not ok:
                continue
            for strength in pc["rewire_strengths"]:
                perturbed, chosen, collateral = inject_s3(geo, a, b, strength, pc["injected_fraction"], pc["injected_minimum"])
                tag = f"{a}->{b}@{strength}"
                plans[tag] = (a, b, strength, chosen, collateral)
                jobs += [(package, b, s, bb["dimension"], bb["learning_rate"], bb["margin"], e_epoch, perturbed, tag)
                         for s in bb["seeds"]]
        with ProcessPoolExecutor(WORKERS) as pool:
            results = list(pool.map(perturbed_task, jobs, chunksize=1))
        pooled: dict[float, dict[str, int]] = {}
        per_run = {}
        for tag, (a, b, strength, chosen, collateral) in plans.items():
            override = {r["seed"]: r["emb"] for r in results if r["tag"] == tag}
            ents, idx_b, deg, buckets, folds = prepared[(a, b)]
            delta = geo.delta_time(a, b, e_epoch, folds, idx_b, override)
            mask, sub = stratum_scores(geo, delta, nulls[(e_epoch, (a, b))], buckets, support, eps)
            names = [ents[i] for i in np.where(mask)[0]]
            sed = sub["sed_plus"]
            avail = np.isfinite(sed)
            inj = np.array([n in chosen for n in names])
            clean_mask = np.array([(n not in chosen) and (n not in collateral) for n in names])
            det = sed >= call
            n_inj, n_clean = int((inj & avail).sum()), int((clean_mask & avail).sum())
            per_run[tag] = {"injected": n_inj, "detected": int((det & inj & avail).sum()), "clean": n_clean,
                            "false_positive": int((det & clean_mask & avail).sum())}
            acc = pooled.setdefault(strength, {"injected": 0, "detected": 0, "clean": 0, "false_positive": 0})
            for k, v in per_run[tag].items():
                acc[k] += v
        summary = {str(s): {**c, "sensitivity": c["detected"] / max(1, c["injected"]),
                            "false_positive_rate": c["false_positive"] / max(1, c["clean"])} for s, c in pooled.items()}
        large = summary["1.0"]["sensitivity"] >= 0.80 and summary["1.0"]["false_positive_rate"] <= 0.10
        moderate = summary["0.5"]["sensitivity"] >= 0.50 and summary["0.5"]["false_positive_rate"] <= 0.10
        detectable = next((float(s) for s in sorted(summary, key=float) if summary[s]["sensitivity"] >= 0.50), None)
        report["positive_control"][f"E{e_epoch}"] = {"pooled": summary, "per_run": per_run, "testable_large": bool(large),
                                                    "testable_moderate": bool(moderate), "detectable_strength": detectable}
        print(f"E={e_epoch} positive control: " + "; ".join(
            f"strength {s}: sens {v['sensitivity']:.2f} (n={v['injected']}) FPR {v['false_positive_rate']:.3f}" for s, v in summary.items())
              + f" | testable_large={large} testable_moderate={moderate} detectable_strength={detectable}", flush=True)

    report["alignment_diagnostics"] = {"checks": len(geo.diagnostics),
                                       "n_invalid_runs": sum(d["valid_folds"] < d["folds"] for d in geo.diagnostics)}
    write_json(run / "n1_drift_report.json", clean(report))
    hashes = {str(N1_CONFIG.relative_to(ROOT)): sha(N1_CONFIG.read_bytes()), str(S5_CONFIG.relative_to(ROOT)): sha(S5_CONFIG.read_bytes()),
              "scripts/n1_drift_s3.py": sha(Path(__file__).read_bytes()), "src/drift/crossfit.py": sha((ROOT / "src/drift/crossfit.py").read_bytes())}
    manifest = {"experiment_id": run.name, "protocol_version": "v1-draft", "mode": "n1_stratum_drift",
                "scientific_certification": False, "git": provenance(), "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": sha((ROOT / package / "snapshot_boundaries.yaml").read_bytes()),
                           "query_hash": None, "entity_map_hash": "entity_map_v2", "relation_map_hash": "unchanged",
                           "config_hash": hashes[str(N1_CONFIG.relative_to(ROOT))], "hashes": hashes},
                "environment": {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": {p.name: sha(p.read_bytes()) for p in sorted(run.iterdir())}},
                "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(), "actor_or_runner": "scripts/n1_drift_s3.py"}}
    validate_manifest(manifest)
    write_json(run / "experiment_manifest.json", manifest)
    print("done:", run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
