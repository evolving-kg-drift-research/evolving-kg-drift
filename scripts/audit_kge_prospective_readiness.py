"""Đếm độ bao phủ lịch sử và tính kịch bản cỡ mẫu, không đọc điểm mô hình."""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

import pyarrow.parquet as pq
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    COLUMNS, FEASIBILITY, RELEASE, ROOT, bound_file, content_hash, get_git_info, read_json,
    require, sha256_file, validate_manifest, verify_artifacts, write_json,
)
from kg_pipeline.contract_authority import audit_machine_contract  # noqa: E402

DESIGN = "outputs/kge_retrospective_t01_candidate/20261104_t01_v2"
SOURCE_PROPOSAL = "outputs/kge_independent_source_proposal/20261104_v1"
SOURCE_IDS = ("vnexpress_sohoa", "tuoitre_congnghe")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục kết quả mới dưới outputs/")
    hashes: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        digest = expected if expected is not None else sha256_file(ROOT / relative)
        require(hashes.setdefault(relative, digest) == digest, f"Mã băm không nhất quán: {relative}")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    def manifest(folder: str) -> dict:
        result = verify_artifacts(ROOT / folder)
        bind(f"{folder}/experiment_manifest.json")
        return result

    prior = manifest(FEASIBILITY)
    design_manifest = manifest(DESIGN)
    proposal = manifest(SOURCE_PROPOSAL)
    bind(f"{SOURCE_PROPOSAL}/de_xuat_nguon.json", proposal["artifacts"]["hashes"]["de_xuat_nguon.json"])
    design = read_json(bind(f"{DESIGN}/design.json", design_manifest["artifacts"]["hashes"]["design.json"]))
    train_path = design["baseline"]["training_split"]
    train = read_json(bind(train_path, design_manifest["inputs"]["hashes"][train_path]))["train"]
    entities = {e for h, _, t in train for e in (h, t)}
    relations = {r for _, r, _ in train}
    require(set(design["candidates"]) == entities and len(train) == 101, "Tập huấn luyện không khớp")
    release_path = f"{RELEASE}/release_manifest.json"
    release = read_json(bind(release_path, prior["inputs"]["hashes"][release_path]))
    release_hashes = {item["path"]: item["sha256"] for item in release["artifacts"]}

    def parquet(relative: str, columns: list[str]) -> list[dict]:
        return pq.read_table(bind(f"{RELEASE}/{relative}", release_hashes[relative]), columns=columns).to_pylist()

    retrievals = parquet("tables/retrievals.parquet", ["retrieval_id", "source_id"])
    sources_by_retrieval = {row["retrieval_id"]: row["source_id"] for row in retrievals}
    require(len(sources_by_retrieval) == len(retrievals), "Mã lượt thu bị trùng")
    memberships = parquet("tables/document_memberships.parquet", ["body_variant_id", "retrieval_ids_json"])
    sources_by_body: dict[str, set[str]] = defaultdict(set)
    for row in memberships:
        for retrieval_id in json.loads(row["retrieval_ids_json"]):
            require(retrieval_id in sources_by_retrieval, "Liên kết lượt thu bị thiếu")
            source = sources_by_retrieval[retrieval_id]
            if source is not None:
                sources_by_body[row["body_variant_id"]].add(source)

    first: dict[tuple[str, str, str], tuple[int, str]] = {}
    triple_cols = COLUMNS[:3]
    for index in range(1, 11):
        relative = f"snapshots/snapshot_T{index:02d}_canonical.parquet"
        require(release_hashes[relative] == prior["inputs"]["hashes"][f"{RELEASE}/{relative}"],
                f"Snapshot khác bản đã kiểm kê: {relative}")
        for row in parquet(relative, [*triple_cols, "source_id"]):
            triple = row[triple_cols[0]], row[triple_cols[1]], row[triple_cols[2]]
            first.setdefault(triple, (index, row["source_id"]))
    coverage: dict[str, Counter] = defaultdict(Counter)
    eligible_bodies: dict[str, set[str]] = defaultdict(set)
    for (h, r, t), (index, body) in first.items():
        labels = sources_by_body[body]
        source = next(iter(labels)) if len(labels) == 1 else "khong_xac_dinh_duy_nhat"
        if index == 1:
            coverage[source]["bo_ba_T01"] += 1
        else:
            coverage[source]["bo_ba_sau_T01"] += 1
            if h in entities and t in entities and r in relations:
                coverage[source]["bo_ba_du_dinh_danh_sau_T01"] += 1
                eligible_bodies[source].add(body)
    require(len(first) == 1205 and sum(c["bo_ba_du_dinh_danh_sau_T01"] for c in coverage.values()) == 26,
            "Độ bao phủ lịch sử không khớp lần rà soát trước")
    source_counts = {
        source: {**{key: coverage[source][key] for key in (
            "bo_ba_T01", "bo_ba_sau_T01", "bo_ba_du_dinh_danh_sau_T01")},
                 "so_ban_noi_dung_dai_dien_cua_nhom_du_dinh_danh": len(eligible_bodies[source])}
        for source in sorted(set(SOURCE_IDS) | set(coverage))
    }

    schema = audit_machine_contract(ROOT)
    mismatches = sum(bool(row["missing_in_pyarrow"] or row["undeclared_in_pyarrow"]
                          or row["missing_in_dataclass"]) for row in schema["tables"])
    protocol = yaml.safe_load(bind("configs/protocol_v1.yaml").read_bytes())
    for path in ("config/schema.yaml", "config/sources.yaml", "docs/data_pipeline_spec.md",
                 "src/kg_pipeline/contract_authority.py", "docs/gates_and_freeze.md",
                 Path(__file__).resolve().relative_to(ROOT).as_posix()):
        bind(path)

    gap = 0.05
    quantile = NormalDist().inv_cdf(0.975)
    scenarios = [
        {"do_lech_chuan_gia_dinh": deviation,
         "so_nhom_cho_nua_do_rong_0_05": math.ceil((quantile * deviation / gap) ** 2),
         "so_nhom_cho_luc_kiem_dinh_80_phan_tram_o_muc_chenh_0_05":
             math.ceil(((quantile + NormalDist().inv_cdf(0.8)) * deviation / gap) ** 2)}
        for deviation in (0.10, 0.15, 0.20, 0.30, 0.40)
    ]
    result = {
        "vai_tro": "Phân tích khả thi trước khi thu thập, không dùng điểm mô hình",
        "do_bao_phu_lich_su_theo_nguon": source_counts,
        "hop_dong_du_lieu_M1": {"trang_thai": schema["status"],
                               "so_bang_lech_truong": mismatches, "so_bang": len(schema["tables"]),
                               "trang_thai_kieu_du_lieu": schema["physical_contract_status"]},
        "co_ban_ke_W7": (ROOT / "data/manifests/w7_freeze.yaml").is_file(),
        "kich_ban_co_mau": {"chenh_lech_du_thao": gap, "muc_tin_cay_minh_hoa": 0.95,
                           "luc_kiem_dinh_minh_hoa": 0.8, "gia_dinh": "Nhóm độc lập, trọng số bằng nhau",
                           "bang": scenarios},
    }
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "phan_tich_kha_thi.json"
    write_json(result_path, result)
    commit, dirty = get_git_info(ROOT)
    receipt = {
        "experiment_id": output.name, "protocol_version": protocol["protocol_version"], "seed": None,
        "stage": "prospective_test_readiness_analysis", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**design_manifest["inputs"], "hashes": hashes, "query_hash": None,
                   "config_hash": content_hash(result["kich_ban_co_mau"])},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {result_path.name: sha256_file(result_path)}},
    }
    validate_manifest(receipt)
    write_json(output / "experiment_manifest.json", receipt)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
