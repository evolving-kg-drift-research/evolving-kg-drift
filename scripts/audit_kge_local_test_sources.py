"""Đối chiếu các gói dữ liệu cục bộ có thể dùng cho kiểm thử TransE-L2."""
from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    COLUMNS, FEASIBILITY, RELEASE, ROOT, bound_file, get_git_info, read_json, require,
    sha256_file, timestamp, validate_manifest, verify_artifacts, write_json,
)

RECOVERY = "outputs/upstream_recovery_release_20261014"
QA_EXPORT = "reports/qa_benchmark_147_human_readable.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục kết quả mới dưới outputs/")
    hashes: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        digest = expected if expected is not None else sha256_file(ROOT / relative)
        require(hashes.setdefault(relative, digest) == digest, f"Mã băm không nhất quán: {relative}")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    previous = verify_artifacts(ROOT / FEASIBILITY)
    bind(f"{FEASIBILITY}/experiment_manifest.json")
    previous_hashes = previous["inputs"]["hashes"]
    audit = read_json(bind(f"{FEASIBILITY}/audit.json", previous["artifacts"]["hashes"]["audit.json"]))
    release_path = f"{RELEASE}/release_manifest.json"
    release = read_json(bind(release_path, previous_hashes[release_path]))
    release_hashes = {item["path"]: item["sha256"] for item in release["artifacts"]}
    require(len(audit["snapshot_rows"]) == release["snapshot_count"] == 10, "Số snapshot không khớp")

    columns = COLUMNS[:3]
    canonical = set()
    for row in audit["snapshot_rows"]:
        relative = f"snapshots/snapshot_{row['snapshot']}_canonical.parquet"
        path = f"{RELEASE}/{relative}"
        require(previous_hashes[path] == release_hashes[relative], f"Khác dữ liệu đã rà soát: {path}")
        table = pq.read_table(bind(path, release_hashes[relative]), columns=columns)
        canonical.update(zip(*(table[name].to_pylist() for name in columns), strict=True))
    require(len(canonical) == audit["unique_triples_previously_in_full_snapshot_training"],
            "Số bộ ba khác kiểm kê lịch sử huấn luyện")

    matched_copies = {}
    for name in ("body_variants", "extracted_claims", "fact_versions", "kg_events"):
        relative = f"tables/{name}.parquet"
        original = bind(f"{RELEASE}/{relative}", release_hashes[relative])
        copy_path = bind(f"data/transe_fact_check_package/{name}.parquet")
        matched_copies[name] = {"trung_ma_bam": hashes[copy_path.relative_to(ROOT).as_posix()]
                                == release_hashes[relative], "so_dong": pq.ParquetFile(original).metadata.num_rows}
    facts_path = f"{RELEASE}/tables/fact_versions.parquet"
    facts = pq.read_table(ROOT / facts_path, columns=COLUMNS)
    fact_triples = set(zip(*(facts[name].to_pylist() for name in columns), strict=True))
    events_path = f"{RELEASE}/tables/kg_events.parquet"
    events = pq.read_table(ROOT / events_path, columns=columns)
    event_triples = set(zip(*(events[name].to_pylist() for name in columns), strict=True))
    latest = timestamp(audit["snapshot_rows"][-1]["cutoff"])
    after_last = sum(timestamp(v) > latest for v in facts["evidence_observed_at"].to_pylist())
    partial_path = "tables/extracted_claims_partial.parquet"
    partial = pq.ParquetFile(bind(f"{RELEASE}/{partial_path}", release_hashes[partial_path]))
    bind(f"{RELEASE}/RELEASE_V3_1.md", release_hashes["RELEASE_V3_1.md"])

    recovery = read_json(bind(f"{RECOVERY}/dataset_manifest.json"))
    for item in recovery["package_files"]:
        path = bind(f"{RECOVERY}/{item['filename']}", item["sha256"])
        require(path.stat().st_size == item["size_bytes"], "Kích thước gói phục hồi không khớp")
    qa = read_json(bind(QA_EXPORT))
    bind("scripts/export_human_readable_qa.py")
    bind("docs/audit/M1_V3_1_INTAKE_REVIEW_20261021.md")
    bind("docs/gates_and_freeze.md")
    bind("configs/protocol_v1.yaml", previous_hashes["configs/protocol_v1.yaml"])
    bind("data/manifests/README.md")
    placeholder_names = ("entity_map_v1.json", "relation_manifest.json", "snapshot_manifest.json", "source_manifest.json")
    placeholders = {name: bind(f"data/manifests/{name}").stat().st_size for name in placeholder_names}
    script = Path(__file__).resolve()
    bind(script.relative_to(ROOT).as_posix())
    result = {
        "pham_vi": "Kiểm kê cục bộ các gói dữ liệu và bằng chứng sử dụng đã xác định",
        "bo_ba_phan_biet_T01_T10": len(canonical),
        "fact_versions": {"so_phien_ban": len(facts), "so_bo_ba_phan_biet": len(fact_triples),
                          "bo_ba_ngoai_T01_T10": len(fact_triples - canonical),
                          "bo_ba_canonical_thieu_trong_bang": len(canonical - fact_triples),
                          "so_dong_co_moc_quan_sat_sau_T10": after_last},
        "kg_events": {"so_dong": len(events), "so_bo_ba_phan_biet": len(event_triples),
                      "bo_ba_ngoai_T01_T10": len(event_triples - canonical),
                      "bo_ba_canonical_thieu_trong_bang": len(canonical - event_triples)},
        "goi_kiem_tra_du_kien": matched_copies,
        "so_dong_trich_xuat_chan_doan": partial.metadata.num_rows,
        "goi_phuc_hoi": {"loai": recovery["release_type"], "san_sang_san_xuat": recovery["production_ready"],
                         "xac_minh_ma_bam_goi_nen": True},
        "so_dong_ban_xuat_hoi_dap": len(qa),
        "kich_thuoc_tep_ke_khai_chua_dien": placeholders,
    }
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "kiem_ke_nguon.json"
    write_json(result_path, result)
    commit, dirty = get_git_info(ROOT)
    manifest = {
        "experiment_id": output.name, "protocol_version": previous["protocol_version"], "seed": None,
        "stage": "local_independent_test_source_audit", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty}, "inputs": {**previous["inputs"], "hashes": hashes},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": script.name},
        "artifacts": {"hashes": {result_path.name: sha256_file(result_path)}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
