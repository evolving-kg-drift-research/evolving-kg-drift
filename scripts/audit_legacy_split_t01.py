"""Descriptive T01 split feasibility; never trains or locks an evaluation split."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_legacy_transe_t01 import (  # noqa: E402
    EXPECTED_SHA256, INPUT, read_legacy_input, write_json,
)

Triple = tuple[str, str, str]


def coverage(rows: list[Triple]) -> tuple[Counter[str], Counter[str]]:
    entities: Counter[str] = Counter()
    relations: Counter[str] = Counter()
    for h, r, t in rows:
        entities.update({h, t})
        relations[r] += 1
    return entities, relations


def diagnostics(train: list[Triple], heldout: list[Triple]) -> dict[str, Any]:
    entities, relations = coverage(train)
    unseen_entities = {e for h, _, t in heldout for e in (h, t) if e not in entities}
    unseen_relations = {r for _, r, _ in heldout if r not in relations}
    pair_set = {frozenset((h, t)) for h, _, t in train}
    valid = [row for row in heldout if row[0] in entities and row[2] in entities and row[1] in relations]
    return {
        "train_triples": len(train), "heldout_triples": len(heldout),
        "train_entities": len(entities), "train_relations": len(relations),
        "unseen_entities": sorted(unseen_entities), "unseen_relations": sorted(unseen_relations),
        "fully_seen_heldout_triples": len(valid),
        "entity_oov_triples": sum(h not in entities or t not in entities for h, _, t in heldout),
        "relation_oov_triples": sum(r not in relations for _, r, _ in heldout),
        "heldout_relation_counts": dict(sorted(Counter(r for _, r, _ in heldout).items())),
        "heldout_pairs_also_in_training": sum(frozenset((h, t)) in pair_set for h, _, t in heldout),
        "partition_disjoint": not (set(train) & set(heldout)),
    }


def audit(rows: list[Triple]) -> dict[str, Any]:
    if not rows or len(rows) != len(set(rows)):
        raise ValueError("Expected nonempty unique triples")
    rows = sorted(rows)
    entities, relations = coverage(rows)
    eligible = [row for row in rows if all(entities[e] > 1 for e in {row[0], row[2]})
                and relations[row[1]] > 1]
    # Fixed outcome-blind order; this greedy witness is not an optimal split.
    order = sorted(rows, key=lambda row: hashlib.sha256(
        json.dumps(["legacy-t01-feasibility-v1", *row], ensure_ascii=False).encode()).digest())
    counts, relation_counts = coverage(rows)
    heldout: list[Triple] = []
    for row in order:
        h, r, t = row
        if all(counts[e] > 1 for e in {h, t}) and relation_counts[r] > 1:
            heldout.append(row)
            counts.subtract({e: 1 for e in {h, t}})
            relation_counts[r] -= 1
    chosen = set(heldout)
    train = [row for row in rows if row not in chosen]
    mapping = {e: i for i, e in enumerate(sorted(entities))}
    relation_mapping = {r: i for i, r in enumerate(sorted(relations))}
    naive = []
    # Reproduce the current trainer's hash split at a diagnostic 20% ratio.
    for row in rows:
        h, r, t = row
        token = f"{mapping[h]}_{relation_mapping[r]}_{mapping[t]}"
        if int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) < int(0.2 * 0xFFFFFFFF):
            naive.append(row)
    naive_set = set(naive)
    return {
        "scope": "descriptive feasibility only; no final split approval, training or QA selection",
        "triples": len(rows), "entities": len(entities), "relations": len(relations),
        "entity_triple_incidence_histogram": dict(sorted(Counter(entities.values()).items())),
        "individually_holdout_eligible": len(eligible),
        "ineligible_due_to_single_incidence_entity": sum(any(entities[e] == 1 for e in {h, t}) for h, _, t in rows),
        "eligible_relation_counts": dict(sorted(Counter(r for _, r, _ in eligible).items())),
        "naive_trainer_hash_20_percent": diagnostics([row for row in rows if row not in naive_set], naive),
        "coverage_preserving_greedy_witness": diagnostics(train, heldout),
        "witness_train": train, "witness_heldout": heldout,
        "limits": ["Greedy witness is not maximum-cardinality proof",
                   "Coverage-preserving subset favors repeated entities; not representative of all triples",
                   "Numeric mappings for actual training must be constructed from training only",
                   "No split has been approved for evaluation; no model outcomes read"],
    }


def main() -> None:
    dataset = read_legacy_input(ROOT / INPUT, EXPECTED_SHA256)
    rows = [t.to_tuple() for t in dataset.triples]
    report = audit(rows)
    if report != audit(list(reversed(rows))):
        raise ValueError("Audit depends on input row order")
    witness = report["coverage_preserving_greedy_witness"]
    if (witness["unseen_entities"] or witness["unseen_relations"]
            or not witness["partition_disjoint"]
            or set(map(tuple, report["witness_train"] + report["witness_heldout"])) != set(rows)):
        raise ValueError("Invalid coverage-preserving witness")
    report["input_sha256"] = EXPECTED_SHA256
    report["verification"] = {"row_order_independent": True, "witness_partition_checked": True,
                              "input_unchanged": hashlib.sha256((ROOT / INPUT).read_bytes()).hexdigest() == EXPECTED_SHA256}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    out = ROOT / "outputs/legacy_split_audit" / run_id
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "report.json", report)
    print(json.dumps({"output": str(out), **{k:v for k,v in report.items()
                                           if k not in ("witness_train", "witness_heldout")}}, indent=2))


if __name__ == "__main__":
    main()
