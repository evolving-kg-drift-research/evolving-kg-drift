"""Tổng hợp và vẽ kết quả xác thực TransE-L2 V3.1 bằng tiếng Việt."""
from __future__ import annotations

import argparse
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import matplotlib
from matplotlib.figure import Figure

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_kge_retrospective_t01 import (  # noqa: E402
    ROOT, bound_file, content_hash, get_git_info, read_json, require, sha256_file,
    validate_manifest, verify_artifacts, write_json,
)

SEEDS = (13, 37, 101)
INDICATORS = ("MRR", "Hits@1", "Hits@3", "Hits@10")


def make_chart(path: Path, rows: dict[str, list[dict]], baselines: dict[str, dict], *, losses: bool) -> None:
    fig = Figure(figsize=(14.5, 7.2), facecolor="white")
    axes = fig.subplots(2, 5, sharex=True, sharey=True).flat
    fig.subplots_adjust(top=.75, bottom=.11, left=.07, right=.98, wspace=.24, hspace=.35)
    title = "Hàm mất mát theo vòng huấn luyện" if losses else "Thứ hạng trên tập xác thực theo vòng huấn luyện"
    fig.text(.07, .94, title, fontsize=20, weight="bold", color="#17283a")
    fig.text(.07, .88, "TransE-L2 · 64 chiều · 10 snapshot V3.1 · Mỗi đường là trung bình ba lần khởi tạo",
             fontsize=11, color="#475b6e")
    for ax, (sid, epochs) in zip(axes, rows.items(), strict=True):
        ax.set_title(sid, loc="left", weight="bold", color="#17283a")
        x = [row["epoch"] for row in epochs]
        if losses:
            ax.plot(x, [row["online_train_loss"] for row in epochs], color="#136c85", label="Hàm mất mát huấn luyện")
            ax.plot(x, [row["validation_loss"] for row in epochs], color="#b65a31", label="Hàm mất mát xác thực")
        else:
            ax.plot(x, [row["MRR"] for row in epochs], color="#136c85", label="MRR của TransE-L2")
            ax.fill_between(x, [row["MRR_min"] for row in epochs], [row["MRR_max"] for row in epochs],
                            color="#136c85", alpha=.15, label="Khoảng thấp nhất đến cao nhất")
            ax.axhline(baselines[sid]["MRR"], color="#a65535", ls="--", label="Đối chứng tần suất")
        ax.grid(axis="y", alpha=.22)
        ax.yaxis.set_major_formatter(lambda value, _: format(value, ".2f" if losses else ".3f").replace(".", ","))
        ax.set_xticks((1, 25, 50))
        ax.spines[["top", "right"]].set_visible(False)
        if sid in ("T01", "T06"):
            ax.set_ylabel("Giá trị hàm mất mát" if losses else "MRR")
    fig.legend(*fig.axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.06, .84),
               ncols=3, frameon=False, fontsize=10)
    fig.supxlabel("Vòng huấn luyện", y=.03, fontsize=11)
    with path.open("xb") as file:
        fig.savefig(file, format="png", dpi=160)


def confirm_baseline(design: dict, baseline: dict) -> None:
    frequencies = Counter(e for h, _, t in design["split"]["train"] for e in (h, t))
    positives = {tuple(t) for t in design["filter_positives"]}
    ranks = []
    for h, r, t in sorted(design["split"]["validation"]):
        for side, target in (("head", h), ("tail", t)):
            eligible = Counter(frequencies[e] for e in design["candidates"] if e == target
                               or ((e, r, t) if side == "head" else (h, r, e)) not in positives)
            target_score = frequencies[target]
            ranks.append(1 + sum(n for score, n in eligible.items() if score > target_score)
                         + (eligible[target_score] - 1) / 2)
    require(ranks == baseline["hang"], "Thứ hạng đối chứng không khớp khi tính lại")
    expected = {"MRR": mean(1 / r for r in ranks),
                **{f"Hits@{k}": mean(r <= k for r in ranks) for k in (1, 3, 10)}}
    require(all(abs(expected[k] - baseline["chi_so"][k]) < 1e-14 for k in INDICATORS),
            "Chỉ số đối chứng không khớp khi tính lại")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registration", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    registration, run, output = (p.resolve() for p in (args.registration, args.run, args.output))
    require(all(p.is_relative_to(ROOT / "outputs") and p != ROOT / "outputs"
                and all(part.lower() != "locked_test" for part in p.parts) for p in (registration, run, output))
            and not output.exists(), "Thư mục kết quả không hợp lệ")
    manifest = verify_artifacts(run)
    registered = verify_artifacts(registration)
    plan = read_json(registration / "ke_hoach.json")["ke_hoach"]
    require(manifest["stage"] == "v31_quality_validation_dev_t01_t10"
            and registered["inputs"]["config_hash"] == manifest["inputs"]["config_hash"] == content_hash(plan),
            "Phiên và bản đăng ký không khớp")
    inputs = {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in (
        registration / "experiment_manifest.json", run / "experiment_manifest.json", Path(__file__).resolve())}
    curves: dict[str, list[dict[str, Any]]] = {}
    baselines = {}
    summary = {}
    total_verified = Counter()
    for item in plan:
        sid = item["snapshot"]
        baseline = read_json(bound_file(ROOT, item["baseline"]))
        baselines[sid] = baseline["chi_so"]
        stage = read_json(run / sid / "experiment_manifest.json")
        hashes = stage["artifacts"]["hashes"]

        def read_bound(relative: str) -> Any:
            p = f"{(run / sid).relative_to(ROOT).as_posix()}/{relative}"
            inputs[p] = hashes[relative]
            return read_json(bound_file(ROOT, {"path": p, "sha256": hashes[relative]}))

        receipt = read_bound("independent_verification.json")
        for checked in receipt.values():
            total_verified.update({key: checked[key] for key in ("epochs_verified", "ranking_rows_verified")})
        design = read_bound("seed_13/design.json")
        confirm_baseline(design, baseline)
        logs = {str(seed): read_bound(f"seed_{seed}/epoch_log.json") for seed in SEEDS}
        curve = []
        for epoch, group in enumerate(zip(*logs.values(), strict=True), start=1):
            require(all(row["epoch"] == epoch and row["snapshot_id"] == sid for row in group), "Sai epoch")
            vals = [row["metrics"]["MRR"] for row in group]
            curve.append({"epoch": epoch, "online_train_loss": mean(row["online_train_loss"] for row in group),
                          "validation_loss": mean(row["validation_loss"] for row in group),
                          **{k: mean(row["metrics"][k] for row in group) for k in INDICATORS},
                          "MRR_min": min(vals), "MRR_max": max(vals)})
        require(len(curve) == 50, "Thiếu epoch")
        curves[sid] = curve
        final = {seed: log[-1]["metrics"] for seed, log in logs.items()}
        summary[sid] = {
            "huan_luyen": len(design["split"]["train"]), "xac_thuc": len(design["split"]["validation"]),
            "epoch_1": curve[0], "epoch_50": curve[-1], "doi_chung_tan_suat": baselines[sid], "tung_seed": final,
            "chenh_lech_epoch_50": {k: curve[-1][k] - baselines[sid][k] for k in INDICATORS},
            "mau_am_bo_qua": sum(row["train_diagnostics"]["skipped"] for log in logs.values() for row in log),
        }
    require(total_verified["epochs_verified"] == 1500 and total_verified["ranking_rows_verified"] == 379500,
            "Không đủ dòng xác minh")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "tong_hop.json", {"theo_snapshot": summary, "kiem_chung": dict(total_verified)})
    write_json(output / "duong_cong.json", curves)
    make_chart(output / "ham_mat_mat.png", curves, baselines, losses=True)
    make_chart(output / "thu_hang_xac_thuc.png", curves, baselines, losses=False)
    commit, dirty = get_git_info(ROOT)
    report_manifest = {
        **manifest, "experiment_id": output.name, "stage": "v31_quality_validation_dev_report",
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**manifest["inputs"], "hashes": inputs},
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "matplotlib": matplotlib.__version__},
        "access": {**manifest["access"], "actor_or_runner": Path(__file__).name,
                   "timestamp": datetime.now(timezone.utc).isoformat()},
        "artifacts": {"hashes": {p.name: sha256_file(p) for p in output.iterdir()}},
    }
    validate_manifest(report_manifest)
    write_json(output / "experiment_manifest.json", report_manifest)
    verify_artifacts(output)


if __name__ == "__main__":
    main()
