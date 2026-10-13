"""Observe the existing training loop without changing its RNG or calculations."""
from __future__ import annotations

import inspect
import json
import math
import platform
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Any, Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_legacy_transe_t01 import (  # noqa: E402
    EXPECTED_SHA256, INPUT, encode, read_legacy_input, sha, write_json,
)
from kge.contract import SnapshotDataset, Triple  # noqa: E402
from kge.model import TransEConfig, TransEModel  # noqa: E402
from kge.trainer import train_single_seed  # noqa: E402

REFERENCE = ROOT / "outputs/legacy_evaluation/20261013T170623Z_e7a3592e"


class EpochObserver:
    """Python line tracing: read locals only, never call the training RNG."""

    def __init__(self) -> None:
        method = TransEModel.train_epoch
        lines, first = inspect.getsourcelines(method)
        anchors = {
            "trial": "corrupt_head = rng.random() < 0.5",
            "head_draw": "if cand_h != h_idx and",
            "tail_draw": "if cand_o != o_idx and",
            "sample_done": "if corrupt_h == h_idx and corrupt_o == o_idx:",
            "hinge": "if loss > 0.0:",
        }
        self.lines = {}
        for key, prefix in anchors.items():
            matches = [first+i for i, line in enumerate(lines) if line.strip().startswith(prefix)]
            if len(matches) != 1:
                raise ValueError(f"Training source instrumentation anchor changed: {key}")
            self.lines[key] = matches[0]
        self.code = method.__code__
        self.epochs: list[dict[str, Any]] = []
        self.current: dict[str, Any] = {}

    @staticmethod
    def norms(model: TransEModel) -> dict[str, float]:
        return {r: math.sqrt(sum(v*v for v in model.relation_embeddings[i]))
                for r, i in model.relation_to_id.items()}

    def trace(self, frame: FrameType, event: str, arg: Any) -> Callable | None:
        if frame.f_code is not self.code:
            return None
        values = frame.f_locals
        if event == "call":
            self.current = {"epoch": len(self.epochs)+1, "counts": Counter(), "samples": [],
                            "relation_norms_start": self.norms(values["self"])}
        elif event == "line":
            counts = self.current["counts"]
            line = frame.f_lineno
            if line == self.lines["trial"]:
                counts["triples_visited"] += 1
            elif line in (self.lines["head_draw"], self.lines["tail_draw"]):
                counts["candidate_draws"] += 1
                head = line == self.lines["head_draw"]
                candidate = values["cand_h" if head else "cand_o"]
                original = values["h_idx" if head else "o_idx"]
                alternative = ((candidate, values["r_idx"], values["o_idx"]) if head
                               else (values["h_idx"], values["r_idx"], candidate))
                if candidate == original:
                    counts["rejected_original"] += 1
                elif alternative in values["positive_triples_set"]:
                    counts["rejected_positive"] += 1
            elif line == self.lines["sample_done"]:
                positive = (values["h_idx"], values["r_idx"], values["o_idx"])
                negative = (values["corrupt_h"], values["r_idx"], values["corrupt_o"])
                side = "head" if values["corrupt_head"] else "tail"
                skipped = positive == negative
                counts["skipped_no_negative" if skipped else "valid_negatives"] += 1
                counts[f"{side}_trials"] += 1
                if not skipped:
                    if negative in values["positive_triples_set"]:
                        raise ValueError("Observer found positive sampled as negative")
                    counts["self_loop_negatives"] += negative[0] == negative[2]
                self.current["samples"].append({"positive": positive, "negative": None if skipped else negative,
                                                 "side": side, "skipped": skipped})
            elif line == self.lines["hinge"]:
                active = values["loss"] > 0.0
                counts["active_updates" if active else "inactive_hinge"] += 1
                sample = self.current["samples"][-1]
                sample["margin_expression"] = values["loss"]
                sample["updated"] = active
                counts["active_self_loop_updates"] += active and values["corrupt_h"] == values["corrupt_o"]
        elif event == "return":
            counts = self.current["counts"]
            for key in ("triples_visited", "candidate_draws", "rejected_original", "rejected_positive",
                        "skipped_no_negative", "valid_negatives", "self_loop_negatives",
                        "active_updates", "inactive_hinge", "active_self_loop_updates", "head_trials", "tail_trials"):
                counts.setdefault(key, 0)
            if (counts["triples_visited"] != counts["valid_negatives"]+counts["skipped_no_negative"]
                    or counts["valid_negatives"] != counts["active_updates"]+counts["inactive_hinge"]):
                raise ValueError("Trace accounting does not balance")
            self.current["counts"] = dict(counts)
            self.current["relation_norms_end"] = self.norms(values["self"])
            self.current["loss"] = arg
            self.epochs.append(self.current)
        return self.trace


def observe_training(dataset: SnapshotDataset, config: TransEConfig, commit: str, dirty: bool):
    if sys.gettrace() is not None:
        raise RuntimeError("Existing tracing session: observer will not replace it")
    observer = EpochObserver()
    try:
        sys.settrace(observer.trace)
        checkpoint = train_single_seed(dataset, config, dev_split_ratio=0.0,
                                       git_commit=commit, git_dirty=dirty)
    finally:
        sys.settrace(None)
    return checkpoint, observer.epochs


def main() -> None:
    reference_inventory = json.loads((REFERENCE/"artifact_hashes.json").read_bytes())
    if any(sha((REFERENCE/p).read_bytes()) != h for p,h in reference_inventory.items()):
        raise ValueError("Reference artifacts changed")
    original = read_legacy_input(ROOT/INPUT, EXPECTED_SHA256)
    split = json.loads((REFERENCE/"split.json").read_bytes())
    train_rows = split["train"]
    if len(train_rows) != 101 or not set(map(tuple, train_rows)).issubset({t.to_tuple() for t in original.triples}):
        raise ValueError("Unexpected training population")
    dataset = SnapshotDataset.create("LEGACY_T01_TRAIN101", [Triple(*t) for t in train_rows])
    now = datetime.now(timezone.utc)
    out = ROOT/"outputs/legacy_training_diagnostics"/(now.strftime("%Y%m%dT%H%M%SZ")+"_"+uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    design = {"mode": "legacy_training_diagnostics", "authorization_date": "2026-10-14",
              "input_sha256": EXPECTED_SHA256, "train_rows": 101, "epochs": 50,
              "seeds": [13,37,101], "reference_run": REFERENCE.relative_to(ROOT).as_posix(),
              "reference_split_sha256": sha((REFERENCE/"split.json").read_bytes()),
              "observer": "sys.settrace, read-only locals, no new random draws",
              "scientific_certification": False}
    write_json(out/"design.json", design)
    write_json(out/"train.json", train_rows)
    write_json(out/"mappings.json", {"entities":dataset.get_entity_mapping(), "relations":dataset.get_relation_mapping()})
    code_hashes = {}
    for p in [Path(__file__), ROOT/"scripts/run_legacy_transe_t01.py", *sorted((ROOT/"src/kge").glob("*.py"))]:
        relative = p.relative_to(ROOT)
        payload = p.read_bytes()
        target = out/"code"/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as handle:
            handle.write(payload)
        code_hashes[relative.as_posix()] = sha(payload)
        if relative.as_posix() in json.loads((REFERENCE/"code_hashes.json").read_bytes()):
            if code_hashes[relative.as_posix()] != json.loads((REFERENCE/"code_hashes.json").read_bytes())[relative.as_posix()]:
                raise ValueError("Training implementation changed since reference")
    write_json(out/"code_hashes.json",code_hashes)
    summaries = {}
    for seed in (13,37,101):
        prior = json.loads((REFERENCE/f"seed_{seed}.json").read_bytes())
        config = TransEConfig(dimension=32, epochs=50, learning_rate=0.01, margin=1.0, norm=2, seed=seed)
        write_json(out/f"seed_{seed}_config.json",asdict(config))
        checkpoint, epochs = observe_training(dataset, config, prior["provenance"]["git_commit"],
                                              prior["provenance"]["git_dirty"])
        path = out/f"seed_{seed}.json"
        checkpoint.save(path)
        if path.read_bytes() != (REFERENCE/f"seed_{seed}.json").read_bytes():
            raise ValueError("Observer changed the full serialized checkpoint")
        write_json(out/f"seed_{seed}_epochs.json",epochs)
        totals = Counter()
        for epoch in epochs:
            totals.update(epoch["counts"])
        summaries[str(seed)] = {"counts":dict(totals), "first_epoch":epochs[0]["counts"],
             "last_epoch":epochs[-1]["counts"], "checkpoint_byte_identical":True,
             "relation_norms_initial":epochs[0]["relation_norms_start"],
             "relation_norms_final":epochs[-1]["relation_norms_end"]}
        # Replay checkpoints retain the historical provenance to compare full bytes.
        # This manifest records the actual new diagnostic execution separately.
        manifest = {"experiment_id":out.name+f"_seed_{seed}","protocol_version":"v1-draft",
            "mode":"legacy_training_diagnostics", "scientific_certification":False,"seed":seed,
            "git":{"commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                   "dirty_state":bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=ROOT).strip()),
                   "new_code_snapshot":True},
            "inputs":{"data_hash":EXPECTED_SHA256,"snapshot_hash":dataset.snapshot_hash,"query_hash":None,
                      "entity_map_hash":dataset.compute_mapping_hash(),"relation_map_hash":checkpoint.provenance.relation_mapping_hash,
                      "config_hash":checkpoint.provenance.config_hash,"design_hash":sha(encode(design)),
                      "code_hashes":code_hashes,"reference_checkpoint_hash":sha((REFERENCE/f"seed_{seed}.json").read_bytes())},
            "environment":{"python":platform.python_version(),"os":platform.platform()},
            "hardware":{"cpu":platform.processor(),"ram":None,"ram_note":"not measured"},
            "artifacts":{"hashes":{p.name:sha(p.read_bytes()) for p in [path,out/f"seed_{seed}_epochs.json"]}},
            "access":{"state":"dev","timestamp":now.isoformat(),"actor_or_runner":"scripts/diagnose_legacy_t01_training.py"},
            "provenance_note":"Checkpoint metadata repeats historical provenance solely for exact replay; manifest describes this run"}
        write_json(out/f"seed_{seed}_manifest.json",manifest)
    unchanged = (sha((ROOT/INPUT).read_bytes()) == EXPECTED_SHA256 and
                 all(sha((REFERENCE/p).read_bytes()) == h for p,h in reference_inventory.items()))
    if not unchanged:
        raise ValueError("Inputs or reference changed")
    write_json(out/"summary.json",{"seeds":summaries,"input_and_reference_unchanged":True,"scientific_certification":False})
    write_json(out/"artifact_hashes.json",{p.relative_to(out).as_posix():sha(p.read_bytes()) for p in out.rglob("*") if p.is_file()})
    print(json.dumps({"output":str(out),"seeds":summaries},indent=2))


if __name__ == "__main__":
    main()
