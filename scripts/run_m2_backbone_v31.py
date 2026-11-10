"""Đăng ký, huấn luyện và kiểm chứng riêng mô hình nền toàn snapshot V3.1."""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.model import TransEConfig  # noqa: E402
from scripts.inspect_m2_inputs import (  # noqa: E402
    ACTIVE_PACKAGE, RELEASE_ID, encode, inspect_package, require_current_package, timestamp,
)
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from scripts.run_m2_pilot import train_replayed  # noqa: E402
from scripts.verify_m2_backbone import verify_saved_job  # noqa: E402

PREFLIGHT = "outputs/m2_preflight/20261104T014424Z_79e57c2b"
SEARCH = "outputs/m2_dimension_epoch_search/20261104_v2"
SELECTION = "outputs/m2_dimension_epoch_search_report/20261104_v1"
PROTOCOL = "configs/protocol_v1.yaml"
KGE_POLICY = "configs/kge.yaml"
CANDIDATE = "configs/m2_data_3_1_candidate_v2.yaml"
OUTPUT_ROOT = ROOT / "outputs/m2_backbone_v31"
SNAPSHOTS = [f"T{i:02d}" for i in range(1, 11)]
SEEDS = [13, 37, 101]
CODE = (
    "scripts/run_m2_backbone_v31.py", "scripts/run_m2_pilot.py", "scripts/verify_m2_backbone.py",
    "scripts/verify_m2_pilot.py", "scripts/inspect_m2_inputs.py", "scripts/prepare_kge_retrospective_t01.py",
    "src/kge/__init__.py", "src/kge/checkpoint.py", "src/kge/contract.py", "src/kge/math_utils.py",
    "src/kge/model.py", "src/kge/splits.py", "src/kge/trainer.py", "src/kg_pipeline/__init__.py",
    "src/kg_pipeline/experiment_manifest.py", "src/kg_pipeline/hashing.py", "src/kg_pipeline/storage.py",
    "configs/schemas/experiment_manifest.schema.yaml",
)


def bind_all(hashes: dict[str, str], root: Path = ROOT) -> None:
    for path, digest in hashes.items():
        bound_file(root, {"path": path, "sha256": digest})


def inspect_inputs() -> tuple[dict[str, SnapshotDataset], dict, dict, dict]:
    package = require_current_package(ROOT, ACTIVE_PACKAGE)
    preflight = verify_artifacts(ROOT / PREFLIGHT)
    hashes = dict(preflight["inputs"]["hashes"])
    bind_all(hashes)
    datasets, observed = inspect_package(package)
    observed["snapshots"] = json.loads(encode(observed["snapshots"]))
    expected = read_json(ROOT / PREFLIGHT / "report.json")
    require(list(datasets) == SNAPSHOTS and observed["snapshots"] == expected["snapshots"],
            "Snapshot hoặc ánh xạ khác bản kê kiểm tra đầu vào")
    release = read_json(package / "release_manifest.json")
    inventory = {row["path"]: row["sha256"] for row in release["artifacts"]}
    require(release["release_id"] == RELEASE_ID and release["snapshot_count"] == len(SNAPSHOTS),
            "Sai bản phát hành")
    for relative, digest in observed["input_hashes"].items():
        require(hashes[(ACTIVE_PACKAGE / relative).as_posix()] == inventory[relative] == digest,
                f"Tệp V3.1 khác bản kê phát hành hoặc kiểm tra đầu vào: {relative}")
    config = yaml.safe_load((package / "config/downstream_transe_config.yaml").read_bytes())
    temporal = {}
    for spec in config["snapshots"]:
        relative = (ACTIVE_PACKAGE / spec["parquet_path"]).as_posix()
        path = bound_file(ROOT, {"path": relative, "sha256": hashes[relative]})
        observed_at = [timestamp(value) for value in pq.read_table(
            path, columns=["evidence_observed_at"]
        )["evidence_observed_at"].to_pylist()]
        sid = spec["snapshot_id"]
        cutoff = timestamp(spec["cutoff"])
        require(len(observed_at) == len(datasets[sid].triples) and max(observed_at) <= cutoff,
                f"{sid}: có bộ ba thiếu mốc quan sát hoặc dùng bằng chứng sau cutoff")
        temporal[sid] = {"so_dong": len(observed_at), "muon_nhat": max(observed_at).isoformat(),
                         "cutoff": cutoff.isoformat()}
    return datasets, observed, temporal, hashes


def mappings_for(datasets: dict[str, SnapshotDataset]) -> dict:
    return {sid: {"entities": ds.get_entity_mapping(), "relations": ds.get_relation_mapping()}
            for sid, ds in datasets.items()}


def model_config(model: dict, seed: int) -> TransEConfig:
    return TransEConfig(**model, seed=seed)


def sealed_manifest(out: Path, stage: str, inputs: dict, *, elapsed: float | None = None,
                    git: dict | None = None) -> dict[str, Any]:
    if git is None:
        commit, dirty = get_git_info(ROOT)
        git = {"commit": commit, "dirty_state": dirty}
    manifest = {
        "experiment_id": out.name, "protocol_version": "v1-draft", "stage": stage,
        "scientific_certification": False, "git": git, "seed": None, "inputs": inputs,
        "environment": {"python": platform.python_version(), "os": platform.platform(), "pyarrow": pa.__version__},
        "hardware": {"cpu": platform.processor(), "ram": None, "elapsed_seconds": elapsed},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha256_file(p)
                                for p in out.rglob("*") if p.is_file()}},
    }
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    return verify_artifacts(out)


def register(out: Path) -> None:
    datasets, observed, temporal, data_hashes = inspect_inputs()
    source = verify_artifacts(ROOT / SEARCH)
    receipt = verify_artifacts(ROOT / SELECTION)
    design = read_json(ROOT / SEARCH / "thiet_ke_tim_kiem.json")
    result = read_json(ROOT / SEARCH / "ket_qua_tim_kiem.json")
    selected = read_json(ROOT / SELECTION / "kiem_tra_chon_cau_hinh.json")
    best = selected["chon"]
    require(source["stage"] == "m2_dimension_epoch_search_dev"
            and receipt["stage"] == "m2_dimension_epoch_search_report"
            and content_hash(design) == source["inputs"]["config_hash"] == receipt["inputs"]["config_hash"]
            and receipt["inputs"]["hashes"][f"{SEARCH}/experiment_manifest.json"]
            == sha256_file(ROOT / SEARCH / "experiment_manifest.json")
            and all(source["inputs"]["hashes"][(ACTIVE_PACKAGE / p).as_posix()] == h
                    for p, h in observed["input_hashes"].items())
            and source["inputs"]["hashes"][(ACTIVE_PACKAGE / "release_manifest.json").as_posix()]
            == data_hashes[(ACTIVE_PACKAGE / "release_manifest.json").as_posix()],
            "Phép chọn cấu hình và dữ liệu không cùng nguồn")
    grid = result["du_lieu_xep_hang"]
    require(best == result["tot_nhat_trong_luoi"]
            == min(grid, key=lambda row: (-row["MRR"], row["chieu"], row["epoch"]))
            and {(row["chieu"], row["epoch"]) for row in grid}
            == {(d, e) for d in design["chieu"] for e in design["epoch_cham"]}
            and len(grid) == len(design["chieu"]) * len(design["epoch_cham"])
            and selected["so_dong_thu_hang_tinh_lai"] == result["so_dong_thu_hang_kiem_chung"],
            "Thiếu kết quả kiểm chứng quy tắc chọn")
    policy = yaml.safe_load((ROOT / KGE_POLICY).read_bytes())
    protocol = yaml.safe_load((ROOT / PROTOCOL).read_bytes())["kge"]
    candidate_design = yaml.safe_load((ROOT / CANDIDATE).read_bytes())
    candidate = candidate_design["kge"]
    fixed = design["tham_so_con_lai"]
    require(policy["model"] == protocol["model"] == candidate["model"] == "TransE"
            and policy["norm"] == protocol["norm"] == fixed["norm"] == 2
            and policy["seeds"] == protocol["seeds"] == candidate["seeds"] == design["seeds"] == SEEDS
            and policy["dimension_search_space"] == design["chieu"]
            and design["snapshot"] == SNAPSHOTS
            and all(candidate[key] == value for key, value in fixed.items())
            and (best["chieu"], best["epoch"]) == (64, 85),
            "Cấu hình vượt phạm vi lượt chạy đã yêu cầu")
    model = {**fixed, "dimension": best["chieu"], "epochs": best["epoch"]}
    plan = {
        "phien_ban": "m2_backbone_v31_dev_v1", "nguon": RELEASE_ID, "pham_vi": "Phát triển",
        "snapshot": SNAPSHOTS, "seeds": SEEDS, "model": model, "phuong_phap": "TransE-L2",
        "ty_le_xac_thuc": 0.0, "so_lan_moi_to_hop": 2, "ket_qua_chon": best,
        "ly_do": {
            "mo_hinh_va_seed": "Theo giao thức M2. Ba lần khởi tạo cố định cho so sánh theo seed và nhiễu cùng snapshot.",
            "so_chieu_va_epoch": design["chon"],
            "tham_so_con_lai": "Giữ đúng cấu hình cố định của lượt dò để áp dụng kết quả chọn trong cùng điều kiện.",
            "toan_snapshot": "Mỗi đồ thị đầy đủ tại cutoff là đầu vào biểu diễn cho phép đo độ trôi.",
            "mau_am": "Đổi thực thể đầu hoặc cuối, lọc mọi bộ ba dương trong cùng snapshot.",
            "batch_size": "Trường tương thích của cấu hình. Bộ tối ưu cập nhật theo từng bộ ba.",
        },
        "tieu_chi": [
            "Khớp mã băm đầu vào, đủ 10 cutoff và mọi mốc quan sát trong Parquet không vượt cutoff.",
            "Đủ 30 tổ hợp, mỗi lượt đủ 85 epoch, mỗi bộ ba có một mẫu âm hợp lệ trong từng epoch.",
            "Loss hữu hạn, đúng mẫu số; đủ vector hữu hạn đúng chiều và khớp ánh xạ canonical.",
            "Hai lần khởi tạo lại cùng seed có checkpoint trùng byte.",
        ],
        "yeu_cau": "Phải xác định được tính khoa học và cơ sở và bằng chứng của từng bước kể cả cấu hình chọn "
                    "cũng phải có nguyên nhân rõ ràng. Thực hiện và thêm vào báo cáo",
    }
    hashes = dict(data_hashes)
    for path in (PROTOCOL, KGE_POLICY, CANDIDATE):
        hashes[path] = source["inputs"]["hashes"][path]
    lock_path = "data/manifests/sources.lock.json"
    hashes[lock_path] = candidate_design["bindings"][lock_path]
    for path in (PREFLIGHT, SEARCH, SELECTION):
        relative = f"{path}/experiment_manifest.json"
        hashes[relative] = sha256_file(ROOT / relative)
    code_hashes = {p: sha256_file(ROOT / p) for p in CODE}
    require(all(source["inputs"]["hashes"].get(p, h) == h for p, h in code_hashes.items()),
            "Mã dùng chung khác lượt dò cấu hình")
    hashes.update(code_hashes)
    bind_all(hashes)
    mappings = mappings_for(datasets)
    inputs = {
        "hashes": hashes, "data_hashes": data_hashes, "code_hashes": code_hashes,
        "data_hash": content_hash(data_hashes), "query_hash": None, "config_hash": content_hash(plan),
        "snapshot_hash": content_hash({sid: ds.snapshot_hash for sid, ds in datasets.items()}),
        "entity_map_hash": content_hash({sid: row["entities"] for sid, row in mappings.items()}),
        "relation_map_hash": content_hash({sid: row["relations"] for sid, row in mappings.items()}),
    }
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "dang_ky.json", plan)
    write_json(out / "dau_vao.json", {"snapshot": observed["snapshots"], "moc_quan_sat": temporal})
    write_json(out / "anh_xa.json", mappings)
    sealed_manifest(out, "m2_backbone_v31_dev_registration", inputs)


def verify_registration(registration: Path, *, replay_from: Path | None = None) -> tuple[dict, dict, dict]:
    manifest = verify_artifacts(registration)
    inputs = manifest["inputs"]
    require(manifest["stage"] == "m2_backbone_v31_dev_registration"
            and manifest["access"]["state"] == "dev" and manifest["scientific_certification"] is False,
            "Cần đăng ký đúng phạm vi phát triển")
    if replay_from is None:
        bind_all(inputs["hashes"])
    else:
        bind_all({p: h for p, h in inputs["hashes"].items() if p not in inputs["code_hashes"]})
        bind_all(inputs["code_hashes"], replay_from)
    datasets, observed, temporal, data_hashes = inspect_inputs()
    plan = read_json(registration / "dang_ky.json")
    require(content_hash(plan) == inputs["config_hash"] and data_hashes == inputs["data_hashes"]
            and content_hash(data_hashes) == inputs["data_hash"]
            and plan["snapshot"] == SNAPSHOTS and plan["seeds"] == SEEDS
            and plan["nguon"] == RELEASE_ID and plan["ty_le_xac_thuc"] == 0.0 and plan["so_lan_moi_to_hop"] == 2
            and read_json(registration / "anh_xa.json") == mappings_for(datasets)
            and read_json(registration / "dau_vao.json") == {
                "snapshot": observed["snapshots"], "moc_quan_sat": temporal,
            }, "Đăng ký hoặc dữ liệu hiện tại không nhất quán")
    return manifest, plan, datasets


def train_job(dataset: SnapshotDataset, config: TransEConfig, out: Path, git: dict) -> dict:
    start = time.perf_counter()
    cp, row = train_replayed(dataset, config, out / dataset.snapshot_id, git)
    losses = cp.training_metrics["epoch_losses"]
    return {
        **row, "path": f"{dataset.snapshot_id}/seed_{config.seed}_repeat_1.json",
        "snapshot_hash": dataset.snapshot_hash, "num_epochs": config.epochs,
        "first_loss": losses[0], "final_loss": losses[-1], "triples": len(dataset.triples),
        "entities": len(dataset.entities), "relations": len(dataset.relations),
        "giay_huan_luyen_va_luu": time.perf_counter() - start,
    }


def execute(registration: Path, out: Path, workers: int) -> None:
    start = time.perf_counter()
    registered, plan, datasets = verify_registration(registration)
    require(workers > 0, "Cần ít nhất một tiến trình")
    commit, dirty = get_git_info(ROOT)
    git = {"commit": commit, "dirty_state": dirty}
    inputs = registered["inputs"]
    out.mkdir(parents=True, exist_ok=False)
    for relative, digest in inputs["code_hashes"].items():
        source = bound_file(ROOT, {"path": relative, "sha256": digest})
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(source.read_bytes())
    write_json(out / "dang_ky.json", plan)
    write_json(out / "anh_xa.json", mappings_for(datasets))
    write_json(out / "tham_so_theo_seed.json", {str(s): asdict(model_config(plan["model"], s)) for s in SEEDS})
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(train_job, datasets[sid], model_config(plan["model"], seed), out, git)
                   for sid in reversed(SNAPSHOTS) for seed in SEEDS]
        results = []
        for future in as_completed(futures):
            row = future.result()
            results.append(row)
            print(f"{len(results)}/30 {row['snapshot_id']} seed={row['seed']} exact replay OK", flush=True)
    write_json(out / "lan_huan_luyen.json", sorted(results, key=lambda row: (row["snapshot_id"], row["seed"])))
    bind_all(inputs["hashes"])
    bind_all(inputs["code_hashes"], out / "code")
    relative = (registration / "experiment_manifest.json").relative_to(ROOT).as_posix()
    hashes = {**inputs["hashes"], relative: sha256_file(ROOT / relative)}
    sealed_manifest(out, "m2_backbone_v31_dev_training", {**inputs, "hashes": hashes, "registration": relative},
                    elapsed=time.perf_counter() - start, git=git)


def verify(run: Path, out: Path) -> None:
    manifest = verify_artifacts(run)
    require(manifest["stage"] == "m2_backbone_v31_dev_training"
            and manifest["access"]["state"] == "dev" and manifest["scientific_certification"] is False,
            "Sai phạm vi bản kê lượt huấn luyện")
    inputs = manifest["inputs"]
    relative = inputs["registration"]
    path = bound_file(ROOT, {"path": relative, "sha256": inputs["hashes"][relative]})
    registered, plan, datasets = verify_registration(path.parent, replay_from=run / "code")
    registered_inputs = registered["inputs"]
    expected_inputs = {**registered_inputs, "registration": relative,
                       "hashes": {**registered_inputs["hashes"], relative: inputs["hashes"][relative]}}
    mappings = read_json(run / "anh_xa.json")
    configs = read_json(run / "tham_so_theo_seed.json")
    rows = read_json(run / "lan_huan_luyen.json")
    require(inputs == expected_inputs and plan == read_json(run / "dang_ky.json")
            and mappings == mappings_for(datasets)
            and configs == {str(s): asdict(model_config(plan["model"], s)) for s in SEEDS}
            and [(row["snapshot_id"], row["seed"]) for row in rows]
            == [(sid, seed) for sid in SNAPSHOTS for seed in SEEDS],
            "Thiếu tổ hợp hoặc cấu hình đã đăng ký không khớp")
    checked, logs = [], {}
    for row in rows:
        sid, seed = row["snapshot_id"], row["seed"]
        require(row["path"] == f"{sid}/seed_{seed}_repeat_1.json", "Sai đường dẫn checkpoint")
        details = verify_saved_job(run, datasets[sid], configs[str(seed)], row, mappings[sid], manifest["git"])
        cp = KGECheckpoint.load(run / row["path"])
        metrics = cp.training_metrics
        diagnostics = metrics["epoch_diagnostics"]
        losses = metrics["epoch_losses"]
        count = len(datasets[sid].triples)
        require(metrics["validation_status"] == "NOT_APPLICABLE_FULL_SNAPSHOT"
                and metrics["validation_counts"] == [] and metrics["split"] is None
                and metrics["split_hash"] is None and len(diagnostics) == len(losses),
                "Nhật ký không đúng phạm vi huấn luyện toàn snapshot")
        for loss, diag in zip(losses, diagnostics, strict=True):
            require(diag["positives"] == diag["usable_negatives"] == count and diag["skipped"] == 0
                    and 0 <= diag["margin_violations"] <= count and diag["loss_sum"] >= 0
                    and diag["loss_definition"] == "online_margin_loss_per_positive_v1"
                    and math.isclose(diag["loss_sum"] / count, loss, rel_tol=1e-12),
                    f"{sid} seed {seed}: số mẫu âm hoặc công thức loss không khớp")
        logs[f"{sid}/{seed}"] = losses
        checked.append({**details, "so_epoch": len(losses), "bo_ba_moi_epoch": count,
                        "so_mau_am_hop_le": sum(d["usable_negatives"] for d in diagnostics),
                        "so_mau_am_bo_qua": sum(d["skipped"] for d in diagnostics)})
    result = {
        "trang_thai": "ĐẠT kiểm chứng kỹ thuật mô hình nền trong phạm vi phát triển",
        "so_to_hop": len(checked), "so_cap_khop_byte": len(checked), "so_lan_huan_luyen": 2 * len(checked),
        "so_epoch_mot_luot": sum(row["so_epoch"] for row in checked),
        "so_mau_am_hop_le_mot_luot": sum(row["so_mau_am_hop_le"] for row in checked),
        "so_mau_am_bo_qua_mot_luot": sum(row["so_mau_am_bo_qua"] for row in checked),
        "so_ma_bam_dau_vao": len(inputs["hashes"]), "so_ma_bam_tep_ket_qua": len(manifest["artifacts"]["hashes"]),
        "chi_tiet": checked,
    }
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "kiem_chung.json", result)
    write_json(out / "loss_theo_epoch.json", logs)
    relative = (run / "experiment_manifest.json").relative_to(ROOT).as_posix()
    code = Path(__file__).resolve().relative_to(ROOT).as_posix()
    verifier = "scripts/verify_m2_backbone.py"
    hashes = {relative: sha256_file(ROOT / relative), code: sha256_file(ROOT / code),
              verifier: sha256_file(ROOT / verifier)}
    sealed_manifest(out, "m2_backbone_v31_dev_verification", {**inputs, "hashes": hashes})


def output_path(path: str) -> Path:
    resolved = Path(path).resolve()
    require(resolved.is_relative_to(OUTPUT_ROOT.resolve()) and resolved != OUTPUT_ROOT.resolve()
            and "locked_test" not in {part.lower() for part in resolved.parts}, "Sai thư mục kết quả")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("register", "train", "verify"))
    parser.add_argument("source", type=output_path)
    parser.add_argument("destination", type=output_path, nargs="?")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.action == "register":
        require(args.destination is None, "Đăng ký chỉ cần thư mục kết quả mới")
        register(args.source)
    else:
        require(args.destination is not None and not args.destination.exists(), "Cần thư mục kết quả mới")
        if args.action == "train":
            execute(args.source, args.destination, args.workers)
        else:
            verify(args.source, args.destination)


if __name__ == "__main__":
    main()
