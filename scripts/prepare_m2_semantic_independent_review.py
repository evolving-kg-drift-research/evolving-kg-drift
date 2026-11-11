"""Chuẩn bị hai lượt chấm độc lập V2 trên 24 phiếu mới của M2 V3.1."""
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
from scripts.prepare_m2_semantic_calibration import GUIDE  # noqa: E402
from scripts.prepare_m2_semantic_review import GROUPS, ONTOLOGY, OUTPUT, indexed, output_path  # noqa: E402
from scripts.run_m2_backbone_v31 import sealed_manifest  # noqa: E402

FORM = "scripts/m2_semantic_independent_review_form.html"
VERSION = "m2-v31-tham-dinh-v2-doc-lap"


def identity(row: dict) -> set[tuple[str, ...]]:
    return {
        ("bai", row["nguon"], row["ma_bai"]),
        ("than_bai", row["body_sha256"]),
        ("fact_version", row["fact_version_id"]),
        ("claim", row["claim_id"]),
    }


def rank(row: dict) -> str:
    return sha256_text(f"{VERSION}:{row['ma_phieu']}")


def choose(rows: list[dict], relations: list[str]) -> list[tuple[str, dict]]:
    slots = []
    for group in GROUPS:
        pool = [r for r in rows if r["nhom"] == group]
        slots.extend((group, relation, [r for r in pool if r["quan_he"] == relation]) for relation in relations)
        slots.append((group, "bo_sung_phat_hanh", [r for r in pool if r["quan_he"] == "released_by"]))
        slots.append((group, "bo_sung_kieu_va_ngu_canh", [
            r for r in pool if r["quan_he"] in {"succeeded_by", "based_on"} and not r["hai_ten_co_trong_doan"]
        ]))
    slots.sort(key=lambda s: (len(s[2]), s[0], s[1]))
    require(len(slots) == 24 and all(pool for _, _, pool in slots), "Thiếu ứng viên cho một tầng đã định")
    ordered = [(purpose, sorted(pool, key=rank)) for _, purpose, pool in slots]
    picked: list[tuple[str, dict]] = []

    def fill(index: int, used: set[tuple[str, ...]]) -> bool:
        if index == len(ordered):
            return True
        purpose, pool = ordered[index]
        for row in pool:
            keys = identity(row)
            if used.isdisjoint(keys):
                picked.append((purpose, row))
                if fill(index + 1, used | keys):
                    return True
                picked.pop()
        return False

    require(fill(0, set()), "Không tìm được đủ 24 phiếu phân biệt theo thiết kế")
    return sorted(picked, key=lambda entry: rank(entry[1]))


def prepare(out: Path) -> None:
    pack = OUTPUT / "20261110_v1"
    calibration = OUTPUT / "20261111_hieu_chuan_v2"
    original = verify_artifacts(pack)
    guide_pack = verify_artifacts(calibration)
    original_hashes = original["inputs"]["hashes"]
    require(original["stage"] == "m2_v31_semantic_review_preparation"
            and guide_pack["stage"] == "m2_v31_semantic_review_calibration_preparation", "Sai gói nguồn")
    hashes: dict[str, str] = {}

    def bind(path: str, digest: str) -> Path:
        file = bound_file(ROOT, {"path": path, "sha256": digest})
        hashes[path] = digest
        return file

    for path in (pack / "experiment_manifest.json", calibration / "experiment_manifest.json",
                 ROOT / FORM, Path(__file__).resolve()):
        bind(path.relative_to(ROOT).as_posix(), sha256_file(path))
    guide_hash = guide_pack["inputs"]["config_hash"]
    bind(GUIDE, guide_hash)
    require(guide_hash == guide_pack["artifacts"]["hashes"]["huong_dan_cham_v2.md"], "Lệch hướng dẫn V2")
    ontology = yaml.safe_load(bind(ONTOLOGY, original_hashes[ONTOLOGY]).read_bytes())
    require(ontology["ontology_version"] == "1.1", "Sai ontology")
    relations = sorted(ontology["relations"])
    plan = read_json(pack / "thiet_ke_phieu.json")
    queue = pq.read_table(pack / "hang_cho_tham_dinh.parquet").to_pylist()
    previous = set(plan["ma_phieu"])
    old = [r for r in queue if r["ma_phieu"] in previous]
    require(len(old) == len(previous) == 24, "Sai phạm vi phiếu đã xem")
    excluded = set().union(*(identity(r) for r in old))
    eligible = [r for r in queue if excluded.isdisjoint(identity(r))]
    selection = choose(eligible, relations)
    bodies_path = (ACTIVE_PACKAGE / "tables/body_variants.parquet").as_posix()
    bodies = indexed(pq.read_table(bind(bodies_path, original_hashes[bodies_path])).to_pylist(), "body_variant_id")
    cases = []
    for _, row in selection:
        url = urlsplit(row["url_ban_luu"])
        require(url.scheme == "https" and url.netloc == "web.archive.org", "Sai liên kết bản lưu")
        body = bodies[row["body_variant_id"]]
        relative = (ACTIVE_PACKAGE / PureWindowsPath(body["body_blob_relative_path"]).as_posix()).as_posix()
        digest = row["body_sha256"]
        require(body["body_text_sha256"] == original_hashes[relative] == digest, "Sai mã băm thân bài")
        text = bind(relative, digest).read_bytes().decode("utf-8")
        require("\r" not in text and len(text) == body["text_char_count"], "Sai độ dài thân bài")
        for span in row["vi_tri"]:
            s, e = span["bat_dau"], span["ket_thuc"]
            require(0 <= s < e <= len(text) and text[s:e] == span["doan_trich"]
                    and sha256_text(text[s:e]) == row["span_sha256"]
                    and text[max(0, s - 420):s] == span["truoc"] and text[e:e + 420] == span["sau"],
                    "Đoạn gốc hoặc ngữ cảnh khác thân bài")
        rule = ontology["relations"][row["quan_he"]]
        cases.append({
            **{key: row[key] for key in ("ma_phieu", "vi_tri", "url_ban_luu", "body_variant_id",
                                          "body_sha256", "ma_ban_luu", "moc_ban_luu")},
            "bo_ba": [row["ten_dau"], row["quan_he"], row["ten_cuoi"]],
            "kieu_dau_cho_phep": rule["subject"], "kieu_cuoi_cho_phep": rule["object"], "than_bai": text,
        })

    template = (ROOT / FORM).read_text(encoding="utf-8")
    require(template.count("__REVIEW_DATA__") == 1, "Mẫu HTML thiếu vị trí dữ liệu")
    data = {"phien_ban": VERSION, "sha256_huong_dan": guide_hash, "sha256_mau_phieu": hashes[FORM],
            "kieu_thuc_the": ontology["entity_types"], "ca": cases}
    data["ma_bo_phieu"] = content_hash(data)
    policy = {
        "phien_ban": VERSION, "sha256_huong_dan": guide_hash,
        "loai_trung": ["nguon_va_ma_bai", "body_sha256", "fact_version_id", "claim_id"],
        "so_ca_moi_nhom": 12, "quan_he_moi_nhom": relations,
        "ca_bo_sung_moi_nhom": ["released_by", "succeeded_by_hoac_based_on_thieu_ten"],
        "thu_tu_chon": "Ưu tiên ô ít ứng viên, rồi nhóm và tiêu chí. Chọn theo SHA-256 với ràng buộc loại trùng.",
    }
    out.mkdir(parents=True, exist_ok=False)
    for role in ("A", "B"):
        embedded = json.dumps({**data, "luot": role}, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
        with (out / f"phieu_tham_dinh_v2_luot_{role}.html").open("x", encoding="utf-8") as stream:
            stream.write(template.replace("__REVIEW_DATA__", embedded))
    write_json(out / "thiet_ke_phieu_v2.json", {
        "quy_tac": policy, "ma_bo_phieu": data["ma_bo_phieu"], "so_ca_da_cham": 0,
        "so_ung_vien": len(eligible), "so_ca_theo_nhom": dict(Counter(r["nhom"] for _, r in selection)),
        "phieu": [{"ma_phieu": r["ma_phieu"], "nhom": r["nhom"], "quan_he": r["quan_he"],
                   "muc_dich": purpose} for purpose, r in selection],
    })
    sealed_manifest(out, "m2_v31_semantic_independent_review_v2_preparation", {
        **original["inputs"], "hashes": hashes, "config_hash": content_hash(policy),
        "data_hash": content_hash(hashes),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=output_path, help="Thư mục mới để lưu hai lượt A và B")
    prepare(parser.parse_args().output)


if __name__ == "__main__":
    main()
