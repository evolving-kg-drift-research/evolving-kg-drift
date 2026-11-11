"""Đối chiếu hai lượt chấm độc lập V2 trên bộ phiếu đã phát."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_text  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, json_bytes, read_json, require, sha256_file, verify_artifacts,
)
from scripts.prepare_m2_semantic_review import GROUPS, LABELS, indexed, output_path, review_path  # noqa: E402
from scripts.run_m2_backbone_v31 import sealed_manifest  # noqa: E402
from scripts.verify_m2_semantic_calibration import ARCHIVE, UNKNOWN, nonempty, unique_fields, verify_span  # noqa: E402

HEADER = ("phien_ban", "ma_bo_phieu", "sha256_huong_dan")
FIELDS = ("nhan_quan_he", "kieu_dau", "kieu_cuoi", "trang_thai_kieu", "vi_tri_doan")


def load_pack(pack: Path) -> tuple[dict, dict, dict]:
    manifest = verify_artifacts(pack)
    require(manifest["stage"] == "m2_v31_semantic_independent_review_v2_preparation", "Sai gói phiếu V2")
    for relative, digest in manifest["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    marker = '<script id="case-data" type="application/json">'
    issued = {}
    for role in "AB":
        html = (pack / f"phieu_tham_dinh_v2_luot_{role}.html").read_text(encoding="utf-8")
        require(html.count(marker) == 1, "Thiếu dữ liệu trong phiếu đã phát")
        data = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
        require(data.pop("luot") == role, "Sai mã lượt đã phát")
        issued[role] = data
    plan = read_json(pack / "thiet_ke_phieu_v2.json")
    data = issued["A"]
    key = data.pop("ma_bo_phieu")
    require(key == content_hash(data) == plan["ma_bo_phieu"], "Sai mã bộ phiếu")
    data["ma_bo_phieu"] = key
    require(data == issued["B"] and len(data["ca"]) == 24
            and [c["ma_phieu"] for c in data["ca"]] == [p["ma_phieu"] for p in plan["phieu"]]
            and Counter(p["nhom"] for p in plan["phieu"]) == dict.fromkeys(GROUPS, 12)
            and content_hash(plan["quy_tac"]) == manifest["inputs"]["config_hash"],
            "Hai lượt hoặc thiết kế khác nội dung đã khóa")
    return manifest, data, plan


def verify_review(data: dict, submitted: object, role: str) -> tuple[str, dict[str, dict]]:
    require(isinstance(submitted, dict) and submitted.get("trang_thai") == "DA_GUI"
            and submitted.get("luot") == role and submitted.get("xac_nhan_doc_lap") is True
            and nonempty(submitted.get("nguoi_tham_dinh"))
            and all(submitted.get(k) == data[k] for k in HEADER), f"Lượt {role}: sai bộ, lượt hoặc xác nhận")
    rows = submitted.get("cau_tra_loi")
    require(isinstance(rows, list) and all(isinstance(r, dict) and nonempty(r.get("ma_phieu")) for r in rows),
            f"Lượt {role}: danh sách câu trả lời không hợp lệ")
    answers = indexed(rows, "ma_phieu")
    cases = indexed(data["ca"], "ma_phieu")
    require(answers.keys() == cases.keys(), f"Lượt {role}: thiếu hoặc sai mã phiếu")
    allowed_types = [*data["kieu_thuc_the"], "NGOAI_ONTOLOGY", UNKNOWN]
    verified = {}
    for key, case in cases.items():
        answer = answers[key]
        require(answer.get("nhan_quan_he") in LABELS and nonempty(answer.get("ly_do_quan_he"))
                and nonempty(answer.get("ly_do_kieu")), f"Lượt {role}, {key}: sai nhãn hoặc thiếu lý do")
        head, tail = answer.get("kieu_dau"), answer.get("kieu_cuoi")
        require(head in allowed_types and tail in allowed_types, f"Lượt {role}, {key}: sai kiểu")
        invalid = ((head != UNKNOWN and head not in case["kieu_dau_cho_phep"])
                   or (tail != UNKNOWN and tail not in case["kieu_cuoi_cho_phep"]))
        status = "SAI_KIEU" if invalid else "CHUA_XAC_MINH_KIEU" if UNKNOWN in (head, tail) else "DUNG_KIEU"
        require(answer.get("trang_thai_kieu") == status, f"Lượt {role}, {key}: trạng thái kiểu không khớp")
        require(all(answer.get(k) == case[k] for k in ARCHIVE)
                and sha256_text(case["than_bai"]) == case["body_sha256"], f"Lượt {role}, {key}: sai bản lưu")
        verified[key] = {**answer, "span_sha256": verify_span(answer, case)}
    return submitted["nguoi_tham_dinh"].strip(), verified


def agreement(pairs: list[tuple[dict, dict]], field: str) -> dict:
    counts = Counter((a[field], b[field]) for a, b in pairs)
    values = sorted({value for pair in counts for value in pair} | (set(LABELS) if field == "nhan_quan_he" else set()))
    left = Counter(a[field] for a, _ in pairs)
    right = Counter(b[field] for _, b in pairs)
    size = len(pairs)
    same = sum(counts[v, v] for v in values)
    expected_num = sum(left[v] * right[v] for v in values)
    return {
        "so_phieu": size, "so_trung": same, "ty_le_trung": same / size,
        "kappa_cohen": (same * size - expected_num) / (size**2 - expected_num) if expected_num < size**2 else None,
        "ma_tran": {x: {y: counts[x, y] for y in values} for x in values},
    }


def summarize(data: dict, plan: dict, left: dict[str, dict], right: dict[str, dict]) -> dict:
    pairs = [(left[c["ma_phieu"]], right[c["ma_phieu"]]) for c in data["ca"]]
    quote_pairs = []
    differences = []
    for case, (a, b) in zip(data["ca"], pairs, strict=True):
        span_a, span_b = a["doan_quyet_dinh"], b["doan_quyet_dinh"]
        fields = [field for field in FIELDS if a[field] != b[field]]
        if span_a and span_b:
            quote_pairs.append((span_a, span_b))
            if (span_a["bat_dau"], span_a["ket_thuc"]) != (span_b["bat_dau"], span_b["ket_thuc"]):
                fields.append("khoang_doan_dan")
        if fields:
            differences.append({"ma_phieu": case["ma_phieu"], "bo_ba": case["bo_ba"], "muc_khac": fields,
                                "A": a, "B": b})
    return {
        "ma_bo_phieu": data["ma_bo_phieu"],
        "so_phieu": len(pairs),
        "dong_thuan": {field: agreement(pairs, field) for field in FIELDS},
        "dong_thuan_theo_nhom": {
            group: {field: agreement(
                [pair for meta, pair in zip(plan["phieu"], pairs, strict=True) if meta["nhom"] == group], field,
            ) for field in FIELDS} for group in GROUPS
        },
        "doan_dan": {
            "so_doan_da_kiem_A": sum(a["span_sha256"] is not None for a, _ in pairs),
            "so_doan_da_kiem_B": sum(b["span_sha256"] is not None for _, b in pairs),
            "so_ca_ca_hai_dan": len(quote_pairs),
            "so_ca_trung_khoang": sum((a["bat_dau"], a["ket_thuc"]) == (b["bat_dau"], b["ket_thuc"])
                                     for a, b in quote_pairs),
            "so_ca_giao_khoang": sum(max(a["bat_dau"], b["bat_dau"]) < min(a["ket_thuc"], b["ket_thuc"])
                                     for a, b in quote_pairs),
        },
        "so_ca_trung_ca_nam_truong": sum(all(a[field] == b[field] for field in FIELDS) for a, b in pairs),
        "chi_tiet_khac_biet": differences,
    }


def compare(pack: Path, path_a: Path, path_b: Path, out: Path) -> dict:
    manifest, data, plan = load_pack(pack)
    files = {"A": path_a.read_bytes(), "B": path_b.read_bytes()}
    left_id, left = verify_review(data, json.loads(files["A"], object_pairs_hook=unique_fields), "A")
    right_id, right = verify_review(data, json.loads(files["B"], object_pairs_hook=unique_fields), "B")
    require(left_id.casefold() != right_id.casefold(), "Hai lượt cần mã người chấm khác nhau")
    summary = summarize(data, plan, left, right)
    result = json_bytes(summary)
    inputs = (pack / "experiment_manifest.json", Path(__file__).resolve(),
              ROOT / "scripts/verify_m2_semantic_calibration.py")
    hashes = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in inputs}
    submissions = {role: sha256(raw).hexdigest() for role, raw in files.items()}
    out.mkdir(parents=True, exist_ok=False)
    for role, raw in files.items():
        with (out / f"phieu_{role}.json").open("xb") as stream:
            stream.write(raw)
    with (out / "doi_chieu_v2.json").open("xb") as stream:
        stream.write(result)
    sealed_manifest(out, "m2_v31_semantic_independent_review_v2_comparison", {
        **manifest["inputs"], "hashes": hashes, "sha256_phieu_da_nop": submissions,
        "data_hash": content_hash({"tep_truy_vet": hashes, "phieu_da_nop": submissions}),
    })
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=output_path)
    parser.add_argument("a", type=review_path)
    parser.add_argument("b", type=review_path)
    parser.add_argument("out", type=output_path)
    args = parser.parse_args()
    try:
        result = compare(args.pack, args.a, args.b, args.out)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Đối chiếu chưa hoàn tất. {exc}\n")
    print(f"Đã kiểm tra và đối chiếu {result['so_phieu']} phiếu.")


if __name__ == "__main__":
    main()
