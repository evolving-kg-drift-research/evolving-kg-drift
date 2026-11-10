"""Đăng ký và chạy riêng lượt xác thực TransE-L2 trên V3.1."""
from __future__ import annotations

import argparse
import platform
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, inspect_package, require_current_package  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from kge.splits import coverage_split  # noqa: E402
from kge.validation import fixed_negative_pairs  # noqa: E402
from scripts.evaluate_legacy_t01 import metrics, rank_query  # noqa: E402
from scripts.run_kge_validation import design_identity, preflight, run  # noqa: E402

SEEDS = [13, 37, 101]
MODEL = {"dimension": 64, "norm": 2, "epochs": 50, "batch_size": 32, "learning_rate": .01,
         "margin": 1.0, "normalize_entities": True}
AUTHORIZATION = "Hãy thực hiện cách 1 giúp tôi."
FEASIBILITY = "outputs/m2_retraining_preparation/20261104_v1"
SNAPSHOTS = [f"T{i:02d}" for i in range(1, 11)]


def verify_inputs() -> tuple[dict, dict, dict[str, str]]:
    base = require_current_package(ROOT, ACTIVE_PACKAGE)
    previous = verify_artifacts(ROOT / FEASIBILITY)
    hashes = dict(previous["inputs"]["hashes"])
    # The engine was accelerated after the structural audit. Record its new identity explicitly.
    validation_code = "src/kge/validation.py"
    hashes[validation_code] = sha256_file(ROOT / validation_code)
    for path, digest in hashes.items():
        bound_file(ROOT, {"path": path, "sha256": digest})
    dataset, receipt = inspect_package(base)
    require(list(dataset) == SNAPSHOTS, "Sai danh sách snapshot")
    for path, digest in receipt["input_hashes"].items():
        require(hashes[(ACTIVE_PACKAGE / path).as_posix()] == digest, f"Sai mã băm V3.1: {path}")
    for path in (f"{FEASIBILITY}/experiment_manifest.json", f"{FEASIBILITY}/kha_thi_xac_thuc.json",
                 "scripts/run_kge_validation.py", "scripts/verify_kge_validation.py", "scripts/evaluate_legacy_t01.py",
                 Path(__file__).resolve().relative_to(ROOT).as_posix()):
        hashes[path] = sha256_file(ROOT / path)
    return dataset, previous, hashes


def register(registration: Path) -> None:
    datasets, previous, hashes = verify_inputs()
    base = ROOT / ACTIVE_PACKAGE
    specs = yaml.safe_load((base / "config/downstream_transe_config.yaml").read_bytes())["snapshots"]
    pilot = yaml.safe_load((ROOT / "configs/m2_pilot.yaml").read_bytes())
    fraction, salt = (pilot["validation"][key] for key in ("target_fraction", "salt"))
    expected = read_json(ROOT / FEASIBILITY / "kha_thi_xac_thuc.json")["so_dem_theo_snapshot"]
    registration.mkdir(parents=True, exist_ok=False)
    plans = []
    for spec, counts in zip(specs, expected, strict=True):
        sid = spec["snapshot_id"]
        ds = datasets[sid]
        split = coverage_split(ds, fraction, salt)
        require(sid == counts["snapshot"] and len(split.train) == counts["huan_luyen"]
                and len(split.validation) == counts["xac_thuc"], "Phân hoạch khác kiểm tra khả thi")
        positives = [t.to_tuple() for t in ds.triples]
        pairs = fixed_negative_pairs(ds, split.validation, positives, seed=13)
        path = registration / sid
        path.mkdir()

        def save(name: str, payload: object) -> dict[str, str]:
            p = path / name
            write_json(p, payload)
            return {"path": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p)}

        snapshot_files = [ACTIVE_PACKAGE / item for item in (
            spec["parquet_path"], spec["parquet_path"] + ".manifest.json", f"snapshots/snapshot_{sid}_manifest.yaml")]
        cfg = {"version": "quality_validation_runner_v1", "status": "APPROVED_DEV_STAGE",
               "scientific_certification": False, "package_root": ACTIVE_PACKAGE.as_posix(), "snapshot": spec,
               "snapshot_files": [{"path": p.as_posix(), "sha256": hashes[p.as_posix()]} for p in snapshot_files],
               "split": save("split.json", split.descriptor()), "negative_pairs": save("negative_pairs.json", pairs),
               "model": MODEL, "seeds": SEEDS, "training_filter_scope": "train", "approval": None}
        identity = design_identity(cfg)
        cfg["approval"] = save("approval.json", {"actor": "user", "scope": "quality_validation_dev",
                                               "instruction": AUTHORIZATION, "design_sha256": identity})
        config = save("design.json", cfg)
        ready, _ = preflight(ROOT, ROOT / config["path"])
        require(ready["ready"] and ready["design_hash"] == identity, f"Thiết kế chưa sẵn sàng: {sid}")
        frequency = Counter(e for h, _, t in split.train for e in (h, t))
        known = set(positives)
        baseline_ranks = [
            rank_query(triple, side, ds.entities, known,
                       lambda candidate, index=index: float(frequency[candidate[index]]))
            for triple in sorted(split.validation) for side, index in (("head", 0), ("tail", 2))
        ]
        baseline = save("baseline.json", {"chi_so": metrics(baseline_ranks),
                                          "hang": [row["rank"] for row in baseline_ranks]})
        plans.append({"snapshot": sid, "design": config, "baseline": baseline, "split_hash": split.sha256})
    write_json(registration / "ke_hoach.json", {"vai_tro": "xac_thuc_phat_trien", "model": MODEL, "seeds": SEEDS,
                                             "seed_cap_am": 13, "ty_le_muc_tieu": fraction, "salt": salt,
                                             "quy_tac_checkpoint": "Mỗi epoch, dùng epoch 50 để đối chiếu mô tả",
                                             "ke_hoach": plans})
    commit, dirty = get_git_info(ROOT)
    manifest = {
        "experiment_id": registration.name, "protocol_version": previous["protocol_version"], "seed": None,
        "stage": "registered_v31_quality_validation_dev", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**previous["inputs"], "config_hash": content_hash(plans), "hashes": hashes},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {p.relative_to(registration).as_posix(): sha256_file(p)
                                 for p in registration.rglob("*") if p.is_file()}},
    }
    validate_manifest(manifest)
    write_json(registration / "experiment_manifest.json", manifest)
    verify_artifacts(registration)


def run_snapshot(config: Path, destination: Path) -> None:
    run(ROOT, config, execute=True, output=destination.relative_to(ROOT))


def check_registration(registration: Path, original_orchestrator: Path | None = None) -> tuple[dict, list, dict]:
    registered = verify_artifacts(registration)
    require(registered["stage"] == "registered_v31_quality_validation_dev", "Sai giai đoạn đã đăng ký")
    hashes = dict(registered["inputs"]["hashes"])
    if original_orchestrator is not None:
        source = Path(__file__).resolve().relative_to(ROOT).as_posix()
        archived = original_orchestrator.relative_to(ROOT).as_posix()
        require(archived != source, "Cần bản sao điều phối ban đầu")
        hashes[archived] = hashes.pop(source)
        hashes[source] = sha256_file(ROOT / source)
    for path, digest in hashes.items():
        bound_file(ROOT, {"path": path, "sha256": digest})
    registered_plan = read_json(registration / "ke_hoach.json")
    plans = registered_plan["ke_hoach"]
    require([p["snapshot"] for p in plans] == SNAPSHOTS
            and content_hash(plans) == registered["inputs"]["config_hash"], "Kế hoạch không khớp")
    return registered, plans, hashes


def execute(registration: Path, destination: Path, workers: int) -> None:
    require(not destination.exists(), "Cần thư mục kết quả mới")
    registered, plans, hashes = check_registration(registration)
    for plan in plans:
        cfg = bound_file(ROOT, plan["design"])
        report, _ = preflight(ROOT, cfg)
        require(report["ready"] and report["split_hash"] == plan["split_hash"], "Kiểm tra trước chạy thất bại")
    destination.mkdir(parents=True, exist_ok=False)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(run_snapshot, ROOT / p["design"]["path"], destination / p["snapshot"]): p["snapshot"]
                for p in reversed(plans)}
        for job in as_completed(jobs):
            job.result()
            print(f"{jobs[job]} 3/3", flush=True)
    seal_run(registration, destination, registered, plans, hashes)


def seal_run(registration: Path, destination: Path, registered: dict, plans: list, hashes: dict) -> None:
    require(destination.is_dir() and not any((destination / p).exists() for p in (
        "experiment_manifest.json", "tong_kiem_chung.json")), "Cần lượt chạy có đủ run con và chưa có bản kê tổng")
    totals = {}
    artifacts = {}
    for plan in plans:
        sid = plan["snapshot"]
        path = destination / sid
        child = verify_artifacts(path)
        expected_config = read_json(bound_file(ROOT, plan["design"]))
        ready = read_json(path / "readiness.json")
        require(child["stage"] == "quality_validation_dev_three_seed"
                and child["inputs"]["config_hash"] == content_hash(expected_config)
                and child["inputs"]["hashes"] == ready["input_hashes"]
                and ready["ready"] and ready["split_hash"] == plan["split_hash"], "Run con khác đăng ký")
        for relative, digest in ready["input_hashes"].items():
            bound_file(path, {"path": "inputs/" + relative, "sha256": digest})
        summary = read_json(path / "independent_verification.json")
        require(set(summary) == set(map(str, SEEDS))
                and all(r["status"] == "SAVED_VALIDATION_CHECKS_PASS" and r["epochs_verified"] == MODEL["epochs"]
                        and r["ranking_rows_verified"] == 2 * MODEL["epochs"] * ready["validation_triples"]
                        and r["manifest_sha256"] == child["artifacts"]["hashes"][f"seed_{seed}/experiment_manifest.json"]
                        for seed, r in summary.items()), "Thiếu epoch đã kiểm tra")
        totals[sid] = {key: sum(r[key] for r in summary.values())
                       for key in ("epochs_verified", "ranking_rows_verified")}
        relative = f"{sid}/experiment_manifest.json"
        artifacts[relative] = sha256_file(destination / relative)
    for path, digest in hashes.items():
        bound_file(ROOT, {"path": path, "sha256": digest})
    write_json(destination / "tong_kiem_chung.json", totals)
    artifacts["tong_kiem_chung.json"] = sha256_file(destination / "tong_kiem_chung.json")
    commit, dirty = get_git_info(ROOT)
    manifest = {**registered, "experiment_id": destination.name, "stage": "v31_quality_validation_dev_t01_t10",
                "git": {"commit": commit, "dirty_state": dirty},
                "access": {**registered["access"], "timestamp": datetime.now(timezone.utc).isoformat()},
                "inputs": {**registered["inputs"], "hashes": {**hashes, (
                    registration / "experiment_manifest.json").relative_to(ROOT).as_posix():
                    sha256_file(registration / "experiment_manifest.json")}},
                "artifacts": {"hashes": artifacts}}
    validate_manifest(manifest)
    write_json(destination / "experiment_manifest.json", manifest)
    verify_artifacts(destination)


def output_path(path: Path) -> Path:
    resolved = path.resolve()
    require(resolved.is_relative_to(ROOT / "outputs") and resolved != ROOT / "outputs"
            and all(p.lower() != "locked_test" for p in resolved.parts), "Chỉ dùng thư mục mới dưới outputs/")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--original-orchestrator", type=Path)
    args = parser.parse_args()
    registration = output_path(args.registration)
    if args.finalize_only:
        require(args.output is not None, "Cần thư mục đã huấn luyện")
        original = output_path(args.original_orchestrator) if args.original_orchestrator else None
        registered, plans, hashes = check_registration(registration, original)
        seal_run(registration, output_path(args.output), registered, plans, hashes)
    elif args.output is None:
        require(args.original_orchestrator is None, "Bản mã cũ chỉ dùng khi hoàn tất bản kê")
        register(registration)
    else:
        require(args.original_orchestrator is None, "Bản mã cũ chỉ dùng khi hoàn tất bản kê")
        execute(registration, output_path(args.output), args.workers)


if __name__ == "__main__":
    main()
