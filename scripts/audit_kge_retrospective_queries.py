"""Rà soát dữ liệu và truy vấn đã dùng trong đối chứng hồi cứu T01."""
from __future__ import annotations

import argparse
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    COLUMNS, FEASIBILITY, RELEASE, ROOT, Triple, bound_file, get_git_info, read_json,
    require, sha256_file, timestamp, validate_manifest, verify_artifacts, write_json,
)

CANDIDATE = "outputs/kge_retrospective_t01_candidate/20261104_t01_v2"
SCORING = "outputs/kge_retrospective_t01_scoring/20261104_t01_v2"
SIDES = ("head", "tail")


def query_key(triple: Triple, side: str) -> Triple:
    h, r, t = triple
    return (side, r, t) if side == "head" else (side, h, r)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục kết quả mới dưới outputs/")
    manifests = {folder: verify_artifacts(ROOT / folder) for folder in (CANDIDATE, SCORING, FEASIBILITY)}
    inputs = {}
    for folder, manifest in manifests.items():
        path = f"{folder}/experiment_manifest.json"
        inputs[path] = sha256_file(ROOT / path)
        for relative, digest in manifest["artifacts"]["hashes"].items():
            inputs[f"{folder}/{relative}"] = digest
        for relative, digest in manifest["inputs"]["hashes"].items():
            require(inputs.setdefault(relative, digest) == digest, f"Mã băm không nhất quán: {relative}")
    script = Path(__file__).resolve()
    inputs[script.relative_to(ROOT).as_posix()] = sha256_file(script)
    for relative, digest in inputs.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})

    design = read_json(ROOT / CANDIDATE / "design.json")
    queries = read_json(ROOT / CANDIDATE / "queries.json")
    members = read_json(ROOT / CANDIDATE / "members.json")
    snapshots = read_json(ROOT / CANDIDATE / "preflight.json")["snapshot_records"]
    split = read_json(ROOT / design["baseline"]["training_split"])
    train, validation = (set(map(tuple, split[key])) for key in ("train", "validation"))
    entities = {entity for h, _, t in train for entity in (h, t)}
    relations = {r for _, r, _ in train}
    require(set(design["candidates"]) == entities and len(entities) == len(design["candidates"]),
            "Danh sách ứng viên khác tập huấn luyện")
    train_keys, validation_keys = ({query_key(triple, side) for triple in rows for side in SIDES}
                                   for rows in (train, validation))
    snapshot_rows = {}
    first = {}
    for sid, record in sorted(snapshots.items()):
        path = f"{RELEASE}/snapshots/snapshot_{sid}_canonical.parquet"
        table = pq.read_table(bound_file(ROOT, {"path": path, "sha256": inputs[path]}), columns=COLUMNS)
        rows = {}
        for row in table.to_pylist():
            triple = tuple(row[column] for column in COLUMNS[:3])
            observed = timestamp(row[COLUMNS[3]])
            require(observed <= timestamp(record["cutoff"]) and triple not in rows, f"Dòng lỗi tại {sid}")
            rows[triple] = observed
            first.setdefault(triple, sid)
        snapshot_rows[sid] = rows
    require(set(snapshot_rows["T01"]) == train | validation and not train & validation, "Phân hoạch T01 sai")
    later = set(first) - snapshot_rows["T01"].keys()
    eligible = {(h, r, t) for h, r, t in later if h in entities and t in entities and r in relations}
    expected_members = {(first[triple], triple) for triple in eligible}
    require(len(members) == len(expected_members)
            and {(m["snapshot"], tuple(m["triple"])) for m in members} == expected_members,
            "Thành viên hồi cứu không khớp")
    for member in members:
        triple = tuple(member["triple"])
        require(all(member[f"{side}_key_in_prior_validation"] == (query_key(triple, side) in validation_keys)
                    for side in SIDES), "Cờ trùng khóa xác thực không khớp")
    expected_queries = {(sid, triple, side) for sid, triple in expected_members for side in SIDES}
    require(len(queries) == len(expected_queries) == len({q["query_id"] for q in queries})
            and {(q["snapshot"], tuple(q["triple"]), q["side"]) for q in queries} == expected_queries,
            "Truy vấn thiếu, trùng hoặc không khớp thành viên")

    keys = Counter()
    contextual_keys = Counter()
    overlaps = Counter()
    mask_sizes = Counter()
    for query in queries:
        sid, triple, side = query["snapshot"], tuple(query["triple"]), query["side"]
        key = query_key(triple, side)
        target_index = 0 if side == "head" else 2
        require(query["target"] == triple[target_index] and triple in snapshot_rows[sid], "Đáp án không khớp")
        other_truths = {row[target_index] for row in snapshot_rows[sid] if query_key(row, side) == key}
        mask = (other_truths & entities) - {query["target"]}
        require(sorted(mask) == query["filtered_entities"]
                and query["candidate_count_after_filter"] == len(entities - mask), "Bộ lọc không khớp")
        keys[key] += 1
        contextual_keys[(sid, *key)] += 1
        overlaps[(key in train_keys, key in validation_keys)] += 1
        mask_sizes[len(mask)] += 1
    expected_ids = {q["query_id"]: [e for e in design["candidates"] if e not in q["filtered_entities"]] for q in queries}
    ranks = read_json(ROOT / SCORING / "thu_hang.json")
    require(set(ranks) == {"tan_suat", "13", "37", "101"}, "Thiếu phương pháp chấm hoặc mã khởi tạo")
    for method, rows in ranks.items():
        require(len(rows) == len(expected_ids)
                and {r["query_id"]: [e for e, _ in r["candidate_scores"]] for r in rows} == expected_ids,
                f"Ứng viên lúc chấm không khớp: {method}")
    baseline = ranks["tan_suat"]
    distribution = Counter(r for _, r, _ in later)
    sample_relations = Counter(r for _, r, _ in eligible)
    oov = Counter(int(h not in entities) + int(t not in entities) for h, _, t in later)
    cutoff_t01 = timestamp(snapshots["T01"]["cutoff"])
    audit = {
        "so_bo_ba_sau_T01": len(later), "so_bo_ba_hoi_cuu": len(eligible),
        "so_bo_ba_co_quan_he_ngoai_tap_huan_luyen": sum(r not in relations for _, r, _ in later),
        "phan_bo_so_dau_thuc_the_ngoai_tap_huan_luyen": dict(oov),
        "phan_bo_quan_he": {r: {"sau_T01": count, "trong_mau": sample_relations[r]}
                           for r, count in sorted(distribution.items())},
        "phan_bo_bo_ba_theo_snapshot": dict(Counter(first[t] for t in eligible)),
        "so_thuc_the_dap_an": len({q["target"] for q in queries}),
        "so_lan_xuat_hien_cua_hai_dap_an_pho_bien_nhat": sorted(
            Counter(q["target"] for q in queries).values(), reverse=True)[:2],
        "so_dong_truy_van": len(queries), "so_khoa_khong_ke_snapshot": len(keys),
        "so_khoa_ke_snapshot": len(contextual_keys),
        "so_nhom_nhieu_dap_an_trong_cung_snapshot": sum(n > 1 for n in contextual_keys.values()),
        "trung_khoa_voi_tap_huan_luyen": sum(n for (a, _), n in overlaps.items() if a),
        "trung_khoa_voi_tap_xac_thuc": sum(n for (_, b), n in overlaps.items() if b),
        "trung_khoa_voi_ca_hai_tap": overlaps[True, True],
        "phan_bo_so_ung_vien_bi_loc": dict(mask_sizes),
        "so_bo_ba_co_moc_quan_sat_trong_hien_vat_sau_T01": sum(
            snapshot_rows[sid][triple] > cutoff_t01 for sid, triple in expected_members),
        "so_truy_van_co_dap_an_dong_diem_cao_nhat_theo_tan_suat": sum(r["better"] == 0 for r in baseline),
        "so_truy_van_co_dap_an_dong_diem_tan_suat_voi_it_nhat_100_ung_vien": sum(
            r["tied_including_target"] > 100 for r in baseline),
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "kiem_toan_truy_van.json", audit)
    commit, dirty = get_git_info(ROOT)
    source = manifests[CANDIDATE]
    manifest = {
        "experiment_id": output.name, "protocol_version": source["protocol_version"], "seed": None,
        "stage": "retrospective_query_audit", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty}, "inputs": {**source["inputs"], "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": script.name},
        "artifacts": {"hashes": {"kiem_toan_truy_van.json": sha256_file(output / "kiem_toan_truy_van.json")}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
