"""S4-S6: cross-fitted alignment, same-snapshot null, drift (signed excess, SED+) and controls on v3.3.

All settings come from configs/s5_drift_v33.yaml (registered before measuring). Dev mode, not certified.
Embeddings are retrained deterministically with the S3 producer SGD (the E=400 prefix equals the S3 checkpoints; checked).
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
from drift.crossfit import crossfit_distances, degree_bucket, entity_scores, stratified_folds  # noqa: E402
from inspect_m2_inputs import encode, provenance, sha, validate_manifest, write_json  # noqa: E402
from s3_backbone import load_package, train_model, trajectory_task, triples_of  # noqa: E402

CONFIG_PATH = ROOT / "configs/s5_drift_v33.yaml"
OUT_ROOT = ROOT / "outputs/s5_drift_v33"
WORKERS = 11
DETECTION_CALL = 2.0   # registered: configs/s5_drift_v33.yaml drift.detection_call "sed_plus >= 2.0"


def clean(value: Any) -> Any:
    """JSON cannot hold NaN/inf: report them as null (= no data), never as a number."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def hkey(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def perturbed_task(task: tuple[Any, ...]) -> dict[str, Any]:
    package, sid, seed, d, lr, margin, epochs, triples, tag = task
    ds = load_package(package)[sid]
    e2i = ds.get_entity_mapping()
    rows = [e2i[e] for e in sorted(e2i)]
    model, _, _, _ = train_model(package, sid, [tuple(t) for t in triples], d, lr, margin, seed, epochs)
    return {"tag": tag, "seed": seed, "emb": np.array(model.entity_embeddings)[rows]}


class Geometry:
    """Embeddings and structure shared by all measurements."""

    def __init__(self, cfg: dict[str, Any], emb: dict[tuple[str, int, int], np.ndarray]):
        self.cfg, self.emb = cfg, emb
        self.package = cfg["package"]
        self.ds = load_package(self.package)
        self.seeds = cfg["backbone"]["seeds"]
        self.ents = {sid: sorted(ds.get_entity_mapping()) for sid, ds in self.ds.items()}
        self.pairs = [tuple(p) for p in cfg["same_snapshot_null"]["pairs"]]
        self.k = cfg["alignment"]["cross_fit_folds"]
        gate = cfg["alignment"]["diagnostics_gate"]
        self.gate = {"max_orthogonality_error": gate["max_orthogonality_error"],
                     "min_rank_fraction": gate["min_rank_fraction"], "max_gap": gate["max_fit_holdout_gap"]}
        self.support, self.eps = cfg["same_snapshot_null"]["support_minimum"], cfg["drift"]["mad_epsilon"]
        self.diagnostics: list[dict[str, Any]] = []

    def prepare(self, a: str, b: str):
        ents = self.ents[a]
        pos_b = {e: i for i, e in enumerate(self.ents[b])}
        idx_b = [pos_b[e] for e in ents]            # persistent entities (append-only)
        deg = Counter([t.subject_id for t in self.ds[a].triples] + [t.object_id for t in self.ds[a].triples])
        buckets = np.array([degree_bucket(deg[e]) for e in ents])
        folds = stratified_folds(ents, list(buckets), f"{a}->{b}", self.k)
        return ents, idx_b, deg, buckets, folds

    def cf(self, x: np.ndarray, y: np.ndarray, folds: np.ndarray, label: str) -> np.ndarray:
        dist, diag = crossfit_distances(x, y, folds, self.k, **self.gate)
        self.diagnostics.append({"label": label, "valid_folds": sum(d["valid"] for d in diag), "folds": self.k,
                                 "reasons": sorted({str(d["reason"]) for d in diag if not d["valid"]}),
                                 "gap_median": float(np.median([d["gap"] for d in diag if "gap" in d])),
                                 "rank_fraction_min": float(min(d["rank_fraction"] for d in diag if "rank_fraction" in d))})
        return dist

    def delta_time(self, a: str, b: str, e_epoch: int, folds, idx_b, b_override: dict[int, np.ndarray] | None = None):
        per_seed = []
        for s in self.seeds:
            later = (b_override[s] if b_override else self.emb[(b, s, e_epoch)])[idx_b]
            per_seed.append(self.cf(self.emb[(a, s, e_epoch)], later, folds, f"time {a}->{b} seed{s} E{e_epoch}"))
        return np.median(np.stack(per_seed), axis=0)

    def null_pairs(self, a: str, b: str, e_epoch: int, folds, idx_b):
        at_a = [self.cf(self.emb[(a, i, e_epoch)], self.emb[(a, j, e_epoch)], folds, f"null {a} pair{i}-{j} E{e_epoch}")
                for i, j in self.pairs]
        at_b = [self.cf(self.emb[(b, i, e_epoch)][idx_b], self.emb[(b, j, e_epoch)][idx_b], folds,
                        f"null {b} pair{i}-{j} E{e_epoch}") for i, j in self.pairs]
        return at_a, at_b


def summarise(df: pd.DataFrame) -> dict[str, Any]:
    avail = df[df.available]
    out = {"entities": len(df), "available": len(avail), "share_signed_excess_pos": float((avail.signed_excess > 0).mean()),
           "share_sed_ge2": float((avail.sed_plus >= DETECTION_CALL).mean()), "median_sed": float(avail.sed_plus.median()),
           "max_sed": float(avail.sed_plus.max()), "by_bucket": {}}
    for b, g in avail.groupby("bucket"):
        out["by_bucket"][int(b)] = {"n": len(g), "share_pos": float((g.signed_excess > 0).mean()),
                                    "share_sed_ge2": float((g.sed_plus >= DETECTION_CALL).mean()), "median_sed": float(g.sed_plus.median())}
    return out


def table_from(ents, deg, buckets, folds, delta, scores, a, b, e_epoch) -> pd.DataFrame:
    return pd.DataFrame({"entity_id": ents, "transition": f"{a}->{b}", "epochs": e_epoch, "pre_degree": [deg[e] for e in ents],
                         "bucket": buckets, "fold": folds, "delta_time": delta, "reference_group": scores["group"],
                         "reference_median": scores["reference_median"], "reference_mad": scores["reference_mad"],
                         "signed_excess": scores["signed_excess"], "sed_plus": scores["sed_plus"],
                         "available": np.isfinite(scores["sed_plus"])})


def main_measure(geo: Geometry, cfg: dict[str, Any], e_epoch: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    ids = list(geo.ds)
    frames, neg_rows = [], []
    for a, b in zip(ids, ids[1:]):
        ents, idx_b, deg, buckets, folds = geo.prepare(a, b)
        delta = geo.delta_time(a, b, e_epoch, folds, idx_b)
        at_a, at_b = geo.null_pairs(a, b, e_epoch, folds, idx_b)
        null = np.median(np.stack(at_a + at_b), axis=0)
        scores = entity_scores(delta, null, buckets, geo.support, geo.eps)
        frames.append(table_from(ents, deg, buckets, folds, delta, scores, a, b, e_epoch))
        # negative control: pseudo drift = pairs at the earlier snapshot, reference = pairs at the later snapshot
        pseudo = np.median(np.stack(at_a), axis=0)
        neg = entity_scores(pseudo, np.median(np.stack(at_b), axis=0), buckets, geo.support, geo.eps)
        neg_rows.append(table_from(ents, deg, buckets, folds, pseudo, neg, a, b, e_epoch))
    df = pd.concat(frames, ignore_index=True)
    neg_df = pd.concat(neg_rows, ignore_index=True)
    return df, {"main": summarise(df), "negative_control": summarise(neg_df),
                "by_transition": {t: summarise(g) for t, g in df.groupby("transition")}}


def inject(geo: Geometry, a: str, b: str, strength: float, fraction: float):
    ents, _, _, buckets, _ = geo.prepare(a, b)
    triples = triples_of(geo.ds[b])
    triple_set = set(triples)
    all_ents = geo.ents[b]
    injected: list[str] = []
    for bucket in sorted(set(buckets)):
        members = sorted((e for e, k in zip(ents, buckets) if k == bucket), key=lambda e: hkey("s5-inject", f"{a}->{b}", e))
        injected += members[:max(1, math.ceil(fraction * len(members)))]
    chosen = set(injected)
    collateral: set[str] = set()
    removed, added = set(), set()
    for e in sorted(chosen):
        incident = sorted((t for t in triples if e in (t[0], t[2])), key=lambda t: hkey("s5-rewire-pick", f"{a}->{b}", t))
        for h, r, t in incident[:math.ceil(strength * len(incident))]:
            other = t if e == h else h
            for cand in sorted(all_ents, key=lambda c: hkey("s5-rewire", f"{a}->{b}", strength, h, r, t, c)):
                new = (e, r, cand) if e == h else (cand, r, e)
                if cand in (e, other) or new in triple_set or new in added:
                    continue
                removed.add((h, r, t))
                added.add(new)
                collateral.update({other, cand})
                break
    perturbed = [t for t in triples if t not in removed] + sorted(added)
    return perturbed, chosen, collateral - chosen


def positive_controls(geo: Geometry, cfg: dict[str, Any], e_epoch: int) -> dict[str, Any]:
    pc, bb = cfg["controls"]["positive"], cfg["backbone"]
    jobs, plans = [], {}
    for a, b in pc["transitions"]:
        for strength in pc["rewire_strengths"]:
            perturbed, chosen, collateral = inject(geo, a, b, strength, pc["injected_fraction"])
            tag = f"{a}->{b}@{strength}"
            plans[tag] = (a, b, strength, chosen, collateral, len(perturbed))
            jobs += [(geo.package, b, s, bb["dimension"], bb["learning_rate"], bb["margin"], e_epoch, perturbed, tag)
                     for s in geo.seeds]
    with ProcessPoolExecutor(WORKERS) as pool:
        results = list(pool.map(perturbed_task, jobs, chunksize=1))
    out: dict[str, Any] = {}
    for tag, (a, b, strength, chosen, collateral, n_triples) in plans.items():
        override = {r["seed"]: r["emb"] for r in results if r["tag"] == tag}
        ents, idx_b, deg, buckets, folds = geo.prepare(a, b)
        delta = geo.delta_time(a, b, e_epoch, folds, idx_b, override)
        at_a, at_b = geo.null_pairs(a, b, e_epoch, folds, idx_b)        # null from the unperturbed models
        scores = entity_scores(delta, np.median(np.stack(at_a + at_b), axis=0), buckets, geo.support, geo.eps)
        df = table_from(ents, deg, buckets, folds, delta, scores, a, b, e_epoch)
        df["injected"] = df.entity_id.isin(chosen)
        df["collateral"] = df.entity_id.isin(collateral)
        av = df[df.available]
        detected = av.sed_plus >= DETECTION_CALL
        inj, clean = av.injected, (~av.injected) & (~av.collateral)
        out[tag] = {"triples_after_rewire": n_triples, "injected": int(inj.sum()),
                    "sensitivity": float(detected[inj].mean()), "false_positive_rate": float(detected[clean].mean()),
                    "median_sed_injected": float(av.sed_plus[inj].median()), "median_sed_clean": float(av.sed_plus[clean].median()),
                    "mean_excess_injected": float(av.signed_excess[inj].mean()), "mean_excess_clean": float(av.signed_excess[clean].mean()),
                    "by_bucket": {int(k): {"injected": int(g.injected.sum()), "sensitivity": float((g.sed_plus[g.injected] >= DETECTION_CALL).mean()),
                                           "false_positive_rate": float((g.sed_plus[(~g.injected) & (~g.collateral)] >= DETECTION_CALL).mean())}
                                  for k, g in av.groupby("bucket") if g.injected.any()}}
    ok = all(v["sensitivity"] >= 0.5 and v["false_positive_rate"] <= 0.10 for t, v in out.items() if t.endswith("@1.0"))
    return {"per_run": out, "detectable_registered_rule": bool(ok)}


def load_embeddings(cfg: dict[str, Any], epochs: list[int]) -> dict[tuple[str, int, int], np.ndarray]:
    bb, package = cfg["backbone"], cfg["package"]
    tasks = [(package, sid, seed, bb["dimension"], bb["learning_rate"], bb["margin"], epochs) for sid in load_package(package)
             for seed in bb["seeds"]]
    with ProcessPoolExecutor(WORKERS) as pool:
        runs = list(pool.map(trajectory_task, tasks, chunksize=1))
    return {(r["sid"], r["seed"], e): m for r in runs for e, m in r["emb"].items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-run", default=None, help="S3 train run dir to cross-check E=400 embeddings against checkpoints")
    ap.add_argument("--skip-controls", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(CONFIG_PATH.read_bytes())
    run = OUT_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    run.mkdir(parents=True)
    print("run dir:", run, flush=True)
    epochs = cfg["backbone"]["sensitivity_epochs"]
    emb = load_embeddings(cfg, epochs)
    geo = Geometry(cfg, emb)
    report: dict[str, Any] = {"scientific_certification": False, "config_sha256": sha(CONFIG_PATH.read_bytes())}
    if args.train_run:
        ck = json.loads((Path(args.train_run) / "train/checkpoints/T05_seed13.json").read_text(encoding="utf-8"))
        rows = np.array([ck["entity_embeddings"][e] for e in geo.ents["T05"]])
        report["checkpoint_crosscheck_T05_seed13_max_abs_diff"] = float(np.abs(rows - emb[("T05", 13, 400)]).max())
    tables = {}
    for e in epochs:
        df, summary = main_measure(geo, cfg, e)
        tables[e] = df
        report[f"E{e}"] = summary
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), run / f"entity_drift_E{e}.parquet", compression="snappy")
        m, n = summary["main"], summary["negative_control"]
        print(f"E={e}: entities {m['entities']} available {m['available']} | drift: share excess>0 {m['share_signed_excess_pos']:.3f}, "
              f"share SED+>=2 {m['share_sed_ge2']:.3f}, median SED+ {m['median_sed']:.3f} | negative control: share>0 "
              f"{n['share_signed_excess_pos']:.3f}, share SED+>=2 {n['share_sed_ge2']:.3f}", flush=True)
        for bucket, v in m["by_bucket"].items():
            print(f"    bucket {bucket}: n={v['n']} share>0={v['share_pos']:.3f} SED>=2={v['share_sed_ge2']:.3f}", flush=True)
    report["alignment_diagnostics"] = {"checks": len(geo.diagnostics),
                                       "invalid": [d for d in geo.diagnostics if d["valid_folds"] < d["folds"]][:50],
                                       "n_invalid_runs": sum(d["valid_folds"] < d["folds"] for d in geo.diagnostics),
                                       "gap_median_overall": float(np.median([d["gap_median"] for d in geo.diagnostics]))}
    if not args.skip_controls:
        for e in epochs:                                  # registered: repeat S4-S6 for every sensitivity E
            report[f"positive_control_E{e}"] = pc = positive_controls(geo, cfg, e)
            for tag, v in pc["per_run"].items():
                print(f"E={e} positive {tag}: sensitivity {v['sensitivity']:.3f} FPR {v['false_positive_rate']:.3f} "
                      f"median SED injected/clean {v['median_sed_injected']:.2f}/{v['median_sed_clean']:.2f}", flush=True)
            print(f"E={e} detectable (registered rule): {pc['detectable_registered_rule']}", flush=True)
    write_json(run / "s5_s6_report.json", clean(report))
    files = {p.name: sha(p.read_bytes()) for p in sorted(run.iterdir())}
    package = ROOT / cfg["package"]
    hashes = {str(CONFIG_PATH.relative_to(ROOT)): sha(CONFIG_PATH.read_bytes()),
              f"{cfg['package']}/snapshot_boundaries.yaml": sha((package / "snapshot_boundaries.yaml").read_bytes()),
              "scripts/s5_drift.py": sha(Path(__file__).read_bytes()), "src/drift/crossfit.py": sha((ROOT / "src/drift/crossfit.py").read_bytes())}
    manifest = {"experiment_id": run.name, "protocol_version": "v1-draft", "mode": "s5_s6_drift_measurement",
                "scientific_certification": False, "git": provenance(), "seed": None,
                "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": hashes[f"{cfg['package']}/snapshot_boundaries.yaml"],
                           "query_hash": None, "entity_map_hash": "entity_map_v2", "relation_map_hash": "unchanged",
                           "config_hash": hashes[str(CONFIG_PATH.relative_to(ROOT))], "hashes": hashes},
                "environment": {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__},
                "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                "artifacts": {"hashes": files},
                "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(), "actor_or_runner": "scripts/s5_drift.py"}}
    validate_manifest(manifest)
    write_json(run / "experiment_manifest.json", manifest)
    print("done:", run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
