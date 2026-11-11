"""Lập hồ sơ tám ánh xạ và rà bản lưu tìm tên ba dòng hệ điều hành ở T01."""
from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from collections import Counter
from pathlib import Path, PureWindowsPath

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.hashing import sha256_json, sha256_text  # noqa: E402
from kg_pipeline.inventory import extract_body  # noqa: E402
from scripts.audit_m2_anchor_frequency_coverage import OUTPUT, RECOVERY, TIME  # noqa: E402
from scripts.audit_m2_anchor_mapping_t01_full import name_spans  # noqa: E402
from scripts.inspect_m2_inputs import ACTIVE_PACKAGE, timestamp  # noqa: E402
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    bound_file, content_hash, read_json, require, sha256_file, verify_artifacts, write_json,
)
from scripts.prepare_m2_semantic_review import indexed  # noqa: E402
from scripts.run_m2_backbone_v31 import sealed_manifest  # noqa: E402

V2 = "data/stage_4_4_runs/stage4_4_final_canonical_v2/raw_acquisition_events.parquet"
TARGETS = ("iOS", "iPadOS", "macOS")
REVIEWED = {
    "iOS": ("4882718", "hệ điều hành iOS", 2506),
    "macOS": ("4883254", "macOS nhận được bản cập nhật", 2116),
}


def audit(out: Path) -> None:
    policy_run = OUTPUT / "20261111_duyet_anh_xa_t01_v1"
    replay = OUTPUT / "20261111_kiem_tra_anh_xa_t01_v1"
    prior = OUTPUT / "20261111_tai_lap_anh_xa_toan_t01_v1"
    alt = TIME / "20261110_doan_trich_v1"
    sources = {p: verify_artifacts(p) for p in (policy_run, replay, prior, RECOVERY, alt, OUTPUT / "20261110_v1")}
    approval = read_json(policy_run / "quyet_dinh_anh_xa_t01.json")
    pilot = read_json(replay / "doi_chieu_anh_xa_t01.json")
    cutoff = timestamp(approval["phuong_an"]["cutoff_nguon_utc"])
    require(approval["trang_thai"] == "DA_DUYET_PHUONG_AN_CHUAN_BI_VA_KIEM_CHUNG"
            and cutoff == timestamp(pilot["cutoff_nguon_utc"]), "Sai quy tắc đã duyệt")
    for p, h in sources[policy_run]["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": p, "sha256": h})
    external_index = read_json(alt / "dau_vao_m1.json")
    m1 = Path(external_index["root"]).resolve()
    require(m1 == (ROOT.parent / "evolving-kg-drift-m1/evolving-kg-drift").resolve(), "Sai kho M1")
    hashes = {(p / "experiment_manifest.json").relative_to(ROOT).as_posix():
              sha256_file(p / "experiment_manifest.json") for p in sources}
    external: dict[str, str] = {}

    def m1_file(relative: str, expected: str | None = None) -> Path:
        digest = expected or external_index["hashes"].get(relative) or sha256_file(m1 / relative)
        require(external.setdefault(relative, digest) == digest, "Mã băm nguồn M1 khác hồ sơ")
        return bound_file(m1, {"path": relative, "sha256": digest})

    release_file = ROOT / ACTIVE_PACKAGE / "release_manifest.json"
    hashes[release_file.relative_to(ROOT).as_posix()] = sha256_file(release_file)
    inventory = {r["path"]: r["sha256"] for r in read_json(release_file)["artifacts"]}

    def package_file(relative: str) -> Path:
        path = (ACTIVE_PACKAGE / relative).as_posix()
        digest = inventory[relative]
        hashes[path] = digest
        return bound_file(ROOT, {"path": path, "sha256": digest})

    def table(relative: str) -> list[dict]:
        return pq.read_table(package_file(relative)).to_pylist()

    recovery = pq.read_table(RECOVERY / "bang_truy_vet_ung_vien.parquet").to_pylist()
    alternate = pq.read_table(alt / "bang_doan_trich_trong_ban_luu_khac.parquet").to_pylist()
    members = {r["raw_blob_sha256"]: r["body_variant_id"] for r in table("tables/document_memberships.parquet")}
    variants = indexed(table("tables/body_variants.parquet"), "body_variant_id")
    raw = indexed(table("tables/raw_inventory.parquet"), "raw_blob_sha256")
    raw_refs = indexed(read_json(package_file("inputs/raw_blob_reference_manifest.json"))["entries"], "sha256")
    article_id = runpy.run_path(str(OUTPUT / "20261110_v1/kiem_tra.py"))["article_id"]
    archive_consistency = runpy.run_path(str(RECOVERY / "khoi_phuc.py"))["archive_consistency"]
    events = pq.read_table(m1_file(V2)).to_pylist()
    eligible = [e for e in events if e["acquisition_mode"] == "historical_wayback_article"
                and e["version_eligible"] is True and e["archive_or_revision_datetime"]
                and timestamp(e["archive_or_revision_datetime"]) <= cutoff]
    captures = {}

    def add_capture(bid: str, raw_sha: str, url: str, observed: str, src: str, article: str,
                    proof: str, event: dict | None = None) -> None:
        require(members[raw_sha] == bid and timestamp(observed) <= cutoff, "Sai nối bản lưu hoặc cutoff")
        key = (bid, raw_sha, url, timestamp(observed))
        captures.setdefault(key, {
            "body_variant_id": bid, "raw_sha256": raw_sha, "url_ban_luu": url,
            "moc_ban_luu_utc": timestamp(observed).isoformat(), "nguon": src, "ma_bai": article,
            "can_cu": proof, "event": event,
        })

    for e in eligible:
        raw_sha = e["content_hash_sha256"]
        src, article = article_id(e["source_id"], e["final_url"])
        add_capture(members[raw_sha], raw_sha, e["final_url"], e["archive_or_revision_datetime"],
                    src, article, "STAGE_4_4_V2", e)
    for r in recovery:
        clock = r["archive_datetime_corroborated"]
        if clock and r["raw_body_matches_v31"] and timestamp(clock) <= cutoff:
            add_capture(r["body_variant_id"], r["raw_blob_sha256"], r["url_final"], clock, r["source_id"],
                        r["publisher_article_id"], "HO_SO_KHOI_PHUC")
    for r in alternate:
        if r["archive_datetime_utc"] <= cutoff:
            add_capture(r["archive_body_variant_id"], r["archive_raw_sha256"], r["archive_url"],
                        r["archive_datetime_utc"].isoformat(), r["source_id"], r["publisher_article_id"],
                        "HO_SO_BAN_LUU_BO_SUNG")

    log_cache = {}
    validated: set[str] = set()

    def verify_capture(c: dict, text: str) -> dict:
        event = c["event"]
        extra = {}
        if event is not None:
            run_id = event["run_id"]
            require(re.fullmatch(r"stage4_4_[a-zA-Z0-9_]+", run_id) is not None, "Sai mã lượt thu")
            rel = f"data/stage_4_4_runs/{run_id}/raw_acquisition_log.jsonl"
            if rel not in log_cache:
                log_cache[rel] = {
                    item["acquisition_event_id"]: (number, item)
                    for number, line in enumerate(m1_file(rel).read_bytes().splitlines(), 1)
                    if (item := json.loads(line)).get("acquisition_event_id")
                }
            number, record = log_cache[rel][event["acquisition_event_id"]]
            require(all(event[k] == record[k] for k in (
                "content_hash_sha256", "final_url", "source_id", "http_status", "http_headers_json",
                "archived_original_url", "archive_original_matches_url",
            )) and record["http_status"] == 200 and record["version_eligible"] is True
                    and timestamp(record["archive_or_revision_datetime"]) == timestamp(c["moc_ban_luu_utc"]),
                    "Nhật ký khác bản lưu Stage 4.4")
            observed = archive_consistency(record, {
                "archive_datetime": record["archive_or_revision_datetime"], "final_url": event["final_url"],
                "source_id": event["source_id"], "retrieved_at_real": record["retrieved_at_real"],
            }, (c["nguon"], c["ma_bai"]), article_id)
            require(observed is not None and timestamp(observed) == timestamp(c["moc_ban_luu_utc"]), "Sai mốc bản lưu")
            extra = {"ma_lan_thu": event["acquisition_event_id"], "nhat_ky_m1": rel,
                     "dong_nhat_ky": number, "sha256_ban_ghi": sha256_json(record)}
        digest = c["raw_sha256"]
        if digest not in validated:
            ref = raw_refs[digest]
            f = m1_file(ref["relative_path"], digest)
            require(f.stat().st_size == ref["bytes"]
                    and extract_body(f, raw[digest]["content_type_detected"])["body_text"] == text, "Sai thân bài HTML")
            validated.add(digest)
        return {**{k: v for k, v in c.items() if k != "event"}, **extra}

    grouped: dict[str, list[dict]] = {}
    for c in captures.values():
        grouped.setdefault(c["body_variant_id"], []).append(c)
    hits = []
    for bid, group in sorted(grouped.items()):
        row = variants[bid]
        path = PureWindowsPath(row["body_blob_relative_path"]).as_posix()
        text = package_file(path).read_bytes().decode("utf-8")
        require(sha256_text(text) == row["body_text_sha256"], "Sai mã băm thân bài")
        found = [(target, s, e) for target in TARGETS for s, e in name_spans(text, target)]
        if not found:
            continue
        verified = [verify_capture(c, text) for c in sorted(group, key=lambda c: c["moc_ban_luu_utc"])]
        for target, s, e in found:
            version = bool(re.match(r"\s+v?\d+(?=[\W_]|$)", text[e:], re.IGNORECASE))
            first, last = max(0, s - 90), min(len(text), e + 105)
            hits.append({
                "ten_dong": target, "ten_nguyen_van": text[s:e], "bat_dau": s, "ket_thuc": e,
                "bat_dau_ngu_canh": first, "ket_thuc_ngu_canh": last, "ngu_canh": text[first:last],
                "body_sha256": row["body_text_sha256"], "gan_so_phien_ban": version, "ban_luu": verified,
                "ma_tai_lap_tu_ten": f"ent_{sha256_text(text[s:e].strip().lower())[:8]}",
            })

    scope_rows = read_json(prior / "doi_chieu_toan_bo_t01.json")["theo_thuc_the"]
    os_ids = {r["ten_trong_ho_so"][0]: r["thuc_the_id"] for r in scope_rows if r["ten_trong_ho_so"][0] in TARGETS}
    checked_names = {}
    for name, (article, fragment, offset) in REVIEWED.items():
        matches = [h for h in hits if h["ten_dong"] == name and not h["gan_so_phien_ban"]
                   and h["bat_dau"] == offset and fragment in h["ngu_canh"]
                   and any(c["ma_bai"] == article for c in h["ban_luu"])]
        require(len(matches) == 1 and matches[0]["ma_tai_lap_tu_ten"] == os_ids[name], "Sai đoạn tên đã rà")
        checked_names[name] = matches[0]

    focus = {r["fact_version_id"] for r in pilot["ten_theo_phieu"]}
    relevant = [r for r in recovery if r["fact_version_id"] in focus]
    require(relevant and all(r["mapping_available_at_verified"] is None for r in relevant)
            and m1_file("data/manifests/entity_map_v1.json").stat().st_size == 0
            and not (m1 / "runs/production_v3/tables/entity_mapping_versions.parquet").is_file(),
            "Có dữ liệu ánh xạ cần đánh giá riêng")
    dossier = [{**r, "so_dong_truy_vet_da_kiem": sum(x["fact_version_id"] == r["fact_version_id"] for x in relevant)}
               for r in pilot["ten_theo_phieu"]]
    config = {
        "pham_vi": "Hồ sơ ánh xạ T01 và rà bản lưu cục bộ tìm tên hệ điều hành",
        "cutoff_nguon_utc": cutoff.isoformat(), "quy_tac_da_duyet": approval["phuong_an"]["phien_ban"],
        "gop_ban_luu": "Stage 4.4 v2 đủ điều kiện và bản lưu đã xác minh ở hai lượt trước",
    }
    hashes[Path(__file__).resolve().relative_to(ROOT).as_posix()] = sha256_file(Path(__file__))
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "ho_so_8_anh_xa_t01.json", {
        "so_anh_xa": len(dossier), "so_moc_hieu_luc_da_xac_minh": 0, "ho_so": dossier,
    })
    write_json(out / "ban_luu_ten_he_dieu_hanh_t01.json", {
        "quy_tac": config, "so_lan_thu_stage_4_4": len(eligible), "so_ban_luu_khong_trung": len(captures),
        "so_than_bai_da_quet": len(grouped), "so_html_tai_tao_lai": len(validated),
        "so_khop_ten": dict(Counter(h["ten_dong"] for h in hits)),
        "ten_dong_nguyen_van_da_doi_chieu": checked_names, "ten_dong_cho_can_cu": ["iPadOS"],
        "ket_qua_tim_ten": hits,
    })
    write_json(out / "dau_vao_m1.json", {"root": str(m1), "hashes": external})
    sealed_manifest(out, "m2_v31_anchor_mapping_t01_evidence_diagnostic", {
        **sources[policy_run]["inputs"], "hashes": hashes, "config_hash": content_hash(config),
        "external_input_index_sha256": sha256_file(out / "dau_vao_m1.json"),
        "data_hash": content_hash({"noi_bo": hashes, "m1": external}),
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
