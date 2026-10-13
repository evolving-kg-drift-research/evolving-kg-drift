"""Read-only graph diagnostics; never train, select a population, or certify M1."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kg_pipeline.baseline import inspect_source_lock  # noqa: E402
from kg_pipeline.contract_authority import audit_machine_contract  # noqa: E402


def graph_summary(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], set[str], set[tuple[str, str, str]]]:
    triples = {(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows}
    entities = {e for s, _, o in triples for e in (s, o)}
    adjacent: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for subject, _, obj in triples:
        adjacent[subject].add(obj)
        adjacent[obj].add(subject)
        outgoing[subject].add(obj)
    remaining = set(entities)
    sizes = []
    while remaining:
        todo = [min(remaining)]
        remaining.remove(todo[0])
        size = 0
        while todo:
            current = todo.pop()
            size += 1
            unseen = adjacent[current] & remaining
            remaining.difference_update(unseen)
            todo.extend(unseen)
        sizes.append(size)
    paths = {(a, b, c) for a in entities for b in outgoing.get(a, ())
             for c in outgoing.get(b, ()) if len({a, b, c}) == 3}
    return {
        "rows": len(rows), "entities": len(entities), "unique_triples": len(triples),
        "repeated_triple_rows": len(rows) - len(triples),
        "relation_counts_unique_triples": dict(sorted(Counter(r for _, r, _ in triples).items())),
        "weak_components": len(sizes), "largest_component_entities": max(sizes, default=0),
        "undirected_neighbor_degree_histogram": dict(sorted(Counter(len(adjacent[e]) for e in entities).items())),
        "self_loop_triples": sum(s == o for s, _, o in triples),
        "directed_simple_two_hop_node_sequences": len(paths),
        "directed_two_hop_starts": len({a for a, _, _ in paths}),
    }, entities, triples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Previous audit reports are immutable; choose a new path")
    archive_bytes = args.zip.read_bytes()
    report: dict[str, Any] = {
        "package_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "scope": "descriptive graph feasibility only; no QA gold, model output, or gate certification",
        "path_definition": "directed 2-hop sequences of three distinct nodes; relation labels collapsed; not validated QA queries",
        "degree_definition": "distinct undirected neighbors; descriptive only, not registered null buckets",
        "source_lock": inspect_source_lock(ROOT),
        "machine_contract": audit_machine_contract(ROOT),
        "local_raw_files": sorted(str(p.relative_to(ROOT)) for p in (ROOT / "data/raw").iterdir() if p.is_file()),
        "local_runs_directory_present": (ROOT / "runs").exists(),
        "approved_baseline_file_present": (ROOT / "data/manifests/config_baseline.json").is_file(),
        "snapshots": [], "transitions": [],
    }
    first_entities: set[str] | None = None
    previous_entities: set[str] | None = None
    previous_triples: set[tuple[str, str, str]] | None = None
    previous_id = ""
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        names = sorted(n for n in archive.namelist() if n.startswith("snapshots/snapshot_T") and n.endswith(".parquet"))
        for name in names:
            rows = pq.read_table(pa.BufferReader(archive.read(name))).to_pylist()
            metrics, entities, triples = graph_summary(rows)
            snapshot_id = Path(name).stem.removeprefix("snapshot_")
            if first_entities is None:
                first_entities = entities
            metrics.update(snapshot_id=snapshot_id, entities_seen_at_T1=len(entities & first_entities))
            report["snapshots"].append(metrics)
            if previous_entities is not None and previous_triples is not None:
                report["transitions"].append({
                    "transition": f"{previous_id}->{snapshot_id}",
                    "persistent_entities": len(previous_entities & entities),
                    "new_entities": len(entities - previous_entities),
                    "disappeared_entities": len(previous_entities - entities),
                    "added_triples": len(triples - previous_triples),
                    "removed_triples": len(previous_triples - triples),
                })
            previous_entities, previous_triples, previous_id = entities, triples, snapshot_id
    refs = subprocess.check_output(["git", "for-each-ref", "--format=%(refname)", "refs/remotes/origin"], cwd=ROOT, text=True).splitlines()
    report["remote_refs"] = [{
        "ref": ref,
        "commit": subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip(),
        "committed_divergence_head_remote": subprocess.check_output(["git", "rev-list", "--left-right", "--count", f"HEAD...{ref}"], cwd=ROOT, text=True).strip(),
    } for ref in refs if not ref.endswith("/HEAD")]
    report["package_unchanged"] = hashlib.sha256(args.zip.read_bytes()).hexdigest() == report["package_sha256"]
    with args.report.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"report": str(args.report), "snapshots": report["snapshots"], "transitions": report["transitions"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
