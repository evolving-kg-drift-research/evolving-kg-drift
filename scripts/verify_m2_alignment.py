"""Independent fractional anchor allocation and NumPy SVD verification of saved alignment."""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, safe_file, sha, validate_manifest, write_json,
)


def fractional_quotas(counts: dict[int, int], count: int) -> dict[int, int]:
    total = sum(counts.values())
    if total < count or total <= 0:
        raise ValueError("Invalid fixed-anchor population")
    exact = {d: Fraction(count * n, total) for d, n in counts.items()}
    result = {d: int(q) for d, q in exact.items()}
    missing = count - sum(result.values())
    for degree in sorted(exact, key=lambda d: (-(exact[d] - int(exact[d])), d))[:missing]:
        result[degree] += 1
    return result


def verify_anchor_plan(
    plan: dict[str, Any], persistent: list[str], degrees: dict[str, int], criteria: dict[str, Any],
    transition: str,
) -> None:
    counts: dict[int, int] = {}
    for e in persistent:
        counts[degrees[e]] = counts.get(degrees[e], 0) + 1
    selected = fractional_quotas(counts, criteria["fit_count"] + criteria["holdout_count"])
    fit_quotas = fractional_quotas(selected, criteria["fit_count"])
    salt = f"{criteria['salt']}:{transition}"
    fit, holdout, allocation = [], [], []
    for degree in sorted(counts):
        population = [e for e in persistent if degrees[e] == degree]
        ordered = sorted(population, key=lambda e: (sha(f"{salt}:degree:{degree}:{e}".encode()), e))
        sample = ordered[:selected[degree]]
        fit.extend(sample[:fit_quotas[degree]])
        holdout.extend(sample[fit_quotas[degree]:])
        allocation.append({"degree": degree, "available": counts[degree], "selected": selected[degree],
                           "fit": fit_quotas[degree], "holdout": selected[degree] - fit_quotas[degree]})
    def hash_ids(ids: list[str]) -> str:
        return sha(json.dumps(sorted(ids), sort_keys=True).encode())
    expected = {"version": "fixed_degree_joint_sample_then_split_v1", "salt": salt,
                "candidate_count": len(persistent), "candidate_hash": hash_ids(persistent),
                "pretransition_degrees_hash": sha(json.dumps(degrees, sort_keys=True).encode()),
                "allocations": allocation, "split": {"fit_anchors": sorted(fit), "holdout_anchors": sorted(holdout),
                                                     "fit_hash": hash_ids(fit), "holdout_hash": hash_ids(holdout)}}
    if plan != expected:
        raise ValueError("Independent pretransition anchor allocation/IDs/hash mismatch")
    if len(fit) != criteria["fit_count"] or len(holdout) != criteria["holdout_count"] or set(fit) & set(holdout):
        raise ValueError("Invalid fixed-count anchor split")


def close(actual: Any, expected: Any, label: str) -> None:
    if not np.allclose(actual, expected, atol=1e-10, rtol=1e-9):
        raise ValueError(f"Independent alignment mismatch: {label}")


def verify_record(
    record: dict[str, Any], source: dict[str, Any], target: dict[str, Any], plan: dict[str, Any],
    criteria: dict[str, Any], job: dict[str, Any],
) -> None:
    if any(record[k] != v for k, v in job.items()):
        raise ValueError("Alignment record/job identity mismatch")
    dimension = source["provenance"]["dimension"]
    if dimension != target["provenance"]["dimension"] or record["dimension"] != dimension:
        raise ValueError("Alignment dimension mismatch")
    for raw, sid, seed, field in ((source, job["source_snapshot"], job["source_seed"], "source_checkpoint_semantic_hash"),
                                  (target, job["target_snapshot"], job["target_seed"], "target_checkpoint_semantic_hash")):
        if (raw["provenance"]["snapshot_id"] != sid or raw["provenance"]["seed"] != seed
                or raw["artifact_hash"] != record[field]):
            raise ValueError("Alignment input checkpoint identity/semantic hash mismatch")
    split = plan["split"]
    fit, holdout = split["fit_anchors"], split["holdout_anchors"]
    if (len(fit) != criteria["fit_count"] or len(holdout) != criteria["holdout_count"]
            or len(set(fit)) != len(fit) or len(set(holdout)) != len(holdout) or set(fit) & set(holdout)):
        raise ValueError("Invalid alignment anchor split")
    x = np.asarray([source["entity_embeddings"][e] for e in fit], dtype=float)
    y = np.asarray([target["entity_embeddings"][e] for e in fit], dtype=float)
    mu_x, mu_y = x.mean(axis=0), y.mean(axis=0)
    u, singular, vt = np.linalg.svd((x - mu_x).T @ (y - mu_y))
    q = u @ vt
    rank = int(np.sum(singular > 1e-6 * max(1e-12, singular[0])))
    diag = record["diagnostics"]
    saved_q = np.asarray(record["Q"])
    if saved_q.shape != (dimension, dimension) or not np.isfinite(saved_q).all():
        raise ValueError("Invalid saved transformation")
    close(record["source_mean"], mu_x, "source fit-only mean")
    close(record["target_mean"], mu_y, "target fit-only mean")
    close(diag["singular_values"], singular, "singular values")
    if rank == dimension:
        close(saved_q, q, "full-rank Q")
    close(np.linalg.norm((x - mu_x) @ saved_q - (y - mu_y)),
          np.linalg.norm((x - mu_x) @ q - (y - mu_y)), "minimum fit objective")
    residuals = {}
    for name, ids in (("fit_residual", fit), ("holdout_residual", holdout)):
        xx = np.asarray([source["entity_embeddings"][e] for e in ids])
        yy = np.asarray([target["entity_embeddings"][e] for e in ids])
        residuals[name] = np.sqrt(np.mean(np.sum(((xx - mu_x) @ saved_q + mu_y - yy) ** 2, axis=1)))
        close(diag[name], residuals[name], name)
    close(diag["fit_holdout_gap"], abs(residuals["fit_residual"] - residuals["holdout_residual"]), "holdout gap")
    close(diag["orthogonality_error"], np.linalg.norm(saved_q.T @ saved_q - np.eye(dimension)), "orthogonality")
    if (diag["numerical_rank"] != rank or diag["dimension"] != dimension
            or diag["num_fit_anchors"] != len(fit) or diag["num_holdout_anchors"] != len(holdout)
            or diag["alignment_type"] != job["alignment_type"]
            or diag["anchor_fit_hash"] != split["fit_hash"] or diag["anchor_holdout_hash"] != split["holdout_hash"]):
        raise ValueError("Alignment diagnostic identity/rank/anchors mismatch")
    reason = ""
    if rank < criteria["minimum_numerical_rank"]:
        reason = f"RANK_DEFICIENT:{rank}<{criteria['minimum_numerical_rank']}"
    elif diag["orthogonality_error"] > criteria["max_orthogonality_error"]:
        reason = f"ORTHOGONALITY_VIOLATION:{diag['orthogonality_error']}>{criteria['max_orthogonality_error']}"
    elif diag["fit_holdout_gap"] > criteria["max_fit_holdout_gap"]:
        reason = f"EXCESSIVE_FIT_HOLDOUT_GAP:{diag['fit_holdout_gap']}>{criteria['max_fit_holdout_gap']}"
    elif diag["holdout_residual"] > criteria["max_holdout_residual"]:
        reason = f"EXCESSIVE_HOLDOUT_RESIDUAL:{diag['holdout_residual']}>{criteria['max_holdout_residual']}"
    if record["available"] != (not reason) or record["unavailable_reason"] != reason:
        raise ValueError("Registered alignment availability/reason mismatch")
    payload = {"alignment_type": diag["alignment_type"], "dimension": dimension,
               "num_fit_anchors": len(fit), "num_holdout_anchors": len(holdout),
               "singular_values": [round(s, 7) for s in diag["singular_values"]], "numerical_rank": rank,
               "fit_residual": round(diag["fit_residual"], 7), "holdout_residual": round(diag["holdout_residual"], 7),
               "orthogonality_error": round(diag["orthogonality_error"], 7),
               "anchor_fit_hash": split["fit_hash"], "anchor_holdout_hash": split["holdout_hash"]}
    if sha(json.dumps(payload, sort_keys=True).encode()) != diag["alignment_hash"]:
        raise ValueError("Alignment diagnostic hash mismatch")


def verify(run: Path) -> dict[str, Any]:
    run = run.resolve()
    if not run.is_relative_to((ROOT / "outputs/m2_alignment").resolve()):
        raise ValueError("Verifier requires a registered alignment output directory")
    manifest_path = safe_file(run, "experiment_manifest.json")
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    if manifest["stage"] != "alignment" or manifest["scientific_certification"] is not False or manifest["access"]["state"] != "dev":
        raise ValueError("Alignment manifest scope mismatch")
    for base, hashes in ((run, manifest["artifacts"]["hashes"]), (ROOT, manifest["inputs"]["hashes"]),
                         (run / "code", manifest["inputs"]["code_hashes"])):
        for relative, digest in hashes.items():
            if sha(safe_file(base, relative).read_bytes()) != digest:
                raise ValueError(f"Input/artifact/code hash mismatch: {relative}")
    resolved = json.loads((run / "resolved_config.json").read_bytes())
    stage, approved = resolved["stage"], resolved["approved"]
    if (manifest["inputs"]["config_hash"] != sha(encode(resolved))
            or manifest["inputs"]["data_hash"] != sha(encode(manifest["inputs"]["hashes"]))
            or stage["approved_config_sha256"] != sha(safe_file(ROOT, stage["approved_config_path"]).read_bytes())
            or stage["backbone_manifest_sha256"] != manifest["inputs"]["backbone_manifest_hash"]):
        raise ValueError("Resolved configuration or backbone lineage mismatch")
    if (approved != yaml.safe_load(safe_file(ROOT, stage["approved_config_path"]).read_bytes())
            or stage != yaml.safe_load(safe_file(ROOT, "configs/m2_alignment_v1.yaml").read_bytes())):
        raise ValueError("Serialized parameters differ from the hash-bound configuration files")
    backbone = ROOT / stage["backbone_run"]
    if sha(safe_file(backbone, "experiment_manifest.json").read_bytes()) != stage["backbone_manifest_sha256"]:
        raise ValueError("Backbone input manifest hash mismatch")
    backbone_summary = json.loads(safe_file(backbone, "summary.json").read_bytes())
    checkpoint_paths = {(r["snapshot_id"], r["seed"]): safe_file(backbone, r["path"]) for r in backbone_summary["results"]}
    raw_checkpoints = {k: json.loads(p.read_bytes()) for k, p in checkpoint_paths.items()}
    datasets, _ = inspect_package(ROOT / PACKAGE)
    if (manifest["inputs"]["snapshot_hash"] != sha(encode({sid: ds.snapshot_hash for sid, ds in datasets.items()}))
            or manifest["inputs"]["entity_map_hash"] != sha(encode({sid: ds.compute_mapping_hash() for sid, ds in datasets.items()}))
            or manifest["inputs"]["relation_map_hash"] != sha(encode({sid: ds.get_relation_mapping() for sid, ds in datasets.items()}))
            or manifest["inputs"]["query_hash"] is not None):
        raise ValueError("Aggregate snapshot/mapping lineage mismatch")
    plans = json.loads((run / "anchor_plans.json").read_bytes())
    jobs = json.loads((run / "registered_jobs.json").read_bytes())
    summary = json.loads((run / "summary.json").read_bytes())
    snapshots = approved["snapshots"]
    criteria = approved["alignment"]
    expected_jobs = []
    for prev, nxt in zip(snapshots, snapshots[1:]):
        transition = f"{prev}->{nxt}"
        persistent = sorted(set(datasets[prev].entities) & set(datasets[nxt].entities))
        degrees = {e: datasets[prev].entity_metadata[e].degree for e in persistent}
        verify_anchor_plan(plans[transition], persistent, degrees, criteria, transition)
        pairs = [(prev, nxt, s, s, "cross_time") for s in (13, 37, 101)]
        pairs.extend((sid, sid, a, b, "same_snapshot_cross_seed") for sid in (prev, nxt)
                     for a, b in itertools.combinations((13, 37, 101), 2))
        for source, target, a, b, kind in pairs:
            expected_jobs.append({"transition_id": transition, "source_snapshot": source, "target_snapshot": target,
                                  "source_seed": a, "target_seed": b, "alignment_type": kind,
                                  "comparison_id": f"{source}_seed{a}__{target}_seed{b}"})
    if jobs != expected_jobs or len(summary["results"]) != 81 or set(plans) != {j["transition_id"] for j in jobs}:
        raise ValueError("Registered comparisons or transition population mismatch")
    available = 0
    transition_counts: dict[str, int] = {}
    for job, entry in zip(jobs, summary["results"]):
        path = safe_file(run, entry["path"])
        second = safe_file(run, path.with_name(path.name.replace("repeat_1", "repeat_2")).relative_to(run))
        if path.read_bytes() != second.read_bytes() or sha(path.read_bytes()) != entry["alignment_sha256"] or entry["exact_replay"] is not True:
            raise ValueError("Alignment exact repeat/hash check failed")
        record = json.loads(path.read_bytes())
        transition = job["transition_id"]
        a, b = (job["source_snapshot"], job["source_seed"]), (job["target_snapshot"], job["target_seed"])
        verify_record(record, raw_checkpoints[a], raw_checkpoints[b], plans[transition], criteria, job)
        expected_checkpoints = {"source": sha(checkpoint_paths[a].read_bytes()), "target": sha(checkpoint_paths[b].read_bytes())}
        if (any(entry[k] != job[k] for k in job)
                or entry["available"] != record["available"] or entry["unavailable_reason"] != record["unavailable_reason"]
                or entry["diagnostics"] != record["diagnostics"] or record["config_hash"] != manifest["inputs"]["config_hash"]
                or record["anchor_plan_hash"] != sha(encode(plans[transition]))
                or record["source_checkpoint_sha256"] != expected_checkpoints["source"]
                or record["target_checkpoint_sha256"] != expected_checkpoints["target"]):
            raise ValueError("Alignment result lineage or summary mismatch")
        nested_path = path.with_name(path.name.replace("_repeat_1.json", "_manifest.json"))
        nested = json.loads(nested_path.read_bytes())
        validate_manifest(nested)
        source, target = raw_checkpoints[a]["provenance"], raw_checkpoints[b]["provenance"]
        if (nested["seed"] != job["source_seed"] or nested["target_seed"] != job["target_seed"]
                or nested["git"] != manifest["git"] or nested["stage"] != "alignment"
                or nested["scientific_certification"] is not False
                or nested["inputs"]["config_hash"] != record["config_hash"]
                or nested["inputs"]["hashes"] != manifest["inputs"]["hashes"]
                or nested["inputs"]["code_hashes"] != manifest["inputs"]["code_hashes"]
                or nested["inputs"]["checkpoint_hashes"] != expected_checkpoints
                or nested["inputs"]["anchor_plan_hash"] != record["anchor_plan_hash"]
                or nested["inputs"]["backbone_manifest_hash"] != stage["backbone_manifest_sha256"]
                or nested["inputs"]["snapshot_hash"] != sha(encode([source["snapshot_hash"], target["snapshot_hash"]]))
                or nested["inputs"]["entity_map_hash"] != sha(encode([source["entity_mapping_hash"], target["entity_mapping_hash"]]))
                or nested["inputs"]["relation_map_hash"] != sha(encode([source["relation_mapping_hash"], target["relation_mapping_hash"]]))
                or nested["artifacts"]["hashes"] != {p.relative_to(run).as_posix(): sha(p.read_bytes()) for p in (path, second)}):
            raise ValueError("Per-alignment manifest mismatch")
        available += record["available"]
        transition_counts[transition] = transition_counts.get(transition, 0) + record["available"]
    for transition, count in transition_counts.items():
        if (summary["transitions"][transition]["alignment_passed"] != count
                or summary["transitions"][transition]["available"] != (count == 9)):
            raise ValueError("Transition availability summary mismatch")
    if (summary["available_comparisons"] != available
            or summary["comparisons"] != 81 or summary["svd_executions"] != 162
            or summary["byte_identical_replays"] != 81
            or summary["scientific_certification"] is not False or summary["auto_execute_next_stage"] is not False
            or summary["status"] != ("ALIGNMENT_DEV_CHECKS_PASS" if available == 81 else "ALIGNMENT_UNAVAILABLE")):
        raise ValueError("Stage availability summary mismatch")
    return {"status": "ALIGNMENT_ARTIFACT_VERIFICATION_PASS", "scientific_certification": False,
            "manifest_sha256": sha(manifest_path.read_bytes()), "anchors_independently_reconstructed": 9,
            "svd_results_independently_recomputed": 81, "available_comparisons": available,
            "available_transitions": sum(c == 9 for c in transition_counts.values()), "byte_identical_replays": 81,
            "per_alignment_manifests_checked": 81, "input_hashes_checked": len(manifest["inputs"]["hashes"]),
            "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "verifier_sha256": sha(Path(__file__).read_bytes()), "verified_at_real": datetime.now(timezone.utc).isoformat(),
            "scope": "Fixed-anchor allocation/SVD/availability/lineage for Dev alignment; no null/drift/G3 certification"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.run)
    output = args.run / ("independent_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                         + "_" + uuid4().hex[:8] + ".json")
    write_json(output, result)
    print(json.dumps({"output": str(output), **result}, indent=2))
