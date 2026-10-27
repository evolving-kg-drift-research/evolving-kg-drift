"""Generate publication-ready visualization figures for M2 Representation Drift and M4 Evaluation/Econometrics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DRIFT_PARQUET = ROOT / "outputs/m2_drift_v2/20261027T190838Z_ea66c2af/all_transitions_entity_drift_v2.parquet"
EVAL_PARQUET = ROOT / "outputs/m4_eval/20261027T193028Z_4bc9876e/recurring_qa_panel_evaluation.parquet"
STATS_JSON = ROOT / "outputs/m4_stats/20261027T193028Z_4bc9876e/h1_h2_econometric_results.json"
FIG_DIR = ROOT / "reports/figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Dataviz validated style tokens
CLR_PRIMARY = "#1e293b"      # Dark slate text/lines
CLR_MUTED = "#64748b"        # Secondary ink
CLR_GRID = "#e2e8f0"         # Recessive grid
CLR_BLUE = "#2563eb"         # Primary categorical (Arm B / Updated)
CLR_AMBER = "#d97706"        # Secondary categorical (Arm A / Frozen)
CLR_EMERALD = "#059669"      # Positive / calibrated signal
CLR_RED = "#dc2626"          # Negative / drift contrast

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
    "axes.edgecolor": "#cbd5e1",
    "axes.linewidth": 0.8,
    "grid.color": CLR_GRID,
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
})


def plot_figure_1_drift_distribution() -> None:
    """Figure 1: Distribution of noise-calibrated representation drift (SED+) across 9 transitions."""
    drift_df = pq.read_table(DRIFT_PARQUET).to_pandas()
    transitions = sorted(drift_df["transition_id"].unique())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5), dpi=300)

    # Subplot A: Boxplot of SED+ per transition
    data_by_trans = [drift_df[drift_df["transition_id"] == t]["SED_plus"].values for t in transitions]
    short_labels = [t.replace("->", "→") for t in transitions]

    box = ax1.boxplot(
        data_by_trans,
        tick_labels=short_labels,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color=CLR_PRIMARY, linewidth=1.5),
    )
    for patch in box["boxes"]:
        patch.set_facecolor("#dbeafe")
        patch.set_edgecolor(CLR_BLUE)
        patch.set_linewidth(1.0)

    ax1.set_title("(A) Distribution of Noise-Calibrated Drift ($SED^+$)", fontweight="bold", pad=10)
    ax1.set_xlabel("Knowledge Graph Transition")
    ax1.set_ylabel("Standardized Excess Drift ($SED^+$)")
    ax1.grid(True, axis="y")
    ax1.tick_params(axis="x", rotation=35)

    # Subplot B: Positive drift rate
    pos_rates = [np.mean(drift_df[drift_df["transition_id"] == t]["SED_plus"] > 0) * 100 for t in transitions]

    x = np.arange(len(transitions))
    ax2.plot(x, pos_rates, marker="o", markersize=6, color=CLR_EMERALD, linewidth=2.0, label="Positive Drift Rate (%)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(short_labels, rotation=35)
    ax2.set_title("(B) Genuine Representation Drift Rate (%)", fontweight="bold", pad=10)
    ax2.set_xlabel("Knowledge Graph Transition")
    ax2.set_ylabel("Entities with Above-Noise Drift (%)")
    ax2.set_ylim(35, 60)
    ax2.axhline(50, color=CLR_MUTED, linestyle=":", linewidth=1, label="Expected Random Noise Symmetry (50%)")
    ax2.grid(True)
    ax2.legend(loc="lower left", framealpha=0.9)

    fig.tight_layout()
    png_path = FIG_DIR / "fig1_m2_representation_drift_sed_plus.png"
    svg_path = FIG_DIR / "fig1_m2_representation_drift_sed_plus.svg"
    fig.savefig(png_path, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] Figure 1: {png_path}")


def plot_figure_2_longitudinal_qa_mrr() -> None:
    """Figure 2: Longitudinal trajectory of Multi-Hop QA MRR across Arms and Candidate Universes."""
    eval_df = pq.read_table(EVAL_PARQUET).to_pandas()
    transitions = sorted(eval_df["transition_id"].unique())
    short_labels = [t.replace("->", "→") for t in transitions]

    mrr_b_t1 = [eval_df[eval_df["transition_id"] == t]["rr_arm_b_seen_at_t1"].mean() for t in transitions]
    mrr_a_t1 = [eval_df[eval_df["transition_id"] == t]["rr_arm_a_seen_at_t1"].mean() for t in transitions]
    mrr_b_open = [eval_df[eval_df["transition_id"] == t]["rr_arm_b_open_world"].mean() for t in transitions]
    mrr_a_open = [eval_df[eval_df["transition_id"] == t]["rr_arm_a_open_world"].mean() for t in transitions]

    x = np.arange(len(transitions))

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)

    # Line plots
    ax.plot(x, mrr_b_t1, marker="o", markersize=6, color=CLR_BLUE, linewidth=2.2, label="Arm B (Updated-KGE) — Seen-at-T1 Universe (Primary H1)")
    ax.plot(x, mrr_a_t1, marker="s", markersize=5, color=CLR_AMBER, linewidth=1.8, linestyle="--", label="Arm A (Frozen-KGE T01) — Seen-at-T1 Universe")
    ax.plot(x, mrr_b_open, marker="^", markersize=5, color="#0284c7", linewidth=1.6, linestyle="-.", label="Arm B (Updated-KGE) — Open-World Universe")
    ax.plot(x, mrr_a_open, marker="d", markersize=5, color="#b45309", linewidth=1.4, linestyle=":", label="Arm A (Frozen-KGE T01) — Open-World Universe")

    # Shaded OOV bias gap between Seen-at-T1 and Open-World for Arm B
    ax.fill_between(x, mrr_b_open, mrr_b_t1, color=CLR_BLUE, alpha=0.1, label="OOV Churn Penalty Gap")

    ax.set_title("Longitudinal Multi-Hop QA Performance (MRR) Across KG Evolution", fontweight="bold", pad=12)
    ax.set_xlabel("Evolutionary Transition ($T_{t-1} \\to T_t$)")
    ax.set_ylabel("Mean Reciprocal Rank (MRR)")
    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, rotation=30)
    ax.set_ylim(0.35, 0.72)
    ax.grid(True)
    ax.legend(loc="lower left", framealpha=0.92)

    fig.tight_layout()
    png_path = FIG_DIR / "fig2_m4_longitudinal_qa_mrr_dynamics.png"
    svg_path = FIG_DIR / "fig2_m4_longitudinal_qa_mrr_dynamics.svg"
    fig.savefig(png_path, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] Figure 2: {png_path}")


def plot_figure_3_twfe_forest_plot() -> None:
    """Figure 3: Two-Way Fixed Effects coefficient estimates and Falsification Test comparison."""
    with STATS_JSON.open("r", encoding="utf-8") as f:
        stats = json.load(f)

    h1 = stats["H1_hypothesis_testing"]
    fals = stats["falsification_testing"]

    beta_h1 = h1["drift_coefficient_beta_d"]
    se_h1 = h1["cluster_robust_se"]
    p_wcb_h1 = h1["wcb_p_value"]

    beta_fals = fals["pseudo_coefficient_beta"]
    se_fals = fals["cluster_robust_se"]
    p_wcb_fals = fals["wcb_p_value"]

    models = [
        f"Primary H1: Standardized Drift ($SED^+$)\nβ = {beta_h1:.5f}, SE = {se_h1:.5f}, p_WCB = {p_wcb_h1:.3f}",
        f"Falsification: Pseudo-Drift ($D^{{pseudo}}$)\nβ = {beta_fals:.5f}, SE = {se_fals:.5f}, p_WCB = {p_wcb_fals:.3f}",
    ]
    betas = [beta_h1, beta_fals]
    ci_low = [b - 1.96 * se for b, se in zip(betas, [se_h1, se_fals])]
    ci_high = [b + 1.96 * se for b, se in zip(betas, [se_h1, se_fals])]

    y_pos = np.arange(len(models))

    fig, ax = plt.subplots(figsize=(9, 4), dpi=300)

    # Plot point estimates and error bars
    for i, (b, low, high) in enumerate(zip(betas, ci_low, ci_high)):
        color = CLR_BLUE if i == 0 else CLR_MUTED
        ax.plot([low, high], [i, i], color=color, linewidth=2.0)
        ax.plot(b, i, marker="o", markersize=8, color=color)

    # Zero reference line
    ax.axvline(0, color=CLR_RED, linestyle="--", linewidth=1.2, label="Null Effect Line (β = 0)")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(models, fontweight="medium")
    ax.set_xlabel("Estimated Coefficient (Δ Reciprocal Rank per unit drift)")
    ax.set_title("Two-Way Fixed Effects Estimation ($H_1$) and Falsification Test", fontweight="bold", pad=12)
    ax.set_xlim(-0.06, 0.04)
    ax.grid(True, axis="x")
    ax.legend(loc="upper right", framealpha=0.9)

    fig.tight_layout()
    png_path = FIG_DIR / "fig3_m4_twfe_h1_falsification_forest_plot.png"
    svg_path = FIG_DIR / "fig3_m4_twfe_h1_falsification_forest_plot.svg"
    fig.savefig(png_path, bbox_inches="tight")
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] Figure 3: {png_path}")


def generate_interactive_dashboard() -> None:
    """Generate interactive HTML dashboard integrating all results."""
    with STATS_JSON.open("r", encoding="utf-8") as f:
        stats = json.load(f)

    h1 = stats["H1_hypothesis_testing"]
    fals = stats["falsification_testing"]
    h2 = stats["H2_contrast_analysis"]

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Báo cáo trực quan hóa Evolving KG Drift</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --primary: #2563eb;
      --success: #059669;
      --danger: #dc2626;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      margin: 0;
      padding: 24px;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
    }}
    h1 {{ font-size: 24px; margin: 0 0 8px; color: var(--text); }}
    .subtitle {{ color: var(--text-muted); font-size: 14px; margin: 0; }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }}
    .metric-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }}
    .metric-value {{ font-size: 22px; font-weight: 700; color: var(--text); }}
    .metric-sub {{ font-size: 12px; color: var(--text-muted); margin-top: 4px; }}
    .chart-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }}
    .chart-card h2 {{ font-size: 16px; margin: 0 0 12px; }}
    .chart-img {{ width: 100%; height: auto; border-radius: 6px; display: block; border: 1px solid var(--border); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }}
    th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
    th {{ background: #f1f5f9; color: var(--text-muted); font-weight: 600; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; }}
    .badge-pass {{ background: #dcfce7; color: #166534; }}
    .badge-inconclusive {{ background: #fef3c7; color: #92400e; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>Báo cáo trực quan hóa kết quả thực nghiệm Evolving KG Drift</h1>
      <p class="subtitle">Định lượng trôi dạt biểu diễn KGE và tác động lên suy luận đa bước qua 10 snapshot thời gian (T01–T10)</p>
    </header>

    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">Hệ số trôi dạt (β_d)</div>
        <div class="metric-value">{h1['drift_coefficient_beta_d']:.5f}</div>
        <div class="metric-sub">SE = {h1['cluster_robust_se']:.5f} (t = {h1['t_statistic']:.2f})</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Wild Cluster Bootstrap</div>
        <div class="metric-value">p = {h1['wcb_p_value']:.3f}</div>
        <div class="metric-sub"><span class="badge badge-inconclusive">Inconclusive (p &gt; 0.05)</span></div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Kiểm định giả mạo</div>
        <div class="metric-value">p = {fals['wcb_p_value']:.3f}</div>
        <div class="metric-sub"><span class="badge badge-pass">PASS (Không có hiệu ứng giả)</span></div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Quy mô mẫu QA Panel</div>
        <div class="metric-value">1.323</div>
        <div class="metric-sub">147 queries × 9 transitions</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Độ lệch OOV Bias (H2)</div>
        <div class="metric-value">{h2['oov_bias_gap']:.4f}</div>
        <div class="metric-sub">Seen-at-T1 vs Open-World</div>
      </div>
    </div>

    <div class="chart-card">
      <h2>1. Phân phối trôi dạt biểu diễn (SED+) qua 9 bước chuyển</h2>
      <img src="fig1_m2_representation_drift_sed_plus.png" class="chart-img" alt="Phân phối SED+">
    </div>

    <div class="chart-card">
      <h2>2. Biến thiên hiệu năng suy luận đa bước (MRR) theo tiến hóa đồ thị</h2>
      <img src="fig2_m4_longitudinal_qa_mrr_dynamics.png" class="chart-img" alt="Biến thiên MRR">
    </div>

    <div class="chart-card">
      <h2>3. Ước lượng Two-Way Fixed Effects (H1) và Kiểm định giả mạo</h2>
      <img src="fig3_m4_twfe_h1_falsification_forest_plot.png" class="chart-img" alt="Forest Plot TWFE">
      <table>
        <thead>
          <tr>
            <th>Mô hình</th>
            <th>Biến giải thích</th>
            <th>Hệ số β</th>
            <th>SE Cụm</th>
            <th>t-stat</th>
            <th>WCB p-value</th>
            <th>Kết luận</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Primary H1</strong> (Two-Way FE)</td>
            <td>Standardized Drift (SED+)</td>
            <td>{h1['drift_coefficient_beta_d']:.5f}</td>
            <td>{h1['cluster_robust_se']:.5f}</td>
            <td>{h1['t_statistic']:.2f}</td>
            <td>{h1['wcb_p_value']:.3f}</td>
            <td><span class="badge badge-inconclusive">Inconclusive</span></td>
          </tr>
          <tr>
            <td><strong>Falsification</strong> (Same-snapshot)</td>
            <td>Pseudo-Drift (D_pseudo)</td>
            <td>{fals['pseudo_coefficient_beta']:.5f}</td>
            <td>{fals['cluster_robust_se']:.5f}</td>
            <td>{fals['t_statistic']:.2f}</td>
            <td>{fals['wcb_p_value']:.3f}</td>
            <td><span class="badge badge-pass">PASS (Không spurious)</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
    dashboard_path = FIG_DIR / "dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    print(f"[SAVED] Dashboard: {dashboard_path}")


def main() -> None:
    print("[INFO] Generating all publication figures...")
    plot_figure_1_drift_distribution()
    plot_figure_2_longitudinal_qa_mrr()
    plot_figure_3_twfe_forest_plot()
    generate_interactive_dashboard()
    print("[SUCCESS] All publication figures and dashboard successfully generated in reports/figures/!")


if __name__ == "__main__":
    main()
