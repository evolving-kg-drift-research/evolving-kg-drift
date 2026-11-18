"""S3: validated TransE-L2 backbone on the v3.3 candidate package.

Stage ``search``: hyper-parameter grid on dev snapshots (held-out folds, filtered MRR), then the common
epoch count E from convergence + validation-MRR evidence.  Stage ``train``: 10 snapshots x 3 seeds with
fixed settings, then convergence / quality / stability / determinism gates.

All values come from configs/s3_backbone_v33.yaml (fixed before running).  Selection uses only link-prediction
quality and seed stability, never drift, QA outcomes or H1 (INV-06).  Dev mode: no scientific certification.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_m2_inputs import encode, provenance, sha, validate_manifest, write_json  # noqa: E402
from kge.checkpoint import CheckpointProvenance, KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.minibatch import MiniBatchTransE  # noqa: E402
from kge.model import TransEConfig, TransEModel  # noqa: E402
from kge.validation import (  # noqa: E402
    bootstrap_ci, filtered_reciprocal_ranks, frequency_baseline_reciprocal_ranks, make_folds,
    noise_aware_converged, procrustes_holdout_distance, random_baseline_mrr, stability_plateau,
)

CONFIG_PATH = ROOT / "configs/s3_backbone_v33.yaml"
OUT_ROOT = ROOT / "outputs/s3_backbone_v33"
WORKERS = 11


@lru_cache(maxsize=None)
def load_package(package: str) -> dict[str, SnapshotDataset]:
    base = ROOT / package
    cfg = yaml.safe_load((base / "config/downstream_transe_config.yaml").read_bytes())
    out = {}
    for spec in cfg["snapshots"]:
        rows = pq.read_table(base / spec["parquet_path"]).to_pylist()
        out[spec["snapshot_id"]] = SnapshotDataset.create(
            spec["snapshot_id"], sorted((r["subject_id"], r["relation_id"], r["object_id"]) for r in rows))
    return out


def triples_of(ds: SnapshotDataset) -> list[tuple[str, str, str]]:
    return sorted((t.subject_id, t.relation_id, t.object_id) for t in ds.triples)


@lru_cache(maxsize=None)
def folds_of(package: str, sid: str, k: int, salt: str):
    return make_folds(triples_of(load_package(package)[sid]), k, sid, salt)


def train_model(package: str, sid: str, train: list[tuple[str, str, str]], d: int, lr: float, margin: float,
                seed: int, epochs: int, probe_epochs: set[int] | None = None, probe=None, neg: str | None = None):
    """neg is None -> producer per-triple SGD (TransEModel); 'uniform'/'bernoulli' -> C3 mini-batch Adam."""
    ds = load_package(package)[sid]
    e2i, r2i = ds.get_entity_mapping(), ds.get_relation_mapping()
    idx = [(e2i[h], r2i[r], e2i[t]) for h, r, t in train]
    rng, pos = random.Random(seed), set(idx)
    if neg is None:
        model = TransEModel(e2i, r2i, TransEConfig(dimension=d, norm=2, margin=margin, learning_rate=lr, epochs=epochs,
                                                   batch_size=1, seed=seed, normalize_entities=True))
        step = lambda: model.train_epoch(idx, rng, positive_triples_set=pos)  # noqa: E731
    else:
        model = MiniBatchTransE(e2i, r2i, dimension=d, margin=margin, learning_rate=lr, seed=seed, negative_sampling=neg)
        arr = np.asarray(idx, dtype=np.int64)
        step = lambda: model.fit_epoch(arr, pos)  # noqa: E731
    losses, probes = [], {}
    for ep in range(1, epochs + 1):
        losses.append(step())
        if probe_epochs and ep in probe_epochs:
            probes[ep] = probe(model)
    return model, losses, probes, idx


def embeddings(model: TransEModel) -> tuple[np.ndarray, np.ndarray]:
    return np.array(model.entity_embeddings), np.array(model.relation_embeddings)


def diagnostics(model: TransEModel, idx: list[tuple[int, int, int]], margin: float, seed: int) -> dict[str, float]:
    """Violation rate with one random negative per training triple, and vector norms (extra to the loss)."""
    ent, rel = embeddings(model)
    rng, n = np.random.default_rng(seed), ent.shape[0]
    pos = set(idx)
    violated = 0
    for h, r, t in idx:
        c = int(rng.integers(n))
        if (c, r, t) in pos if rng.random() < 0.5 else (h, r, c) in pos:
            continue
        head, tail = (c, t) if rng.random() < 0.5 else (h, c)
        violated += (margin + np.linalg.norm(ent[h] + rel[r] - ent[t]) - np.linalg.norm(ent[head] + rel[r] - ent[tail])) > 0
    return {"violation_rate": float(violated / len(idx)), "entity_norm_mean": float(np.linalg.norm(ent, axis=1).mean()),
            "relation_norm_mean": float(np.linalg.norm(rel, axis=1).mean())}


# ------------------------------------------------------------------ search stage
def search_task(task: tuple[Any, ...]) -> dict[str, Any]:
    package, sid, fold, seed, d, lr, margin, eval_epochs, salt, k, *rest = task
    neg = rest[0] if rest else None
    triples = triples_of(load_package(package)[sid])
    val = folds_of(package, sid, k, salt)[fold]
    held = set(val)
    train = [t for t in triples if t not in held]
    ds = load_package(package)[sid]
    e2i, r2i = ds.get_entity_mapping(), ds.get_relation_mapping()

    def probe(model: TransEModel) -> list[float]:
        ent, rel = embeddings(model)
        return filtered_reciprocal_ranks(ent, rel, e2i, r2i, val, triples).tolist()

    _, losses, probes, _ = train_model(package, sid, train, d, lr, margin, seed, max(eval_epochs), set(eval_epochs), probe, neg)
    return {"sid": sid, "fold": fold, "seed": seed, "d": d, "lr": lr, "margin": margin, "neg": neg,
            "rr": {str(e): v for e, v in probes.items()}, "loss_at": {str(e): losses[e - 1] for e in eval_epochs}}


def convergence_task(task: tuple[Any, ...]) -> dict[str, Any]:
    package, sid, seed, d, lr, margin, emax = task
    triples = triples_of(load_package(package)[sid])
    _, losses, _, _ = train_model(package, sid, triples, d, lr, margin, seed, emax)
    return {"sid": sid, "seed": seed, "losses": losses}


def trajectory_task(task: tuple[Any, ...]) -> dict[str, Any]:
    """Full-snapshot run recording the loss of every epoch and entity matrices (sorted-id rows) at ``epochs``."""
    package, sid, seed, d, lr, margin, epochs, *rest = task
    neg = rest[0] if rest else None
    ds = load_package(package)[sid]
    e2i = ds.get_entity_mapping()
    rows = [e2i[e] for e in sorted(e2i)]
    _, losses, probes, _ = train_model(package, sid, triples_of(ds), d, lr, margin, seed, max(epochs), set(epochs),
                                       lambda model: np.array(model.entity_embeddings)[rows], neg)
    config = [d, lr, margin] if neg is None else [d, lr, margin, neg]
    return {"sid": sid, "seed": seed, "config": config, "losses": losses, "emb": probes}


def anchor_split(sid: str, ents: list[str]) -> tuple[list[int], list[int]]:
    key = [int(sha(f"s3-anchor|{sid}|{e}".encode())[:8], 16) % 100 for e in ents]
    return [i for i, k in enumerate(key) if k < 60], [i for i, k in enumerate(key) if k >= 60]


def median_noise(mats: dict[int, np.ndarray], fit: list[int], hold: list[int]) -> float:
    pairs = [(a, b) for i, a in enumerate(sorted(mats)) for b in sorted(mats)[i + 1:]]
    return float(np.nanmedian(np.concatenate([procrustes_holdout_distance(mats[a], mats[b], fit, hold) for a, b in pairs])))


def best_configs(search_dir: Path) -> tuple[dict[tuple[int, float, float], dict[int, float]], list[tuple[int, float, float]]]:
    rows = json.loads((search_dir / "search_scores.json").read_text(encoding="utf-8"))["rows"]
    by_config: dict[tuple[int, float, float], dict[int, float]] = {}
    for r in rows:
        by_config.setdefault((r["dimension"], r["learning_rate"], r["margin"]), {})[r["epoch"]] = r["score"]
    top = max(max(v.values()) for v in by_config.values())
    tied = sorted(k for k, v in by_config.items() if max(v.values()) >= top - 0.005)
    return by_config, tied


def run_contingency(cfg: dict[str, Any], search_dir: Path, step: str) -> int:
    c, package, gate = cfg["contingency_c"], cfg["package"], cfg["gates"]["convergence"]
    by_config, tied = best_configs(search_dir)
    run_dir = OUT_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    stage = run_dir / f"contingency_{step}"
    stage.mkdir(parents=True)
    print("run dir:", run_dir, flush=True)
    if step == "c1":
        record = list(cfg["search"]["eval_epochs"])
    else:
        record = sorted(set(c["c2"]["candidate_epochs"]) | set(c["c2"]["lookahead_epochs"]))
    snaps = cfg["epochs"]["convergence_snapshots"]
    tasks = [(package, sid, seed, d, lr, m, record) for (d, lr, m) in tied for sid in snaps for seed in cfg["seeds"]]
    print(f"{step}: tied configs {tied}; {len(tasks)} trajectory runs, epochs {record}", flush=True)
    with ProcessPoolExecutor(WORKERS) as pool:
        traj = list(pool.map(trajectory_task, tasks, chunksize=1))

    per_config: dict[str, Any] = {}
    for conf in tied:
        runs = [t for t in traj if tuple(t["config"]) == conf]
        noise: dict[str, dict[int, float]] = {}
        for sid in snaps:
            ents = sorted(load_package(package)[sid].get_entity_mapping())
            fit, hold = anchor_split(sid, ents)
            noise[sid] = {e: median_noise({t["seed"]: t["emb"][e] for t in runs if t["sid"] == sid}, fit, hold)
                          for e in record}
        mrr = by_config[conf]
        best = max(mrr.values())
        epochs = []
        if step == "c1":
            for e in cfg["search"]["eval_epochs"]:
                conv = [noise_aware_converged(t["losses"][:e], gate["block"], gate["z"], gate["max_last_to_first"])["converged"]
                        for t in runs]
                epochs.append({"epoch": e, "mrr": mrr[e], "mrr_ok": mrr[e] >= 0.98 * best,
                               "converged_runs": sum(conv), "runs": len(conv),
                               "qualifies": mrr[e] >= 0.98 * best and all(conv)})
        else:
            nxt = dict(zip(c["c2"]["candidate_epochs"], c["c2"]["lookahead_epochs"]))
            for e in c["c2"]["candidate_epochs"]:
                stable = {sid: stability_plateau(noise[sid], e, nxt[e], 0.01) for sid in snaps}
                epochs.append({"epoch": e, "next": nxt[e], "mrr": mrr[e], "mrr_ok": mrr[e] >= 0.98 * best,
                               "stable_by_snapshot": stable,
                               "qualifies": mrr[e] >= 0.98 * best and all(stable.values())})
        per_config[str(list(conf))] = {"epochs": epochs, "best_mrr": best,
                                       "noise_by_snapshot_epoch": {sid: {str(e): v for e, v in noise[sid].items()} for sid in snaps},
                                       "first_qualifying_epoch": next((x["epoch"] for x in epochs if x["qualifies"]), None)}
    qualifying = [(v["first_qualifying_epoch"], json.loads(k)) for k, v in per_config.items() if v["first_qualifying_epoch"]]
    chosen = min(qualifying, key=lambda q: (q[0], q[1])) if qualifying else None
    selection = {"step": step, "status": "SELECTED" if chosen else "NO_EPOCH_SATISFIES_REGISTERED_RULE",
                 "epoch_rule": "c1_gate_v2" if step == "c1" else "c2_stability",
                 "train_convergence_gate": c[step]["train_convergence_gate"],
                 "dimension": chosen[1][0] if chosen else None, "learning_rate": chosen[1][1] if chosen else None,
                 "margin": chosen[1][2] if chosen else None, "epochs": chosen[0] if chosen else None,
                 "tied_configs": [list(t) for t in tied], "search_dir": str(search_dir),
                 "search_scores_sha256": sha((search_dir / "search_scores.json").read_bytes()), "per_config": per_config}
    write_json(stage / "selection.json", selection)
    write_json(stage / "loss_curves.json", {f"{t['config']}_{t['sid']}_seed{t['seed']}": t["losses"] for t in traj})
    manifest(stage, f"s3_contingency_{step}", cfg, {"selection.json": None, "loss_curves.json": None})
    print(json.dumps({k: v for k, v in selection.items() if k != "per_config"}, indent=1))
    for k, v in per_config.items():
        print(k, "first qualifying E:", v["first_qualifying_epoch"])
        for x in v["epochs"]:
            print("   ", {kk: vv for kk, vv in x.items() if kk != "stable_by_snapshot"}, x.get("stable_by_snapshot", ""))
        print("   noise:", {sid: {e: round(n, 3) for e, n in d.items()} for sid, d in v["noise_by_snapshot_epoch"].items()})
    return 0 if chosen else 2


def run_c3(cfg: dict[str, Any]) -> int:
    """Pre-registered C3: mini-batch Adam grid search, then the C2 stability epoch rule on the tied set."""
    c2, package = cfg["contingency_c"]["c2"], cfg["package"]
    s, v, g = cfg["search"], cfg["validation"], cfg["contingency_c"]["c3"]["grid"]
    run_dir = OUT_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    stage = run_dir / "contingency_c3"
    stage.mkdir(parents=True)
    print("run dir:", run_dir, flush=True)
    grid = [(d, lr, m, neg) for d in g["dimension"] for lr in g["learning_rate"] for m in g["margin"]
            for neg in g["negative_sampling"]]
    tasks = [(package, sid, fold, seed, d, lr, m, s["eval_epochs"], v["fold_salt"], v["folds"], neg)
             for (d, lr, m, neg) in grid for sid in s["dev_snapshots"] for seed in s["seeds"] for fold in range(v["folds"])]
    print(f"c3 search: {len(tasks)} runs", flush=True)
    with ProcessPoolExecutor(WORKERS) as pool:
        results = list(pool.map(search_task, tasks, chunksize=1))
    pooled: dict[tuple[Any, ...], dict[int, dict[str, list[float]]]] = {}
    for r in results:
        cell = pooled.setdefault((r["d"], r["lr"], r["margin"], r["neg"]), {})
        for ep, rr in r["rr"].items():
            cell.setdefault(int(ep), {}).setdefault(r["sid"], []).extend(rr)
    score = {conf: {ep: float(np.mean([np.mean(x) for x in by_snap.values()])) for ep, by_snap in by_ep.items()}
             for conf, by_ep in pooled.items()}
    rows = [{"config": list(conf), "epoch": ep, "score": sc,
             "per_snapshot_mrr": {sid: float(np.mean(x)) for sid, x in pooled[conf][ep].items()}}
            for conf, by_ep in sorted(score.items()) for ep, sc in sorted(by_ep.items())]
    top = max(max(v_.values()) for v_ in score.values())
    tied = sorted(conf for conf, v_ in score.items() if max(v_.values()) >= top - 0.005)
    print(f"c3 top score {top:.4f}; tied {tied}", flush=True)

    record = sorted(set(c2["candidate_epochs"]) | set(c2["lookahead_epochs"]))
    snaps = cfg["epochs"]["convergence_snapshots"]
    ttasks = [(package, sid, seed, d, lr, m, record, neg) for (d, lr, m, neg) in tied for sid in snaps for seed in cfg["seeds"]]
    with ProcessPoolExecutor(WORKERS) as pool:
        traj = list(pool.map(trajectory_task, ttasks, chunksize=1))
    gate = cfg["gates"]["convergence"]
    nxt = dict(zip(c2["candidate_epochs"], c2["lookahead_epochs"]))
    per_config: dict[str, Any] = {}
    for conf in tied:
        runs = [t for t in traj if tuple(t["config"]) == conf]
        noise = {}
        for sid in snaps:
            ents = sorted(load_package(package)[sid].get_entity_mapping())
            fit, hold = anchor_split(sid, ents)
            noise[sid] = {e: median_noise({t["seed"]: t["emb"][e] for t in runs if t["sid"] == sid}, fit, hold) for e in record}
        best = max(score[conf].values())
        epochs = []
        for e in c2["candidate_epochs"]:
            stable = {sid: stability_plateau(noise[sid], e, nxt[e], 0.01) for sid in snaps}
            gate_v2 = sum(noise_aware_converged(t["losses"][:e], gate["block"], gate["z"], gate["max_last_to_first"])["converged"]
                          for t in runs)
            epochs.append({"epoch": e, "next": nxt[e], "mrr": score[conf][e], "mrr_ok": score[conf][e] >= 0.98 * best,
                           "stable_by_snapshot": stable, "gate_v2_diagnostic_runs": gate_v2,
                           "qualifies": score[conf][e] >= 0.98 * best and all(stable.values())})
        per_config[json.dumps(list(conf))] = {
            "epochs": epochs, "best_mrr": best, "first_qualifying_epoch": next((x["epoch"] for x in epochs if x["qualifies"]), None),
            "noise_by_snapshot_epoch": {sid: {str(e): x for e, x in noise[sid].items()} for sid in snaps}}
    neg_order = {"uniform": 0, "bernoulli": 1}
    qualifying = [(v_["first_qualifying_epoch"], json.loads(k)) for k, v_ in per_config.items() if v_["first_qualifying_epoch"]]
    chosen = min(qualifying, key=lambda q: (q[0], q[1][0], q[1][1], q[1][2], neg_order[q[1][3]])) if qualifying else None
    selection = {"step": "c3", "status": "SELECTED" if chosen else "NO_EPOCH_SATISFIES_REGISTERED_RULE",
                 "epoch_rule": "c2_stability", "train_convergence_gate": "v2_diagnostic_only", "trainer": "minibatch_adam",
                 "dimension": chosen[1][0] if chosen else None, "learning_rate": chosen[1][1] if chosen else None,
                 "margin": chosen[1][2] if chosen else None, "negative_sampling": chosen[1][3] if chosen else None,
                 "epochs": chosen[0] if chosen else None, "tied_configs": [list(t) for t in tied], "top_score": top,
                 "per_config": per_config}
    write_json(stage / "search_scores.json", {"rows": rows})
    write_json(stage / "selection.json", selection)
    write_json(stage / "loss_curves.json", {f"{t['config']}_{t['sid']}_seed{t['seed']}": t["losses"] for t in traj})
    manifest(stage, "s3_contingency_c3", cfg, {"search_scores.json": None, "selection.json": None, "loss_curves.json": None},
             extra={"src/kge/minibatch.py": sha((ROOT / "src/kge/minibatch.py").read_bytes())})
    print(json.dumps({k: v_ for k, v_ in selection.items() if k != "per_config"}, indent=1))
    for k, v_ in per_config.items():
        print(k, "first qualifying E:", v_["first_qualifying_epoch"])
        for x in v_["epochs"]:
            print("   ", {kk: vv for kk, vv in x.items() if kk != "stable_by_snapshot"}, x["stable_by_snapshot"])
        print("   noise:", {sid: {e: round(n, 3) for e, n in d_.items()} for sid, d_ in v_["noise_by_snapshot_epoch"].items()})
    return 0 if chosen else 2


def run_search(cfg: dict[str, Any], run_dir: Path) -> int:
    s, package, g = cfg["search"], cfg["package"], cfg["search"]["grid"]
    v = cfg["validation"]
    stage = run_dir / "search"
    stage.mkdir(parents=True)
    tasks = [(package, sid, fold, seed, d, lr, m, s["eval_epochs"], v["fold_salt"], v["folds"])
             for d in g["dimension"] for lr in g["learning_rate"] for m in g["margin"]
             for sid in s["dev_snapshots"] for seed in s["seeds"] for fold in range(v["folds"])]
    print(f"search: {len(tasks)} runs on {WORKERS} workers", flush=True)
    with ProcessPoolExecutor(WORKERS) as pool:
        results = list(pool.map(search_task, tasks, chunksize=1))

    table: dict[tuple[int, float, float], dict[int, dict[str, list[float]]]] = {}
    for r in results:
        cell = table.setdefault((r["d"], r["lr"], r["margin"]), {})
        for ep, rr in r["rr"].items():
            cell.setdefault(int(ep), {}).setdefault(r["sid"], []).extend(rr)
    rows = []
    for (d, lr, m), by_epoch in sorted(table.items()):
        for ep, by_snap in sorted(by_epoch.items()):
            per_snap = {sid: float(np.mean(vals)) for sid, vals in by_snap.items()}
            rows.append({"dimension": d, "learning_rate": lr, "margin": m, "epoch": ep,
                         "per_snapshot_mrr": per_snap, "score": float(np.mean(list(per_snap.values()))),
                         "n_heldout_instances": {sid: len(vals) for sid, vals in by_snap.items()}})
    best_by_config: dict[tuple[int, float, float], dict[str, Any]] = {}
    for row in rows:
        key = (row["dimension"], row["learning_rate"], row["margin"])
        if key not in best_by_config or row["score"] > best_by_config[key]["score"]:
            best_by_config[key] = row
    top = max(r["score"] for r in best_by_config.values())
    tied = [k for k, r in best_by_config.items() if r["score"] >= top - 0.005]
    chosen = min(tied)  # smaller dimension, then smaller learning rate, then smaller margin
    d, lr, m = chosen
    print(f"selected d={d} lr={lr} margin={m} score={best_by_config[chosen]['score']:.4f} (top {top:.4f}, tied={len(tied)})", flush=True)

    ep_cfg = cfg["epochs"]
    emax = max(s["eval_epochs"])
    conv_tasks = [(package, sid, seed, d, lr, m, emax) for sid in ep_cfg["convergence_snapshots"] for seed in cfg["seeds"]]
    with ProcessPoolExecutor(WORKERS) as pool:
        conv = list(pool.map(convergence_task, conv_tasks, chunksize=1))
    gate = cfg["gates"]["convergence"]
    chosen_rows = {r["epoch"]: r for r in rows if (r["dimension"], r["learning_rate"], r["margin"]) == chosen}
    best_mrr = max(r["score"] for r in chosen_rows.values())
    candidates = []
    for e in sorted(chosen_rows):
        checks = [noise_aware_converged(c["losses"][:e], gate["block"], gate["z"],
                                        gate["max_last_to_first"])["converged"] for c in conv]
        candidates.append({"epoch": e, "mrr": chosen_rows[e]["score"], "mrr_ok": chosen_rows[e]["score"] >= 0.98 * best_mrr,
                           "converged_runs": sum(checks), "runs": len(checks), "all_converged": all(checks)})
    epoch = next((c["epoch"] for c in candidates if c["mrr_ok"] and c["all_converged"]), None)
    selection = {"dimension": d, "learning_rate": lr, "margin": m, "epochs": epoch,
                 "status": "SELECTED" if epoch else "NO_EPOCH_SATISFIES_REGISTERED_RULE",
                 "score_at_best_epoch": best_by_config[chosen]["score"], "tied_configs": [list(t) for t in sorted(tied)],
                 "epoch_candidates": candidates}
    write_json(stage / "selection.json", selection)
    write_json(stage / "search_scores.json", {"rows": rows})
    write_json(stage / "convergence_loss_curves.json", {f"{c['sid']}_seed{c['seed']}": c["losses"] for c in conv})
    manifest(stage, "s3_search", cfg, {"search_scores.json": None, "selection.json": None, "convergence_loss_curves.json": None})
    print(json.dumps(selection, indent=1)[:1800])
    return 0 if epoch else 2


# ------------------------------------------------------------------ train stage
def final_task(task: tuple[Any, ...]) -> dict[str, Any]:
    package, sid, seed, d, lr, margin, epochs, ckpt_dir, config_hash, git, *rest = task
    neg = rest[0] if rest else None
    ds = load_package(package)[sid]
    triples = triples_of(ds)
    model, losses, _, idx = train_model(package, sid, triples, d, lr, margin, seed, epochs, neg=neg)
    prov = CheckpointProvenance(
        snapshot_id=sid, snapshot_hash=ds.snapshot_hash, seed=seed, model="TransE", dimension=d, norm=2,
        entity_mapping_hash=ds.compute_mapping_hash(), relation_mapping_hash=sha(json.dumps(
            ds.get_relation_mapping(), sort_keys=True).encode()), config_hash=config_hash,
        git_commit=git["commit"], git_dirty=git["dirty_state"])
    diag = diagnostics(model, idx, margin, seed)
    ckpt = KGECheckpoint(provenance=prov, entity_embeddings=model.get_all_entity_embeddings(),
                         relation_embeddings=model.get_all_relation_embeddings(),
                         training_metrics={"epochs": epochs, "epoch_losses": losses, "final_loss": losses[-1], **diag})
    ckpt.verify_finite()
    path = None
    if ckpt_dir:
        path = ckpt.save(Path(ckpt_dir) / f"{sid}_seed{seed}.json")
    return {"sid": sid, "seed": seed, "artifact_hash": ckpt.artifact_hash, "path": path, "losses": losses, **diag}


def quality_task(task: tuple[Any, ...]) -> dict[str, Any]:
    package, sid, fold, seed, d, lr, margin, epochs, salt, k, *rest = task
    neg = rest[0] if rest else None
    ds = load_package(package)[sid]
    triples = triples_of(ds)
    val = folds_of(package, sid, k, salt)[fold]
    held = set(val)
    train = [t for t in triples if t not in held]
    model, _, _, _ = train_model(package, sid, train, d, lr, margin, seed, epochs, neg=neg)
    e2i, r2i = ds.get_entity_mapping(), ds.get_relation_mapping()
    ent, rel = embeddings(model)
    return {"sid": sid, "fold": fold,
            "model": filtered_reciprocal_ranks(ent, rel, e2i, r2i, val, triples).tolist(),
            "baseline": frequency_baseline_reciprocal_ranks(e2i, train, val, triples).tolist(),
            "n_entities": len(e2i)}


def noise_floor(package: str, sid: str, ckpts: dict[int, dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    ds = load_package(package)[sid]
    ents = sorted(ds.get_entity_mapping())
    deg = Counter([h for h, _, _ in triples_of(ds)] + [t for _, _, t in triples_of(ds)])
    fit, hold = anchor_split(sid, ents)
    mats = {s: np.array([c["entity_embeddings"][e] for e in ents]) for s, c in ckpts.items()}
    rng = np.random.default_rng(int(sha(f"s3-random|{sid}".encode())[:8], 16))
    d = next(iter(mats.values())).shape[1]
    rand = [rng.normal(size=(len(ents), d)) for _ in range(2)]
    ref = np.nanmedian(procrustes_holdout_distance(rand[0], rand[1], fit, hold))
    pairs = [(13, 37), (13, 101), (37, 101)]
    out = {"random_reference_median": float(ref), "buckets": {}}
    for name, lo, hi in ((str(b), b[0], b[1]) for b in cfg["gates"]["stability"]["degree_buckets"]):
        sel = [j for j, i in enumerate(hold) if lo <= deg[ents[i]] <= hi]
        if len(sel) < 10:
            out["buckets"][name] = {"holdout_anchors": len(sel), "status": "NOT_EVALUATED_FEWER_THAN_10"}
            continue
        dist = np.concatenate([procrustes_holdout_distance(mats[a], mats[b], fit, hold)[sel] for a, b in pairs])
        med = float(np.nanmedian(dist))
        out["buckets"][name] = {"holdout_anchors": len(sel), "median_distance": med,
                                "status": "PASS" if med < ref else "FAIL"}
    return out


def run_train(cfg: dict[str, Any], run_dir: Path, selection_path: Path | None = None) -> int:
    sel = json.loads((selection_path or run_dir / "search/selection.json").read_text(encoding="utf-8"))
    binding_convergence = sel.get("train_convergence_gate", "v2_binding") == "v2_binding"
    if sel["status"] != "SELECTED":
        raise SystemExit("search stage did not select an epoch count; train stage refused")
    d, lr, m, epochs, package = sel["dimension"], sel["learning_rate"], sel["margin"], sel["epochs"], cfg["package"]
    neg = sel.get("negative_sampling")
    stage = run_dir / "train"
    ckpt_dir = stage / "checkpoints"
    ckpt_dir.mkdir(parents=True)
    git = provenance()
    config_hash = sha(encode({"d": d, "lr": lr, "margin": m, "epochs": epochs, "norm": 2,
                              "trainer": sel.get("trainer", "producer_sgd"),
                              "negatives": neg or cfg["negative_sampling"]}))
    snaps = list(load_package(package))
    print(f"train: d={d} lr={lr} margin={m} E={epochs}; {len(snaps)} snapshots x {len(cfg['seeds'])} seeds", flush=True)
    qv = cfg["gates"]["quality"]
    ftasks = [(package, sid, seed, d, lr, m, epochs, str(ckpt_dir), config_hash, git, neg)
              for sid in snaps for seed in cfg["seeds"]]
    qtasks = [(package, sid, fold, qv["seed"], d, lr, m, epochs, cfg["validation"]["fold_salt"], qv["folds"], neg)
              for sid in snaps for fold in range(qv["folds"])]
    with ProcessPoolExecutor(WORKERS) as pool:
        finals = list(pool.map(final_task, ftasks, chunksize=1))
        quals = list(pool.map(quality_task, qtasks, chunksize=1))
        again = pool.submit(final_task, (package, "T05", 13, d, lr, m, epochs, None, config_hash, git, neg)).result()

    gate = cfg["gates"]["convergence"]
    convergence = {}
    for f in finals:
        res = noise_aware_converged(f["losses"], gate["block"], gate["z"], gate["max_last_to_first"])
        convergence[f"{f['sid']}_seed{f['seed']}"] = {**res, "final_loss": f["losses"][-1],
                                                      "violation_rate": f["violation_rate"]}
    quality = {}
    for sid in snaps:
        rows = [q for q in quals if q["sid"] == sid]
        model_rr = [x for q in rows for x in q["model"]]
        base_rr = [x for q in rows for x in q["baseline"]]
        mean, lo, hi = bootstrap_ci(model_rr, qv["bootstrap_draws"], qv["bootstrap_seed"])
        base = float(np.mean(base_rr)) if base_rr else float("nan")
        quality[sid] = {"heldout_triples": len(model_rr), "model_mrr": mean, "ci95": [lo, hi], "frequency_baseline_mrr": base,
                        "random_baseline_mrr": random_baseline_mrr(rows[0]["n_entities"]),
                        "status": "PASS" if (lo > base) else "FAIL"}
    stability = {}
    for sid in snaps:
        ck = {seed: json.loads((ckpt_dir / f"{sid}_seed{seed}.json").read_text(encoding="utf-8")) for seed in cfg["seeds"]}
        stability[sid] = noise_floor(package, sid, ck, cfg)
    first = next(f for f in finals if f["sid"] == "T05" and f["seed"] == 13)
    determinism = {"first": first["artifact_hash"], "second": again["artifact_hash"],
                   "status": "PASS" if first["artifact_hash"] == again["artifact_hash"] else "FAIL"}
    statuses = {
        "convergence": all(v["converged"] for v in convergence.values()),
        "quality": all(v["status"] == "PASS" for v in quality.values()),
        "stability": all(b["status"] != "FAIL" for s in stability.values() for b in s["buckets"].values()),
        "determinism": determinism["status"] == "PASS"}
    binding = {k: v for k, v in statuses.items() if k != "convergence" or binding_convergence}
    report = {"stage": "S3", "scientific_certification": False, "selection": {k: sel.get(k) for k in (
                  "dimension", "learning_rate", "margin", "epochs", "step", "epoch_rule", "train_convergence_gate",
                  "trainer", "negative_sampling")},
              "gates": statuses, "binding_gates": sorted(binding),
              "status": "TECHNICAL_GATES_PASS" if all(binding.values()) else "TECHNICAL_GATES_FAIL",
              "convergence": convergence, "quality": quality, "stability": stability, "determinism": determinism,
              "checkpoints": {f"{f['sid']}_seed{f['seed']}": f["artifact_hash"] for f in finals}}
    write_json(stage / "s3_report.json", report)
    manifest(stage, "s3_train", cfg, {"s3_report.json": None},
             extra={f"checkpoints/{p.name}": sha(p.read_bytes()) for p in sorted(ckpt_dir.glob("*.json"))})
    print(json.dumps({"status": report["status"], "gates": statuses, "binding": sorted(binding)}, indent=1))
    return 0 if all(binding.values()) else 2


def manifest(stage: Path, mode: str, cfg: dict[str, Any], files: dict[str, None], extra: dict[str, str] | None = None) -> None:
    package = ROOT / cfg["package"]
    hashes = {str(CONFIG_PATH.relative_to(ROOT)): sha(CONFIG_PATH.read_bytes()),
              f"{cfg['package']}/snapshot_boundaries.yaml": sha((package / "snapshot_boundaries.yaml").read_bytes()),
              f"{cfg['package']}/config/downstream_transe_config.yaml": sha((package / "config/downstream_transe_config.yaml").read_bytes()),
              "scripts/s3_backbone.py": sha(Path(__file__).read_bytes()), "src/kge/validation.py": sha((ROOT / "src/kge/validation.py").read_bytes()),
              "src/kge/model.py": sha((ROOT / "src/kge/model.py").read_bytes())}
    artifacts = {n: sha((stage / n).read_bytes()) for n in files} | (extra or {})
    m = {"experiment_id": f"{mode}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
         "protocol_version": "v1-draft", "mode": mode, "scientific_certification": False, "git": provenance(),
         "seed": None, "inputs": {"data_hash": sha(encode(hashes)), "snapshot_hash": hashes[f"{cfg['package']}/snapshot_boundaries.yaml"],
                                   "query_hash": None, "entity_map_hash": "entity_map_v2", "relation_map_hash": "unchanged",
                                   "config_hash": hashes[str(CONFIG_PATH.relative_to(ROOT))], "hashes": hashes},
         "environment": {"python": platform.python_version(), "os": platform.platform(), "pyarrow": pa.__version__, "numpy": np.__version__},
         "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
         "artifacts": {"hashes": artifacts},
         "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(), "actor_or_runner": "scripts/s3_backbone.py"}}
    validate_manifest(m)
    write_json(stage / "experiment_manifest.json", m)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["search", "contingency", "c3", "train"])
    ap.add_argument("--run-dir", default=None, help="existing run directory (required for train)")
    ap.add_argument("--search-dir", default=None, help="search stage directory (contingency)")
    ap.add_argument("--step", choices=["c1", "c2"], default=None, help="contingency step")
    ap.add_argument("--selection", default=None, help="selection.json to train from (default: <run-dir>/search)")
    args = ap.parse_args()
    cfg = yaml.safe_load(CONFIG_PATH.read_bytes())
    if args.stage == "search":
        run_dir = OUT_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        print("run dir:", run_dir, flush=True)
        return run_search(cfg, run_dir)
    if args.stage == "c3":
        return run_c3(cfg)
    if args.stage == "contingency":
        if not (args.search_dir and args.step):
            raise SystemExit("--search-dir and --step are required for the contingency stage")
        return run_contingency(cfg, Path(args.search_dir), args.step)
    if not args.run_dir:
        raise SystemExit("--run-dir is required for the train stage")
    return run_train(cfg, Path(args.run_dir), Path(args.selection) if args.selection else None)


if __name__ == "__main__":
    raise SystemExit(main())
