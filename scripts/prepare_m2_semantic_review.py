"""Lập bộ phiếu thẩm định quan hệ M2 V3.1 và đối chiếu hai phiếu đã ghi."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, require_current_package, timestamp  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.run_m2_backbone_v31 import bind_all, sealed_manifest  # noqa: E402
from kg_pipeline.hashing import sha256_text  # noqa: E402

OUTPUT = ROOT / "outputs/m2_anchor_semantic_review"
RECOVERY = "outputs/m2_anchor_article_recovery/20261110_v1"
TEMPORAL = "outputs/m2_anchor_temporal_review"
BASE = f"{TEMPORAL}/20261110_v1"
EXTRA = f"{TEMPORAL}/20261110_doan_trich_v1"
VERIFIED = f"{TEMPORAL}/20261110_kiem_chung_v1"
CODE = "scripts/prepare_m2_semantic_review.py"
ONTOLOGY = "config/ontology.yaml"
TEMPLATE = "scripts/m2_semantic_review_form.html"
GROUPS = ("CUNG_THAN_BAI", "KHAC_THAN_BAI")
SALT = "m2-v31-semantic-review-pilot-v1"
LABELS = ("HO_TRO", "KHONG_HO_TRO", "CHUA_DU_CAN_CU")


def indexed(rows: list[dict], field: str) -> dict:
    result = {row[field]: row for row in rows}
    require(len(result) == len(rows), f"Trùng khóa {field}")
    return result


def hash_rank(unit: dict) -> str:
    return sha256_text(f"{SALT}:{unit['ma_phieu']}")


def select_pilot(rows: list[dict], relations: list[str]) -> list[dict]:
    selected, articles, facts = [], set(), set()
    cells = [(group, relation) for group in GROUPS for relation in relations]
    population = {cell: [r for r in rows if (r["nhom"], r["quan_he"]) == cell] for cell in cells}

    def take(pool: list[dict], order) -> None:
        available = [r for r in pool if (r["nguon"], r["ma_bai"]) not in articles
                     and r["fact_version_id"] not in facts]
        require(bool(available), "Thiếu trường hợp độc lập để tạo phiếu thử")
        chosen = min(available, key=order)
        selected.append(chosen)
        articles.add((chosen["nguon"], chosen["ma_bai"]))
        facts.add(chosen["fact_version_id"])

    for cell in sorted(cells, key=lambda c: (len(population[c]), c)):
        take(population[cell], hash_rank)
    for group in GROUPS:
        pool = [r for r in rows if r["nhom"] == group]
        take(pool, lambda r: (len(r["vi_tri"]) <= 1, hash_rank(r)))
        take(pool, lambda r: (r["hai_ten_co_trong_doan"], hash_rank(r)))
    return sorted(selected, key=hash_rank)


def prepare(out: Path) -> None:
    package = require_current_package(ROOT, ACTIVE_PACKAGE)
    verification = verify_artifacts(ROOT / VERIFIED)
    parents = {name: verify_artifacts(ROOT / name) for name in (BASE, EXTRA, RECOVERY)}
    for name in (BASE, EXTRA):
        relative = f"{name}/experiment_manifest.json"
        require(verification["inputs"]["hashes"][relative] == sha256_file(ROOT / relative),
                "Kiểm chứng khác lượt rà soát thời gian")
    hashes = dict(parents[EXTRA]["inputs"]["hashes"])
    bind_all(hashes)
    for relative in (CODE, TEMPLATE, ONTOLOGY, "docs/data_pipeline_spec.md",
                     "docs/audit/m1_acceptance_design_v2/quality.md",
                     *(f"{name}/experiment_manifest.json" for name in (*parents, VERIFIED))):
        hashes[relative] = sha256_file(ROOT / relative)
    ontology = yaml.safe_load((ROOT / ONTOLOGY).read_bytes())
    relations = sorted(ontology["relations"])
    release = indexed(read_json(package / "release_manifest.json")["artifacts"], "path")
    facts = indexed(pq.read_table(package / "tables/fact_versions.parquet").to_pylist(), "fact_version_id")
    claims = indexed(pq.read_table(package / "tables/extracted_claims.parquet").to_pylist(), "claim_id")
    bodies = indexed(pq.read_table(package / "tables/body_variants.parquet").to_pylist(), "body_variant_id")
    trace = pq.read_table(ROOT / RECOVERY / "bang_truy_vet_ung_vien.parquet").to_pylist()
    retrievals = {r["retrieval_id"]: r for r in trace}
    fact_retrievals = {(r["fact_version_id"], r["retrieval_id"]): r for r in trace}
    last = read_json(ROOT / EXTRA / "bao_phu_bo_sung.json")["theo_snapshot"][-1]
    require(last["snapshot"] == "T10", "Sai giới hạn khảo sát")
    cutoff = timestamp(last["cutoff"])
    cache: dict[str, str] = {}
    units = {}

    def add(fid: str, cid: str, group: str, bid: str, body_sha: str, source: str, article: str,
            archive_ref: str, url: str, seen: datetime, raw_sha: str, offsets: list[tuple[int, int]],
            excerpt_sha: str) -> None:
        if seen > cutoff:
            return
        url_parts = urlsplit(url)
        require(url_parts.scheme == "https" and url_parts.hostname == "web.archive.org", "Sai URL bản lưu")
        fact, claim, body = facts[fid], claims[cid], bodies[bid]
        require(fid == fact["logical_fact_id"] + "_" + cid and fact["relation_id"] in relations
                and claim["relation_name"] == fact["relation_id"] and body["body_text_sha256"] == body_sha,
                "Bằng chứng lệch dữ kiện hoặc ontology")
        if bid not in cache:
            path = PureWindowsPath(body["body_blob_relative_path"]).as_posix()
            require(release[path]["sha256"] == body_sha, "Hash thân bài khác bản phát hành")
            relative = (ACTIVE_PACKAGE / path).as_posix()
            require(hashes.setdefault(relative, body_sha) == body_sha, "Hash thân bài khác bản kê")
            cache[bid] = bound_file(ROOT, {"path": relative, "sha256": body_sha}).read_bytes().decode("utf-8")
        text = cache[bid]
        positions = sorted(set(offsets))
        require(bool(positions) and all(0 <= s < e <= len(text) and sha256_text(text[s:e]) == excerpt_sha
                                       for s, e in positions), "Offset hoặc hash đoạn trích sai")
        unit_key = [fid, source, article, body_sha, positions]
        key_hash = content_hash(unit_key)
        segments = [{"bat_dau": s, "ket_thuc": e, "truoc": text[max(0, s - 420):s],
                     "doan_trich": text[s:e], "sau": text[e:e + 420]} for s, e in positions]
        row = {
            "ma_phieu": "M2-" + key_hash[:16].upper(), "fact_version_id": fid, "claim_id": cid,
            "quan_he": fact["relation_id"], "thuc_the_dau_id": fact["subject_id"], "thuc_the_cuoi_id": fact["object_id"],
            "ten_dau": claim["subject_mention"], "ten_cuoi": claim["object_mention"], "nguon": source,
            "ma_bai": article, "nhom": group, "body_variant_id": bid, "body_sha256": body_sha,
            "span_sha256": excerpt_sha, "vi_tri": segments,
            "ma_ban_luu": archive_ref, "url_ban_luu": url, "raw_sha256": raw_sha, "moc_ban_luu": seen.isoformat(),
            "hai_ten_co_trong_doan": all(bool(claim[k].strip()) and claim[k].strip().casefold()
                                         in segments[0]["doan_trich"].casefold()
                                         for k in ("subject_mention", "object_mention")),
            "trang_thai": "CHO_THAM_DINH_DOC_LAP",
        }
        old = units.get(key_hash)
        if old is None or (seen, archive_ref) < (timestamp(old["moc_ban_luu"]), old["ma_ban_luu"]):
            units[key_hash] = row

    for row in pq.read_table(ROOT / BASE / "bang_can_cu_thoi_gian.parquet").to_pylist():
        if row["content_seen_by_utc"] is None:
            continue
        original = fact_retrievals[row["fact_version_id"], row["retrieval_id"]]
        capture = retrievals[row["independent_wayback_retrieval_id"]]
        require(all(capture[k] == row[k] for k in ("source_id", "publisher_article_id", "body_text_sha256"))
                and capture["raw_body_matches_v31"]
                and timestamp(capture["archive_datetime_corroborated"]) == row["content_seen_by_utc"],
                "Bản lưu khác nội dung đã được kiểm")
        add(row["fact_version_id"], row["claim_id"], GROUPS[0], capture["body_variant_id"], capture["body_text_sha256"],
            capture["source_id"], capture["publisher_article_id"], capture["retrieval_id"], capture["url_final"],
            row["content_seen_by_utc"], capture["raw_blob_sha256"],
            [(original["span_start"], original["span_end"])], row["span_sha256_recomputed"])
    for row in pq.read_table(ROOT / EXTRA / "bang_doan_trich_trong_ban_luu_khac.parquet").to_pylist():
        add(row["fact_version_id"], row["claim_id"], GROUPS[1], row["archive_body_variant_id"],
            row["archive_body_text_sha256"], row["source_id"], row["publisher_article_id"],
            row["archive_acquisition_event_id"], row["archive_url"], row["archive_datetime_utc"],
            row["archive_raw_sha256"], list(zip(row["span_starts"], row["span_ends"], strict=True)), row["span_sha256"])

    queue = sorted(units.values(), key=lambda r: r["ma_phieu"])
    require(len({r["ma_phieu"] for r in queue}) == len(queue), "Mã phiếu bị trùng")
    timed = {r["fact_version_id"] for r in queue}
    require(len(timed) == last["so_fact_version_co_moc_den_cutoff_gop"]
            and len(set(facts) - timed) == last["so_fact_version_chua_co_moc"], "Phạm vi không khớp độ phủ")
    pilot = select_pilot(queue, relations)
    masked = [{k: r[k] for k in ("ma_phieu", "quan_he", "ten_dau", "ten_cuoi", "vi_tri", "url_ban_luu")} for r in pilot]
    policy = {
        "version": SALT, "scope": "Thử cách dùng phiếu trên bằng chứng của quan hệ, chưa có nhãn.",
        "nhan": LABELS, "dinh_dang_doan": "Unicode nguyên văn, ngữ cảnh tối đa 420 ký tự mỗi phía.",
        "chon": "Một dòng mỗi quan hệ trong mỗi nhóm, rồi hai ca thực hành mỗi nhóm. "
                "Ưu tiên ca lặp đoạn và ca thiếu tên trong trích đoạn cho phần thực hành.",
        "chong_trung": "Không lặp bài hoặc FactVersion trong phiếu thử. SHA-256 cố định thứ tự chọn.",
        "tieu_chi": "Đúng hai thực thể, nghĩa và chiều quan hệ, phủ định, giả định và ngữ cảnh.",
        "doi_chieu": "Hai người đọc độc lập. Bất đồng để riêng cho người phân xử.",
        "loai_tru": "Chưa có mốc đến T10 giữ ở hàng chờ. Không dùng nhãn cũ hay kết quả downstream để chọn.",
    }
    plan = {
        "quy_tac": policy, "ma_phieu": [r["ma_phieu"] for r in pilot], "sha256_noi_dung_phieu": content_hash(masked),
        "so_dong_hang_cho": len(queue), "so_fact_version_co_moc": len(timed),
        "so_fact_version_thieu_moc": len(set(facts) - timed), "so_bai_toan_bo": len({(r["nguon"], r["ma_bai"]) for r in queue}),
        "so_dong_theo_nhom": dict(Counter(r["nhom"] for r in queue)),
        "so_dong_thu_theo_nhom": dict(Counter(r["nhom"] for r in pilot)),
        "nguon_phieu_thu": sorted({r["nguon"] for r in pilot}), "so_nhan_da_co": 0,
    }
    payload = {"ma_bo_phieu": plan["sha256_noi_dung_phieu"], "phieu": masked, "nhan": LABELS,
               "quan_he_doi_xung": [r for r, rules in ontology["relations"].items() if rules.get("symmetric")]}
    embedded = json.dumps(payload, ensure_ascii=False).replace("<", r"\u003c")
    html = (ROOT / TEMPLATE).read_text(encoding="utf-8").replace("__REVIEW_DATA__", embedded)
    require("__REVIEW_DATA__" not in html, "Dữ liệu phiếu chưa được gắn")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "thiet_ke_phieu.json", plan)
    write_json(out / "ma_phieu_thu.json", masked)
    write_json(out / "fact_version_cho_can_cu_thoi_gian.json", {
        "ly_do": "CHUA_CO_CAN_CU_THOI_GIAN", "ma_fact_version": sorted(set(facts) - timed),
    })
    with (out / "hang_cho_tham_dinh.parquet").open("xb") as stream:
        pq.write_table(pa.Table.from_pylist(queue), stream, compression="zstd")
    with (out / "phieu_tham_dinh_thu.html").open("x", encoding="utf-8") as stream:
        stream.write(html)
    sealed_manifest(out, "m2_v31_semantic_review_preparation", {
        **parents[EXTRA]["inputs"], "hashes": hashes, "config_hash": content_hash(policy),
        "data_hash": content_hash(hashes),
    })


def validate_review(path: Path, plan: dict, slot: str) -> dict:
    review = read_json(path)
    require(review["ma_bo_phieu"] == plan["sha256_noi_dung_phieu"] and review["luot"] == slot
            and review["xac_nhan_doc_lap"] is True and bool(review["nguoi_tham_dinh"].strip()),
            "Sai bộ phiếu, lượt hoặc thiếu xác nhận người thẩm định")
    answers = indexed(review["cau_tra_loi"], "ma_phieu")
    require(set(answers) == set(plan["ma_phieu"]) and all(
        r["nhan"] in LABELS and r["ly_do"].strip() for r in answers.values()
    ), "Phiếu thiếu dòng, lý do hoặc nhãn hợp lệ")
    return {"nguoi_tham_dinh": review["nguoi_tham_dinh"].strip(), "tra_loi": answers}


def compare(pack: Path, a: Path, b: Path, out: Path) -> None:
    manifest = verify_artifacts(pack)
    require(manifest["stage"] == "m2_v31_semantic_review_preparation", "Sai gói phiếu")
    plan = read_json(pack / "thiet_ke_phieu.json")
    left, right = validate_review(a, plan, "A"), validate_review(b, plan, "B")
    require(left["nguoi_tham_dinh"].casefold() != right["nguoi_tham_dinh"].casefold(),
            "Hai lượt cần hai người đọc khác nhau")
    matrix = {label: dict.fromkeys(LABELS, 0) for label in LABELS}
    disagreements = []
    for key in plan["ma_phieu"]:
        x, y = left["tra_loi"][key], right["tra_loi"][key]
        matrix[x["nhan"]][y["nhan"]] += 1
        if x["nhan"] != y["nhan"]:
            disagreements.append({"ma_phieu": key, "A": x, "B": y})
    agreement = sum(matrix[label][label] for label in LABELS)
    out.mkdir(parents=True, exist_ok=False)
    for role, file in (("A", a), ("B", b)):
        with (out / f"phieu_{role}.json").open("xb") as stream:
            stream.write(file.read_bytes())
    write_json(out / "doi_chieu.json", {
        "so_phieu": len(plan["ma_phieu"]), "so_dong_dong_y": agreement,
        "ty_le_dong_y": agreement / len(plan["ma_phieu"]), "ma_tran_nhan": matrix,
        "bat_dong_can_phan_xu": disagreements, "trang_thai": "Kết quả thử tiêu chí, chờ chốt nhãn.",
    })
    hashes = {file.relative_to(ROOT).as_posix(): sha256_file(file)
              for file in (pack / "experiment_manifest.json", ROOT / CODE)}
    sealed_manifest(out, "m2_v31_semantic_review_pilot_comparison", {
        **manifest["inputs"], "hashes": hashes, "data_hash": content_hash(hashes),
    })


def output_path(raw: str) -> Path:
    path = Path(raw).resolve()
    require(path.is_relative_to(OUTPUT.resolve()) and path != OUTPUT.resolve()
            and "locked_test" not in {p.lower() for p in path.parts}, "Sai thư mục kết quả")
    return path


def review_path(raw: str) -> Path:
    path = Path(raw).resolve()
    require("locked_test" not in {p.lower() for p in path.parts}, "Phiếu nằm ngoài phạm vi cho phép")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("prepare").add_argument("output", type=output_path)
    compare_cli = sub.add_parser("compare")
    compare_cli.add_argument("pack", type=output_path)
    compare_cli.add_argument("a", type=review_path)
    compare_cli.add_argument("b", type=review_path)
    compare_cli.add_argument("output", type=output_path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output)
    else:
        compare(args.pack, args.a, args.b, args.output)


if __name__ == "__main__":
    main()
