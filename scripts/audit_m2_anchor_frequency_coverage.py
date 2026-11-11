"""Đo độ phủ hồ sơ bài nguồn theo cutoff của chín chuyển tiếp M2 V3.1."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts.compare_m2_semantic_independent_review import ARCHIVE, HEADER, load_pack, verify_span  # noqa: E402
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, timestamp  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.prepare_m2_semantic_review import indexed  # noqa: E402
from scripts.run_m2_backbone_v31 import inspect_inputs, sealed_manifest  # noqa: E402

OUTPUT = ROOT / "outputs/m2_anchor_article_readiness"
SEMANTIC = ROOT / "outputs/m2_anchor_semantic_review"
TIME = ROOT / "outputs/m2_anchor_temporal_review"
RECOVERY = ROOT / "outputs/m2_anchor_article_recovery/20261110_v1"
ALIGNMENT = ROOT / "outputs/m2_alignment_v31_readiness/20261110_v1"


def entity_ids(row: dict) -> set[str]:
    return {row["thuc_the_dau_id"], row["thuc_the_cuoi_id"]}


def article_key(row: dict) -> tuple[str, str]:
    return row["nguon"], row["ma_bai"]


def validate_times(queue: list[dict], recovery: list[dict], original: list[dict], alternate: list[dict]) -> None:
    require(all(r["mapping_available_at_verified"] is None for r in recovery)
            and all(r["mapping_as_of_verified"] is False for r in original + alternate),
            "Hồ sơ có ánh xạ đã xác minh, cần đối chiếu phiên bản và phạm vi hiệu lực trước khi tổng hợp")
    captures = {r["retrieval_id"]: r for r in recovery}
    same_body = set()
    for row in original:
        if row["content_seen_by_utc"] is None:
            continue
        capture = captures[row["independent_wayback_retrieval_id"]]
        require(capture["raw_body_matches_v31"]
                and all(capture[k] == row[k] for k in ("source_id", "publisher_article_id", "body_text_sha256"))
                and timestamp(capture["archive_datetime_corroborated"]) == row["content_seen_by_utc"],
                "Căn cứ thời gian cùng thân bài khác hồ sơ khôi phục")
        same_body.add((row["fact_version_id"], row["source_id"], row["publisher_article_id"],
                       capture["retrieval_id"], capture["body_variant_id"], capture["body_text_sha256"],
                       capture["raw_blob_sha256"], capture["url_final"], row["content_seen_by_utc"]))
    other_body = {
        (r["fact_version_id"], r["source_id"], r["publisher_article_id"], r["archive_acquisition_event_id"],
         r["archive_body_variant_id"], r["archive_body_text_sha256"], r["archive_raw_sha256"],
         r["archive_url"], r["archive_datetime_utc"])
        for r in alternate
    }
    sources = {"CUNG_THAN_BAI": same_body, "KHAC_THAN_BAI": other_body}
    for row in queue:
        key = (row["fact_version_id"], *article_key(row), row["ma_ban_luu"], row["body_variant_id"],
               row["body_sha256"], row["raw_sha256"], row["url_ban_luu"], timestamp(row["moc_ban_luu"]))
        require(key in sources[row["nhom"]], f"{row['ma_phieu']}: không khớp căn cứ thời gian cấp bài")


def approved_evidence(issued: dict, final: dict, queue: dict[str, dict]) -> list[dict]:
    require(final["trang_thai"] == "DA_CHOT" and all(final[k] == issued[k] for k in HEADER)
            and final["xac_nhan_nguoi_phu_trach"]["muc_da_xac_nhan"] == list(range(1, 10)),
            "Thiếu biên bản phân xử được xác nhận cho bộ phiếu")
    cases = indexed(issued["ca"], "ma_phieu")
    answers = indexed(final["cau_tra_loi"], "ma_phieu")
    require(answers.keys() == cases.keys(), "Kết quả phân xử khác mã phiếu đã phát")
    accepted = []
    for key, answer in answers.items():
        case, row = cases[key], queue[key]
        require(all(answer[k] == case[k] == row[k] for k in (*ARCHIVE, "url_ban_luu"))
                and case["bo_ba"] == [row["ten_dau"], row["quan_he"], row["ten_cuoi"]]
                and verify_span(answer, case) == answer["span_sha256"], f"{key}: sai bản lưu hoặc đoạn đã chốt")
        if answer["nhan_quan_he"] == "HO_TRO" and answer["trang_thai_kieu"] == "DUNG_KIEU":
            accepted.append({
                **{k: row[k] for k in ("ma_phieu", "fact_version_id", "thuc_the_dau_id", "thuc_the_cuoi_id",
                                       "nguon", "ma_bai", *ARCHIVE, "url_ban_luu")},
                "span_sha256": answer["span_sha256"], "doan_quyet_dinh": answer["doan_quyet_dinh"],
            })
    require(len(accepted) == final["tong_ket"]["so_ho_tro_va_dung_kieu"] == 15, "Sai số phiếu đủ nội dung")
    return accepted


def articles_by_entity(rows: list[dict], persistent: set[str]) -> dict[str, set[tuple[str, str]]]:
    articles: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        for entity in entity_ids(row) & persistent:
            articles[entity].add(article_key(row))
    return articles


def audit(out: Path) -> None:
    datasets, _, clocks, hashes = inspect_inputs()
    queue_dir = SEMANTIC / "20261110_v1"
    pack = SEMANTIC / "20261111_ban_giao_ab_v2"
    final_dir = SEMANTIC / "20261111_chot_phan_xu_ab_v2"
    same = TIME / "20261110_v1"
    alt = TIME / "20261110_doan_trich_v1"
    verified_time = TIME / "20261110_kiem_chung_v1"
    _, issued, _ = load_pack(pack)
    parents = {p: verify_artifacts(p) for p in (queue_dir, final_dir, RECOVERY, same, alt, verified_time, ALIGNMENT)}
    for directory in (*parents, pack, OUTPUT / "20261110_v1"):
        file = directory / "experiment_manifest.json"
        hashes[file.relative_to(ROOT).as_posix()] = sha256_file(file)
    for source in (same, alt):
        relative = (source / "experiment_manifest.json").relative_to(ROOT).as_posix()
        require(hashes[relative] == parents[verified_time]["inputs"]["hashes"][relative],
                "Hồ sơ thời gian khác lượt kiểm chứng")

    final = read_json(final_dir / "phan_xu_v2_da_chot.json")
    require(parents[final_dir]["stage"] == "m2_v31_semantic_independent_review_adjudication_confirmed",
            "Sai loại hồ sơ phân xử")
    for key in ("snapshot_hash", "entity_map_hash", "relation_map_hash"):
        require(parents[final_dir]["inputs"][key] == parents[alt]["inputs"][key] == parents[queue_dir]["inputs"][key],
                f"Khác dữ liệu V3.1 ở {key}")
    queue = pq.read_table(queue_dir / "hang_cho_tham_dinh.parquet").to_pylist()
    recovery = pq.read_table(RECOVERY / "bang_truy_vet_ung_vien.parquet").to_pylist()
    original = pq.read_table(same / "bang_can_cu_thoi_gian.parquet").to_pylist()
    alternate = pq.read_table(alt / "bang_doan_trich_trong_ban_luu_khac.parquet").to_pylist()
    validate_times(queue, recovery, original, alternate)
    accepted = approved_evidence(issued, final, indexed(queue, "ma_phieu"))
    reviewed = {r["ma_phieu"] for r in final["cau_tra_loi"]}

    package = ROOT / ACTIVE_PACKAGE
    release = read_json(package / "release_manifest.json")
    inventory = {r["path"]: r["sha256"] for r in release["artifacts"]}
    require(not any("entity_mapping_versions" in p.lower() for p in inventory),
            "Gói phát hành có bảng lịch sử ánh xạ cần đối chiếu riêng")

    def release_table(path: str) -> list[dict]:
        relative = (ACTIVE_PACKAGE / path).as_posix()
        digest = inventory[path]
        require(hashes.setdefault(relative, digest) == digest, "Tệp Parquet khác bản kê")
        return pq.read_table(bound_file(ROOT, {"path": relative, "sha256": digest})).to_pylist()

    facts = indexed(release_table("tables/fact_versions.parquet"), "fact_version_id")
    for row in queue:
        f = facts[row["fact_version_id"]]
        require((f["subject_id"], f["relation_id"], f["object_id"])
                == (row["thuc_the_dau_id"], row["quan_he"], row["thuc_the_cuoi_id"]), "Sai nối FactVersion")
    profile = indexed(read_json(ALIGNMENT / "kiem_tra_truoc_can_chinh.json")["ho_so_neo_theo_chuyen_tiep"],
                      "chuyen_tiep")
    previous_time = indexed(read_json(alt / "bao_phu_bo_sung.json")["theo_snapshot"], "snapshot")
    pairs, entities = [], []
    names = list(datasets)
    for prev, nxt in zip(names, names[1:]):
        transition = f"{prev}->{nxt}"
        cutoff = timestamp(clocks[prev]["cutoff"])
        persistent = set(datasets[prev].entities) & set(datasets[nxt].entities)
        plan = profile[transition]
        require(len(persistent) == plan["so_thuc_the_chung"] and (plan["khop"], plan["giu_rieng"]) == (101, 66),
                "Quần thể thực thể chung hoặc quy mô neo khác hồ sơ thiết kế")
        full_ids = {r["fact_version_id"] for r in release_table(f"snapshots/snapshot_{prev}.parquet")}
        timed = [r for r in queue if r["fact_version_id"] in full_ids and timestamp(r["moc_ban_luu"]) <= cutoff]
        timed_entities = set().union(*(entity_ids(r) for r in timed))
        require(len(timed_entities) == previous_time[prev]["thuc_the_co_moc_den_cutoff"]
                and len({r["fact_version_id"] for r in timed})
                == previous_time[prev]["so_fact_version_co_moc_den_cutoff_gop"],
                f"{prev}: độ phủ thời gian khác hồ sơ đã kiểm chứng")
        good = [r for r in accepted if timestamp(r["moc_ban_luu"]) <= cutoff]
        waiting = articles_by_entity([r for r in timed if r["ma_phieu"] not in reviewed], persistent)
        timed_articles = articles_by_entity(timed, persistent)
        good_articles = articles_by_entity(good, persistent)
        touched = [r for r in good if entity_ids(r) & persistent]
        needed = plan["khop"] + plan["giu_rieng"]
        for entity in sorted(persistent):
            entities.append({
                "chuyen_tiep": transition, "cutoff_nguon_utc": cutoff.isoformat(), "thuc_the_id": entity,
                "bac_nguon": datasets[prev].entity_metadata[entity].degree,
                "so_bai_co_moc_trong_snapshot_nguon": len(timed_articles.get(entity, ())),
                "so_bai_chua_cham_v2_trong_snapshot_nguon": len(waiting.get(entity, ())),
                "so_bai_dat_noi_dung_va_moc_cho_anh_xa": len(good_articles.get(entity, ())),
                "tan_suat_bai_nguon_da_xac_minh": None,
                "trang_thai_tan_suat": "CHUA_XAC_MINH",
            })
        pairs.append({
            "chuyen_tiep": transition, "cutoff_nguon_utc": cutoff.isoformat(),
            "so_thuc_the_chung": len(persistent), "so_neo_khop_can": plan["khop"],
            "so_neo_giu_rieng_can": plan["giu_rieng"],
            "so_thuc_the_co_moc_trong_snapshot_nguon": len(timed_articles),
            "so_thuc_the_chua_co_moc_trong_snapshot_nguon": len(persistent) - len(timed_articles),
            "so_phieu_dat_noi_dung_va_moc_den_cutoff": len(good),
            "so_phieu_dat_noi_dung_va_moc_sau_cutoff": len(accepted) - len(good),
            "so_phieu_den_cutoff_cham_thuc_the_chung": len(touched),
            "so_phieu_den_cutoff_cham_thuc_the_chung_co_fact_version_trong_snapshot": sum(
                r["fact_version_id"] in full_ids for r in touched
            ),
            "so_cap_thuc_the_bai_dat_noi_dung_va_moc": sum(map(len, good_articles.values())),
            "so_thuc_the_co_bai_dat_noi_dung_va_moc_cho_anh_xa": len(good_articles),
            "so_thuc_the_co_tan_suat_da_xac_minh": 0, "so_thuc_the_xac_nhan_tan_suat_bang_0": 0,
            "so_thuc_the_con_thieu_de_du_167_neo_ngay_ca_khi_xac_minh_anh_xa": max(0, needed - len(good_articles)),
            "du_dieu_kien_khoa_neo": False,
        })

    config = {
        "pham_vi": "Rà độ phủ tần suất bài nguồn cho 9 chuyển tiếp M2 V3.1",
        "khoa_bai": ["nguon", "ma_bai"],
        "moc_thoi_gian": "Mốc bản lưu đúng phiên bản chứa đoạn đã chấm <= cutoff nguồn",
        "tan_suat_thieu": None,
        "so_neo_khop": 101, "so_neo_giu_rieng": 66,
    }
    for file in (Path(__file__).resolve(), ROOT / "config/schema.yaml",
                 OUTPUT / "20261110_v1/lua_chon_da_xac_nhan.json"):
        hashes[file.relative_to(ROOT).as_posix()] = sha256_file(file)
    table = pa.Table.from_pylist(entities)
    column = table.schema.get_field_index("tan_suat_bai_nguon_da_xac_minh")
    table = table.set_column(column, "tan_suat_bai_nguon_da_xac_minh", pa.nulls(len(entities), type=pa.int64()))
    out.mkdir(parents=True, exist_ok=False)
    with (out / "do_phu_theo_thuc_the.parquet").open("xb") as stream:
        pq.write_table(table, stream, compression="zstd")
    write_json(out / "phieu_dat_noi_dung_cho_anh_xa.json", accepted)
    write_json(out / "bao_phu_neo.json", {
        "quy_tac": config, "so_phieu_v2_da_chot": len(reviewed), "so_phieu_dat_noi_dung": len(accepted),
        "so_dong_truy_vet_thieu_moc_anh_xa": len(recovery), "so_chuyen_tiep_du_dieu_kien": 0,
        "so_dong_thuc_the_chuyen_tiep": len(entities), "theo_chuyen_tiep": pairs,
    })
    sealed_manifest(out, "m2_v31_anchor_frequency_coverage_diagnostic", {
        **parents[final_dir]["inputs"], "hashes": hashes, "data_hash": content_hash(hashes),
        "config_hash": content_hash(config),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", help="Thư mục mới trong outputs/m2_anchor_article_readiness")
    out = Path(parser.parse_args().out).resolve()
    require(out.is_relative_to(OUTPUT) and out != OUTPUT and "locked_test" not in {p.lower() for p in out.parts},
            "Sai thư mục kết quả")
    audit(out)


if __name__ == "__main__":
    main()
