"""Execute alignment geometry pilot collection across all 81 registered comparisons."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from kge.checkpoint import KGECheckpoint  # noqa: E402
from drift.measurement_v2 import collect_alignment_geometry_v2  # noqa: E402

BACKBONE_DIR = ROOT / "outputs/m2_backbone/20261014T034042Z_65c464ba"
ALIGNMENT_DIR = ROOT / "outputs/m2_alignment/20261014T040001Z_96d9ccbc"
OUT_DIR = ROOT / "outputs/m2_alignment_pilot_run"


def run_pilot_collection() -> dict[str, Any]:
    with (ALIGNMENT_DIR / "registered_jobs.json").open("r", encoding="utf-8") as f:
        jobs = json.load(f)
    with (ALIGNMENT_DIR / "anchor_plans.json").open("r", encoding="utf-8") as f:
        anchor_plans = json.load(f)

    # Cache checkpoints in memory
    checkpoints: dict[tuple[str, int], KGECheckpoint] = {}
    snapshots = [f"T{i:02d}" for i in range(1, 11)]
    seeds = [13, 37, 101]

    print(f"[INFO] Loading 30 checkpoints from {BACKBONE_DIR}...")
    for sid in snapshots:
        for seed in seeds:
            ckpt_path = BACKBONE_DIR / f"checkpoints/{sid}/seed_{seed}_repeat_1.json"
            checkpoints[sid, seed] = KGECheckpoint.load(ckpt_path)

    print(f"[INFO] Running collect_alignment_geometry_v2 across {len(jobs)} jobs...")
    results = []
    fit_residuals = []
    holdout_residuals = []
    signed_gaps = []
    abs_gaps = []
    orth_errors = []
    rank_fractions = []

    for job in jobs:
        src_snap = job["source_snapshot"]
        tgt_snap = job["target_snapshot"]
        src_seed = job["source_seed"]
        tgt_seed = job["target_seed"]
        trans = job["transition_id"]
        cid = job["comparison_id"]

        align_path = ALIGNMENT_DIR / f"alignments/{trans.replace('->', '__')}/{cid}_repeat_1.json"
        with align_path.open("r", encoding="utf-8") as f:
            record = json.load(f)

        plan = anchor_plans[trans]
        source_ckpt = checkpoints[src_snap, src_seed]
        target_ckpt = checkpoints[tgt_snap, tgt_seed]

        stats = collect_alignment_geometry_v2(
            source=source_ckpt,
            target=target_ckpt,
            record=record,
            anchor_plan=plan,
            rank_relative_tolerance=1e-6,
        )

        results.append({
            "job": job,
            "stats": stats,
        })

        if stats["relative_fit_residual"] is not None:
            fit_residuals.append(stats["relative_fit_residual"])
        if stats["relative_holdout_residual"] is not None:
            holdout_residuals.append(stats["relative_holdout_residual"])
        if stats["signed_holdout_minus_fit"] is not None:
            signed_gaps.append(stats["signed_holdout_minus_fit"])
            abs_gaps.append(stats["absolute_holdout_minus_fit"])
        if stats["normalized_orthogonality_error"] is not None:
            orth_errors.append(stats["normalized_orthogonality_error"])
        if stats["rank_fraction"] is not None:
            rank_fractions.append(stats["rank_fraction"])

    def summarize(vals: list[float]) -> dict[str, float]:
        if not vals:
            return {}
        s = sorted(vals)
        n = len(s)
        return {
            "count": len(vals),
            "min": round(s[0], 6),
            "q25": round(s[int(n * 0.25)], 6),
            "median": round(statistics.median(s), 6),
            "q75": round(s[int(n * 0.75)], 6),
            "max": round(s[-1], 6),
            "mean": round(statistics.mean(s), 6),
            "stdev": round(statistics.stdev(s) if len(s) > 1 else 0.0, 6),
        }

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(jobs),
        "successful_collections": len(results),
        "metrics_summary": {
            "relative_fit_residual": summarize(fit_residuals),
            "relative_holdout_residual": summarize(holdout_residuals),
            "signed_holdout_minus_fit_gap": summarize(signed_gaps),
            "absolute_holdout_minus_fit_gap": summarize(abs_gaps),
            "normalized_orthogonality_error": summarize(orth_errors),
            "rank_fraction": summarize(rank_fractions),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / "m2_alignment_pilot_statistics_v2.json"
    with out_file.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2)

    print(f"[SUCCESS] Pilot statistics saved to {out_file}")
    return summary


if __name__ == "__main__":
    summary = run_pilot_collection()
    print("\n=== PILOT SUMMARY ===")
    print(json.dumps(summary["metrics_summary"], indent=2))
