"""Chuẩn bị phiếu hiệu chuẩn từ các ca đã đối chiếu A/B."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_text  # noqa: E402
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.prepare_m2_semantic_review import ONTOLOGY, OUTPUT, indexed, output_path, validate_review  # noqa: E402
from scripts.run_m2_backbone_v31 import sealed_manifest  # noqa: E402

GUIDE = "docs/audit/M2_HUONG_DAN_CHAM_QUAN_HE_V2.md"
FORM = "scripts/m2_semantic_calibration_form.html"
VERSION = "v2.0-hieu-chuan"
GROUPS = {
    "CAN_CU_SU_KIEN_PHAT_HANH": 4,
    "KIEU_THUC_THE_ONTOLOGY": 4,
    "VI_TRI_DOAN_TRICH": 2,
}


def prepare(out: Path) -> None:
    pack = OUTPUT / "20261110_v1"
    compare = OUTPUT / "20261111_doi_chieu_ab_v1"
    checked = OUTPUT / "20261111_kiem_chung_ab_v1"
    manifests = {run: verify_artifacts(run) for run in (pack, compare, checked)}
    hashes: dict[str, str] = {}

    def bind(relative: str, expected: str) -> Path:
        path = bound_file(ROOT, {"path": relative, "sha256": expected})
        require(hashes.setdefault(relative, expected) == expected, "Mã băm đầu vào không nhất quán")
        return path

    for run in (pack, compare):
        relative = (run / "experiment_manifest.json").relative_to(ROOT).as_posix()
        digest = manifests[checked]["inputs"]["hashes"][relative]
        bind(relative, digest)
        if run == pack:
            require(manifests[compare]["inputs"]["hashes"][relative] == digest, "Đối chiếu lệch bộ A/B")
    for file in (checked / "experiment_manifest.json", ROOT / GUIDE, ROOT / FORM, Path(__file__).resolve()):
        bind(file.relative_to(ROOT).as_posix(), sha256_file(file))

    source_hashes = manifests[pack]["inputs"]["hashes"]
    ontology = yaml.safe_load(bind(ONTOLOGY, source_hashes[ONTOLOGY]).read_bytes())
    require(ontology["ontology_version"] == "1.1", "Sai phiên bản ontology")
    plan = read_json(pack / "thiet_ke_phieu.json")
    reviews = {slot: validate_review(compare / f"phieu_{slot}.json", plan, slot)["tra_loi"]
               for slot in ("A", "B")}
    flags = read_json(checked / "phieu_can_lam_ro_tieu_chi.json")
    requests = [*flags["can_lam_ro_tieu_chi"], *(
        {**row, "nhom_can_lam_ro": "VI_TRI_DOAN_TRICH"}
        for row in flags["can_kiem_tra_lai_vi_tri_doan_trich"]
    )]
    keys = set(indexed(requests, "ma_phieu"))
    require(keys <= set(plan["ma_phieu"]) and Counter(x["nhom_can_lam_ro"] for x in requests) == GROUPS,
            "Sai danh sách ca hiệu chuẩn")
    queue = indexed(
        pq.read_table(pack / "hang_cho_tham_dinh.parquet", filters=[("ma_phieu", "in", sorted(keys))]).to_pylist(),
        "ma_phieu",
    )
    require(set(queue) == keys, "Thiếu ca trong hàng chờ")
    bodies_path = (ACTIVE_PACKAGE / "tables/body_variants.parquet").as_posix()
    bodies = indexed(pq.read_table(bind(bodies_path, source_hashes[bodies_path])).to_pylist(), "body_variant_id")

    cases = []
    for flag in requests:
        key = flag["ma_phieu"]
        row = queue[key]
        triple = [row["ten_dau"], row["quan_he"], row["ten_cuoi"]]
        require(triple == flag["bo_ba"], "Bộ ba khác ca đã đối chiếu")
        url = urlsplit(row["url_ban_luu"])
        require(url.scheme == "https" and url.netloc == "web.archive.org", "Sai liên kết bản lưu")
        body = bodies[row["body_variant_id"]]
        relative = (ACTIVE_PACKAGE / PureWindowsPath(body["body_blob_relative_path"]).as_posix()).as_posix()
        digest = row["body_sha256"]
        require(body["body_text_sha256"] == source_hashes[relative] == digest, "Sai mã băm thân bài")
        body_text = bind(relative, digest).read_bytes().decode("utf-8")
        require("\r" not in body_text and len(body_text) == body["text_char_count"],
                "Thân bài không tương thích với vị trí văn bản trên phiếu")
        for span in row["vi_tri"]:
            s, e = span["bat_dau"], span["ket_thuc"]
            require(0 <= s < e <= len(body_text) and body_text[s:e] == span["doan_trich"]
                    and sha256_text(body_text[s:e]) == row["span_sha256"]
                    and body_text[max(0, s - 420):s] == span["truoc"] and body_text[e:e + 420] == span["sau"],
                    "Đoạn gốc hoặc ngữ cảnh khác thân bài")
        suggested = None
        if "trich_dan_vi_tri_khac" in flag:
            s, e = flag["bat_dau"], flag["ket_thuc"]
            require(0 <= s < e <= len(body_text) and body_text[s:e] == flag["trich_dan_vi_tri_khac"]
                    and flag["than_bai_sha256"] == digest and flag["url_ban_luu"] == row["url_ban_luu"],
                    "Đoạn gợi ý khác bản lưu đã kiểm")
            suggested = {"bat_dau": s, "ket_thuc": e, "doan_trich": body_text[s:e]}
        relation = ontology["relations"][row["quan_he"]]
        old = {slot: {k: reviews[slot][key][k] for k in ("nhan", "ly_do")} for slot in reviews}
        require(all(old[slot]["nhan"] == flag[f"nhan_{slot}"] for slot in reviews)
                and all(old[slot]["ly_do"] == flag.get(f"ly_do_{slot}", old[slot]["ly_do"]) for slot in reviews),
                "Lý do hoặc nhãn A/B khác đối chiếu")
        cases.append({
            **row, "bo_ba": triple, "nhom_hieu_chuan": flag["nhom_can_lam_ro"], "doc_ab": old,
            "kieu_dau_cho_phep": relation["subject"], "kieu_cuoi_cho_phep": relation["object"],
            "goi_y": suggested, "than_bai": body_text,
        })

    payload = {
        "phien_ban": VERSION, "ma_bo_phieu_goc": plan["sha256_noi_dung_phieu"],
        "sha256_huong_dan": hashes[GUIDE], "sha256_ontology": hashes[ONTOLOGY],
        "kieu_thuc_the": ontology["entity_types"], "ca": cases,
    }
    payload["ma_bo_hieu_chuan"] = content_hash(payload)
    guide = (ROOT / GUIDE).read_bytes()
    html = (ROOT / FORM).read_text(encoding="utf-8")
    require(html.count("__CALIBRATION_DATA__") == 1, "Mẫu HTML thiếu vị trí dữ liệu")
    embedded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    out.mkdir(parents=True, exist_ok=False)
    (out / "huong_dan_cham_v2.md").write_bytes(guide)
    (out / "phieu_hieu_chuan_v2.html").write_text(html.replace("__CALIBRATION_DATA__", embedded), encoding="utf-8")
    write_json(out / "bien_nhan_chuan_bi.json", {
        "trang_thai": "CHO_NGUOI_PHAN_XU", "ma_bo_hieu_chuan": payload["ma_bo_hieu_chuan"],
        "so_ca_theo_nhom": GROUPS, "ma_phieu": [case["ma_phieu"] for case in cases],
        "so_quyet_dinh_hieu_chuan": 0,
    })
    sealed_manifest(out, "m2_v31_semantic_review_calibration_preparation", {
        **manifests[pack]["inputs"], "hashes": hashes, "config_hash": hashes[GUIDE],
        "data_hash": content_hash(hashes),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", help="Thư mục kết quả mới trong outputs/m2_anchor_semantic_review")
    args = parser.parse_args()
    prepare(output_path(args.out))


if __name__ == "__main__":
    main()
