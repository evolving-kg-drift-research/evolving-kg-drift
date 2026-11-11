"""Thử tái lập ánh xạ theo tên trên toàn bộ thực thể chung T01–T02."""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_text  # noqa: E402
from scripts.audit_m2_anchor_frequency_coverage import OUTPUT, SEMANTIC, entity_ids  # noqa: E402
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, timestamp  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.prepare_m2_semantic_review import indexed  # noqa: E402
from scripts.run_m2_backbone_v31 import inspect_inputs, sealed_manifest  # noqa: E402

LEVELS = ("DOAN_TRICH_GOC", "NGU_CANH_LIEN_KE", "THAN_BAI", "THIEU_TEN_DOC_LAP")
MISSING = len(LEVELS) - 1


def name_spans(text: str, name: str) -> list[tuple[int, int]]:
    require(bool(name), "Tên thực thể trống")
    pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
    return [m.span() for m in re.finditer(pattern, text, re.IGNORECASE) if m[0].lower() == name.lower()]


def location(start: int, end: int, quotes: list[dict]) -> int:
    if any(q["bat_dau"] <= start < end <= q["ket_thuc"] for q in quotes):
        return 0
    if any(q["bat_dau"] - len(q["truoc"]) <= start < end <= q["ket_thuc"] + len(q["sau"]) for q in quotes):
        return 1
    return 2


def inspect_names(text: str, names: tuple[str, str], quotes: list[dict]) -> list[dict]:
    positions = [name_spans(text, name) for name in names]
    checked = []
    for index, matches in enumerate(positions):
        other = positions[1 - index]
        separate = [
            (s, e) for s, e in matches if not any(a <= s < e <= b and e - s < b - a for a, b in other)
        ]
        best = min(((location(s, e, quotes), s, e) for s, e in separate), default=(MISSING, None, None))
        level, start, end = best
        checked.append({
            "muc": level, "bat_dau": start, "ket_thuc": end,
            "so_vi_tri_khop": len(matches), "so_vi_tri_long_trong_ten_con_lai": len(matches) - len(separate),
        })
    return checked


def audit(out: Path) -> None:
    coverage = OUTPUT / "20261111_do_phu_tan_suat_v1"
    pilot = OUTPUT / "20261111_kiem_tra_anh_xa_t01_v1"
    queue_run = SEMANTIC / "20261110_v1"
    datasets, _, clocks, hashes = inspect_inputs()
    sources = {run: verify_artifacts(run) for run in (coverage, pilot, queue_run)}
    for relative, digest in sources[coverage]["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    proof = read_json(pilot / "doi_chieu_anh_xa_t01.json")
    cutoff = timestamp(clocks["T01"]["cutoff"])
    persistent = set(datasets["T01"].entities) & set(datasets["T02"].entities)
    require(len(persistent) == 167 and cutoff == timestamp(proof["cutoff_nguon_utc"]), "Sai quần thể hoặc cutoff T01")
    require(proof["so_thuc_the_tai_lap_dung_ma"] == 8 and proof["so_thuc_the_xac_minh_moc_anh_xa"] == 0,
            "Hồ sơ thử tám thực thể có trạng thái khác")
    release = read_json(ROOT / ACTIVE_PACKAGE / "release_manifest.json")
    inventory = {r["path"]: r["sha256"] for r in release["artifacts"]}

    def release_file(path: str) -> Path:
        relative = (ACTIVE_PACKAGE / path).as_posix()
        digest = inventory[path]
        require(hashes.setdefault(relative, digest) == digest, "Tệp khác bản kê phát hành")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    full = pq.read_table(release_file("snapshots/snapshot_T01.parquet"), columns=["fact_version_id"]).to_pylist()
    full_ids = set(indexed(full, "fact_version_id"))
    facts = indexed(pq.read_table(release_file("tables/fact_versions.parquet")).to_pylist(), "fact_version_id")
    claims = indexed(pq.read_table(release_file("tables/extracted_claims.parquet")).to_pylist(), "claim_id")
    variants = indexed(pq.read_table(release_file("tables/body_variants.parquet")).to_pylist(), "body_variant_id")
    queue = pq.read_table(queue_run / "hang_cho_tham_dinh.parquet").to_pylist()
    selected = [r for r in queue if timestamp(r["moc_ban_luu"]) <= cutoff and entity_ids(r) & persistent]
    primary = [r for r in selected if r["fact_version_id"] in full_ids]
    require(len(primary) == len(full_ids) == 127 and {r["fact_version_id"] for r in primary} == full_ids,
            "Thiếu FactVersion T01 có bản lưu trước cutoff")
    bodies = {}
    spellings: dict[str, set[str]] = defaultdict(set)
    normalized_by_entity: dict[str, set[str]] = defaultdict(set)
    entity_by_normalized: dict[str, set[str]] = defaultdict(set)
    names_by_replayed_id: dict[str, set[str]] = defaultdict(set)
    per_entity: dict[str, list[dict]] = defaultdict(list)
    for row in selected:
        fact, claim = facts[row["fact_version_id"]], claims[row["claim_id"]]
        names = (row["ten_dau"].strip(), row["ten_cuoi"].strip())
        ids = (row["thuc_the_dau_id"], row["thuc_the_cuoi_id"])
        require(ids == (fact["subject_id"], fact["object_id"])
                and row["quan_he"] == fact["relation_id"] == claim["relation_name"]
                and names == (claim["subject_mention"].strip(), claim["object_mention"].strip())
                and row["fact_version_id"] == f"{fact['logical_fact_id']}_{row['claim_id']}",
                "Sai nối FactVersion, mệnh đề hoặc tên")
        body_id = row["body_variant_id"]
        variant = variants[body_id]
        require(variant["body_text_sha256"] == row["body_sha256"], "Sai thân bài trong hàng chờ")
        if body_id not in bodies:
            relative = PureWindowsPath(variant["body_blob_relative_path"]).as_posix()
            text = release_file(relative).read_bytes().decode("utf-8")
            require(sha256_text(text) == row["body_sha256"], "Sai mã băm thân bài")
            bodies[body_id] = text
        text = bodies[body_id]
        for q in row["vi_tri"]:
            start, end = q["bat_dau"], q["ket_thuc"]
            require(0 <= start < end <= len(text) and text[start:end] == q["doan_trich"]
                    and sha256_text(text[start:end]) == row["span_sha256"]
                    and text[max(0, start - 420):start] == q["truoc"] and text[end:end + 420] == q["sau"],
                    "Sai vị trí, nguyên văn hoặc ngữ cảnh")
        checked = inspect_names(text, names, row["vi_tri"])
        for role, name, entity, item in zip(("DAU", "CUOI"), names, ids, checked, strict=True):
            if entity not in persistent:
                continue
            normalized = name.lower()
            from_label = f"ent_{sha256_text(normalized)[:8]}"
            start, end = item["bat_dau"], item["ket_thuc"]
            found = text[start:end] if start is not None else None
            from_archive = f"ent_{sha256_text(found.lower())[:8]}" if found is not None else None
            spellings[entity].add(name)
            normalized_by_entity[entity].add(normalized)
            entity_by_normalized[normalized].add(entity)
            names_by_replayed_id[from_label].add(normalized)
            per_entity[entity].append({
                **item, "muc_vi_tri": LEVELS[item["muc"]], "ten_trong_ho_so": name, "ten_trong_ban_luu": found,
                "ma_tu_ten_trong_ho_so": from_label, "ma_tu_ten_trong_ban_luu": from_archive, "ma_v31": entity,
                "vai_tro": role, "ma_phieu": row["ma_phieu"], "fact_version_id": row["fact_version_id"],
                "fact_version_thuoc_t01": row["fact_version_id"] in full_ids,
                "nguon": row["nguon"], "ma_bai": row["ma_bai"], "ma_ban_luu": row["ma_ban_luu"],
                "moc_ban_luu_utc": timestamp(row["moc_ban_luu"]).isoformat(), "body_sha256": row["body_sha256"],
                "span_sha256": row["span_sha256"], "mapping_available_at_verified": None,
            })
    require(set(per_entity) == persistent, "Thiếu thực thể chung trong hồ sơ kiểm tra")

    def best_level(rows: list[dict]) -> int:
        return min((r["muc"] for r in rows if r["ma_tu_ten_trong_ban_luu"] == r["ma_v31"]), default=MISSING)

    primary_counts: Counter[str] = Counter()
    combined_counts: Counter[str] = Counter()
    rows = []
    for entity, hits in sorted(per_entity.items()):
        level_a = LEVELS[best_level([r for r in hits if r["fact_version_thuoc_t01"]])]
        level_b = LEVELS[best_level(hits)]
        primary_counts[level_a] += 1
        combined_counts[level_b] += 1
        rows.append({
            "thuc_the_id": entity, "ten_trong_ho_so": sorted(spellings[entity]),
            "muc_tu_fact_version_t01": level_a, "muc_gop_ban_luu_bo_sung": level_b,
            "ma_tu_ten_ho_so_khop": all(r["ma_tu_ten_trong_ho_so"] == entity for r in hits),
            "mapping_available_at_verified": None,
        })
    bindings = [r for hits in per_entity.values() for r in hits]
    pilot_entities = {r["thuc_the_id_v31"] for r in proof["ten_theo_phieu"]}
    require(pilot_entities <= {r["thuc_the_id"] for r in rows if r["muc_gop_ban_luu_bo_sung"] != LEVELS[MISSING]},
            "Thiếu kết quả kỹ thuật đã tái lập ở nhóm thử")
    cfg = {
        "pham_vi": "T01->T02, kiểm tra kỹ thuật tên nguyên văn và mã từ bản lưu đến cutoff nguồn",
        "tai_lap": "ent_ + 8 ký tự đầu SHA-256 của tên UTF-8 sau strip().lower()",
        "rang_buoc": "Tên độc lập với tên đầu hoặc cuối còn lại. Phân loại theo vị trí so với đoạn gốc.",
    }
    for file in (*(run / "experiment_manifest.json" for run in sources), Path(__file__).resolve()):
        hashes[file.relative_to(ROOT).as_posix()] = sha256_file(file)
    summary = {
        "quy_tac": cfg, "cutoff_nguon_utc": cutoff.isoformat(),
        "thoi_diem_tai_lap_thuc_te_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "so_thuc_the_chung": len(persistent), "so_phieu_fact_version_t01": len(primary),
        "so_phieu_bo_sung_ngoai_fact_version_t01": len(selected) - len(primary),
        "so_dong_ten": len(bindings), "so_thuc_the_ma_tu_ten_ho_so_khop": sum(r["ma_tu_ten_ho_so_khop"] for r in rows),
        "muc_tu_fact_version_t01": dict(primary_counts), "muc_gop_ban_luu_bo_sung": dict(combined_counts),
        "ten_chuan_hoa_khop_nhieu_ma": {k: sorted(v) for k, v in entity_by_normalized.items() if len(v) > 1},
        "ma_v31_co_nhieu_ten_chuan_hoa": {k: sorted(v) for k, v in normalized_by_entity.items() if len(v) > 1},
        "va_cham_ma_bam": {k: sorted(v) for k, v in names_by_replayed_id.items() if len(v) > 1},
        "so_moc_hieu_luc_da_xac_minh": 0, "theo_thuc_the": rows,
    }
    table = pa.Table.from_pylist(bindings)
    idx = table.schema.get_field_index("mapping_available_at_verified")
    table = table.set_column(idx, "mapping_available_at_verified", pa.nulls(len(bindings), type=pa.timestamp("us", "UTC")))
    out.mkdir(parents=True, exist_ok=False)
    with (out / "vi_tri_ten_theo_phieu.parquet").open("xb") as stream:
        pq.write_table(table, stream, compression="zstd")
    write_json(out / "doi_chieu_toan_bo_t01.json", summary)
    sealed_manifest(out, "m2_v31_anchor_mapping_t01_full_replay_diagnostic", {
        **sources[coverage]["inputs"], "hashes": hashes, "config_hash": content_hash(cfg), "data_hash": content_hash(hashes),
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
