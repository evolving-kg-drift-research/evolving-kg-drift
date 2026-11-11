"""Đối chiếu phiếu hiệu chuẩn đã nộp với gói M2 V3.1 đã phát."""
from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_text  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, json_bytes, read_json, require, sha256_file, verify_artifacts,
)
from scripts.prepare_m2_semantic_review import LABELS, indexed, output_path, review_path  # noqa: E402
from scripts.run_m2_backbone_v31 import sealed_manifest  # noqa: E402

IDENTITY = ("phien_ban", "ma_bo_hieu_chuan", "ma_bo_phieu_goc", "sha256_huong_dan")
ARCHIVE = ("body_variant_id", "body_sha256", "ma_ban_luu", "moc_ban_luu")
UNKNOWN = "CHUA_XAC_MINH"


def unique_fields(items: list[tuple[str, Any]]) -> dict[str, Any]:
    fields = dict(items)
    require(len(fields) == len(items), "Tệp nộp có trường JSON bị lặp")
    return fields


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_pack(pack: Path) -> tuple[dict, dict]:
    manifest = verify_artifacts(pack)
    require(manifest["stage"] == "m2_v31_semantic_review_calibration_preparation", "Sai gói hiệu chuẩn")
    for relative, digest in manifest["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    html = (pack / "phieu_hieu_chuan_v2.html").read_text(encoding="utf-8")
    marker = '<script id="case-data" type="application/json">'
    require(html.count(marker) == 1, "Thiếu dữ liệu đã phát trong phiếu")
    data = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
    digest = data.pop("ma_bo_hieu_chuan")
    receipt = read_json(pack / "bien_nhan_chuan_bi.json")
    require(digest == content_hash(data) == receipt["ma_bo_hieu_chuan"]
            and data["sha256_huong_dan"] == manifest["inputs"]["config_hash"]
            == manifest["artifacts"]["hashes"]["huong_dan_cham_v2.md"]
            and len(data["ca"]) == 10 and [c["ma_phieu"] for c in data["ca"]] == receipt["ma_phieu"],
            "Gói phiếu khác biên nhận hoặc hướng dẫn")
    data["ma_bo_hieu_chuan"] = digest
    return manifest, data


def verify_span(answer: dict, case: dict) -> str | None:
    key = case["ma_phieu"]
    span = answer.get("doan_quyet_dinh")
    if answer["nhan_quan_he"] == "CHUA_DU_CAN_CU":
        require("doan_quyet_dinh" in answer and span is None and answer.get("vi_tri_doan") == "CHUA_CO_DOAN_DU",
                f"{key}: nhãn chưa đủ căn cứ cần để trống đoạn quyết định")
        return None
    require(isinstance(span, dict), f"{key}: thiếu đoạn quyết định")
    start, end, quote = (span.get(k) for k in ("bat_dau", "ket_thuc", "doan_trich"))
    body = case["than_bai"]
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(body)
            and nonempty(quote) and body[start:end] == quote, f"{key}: đoạn sai nguyên văn hoặc vị trí Unicode")
    originals = case["vi_tri"]
    if any(v["bat_dau"] <= start and end <= v["ket_thuc"] for v in originals):
        location = "DOAN_GOC"
    elif any(v["bat_dau"] - len(v["truoc"]) <= start and end <= v["ket_thuc"] + len(v["sau"]) for v in originals):
        location = "NGU_CANH_LIEN_KE"
    else:
        location = "DOAN_KHAC_CUNG_BAN_LUU"
    require(answer.get("vi_tri_doan") == location, f"{key}: sai nhóm vị trí đoạn")
    return sha256_text(quote)


def verify_submission(data: dict, submitted: object) -> dict:
    require(isinstance(submitted, dict) and submitted.get("trang_thai") == "DA_GUI_HIEU_CHUAN",
            "Cần tệp kết quả đã xuất từ phiếu hiệu chuẩn")
    require(all(submitted.get(k) == data[k] for k in IDENTITY), "Tệp nộp khác bộ phiếu hoặc hướng dẫn")
    verdict = submitted.get("ket_luan_huong_dan")
    require(verdict in ("DONG_Y_TIEU_CHI", "CAN_SUA_TIEU_CHI")
            and nonempty(submitted.get("nguoi_phan_xu")) and nonempty(submitted.get("ly_do_ket_luan")),
            "Thiếu mã người phân xử hoặc kết luận có lý do")
    rows = submitted.get("quyet_dinh")
    require(isinstance(rows, list) and all(isinstance(row, dict) and nonempty(row.get("ma_phieu")) for row in rows),
            "Danh sách quyết định không hợp lệ")
    answers = indexed(rows, "ma_phieu")
    cases = indexed(data["ca"], "ma_phieu")
    require(answers.keys() == cases.keys(), "Danh sách quyết định khác 10 mã phiếu đã phát")
    types = [*data["kieu_thuc_the"], "NGOAI_ONTOLOGY", UNKNOWN]
    verified = []
    for key, case in cases.items():
        answer = answers[key]
        require(answer.get("nhan_quan_he") in LABELS and nonempty(answer.get("ly_do_quan_he"))
                and nonempty(answer.get("ly_do_kieu")), f"{key}: thiếu nhãn hoặc lý do")
        head, tail = answer.get("kieu_dau"), answer.get("kieu_cuoi")
        require(head in types and tail in types, f"{key}: kiểu thực thể không hợp lệ")
        if ((head != UNKNOWN and head not in case["kieu_dau_cho_phep"])
                or (tail != UNKNOWN and tail not in case["kieu_cuoi_cho_phep"])):
            type_status = "SAI_KIEU"
        elif UNKNOWN in (head, tail):
            type_status = "CHUA_XAC_MINH_KIEU"
        else:
            type_status = "DUNG_KIEU"
        require(answer.get("trang_thai_kieu") == type_status, f"{key}: trạng thái kiểu không khớp lựa chọn")
        require(all(answer.get(k) == case[k] for k in ARCHIVE)
                and sha256_text(case["than_bai"]) == case["body_sha256"], f"{key}: sai bản lưu hoặc thân bài")
        verified.append({
            **answer, "span_sha256": verify_span(answer, case), "url_ban_luu": case["url_ban_luu"],
        })
    return {
        **{k: submitted[k] for k in (*IDENTITY, "nguoi_phan_xu", "ket_luan_huong_dan", "ly_do_ket_luan")},
        "trang_thai": "HOP_LE_VE_HO_SO", "so_quyet_dinh": len(verified),
        "so_doan_da_doi_chieu": sum(row["span_sha256"] is not None for row in verified), "quyet_dinh": verified,
    }


def receive(pack: Path, submission: Path, out: Path) -> dict:
    manifest, data = load_pack(pack)
    raw = submission.read_bytes()
    verified = verify_submission(data, json.loads(raw, object_pairs_hook=unique_fields))
    receipt = json_bytes(verified)
    file_hash = sha256(raw).hexdigest()
    files = (pack / "experiment_manifest.json", Path(__file__).resolve())
    hashes = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in files}
    out.mkdir(parents=True, exist_ok=False)
    with (out / "phieu_da_nop.json").open("xb") as stream:
        stream.write(raw)
    with (out / "bien_nhan_kiem_tra.json").open("xb") as stream:
        stream.write(receipt)
    sealed_manifest(out, "m2_v31_semantic_review_calibration_receipt", {
        **manifest["inputs"], "hashes": hashes, "submission_sha256": file_hash,
        "data_hash": content_hash({"tep_truy_vet": hashes, "sha256_phieu_da_nop": file_hash}),
    })
    return verified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=output_path, help="Gói hiệu chuẩn đã phát")
    parser.add_argument("submission", type=review_path, help="Tệp JSON người phân xử đã nộp")
    parser.add_argument("output", type=output_path, help="Thư mục mới để lưu biên nhận và tệp nộp")
    args = parser.parse_args()
    try:
        verified = receive(args.pack, args.submission, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Kiểm tra hồ sơ không đạt. {exc}\n")
    print(f"Hồ sơ hợp lệ về cấu trúc và truy vết. Đã đối chiếu {verified['so_quyet_dinh']} quyết định.")


if __name__ == "__main__":
    main()
