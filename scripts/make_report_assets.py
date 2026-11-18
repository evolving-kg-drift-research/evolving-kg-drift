"""Generate Vietnamese report assets from the five registered JSON reports."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import ScalarFormatter

matplotlib.use("Agg")


class CommaFormatter(ScalarFormatter):
    """Vietnamese decimal comma for numeric tick labels."""

    def __call__(self, x: float, pos: int | None = None) -> str:
        return super().__call__(x, pos).replace(".", ",")


def use_decimal_comma(figure: Figure) -> None:
    for axis in figure.axes:
        for ticks in (axis.xaxis, axis.yaxis):
            if type(ticks.get_major_formatter()) is ScalarFormatter:
                ticks.set_major_formatter(CommaFormatter())

JSON = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
Record = dict[str, JSON]
ROOT = Path(__file__).resolve().parents[1]
REPORT = Path("reports/report_latex_final")
SOURCES: dict[str, str] = {
    "S1": "data/evolving_kg_downstream_v3_3/reports/s1_validation_report.json",
    "S3": "outputs/s3_backbone_v33/20261117T194615Z_fd779c44_r1/train/s3_report.json",
    "S5": "outputs/s5_drift_v33/20261117T195720Z_d5692c54/s5_s6_report.json",
    "N1D": "outputs/n1_h1_v33/20261117T201007Z_19ea4bcf/n1_drift_report.json",
    "N1H": "outputs/n1_h1_v33/20261117T201007Z_19ea4bcf/h1/n1_h1_report.json",
}
DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "generated/tab_snapshots.tex": ("S1",),
    "generated/tab_quality.tex": ("S3",),
    "generated/tab_stability.tex": ("S3",),
    "generated/tab_population.tex": ("S5",),
    "generated/tab_poscontrol_population.tex": ("S5",),
    "generated/tab_poscontrol_s3.tex": ("N1D",),
    "generated/tab_h1.tex": ("N1H",),
    "generated/tab_panel.tex": ("N1H", "N1D"),
    "figures/fig_noise_by_degree.png": ("S3",),
    "figures/fig_positive_control.png": ("N1D",),
    "figures/fig_h1_forest.png": ("N1H",),
    "figures/fig_panel_transitions.png": ("N1H",),
    "figures/fig_detect_by_degree.png": ("S5", "N1D"),
    "figures/fig_evidence_chain.png": ("S3", "S5", "N1D", "N1H"),
    "generated/SOURCES.txt": tuple(SOURCES),
}
EPOCHS = ("E300", "E400", "E500")
BUCKETS = ("[0, 2]", "[3, 5]", "[6, 1000000]")
COLORS = ("#176b88", "#bf642b", "#7759aa")
SPECS: dict[str, str] = {
    "primary": r"Chính (trung vị SED$^+$)",
    "falsification_pseudo": "Kiểm chứng bằng độ trôi giả",
    "control_log_degree": "Có biến kiểm soát (log bậc)",
    "exposure_signed_excess": "Phụ: phần dư có dấu",
    "exposure_max": r"Phụ: SED$^+$ lớn nhất",
    "uncapped": "Không giới hạn số câu mỗi thực thể đầu",
    "hop2": "Chỉ câu 2 chặng",
    "hop3": "Chỉ câu 3 chặng",
}


def obj(value: JSON) -> Record:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def num(value: JSON) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"Expected a finite JSON number, got {value!r}")
    return value


def fmt(x: JSON, nd: int) -> str:
    """Format a count, or a decimal in LaTeX math with a Vietnamese comma."""
    value = num(x)
    if value is None:
        return "--"
    if nd == 0:
        if value != int(value):
            raise ValueError(f"Expected an integer count, got {value!r}")
        return str(int(value))
    return "$" + f"{np.round(value, nd):.{nd}f}".replace(".", "{,}") + "$"


def pct(value: JSON) -> str:
    number = num(value)
    return "--" if number is None else fmt(100 * number, 1).removesuffix("$") + r"\%$"


def yes_no(value: JSON) -> str:
    if value is None:
        return "--"
    if not isinstance(value, bool):
        raise ValueError(f"Expected a JSON boolean, got {value!r}")
    return "Có" if value else "Không"


def plot_number(value: JSON) -> float:
    number = num(value)
    return np.nan if number is None else float(number)


def row(*cells: str) -> str:
    return " & ".join(cells) + r" \\"


def tabular(columns: str, headers: list[str], rows: list[str]) -> str:
    return "\n".join(
        [
            r"\begin{tabular}{" + columns + "}",
            r"\toprule",
            *headers,
            r"\midrule",
            *rows,
            r"\bottomrule",
            r"\end{tabular}",
            "",
        ]
    )


def pooled_sensitivity(buckets: Record, keys: tuple[str, ...]) -> float | None:
    """Pool by injected counts; an empty or incomplete stratum stays missing."""
    total = 0.0
    detected = 0.0
    for key in keys:
        bucket = obj(buckets.get(key))
        injected = num(bucket.get("injected"))
        if injected is None or injected < 0:
            return None
        if injected == 0:
            continue
        sensitivity = num(bucket.get("sensitivity"))
        if sensitivity is None:
            return None
        total += injected
        detected += injected * sensitivity
    return detected / total if total else None


def make_tables(reports: dict[str, Record]) -> dict[str, str]:
    s1, s3, s5, n1d, n1h = (reports[key] for key in SOURCES)
    tables: dict[str, str] = {}
    snapshots = s1["snapshots"]
    if not isinstance(snapshots, list):
        raise ValueError("S1.snapshots must be a JSON array")
    rows: list[str] = []
    for snapshot in sorted((obj(item) for item in snapshots), key=lambda item: str(item["snapshot_id"])):
        cutoff = snapshot.get("cutoff")
        rows.append(
            row(
                str(snapshot["snapshot_id"]),
                "--" if cutoff is None else str(cutoff)[:10],
                fmt(snapshot.get("triples"), 0),
                fmt(snapshot.get("entities"), 0),
                fmt(snapshot.get("duration_days"), 1),
            )
        )
    tables["generated/tab_snapshots.tex"] = tabular(
        "llrrr",
        [
            row(
                "Lát cắt",
                "Ngày chốt",
                "Số bộ ba",
                "Số thực thể",
                "Độ dài (ngày)",
            )
        ],
        rows,
    )

    quality = obj(s3["quality"])
    rows = []
    for snapshot_id in sorted(quality):
        quality_row = obj(quality[snapshot_id])
        ci = quality_row.get("ci95")
        if ci is None:
            interval = "--"
        elif isinstance(ci, list) and len(ci) == 2:
            interval = "[" + fmt(ci[0], 3) + "; " + fmt(ci[1], 3) + "]"
        else:
            raise ValueError(f"Invalid ci95 for {snapshot_id}")
        rows.append(
            row(
                snapshot_id,
                fmt(quality_row.get("heldout_triples"), 0),
                fmt(quality_row.get("model_mrr"), 3),
                interval,
                fmt(quality_row.get("frequency_baseline_mrr"), 3),
                fmt(quality_row.get("random_baseline_mrr"), 4),
            )
        )
    tables["generated/tab_quality.tex"] = tabular(
        "lrrrrr",
        [
            row(
                "Lát cắt",
                "Số bộ ba để kiểm tra",
                "MRR mô hình",
                r"CI 95\%",
                "MRR cách đoán theo tần suất",
                "MRR ngẫu nhiên",
            )
        ],
        rows,
    )

    stability = obj(s3["stability"])
    rows = []
    for snapshot_id in sorted(stability):
        stable = obj(stability[snapshot_id])
        buckets = obj(stable["buckets"])
        cells = [snapshot_id, fmt(stable.get("random_reference_median"), 3)]
        for key in BUCKETS:
            bucket = obj(buckets[key])
            skipped = str(bucket.get("status", "")).startswith("NOT_EVALUATED")
            distance = fmt(None if skipped else bucket.get("median_distance"), 3)
            cells.append(f"{distance} ({fmt(bucket.get('holdout_anchors'), 0)})")
        rows.append(row(*cells))
    tables["generated/tab_stability.tex"] = tabular(
        "lrrrr",
        [
            row(
                "Lát cắt",
                "Mốc ngẫu nhiên",
                r"Bậc $<3$",
                "Bậc 3--5",
                r"Bậc $\geq 6$",
            )
        ],
        rows,
    )

    rows = []
    for epoch in EPOCHS:
        result = obj(s5[epoch])
        main, negative = obj(result["main"]), obj(result["negative_control"])
        rows.append(
            row(
                epoch[1:],
                fmt(main.get("available"), 0),
                pct(main.get("share_signed_excess_pos")),
                pct(main.get("share_sed_ge2")),
                pct(negative.get("share_signed_excess_pos")),
                pct(negative.get("share_sed_ge2")),
            )
        )
    tables["generated/tab_population.tex"] = tabular(
        "rrrrrr",
        [
            row(
                "$E$",
                "Số thực thể khả dụng",
                r"Độ trôi: tỷ lệ phần dư dương",
                r"Độ trôi: tỷ lệ SED$^+\geq 2$",
                r"Đối chứng âm: tỷ lệ phần dư dương",
                r"Đối chứng âm: SED$^+\geq 2$",
            )
        ],
        rows,
    )

    per_run = obj(obj(s5["positive_control_E400"])["per_run"])
    rows = []
    for run in sorted(per_run, key=lambda key: (key.split("@")[0], float(key.split("@")[1]))):
        result = obj(per_run[run])
        transition, strength = run.split("@")
        label = transition.replace("->", r"$\to$") + ", " + strength.replace(".", ",")
        buckets = obj(result["by_bucket"])
        rows.append(
            row(
                label,
                fmt(result.get("injected"), 0),
                pct(result.get("sensitivity")),
                pct(result.get("false_positive_rate")),
                pct(pooled_sensitivity(buckets, ("0",))),
                pct(pooled_sensitivity(buckets, ("1", "2"))),
            )
        )
    flags = "; ".join(
        f"{epoch}: {yes_no(obj(s5['positive_control_' + epoch]).get('detectable_registered_rule'))}" for epoch in EPOCHS
    )
    rows.extend([r"\midrule", r"\multicolumn{6}{l}{Đạt quy tắc phát hiện: " + flags + r"} \\"])
    tables["generated/tab_poscontrol_population.tex"] = tabular(
        "lrrrrr",
        [
            row(
                "Lần thử",
                "Số thực thể bị thay đổi có chủ đích",
                "Độ nhạy",
                "Tỷ lệ dương tính giả",
                r"Độ nhạy bậc $<3$",
                r"Độ nhạy bậc $\geq 3$",
            )
        ],
        rows,
    )

    positive = obj(n1d["positive_control"])
    strengths = sorted(obj(obj(positive[EPOCHS[0]])["pooled"]), key=float)
    rows = []
    for strength in strengths:
        cells = [fmt(float(strength), len(strength.split(".")[1]))]
        for epoch in EPOCHS:
            pooled = obj(obj(obj(positive[epoch])["pooled"])[strength])
            cells.extend(
                [
                    pct(pooled.get("sensitivity")) + f" ({fmt(pooled.get('injected'), 0)})",
                    pct(pooled.get("false_positive_rate")),
                ]
            )
        rows.append(row(*cells))
    rows.append(r"\midrule")
    for flag in ("testable_large", "testable_moderate"):
        rows.append(
            row(
                {"testable_large": "Đạt tiêu chí thay đổi lớn", "testable_moderate": "Đạt tiêu chí thay đổi vừa"}[flag],
                *(r"\multicolumn{2}{c}{" + yes_no(obj(positive[epoch]).get(flag)) + "}" for epoch in EPOCHS),
            )
        )
    tables["generated/tab_poscontrol_s3.tex"] = tabular(
        "lrrrrrr",
        [
            row("Cường độ", *(r"\multicolumn{2}{c}{$E=" + epoch[1:] + "$}" for epoch in EPOCHS)),
            r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
            row("", *(["Độ nhạy", "Dương tính giả"] * len(EPOCHS))),
        ],
        rows,
    )

    estimates = obj(n1h["estimates"])
    rows = []
    for index, epoch in enumerate(EPOCHS):
        if index:
            rows.append(r"\midrule")
        for spec, label in SPECS.items():
            estimate = obj(estimates.get(f"{epoch}|{spec}", {}))
            cells = [epoch[1:], label]
            if estimate.get("status") == "OK":
                cells.extend(
                    fmt(estimate.get(key), nd)
                    for key, nd in (
                        ("n_obs", 0),
                        ("n_queries", 0),
                        ("beta", 3),
                        ("se", 3),
                        ("p_wcb", 3),
                        ("mde80", 3),
                    )
                )
            else:
                cells.extend(["--"] * 6)
            rows.append(row(*cells))
    tables["generated/tab_h1.tex"] = tabular(
        "rlrrrrrr",
        [
            row(
                "$E$",
                "Mô hình",
                "Số quan sát",
                "Số câu hỏi",
                r"$\hat\beta$",
                "Sai số chuẩn theo cụm",
                r"$p_{\mathrm{WCB}}$",
                r"MDE$_{80}$",
            )
        ],
        rows,
    )

    transitions = obj(n1d["usable_transitions"])
    entities, usable = obj(transitions["s3_entities"]), obj(transitions["usable"])
    panel_rows = obj(obj(n1h["panel"])["by_transition"])
    rows = [
        row(
            transition.replace("->", r"$\to$"),
            fmt(entities[transition], 0),
            yes_no(usable.get(transition)),
            fmt(panel_rows.get(transition, 0), 0),
        )
        for transition in sorted(entities)
    ]
    tables["generated/tab_panel.tex"] = tabular(
        "lrcr",
        [
            row(
                "Chuyển tiếp",
                r"Số thực thể bậc $\geq 3$",
                "Khả dụng",
                "Số dòng bảng câu hỏi",
            )
        ],
        rows,
    )
    return tables


def figure_detect_by_degree(reports: dict[str, Record]) -> Figure:
    """Detection rate of deliberately changed entities by degree group (full change of neighbours)."""
    s5 = reports["S5"]
    n1 = reports["N1D"]
    fig = Figure(figsize=(7.2, 4.2))
    axis = fig.add_subplot()
    groups = ["Bậc 1–2\n(≈ 90% thực thể)", "Bậc ≥ 3\n(≈ 10% thực thể)"]
    xs = np.arange(len(groups))
    width = 0.25
    for k, epoch in enumerate(EPOCHS):
        runs = obj(obj(s5[f"positive_control_{epoch}"])["per_run"])
        low = [obj(obj(v)["by_bucket"]).get("0") for key, v in runs.items() if key.endswith("@1.0")]
        n_low = sum(num(obj(b).get("injected")) or 0 for b in low if b)
        d_low = sum((num(obj(b).get("injected")) or 0) * (num(obj(b).get("sensitivity")) or 0) for b in low if b)
        high = num(obj(obj(obj(obj(n1["positive_control"])[epoch])["pooled"])["1.0"]).get("sensitivity"))
        values = [d_low / n_low if n_low else 0.0, high or 0.0]
        bars = axis.bar(xs + (k - 1) * width, values, width, label=f"E={epoch[1:]} vòng huấn luyện")
        for bar, v in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2, v + 0.02, f"{v:.0%}".replace(".", ","), ha="center", fontsize=8)
    axis.set_xticks(xs, groups)
    axis.set_ylim(0, 1.1)
    axis.set_ylabel("Tỷ lệ thay đổi được phát hiện")
    axis.set_title("Thay toàn bộ quan hệ của một thực thể: phép đo có nhận ra không?", fontsize=10)
    axis.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    return fig


def figure_evidence_chain(reports: dict[str, Record]) -> Figure:
    """Pass/fail of each step of the evidence chain, read from the reports."""
    s3, s5, n1, h1 = reports["S3"], reports["S5"], reports["N1D"], reports["N1H"]
    pos = obj(n1["positive_control"])
    steps = [
        ("1. Dữ liệu", "Sửa trục thời gian,\nđịnh danh thực thể", True),
        ("2. Mô hình nhúng", "Vượt cách đoán đơn giản\nở cả 10 lát cắt", str(s3.get("status", "")).endswith("PASS")),
        ("3. Phép đo (toàn bộ)", "Không phân biệt được\nvới nhiễu", bool(obj(s5["positive_control_E400"]).get("detectable_registered_rule"))),
        ("4. Phép đo (bậc ≥ 3)", "Nhận ra thay đổi lớn,\nbáo động giả tăng dần",
         all(bool(obj(pos[e]).get("testable_large")) for e in EPOCHS)),
        ("5. Giả thuyết H1", "Không kiểm định được",
         str(obj(h1["decision"]).get("H1_status")) == "TESTABLE"),
    ]
    fig = Figure(figsize=(9.6, 2.9))
    axis = fig.add_subplot()
    axis.set_xlim(0, len(steps))
    axis.set_ylim(0, 1)
    axis.axis("off")
    for i, (title, note, ok) in enumerate(steps):
        color = "#2e7d32" if ok else "#c62828"
        axis.add_patch(Rectangle((i + 0.06, 0.18), 0.88, 0.66, color=color, alpha=0.12, ec=color, lw=1.5))
        axis.text(i + 0.5, 0.70, title, ha="center", va="center", fontsize=9.5, weight="bold")
        axis.text(i + 0.5, 0.45, note, ha="center", va="center", fontsize=8)
        axis.text(i + 0.5, 0.25, "ĐẠT" if ok else "KHÔNG ĐẠT", ha="center", va="center", fontsize=8.5, color=color, weight="bold")
        if i < len(steps) - 1:
            axis.annotate("", xy=(i + 1.04, 0.51), xytext=(i + 0.96, 0.51), arrowprops={"arrowstyle": "->", "color": "grey"})
    fig.tight_layout()
    return fig


def make_figures(reports: dict[str, Record]) -> dict[str, Figure]:
    matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "text.usetex": False})
    figures: dict[str, Figure] = {}
    stability = obj(reports["S3"]["stability"])
    snapshots = sorted(stability)
    x = np.arange(len(snapshots))
    figure = Figure(figsize=(7.2, 4.2))
    axis = figure.add_subplot()
    for key, label, color in zip(BUCKETS, ("Bậc < 3", "Bậc 3--5", "Bậc ≥ 6"), COLORS):
        distances: list[float] = []
        for snapshot in snapshots:
            bucket = obj(obj(obj(stability[snapshot])["buckets"])[key])
            skipped = str(bucket.get("status", "")).startswith("NOT_EVALUATED")
            distances.append(plot_number(None if skipped else bucket.get("median_distance")))
        axis.plot(x, distances, marker="o", markersize=4, label=label, color=color)
    references = [plot_number(obj(stability[snapshot]).get("random_reference_median")) for snapshot in snapshots]
    finite_references = [value for value in references if np.isfinite(value)]
    if finite_references:
        axis.axhline(float(np.mean(finite_references)), linestyle="--", color="grey", label="Mốc ngẫu nhiên")
    axis.set_xticks(x, snapshots)
    axis.set_xlabel("Lát cắt thời gian")
    axis.set_ylabel("Độ lệch giữa các lần huấn luyện lại")
    axis.grid(axis="y", alpha=0.2)
    axis.legend()
    figure.tight_layout()
    figures["figures/fig_noise_by_degree.png"] = figure

    positive = obj(reports["N1D"]["positive_control"])
    strengths = sorted(obj(obj(positive[EPOCHS[0]])["pooled"]), key=float)
    strength_values = [float(strength) for strength in strengths]
    figure = Figure(figsize=(7.2, 4.2))
    left, right = figure.add_subplot(1, 2, 1), figure.add_subplot(1, 2, 2)
    for epoch, color in zip(EPOCHS, COLORS):
        pooled = obj(obj(positive[epoch])["pooled"])
        for axis, metric in ((left, "sensitivity"), (right, "false_positive_rate")):
            axis.plot(
                strength_values,
                [plot_number(obj(pooled[strength]).get(metric)) for strength in strengths],
                marker="o",
                color=color,
                label=f"E={epoch[1:]}",
            )
    left.axhline(0.80, linestyle="--", color="grey", label="ngưỡng tiêu chí 0,80")
    right.axhline(0.10, linestyle="--", color="grey", label="ngưỡng 0,10")
    left.set_ylabel("Độ nhạy")
    right.set_ylabel("Tỷ lệ dương tính giả")
    left.set_ylim(0, 1.05)
    right.set_ylim(bottom=0)
    for axis in (left, right):
        axis.set_xlabel("Cường độ viết lại cạnh")
        axis.set_xticks(strength_values, [strength.replace(".", ",") for strength in strengths])
        axis.grid(axis="y", alpha=0.2)
        axis.legend(fontsize=7)
    figure.tight_layout()
    figures["figures/fig_positive_control.png"] = figure

    estimates = obj(reports["N1H"]["estimates"])
    figure = Figure(figsize=(7.2, 4.2))
    axis = figure.add_subplot()
    labels: list[str] = []
    for epoch, color in zip(EPOCHS, COLORS):
        for spec, label, marker in (
            ("primary", "chính", "o"),
            ("falsification_pseudo", "kiểm chứng giả", "s"),
        ):
            position = len(EPOCHS) * 2 - 1 - len(labels)
            labels.append(f"E={epoch[1:]} {label}")
            estimate = obj(estimates.get(f"{epoch}|{spec}", {}))
            ok = estimate.get("status") == "OK"
            beta, se = (num(estimate.get(key)) if ok else None for key in ("beta", "se"))
            if beta is not None and se is not None:
                if se < 0:
                    raise ValueError(f"Negative standard error: {epoch}|{spec}")
                axis.errorbar(
                    beta,
                    position,
                    xerr=1.96 * se,
                    fmt=marker,
                    color=color,
                    capsize=3,
                    markerfacecolor=color if spec == "primary" else "none",
                    label=label.capitalize() if epoch == EPOCHS[0] else None,
                )
            p_value = fmt(estimate.get("p_wcb") if ok else None, 3).strip("$").replace("{,}", ",")
            axis.text(1.02, position, f"p = {p_value}", va="center", transform=axis.get_yaxis_transform())
    axis.set_yticks(list(reversed(range(len(labels)))), labels)
    axis.set_ylim(-0.6, len(labels) - 0.4)
    axis.axvline(0, color="black", linewidth=1)
    axis.set_xlabel(r"Hệ số β (RR$_B$ trên mỗi đơn vị SED$^+$)")
    axis.grid(axis="x", alpha=0.2)
    axis.legend(fontsize=8)
    figure.tight_layout()
    figures["figures/fig_h1_forest.png"] = figure

    by_transition = obj(obj(reports["N1H"]["panel"])["by_transition"])
    transitions = sorted(by_transition)
    x = np.arange(len(transitions))
    counts = [plot_number(by_transition[transition]) for transition in transitions]
    figure = Figure(figsize=(7.2, 4.2))
    axis = figure.add_subplot()
    axis.bar(x, counts, color=COLORS[0], width=0.65)
    for position, transition, count in zip(x, transitions, counts):
        if np.isfinite(count):
            axis.annotate(
                fmt(by_transition[transition], 0),
                (position, count),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
            )
    axis.set_xticks(x, [transition.replace("->", "→") for transition in transitions], rotation=25, ha="right")
    axis.set_xlabel("Chuyển tiếp")
    axis.set_ylabel("Số dòng (câu hỏi × chuyển tiếp)")
    axis.margins(y=0.15)
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figures["figures/fig_panel_transitions.png"] = figure
    figures["figures/fig_detect_by_degree.png"] = figure_detect_by_degree(reports)
    figures["figures/fig_evidence_chain.png"] = figure_evidence_chain(reports)
    for figure in figures.values():
        use_decimal_comma(figure)
    return figures


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing report assets")
    args = parser.parse_args(argv)
    output_root = ROOT / REPORT
    existing = [name for name in DEPENDENCIES if (output_root / name).exists() or (output_root / name).is_symlink()]
    if existing and not args.force:
        parser.error("Refusing to overwrite existing outputs without --force: " + ", ".join(existing))

    reports: dict[str, Record] = {}
    hashes: dict[str, str] = {}
    for key, relative in SOURCES.items():
        payload = (ROOT / relative).read_bytes()
        reports[key] = obj(json.loads(payload))
        hashes[key] = hashlib.sha256(payload).hexdigest()
    tables = make_tables(reports)
    figures = make_figures(reports)
    tables["generated/SOURCES.txt"] = (
        "\n".join(
            (REPORT / name).as_posix() + "\t" + "; ".join(f"{SOURCES[key]} sha256={hashes[key]}" for key in keys)
            for name, keys in DEPENDENCIES.items()
        )
        + "\n"
    )

    for name in DEPENDENCIES:
        path = output_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name in tables:
            with path.open("w" if args.force else "x", encoding="utf-8", newline="\n") as handle:
                handle.write(tables[name])
        else:
            with path.open("wb" if args.force else "xb") as handle:
                figures[name].savefig(handle, format="png", dpi=200)
        print((REPORT / name).as_posix())


if __name__ == "__main__":
    main()
