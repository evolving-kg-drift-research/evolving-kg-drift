"""Diễn tập nội bộ bằng RSS, bài viết và vai trò mô phỏng."""
from __future__ import annotations

import argparse
import hashlib
import platform
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require,
    sha256_file, timestamp, validate_manifest, verify_artifacts, write_json,
)

SOURCE = "outputs/kge_independent_source_proposal/20261104_v1"
ANALYSIS = "outputs/kge_prospective_readiness/20261104_v1"
PILOT_DESIGN = "outputs/kge_retrospective_t01_candidate/20261104_t01_v2"
START = "2026-11-09T00:00:00+07:00"
END = "2026-12-07T00:00:00+07:00"
RSS = """<rss version="2.0"><channel>
<item><link>https://fixture.invalid/bai-1.html?utm_source=rss</link></item>
<item><link>https://fixture.invalid/bai-1.html</link></item>
<item><link>https://fixture.invalid/bai-2.html</link></item>
<item><link>https://fixture.invalid/bai-3.html</link></item>
<item><link>https://fixture.invalid/bai-4.html</link></item>
</channel></rss>"""


def rehearse() -> dict:
    start, end = timestamp(START), timestamp(END)
    slots = [start + timedelta(hours=i * 6) for i in range(112)]
    require(slots[-1] + timedelta(hours=6) == end, "Sai cửa sổ RSS")
    journal = [
        {"moc": slot.isoformat(), "ket_qua": "loi_gia_lap" if i == 1 else "da_ghi",
         "so_muc": 5 if i == 0 else 0}
        for i, slot in enumerate(slots)
    ]
    links = [urlsplit(item.text or "") for item in ElementTree.fromstring(RSS).findall("./channel/item/link")]
    require(all(url.hostname == "fixture.invalid" for url in links), "URL mô phỏng nằm ngoài phạm vi")
    ids = [(url.hostname, url.path) for url in links]
    require(len(ids) == 5 and len(set(ids)) == 4, "Gom URL mô phỏng không khớp")
    require(sum(row["ket_qua"] == "loi_gia_lap" for row in journal) == 1, "Thiếu dấu vết lượt lỗi")

    observations = [
        ("ngay_tai_moc_mo", start, "trong_cua_so"),
        ("truoc_moc_mo", start - timedelta(seconds=1), "ngoai_cua_so"),
        ("truoc_moc_dong", end - timedelta(seconds=1), "trong_cua_so"),
        ("ngay_tai_moc_dong", end, "ngoai_cua_so"),
        ("thieu_bang_chung_thoi_gian", None, "cach_ly"),
    ]
    for name, observed_at, expected in observations:
        actual = ("cach_ly" if observed_at is None else
                  "trong_cua_so" if start <= observed_at < end else "ngoai_cua_so")
        require(actual == expected, f"Sai phân loại: {name}")

    # Các chuỗi và quyết định gần trùng dưới đây chỉ là tình huống mô phỏng.
    versions = [
        ("bai-1", "v1", None, "THU_MO_PHONG_RIENG"),
        ("bai-2", "v1", None, "THU_MO_PHONG_RIENG"),
        ("bai-1", "v2", ("bai-1", "v1"), "THU_MO_PHONG_RIENG + bằng chứng mới"),
        ("bai-3", "v1", None, "Bản gần trùng chờ người quản lý"),
        ("bai-4", "v1", None, "Đã gom theo quyết định giả lập của người quản lý"),
    ]
    recorded: dict[tuple[str, str], str] = {}
    for article, version, predecessor, text in versions:
        key = (article, version)
        require(key not in recorded and (predecessor is None or predecessor in recorded),
                "Trùng bản ghi hoặc thiếu phiên bản trước")
        recorded[key] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    require(recorded["bai-1", "v1"] == recorded["bai-2", "v1"], "Nhóm nội dung trùng không khớp")
    require(recorded["bai-1", "v2"] != recorded["bai-1", "v1"], "Bản sửa đổi không được giữ riêng")
    near_decisions = {"bai-3": "cho_xem_xet", "bai-4": "gom_voi_bai_1"}
    releasable = {key for key in recorded if near_decisions.get(key[0]) != "cho_xem_xet"}
    require(("bai-3", "v1") not in releasable and len(releasable) == 4, "Ứng viên chờ xử lý đã lọt qua")

    def view(role: str, approved: bool) -> dict:
        if role == "phat_trien":
            return {"so_phien_ban": len(recorded), "so_ung_vien_cho_xem_xet": 1}
        if role == "quan_ly":
            return {"du_lieu_mo_phong": versions}
        if role == "cham_diem" and approved:
            return {"ban_ke_mo_phong": sorted(releasable)}
        raise PermissionError("Vai trò chưa đủ điều kiện")

    require(set(view("phat_trien", False)) == {"so_phien_ban", "so_ung_vien_cho_xem_xet"}
            and "THU_MO_PHONG_RIENG" not in str(view("phat_trien", True)),
            "Thông tin giữ riêng xuất hiện ở phần bàn giao phát triển")
    require(len(view("quan_ly", False)["du_lieu_mo_phong"]) == 5
            and len(view("cham_diem", True)["ban_ke_mo_phong"]) == 4,
            "Bàn giao mô phỏng thiếu dữ liệu")
    for role, approved in (("cham_diem", False), ("khong_xac_dinh", True)):
        try:
            view(role, approved)
        except PermissionError:
            continue
        raise ValueError("Vai trò ngoài phạm vi được mở dữ liệu")

    for count, expected in ((199, 1), (200, 0), (201, 0)):
        require(int(count < 200) == expected, "Sai kiểm tra trần mô phỏng")
    return {
        "nguon": "RSS và tình huống hoàn toàn mô phỏng",
        "nhat_ky": dict(Counter(row["ket_qua"] for row in journal)),
        "so_muc_RSS_mo_phong": len(ids),
        "so_URL_phan_biet_mo_phong": len(set(ids)),
        "thu_moc_thoi_gian": [name for name, _, _ in observations],
        "thu_trung_lap": ["URL lặp", "nội dung trùng", "bản sửa đổi", "gần trùng chờ xem xét",
                          "gần trùng có quyết định mô phỏng"],
        "thu_tran_URL": [199, 200, 201],
        "thu_phan_vai": ["phát triển chỉ thấy số đếm", "quản lý thấy bản mô phỏng",
                         "chấm chưa có phê duyệt bị từ chối", "chấm đã có phê duyệt mô phỏng nhận bản kê",
                         "vai trò lạ bị từ chối"],
        "trang_thai": "Các kiểm tra mô phỏng đạt",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    out = parser.parse_args().output.resolve()
    require(out.is_relative_to(ROOT / "outputs") and out != ROOT / "outputs"
            and not out.exists() and all(part.lower() != "locked_test" for part in out.parts),
            "Cần thư mục mới dưới outputs/")
    inputs: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        digest = expected if expected is not None else sha256_file(ROOT / relative)
        inputs[relative] = digest
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    manifests = {folder: verify_artifacts(ROOT / folder) for folder in (SOURCE, ANALYSIS, PILOT_DESIGN)}
    for folder in manifests:
        bind(f"{folder}/experiment_manifest.json")
    proposal = read_json(bind(f"{SOURCE}/de_xuat_nguon.json",
                              manifests[SOURCE]["artifacts"]["hashes"]["de_xuat_nguon.json"]))
    bind(f"{ANALYSIS}/phan_tich_kha_thi.json",
         manifests[ANALYSIS]["artifacts"]["hashes"]["phan_tich_kha_thi.json"])
    pilot = manifests[PILOT_DESIGN]
    design = read_json(bind(f"{PILOT_DESIGN}/design.json", pilot["artifacts"]["hashes"]["design.json"]))
    train = design["baseline"]["training_split"]
    bind(train, pilot["inputs"]["hashes"][train])
    for item in design["model"]["checkpoints"]:
        bind(item["path"], item["sha256"])
        bind(item["sidecar"], pilot["inputs"]["hashes"][item["sidecar"]])
    for relative in ("configs/protocol_v1.yaml", "config/sources.yaml", "docs/data_pipeline_spec.md",
                     "docs/gates_and_freeze.md", Path(__file__).resolve().relative_to(ROOT).as_posix()):
        bind(relative)

    draft = {
        "trang_thai": "DỰ THẢO CHƯA ĐĂNG KÝ",
        "muc_dich": "Đánh giá khả thi cho kiểm thử dự đoán liên kết tiến cứu",
        "nguon": proposal["ma_nguon"], "RSS": proposal["kenh_phat_hien"],
        "moc_du_thao": {"mo": START, "dong_khong_bao_gom": END, "gio_doc_RSS": [0, 6, 12, 18],
                        "tran_URL_bai": 200},
        "mo_hinh": design["model"], "doi_chung": design["baseline"],
        "chi_so_chinh_du_thao": "Chênh lệch MRR ghép cặp, tổng hợp trên khóa truy vấn",
        "phan_nhom_du_thao": "Nhóm bằng chứng, sự kiện và khóa chung được xử lý trước khi mở điểm",
        "giu_rieng_du_thao": "Quản lý dữ liệu độc lập, bản gốc chỉ bổ sung, nhật ký truy cập, "
                             "bàn giao có mã băm, nhóm phát triển nhận số đếm",
        "xu_ly_thieu_mau": "Báo cáo khả thi, xem xét thiết kế tiếp theo theo hồ sơ riêng",
        "can_chot_truoc_trien_khai": [
            "Người quản lý và kiểm tra quyền truy cập thật",
            "Điều kiện M1 áp dụng và kiểm tra truy cập nguồn",
            "Ngày mở chính thức, chính sách gián đoạn và phạm vi thu",
            "Quy tắc gần trùng, mốc quan sát và ánh xạ tại cutoff",
            "Mục tiêu độ chính xác hoặc lực kiểm định, số nhóm cần thiết và phạm vi định danh chưa thấy",
            "Điều kiện đăng ký, bàn giao và mở chấm",
        ],
    }
    checks = rehearse()
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "dang_ky_du_thao.json", draft)
    write_json(out / "ket_qua_dien_tap.json", checks)
    commit, dirty = get_git_info(ROOT)
    manifest = {
        "experiment_id": out.name, "protocol_version": pilot["protocol_version"], "seed": None,
        "stage": "prospective_registration_rehearsal", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**pilot["inputs"], "query_hash": None, "config_hash": content_hash(draft), "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {path.name: sha256_file(path) for path in out.iterdir()}},
    }
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    verify_artifacts(out)


if __name__ == "__main__":
    main()
