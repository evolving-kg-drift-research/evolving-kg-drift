"""Descriptive M2 report from immutable artifacts; never trains or advances stages."""
from __future__ import annotations

import argparse
import base64
import html
import importlib.metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs/m2_report_packages_20261014"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs/m2_report_plot_cache"))
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from scripts.inspect_m2_inputs import encode, provenance, safe_file, sha, validate_manifest, write_json  # noqa: E402

RUNS = {
    "preflight": "outputs/m2_preflight/20261014T031739Z_71f4e280",
    "pilot": "outputs/m2_pilot/20261014T031822Z_9b722664",
    "backbone": "outputs/m2_backbone/20261014T034042Z_65c464ba",
    "alignment": "outputs/m2_alignment/20261014T040001Z_96d9ccbc",
    "null": "outputs/m2_null/20261014T042450Z_43e91590",
    "drift": "outputs/m2_drift/20261014T044648Z_ae9f0401",
}
RECEIPTS = {
    "pilot": "independent_verification_20261014T032428Z_ea8b68ae.json",
    "backbone": "independent_verification_20261014T034333Z_cea99585.json",
    "alignment": "independent_verification_20261014T040130Z_31179f1c.json",
    "null": "independent_verification_20261014T042638Z_7d9e8c02.json",
    "drift": "independent_verification_20261014T044723Z_0f2a3d8a.json",
}
COLORS = ["#176b88", "#bf642b", "#7759aa"]
SEEDS = [13, 37, 101]


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def json_lines(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def checked_sources() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    manifests, hashes, receipts = {}, {}, {}
    for name, relative in RUNS.items():
        run = ROOT / relative
        path = safe_file(run, "experiment_manifest.json")
        manifest = read_json(path)
        validate_manifest(manifest)
        if manifest["scientific_certification"] is not False or manifest["access"]["state"] != "dev":
            raise ValueError("Report requires the registered Dev sources")
        catalogs = ((ROOT, manifest["inputs"].get("hashes", {})), (run, manifest["artifacts"]["hashes"]))
        # Preflight stores its canonical input inventory in report.json.
        if name == "preflight":
            catalogs = (*catalogs, (ROOT, read_json(run / "report.json")["input_hashes"]))
        for base, catalog in catalogs:
            for key, digest in catalog.items():
                source = safe_file(base, key)
                repo_key = source.relative_to(ROOT).as_posix()
                if repo_key in hashes and hashes[repo_key] != digest:
                    raise ValueError("Conflicting source hash catalogs")
                hashes[repo_key] = digest
        hashes[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
        manifests[name] = manifest
        if name in RECEIPTS:
            receipt_path = safe_file(run, RECEIPTS[name])
            receipt = read_json(receipt_path)
            if receipt.get("manifest_sha256") != sha(path.read_bytes()) or "PASS" not in receipt["status"]:
                raise ValueError(f"Missing completed independent receipt: {name}")
            archived = run / "code/scripts" / f"verify_m2_{name}.py"
            if archived.is_file() and sha(archived.read_bytes()) != receipt["verifier_sha256"]:
                raise ValueError("Receipt verifier archive changed")
            hashes[receipt_path.relative_to(ROOT).as_posix()] = sha(receipt_path.read_bytes())
            receipts[name] = receipt
    for relative, digest in hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Immutable report source changed: {relative}")
    return manifests, hashes, receipts


def extract_data() -> dict[str, Any]:
    preflight = read_json(ROOT / RUNS["preflight"] / "report.json")
    pilot = read_json(ROOT / RUNS["pilot"] / "summary.json")
    backbone = read_json(ROOT / RUNS["backbone"] / "summary.json")
    alignment = read_json(ROOT / RUNS["alignment"] / "summary.json")
    drift_run = ROOT / RUNS["drift"]
    entity = pq.read_table(drift_run / "entity_drift.parquet").to_pylist()
    temporal = pq.read_table(drift_run / "temporal_displacements.parquet").to_pylist()
    temporal_index = {(r["transition_id"], r["entity_id"], r["seed"]): r for r in temporal}
    if len(temporal_index) != 20691 or len(entity) != 6897:
        raise ValueError("Unexpected immutable drift population")
    training, models = [], []
    for result in backbone["results"]:
        path = safe_file(ROOT / RUNS["backbone"], result["path"])
        checkpoint = read_json(path)
        losses = checkpoint["training_metrics"]["epoch_losses"]
        if len(losses) != 50 or not np.isfinite(losses).all() or checkpoint["training_metrics"]["dev_losses"]:
            raise ValueError("Incomplete epoch log or unexpected full-snapshot validation")
        model = {**result, "epoch_losses": losses, "loss_reduction_percent": 100 * (losses[0] - losses[-1]) / losses[0]}
        models.append(model)
        for epoch, loss in enumerate(losses, 1):
            training.append({"snapshot_id": result["snapshot_id"], "seed": result["seed"], "epoch": epoch,
                             "training_loss": loss, "checkpoint_sha256": sha(path.read_bytes()),
                             "source_path": path.relative_to(ROOT).as_posix()})
    for row in entity:
        row.update({f"delta_seed_{seed}": temporal_index[row["transition_id"], row["entity_id"], seed]["temporal_displacement"] for seed in SEEDS})
        row["seed_range"] = max(row[f"delta_seed_{s}"] for s in SEEDS) - min(row[f"delta_seed_{s}"] for s in SEEDS)
    if len(training) != 1500 or len({(m["snapshot_id"], m["seed"]) for m in models}) != 30:
        raise ValueError("Missing snapshot/seed training logs")
    transitions = [r["transition_id"] for r in read_json(drift_run / "summary.json")["results"]]
    stats = []
    for transition in transitions:
        population = [r for r in entity if r["transition_id"] == transition]
        record: dict[str, Any] = {"transition_id": transition, "entities": len(population),
                                 "available": sum(r["available"] for r in population),
                                 "positive_excess": sum(r["signed_excess"] > 0 for r in population),
                                 "min_reference_entities": min(r["reference_entity_count"] for r in population)}
        for metric in ("delta_time", "null_median", "signed_excess", "SED_plus", "seed_range"):
            array = [r[metric] for r in population]
            record[metric] = {"q25": float(np.quantile(array, .25)), "median": float(np.median(array)),
                              "q75": float(np.quantile(array, .75)), "p95": float(np.quantile(array, .95)), "max": max(array)}
        stats.append(record)
    buckets = []
    for transition in transitions:
        for bucket in ("low", "medium", "high"):
            rows = [r for r in entity if r["transition_id"] == transition and r["bucket_id"] == bucket]
            buckets.append({"transition_id": transition, "bucket_id": bucket, "entities": len(rows),
                            "reference_entities": min(r["reference_entity_count"] for r in rows) if rows else None,
                            "SED_plus_median": float(np.median([r["SED_plus"] for r in rows])) if rows else None})
    return {"preflight": preflight, "pilot": pilot, "backbone": backbone, "alignment": alignment,
            "training": training, "models": models, "entities": entity, "transitions": transitions, "transition_stats": stats, "buckets": buckets}


def make_figures(out: Path, data: dict[str, Any]) -> list[dict[str, str]]:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .15, "svg.fonttype": "none"})
    figures: list[dict[str, str]] = []
    folder = out / "figures"
    folder.mkdir()

    def save(fig: Any, slug: str, title: str, caption: str) -> None:
        fig.suptitle(title, fontsize=16, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, .95))
        png, svg = folder / f"{slug}.png", folder / f"{slug}.svg"
        fig.savefig(png, dpi=180, facecolor="white")
        fig.savefig(svg, facecolor="white", metadata={"Date": None})
        plt.close(fig)
        figures.append({"id": slug, "title": title, "caption": caption, "png": png.relative_to(out).as_posix(), "svg": svg.relative_to(out).as_posix()})

    snapshots = data["preflight"]["snapshots"]
    sids = [r["snapshot_id"] for r in snapshots]
    transitions = data["transitions"]
    labels = [t.replace("->", "→") for t in transitions]
    ix = np.arange(9)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    for ax, field, label in zip(axes, ("triples", "entities"), ("Số triples", "Số thực thể")):
        vals = [r[field] for r in snapshots]
        ax.plot(sids, vals, "o-", color=COLORS[0])
        for i, val in enumerate(vals):
            ax.annotate(str(val), (i, val), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
        ax.set(ylabel=label, xlabel="Snapshot", ylim=(0, max(vals) * 1.18))
    save(fig, "01_snapshot_growth", "Quy mô dữ liệu T01–T10", "10 relations ở mọi snapshot. Trục x là thứ tự snapshot; các cutoff không cách đều theo thời gian.")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    x = np.arange(2)
    for i, seed in enumerate(SEEDS):
        axes[0].bar(x + (i - 1) * .22, [data["pilot"]["dimensions"][str(d)]["validation"][str(seed)]["MRR"] for d in (32, 64)],
                    width=.2, color=COLORS[i], label=f"Seed {seed}")
    means = [data["pilot"]["dimensions"][str(d)]["mean_validation_MRR"] for d in (32, 64)]
    axes[0].plot(x, means, "D", color="#172d42", label="Trung bình 3 seeds")
    axes[0].set(xticks=x, xticklabels=["32 chiều", "64 chiều"], ylabel="Validation MRR", ylim=(0, .20))
    axes[0].legend(fontsize=8)
    for i, metric in enumerate(("Hits@1", "Hits@3", "Hits@10")):
        axes[1].bar(np.arange(3) + (i - 1) * .22, [data["pilot"]["dimensions"]["64"]["validation"][str(s)][metric] for s in SEEDS],
                    width=.2, color=COLORS[i], label=metric)
    axes[1].set(xticks=np.arange(3), xticklabels=[str(s) for s in SEEDS], xlabel="Seed (64 chiều)", ylabel="Validation Hits@k", ylim=(0, .4))
    axes[1].legend(fontsize=8)
    save(fig, "02_pilot_validation", "Pilot: chất lượng link prediction trên T01", "101 train / 20 validation triples; 40 head/tail queries/seed/dimension. Đây là validation link prediction, chưa phải QA multi-hop. Hits@1 của cả 3 seeds 64 chiều bằng 0.")

    fig, axes = plt.subplots(2, 5, figsize=(16, 7), sharex=True, sharey=True)
    for ax, sid in zip(axes.flat, sids):
        for i, seed in enumerate(SEEDS):
            model = next(m for m in data["models"] if m["snapshot_id"] == sid and m["seed"] == seed)
            ax.plot(np.arange(1, 51), model["epoch_losses"], color=COLORS[i], label=f"Seed {seed}", linewidth=1.3)
        ax.set(title=sid, xlabel="Epoch", ylabel="Training loss", ylim=(0, 1.15), xlim=(1, 50))
    axes[0, 0].legend(fontsize=8)
    save(fig, "03_training_losses", "Loss huấn luyện: 30 mô hình × 50 epoch", "Đường loss thô từ checkpoints, không làm trơn; full-snapshot training không có validation loss. Loss dao động do negative sampling; đồ thị chưa xác nhận hội tụ tối ưu hoặc chất lượng QA.")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    for ax, metric, title, fmt in zip(axes, ("final_loss", "loss_reduction_percent"), ("Loss epoch 50", "Giảm loss so với epoch 1 (%)"), (".3f", ".1f")):
        matrix = np.asarray([[next(m[metric] for m in data["models"] if m["snapshot_id"] == sid and m["seed"] == seed) for seed in SEEDS] for sid in sids])
        im = ax.imshow(matrix, cmap="Blues", aspect="auto")
        for row in range(10):
            for col in range(3):
                ax.text(col, row, format(matrix[row, col], fmt), ha="center", va="center", fontsize=9,
                        color="white" if matrix[row, col] > (matrix.min() + matrix.max()) / 2 else "#123")
        ax.set(xticks=np.arange(3), xticklabels=[str(s) for s in SEEDS], yticks=np.arange(10), yticklabels=sids, title=title, xlabel="Seed")
        ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=.75)
    save(fig, "04_training_summary", "Chẩn đoán loss cuối và mức giảm loss", "Phần trăm giảm = 100×(loss epoch 1 − loss epoch 50)/loss epoch 1. Mỗi mô hình train từ đầu; quy mô và samples khác nhau giữa snapshots nên loss không phải thước đo so sánh độ chính xác QA.")

    alignment = data["alignment"]["results"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for i, kind in enumerate(("cross_time", "same_snapshot_cross_seed")):
        for field, style in (("fit_residual", "--"), ("holdout_residual", "-")):
            vals = [max(r["diagnostics"][field] for r in alignment if r["transition_id"] == t and r["alignment_type"] == kind) for t in transitions]
            axes[0, 0].plot(ix, vals, style, color=COLORS[i], marker="o", markersize=3,
                            label=f"{'Cross-time' if i == 0 else 'Same-snapshot'} / {'fit' if style == '--' else 'holdout'}")
        for ax, field in ((axes[0, 1], "fit_holdout_gap"), (axes[1, 0], "orthogonality_error")):
            vals = [max(r["diagnostics"][field] for r in alignment if r["transition_id"] == t and r["alignment_type"] == kind) for t in transitions]
            ax.plot(ix, vals, "o-", color=COLORS[i], label="Cross-time" if i == 0 else "Same-snapshot")
    axes[0, 0].axhline(2, color="#ae4257", linewidth=1, label="Giới hạn holdout Dev: 2")
    axes[0, 1].axhline(1, color="#ae4257", linewidth=1, label="Giới hạn gap Dev: 1")
    axes[1, 0].axhline(1e-4, color="#ae4257", linewidth=1, label="Giới hạn Dev: 1e−4")
    axes[1, 0].set_yscale("log")
    for ax, title in zip([axes[0, 0], axes[0, 1], axes[1, 0]], ["Max fit / holdout RMSE", "Max holdout − fit gap", "Max orthogonality error (log scale)"]):
        ax.set(title=title, xticks=ix, xticklabels=labels)
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
        ax.legend(fontsize=7)
    axes[1, 1].bar(ix, [min(r["diagnostics"]["numerical_rank"] for r in alignment if r["transition_id"] == t) for t in transitions], color=COLORS[0])
    axes[1, 1].axhline(64, color="#ae4257", label="Dimension / rank yêu cầu: 64")
    axes[1, 1].set(title="Minimum numerical rank", xticks=ix, xticklabels=labels, ylim=(0, 72))
    axes[1, 1].tick_params(axis="x", labelrotation=35, labelsize=8)
    axes[1, 1].legend(fontsize=7)
    save(fig, "05_alignment_diagnostics", "Alignment: 81 comparisons và các guard Dev đã duyệt", "27 cross-time + 54 same-snapshot comparisons; 101 fit / 66 holdout anchors. Max/Min tổng hợp theo transition, không phải CI. Numerical diagnostics đạt guard không xác nhận semantic quality hoặc cấp G3.")

    stats = data["transition_stats"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for i, (metric, label) in enumerate((("delta_time", "δ_time"), ("null_median", "Median null LTO"))):
        med, lo, hi = ([r[metric][k] for r in stats] for k in ("median", "q25", "q75"))
        axes[0].plot(ix, med, "o-", color=COLORS[i], label=label)
        axes[0].fill_between(ix, lo, hi, color=COLORS[i], alpha=.13)
    axes[0].set(title="Median và IQR qua các thực thể", ylabel="Centered cosine displacement", xticks=ix, xticklabels=labels, ylim=(0, 1.5))
    axes[0].legend()
    for i, transition in enumerate(transitions):
        rows = [r for r in data["entities"] if r["transition_id"] == transition]
        axes[1].scatter([r["null_median"] for r in rows], [r["delta_time"] for r in rows], s=5, alpha=.22,
                        color=plt.colormaps["viridis"](i / 8), rasterized=True)
    axes[1].plot([0, 2], [0, 2], "--", color="#ae4257", label="δ_time = null median")
    axes[1].set(xlabel="Median null LTO", ylabel="δ_time", xlim=(0, 2), ylim=(0, 2))
    axes[1].legend(fontsize=8)
    axes[0].tick_params(axis="x", labelrotation=35, labelsize=8)
    save(fig, "06_temporal_vs_noise", "Chuyển dịch qua thời gian so với nhiễu retraining", "Mỗi điểm là một entity×transition. Vùng màu là IQR (25–75%), không phải khoảng tin cậy. Điểm trên đường chéo có r>0; điều này chưa phải kiểm định ý nghĩa thống kê.")

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for ax, field, label in zip(axes, ("signed_excess", "SED_plus"), ("Signed excess r", "SED+")):
        samples = [[r[field] for r in data["entities"] if r["transition_id"] == t] for t in transitions]
        box = ax.boxplot(samples, positions=ix, widths=.55, patch_artist=True,
                         flierprops={"markersize": 2, "alpha": .25}, medianprops={"color": "#152d43", "linewidth": 1.5})
        for patch in box["boxes"]:
            patch.set_facecolor("#d1e8ed")
        ax.axhline(0, color="#ae4257", linewidth=1)
        ax.set(ylabel=label)
    axes[1].set(xticks=ix, xticklabels=[f"{label}\nn={r['entities']}" for label, r in zip(labels, stats)])
    axes[1].tick_params(axis="x", labelsize=8)
    save(fig, "07_drift_distributions", "Phân bố signed excess và SED+", "Median/IQR, whiskers 1.5×IQR và mọi outlier được hiển thị. r giữ dấu âm; SED+ cắt phần âm về 0 và chuẩn hóa bằng 1.4826×LTO_MAD + 1e−4. Tất cả 6.897 rows được giữ.")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.7))
    rates = [100 * r["positive_excess"] / r["entities"] for r in stats]
    axes[0].bar(ix, rates, color=COLORS[0])
    for i, (rate, r) in enumerate(zip(rates, stats)):
        axes[0].text(i, rate + 1, f"{r['positive_excess']}/{r['entities']}", ha="center", fontsize=7)
    axes[0].set(ylabel="Tỷ lệ r>0 (%)", ylim=(0, 75), xticks=ix, xticklabels=labels)
    axes[1].plot(ix, [r["SED_plus"]["median"] for r in stats], "o-", color=COLORS[0], label="Median")
    axes[1].plot(ix, [r["SED_plus"]["p95"] for r in stats], "o--", color=COLORS[1], label="P95")
    axes[1].set(ylabel="SED+", xticks=ix, xticklabels=labels)
    axes[1].legend()
    for ax in axes:
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
    save(fig, "08_drift_summary", "Tỷ lệ excess dương và phần đuôi SED+", "Phân vị và tỷ lệ mô tả trên toàn population; không có p-value hoặc kiểm định H1. Median thấp vẫn có thể đi cùng một phần đuôi SED+ cao.")

    fig, axes = plt.subplots(1, 3, figsize=(14, 6))
    for ax, field, title, fmt in zip(axes, ("entities", "reference_entities", "SED_plus_median"),
                                   ("Số target entities", "Reference entities mỗi LTO", "Median SED+"), (".0f", ".0f", ".3f")):
        matrix = np.asarray([[next(r[field] for r in data["buckets"] if r["transition_id"] == t and r["bucket_id"] == b) for b in ("low", "medium", "high")] for t in transitions], dtype=float)
        im = ax.imshow(matrix, aspect="auto", cmap="Blues")
        for row in range(9):
            for col in range(3):
                ax.text(col, row, format(matrix[row, col], fmt), ha="center", va="center", fontsize=8,
                        color="white" if matrix[row, col] > (matrix.min() + matrix.max()) / 2 else "#123")
        ax.set(xticks=np.arange(3), xticklabels=["Low\n<3", "Medium\n3–5", "High\n≥6"], yticks=ix, yticklabels=labels, title=title)
        ax.grid(False)
        fig.colorbar(im, ax=ax, shrink=.75)
    save(fig, "09_degree_support", "Degree buckets và support của null LTO", "Degree lấy từ snapshot trước. T01→T02 high bucket có 2 targets; mỗi LTO chỉ còn 1 reference entity/6 correlated pair observations. Giữ nguyên buckets và các guard đã duyệt.")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    for i, seed in enumerate(SEEDS):
        medians = [float(np.median([r[f"delta_seed_{seed}"] for r in data["entities"] if r["transition_id"] == t])) for t in transitions]
        axes[0].plot(ix, medians, "o-", color=COLORS[i], label=f"Seed {seed}")
    axes[0].set(ylabel="Median δ_seed qua entities", xticks=ix, xticklabels=labels)
    axes[0].legend()
    for key, style, label in (("median", "-", "Median"), ("p95", "--", "P95")):
        axes[1].plot(ix, [r["seed_range"][key] for r in stats], "o" + style, label=label)
    axes[1].set(ylabel="max(δ_seed) − min(δ_seed) mỗi entity", xticks=ix, xticklabels=labels)
    axes[1].legend()
    for ax in axes:
        ax.tick_params(axis="x", labelrotation=35, labelsize=8)
    save(fig, "10_seed_variability", "Độ biến thiên displacement giữa ba seeds", "Range đo chênh lệch của ba parallel seed values; không phải sai số chuẩn. δ_time production vẫn là median theo từng entity, không phải median của ba đường tổng hợp trong hình.")
    return figures


def sections(data: dict[str, Any], receipts: dict[str, Any], figures: list[dict[str, str]]) -> list[dict[str, Any]]:
    models, stats = data["models"], data["transition_stats"]
    final = [m["final_loss"] for m in models]
    reduction = [m["loss_reduction_percent"] for m in models]
    alignment = data["alignment"]["results"]
    positive = sum(r["positive_excess"] for r in stats)
    index = {f["id"]: f for f in figures}

    def block(title: str, paragraphs: list[str], ids: list[str] | None = None, table: list[list[Any]] | None = None) -> dict[str, Any]:
        return {"title": title, "paragraphs": paragraphs, "figures": [index[i] for i in (ids or [])], "table": table}

    return [
        block("1. Mục tiêu, phạm vi và kết quả chính", [
            "Mục tiêu của M2 là đo sự thay đổi representation qua thời gian và hiệu chỉnh theo nhiễu do retraining. Backbone giữ TransE-L2; dự án không đề xuất một kiến trúc KGE mới.",
            "Người dùng yêu cầu sử dụng toàn bộ dữ liệu đã upload, bỏ điều kiện nghiệm thu M1 cho lần thực hiện M2 này, tạo nhánh mới và làm từng bước. Nhánh làm việc là codex/m2-drift-workflow, base commit 2860235; công việc M1 đang mở được giữ nguyên.",
            "Đã hoàn tất preflight → pilot → chốt cấu hình → backbone → alignment → empirical null/LTO → longitudinal drift → Dev handoff. 30 checkpoint configurations, 81 alignments, 41.382 noise observations, 20.691 temporal observations và 6.897 entity×transition drift rows đã được lưu và kiểm độc lập.",
            "Báo cáo này bổ sung trực quan hóa và log dễ tra cứu từ artifacts đã lưu; không chạy lại training hoặc thay đổi bất kỳ tham số, snapshot, anchor, bucket, null reference hay metric nào. M3 hiện mới có khung module; M4/QA/statistical inference chưa được thực hiện.",
        ], table=[["Phần", "Trạng thái"], ["M2", "EXECUTED / VERIFIED trong Dev scope"], ["M3 paths / auditor", "Khung module; chưa triển khai thực thi"], ["M4 QA / thống kê", "Chưa thực hiện; bước kế tiếp là readiness"], ["Nghiệm thu khoa học M1 / G3", "Chưa chứng nhận"]]),
        block("2. Kiểm tra đầu vào và tiến trình snapshots", [
            "Nguồn KGE là canonical Parquet của data/KG_lan2/evolving_kg_downstream_v3. Preflight kiểm bytes/hashes, schema ID columns, mappings, counts và cutoff ordering. Giữ toàn bộ provenance columns của canonical export; không dựng private snapshots.",
            "10 snapshots có cùng 10 relations; T01 có 121 triples/167 entities, T10 có 1.205 triples/1.389 entities. Trong gói này các transitions chỉ thêm cạnh/thực thể và giữ toàn bộ population trước đó; đây là giới hạn phạm vi khi diễn giải các thay đổi KG.",
            "Cutoffs do gói bên ngoài cung cấp được giữ nguyên. Các khoảng cách thời gian không đều, đặc biệt T07–T10 tập trung trong tháng 9/2026. Đồ thị theo thứ tự transition chưa phải tốc độ drift mỗi ngày. Historical observation/identity validity của M1 vẫn chưa được chứng nhận.",
        ], ["01_snapshot_growth"], [["Snapshot", "Cutoff (UTC)", "Triples", "Entities", "Relations"]] +
              [[r["snapshot_id"], r["cutoff"], r["triples"], r["entities"], r["relations"]] for r in data["preflight"]["snapshots"]]),
        block("3. Pilot và quyết định 64 chiều", [
            "Pilot thử dimensions 32 và 64, seeds 13/37/101. T01 chia coverage-preserving thành 101 train và 20 validation triples; mỗi seed/dimension có 40 head/tail ranking queries với 167 candidate entities. Có 18 configurations, mỗi configuration chạy từ đầu hai lần (36 training executions).",
            "Mean validation MRR: 32 chiều = 0,110916; 64 chiều = 0,122906. Cả hai dimensions đạt 9/9 pilot alignment checks; quy tắc chọn đã đăng ký trước outcomes đề xuất 64 chiều và người dùng duyệt cấu hình. Chênh lệch khoảng 0,01199 chỉ là kết quả pilot Dev, chưa có kiểm định superiority.",
            "Hits@1 của cả ba seeds 64 chiều bằng 0. Validation thiên về entities có nhiều cạnh do split giữ coverage; kết quả không đại diện cho toàn corpus hoặc QA multi-hop. Dimension không được chọn bằng SED+, RR của QA hay dấu H1.",
            "Independent pilot verifier đo lại 240 ranking rows và 18 SVD alignments từ serialized vectors, kiểm input/output provenance, exact replays và selection.",
        ], ["02_pilot_validation"]),
        block("4. Backbone và log huấn luyện", [
            "Cấu hình đã duyệt: TransE-L2, dimension 64, epochs 50, learning rate 0,01, margin 1, entity normalization và seeds 13/37/101. Mỗi snapshot/seed train từ đầu độc lập trên toàn snapshot. Field batch_size=32 có trong cấu hình, nhưng implementation cập nhật per-triple; báo cáo không gọi đây là mini-batch training.",
            "30 configurations × 2 repeats = 60 training executions, mất 160,32 giây theo stage log. 30/30 replay checkpoint pairs byte-identical trong môi trường đã dùng; full mapping/config/snapshot/seed/git lineage và finite losses/embeddings được kiểm độc lập.",
            f"Loss epoch 50 nằm trong [{min(final):.6f}, {max(final):.6f}]. Median giảm loss so với epoch 1 là {float(np.median(reduction)):.2f}%, range [{min(reduction):.2f}%, {max(reduction):.2f}%]. Các giá trị này chỉ mô tả training diagnostics.",
            "Đã xuất 1.500 epoch log rows cho 30 mô hình × 50 epoch từ repeat 1; repeat 2 đã chứng minh exact byte replay. Full-snapshot training không có validation loss. Không có intermediate embeddings/checkpoints theo từng epoch trong run này, nên không thể vẽ quỹ đạo embedding hoặc drift theo epoch từ log hiện có.",
            "Loss là margin-ranking objective với negative sampling. Đường loss giảm và có dao động; không tuyên bố đã hội tụ tối ưu, khái quát tốt hay có QA quality chỉ từ biểu đồ loss. Phần Log huấn luyện trong báo cáo HTML cho phép chọn snapshot/seed, đọc epoch và tải log đang chọn.",
        ], ["03_training_losses", "04_training_summary"], [["Snapshot", "Triples", "Entities", "Loss seed 13", "Loss seed 37", "Loss seed 101"]] +
              [[sid, next(m["triples"] for m in models if m["snapshot_id"] == sid), next(m["entities"] for m in models if m["snapshot_id"] == sid)] +
               [f"{next(m['final_loss'] for m in models if m['snapshot_id'] == sid and m['seed'] == seed):.6f}" for seed in SEEDS]
               for sid in [r["snapshot_id"] for r in data["preflight"]["snapshots"]]]),
        block("5. Centered Procrustes alignment", [
            "Anchors là persistent canonical entities, phân tầng theo exact degree ở snapshot trước. Split cố định, deterministic và disjoint: 101 fit / 66 holdout; cùng split dùng cho mọi comparison trong một transition. Không chọn anchors theo drift, fact-change labels hoặc QA outcomes.",
            "81 comparisons = 9 transitions × (3 cross-time same-seed + 6 same-snapshot cross-seed tại hai endpoints). Mỗi comparison chạy SVD hai lần, tổng 162 SVD executions; 81/81 exact replays và 81/81 available theo các guard Dev đã duyệt.",
            f"Tất cả numerical rank bằng 64. Max holdout RMSE = {max(r['diagnostics']['holdout_residual'] for r in alignment):.6f}; max holdout−fit gap = {max(r['diagnostics']['fit_holdout_gap'] for r in alignment):.6f}; max orthogonality error = {max(r['diagnostics']['orthogonality_error'] for r in alignment):.6e}.",
            "Guard đã duyệt trước measurement: rank tối thiểu 64, holdout RMSE tối đa 2, gap tối đa 1, orthogonality error tối đa 1e−4. Đạt numerical diagnostics trong Dev scope không tương đương semantic stability hoặc G3 scientific certification.",
        ], ["05_alignment_diagnostics"]),
        block("6. Empirical null và Leave-Target-Out", [
            "Mỗi persistent entity có 6 noise observations: seed pairs (13,37), (13,101), (37,101) ở mỗi endpoint. Noise dùng saved centered Q/fit means; không re-align. Có 41.382 observations; các seed-pair observations có tương quan và không được tính là 6 statistical units độc lập.",
            "Buckets dùng degree ở snapshot trước: low <3, medium 3–5, high ≥6. Sparse merging pooled theo adjacency, tie về trái; trong run thật không có merge. LTO bỏ toàn bộ 6 observations của target, rồi tính median/MAD/robust scale từ reference entities còn lại. Không target-specific remerge.",
            "Guard reference: ít nhất 5 observations và MAD≥1e−12; scale=1,4826×MAD. Empty/degenerate references phải unavailable có reason. 6.897/6.897 references available theo rules đã duyệt, nhưng numerical availability chưa chứng minh adequate inferential support.",
            "T01→T02 high bucket chỉ có 2 target entities: mỗi LTO còn 1 reference entity và 6 correlated observations. Bảng/biểu đồ support giữ rõ hạn chế này; không đổi threshold/buckets sau khi nhìn outcomes.",
        ], ["09_degree_support"]),
        block("7. Longitudinal drift: displacement, signed excess và SED+", [
            "Mỗi seed: δ_seed = 1 − cos((x_previous − μ_source)Q, y_next − μ_target). Dùng đúng ba cross-time parallel seeds 13/37/101; δ_time là median ba values của từng entity. Undefined centered cosine hoặc unavailable alignment làm stage dừng, không sinh defaults.",
            "Signed excess r = δ_time − LTO_null_median, giữ cả giá trị âm. SED+ = max(0,r)/(1,4826×LTO_MAD + 0,0001), chỉ khi null available. Epsilon không được dùng để cứu ZERO_MAD/thiếu reference.",
            f"Có 20.691 temporal observations và 6.897 entity×transition drift rows, đều available theo Dev config. {positive:,} rows có r>0 ({100 * positive / 6897:.2f}%); {6897 - positive:,} rows âm được giữ và có SED+=0. SED+ lớn nhất {max(r['SED_plus'] for r in data['entities']):.6f}.".replace("3,640", "3.640").replace("3,257", "3.257"),
            "Giá trị SED+ lớn nhất thuộc high bucket của T01→T02, nơi mỗi LTO chỉ có một reference entity. Đây là điểm cần đọc cùng support counts; extreme SED+ trong bucket nhỏ chưa đủ cơ sở cho kết luận drift có ý nghĩa thống kê.",
            "Independent NumPy verifier đo lại toàn bộ temporal/calibrated values, kiểm 549 input hashes, 57 artifact hashes, 9 transition manifests, JSON/Parquet equality, replays và Dev handoff. 9/9 transition JSON repeats và 2/2 Parquet serialization repeats exact bytes.",
            "Một r>0 hay SED+ cao chỉ là chỉ số mô tả representation movement trên noise reference. Chưa có p-value, kiểm định H1, ước lượng tác động QA hoặc kết luận nhân quả. Population và upstream measurement parameters không thay đổi theo các đồ thị mới.",
        ], ["06_temporal_vs_noise", "07_drift_distributions", "08_drift_summary", "10_seed_variability"],
              [["Transition", "n", "Median δ_time", "Median r", "Median SED+", "P95 SED+", "r>0", "Min LTO entities"]] +
              [[r["transition_id"].replace("->", "→"), r["entities"], f"{r['delta_time']['median']:.6f}", f"{r['signed_excess']['median']:.6f}",
                f"{r['SED_plus']['median']:.6f}", f"{r['SED_plus']['p95']:.6f}", r["positive_excess"], r["min_reference_entities"]] for r in stats]),
        block("8. Kiểm chứng, tái lập và artifact lineage", [
            "Các stage độc lập theo thứ tự inspect → plan → implement → test → execute → validate → report → dừng. Mỗi lần advance có yêu cầu người dùng. Artifacts mới append-only; old runs và historical source data được giữ nguyên.",
            "Bản M2 cuối được full suite kiểm: 505 passed, 10 existing skipped; Ruff và diff checks PASS, Python 3.11.9. 10 skip là placeholder tests có sẵn, không dùng để nghiệm thu gate. Python 3.10 chưa được chạy local.",
            "IMPLEMENTED: code/guards/manifests đã viết. TESTED: fixtures/contract/scientific regression. EXECUTED: stage chạy trên real artifact-backed data. VERIFIED: verifier độc lập kiểm lại arithmetic/population/lineage. Các tier này áp dụng đúng scope Dev, không xác minh bổ sung M1 temporal semantics.",
            "Báo cáo mới kiểm lại source manifest/receipt fingerprints và các source hash catalogs trước khi trích log/vẽ. Report manifest bind source hashes, exact report/plot/log hashes và archived report code/template. Không có hosted scientific decision-maker hoặc truy cập locked_test.",
        ], table=[["Stage", "Run", "Independent receipt", "Manifest SHA-256"]] +
              [[name, RUNS[name], receipts[name]["status"] if name in receipts else "Preflight technical inventory", sha((ROOT / RUNS[name] / "experiment_manifest.json").read_bytes())] for name in RUNS]),
        block("9. Những phần còn thiếu và bước tiếp theo", [
            "M2 Dev đã hoàn tất đến entity-level drift và handoff. M1 G1/G2/official handoff và scientific G3 chưa được chứng nhận; scientific protocol vẫn còn các giá trị chờ freeze. Numerical PASS của run này không chuyển trạng thái các gate đó.",
            "M3 bounded paths và semantic auditor mới có khung module, chưa triển khai/chạy. Đây là support track; không dùng việc chờ M3 để chặn CORE. M4 chưa có recurring QA panel đã chốt trong gói đang dùng; chưa chạy Arms A/B/C, RR/MRR QA, H1/H2, WCB hoặc pseudo-drift falsification.",
            "Bước kế tiếp là M4 readiness: kiểm query/gold/support evidence theo cutoff, recurring population, Seen-at-T1/candidate universes và complete-support joins với drift. Khi panel/rules đầy đủ mới thực hiện đánh giá theo stage authorization. Trước kết luận khoa học chính thức cần hoàn tất nghiệm thu M1/G3.",
            "Các biểu đồ hiện có phản ánh loss theo epoch và movement giữa snapshots. Chưa có log gradient, intermediate embedding trajectories hoặc validation mỗi epoch của full-snapshot backbone; báo cáo giữ rõ phạm vi log thật, không dựng dữ liệu giả.",
        ]),
    ]


def render_reports(out: Path, blocks: list[dict[str, Any]], data: dict[str, Any]) -> None:
    title = "Báo cáo toàn bộ quy trình M2 — huấn luyện, alignment, nhiễu và drift"
    markdown, rendered = [f"# {title}\n\nNgày: 14/10/2026. Phạm vi: external-package Dev, scientific_certification=false.\n"], []
    for i, block in enumerate(blocks):
        markdown.append(f"## {block['title']}\n")
        section = [f'<section id="section-{i + 1}"><h2>{html.escape(block["title"])}</h2>']
        for paragraph in block["paragraphs"]:
            markdown.append(paragraph + "\n")
            section.append(f"<p>{html.escape(paragraph)}</p>")
        table = block["table"]
        if table:
            table_lines = ["| " + " | ".join(map(str, table[0])) + " |", "| " + " | ".join("---" for _ in table[0]) + " |"]
            table_lines.extend("| " + " | ".join(str(v).replace("|", "\\|") for v in row) + " |" for row in table[1:])
            markdown.append("\n".join(table_lines) + "\n")
            section.append('<div class="table-wrap"><table><thead><tr>' + "".join(f"<th>{html.escape(str(v))}</th>" for v in table[0]) + "</tr></thead><tbody>")
            for row in table[1:]:
                section.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row) + "</tr>")
            section.append("</tbody></table></div>")
        for figure in block["figures"]:
            markdown.append(f"![{figure['title']}](<{(out / figure['png']).as_posix()}>)\n\n{figure['caption']}\n")
            encoded = base64.b64encode((out / figure["png"]).read_bytes()).decode()
            section.append(f'<figure><img loading="lazy" src="data:image/png;base64,{encoded}" alt="{html.escape(figure["title"])}"><figcaption>{html.escape(figure["caption"])}</figcaption></figure>')
        section.append("</section>")
        rendered.append("".join(section))
    markdown.append("## Log và các file bàn giao\n")
    for name, description in (("report.html", "Báo cáo và bảng tra cứu tương tác"), ("training_epoch_log.jsonl", "1.500 log epoch huấn luyện"),
                              ("entity_drift_log.jsonl", "6.897 log drift có ba seed values"), ("analysis_summary.json", "Thống kê và dữ liệu nguồn cho biểu đồ"),
                              ("experiment_manifest.json", "Report lineage và hashes")):
        markdown.append(f"- [{description}](<{(out / name).as_posix()}>)")
    with (out / "report.md").open("x", encoding="utf-8") as handle:
        handle.write("\n\n".join(markdown))
    payload = {"models": [{k: m[k] for k in ("snapshot_id", "seed", "epoch_losses", "checkpoint_sha256", "first_loss", "final_loss")} for m in data["models"]],
               "entities": data["entities"], "transitions": data["transitions"]}
    safe_json = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    template = (ROOT / "scripts/templates/m2_report.html").read_text(encoding="utf-8")
    document = template.replace("__REPORT_CONTENT__", "\n".join(rendered)).replace("__REPORT_DATA__", safe_json)
    with (out / "report.html").open("x", encoding="utf-8") as handle:
        handle.write(document)


def run() -> Path:
    manifests, source_hashes, receipts = checked_sources()
    data = extract_data()
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/m2_report" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "source_hashes.json", source_hashes)
    write_json(out / "source_verification_receipts.json", receipts)
    resolved = {"version": "m2_descriptive_report_v1", "source_runs": RUNS, "scientific_certification": False,
                "measurement_parameters_changed": False, "training_reexecuted": False, "auto_execute_M3_M4": False,
                "quantiles": [0.25, 0.5, 0.75, 0.95], "boxplot_whisker_IQR": 1.5,
                "note": "IQR and percentiles are descriptive, no confidence intervals or inferential tests"}
    write_json(out / "resolved_config.json", resolved)
    json_lines(out / "training_epoch_log.jsonl", data["training"])
    json_lines(out / "entity_drift_log.jsonl", data["entities"])
    figures = make_figures(out, data)
    analysis = {"scientific_certification": False, "training_epochs": len(data["training"]), "entity_drift_rows": len(data["entities"]),
                "transition_stats": data["transition_stats"], "degree_support": data["buckets"], "figures": figures,
                "final_loss_range": [min(m["final_loss"] for m in data["models"]), max(m["final_loss"] for m in data["models"])],
                "loss_reduction_percent_range": [min(m["loss_reduction_percent"] for m in data["models"]), max(m["loss_reduction_percent"] for m in data["models"])],
                "total_positive_excess": sum(r["positive_excess"] for r in data["transition_stats"]),
                "total_negative_excess": sum(r["signed_excess"] < 0 for r in data["entities"]),
                "SED_plus_max": max(r["SED_plus"] for r in data["entities"])}
    write_json(out / "analysis_summary.json", analysis)
    render_reports(out, sections(data, receipts, figures), data)
    code_hashes = {}
    for relative in ("scripts/build_m2_report.py", "scripts/verify_m2_report.py", "scripts/templates/m2_report.html", "scripts/inspect_m2_inputs.py"):
        source = safe_file(ROOT, relative)
        target = out / "code" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(source.read_bytes())
        code_hashes[relative] = sha(source.read_bytes())
    environment = {"python": platform.python_version(), "os": platform.platform(), "matplotlib": matplotlib.__version__,
                   "numpy": np.__version__, "pyarrow": importlib.metadata.version("pyarrow"),
                   "plot_dependencies": {name: importlib.metadata.version(name) for name in ("matplotlib", "numpy", "pillow", "fonttools", "contourpy", "cycler", "kiwisolver", "packaging", "pyparsing", "python-dateutil", "six")}}
    for relative, digest in source_hashes.items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Source changed during report generation: {relative}")
    parent = manifests["drift"]
    manifest = {"experiment_id": out.name, "protocol_version": "v1-draft", "stage": "descriptive_report",
                "mode": "external_package_dev_experiment", "scientific_certification": False, "git": provenance(), "seed": None,
                "inputs": {**{k: parent["inputs"][k] for k in ("snapshot_hash", "entity_map_hash", "relation_map_hash")},
                           "data_hash": sha(encode(source_hashes)), "query_hash": None, "config_hash": sha(encode(resolved)),
                           "hashes": source_hashes, "code_hashes": code_hashes,
                           "source_manifest_hashes": {name: sha((ROOT / relative / "experiment_manifest.json").read_bytes()) for name, relative in RUNS.items()}},
                "environment": environment, "hardware": {"cpu": platform.processor(), "ram": None},
                "artifacts": {"hashes": {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}},
                "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/build_m2_report.py"}}
    validate_manifest(manifest)
    write_json(out / "experiment_manifest.json", manifest)
    print(json.dumps({"output": str(out), "figures": len(figures), "training_log_rows": 1500, "drift_log_rows": 6897,
                      "source_hashes_checked": len(source_hashes), "source_unchanged": True, "new_training": False}, indent=2))
    return out


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
