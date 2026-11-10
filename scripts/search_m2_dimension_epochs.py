"""Tìm số chiều và ngân sách huấn luyện TransE-L2 trong phạm vi xác thực Dev."""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from kge.checkpoint import CheckpointProvenance, KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.model import TransEConfig, TransEModel  # noqa: E402
from kge.validation import validation_observations, validate_validation_inputs  # noqa: E402
from scripts.run_kge_validation import preflight  # noqa: E402

REGISTRATION = "outputs/m2_quality_validation_registration/20261104_v1"
PARENT = "outputs/m2_quality_validation_v31/20261104_v1"
DIMENSIONS = (32, 64)
EPOCHS = (1, *range(5, 251, 5))
SEEDS = (13, 37, 101)


def mean(values: Iterable[float]) -> float:
    numbers = tuple(values)
    return math.fsum(numbers) / len(numbers)


def verify_checkpoint(cp: KGECheckpoint, queries: list, pairs: list, candidates: list[str],
                      loss: float, rows: list[dict], margin: float) -> None:
    indices = {entity: i for i, entity in enumerate(candidates)}
    vectors = np.asarray([cp.entity_embeddings[e] for e in candidates])
    relations = {r: np.asarray(v) for r, v in cp.relation_embeddings.items()}

    def energy(triple: tuple[str, str, str]) -> float:
        h, r, t = triple
        z = vectors[indices[h]] + relations[r] - vectors[indices[t]]
        return float(np.linalg.norm(z))

    expected_loss = mean(max(0.0, margin + energy(a) - energy(b)) for a, b in pairs)
    require(math.isclose(loss, expected_loss, rel_tol=1e-10, abs_tol=1e-12), "Loss xác thực không khớp")
    for (triple, side, gold, mask), saved in zip(queries, rows, strict=True):
        h, r, t = triple
        z = (vectors + relations[r] - vectors[indices[t]] if side == "head"
             else vectors[indices[h]] + relations[r] - vectors)
        scores = -np.sqrt(np.sum(np.square(z), axis=1))
        ordered = np.sort(scores[mask])
        score = scores[indices[gold]]
        lower, upper = np.searchsorted(ordered, score, side="left"), np.searchsorted(ordered, score, side="right")
        rank = len(ordered) - (lower + upper - 1) / 2
        require(saved == {"triple": list(triple), "side": side, "rank": rank, "reciprocal_rank": 1 / rank,
                          "candidate_count": len(ordered)}, "Thứ hạng xác thực không khớp")


def run_job(descriptor: dict, destination: Path, dimension: int, seed: int, design_hash: str) -> None:
    config_path = bound_file(ROOT, descriptor)
    _, (cfg, source, split, pairs, positives) = preflight(ROOT, config_path)
    require(cfg["training_filter_scope"] == "train", "Phạm vi lấy mẫu âm không khớp")
    config = TransEConfig(**{**cfg["model"], "dimension": dimension, "epochs": EPOCHS[-1]}, seed=seed)
    validate_validation_inputs(source, config, split, pairs, positives, training_filter_scope="train")
    train = SnapshotDataset.create(source.snapshot_id + "_VALIDATION_TRAIN", split.train)
    model = TransEModel(train.get_entity_mapping(), train.get_relation_mapping(), config)
    train_ids = [(model.entity_to_id[h], model.relation_to_id[r], model.entity_to_id[t]) for h, r, t in split.train]
    known = set(positives)
    candidates = train.entities
    queries = [
        ((h, r, t), side, gold, np.array([
            e == gold or ((e, r, t) if side == "head" else (h, r, e)) not in known for e in candidates]))
        for h, r, t in sorted(split.validation) for side, gold in (("head", h), ("tail", t))
    ]
    commit, dirty = get_git_info(ROOT)
    job = {"snapshot": source.snapshot_id, "model": asdict(config), "split_hash": split.sha256,
           "registration_config_sha256": descriptor["sha256"], "search_hash": design_hash}
    job_hash = content_hash(job)
    provenance = CheckpointProvenance(
        train.snapshot_id, train.snapshot_hash, seed, "TransE", dimension, 2, train.compute_mapping_hash(),
        content_hash(train.get_relation_mapping()), job_hash, commit, dirty,
    )
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "thiet_ke.json", job)
    checkpoints = destination / "epochs"
    checkpoints.mkdir()
    rng = random.Random(seed)
    training_known = set(train_ids)
    log = []
    for epoch in range(1, config.epochs + 1):
        loss = model.train_epoch(train_ids, rng, positive_triples_set=training_known)
        row = {"epoch": epoch, "loss_huan_luyen": loss, "chan_doan": asdict(model.last_train_diagnostics)}
        require(math.isfinite(loss), "Loss huấn luyện không hữu hạn")
        if epoch in EPOCHS:
            val_loss, ranks, metrics = validation_observations(model, split, pairs, positives)
            path = checkpoints / f"{epoch:04d}.json"
            KGECheckpoint(provenance, model.get_all_entity_embeddings(), model.get_all_relation_embeddings(),
                          {"epoch": epoch, "role": "dimension_epoch_search_dev"}).save(path)
            verify_checkpoint(KGECheckpoint.load(path), queries, pairs, candidates, val_loss, ranks, config.margin)
            row.update({"loss_xac_thuc": val_loss, "chi_so": metrics, "so_thu_hang": len(ranks)})
            write_json(checkpoints / f"{epoch:04d}_ranks.json", ranks)
        log.append(row)
    write_json(destination / "nhat_ky.json", log)
    write_json(destination / "ma_bam.json", {p.relative_to(destination).as_posix(): sha256_file(p)
                                             for p in destination.rglob("*") if p.is_file()})


def summarize(output: Path, snapshots: list[str]) -> dict[str, Any]:
    logs = {}
    for d in DIMENSIONS:
        for sid in snapshots:
            for seed in SEEDS:
                logs[d, sid, seed] = read_json(output / f"d{d}" / sid / f"seed_{seed}" / "nhat_ky.json")
    grid = []
    for d in DIMENSIONS:
        for epoch in EPOCHS:
            snapshot_mrr = {sid: mean(logs[d, sid, s][epoch - 1]["chi_so"]["MRR"] for s in SEEDS)
                            for sid in snapshots}
            grid.append({"chieu": d, "epoch": epoch, "MRR": mean(snapshot_mrr.values()),
                         "MRR_theo_snapshot": snapshot_mrr,
                         "loss_xac_thuc": mean(logs[d, sid, s][epoch - 1]["loss_xac_thuc"]
                                               for sid in snapshots for s in SEEDS)})
    ordered = sorted(grid, key=lambda r: (-r["MRR"], r["chieu"], r["epoch"]))
    return {"tot_nhat_trong_luoi": ordered[0],
            "tot_nhat_theo_chieu": {str(d): next(r for r in ordered if r["chieu"] == d) for d in DIMENSIONS},
            "du_lieu_xep_hang": grid,
            "so_epoch_huan_luyen": sum(map(len, logs.values())),
            "so_checkpoint_kiem_chung": len(logs) * len(EPOCHS),
            "so_dong_thu_hang_kiem_chung": sum(r.get("so_thu_hang", 0) for log in logs.values() for r in log)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 7), default=4)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs" and not output.exists()
            and all(p.lower() != "locked_test" for p in output.parts), "Cần thư mục kết quả mới dưới outputs/")
    original = verify_artifacts(ROOT / REGISTRATION)
    verified = verify_artifacts(ROOT / PARENT)
    require(original["inputs"]["config_hash"] == verified["inputs"]["config_hash"], "Hai hồ sơ không khớp")
    source_hashes = dict(verified["inputs"]["hashes"])
    for relative in (f"{REGISTRATION}/experiment_manifest.json", f"{PARENT}/experiment_manifest.json",
                     "configs/kge.yaml", "configs/m2_data_3_1_candidate_v2.yaml", "src/kge/model.py",
                     "src/kge/checkpoint.py", "src/kge/math_utils.py", Path(__file__).relative_to(ROOT).as_posix()):
        source_hashes[relative] = sha256_file(ROOT / relative)
    for relative, digest in source_hashes.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    allowed = yaml.safe_load((ROOT / "configs/kge.yaml").read_bytes())["dimension_search_space"]
    require(tuple(allowed) == DIMENSIONS, "Không gian số chiều khác giao thức")
    plan = read_json(ROOT / REGISTRATION / "ke_hoach.json")
    snapshots = [r["snapshot"] for r in plan["ke_hoach"]]
    require(snapshots == [f"T{i:02d}" for i in range(1, 11)] and tuple(plan["seeds"]) == SEEDS,
            "Thiếu snapshot hoặc seed")
    for row in plan["ke_hoach"]:
        ready, _ = preflight(ROOT, bound_file(ROOT, row["design"]))
        require(ready["ready"] and ready["split_hash"] == row["split_hash"], "Phân hoạch đã thay đổi")
    design = {"snapshot": snapshots, "chieu": DIMENSIONS, "epoch_cham": EPOCHS, "seeds": SEEDS,
              "tham_so_con_lai": {k: v for k, v in plan["model"].items() if k not in {"dimension", "epochs"}},
              "chon": "MRR xác thực trung bình đều theo seed và snapshot cao nhất; đồng điểm chọn chiều nhỏ hơn, "
                      "sau đó epoch sớm hơn", "phan_hoach": plan["ke_hoach"], "pham_vi": "Phát triển V3.1"}
    design_hash = content_hash(design)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "thiet_ke_tim_kiem.json", design)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for row in reversed(plan["ke_hoach"]):
            for dimension in DIMENSIONS:
                for seed in SEEDS:
                    label = f"d{dimension}/{row['snapshot']}/seed_{seed}"
                    future = pool.submit(run_job, row["design"], output / label, dimension, seed, design_hash)
                    futures[future] = label
        for future in as_completed(futures):
            future.result()
            print(f"{futures[future]} OK", flush=True)
    summary = summarize(output, snapshots)
    write_json(output / "ket_qua_tim_kiem.json", summary)
    for relative, digest in source_hashes.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    artifacts = {p.relative_to(output).as_posix(): sha256_file(p) for p in (
        output / "thiet_ke_tim_kiem.json", output / "ket_qua_tim_kiem.json", *sorted(output.glob("d*/T*/seed_*/ma_bam.json")))}
    require(len(artifacts) == 62, "Thiếu bản kê lần huấn luyện")
    commit, dirty = get_git_info(ROOT)
    manifest = {
        **verified, "experiment_id": output.name, "stage": "m2_dimension_epoch_search_dev",
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**verified["inputs"], "config_hash": design_hash, "hashes": source_hashes},
        "environment": {"python": platform.python_version(), "os": platform.platform(), "numpy": np.__version__},
        "access": {**verified["access"], "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": artifacts},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)
    print(json.dumps(summary["tot_nhat_trong_luoi"]), flush=True)


if __name__ == "__main__":
    main()
