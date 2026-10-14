"""Independently match exported report logs and descriptive summaries to saved sources."""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.inspect_m2_inputs import encode, safe_file, sha, validate_manifest, write_json  # noqa: E402


def verify(run: Path) -> dict:
    run = run.resolve()
    manifest_path = safe_file(run, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    for base, hashes in ((ROOT, manifest["inputs"]["hashes"]), (run, manifest["artifacts"]["hashes"])):
        for relative, digest in hashes.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Report source/output hash mismatch: {relative}")
    config = json.loads(safe_file(run, "resolved_config.json").read_bytes())
    if (manifest["stage"] != "descriptive_report" or manifest["scientific_certification"] is not False
            or manifest["access"]["state"] != "dev" or manifest["inputs"]["query_hash"] is not None
            or config["measurement_parameters_changed"] is not False or config["training_reexecuted"] is not False
            or config["auto_execute_M3_M4"] is not False or sha(encode(config)) != manifest["inputs"]["config_hash"]
            or sha(encode(manifest["inputs"]["hashes"])) != manifest["inputs"]["data_hash"]):
        raise ValueError("Report scope/config mismatch")
    runs = config["source_runs"]
    for name, relative in runs.items():
        path = safe_file(ROOT / relative, "experiment_manifest.json")
        if sha(path.read_bytes()) != manifest["inputs"]["source_manifest_hashes"][name]:
            raise ValueError("Parent report lineage mismatch")
    training = [json.loads(line) for line in (run / "training_epoch_log.jsonl").read_text(encoding="utf-8").splitlines()]
    index = {(r["snapshot_id"], r["seed"], r["epoch"]): r for r in training}
    if len(index) != 1500 or len(training) != 1500:
        raise ValueError("Missing/duplicate report epoch log")
    backbone = ROOT / runs["backbone"]
    summary = json.loads(safe_file(backbone, "summary.json").read_bytes())
    final, reductions = [], []
    models = []
    for result in summary["results"]:
        source = safe_file(backbone, result["path"])
        checkpoint = json.loads(source.read_bytes())
        metrics = checkpoint["training_metrics"]
        if metrics["num_epochs"] != 50 or len(metrics["epoch_losses"]) != 50:
            raise ValueError("Incomplete backbone source log")
        for epoch, loss in enumerate(metrics["epoch_losses"], 1):
            row = index[result["snapshot_id"], result["seed"], epoch]
            if row != {"snapshot_id": result["snapshot_id"], "seed": result["seed"], "epoch": epoch,
                       "training_loss": loss, "checkpoint_sha256": sha(source.read_bytes()),
                       "source_path": source.relative_to(ROOT).as_posix()}:
                raise ValueError("Exported training log differs from saved checkpoint")
        final.append(metrics["epoch_losses"][-1])
        reductions.append(100 * (metrics["epoch_losses"][0] - metrics["epoch_losses"][-1]) / metrics["epoch_losses"][0])
        models.append({"snapshot_id": result["snapshot_id"], "seed": result["seed"], "epoch_losses": metrics["epoch_losses"],
                       "checkpoint_sha256": sha(source.read_bytes()), "first_loss": metrics["epoch_losses"][0], "final_loss": metrics["epoch_losses"][-1]})
    drift_run = ROOT / runs["drift"]
    saved = pq.read_table(drift_run / "entity_drift.parquet").to_pylist()
    temporal = pq.read_table(drift_run / "temporal_displacements.parquet").to_pylist()
    temporal_index = {(r["transition_id"], r["entity_id"], r["seed"]): r["temporal_displacement"] for r in temporal}
    exported = [json.loads(line) for line in (run / "entity_drift_log.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(exported) != 6897 or len(saved) != 6897 or len(temporal_index) != 20691:
        raise ValueError("Report drift population mismatch")
    for original, row in zip(saved, exported):
        values = [temporal_index[original["transition_id"], original["entity_id"], seed] for seed in (13, 37, 101)]
        expected = {**original, **{f"delta_seed_{s}": v for s, v in zip((13, 37, 101), values)}, "seed_range": max(values) - min(values)}
        if row != expected:
            raise ValueError("Report drift log differs from immutable metrics")
    analysis = json.loads(safe_file(run, "analysis_summary.json").read_bytes())
    for record in analysis["transition_stats"]:
        rows = [r for r in exported if r["transition_id"] == record["transition_id"]]
        if (record["entities"] != len(rows) or record["available"] != sum(r["available"] for r in rows)
                or record["positive_excess"] != sum(r["signed_excess"] > 0 for r in rows)
                or record["min_reference_entities"] != min(r["reference_entity_count"] for r in rows)):
            raise ValueError("Report descriptive transition counts mismatch")
        for field in ("delta_time", "null_median", "signed_excess", "SED_plus", "seed_range"):
            array = np.asarray([r[field] for r in rows])
            expected = {"q25": float(np.quantile(array, .25)), "median": float(np.median(array)), "q75": float(np.quantile(array, .75)),
                        "p95": float(np.quantile(array, .95)), "max": float(np.max(array))}
            if record[field] != expected:
                raise ValueError("Report quantiles mismatch")
    for record in analysis["degree_support"]:
        rows = [r for r in exported if r["transition_id"] == record["transition_id"] and r["bucket_id"] == record["bucket_id"]]
        if (record["entities"] != len(rows) or record["reference_entities"] != min(r["reference_entity_count"] for r in rows)
                or record["SED_plus_median"] != float(np.median([r["SED_plus"] for r in rows]))):
            raise ValueError("Report bucket support mismatch")
    if (analysis["training_epochs"] != 1500 or analysis["entity_drift_rows"] != 6897
            or analysis["final_loss_range"] != [min(final), max(final)]
            or analysis["loss_reduction_percent_range"] != [min(reductions), max(reductions)]
            or analysis["total_positive_excess"] != 3640 or analysis["total_negative_excess"] != 3257
            or analysis["SED_plus_max"] != max(r["SED_plus"] for r in exported)):
        raise ValueError("Report aggregate diagnostics mismatch")
    document = safe_file(run, "report.html").read_text(encoding="utf-8")
    match = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', document, re.DOTALL)
    if not match:
        raise ValueError("Missing self-contained report data")
    embedded = json.loads(match.group(1))
    if embedded["entities"] != exported or embedded["models"] != models:
        raise ValueError("HTML interactive data differs from source logs")
    if "__REPORT_CONTENT__" in document or "__REPORT_DATA__" in document or re.search(r'<(?:script|img)[^>]*src="https?://', document):
        raise ValueError("Report has unresolved placeholders or external asset dependencies")
    for figure in analysis["figures"]:
        payload = safe_file(run, figure["png"]).read_bytes()
        if payload[:8] != b"\x89PNG\r\n\x1a\n" or min(struct.unpack(">II", payload[16:24])) < 500:
            raise ValueError("Invalid figure raster export")
        if "<svg" not in safe_file(run, figure["svg"]).read_text(encoding="utf-8"):
            raise ValueError("Missing figure SVG export")
    if len(analysis["figures"]) != 10:
        raise ValueError("Incomplete report figures")
    return {"status": "REPORT_SOURCE_DATA_VERIFICATION_PASS", "scientific_certification": False,
            "manifest_sha256": sha(manifest_path.read_bytes()), "training_rows_verified": len(training), "drift_rows_verified": len(exported),
            "self_contained_HTML_data_verified": True, "figures_checked": 10,
            "source_hashes_checked": len(manifest["inputs"]["hashes"]), "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "verifier_sha256": sha(Path(__file__).read_bytes()), "verified_at_real": datetime.now(timezone.utc).isoformat(),
            "scope": "Read-only report log/quantile/bucket/HTML/source lineage verification; no new scientific gate or training"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    path = args.run / ("report_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8] + ".json")
    write_json(path, result)
    print(json.dumps({"output": str(path), **result}, indent=2))
