"""Kiểm tra hồ sơ ánh xạ và tái lập mã thực thể trên bốn phiếu T01."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from itertools import product
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_text  # noqa: E402
from scripts.audit_m2_anchor_frequency_coverage import OUTPUT, RECOVERY, SEMANTIC, entity_ids  # noqa: E402
from scripts.compare_m2_semantic_independent_review import load_pack  # noqa: E402
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, timestamp  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.prepare_m2_semantic_review import indexed  # noqa: E402
from scripts.run_m2_backbone_v31 import inspect_inputs, sealed_manifest  # noqa: E402

REGISTRY = "data/manifests/entity_map_v1.json"
BUNDLE = "runs/production_v3/inputs/proposed_config_bundle.yaml"
M1_CODE = ("src/kg_pipeline/adjudicate.py", "src/kg_pipeline/adjudication.py")


def audit_history(m1: Path) -> dict:
    command = ["git", f"--git-dir={m1 / '.git'}", f"--work-tree={m1}"]

    def git(*args: str) -> str:
        return subprocess.run(
            [*command, *args], check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

    history = []
    for row in git("log", "--all", "--format=%H %cI", "--", REGISTRY).splitlines():
        commit, when = row.split()
        size = git("ls-tree", "-l", commit, "--", REGISTRY).split()
        history.append({"commit": commit, "thoi_diem_commit": when, "so_byte": int(size[3]) if size else None})
    require(history and all(r["so_byte"] in (None, 0) for r in history),
            "Lịch sử có phiên bản danh mục chứa dữ liệu, cần kiểm tra nội dung và hiệu lực")
    mapping_history = git("log", "--all", "--format=%H", "--", "*entity_mapping_versions*", "*mapping_decision*")
    require(not mapping_history, "Có lịch sử tệp ánh xạ cần kiểm tra hiệu lực")
    return {"m1_head": git("rev-parse", "HEAD"), "lich_su_tep_danh_muc": history}


def replay_pair(quote: dict, names: list[str]) -> list[dict]:
    matches = []
    for name in names:
        pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
        matches.append([
            m for m in re.finditer(pattern, quote["doan_trich"], flags=re.IGNORECASE)
            if m[0].lower() == name.lower()
        ])
    selected = next(((a, b) for a, b in product(*matches) if a.end() <= b.start() or b.end() <= a.start()), None)
    require(selected is not None, "Thiếu hai tên độc lập trong đoạn đã chốt")
    base = quote["bat_dau"]
    return [{
        "ten_trong_doan": m[0],
        "bat_dau": base + m.start(), "ket_thuc": base + m.end(),
        "ma_tai_lap": f"ent_{sha256_text(m[0].strip().lower())[:8]}",
    } for m in selected]


def audit(out: Path) -> None:
    coverage = OUTPUT / "20261111_do_phu_tan_suat_v1"
    queue_dir = SEMANTIC / "20261110_v1"
    pack = SEMANTIC / "20261111_ban_giao_ab_v2"
    datasets, _, clocks, hashes = inspect_inputs()
    scope = verify_artifacts(coverage)
    verify_artifacts(queue_dir)
    verify_artifacts(RECOVERY)
    _, issued, _ = load_pack(pack)
    cases = indexed(issued["ca"], "ma_phieu")
    for p, h in scope["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": p, "sha256": h})
    cutoff = timestamp(clocks["T01"]["cutoff"])
    persistent = set(datasets["T01"].entities) & set(datasets["T02"].entities)
    candidates = [r for r in read_json(coverage / "phieu_dat_noi_dung_cho_anh_xa.json")
                  if timestamp(r["moc_ban_luu"]) <= cutoff and entity_ids(r) & persistent]
    require(len(candidates) == 4 and len(set().union(*(entity_ids(r) for r in candidates))) == 8,
            "Phạm vi thử khác bốn phiếu và tám thực thể T01")

    reference = read_json(RECOVERY / "dau_vao_m1.json")
    m1 = Path(reference["root"]).resolve()
    require(m1 == (ROOT.parent / "evolving-kg-drift-m1/evolving-kg-drift").resolve(), "Sai kho M1 gốc")
    external = {}
    for path in (*M1_CODE, REGISTRY, BUNDLE):
        digest = sha256_file(m1 / path)
        bound_file(m1, {"path": path, "sha256": digest})
        if path in M1_CODE:
            require(reference["hashes"][path] == digest, "Mã tái lập khác nguồn M1 đã kiểm")
        external[path] = digest
    bundle_path = (ACTIVE_PACKAGE / "inputs/proposed_config_bundle.yaml").as_posix()
    bundle = bound_file(ROOT, {"path": bundle_path, "sha256": external[BUNDLE]})
    require(not yaml.safe_load(bundle.read_bytes()).get("entity_catalog")
            and (m1 / REGISTRY).stat().st_size == 0, "Tìm thấy danh mục ánh xạ cần kiểm tra")
    history = audit_history(m1)

    queue = indexed(pq.read_table(queue_dir / "hang_cho_tham_dinh.parquet").to_pylist(), "ma_phieu")
    facts_path = (ACTIVE_PACKAGE / "tables/fact_versions.parquet").as_posix()
    facts_digest = scope["inputs"]["hashes"][facts_path]
    facts = indexed(pq.read_table(bound_file(ROOT, {"path": facts_path, "sha256": facts_digest})).to_pylist(),
                    "fact_version_id")
    recovery = pq.read_table(RECOVERY / "bang_truy_vet_ung_vien.parquet",
                             columns=["fact_version_id", "mapping_available_at_verified"]).to_pylist()
    results = []
    for row in candidates:
        key = row["ma_phieu"]
        case, source, fact = cases[key], queue[key], facts[row["fact_version_id"]]
        quote = row["doan_quyet_dinh"]
        start, end = quote["bat_dau"], quote["ket_thuc"]
        body = case["than_bai"]
        require(body[start:end] == quote["doan_trich"] and sha256_text(body) == row["body_sha256"]
                and sha256_text(quote["doan_trich"]) == row["span_sha256"], "Sai đoạn đã chốt")
        names = [source["ten_dau"], source["ten_cuoi"]]
        ids = [source["thuc_the_dau_id"], source["thuc_the_cuoi_id"]]
        require(ids == [fact["subject_id"], fact["object_id"]] and set(ids) <= persistent,
                "Sai mã FactVersion hoặc giao T01–T02")
        traced = [r for r in recovery if r["fact_version_id"] == row["fact_version_id"]]
        require(traced and all(r["mapping_available_at_verified"] is None for r in traced)
                and fact["entity_map_version"] == "v1_mock", "Hồ sơ ánh xạ khác phạm vi tái lập")
        replayed = replay_pair(quote, names)
        for role, item, entity in zip(("DAU", "CUOI"), replayed, ids, strict=True):
            require(item["ma_tai_lap"] == entity
                    and body[item["bat_dau"]:item["ket_thuc"]] == item["ten_trong_doan"], "Mã tái lập khác V3.1")
            results.append({
                **item, "vai_tro": role, "thuc_the_id_v31": entity, "ma_phieu": key,
                "fact_version_id": row["fact_version_id"], "ma_ban_luu": row["ma_ban_luu"],
                "moc_ban_luu": row["moc_ban_luu"], "body_sha256": row["body_sha256"],
                "span_sha256": row["span_sha256"], "entity_map_version": fact["entity_map_version"],
                "ingested_at_real": fact["ingested_at_real"],
                "mapping_available_at_verified": None, "trang_thai": "TAI_LAP_DUOC_MA_THIEU_MOC_ANH_XA",
            })
    require(len({r["thuc_the_id_v31"] for r in results}) == len(results) == 8, "Trùng mã trong phạm vi thử")
    hashes[bundle_path] = external[BUNDLE]
    hashes[facts_path] = facts_digest
    for file in (*(p / "experiment_manifest.json" for p in (coverage, queue_dir, pack, RECOVERY)),
                 ROOT / "config/schema.yaml", Path(__file__).resolve()):
        hashes[file.relative_to(ROOT).as_posix()] = sha256_file(file)

    policy = {
        "pham_vi": "Thử tái lập mã từ tên trong đoạn của đúng bản lưu đến cutoff T01",
        "tai_lap": "ent_ + 8 ký tự đầu SHA-256 của tên UTF-8 sau strip().lower()",
        "moc_anh_xa": "Căn cứ lịch sử độc lập cho từng ánh xạ",
    }
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "doi_chieu_anh_xa_t01.json", {
        "quy_tac": policy, "chuyen_tiep": "T01->T02", "cutoff_nguon_utc": cutoff.isoformat(),
        "so_phieu": len(candidates), "so_thuc_the_tai_lap_dung_ma": len(results),
        "so_thuc_the_xac_minh_moc_anh_xa": 0, "du_dieu_kien_tinh_tan_suat": False,
        "lich_su_m1": history, "ten_theo_phieu": results,
    })
    write_json(out / "dau_vao_m1.json", {"root": str(m1), "hashes": external})
    sealed_manifest(out, "m2_v31_anchor_mapping_replay_diagnostic", {
        **scope["inputs"], "hashes": hashes, "config_hash": content_hash(policy),
        "external_input_index_sha256": sha256_file(out / "dau_vao_m1.json"),
        "data_hash": content_hash({"noi_bo": hashes, "m1": external, "lich_su_m1": history}),
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
