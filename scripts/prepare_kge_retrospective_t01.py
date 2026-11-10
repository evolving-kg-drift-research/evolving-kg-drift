"""Build or replay the unscored T01 retrospective diagnostic candidate."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from kg_pipeline.experiment_manifest import bound_file, validate_manifest, verify_artifacts  # noqa: E402
from kg_pipeline.hashing import get_git_info, sha256_file  # noqa: E402
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset  # noqa: E402
from kge.splits import content_hash  # noqa: E402
from scripts.inspect_m2_inputs import inspect_snapshot, timestamp  # noqa: E402

RELEASE = "data/evolving_kg_downstream_v3_1"
PILOT = "outputs/kge_validation_dev/20261103_t01_three_seed_v1"
FEASIBILITY = "outputs/kge_independent_test_feasibility/20261104_v1"
SEEDS = (13, 37, 101)
COLUMNS = ["subject_id", "relation_id", "object_id", "evidence_observed_at"]
Triple = tuple[str, str, str]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> None:
    with path.open("xb") as stream:
        stream.write(json_bytes(value))


def prepare() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    inputs: dict[str, str] = {}

    def bind(relative: str, expected: str | None = None) -> Path:
        path = ROOT / relative
        digest = sha256_file(path) if expected is None else expected
        path = bound_file(ROOT, {"path": relative, "sha256": digest})
        require(inputs.setdefault(relative, digest) == digest, f"Conflicting binding: {relative}")
        return path

    audit_manifest = verify_artifacts(ROOT / FEASIBILITY)
    bind(f"{FEASIBILITY}/experiment_manifest.json")
    audit = read_json(bind(f"{FEASIBILITY}/audit.json", audit_manifest["artifacts"]["hashes"]["audit.json"]))
    audited = audit_manifest["inputs"]["hashes"]
    config_path = f"{RELEASE}/config/downstream_transe_config.yaml"
    specs = yaml.safe_load(bind(config_path, audited[config_path]).read_bytes())["snapshots"]
    release_path = f"{RELEASE}/release_manifest.json"
    release = read_json(bind(release_path, audited[release_path]))
    release_hashes = {entry["path"]: entry["sha256"] for entry in release["artifacts"]}
    cutoffs = [timestamp(spec["cutoff"]) for spec in specs]
    require(cutoffs == sorted(set(cutoffs)), "Non-increasing snapshot cutoffs")
    require([s["snapshot_id"] for s in specs] == [f"T{i:02d}" for i in range(1, 11)],
            "Unexpected snapshot series")

    snapshots: dict[str, set[Triple]] = {}
    records: dict[str, dict[str, Any]] = {}
    first_direct: dict[Triple, str] = {}
    observed_rows = 0
    # Read projected canonical rows separately and derive first presence by minimum snapshot ID.
    for spec in reversed(specs):
        parquet = bind(f"{RELEASE}/{spec['parquet_path']}", release_hashes[spec["parquet_path"]])
        sid = spec["snapshot_id"]
        cutoff = timestamp(spec["cutoff"])
        for row in pq.read_table(parquet, columns=COLUMNS).to_pylist():
            triple = (row["subject_id"], row["relation_id"], row["object_id"])
            require(timestamp(row["evidence_observed_at"]) <= cutoff, f"Future observation in {sid}")
            first_direct[triple] = sid
            observed_rows += 1
    for spec in specs:
        dataset, record, hashes = inspect_snapshot(ROOT / RELEASE, spec)
        sid = dataset.snapshot_id
        for relative, digest in hashes.items():
            path = f"{RELEASE}/{relative}"
            require(digest == release_hashes[relative] == audited[path], f"Release lineage mismatch: {path}")
            bind(path, digest)
        records[sid] = record
        snapshots[sid] = {triple.to_tuple() for triple in dataset.triples}

    pilot_path = f"{PILOT}/experiment_manifest.json"
    pilot = read_json(bind(pilot_path, audited[pilot_path]))
    validate_manifest(pilot)
    require(pilot["inputs"]["snapshot_hash"] == records["T01"]["snapshot_hash"], "Pilot T01 mismatch")
    parent_hashes = pilot["artifacts"]["hashes"]
    split_path = next(path for path in parent_hashes if path.startswith("inputs/") and path.endswith("/split.json"))
    split = read_json(bind(f"{PILOT}/{split_path}", parent_hashes[split_path]))
    train, validation = set(map(tuple, split["train"])), set(map(tuple, split["validation"]))
    require(len(train) == len(split["train"]) == 101 and len(validation) == len(split["validation"]) == 20
            and not train & validation and train | validation == snapshots["T01"], "T01 split mismatch")
    training = SnapshotDataset.create("T01_VALIDATION_TRAIN", sorted(train))
    candidates, relations = training.entities, set(training.relations)
    require(len(candidates) == 167 and len(relations) == 10, "Unexpected train mapping size")
    entity_hash = training.compute_mapping_hash()
    relation_hash = content_hash(training.get_relation_mapping())
    checkpoints = []
    for seed in SEEDS:
        folder = f"seed_{seed}"
        child_path = f"{folder}/experiment_manifest.json"
        child = read_json(bind(f"{PILOT}/{child_path}", parent_hashes[child_path]))
        validate_manifest(child)
        child_hashes = child["artifacts"]["hashes"]

        def pilot_artifact(name: str) -> Path:
            relative = f"{folder}/{name}"
            require(child_hashes[name] == parent_hashes[relative], f"Parent/child disagreement: {relative}")
            return bind(f"{PILOT}/{relative}", child_hashes[name])

        seed_design = read_json(pilot_artifact("design.json"))
        require(child["seed"] == seed and seed_design["role"] == "quality_validation"
                and seed_design["source_snapshot_hash"] == records["T01"]["snapshot_hash"]
                and set(map(tuple, seed_design["split"]["train"])) == train
                and set(map(tuple, seed_design["split"]["validation"])) == validation
                and seed_design["candidates"] == candidates and seed_design["model"]["epochs"] == 50,
                f"Pilot seed design mismatch: {seed}")
        path = pilot_artifact("epochs/0050.json")
        sidecar = pilot_artifact("epochs/0050.json.sha256")
        checkpoint = KGECheckpoint.load(path)
        prov = checkpoint.provenance
        require((prov.model, prov.norm, prov.dimension, prov.seed) == ("TransE", 2, 64, seed)
                and (prov.snapshot_id, prov.snapshot_hash) == (training.snapshot_id, training.snapshot_hash)
                and (prov.entity_mapping_hash, prov.relation_mapping_hash) == (entity_hash, relation_hash)
                and prov.config_hash == child["inputs"]["config_hash"] == content_hash(seed_design)
                and checkpoint.training_metrics == {"epoch": 50, "role": "quality_validation",
                    "design_hash": prov.config_hash, "split_hash": seed_design["split_hash"]}
                and set(checkpoint.entity_embeddings) == set(candidates)
                and set(checkpoint.relation_embeddings) == relations, f"Checkpoint mismatch: {seed}")
        relative = path.relative_to(ROOT).as_posix()
        checkpoints.append({"seed": seed, "epoch": 50, "path": relative, "sha256": inputs[relative],
                            "sidecar": sidecar.relative_to(ROOT).as_posix(),
                            "semantic_hash": checkpoint.artifact_hash})

    entities = set(candidates)
    val_heads = {(r, t) for _, r, t in validation}
    val_tails = {(h, r) for h, r, _ in validation}
    seen: set[Triple] = set()
    members = []
    counts: Counter[str] = Counter()
    for sid, triples in snapshots.items():
        for h, r, t in sorted(triples - seen):
            if sid == "T01" or h not in entities or t not in entities or r not in relations:
                continue
            counts[sid] += 1
            members.append({"snapshot": sid, "cutoff": records[sid]["cutoff"], "triple": [h, r, t],
                            "head_key_in_prior_validation": (r, t) in val_heads,
                            "tail_key_in_prior_validation": (h, r) in val_tails})
        seen.update(triples)
    replay = {(sid, triple) for triple, sid in first_direct.items() if sid != "T01"
              and triple[0] in entities and triple[1] in relations and triple[2] in entities}
    require({(row["snapshot"], tuple(row["triple"])) for row in members} == replay, "Membership replay mismatch")
    overlap = sum(row["head_key_in_prior_validation"] or row["tail_key_in_prior_validation"] for row in members)
    later = sum(sid != "T01" for sid in first_direct.values())
    require(len(members) == len(replay) == audit["later_seen_id_triples"] == 26
            and len(seen) == len(first_direct) == audit["unique_canonical_triples"]
            and later == audit["later_first_present_triples"]
            and overlap == audit["later_seen_id_query_overlap_triples"] == 2
            and dict(Counter(row["triple"][1] for row in members)) == audit["later_seen_id_relation_counts"]
            and all(counts[row["snapshot"]] == row["all_ids_seen_in_t01_training"] for row in audit["snapshot_rows"]),
            "Feasibility totals disagree")

    queries = []
    for number, member in enumerate(members, start=1):
        h, r, t = member["triple"]
        sid = member["snapshot"]
        positives = snapshots[sid]
        for side, target in (("head", h), ("tail", t)):
            filtered = [e for e in candidates if e != target
                        and ((e, r, t) if side == "head" else (h, r, e)) in positives]
            if side == "head":
                replay_mask = ({a for a, b, c in positives if (b, c) == (r, t)} & entities) - {target}
            else:
                replay_mask = ({c for a, b, c in positives if (a, b) == (h, r)} & entities) - {target}
            require(set(filtered) == replay_mask and target in entities and (h, r, t) in positives,
                    "Invalid filter mask")
            queries.append({"query_id": f"{sid}-{number:02d}-{side}", "snapshot": sid, "side": side,
                            "triple": member["triple"], "target": target, "filtered_entities": filtered,
                            "candidate_count_after_filter": len(candidates) - len(filtered)})

    for relative in ("configs/protocol_v1.yaml", "configs/kge.yaml", "configs/schemas/experiment_manifest.schema.yaml",
                     "scripts/evaluate_legacy_t01.py", "scripts/inspect_m2_inputs.py", "src/kge/checkpoint.py",
                     "src/kge/contract.py", "src/kge/math_utils.py", "src/kge/model.py", "src/kge/splits.py",
                     "src/kg_pipeline/experiment_manifest.py", "src/kg_pipeline/hashing.py",
                     Path(__file__).relative_to(ROOT).as_posix()):
        bind(relative, audited.get(relative))
    design = {
        "version": "kge_retrospective_t01_v1", "status": "CANDIDATE_NOT_ACTIVE",
        "role": "retrospective_dev_link_prediction", "scientific_certification": False,
        "model": {"name": "TransE", "norm": 2, "dimension": 64, "score": "-L2(h + r - t)",
                  "checkpoint_selection": "fixed epoch 50 for every seed", "checkpoints": checkpoints},
        "baseline": {"score": "frequency of substituted entity as either endpoint in exact pilot train",
                     "training_split": f"{PILOT}/{split_path}", "training_triples": len(train),
                     "train_membership_hash": content_hash(sorted(train))},
        "population": "first presence after T01 in canonical T01-T10 with all IDs in exact T01 pilot train",
        "unit": "one head and one tail query for each distinct triple at its first-present snapshot",
        "candidates": candidates, "filter": "other true triples in the query snapshot only; always retain target",
        "ties": "exact equality, rank = 1 + strictly better + (tied including target - 1) / 2",
        "metrics": {"MRR": "mean of 1/rank over all 52 queries",
                    "Hits@1": "fraction with rank <= 1", "Hits@10": "fraction with rank <= 10"},
        "comparison": "per-seed paired full-panel metric difference (TransE minus shared baseline), "
                      "then arithmetic mean over the three seeds; descriptive only",
        "primary_query_set": "all queries; keep prior validation key overlaps and flag at triple level",
        "artifacts": {"members": "members.json", "queries": "queries.json"},
        "entity_map_hash": entity_hash, "relation_map_hash": relation_hash,
    }
    artifacts = {"design.json": design, "members.json": members, "queries.json": queries,
                 "preflight.json": {"status": "DESIGN_CHECKS_PASS", "scoring_authorized": False,
                     "canonical_rows_timestamp_checked": observed_rows, "snapshot_records": records,
                     "later_first_present_triples": later, "triples": len(members), "queries": len(queries),
                     "overlap_triples": overlap, "counts_by_snapshot": {sid: counts[sid] for sid in snapshots},
                     "candidate_count": len(candidates), "candidate_substitutions_filtered": sum(
                         len(row["filtered_entities"]) for row in queries),
                     "checkpoint_count": len(checkpoints)}}
    return design, artifacts, inputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--write", action="store_true", help="Create a fresh candidate directory under outputs/")
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "outputs") and output != ROOT / "outputs"
            and all(p.lower() != "locked_test" for p in output.parts), "Expected a candidate under outputs/")
    if args.write:
        require(not output.exists(), "Refusing to overwrite an existing run")
    design, artifacts, inputs = prepare()
    preflight = artifacts["preflight.json"]
    if args.write:
        output.mkdir(parents=True, exist_ok=False)
        for name, data in artifacts.items():
            write_json(output / name, data)
        commit, dirty = get_git_info(ROOT)
        records = preflight["snapshot_records"]
        manifest = {"experiment_id": output.name, "protocol_version": "v1-draft", "seed": None,
                    "model_seeds": list(SEEDS), "stage": "retrospective_dev_design",
                    "scientific_certification": False, "git": {"commit": commit, "dirty_state": dirty},
                    "inputs": {"data_hash": content_hash({s: r["physical_sha256"] for s, r in records.items()}),
                               "snapshot_hash": content_hash({s: r["snapshot_hash"] for s, r in records.items()}),
                               "query_hash": content_hash(artifacts["queries.json"]),
                               "entity_map_hash": design["entity_map_hash"],
                               "relation_map_hash": design["relation_map_hash"],
                               "config_hash": content_hash(design), "hashes": inputs},
                    "environment": {"python": platform.python_version(), "os": platform.platform()},
                    "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
                    "access": {"state": "dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                               "actor_or_runner": Path(__file__).name},
                    "artifacts": {"hashes": {name: sha256_file(output / name) for name in artifacts}}}
        validate_manifest(manifest)
        write_json(output / "experiment_manifest.json", manifest)
    manifest = verify_artifacts(output)
    require(manifest["inputs"]["hashes"] == inputs and manifest["inputs"]["config_hash"] == content_hash(design)
            and manifest["inputs"]["query_hash"] == content_hash(artifacts["queries.json"])
            and set(manifest["artifacts"]["hashes"]) == set(artifacts), "Manifest replay mismatch")
    for relative, digest in inputs.items():
        bound_file(ROOT, {"path": relative, "sha256": digest})
    for name, data in artifacts.items():
        require((output / name).read_bytes() == json_bytes(data), f"Candidate replay mismatch: {name}")
    print(json.dumps({k: v for k, v in preflight.items() if k != "snapshot_records"}
                     | {"design_hash": content_hash(design), "bound_inputs": len(inputs)}, indent=2))


if __name__ == "__main__":
    main()
