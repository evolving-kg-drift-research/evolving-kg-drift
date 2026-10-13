"""Approved 101/20 legacy link-prediction experiment; no scientific certification."""
from __future__ import annotations

import json
import math
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_legacy_split_t01 import audit  # noqa: E402
from scripts.run_legacy_transe_t01 import (  # noqa: E402
    EXPECTED_SHA256, INPUT, encode, read_legacy_input, sha, write_json,
)
from kge.checkpoint import KGECheckpoint  # noqa: E402
from kge.contract import SnapshotDataset, Triple  # noqa: E402
from kge.model import TransEConfig  # noqa: E402
from kge.trainer import train_single_seed  # noqa: E402

TripleTuple = tuple[str, str, str]


def rank_query(
    triple: TripleTuple, side: str, candidates: list[str],
    positives: set[TripleTuple], score: Callable[[TripleTuple], float],
) -> dict[str, Any]:
    """Higher scores are better; exact score ties receive their average rank."""
    if side not in ("head", "tail"):
        raise ValueError("Invalid prediction side")
    h, r, t = triple
    target = h if side == "head" else t
    if target not in candidates or len(candidates) != len(set(candidates)):
        raise ValueError("Missing target or duplicate candidate")
    scored = []
    for entity in candidates:
        alternative = (entity, r, t) if side == "head" else (h, r, entity)
        if entity != target and alternative in positives:
            continue
        value = score(alternative)
        if not math.isfinite(value):
            raise ValueError("Non-finite ranking score")
        scored.append((entity, value))
    target_score = next(value for entity, value in scored if entity == target)
    better = sum(value > target_score for _, value in scored)
    tied = sum(value == target_score for _, value in scored)
    rank = 1 + better + (tied - 1) / 2
    return {"triple": triple, "side": side, "rank": rank, "reciprocal_rank": 1 / rank,
            "better": better, "tied_including_target": tied,
            "candidate_count": len(scored), "filtered_count": len(candidates) - len(scored),
            "target_score": target_score,
            "candidate_scores": scored}


def metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    if not rows:
        raise ValueError("Cannot score an empty population")
    return {"queries": len(rows), "MRR": sum(1/r["rank"] for r in rows)/len(rows),
            **{f"Hits@{k}": sum(r["rank"] <= k for r in rows)/len(rows) for k in (1, 3, 10)}}


def evaluate(
    heldout: list[TripleTuple], candidates: list[str], positives: set[TripleTuple],
    score: Callable[[TripleTuple], float],
) -> list[dict[str, Any]]:
    return [rank_query(t, side, candidates, positives, score) for t in heldout for side in ("head", "tail")]


def main() -> None:
    original = read_legacy_input(ROOT / INPUT, EXPECTED_SHA256)
    triples = [t.to_tuple() for t in original.triples]
    split_audit = audit(triples)
    recorded = json.loads((ROOT / "outputs/legacy_split_audit/20261013T165714Z_b4c0f356/report.json").read_bytes())
    for key in ("witness_train", "witness_heldout"):
        if [list(t) for t in split_audit[key]] != recorded[key]:
            raise ValueError("Split differs from the reviewed witness")
    train_rows = split_audit["witness_train"]
    heldout = split_audit["witness_heldout"]
    if len(train_rows) != 101 or len(heldout) != 20:
        raise ValueError("Unexpected split counts")
    train = SnapshotDataset.create("LEGACY_T01_TRAIN101", [Triple(*t) for t in train_rows])
    if set(train.entities) != set(original.entities) or set(train.relations) != set(original.relations):
        raise ValueError("Split has OOV entities or relations")
    if set(train_rows) & set(heldout) or set(train_rows) | set(heldout) != set(triples):
        raise ValueError("Invalid split partition")
    now = datetime.now(timezone.utc)
    out = ROOT / "outputs/legacy_evaluation" / (now.strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    split = {"train": train_rows, "heldout": heldout}
    design = {"authorization_date": "2026-10-14", "scope": "user-approved legacy 101/20 evaluation",
              "input_sha256": EXPECTED_SHA256, "split_hash": sha(encode(split)),
              "seeds": [13, 37, 101], "dimension": 32, "epochs": 50,
              "learning_rate": 0.01, "margin": 1.0, "norm": 2,
              "candidates": "167 training entities; no type restriction",
              "queries": "20 held-out triples, both head and tail",
              "filter": "all 121 T01 positives, only during evaluation; always retain target",
              "ties": "average rank of exactly equal scores; Hits@k uses average rank <= k",
              "baseline": "global training endpoint frequency, head+tail occurrences summed",
              "tuning": False, "scientific_certification": False}
    # These immutable files exist before any model training or metric computation.
    write_json(out / "design.json", design)
    write_json(out / "split.json", split)
    candidates = train.entities
    write_json(out / "mappings.json", {"entities": train.get_entity_mapping(), "relations": train.get_relation_mapping()})
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT).strip())
    code_paths = [Path(__file__), ROOT/"scripts/audit_legacy_split_t01.py", ROOT/"scripts/run_legacy_transe_t01.py",
                  *sorted((ROOT/"src/kge").glob("*.py"))]
    code_hashes = {}
    for p in code_paths:
        relative = p.relative_to(ROOT)
        target = out/"code"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = p.read_bytes()
        with target.open("xb") as handle:
            handle.write(payload)
        code_hashes[relative.as_posix()] = sha(payload)
    write_json(out/"code_hashes.json", code_hashes)
    known = set(triples)
    frequency = Counter(entity for h, _, t in train_rows for entity in (h, t))
    write_json(out / "baseline_frequency.json", dict(frequency))
    baseline = [rank_query(t, side, candidates, known,
                           lambda alt, s=side: float(frequency[alt[0] if s == "head" else alt[2]]))
                for t in heldout for side in ("head", "tail")]
    write_json(out / "baseline_ranks.json", baseline)
    results: dict[str, Any] = {"baseline": metrics(baseline), "seeds": {}}
    for seed in (13, 37, 101):
        config = TransEConfig(dimension=32, epochs=50, learning_rate=0.01, margin=1.0, norm=2, seed=seed)
        ckpt = train_single_seed(train, config, dev_split_ratio=0.0, git_commit=commit, git_dirty=dirty)
        ckpt.save(out / f"seed_{seed}.json")
        loaded = KGECheckpoint.load(out / f"seed_{seed}.json")
        if loaded != ckpt:
            raise ValueError("Checkpoint round-trip failed")

        def score(row: TripleTuple) -> float:
            h, r, t = row
            return -math.sqrt(sum((x+y-z)**2 for x, y, z in zip(
                loaded.entity_embeddings[h], loaded.relation_embeddings[r], loaded.entity_embeddings[t])))

        ranks = evaluate(heldout, candidates, known, score)
        write_json(out / f"seed_{seed}_ranks.json", ranks)
        results["seeds"][str(seed)] = {"all": metrics(ranks),
            "head": metrics([r for r in ranks if r["side"] == "head"]),
            "tail": metrics([r for r in ranks if r["side"] == "tail"])}
        manifest = {"experiment_id": out.name + f"_seed_{seed}", "protocol_version": "v1-draft",
            "mode": "legacy_evaluation", "scientific_certification": False,
            "git": {"commit": commit, "dirty_state": dirty}, "seed": seed,
            "inputs": {"data_hash": EXPECTED_SHA256, "snapshot_hash": train.snapshot_hash,
                "query_hash": sha(encode(heldout)), "entity_map_hash": train.compute_mapping_hash(),
                "relation_map_hash": ckpt.provenance.relation_mapping_hash,
                "config_hash": sha(encode(design)), "training_config_hash": ckpt.provenance.config_hash,
                "split_hash": design["split_hash"], "code_hashes": code_hashes},
            "environment": {"python": platform.python_version(), "os": platform.platform()},
            "hardware": {"cpu": platform.processor(), "ram": None, "ram_note": "not measured"},
            "artifacts": {"hashes": {p.name: sha(p.read_bytes()) for p in
                [out/f"seed_{seed}.json", out/f"seed_{seed}_ranks.json", out/"baseline_ranks.json"]}},
            "access": {"state": "dev", "timestamp": now.isoformat(), "actor_or_runner": "scripts/evaluate_legacy_t01.py"}}
        write_json(out / f"seed_{seed}_manifest.json", manifest)
    if sha((ROOT / INPUT).read_bytes()) != EXPECTED_SHA256:
        raise ValueError("Input changed")
    results["input_unchanged"] = True
    results["scientific_certification"] = False
    write_json(out / "results.json", results)
    write_json(out / "artifact_hashes.json", {p.relative_to(out).as_posix(): sha(p.read_bytes())
                                              for p in out.rglob("*") if p.is_file()})
    print(json.dumps({"output": str(out), **results}, indent=2))


if __name__ == "__main__":
    main()
