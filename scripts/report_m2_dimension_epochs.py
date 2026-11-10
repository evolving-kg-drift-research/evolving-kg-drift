"""Kiểm lại điểm chọn cấu hình và vẽ đường cong tìm kiếm bằng tiếng Việt."""
from __future__ import annotations

import argparse
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)
from scripts.search_m2_dimension_epochs import DIMENSIONS, EPOCHS, PARENT, REGISTRATION, SEEDS, mean  # noqa: E402


def chart(path: Path, grid: list[dict], best: dict, baseline: float) -> None:
    fig = Figure(figsize=(10.4, 5.7), facecolor="white")
    ax = fig.subplots()
    fig.subplots_adjust(left=.105, right=.955, bottom=.15, top=.74)
    fig.text(.105, .935, "Tìm số chiều và số vòng huấn luyện TransE-L2",
             color="#182839", weight="bold", fontsize=18)
    fig.text(.105, .86, "MRR xác thực trung bình đều qua 10 snapshot V3.1 và ba lần khởi tạo",
             color="#44566a", fontsize=10.5)
    for d, color in zip(DIMENSIONS, ("#b55d32", "#116981"), strict=True):
        rows = [r for r in grid if r["chieu"] == d]
        ax.plot([r["epoch"] for r in rows], [r["MRR"] for r in rows], label=f"{d} chiều",
                color=color, linewidth=2)
    ax.axhline(baseline, linestyle="--", color="#697381", linewidth=1, label="Đối chứng tần suất")
    ax.scatter(best["epoch"], best["MRR"], zorder=4, color="#17283a", s=25)
    label = f"{best['chieu']} chiều · vòng {best['epoch']} · {best['MRR']:.4f}".replace(".", ",")
    ax.annotate(label, (best["epoch"], best["MRR"]), xytext=(-5, 13),
                textcoords="offset points", ha="right", color="#17283a")
    ax.set_xlabel("Vòng huấn luyện")
    ax.set_ylabel("MRR xác thực")
    ax.set_xticks((1, 50, 100, 150, 200, 250))
    ax.set_ylim(bottom=0, top=max(r["MRR"] for r in grid) * 1.17)
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.3f}".replace(".", ","))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=.25)
    fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.098, .825),
               ncols=3, frameon=False, fontsize=10)
    with path.open("xb") as stream:
        fig.savefig(stream, format="png", dpi=170)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run, output = (path.resolve() for path in (args.run, args.output))
    require(all(p.is_relative_to(ROOT / "outputs") and p != ROOT / "outputs"
                and all(part.lower() != "locked_test" for part in p.parts) for p in (run, output))
            and not output.exists(), "Thư mục không hợp lệ")
    source = verify_artifacts(run)
    require(source["stage"] == "m2_dimension_epoch_search_dev", "Sai loại lượt chạy")
    for p, digest in source["inputs"]["hashes"].items():
        bound_file(ROOT, {"path": p, "sha256": digest})
    design = read_json(run / "thiet_ke_tim_kiem.json")
    require(content_hash(design) == source["inputs"]["config_hash"], "Thiết kế không khớp")
    original = verify_artifacts(ROOT / PARENT)
    registration = verify_artifacts(ROOT / REGISTRATION)
    saved = read_json(run / "ket_qua_tim_kiem.json")
    best = saved["tot_nhat_trong_luoi"]
    grid = {(row["chieu"], row["epoch"]): row for row in saved["du_lieu_xep_hang"]}
    per_trial = {}
    ranks_checked = 0
    file_count = 0
    identical_fifty = 0
    seeds_by_snapshot = {}
    baselines = {}
    for sid in design["snapshot"]:
        path = f"{sid}/baseline.json"
        baselines[sid] = read_json(bound_file(ROOT / REGISTRATION,
                                             {"path": path, "sha256": registration["artifacts"]["hashes"][path]}))
        prior = verify_artifacts(bound_file(ROOT / PARENT, {
            "path": f"{sid}/experiment_manifest.json",
            "sha256": original["artifacts"]["hashes"][f"{sid}/experiment_manifest.json"],
        }).parent)
        seeds_by_snapshot[sid] = {}
        for d in DIMENSIONS:
            for seed in SEEDS:
                relative = f"d{d}/{sid}/seed_{seed}/ma_bam.json"
                index = read_json(bound_file(run, {"path": relative, "sha256": source["artifacts"]["hashes"][relative]}))
                folder = (run / relative).parent
                log = read_json(bound_file(folder, {"path": "nhat_ky.json", "sha256": index["nhat_ky.json"]}))
                require([r["epoch"] for r in log] == list(range(1, EPOCHS[-1] + 1)), "Thiếu vòng huấn luyện")
                expected_rows = len(baselines[sid]["hang"])
                for row in log:
                    diagnostics = row["chan_doan"]
                    require(math.isclose(row["loss_huan_luyen"], diagnostics["loss_sum"] / diagnostics["positives"])
                            and diagnostics["usable_negatives"] + diagnostics["skipped"] == diagnostics["positives"],
                            "Loss hoặc mẫu âm huấn luyện không khớp")
                for epoch in EPOCHS:
                    rpath = f"epochs/{epoch:04d}_ranks.json"
                    rows = read_json(bound_file(folder, {"path": rpath, "sha256": index[rpath]}))
                    require(len(rows) == expected_rows, "Thiếu dòng xếp hạng")
                    rank_mrr = mean(1 / row["rank"] for row in rows)
                    logged = log[epoch - 1]["chi_so"]
                    require(math.isclose(rank_mrr, logged["MRR"], rel_tol=1e-12)
                            and all(math.isclose(mean(row["rank"] <= k for row in rows), logged[f"Hits@{k}"])
                                    for k in (1, 3, 10)), "Chỉ số không khớp thứ hạng")
                    per_trial[d, sid, seed, epoch] = rank_mrr
                    ranks_checked += len(rows)
                if d == best["chieu"]:
                    seeds_by_snapshot[sid][str(seed)] = log[best["epoch"] - 1]["chi_so"]
                if d == 64:
                    name = "epochs/0050.json"
                    old_name = f"seed_{seed}/{name}"
                    past = read_json(bound_file(ROOT / PARENT / sid,
                                                {"path": old_name, "sha256": prior["artifacts"]["hashes"][old_name]}))
                    current = read_json(bound_file(folder, {"path": name, "sha256": index[name]}))
                    require(all(past[k] == current[k] for k in ("entity_embeddings", "relation_embeddings")),
                            "Vector 64 chiều vòng 50 lệch với lần trước")
                    identical_fifty += 1
                file_count += len(index)
    for (d, epoch), row in grid.items():
        values = {sid: mean(per_trial[d, sid, seed, epoch] for seed in SEEDS) for sid in design["snapshot"]}
        require(all(math.isclose(values[sid], row["MRR_theo_snapshot"][sid], rel_tol=1e-12) for sid in values)
                and math.isclose(mean(values.values()), row["MRR"], rel_tol=1e-12), "Điểm lưới không khớp")
    require(best == min(grid.values(), key=lambda r: (-r["MRR"], r["chieu"], r["epoch"]))
            and ranks_checked == saved["so_dong_thu_hang_kiem_chung"] and identical_fifty == 30,
            "Cấu hình chọn hoặc độ bao phủ xác minh không khớp")
    baseline = mean(row["chi_so"]["MRR"] for row in baselines.values())
    result = {
        "chon": best, "theo_chieu": saved["tot_nhat_theo_chieu"], "doi_chung_tan_suat_MRR": baseline,
        "so_snapshot_vuot_doi_chung": sum(best["MRR_theo_snapshot"][sid] > baselines[sid]["chi_so"]["MRR"]
                                          for sid in design["snapshot"]),
        "chi_so_theo_seed_o_moc_chon": seeds_by_snapshot,
        "so_dong_thu_hang_tinh_lai": ranks_checked, "so_checkpoint_d64_vong_50_khop_vector": identical_fifty,
        "so_tep_trong_ban_ke_job": file_count,
        "du_lieu_chon": "Xác thực phát triển V3.1",
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "kiem_tra_chon_cau_hinh.json", result)
    chart(output / "so_sanh_MRR_theo_epoch.png", list(grid.values()), best, baseline)
    paths = (run / "experiment_manifest.json", ROOT / REGISTRATION / "experiment_manifest.json",
             ROOT / PARENT / "experiment_manifest.json", Path(__file__).resolve())
    commit, dirty = get_git_info(ROOT)
    manifest = {
        **source, "experiment_id": output.name, "stage": "m2_dimension_epoch_search_report",
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**source["inputs"], "hashes": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths}},
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "matplotlib": matplotlib.__version__},
        "access": {**source["access"], "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {p.name: sha256_file(p) for p in output.iterdir()}},
    }
    validate_manifest(manifest)
    write_json(output / "experiment_manifest.json", manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
