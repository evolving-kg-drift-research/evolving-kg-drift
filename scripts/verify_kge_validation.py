"""Independently recompute fixed-pair loss and ranks from saved epoch vectors."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kg_pipeline.experiment_manifest import verify_artifacts  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.splits import ValidationSplit  # noqa: E402


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(run: Path) -> dict:
    run = run.resolve()
    manifest = verify_artifacts(run)
    if manifest.get("stage") != "quality_validation_dev" or manifest.get("scientific_certification") is not False:
        raise ValueError("Wrong validation stage/scope")

    def require_bound(*paths: str) -> None:
        if any(path not in manifest["artifacts"]["hashes"] for path in paths):
            raise ValueError("Consumed validation artifact is not bound in manifest")

    def check_number(actual: object, expected: float, label: str) -> None:
        if (type(actual) not in (int, float) or not math.isfinite(actual)
                or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)):
            raise ValueError(f"Independent {label} mismatch")

    require_bound("design.json", "epoch_log.json")
    design = json.loads((run / "design.json").read_bytes())
    if (design.get("version") != "kge_validation_dev_v2" or design.get("role") != "quality_validation"
            or design.get("selection") != "fixed_budget_no_test_access"
            or design.get("checkpoint_schedule") != "every_epoch"):
        raise ValueError("Unsupported validation design contract")
    design_hash = digest(design)
    if design_hash != manifest["inputs"]["config_hash"]:
        raise ValueError("Validation design identity mismatch")
    source = SnapshotDataset.create(design["source_snapshot_id"], design["source_triples"])
    if source.snapshot_hash != design["source_snapshot_hash"]:
        raise ValueError("Source snapshot content mismatch")
    split = ValidationSplit(tuple(tuple(t) for t in design["split"]["train"]),
                            tuple(tuple(t) for t in design["split"]["validation"]), design["split"]["version"])
    split.validate(source)
    if split.sha256 != design["split_hash"]:
        raise ValueError("Split identity mismatch")
    train = SnapshotDataset.create(source.snapshot_id + "_VALIDATION_TRAIN", split.train)
    identities = {"data_hash": source.snapshot_hash, "snapshot_hash": source.snapshot_hash,
                  "query_hash": digest(split.validation), "entity_map_hash": train.compute_mapping_hash(),
                  "relation_map_hash": digest(train.get_relation_mapping()), "config_hash": design_hash}
    if any(manifest["inputs"][key] != value for key, value in identities.items()):
        raise ValueError("Declared validation input identity/hash mismatch")
    if manifest.get("seed") != design["model"]["seed"]:
        raise ValueError("Validation seed identity mismatch")
    code_hashes = manifest["inputs"].get("code_hashes", {})
    required_code = {"kge/" + name for name in
                     ("validation.py", "splits.py", "model.py", "checkpoint.py", "contract.py", "math_utils.py")}
    required_code.update("kg_pipeline/" + name for name in ("experiment_manifest.py", "hashing.py", "storage.py"))
    if not required_code.issubset(code_hashes):
        raise ValueError("Executed validation code identity is incomplete")
    for relative, sha in code_hashes.items():
        require_bound("code/" + relative)
        if manifest["artifacts"]["hashes"]["code/" + relative] != sha:
            raise ValueError("Executed code hash mismatch")
    known = {tuple(t) for t in design["filter_positives"]}
    if known != {t.to_tuple() for t in source.triples}:
        raise ValueError("Validation positive filter mismatch")
    candidates = design["candidates"]
    if candidates != source.entities:
        raise ValueError("Candidate membership mismatch")
    pairs = design["negative_pairs"]
    if (len(pairs) != len(split.validation) or {tuple(a) for a, _ in pairs} != set(split.validation)):
        raise ValueError("Fixed negative validation population mismatch")
    for (h, r, t), (hn, rn, tn) in pairs:
        if (rn != r or ((h != hn) + (t != tn)) != 1 or (hn, rn, tn) in known
                or hn not in candidates or tn not in candidates):
            raise ValueError("Invalid fixed validation negative")
    logs = json.loads((run / "epoch_log.json").read_bytes())
    if [r["epoch"] for r in logs] != list(range(1, design["model"]["epochs"] + 1)):
        raise ValueError("Missing, duplicate or reordered epoch")
    total = 0
    candidate_index = {entity: i for i, entity in enumerate(candidates)}
    allowed = {}
    for h, r, t in sorted(split.validation):
        allowed[h, r, t] = (
            np.array([candidate == h or (candidate, r, t) not in known for candidate in candidates]),
            np.array([candidate == t or (h, r, candidate) not in known for candidate in candidates]),
        )
    for row in logs:
        epoch = row["epoch"]
        expected_checkpoint = f"epochs/{epoch:04d}.json"
        if row["checkpoint"] != expected_checkpoint or expected_checkpoint not in manifest["artifacts"]["hashes"]:
            raise ValueError("Unexpected checkpoint path")
        require_bound(expected_checkpoint + ".sha256", f"epochs/{epoch:04d}_ranks.json")
        cp = KGECheckpoint.load(run / expected_checkpoint)
        if (cp.provenance.config_hash != design_hash or cp.provenance.seed != design["model"]["seed"]
                or cp.provenance.norm != 2 or cp.provenance.dimension != design["model"]["dimension"]
                or cp.provenance.snapshot_id != train.snapshot_id
                or cp.provenance.snapshot_hash != train.snapshot_hash
                or cp.provenance.entity_mapping_hash != train.compute_mapping_hash()
                or cp.provenance.relation_mapping_hash != identities["relation_map_hash"]
                or cp.provenance.git_commit != manifest["git"]["commit"]
                or cp.provenance.git_dirty != manifest["git"]["dirty_state"]
                or set(cp.entity_embeddings) != set(train.entities)
                or set(cp.relation_embeddings) != set(train.relations)
                or cp.training_metrics["role"] != design["role"]
                or cp.training_metrics["design_hash"] != design_hash
                or cp.training_metrics["split_hash"] != split.sha256
                or cp.training_metrics["epoch"] != epoch):
            raise ValueError("Checkpoint provenance mismatch")
        if (row["design_hash"] != design_hash or row["seed"] != cp.provenance.seed
                or row["snapshot_id"] != source.snapshot_id):
            raise ValueError("Epoch identity mismatch")
        counts = row["train_diagnostics"]
        n = len(split.train)
        if (any(type(counts[k]) is not int for k in ("positives", "usable_negatives", "skipped", "margin_violations"))
                or counts["positives"] != n or not 0 < counts["usable_negatives"] <= n
                or counts["skipped"] != n - counts["usable_negatives"]
                or not 0 <= counts["margin_violations"] <= counts["usable_negatives"]
                or counts["loss_definition"] != "online_margin_loss_per_positive_v1"
                or type(counts["loss_sum"]) not in (float, int)
                or not math.isfinite(counts["loss_sum"]) or counts["loss_sum"] < 0):
            raise ValueError("Training sample/loss accounting mismatch")
        check_number(row["online_train_loss"], counts["loss_sum"] / n, "online training loss accounting")
        if row["validation_pairs"] != len(pairs):
            raise ValueError("Validation observation accounting mismatch")

        def energy(triple: list[str] | tuple[str, str, str]) -> float:
            h, r, t = triple
            delta = (np.asarray(cp.entity_embeddings[h]) + np.asarray(cp.relation_embeddings[r])
                     - np.asarray(cp.entity_embeddings[t]))
            return float(np.sqrt(np.sum(delta * delta)))

        losses = [max(0.0, design["model"]["margin"] + energy(a) - energy(b))
                  for a, b in design["negative_pairs"]]
        check_number(row["validation_loss"], sum(losses) / len(losses), "validation loss")
        saved = json.loads((run / "epochs" / f"{epoch:04d}_ranks.json").read_bytes())
        references = []
        entity_matrix = np.asarray([cp.entity_embeddings[e] for e in candidates])
        relation_vectors = {r: np.asarray(v) for r, v in cp.relation_embeddings.items()}
        for h, r, t in sorted(split.validation):
            head, tail = entity_matrix[candidate_index[h]], entity_matrix[candidate_index[t]]
            for side, gold, mask in zip(("head", "tail"), (h, t), allowed[h, r, t], strict=True):
                relation = relation_vectors[r]
                vectors = (entity_matrix + relation - tail if side == "head" else head + relation - entity_matrix)
                scores = -np.sqrt(np.sum(np.square(vectors), axis=1))
                ordered = np.sort(scores[mask])
                # Rank by positions of the target in a sorted list, independent of producer counting.
                lower, upper = np.searchsorted(ordered, scores[candidate_index[gold]], side="left"), np.searchsorted(
                    ordered, scores[candidate_index[gold]], side="right")
                rank = float(len(ordered) - (lower + upper - 1) / 2)
                references.append({"triple": [h, r, t], "side": side, "rank": rank,
                                   "reciprocal_rank": 1 / rank, "candidate_count": len(ordered)})
        if saved != references:
            raise ValueError("Independent validation ranking mismatch")
        expected = {"MRR": sum(r["reciprocal_rank"] for r in references) / len(references),
                    **{f"Hits@{k}": sum(r["rank"] <= k for r in references) / len(references) for k in (1, 3, 10)}}
        for k, value in expected.items():
            check_number(row["metrics"][k], value, "validation aggregate " + k)
        total += len(references)
    return {"status": "SAVED_VALIDATION_CHECKS_PASS", "epochs_verified": len(logs),
            "ranking_rows_verified": total, "scientific_certification": False,
            "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "manifest_sha256": hashlib.sha256((run / "experiment_manifest.json").read_bytes()).hexdigest(),
            "numpy_version": np.__version__,
            "scope": "fixed validation loss/ranks and lineage; online training trajectory not replayed"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().run), indent=2))
