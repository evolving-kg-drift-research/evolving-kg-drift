"""Verify saved pilot artifacts using independent ranking and NumPy SVD arithmetic."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from scripts.inspect_m2_inputs import (  # noqa: E402
    PACKAGE, encode, inspect_package, safe_file, sha, validate_manifest, write_json,
)
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.model import TransEConfig  # noqa: E402


def require_close(actual: Any, expected: Any, label: str) -> None:
    if not np.allclose(actual, expected, rtol=1e-9, atol=1e-10):
        raise ValueError(f"Independent arithmetic mismatch: {label}")


def verify_alignment(record: dict[str, Any], source: KGECheckpoint, target: KGECheckpoint,
                     split: dict[str, Any]) -> None:
    fit, holdout = split["fit_anchors"], split["holdout_anchors"]
    if not fit or not holdout or set(fit) & set(holdout):
        raise ValueError("Alignment split missing, empty, or overlapping")
    for name, entities in (("fit", fit), ("holdout", holdout)):
        digest = sha(json.dumps(sorted(entities), sort_keys=True).encode())
        if digest != split[f"{name}_hash"] or digest != record["diagnostics"][f"anchor_{name}_hash"]:
            raise ValueError("Alignment anchor hash mismatch")
    x = np.array([source.entity_embeddings[e] for e in fit])
    y = np.array([target.entity_embeddings[e] for e in fit])
    mu_x, mu_y = x.mean(axis=0), y.mean(axis=0)
    u, singular, vt = np.linalg.svd((x - mu_x).T @ (y - mu_y))
    q = u @ vt
    diag = record["diagnostics"]
    require_close(record["source_mean"], mu_x, "source mean")
    require_close(record["target_mean"], mu_y, "target mean")
    require_close(diag["singular_values"], singular, "singular values")
    rank = int(np.sum(singular > 1e-6 * max(1e-12, singular[0])))
    # Full-rank pilot results have a unique Q; deficient results compare the
    # objective because the production solver uses a canonical null-space basis.
    if rank == record["dimension"]:
        require_close(record["Q"], q, "full-rank Q")
    saved_q = np.asarray(record["Q"])
    expected = {}
    for name, entities in (("fit_residual", fit), ("holdout_residual", holdout)):
        xx = np.array([source.entity_embeddings[e] for e in entities])
        yy = np.array([target.entity_embeddings[e] for e in entities])
        expected[name] = float(np.sqrt(np.mean(np.sum(((xx - mu_x) @ saved_q + mu_y - yy) ** 2, axis=1))))
        require_close(diag[name], expected[name], name)
    require_close(diag["fit_holdout_gap"], abs(expected["fit_residual"] - expected["holdout_residual"]), "fit/holdout gap")
    require_close(diag["orthogonality_error"], np.linalg.norm(saved_q.T @ saved_q - np.eye(len(saved_q))), "orthogonality")
    if diag["numerical_rank"] != rank or record["full_rank"] != (rank == record["dimension"]):
        raise ValueError("Independent numerical rank mismatch")
    if diag["num_fit_anchors"] != len(fit) or diag["num_holdout_anchors"] != len(holdout):
        raise ValueError("Anchor count mismatch")
    valid = (rank >= max(1, record["dimension"] // 2)
             and diag["orthogonality_error"] <= 1e-4
             and diag["fit_holdout_gap"] <= 1.0 and diag["holdout_residual"] <= 2.0)
    if valid != record["operational_valid"]:
        raise ValueError("Operational alignment validity mismatch")


def verify_ranks(rows: list[dict[str, Any]], checkpoint: KGECheckpoint,
                 positives: set[tuple[str, str, str]]) -> float:
    if not rows:
        raise ValueError("Empty validation population")
    candidates = sorted(checkpoint.entity_embeddings)
    reciprocal_ranks = []
    for row in rows:
        h, r, t = row["triple"]
        side = row["side"]
        if side not in ("head", "tail"):
            raise ValueError("Invalid ranking side")
        target = h if side == "head" else t
        scores = {}
        for e in candidates:
            triple = (e, r, t) if side == "head" else (h, r, e)
            if e != target and triple in positives:
                continue
            hh, rr, tt = triple
            vector = [a + b - c for a, b, c in zip(checkpoint.entity_embeddings[hh],
                      checkpoint.relation_embeddings[rr], checkpoint.entity_embeddings[tt])]
            scores[e] = -math.sqrt(sum(v * v for v in vector))
        if set(scores) != set(dict(row["candidate_scores"])):
            raise ValueError("Candidate set mismatch")
        for entity, saved in row["candidate_scores"]:
            require_close(saved, scores[entity], "candidate score")
        target_score = scores[target]
        better = sum(v > target_score for v in scores.values())
        ties = sum(v == target_score for v in scores.values())
        rank = 1 + better + (ties - 1) / 2
        require_close(row["rank"], rank, "average-tie rank")
        require_close(row["reciprocal_rank"], 1 / rank, "reciprocal rank")
        if row["candidate_count"] != len(scores) or row["filtered_count"] != len(candidates) - len(scores):
            raise ValueError("Ranking count mismatch")
        reciprocal_ranks.append(1 / rank)
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def verify(run: Path) -> dict[str, Any]:
    run = run.resolve()
    if not run.is_relative_to((ROOT / "outputs/m2_pilot").resolve()):
        raise ValueError("Verification must target a registered pilot directory")
    manifest_path = run / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    validate_manifest(manifest)
    for relative, digest in manifest["artifacts"]["hashes"].items():
        if sha(safe_file(run, relative).read_bytes()) != digest:
            raise ValueError(f"Artifact hash mismatch: {relative}")
    for relative, digest in manifest["inputs"]["hashes"].items():
        if sha(safe_file(ROOT, relative).read_bytes()) != digest:
            raise ValueError(f"Input hash mismatch: {relative}")
    for relative, digest in manifest["inputs"]["code_hashes"].items():
        if sha(safe_file(run / "code", relative).read_bytes()) != digest:
            raise ValueError(f"Archived code mismatch: {relative}")
    summary = json.loads((run / "summary.json").read_bytes())
    anchors = json.loads((run / "anchors.json").read_bytes())
    split = json.loads((run / "split.json").read_bytes())
    design = json.loads((run / "design.json").read_bytes())
    if (sha(encode(design)) != manifest["inputs"]["config_hash"]
            or sha(encode(manifest["inputs"]["hashes"])) != manifest["inputs"]["data_hash"]):
        raise ValueError("Resolved design or data aggregate hash mismatch")
    datasets, _ = inspect_package(ROOT / PACKAGE)
    train = {tuple(t) for t in split["train"]}
    heldout = {tuple(t) for t in split["validation"]}
    positives = {t.to_tuple() for t in datasets["T01"].triples}
    if not heldout or train & heldout or train | heldout != positives:
        raise ValueError("Invalid validation partition")
    training = SnapshotDataset.create("T01_PILOT_TRAIN", sorted(train))
    if training.entities != datasets["T01"].entities or training.relations != datasets["T01"].relations:
        raise ValueError("OOV validation split")
    mappings = json.loads((run / "mappings.json").read_bytes())
    all_checkpoints = {}
    ranking_count = 0
    validation_mrrs: dict[int, list[float]] = {32: [], 64: []}
    if len(summary["checkpoints"]) != 18:
        raise ValueError("Pilot must contain exactly 18 checkpoint configurations")
    expected_keys = {(dim, sid, seed) for dim in (32, 64)
                     for sid in ("T01_PILOT_TRAIN", "T01", "T02") for seed in (13, 37, 101)}
    for record in summary["checkpoints"]:
        path = safe_file(run, record["path"])
        a = path.read_bytes()
        b = path.with_name(path.name.replace("repeat_1", "repeat_2")).read_bytes()
        if a != b or record["checkpoint_sha256"] != sha(a):
            raise ValueError("Checkpoint byte replay failed")
        checkpoint = KGECheckpoint.load(path)
        if checkpoint.compute_artifact_hash() != checkpoint.artifact_hash:
            raise ValueError("Checkpoint semantic hash mismatch")
        checkpoint.verify_finite()
        sid, seed, dimension = record["snapshot_id"], record["seed"], record["dimension"]
        dataset = training if sid == training.snapshot_id else datasets[sid]
        cfg = TransEConfig(dimension=dimension, norm=2, seed=seed, epochs=design["epochs"],
                           learning_rate=design["learning_rate"], margin=design["margin"])
        config_hash = sha(json.dumps(asdict(cfg), sort_keys=True).encode())
        if (checkpoint.provenance.seed != seed or checkpoint.provenance.dimension != dimension
                or checkpoint.provenance.snapshot_id != sid or checkpoint.provenance.snapshot_hash != dataset.snapshot_hash
                or checkpoint.provenance.config_hash != config_hash or record["config_hash"] != config_hash
                or checkpoint.provenance.entity_mapping_hash != dataset.compute_mapping_hash()
                or mappings[sid]["entities"] != dataset.get_entity_mapping()
                or mappings[sid]["relations"] != dataset.get_relation_mapping()
                or set(checkpoint.entity_embeddings) != set(dataset.entities)
                or set(checkpoint.relation_embeddings) != set(dataset.relations)
                or checkpoint.provenance.git_commit != manifest["git"]["commit"]
                or checkpoint.provenance.git_dirty != manifest["git"]["dirty_state"]
                or checkpoint.provenance.relation_mapping_hash != sha(json.dumps(dataset.get_relation_mapping(), sort_keys=True).encode())
                or record["exact_replay"] is not True):
            raise ValueError("Checkpoint input/config/mapping provenance mismatch")
        all_checkpoints[dimension, sid, seed] = checkpoint
        losses = checkpoint.training_metrics["epoch_losses"]
        if len(losses) != design["epochs"] or not all(math.isfinite(v) for v in losses):
            raise ValueError("Invalid loss sequence")
        if sid == training.snapshot_id:
            ranking_rows = json.loads(path.with_name(f"seed_{seed}_validation_ranks.json").read_bytes())
            if (len(ranking_rows) != 2 * len(heldout)
                    or {(tuple(r["triple"]), r["side"]) for r in ranking_rows} != {(t, side) for t in heldout for side in ("head", "tail")}):
                raise ValueError("Validation ranking population mismatch")
            mrr = verify_ranks(ranking_rows, checkpoint, positives)
            require_close(summary["dimensions"][str(dimension)]["validation"][str(seed)]["MRR"], mrr, "seed MRR")
            validation_mrrs[dimension].append(mrr)
            ranking_count += len(ranking_rows)
    if set(all_checkpoints) != expected_keys:
        raise ValueError("Missing or duplicate seed/snapshot/dimension configuration")
    alignment_records = json.loads((run / "alignments.json").read_bytes())
    if len(alignment_records) != 18:
        raise ValueError("Pilot must contain 18 alignment records")
    expected_alignments = {
        (d, sid, sid, a, b) for d in (32, 64) for sid in ("T01", "T02")
        for a, b in itertools.combinations((13, 37, 101), 2)
    } | {(d, "T01", "T02", s, s) for d in (32, 64) for s in (13, 37, 101)}
    if {(r["dimension"], r["source_snapshot"], r["target_snapshot"], r["source_seed"], r["target_seed"])
            for r in alignment_records} != expected_alignments:
        raise ValueError("Missing or duplicate alignment comparison")
    feasibility: dict[int, list[bool]] = {32: [], 64: []}
    for record in alignment_records:
        d = record["dimension"]
        source = all_checkpoints[d, record["source_snapshot"], record["source_seed"]]
        target = all_checkpoints[d, record["target_snapshot"], record["target_seed"]]
        verify_alignment(record, source, target, anchors[record["split_key"]])
        feasibility[d].append(record["operational_valid"] and record["full_rank"])
    mean_mrrs = {d: sum(values) / len(values) for d, values in validation_mrrs.items()}
    for d in (32, 64):
        require_close(summary["dimensions"][str(d)]["mean_validation_MRR"], mean_mrrs[d], "mean MRR")
        if (len(feasibility[d]) != 9 or summary["dimensions"][str(d)]["alignment_passed"] != sum(feasibility[d])
                or summary["dimensions"][str(d)]["alignment_feasible"] != all(feasibility[d])):
            raise ValueError("Alignment feasibility summary mismatch")
    eligible = [d for d in (32, 64) if all(feasibility[d])]
    selected = min(eligible, key=lambda d: (-mean_mrrs[d], d)) if eligible else None
    if selected != summary["recommended_dimension"] or manifest["scientific_certification"] is not False:
        raise ValueError("Selection or certification scope mismatch")
    return {"status": "PILOT_ARTIFACT_VERIFICATION_PASS", "scientific_certification": False,
            "manifest_sha256": sha(manifest_path.read_bytes()), "checkpoint_configurations": 18,
            "byte_identical_replays": 18, "independently_recomputed_rankings": ranking_count,
            "independently_recomputed_alignments": 18, "recommended_dimension": selected,
            "input_hashes_checked": len(manifest["inputs"]["hashes"]),
            "artifact_hashes_checked": len(manifest["artifacts"]["hashes"]),
            "verified_at_real": datetime.now(timezone.utc).isoformat(),
            "verifier_sha256": sha(Path(__file__).read_bytes()),
            "scope": "Saved pilot arithmetic/bytes/lineage only; temporal identity and G3 not certified"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.run)
    output = args.run / ("independent_verification_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                         + "_" + uuid4().hex[:8] + ".json")
    write_json(output, result)
    print(json.dumps(result, indent=2))
