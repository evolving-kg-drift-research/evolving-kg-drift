"""Kiểm lại lượt xác thực và lập cấu hình backbone dự thảo, không huấn luyện."""
from __future__ import annotations

import argparse
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from scripts.run_m2_measurement_v2 import inspect_registration  # noqa: E402
from scripts.verify_kge_validation import verify as verify_validation  # noqa: E402

REGISTRATION = "outputs/m2_quality_validation_registration/20261104_v1"
RUN = "outputs/m2_quality_validation_v31/20261104_v1"
REPORT = "outputs/m2_quality_validation_v31_report/20261104_v2"
ARCHIVED_ORCHESTRATOR = "outputs/m2_quality_validation_recovery/20261104_v1/run_m2_quality_validation_v31_original.py"
ORIGINAL_ORCHESTRATOR = "scripts/run_m2_quality_validation_v31.py"
CANDIDATE = "configs/m2_data_3_1_candidate_v2.yaml"
MEASUREMENT = "configs/m2_measurement_v2_candidate.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục kết quả mới dưới outputs/")
    inputs: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        digest = expected if expected is not None else sha256_file(ROOT / relative)
        require(inputs.setdefault(relative, digest) == digest, f"Mã băm không nhất quán: {relative}")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    parents = {folder: verify_artifacts(ROOT / folder) for folder in (REGISTRATION, RUN, REPORT)}
    for folder, manifest in parents.items():
        bind(f"{folder}/experiment_manifest.json")
        for path, digest in manifest["inputs"]["hashes"].items():
            if folder == REGISTRATION and path == ORIGINAL_ORCHESTRATOR:
                require(parents[RUN]["inputs"]["hashes"][ARCHIVED_ORCHESTRATOR] == digest,
                        "Thiếu bản lưu mã điều phối ban đầu")
                path = ARCHIVED_ORCHESTRATOR
            bind(path, digest)
    plan = read_json(ROOT / REGISTRATION / "ke_hoach.json")
    candidate = yaml.safe_load(bind(CANDIDATE).read_bytes())
    require(all(candidate["kge"][k] == v for k, v in plan["model"].items())
            and plan["seeds"] == candidate["kge"]["seeds"] == [13, 37, 101], "Thông số không khớp")
    totals = {"tep": 0, "epoch": 0, "thu_hang": 0, "mau_am_bo_qua": 0}
    review = []
    snapshots = []
    for item in plan["ke_hoach"]:
        sid = item["snapshot"]
        folder = ROOT / RUN / sid
        child = verify_artifacts(folder)
        totals["tep"] += len(child["artifacts"]["hashes"])
        receipt = read_json(folder / "independent_verification.json")
        require(set(receipt) == set(map(str, plan["seeds"])), "Thiếu seed")
        logs = []
        for seed, check in receipt.items():
            require(check["status"] == "SAVED_VALIDATION_CHECKS_PASS"
                    and child["artifacts"]["hashes"][f"seed_{seed}/experiment_manifest.json"]
                    == check["manifest_sha256"], "Biên nhận xác thực khác bản kê")
            log = read_json(folder / f"seed_{seed}/epoch_log.json")
            require(len(log) == check["epochs_verified"] == 50, "Thiếu epoch")
            logs.append(log)
            totals["epoch"] += check["epochs_verified"]
            totals["thu_hang"] += check["ranking_rows_verified"]
            totals["mau_am_bo_qua"] += sum(row["train_diagnostics"]["skipped"] for row in log)
        report = read_json(folder / "readiness.json")
        snapshot = report["snapshot"]
        snapshots.append({k: snapshot[k] for k in (
            "snapshot_id", "cutoff", "triples", "entities", "relations", "physical_sha256",
            "snapshot_hash", "entity_map_hash", "relation_map_hash")})
        mrr = [mean(log[i]["metrics"]["MRR"] for log in logs) for i in range(50)]
        validation = [mean(log[i]["validation_loss"] for log in logs) for i in range(50)]
        review.append({"snapshot": sid, "MRR_vong_40": mrr[39], "MRR_vong_50": mrr[49],
                       "loss_xac_thuc_vong_40": validation[39], "loss_xac_thuc_vong_50": validation[49],
                       "vong_co_MRR_cao_nhat_quan_sat": max(range(50), key=mrr.__getitem__) + 1})
    require(totals == {"tep": 5130, "epoch": 1500, "thu_hang": 379500, "mau_am_bo_qua": 0},
            "Số liệu lưu không khớp phạm vi đã chạy")
    spot = {sid: verify_validation(ROOT / RUN / sid / "seed_13") for sid in ("T01", "T10")}
    _, _, measurement, checked = inspect_registration(ROOT, Path(MEASUREMENT))
    for relative, digest in checked.items():
        bind(relative, digest)
    for relative in ("src/kge/trainer.py", "src/kge/model.py", "scripts/run_m2_backbone.py",
                     "scripts/verify_kge_validation.py", Path(__file__).resolve().relative_to(ROOT).as_posix()):
        bind(relative)

    draft = {
        "trang_thai": "DỰ THẢO, CHƯA ĐĂNG KÝ THỰC THI",
        "vai_tro": "Backbone toàn snapshot phục vụ đo độ trôi",
        "nguon": candidate["release_id"], "goi": candidate["package_root"], "snapshot": snapshots,
        "model": "TransE-L2", "tham_so": plan["model"], "seeds": plan["seeds"],
        "phan_hoach": "Toàn bộ bộ ba của từng snapshot",
        "khoi_tao": "Từ đầu và độc lập cho từng tổ hợp snapshot và seed",
        "mau_am": "Thay thực thể đầu hoặc cuối, lọc bộ ba dương của cùng snapshot",
        "quy_tac_chon": "Dùng vòng 50 cố định và chung cho 30 tổ hợp",
        "lich_luu_de_xuat": "Nhật ký mọi vòng, checkpoint vòng 50 cho phép đo độ trôi",
        "xac_thuc": "Không áp dụng cho lượt toàn snapshot",
    }
    audit = {"da_kiem": totals, "kiem_tra_lai_tu_vector": spot, "cuoi_luot_xac_thuc": review,
             "trung_binh_MRR_vong_40": mean(row["MRR_vong_40"] for row in review),
             "trung_binh_MRR_vong_50": mean(row["MRR_vong_50"] for row in review),
             "dang_ky_phep_do_M2": measurement["status"],
             "dieu_kien_phep_do_con_mo": measurement["execution_blockers"]}
    require(all(math.isfinite(row["MRR_vong_50"]) for row in review), "Chỉ số không hữu hạn")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "kiem_tra_lai.json", audit)
    write_json(output / "cau_hinh_backbone_du_thao.json", draft)
    commit, dirty = get_git_info(ROOT)
    base = parents[RUN]
    manifest: dict[str, Any] = {
        **base, "experiment_id": output.name, "stage": "backbone_design_read_only_review",
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**base["inputs"], "query_hash": None, "config_hash": content_hash(draft), "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "access": {**base["access"], "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {p.name: sha256_file(p) for p in output.iterdir()}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
