"""Kiểm kê trạng thái và đối chiếu hiện vật dự án ở chế độ chỉ đọc đầu vào."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import pyarrow.parquet as pq
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    RELEASE, ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from kg_pipeline.contract_authority import audit_machine_contract  # noqa: E402
from kg_pipeline.gates import evaluate_scientific_gate  # noqa: E402
from scripts.inspect_m2_reuse import inspect_backbone  # noqa: E402
from scripts.run_m2_measurement_v2 import inspect_registration  # noqa: E402
from scripts.verify_m2_alignment import verify as verify_alignment  # noqa: E402

BACKBONE = "outputs/m2_backbone/20261014T034042Z_65c464ba"
ALIGNMENT = "outputs/m2_alignment/20261014T040001Z_96d9ccbc"
DEV = "outputs/kge_validation_dev/20261103_t01_three_seed_v1"
OLD_RUNS = {
    "nhieu": "outputs/m2_null_v2/20261027T190109Z_e6d40655",
    "do_troi": "outputs/m2_drift_v2/20261027T190838Z_ea66c2af",
    "hoi_dap": "outputs/m4_eval/20261028T070316Z_064921be",
    "thong_ke": "outputs/m4_stats/20261028T070316Z_064921be",
}
RECENT_RUNS = (
    "outputs/kge_retrospective_t01_scoring/20261104_t01_v2",
    "outputs/kge_retrospective_query_audit/20261104_t01_v1",
    "outputs/kge_local_test_source_audit/20261104_v1",
    "outputs/kge_independent_source_proposal/20261104_v1",
    "outputs/kge_prospective_readiness/20261104_v1",
    "outputs/kge_prospective_registration_rehearsal/20261104_v1",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and not output.exists() and all(p.lower() != "locked_test" for p in output.parts),
            "Cần thư mục mới dưới outputs/")
    hashes: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        path = workspace_path(relative)
        digest = expected if expected is not None else sha256_file(path)
        require(hashes.setdefault(relative, digest) == digest, f"Mã băm không nhất quán: {relative}")
        return bound_file(ROOT, {"path": relative, "sha256": digest})

    def workspace_path(relative: str) -> Path:
        path = (ROOT / relative).resolve()
        require(not Path(relative).is_absolute() and path.is_relative_to(ROOT)
                and all(part.lower() != "locked_test" for part in path.parts), "Tệp ngoài phạm vi rà soát")
        return path

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")

    pathspec = (".", ":!data/locked_test", ":!data/locked_test/**")
    tracked = [path for path in git("ls-files", "-z", "--", *pathspec).split("\0") if path]
    changes = [line for line in git("status", "--porcelain=v1", "--untracked-files=all", "--", *pathspec).splitlines()]
    schema = audit_machine_contract(ROOT)
    mismatches = [row for row in schema["tables"] if any(row[key] for key in (
        "missing_in_pyarrow", "undeclared_in_pyarrow", "missing_in_dataclass"))]
    run_gate = {gate: evaluate_scientific_gate(ROOT, "production_v3", gate) for gate in ("G1", "G2")}

    release = read_json(bind(f"{RELEASE}/release_manifest.json"))
    release_hashes = {item["path"]: item["sha256"] for item in release["artifacts"]}
    require(len(release_hashes) == release["artifact_inventory_count"], "Danh mục phát hành có đường dẫn trùng")
    for item in release["artifacts"]:
        path = bound_file(ROOT / RELEASE, {"path": item["path"], "sha256": item["sha256"]})
        require(path.stat().st_size == item["bytes"], f"Kích thước khác bản kê: {item['path']}")
    release_reports = {}
    for key in ("validation_report", "exact_neo4j_readback_report"):
        relative = release[key]
        release_reports[key] = read_json(bind(f"{RELEASE}/{relative}", release_hashes[relative]))
    parity = release_reports["exact_neo4j_readback_report"]["snapshots"]
    raw_rel = "inputs/raw_blob_reference_manifest.json"
    raw = read_json(bind(f"{RELEASE}/{raw_rel}", release_hashes[raw_rel]))
    raw_paths = [(ROOT / item["relative_path"]).resolve() for item in raw["entries"]]
    require(all(path.is_relative_to(ROOT / "data/raw") and "locked_test" not in path.parts for path in raw_paths),
            "Tham chiếu dữ liệu thô nằm ngoài phạm vi")

    candidate_path = "configs/m2_data_3_1_candidate_v2.yaml"
    reuse = inspect_backbone(ROOT, yaml.safe_load(bind(candidate_path).read_bytes()))
    alignment_manifest = verify_artifacts(ROOT / ALIGNMENT)
    try:
        alignment = verify_alignment(ROOT / ALIGNMENT)
    except (OSError, ValueError) as exc:
        differences = {}
        for relative, expected in alignment_manifest["inputs"]["hashes"].items():
            path = workspace_path(relative)
            actual = sha256_file(path) if path.is_file() else None
            if actual != expected:
                differences[relative] = {"ban_luu": expected, "hien_tai": actual}
        alignment = {"trang_thai": "Kiểm tra đầy đủ dừng", "ly_do": str(exc),
                     "so_tep_da_luu_khop": len(alignment_manifest["artifacts"]["hashes"]),
                     "dau_vao_khac_ban_ke": differences}
    registration_path = "configs/m2_measurement_v2_candidate.yaml"
    _, _, registration, registration_hashes = inspect_registration(ROOT, Path(registration_path))
    for relative, digest in registration_hashes.items():
        bind(relative, digest)
    for folder in (BACKBONE, ALIGNMENT):
        bind(f"{folder}/experiment_manifest.json")
    current_artifacts = {}
    for folder in (DEV, *RECENT_RUNS):
        receipt = verify_artifacts(ROOT / folder)
        bind(f"{folder}/experiment_manifest.json")
        current_artifacts[folder] = len(receipt["artifacts"]["hashes"])

    old_artifacts = {}
    for role, folder in OLD_RUNS.items():
        receipt = read_json(bind(f"{folder}/experiment_manifest.json"))
        artifacts = receipt["artifacts"]
        for relative, digest in artifacts.items():
            bind(f"{folder}/{relative}", digest)
        old_artifacts[role] = {"duong_dan": folder, "so_tep_khop": len(artifacts),
                               "git_commit_trong_ban_ke": receipt["git"]["commit"],
                               "co_ma_bam_dau_vao": bool(receipt["inputs"].get("hashes"))}
    panel = pq.read_table(ROOT / OLD_RUNS["hoi_dap"] / "recurring_qa_panel_evaluation.parquet").to_pylist()
    unique_queries = {(row["query_id"], row["hops"]) for row in panel}
    stats = read_json(ROOT / OLD_RUNS["thong_ke"] / "h1_h2_econometric_results.json")
    bind("decisions/decision_log.jsonl")
    decision = next(row for row in (
        json.loads(line) for line in (ROOT / "decisions/decision_log.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()) if row["decision_id"] == "d_diag_g3_thresholds_20261028")
    for relative in ("config/schema.yaml", "docs/gates_and_freeze.md", "src/paths/__init__.py",
                     "src/auditor/__init__.py", "scripts/run_m4_evaluation_and_stats.py",
                     Path(__file__).resolve().relative_to(ROOT).as_posix()):
        bind(relative)

    result = {
        "ma_va_cau_hinh": {"nhanh": git("branch", "--show-current").strip(),
                           "so_tep_theo_thu_muc": dict(Counter(path.split("/")[0] for path in tracked)),
                           "so_tep_theo_doi": len(tracked), "so_thay_doi_theo_loai": dict(
                               Counter(line[:2] for line in changes))},
        "M1": {"so_tep_phat_hanh_khop": len(release_hashes), "trang_thai_ban_giao":
                   release_reports["validation_report"]["stage_4_18_status"],
               "pham_vi_chung_nhan_M1": release_reports["validation_report"]["full_m1_acceptance"],
               "so_snapshot_khop_node_edge_trong_bao_cao_Neo4j": sum(
                   row["node_set_equal"] and row["edge_set_equal"] for row in parity),
               "so_tham_chieu_raw": len(raw_paths), "so_raw_co_o_duong_dan_da_khai_bao": sum(
                   path.is_file() for path in raw_paths),
               "hop_dong": schema["status"], "so_bang": len(schema["tables"]), "bang_lech_truong": mismatches,
               "kiem_tra": run_gate},
        "M2": {"kiem_tra_backbone": {k: reuse[k] for k in (
                   "status", "technical_reuse_eligible", "checkpoint_configurations_verified",
                   "saved_checkpoint_files_verified", "saved_replays_byte_identical", "artifact_hashes_checked",
                   "environment_current", "environment_training", "code_comparison")},
               "doi_chieu_can_chinh": alignment, "dang_ky": registration,
               "quyet_dinh_nguong": decision["change"],
               "nguong_trong_cau_hinh": yaml.safe_load((ROOT / registration_path).read_bytes())["settings"][
                   "maximum_normalized_orthogonality_error"]},
        "M3": {"tep_path": [f for f in tracked if f.startswith("src/paths/")],
               "tep_auditor": [f for f in tracked if f.startswith("src/auditor/")]},
        "M4": {"so_dong": len(panel), "so_truy_van": len(unique_queries), "so_chuyen_tiep": len(
                   {row["transition_id"] for row in panel}), "phan_bo_so_buoc": dict(
                   Counter(hops for _, hops in unique_queries)),
               "so_dong_dap_an_ngoai_T01": sum(row["is_gold_seen_at_t1"] is False for row in panel),
               "MRR_tinh_lai": {
                   scope: {side: mean(row[f"rr_arm_{side}_{scope}"] for row in panel) for side in ("a", "b")}
                   for scope in ("seen_at_t1", "open_world")},
               "H2_lich_su": stats["H2_contrast_analysis"],
               "H1_lich_su": stats["H1_hypothesis_testing"],
               "doi_chung_gia_lich_su": stats["falsification_testing"]},
        "W7": {"co_ban_ke": (ROOT / "data/manifests/w7_freeze.yaml").is_file(),
               "co_the_Git": bool(git("tag", "--list", "protocol-v1-frozen").strip())},
        "so_tep_hien_vat_cac_dot_gan_day": current_artifacts,
        "hien_vat_lich_su": old_artifacts,
    }
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "trang_thai_kiem_tra.json"
    write_json(result_path, result)
    commit, dirty = get_git_info(ROOT)
    pilot = read_json(ROOT / DEV / "experiment_manifest.json")
    receipt: dict[str, Any] = {
        "experiment_id": output.name, "protocol_version": pilot["protocol_version"], "seed": None,
        "stage": "project_status_read_only_audit", "scientific_certification": False,
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**pilot["inputs"], "query_hash": None, "config_hash": content_hash(OLD_RUNS),
                   "hashes": hashes},
        "environment": {"python": platform.python_version(), "os": platform.platform()},
        "hardware": {"cpu": platform.processor(), "ram": None},
        "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {result_path.name: sha256_file(result_path)}},
    }
    validate_manifest(receipt)
    write_json(output / "experiment_manifest.json", receipt)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
