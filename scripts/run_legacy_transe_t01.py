"""User-authorized T01 legacy smoke experiment; never a certified M2 loader."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pyarrow
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset, Triple  # noqa: E402
from kge.model import TransEConfig  # noqa: E402
from kge.trainer import train_single_seed  # noqa: E402

INPUT = "data/KG_lan2/evolving_kg_downstream_v3/snapshots/snapshot_T01_canonical.parquet"
EXPECTED_SHA256 = "42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e"
SCOPE = {
    "mode": "legacy_exploration", "snapshot_id": "LEGACY_V3_T01",
    "input": INPUT, "input_sha256": EXPECTED_SHA256,
    "seeds": [13, 37, 101], "dimension": 32, "norm": 2,
    "epochs": 50, "learning_rate": 0.01, "margin": 1.0,
    "dev_split_ratio": 0.0, "repetitions_per_seed": 2,
    "purpose": "training/serialization/reproducibility smoke check only",
    "scientific_certification": False,
    "authorization": "User selected T01 after the bounded legacy scope was presented, 2026-10-13",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False).encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(encode(value))


def read_legacy_input(path: Path, expected_hash: str) -> SnapshotDataset:
    """Validate bytes and triples, without asserting scientific provenance."""
    payload = path.read_bytes()
    if sha(payload) != expected_hash:
        raise ValueError("Legacy input hash differs from the authorized bytes")
    sidecar = json.loads(path.with_suffix(".parquet.manifest.json").read_bytes())
    rows = pq.read_table(pyarrow.BufferReader(payload)).to_pylist()
    semantic = json.dumps({"table_name": sidecar["table_name"],
                           "contract_version": sidecar["contract_version"], "rows": rows},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if (sidecar["physical_sha256_computed_at_real"] != expected_hash
            or sidecar["semantic_sha256"] != sha(semantic)
            or sidecar["row_count"] != len(rows)):
        raise ValueError("Legacy sidecar does not match its Parquet")
    values = [(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows]
    if not values or any(not isinstance(v, str) or not v.strip() for t in values for v in t):
        raise ValueError("Legacy triples need nonempty string IDs")
    if len(values) != len(set(values)):
        raise ValueError("Legacy canonical triples must be unique")
    return SnapshotDataset.create(SCOPE["snapshot_id"], [Triple(*t) for t in values])


def main() -> None:
    source = ROOT / INPUT
    dataset = read_legacy_input(source, EXPECTED_SHA256)
    if (len(dataset.triples), len(dataset.entities), len(dataset.relations)) != (121, 167, 10):
        raise ValueError("Unexpected T01 dimensions")
    git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                     cwd=ROOT, text=True)
    dirty = bool(status.strip())
    now = datetime.now(timezone.utc)
    run_id = f"t01_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    out = ROOT / "outputs/legacy_transe" / run_id
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "scope.json", SCOPE)
    code = [Path(__file__), *sorted((ROOT / "src/kge").glob("*.py"))]
    code_hashes = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in code}
    write_json(out / "code_hashes.json", code_hashes)
    for p in code:
        target = out / "code" / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(p.read_bytes())
    write_json(out / "environment.json", {"python": platform.python_version(),
               "os": platform.platform(), "pyarrow": pyarrow.__version__})
    mappings = {"entities": dataset.get_entity_mapping(), "relations": dataset.get_relation_mapping()}
    write_json(out / "mappings.json", mappings)
    input_hashes = {INPUT: sha(source.read_bytes()), INPUT + ".manifest.json":
                    sha(source.with_suffix(".parquet.manifest.json").read_bytes())}
    results = []
    schema = yaml.safe_load((ROOT / "configs/schemas/experiment_manifest.schema.yaml").read_bytes())
    for seed in SCOPE["seeds"]:
        cfg = TransEConfig(dimension=32, norm=2, epochs=50, learning_rate=0.01, margin=1.0, seed=seed)
        write_json(out / f"seed_{seed}_config.json", asdict(cfg))
        checkpoints = []
        timings = []
        for repetition in (1, 2):
            started = time.perf_counter()
            checkpoint = train_single_seed(dataset, cfg, dev_split_ratio=0.0,
                                           git_commit=git_commit, git_dirty=dirty)
            timings.append(time.perf_counter() - started)
            vectors = [*checkpoint.entity_embeddings.values(), *checkpoint.relation_embeddings.values()]
            if not all(len(v) == 32 and all(math.isfinite(x) for x in v) for v in vectors):
                raise ValueError("Invalid embedding dimensions or values")
            losses = checkpoint.training_metrics["epoch_losses"]
            if len(losses) != 50 or not all(math.isfinite(x) for x in losses):
                raise ValueError("Invalid loss sequence")
            if (set(checkpoint.entity_embeddings) != set(dataset.entities)
                    or set(checkpoint.relation_embeddings) != set(dataset.relations)
                    or checkpoint.provenance.entity_mapping_hash != dataset.compute_mapping_hash()):
                raise ValueError("Mapping mismatch")
            path = out / f"seed_{seed}_repeat_{repetition}.json"
            checkpoint.save(path)
            loaded = KGECheckpoint.load(path)
            if loaded != checkpoint or loaded.compute_artifact_hash() != checkpoint.artifact_hash:
                raise ValueError("Checkpoint round-trip mismatch")
            checkpoints.append(path)
        if checkpoints[0].read_bytes() != checkpoints[1].read_bytes():
            raise ValueError("Same-seed full checkpoint bytes are not identical")
        result = {"seed": seed, "first_loss": losses[0], "final_loss": losses[-1],
                  "elapsed_seconds": timings, "exact_checkpoint_replay": True,
                  "checkpoint_sha256": sha(checkpoints[0].read_bytes())}
        results.append(result)
        manifest = {
            "experiment_id": f"{run_id}_seed_{seed}", "protocol_version": "v1-draft",
            "mode": "legacy_exploration", "scientific_certification": False,
            "git": {"commit": git_commit, "dirty_state": dirty},
            "inputs": {"data_hash": EXPECTED_SHA256, "snapshot_hash": dataset.snapshot_hash,
                       "query_hash": None, "entity_map_hash": dataset.compute_mapping_hash(),
                       "relation_map_hash": checkpoint.provenance.relation_mapping_hash,
                       "config_hash": checkpoint.provenance.config_hash, "hashes": input_hashes,
                       "scope_hash": sha(encode(SCOPE)), "code_hashes": code_hashes},
            "seed": seed, "environment": {"python": platform.python_version(), "os": platform.platform()},
            "hardware": {"cpu": platform.processor(), "ram": None,
                         "ram_measurement": "not measured", "elapsed_seconds": timings},
            "artifacts": {"hashes": {p.name: sha(p.read_bytes()) for p in checkpoints}},
            "access": {"state": "dev", "timestamp": now.isoformat(),
                       "actor_or_runner": "scripts/run_legacy_transe_t01.py"},
            "limitations": ["No held-out evaluation; query_hash is inapplicable",
                            "Legacy identity/provenance remain uncertified; all scientific gates unchanged"],
        }
        if any(k not in manifest for k in schema["required"]):
            raise ValueError("Experiment manifest missing required fields")
        for field, rules in schema["fields"].items():
            if any(k not in manifest.get(field, {}) for k in rules.get("required", [])):
                raise ValueError(f"Manifest missing nested fields: {field}")
        write_json(out / f"seed_{seed}_manifest.json", manifest)
    if any(sha((ROOT / p).read_bytes()) != h for p, h in input_hashes.items()):
        raise ValueError("Input changed during experiment")
    write_json(out / "summary.json", {"status": "LEGACY_TECHNICAL_CHECKS_PASS",
               "scientific_certification": False, "counts": {"triples": 121, "entities": 167, "relations": 10},
               "input_unchanged": True, "results": results})
    artifacts = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()}
    write_json(out / "artifact_hashes.json", artifacts)
    print(json.dumps({"output": str(out), "results": results}, indent=2))


if __name__ == "__main__":
    main()
