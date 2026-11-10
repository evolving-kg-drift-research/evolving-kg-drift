"""Vẽ và lập bản kê biểu đồ loss từ nhật ký mô hình nền đã kiểm chứng."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kg_pipeline.experiment_manifest import validate_manifest, verify_artifacts  # noqa: E402
from kg_pipeline.hashing import get_git_info, sha256_file  # noqa: E402

SEEDS = (13, 37, 101)
SNAPSHOTS = tuple(f"T{i:02d}" for i in range(1, 11))
OUT_ROOT = ROOT / "outputs/m2_backbone_v31"


def chart(logs: dict[str, list[float]], path: Path) -> None:
    fig = Figure(figsize=(11.6, 6.5), facecolor="white")
    axes = fig.subplots(2, 5, sharex=True, sharey=True)
    fig.subplots_adjust(left=.09, right=.975, bottom=.12, top=.73, hspace=.42, wspace=.14)
    for sid, ax in zip(SNAPSHOTS, axes.flat, strict=True):
        for seed, color in zip(SEEDS, ("#086e87", "#bf641f", "#7554a3"), strict=True):
            values = logs[f"{sid}/{seed}"]
            ax.plot(range(1, len(values) + 1), values, color=color, label=f"Seed {seed}", linewidth=1.25)
        ax.set_title(sid, loc="left", color="#263e4d", weight="bold")
        ax.grid(axis="y", color="#d6e0e7", linewidth=.7)
        ax.set_xticks((1, 25, 50, 85))
        ax.set_ylim(bottom=0)
        ax.yaxis.set_major_formatter(lambda value, _: f"{value:.1f}".replace(".", ","))
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=8)
    fig.text(.09, .941, "Hàm mất mát huấn luyện TransE-L2", fontsize=19, weight="bold", color="#172c3a")
    fig.text(.09, .881, "Toàn bộ snapshot V3.1 · 64 chiều · 85 vòng · Cùng thang đo cho T01–T10",
             color="#40576a", fontsize=11)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="upper left",
               bbox_to_anchor=(.083, .859), ncols=3, frameon=False)
    fig.supxlabel("Vòng huấn luyện", y=.045, fontsize=11)
    fig.supylabel("Mất mát trực tuyến trên mỗi bộ ba dương", x=.018, fontsize=10)
    with path.open("xb") as handle:
        fig.savefig(handle, format="png", dpi=160)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verification", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, out = (p.resolve() for p in (args.verification, args.output))
    if any(not p.is_relative_to(OUT_ROOT.resolve()) or p == OUT_ROOT.resolve()
           or "locked_test" in {part.lower() for part in p.parts} for p in (source, out)):
        raise ValueError("Cần thư mục dưới outputs/m2_backbone_v31")
    verified = verify_artifacts(source)
    logs = json.loads((source / "loss_theo_epoch.json").read_bytes())
    if (verified["stage"] != "m2_backbone_v31_dev_verification"
            or set(logs) != {f"{sid}/{seed}" for sid in SNAPSHOTS for seed in SEEDS}
            or any(len(row) != 85 for row in logs.values())):
        raise ValueError("Cần đúng nhật ký đã kiểm chứng của 30 tổ hợp")
    out.mkdir(parents=True, exist_ok=False)
    figure = out / "mat_mat_huan_luyen_theo_snapshot.png"
    chart(logs, figure)
    paths = (source / "experiment_manifest.json", Path(__file__).resolve())
    commit, dirty = get_git_info(ROOT)
    manifest = {
        **verified, "experiment_id": out.name, "stage": "m2_backbone_v31_dev_report",
        "git": {"commit": commit, "dirty_state": dirty},
        "inputs": {**verified["inputs"], "hashes": {p.relative_to(ROOT).as_posix(): sha256_file(p) for p in paths}},
        "environment": {"python": platform.python_version(), "os": platform.platform(),
                        "matplotlib": matplotlib.__version__},
        "access": {**verified["access"], "timestamp": datetime.now(timezone.utc).isoformat(),
                   "actor_or_runner": Path(__file__).name},
        "artifacts": {"hashes": {figure.name: sha256_file(figure)}},
    }
    validate_manifest(manifest)
    with (out / "experiment_manifest.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True, allow_nan=False)
    verify_artifacts(out)


if __name__ == "__main__":
    main()
