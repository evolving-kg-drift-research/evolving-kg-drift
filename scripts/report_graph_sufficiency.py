"""S2: structural sufficiency of a snapshot package (outcome-blind; graph structure only).

Reports degree/connectivity, persistent anchors per pre-transition degree bucket (M2 bins <3, 3-5, >=6)
and how many multi-hop (2/3) query candidates exist per snapshot cohort. It trains nothing and reads no
embedding, drift, RR, MRR or QA result, so it cannot influence upstream choices (INV-06).
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_m2_inputs import write_json  # noqa: E402

BUCKETS = (("deg<3", 0, 2), ("deg3-5", 3, 5), ("deg>=6", 6, 10**9))
PER_HEAD_CAPS = (1, 3, 5)


def components(triples: set[tuple[str, str, str]]) -> list[int]:
    adj: dict[str, set[str]] = defaultdict(set)
    for h, _, t in triples:
        adj[h].add(t)
        adj[t].add(h)
    seen: set[str] = set()
    sizes = []
    for start in adj:
        if start in seen:
            continue
        stack, n = [start], 0
        seen.add(start)
        while stack:
            node = stack.pop()
            n += 1
            for nxt in adj[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        sizes.append(n)
    return sorted(sizes, reverse=True)


def paths(triples: set[tuple[str, str, str]]) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    """Directed 2- and 3-hop paths without shortcut, repeated node or self return."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    linked: set[tuple[str, str]] = set()
    for h, r, t in triples:
        out[h].append((r, t))
        linked.update({(h, t), (t, h)})
    two: set[tuple[str, ...]] = set()
    three: set[tuple[str, ...]] = set()
    for h in out:
        for r1, m in out[h]:
            for r2, t in out.get(m, []):
                if t in (h, m) or (h, t) in linked:
                    continue
                two.add((h, r1, m, r2, t))
                for r3, u in out.get(t, []):
                    if u in (h, m, t) or (h, u) in linked:
                        continue
                    three.add((h, r1, m, r2, t, r3, u))
    return two, three


def capped(path_set: set[tuple[str, ...]], cap: int) -> int:
    per_head = Counter(p[0] for p in path_set)
    return sum(min(n, cap) for n in per_head.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", default="data/evolving_kg_downstream_v3_3")
    args = ap.parse_args()
    pkg = ROOT / args.package
    cfg = yaml.safe_load((pkg / "config/downstream_transe_config.yaml").read_bytes())
    snaps: dict[str, set[tuple[str, str, str]]] = {}
    for spec in cfg["snapshots"]:
        rows = pq.read_table(pkg / spec["parquet_path"]).to_pylist()
        snaps[spec["snapshot_id"]] = {(r["subject_id"], r["relation_id"], r["object_id"]) for r in rows}
    ids = list(snaps)

    per_snapshot, path_sets = [], {}
    for sid in ids:
        triples = snaps[sid]
        deg = Counter([h for h, _, _ in triples] + [t for _, _, t in triples])
        comps = components(triples)
        two, three = paths(triples)
        path_sets[sid] = (two, three)
        values = sorted(deg.values())
        per_snapshot.append({
            "snapshot_id": sid, "triples": len(triples), "entities": len(deg),
            "degree_median": values[len(values) // 2], "degree_max": values[-1],
            "share_degree_le2": round(sum(v <= 2 for v in values) / len(values), 3),
            "components": len(comps), "largest_component": comps[0],
            "isolated_edges": sum(c == 2 for c in comps),
            "paths_2hop": len(two), "paths_3hop": len(three),
            "relations": dict(Counter(r for _, r, _ in triples).most_common())})

    transitions = []
    for a, b in zip(ids, ids[1:]):
        deg_a = Counter([h for h, _, _ in snaps[a]] + [t for _, _, t in snaps[a]])
        persistent = set(deg_a) & ({h for h, _, _ in snaps[b]} | {t for _, _, t in snaps[b]})
        buckets = {name: sum(lo <= deg_a[e] <= hi for e in persistent) for name, lo, hi in BUCKETS}
        transitions.append({"transition": f"{a}->{b}", "persistent_anchors": len(persistent),
                            "by_pre_degree_bucket": buckets,
                            "added_triples": len(snaps[b] - snaps[a]), "removed_triples": len(snaps[a] - snaps[b])})

    cohorts, obs = [], {2: 0, 3: 0}
    obs_capped = {c: {2: 0, 3: 0} for c in PER_HEAD_CAPS}
    previous = (set(), set())
    for k, sid in enumerate(ids):
        two, three = path_sets[sid]
        new2, new3 = two - previous[0], three - previous[1]
        later = len(ids) - 1 - k  # number of transitions after entering at snapshot k
        cohorts.append({"cohort": sid, "new_2hop": len(new2), "new_3hop": len(new3), "transitions_observed": later})
        obs[2] += len(new2) * later
        obs[3] += len(new3) * later
        for c in PER_HEAD_CAPS:
            obs_capped[c][2] += capped(new2, c) * later
            obs_capped[c][3] += capped(new3, c) * later
        previous = (two, three)

    report = {
        "package": args.package, "release_id": cfg.get("release_id"),
        "entity_map_version": cfg.get("entity_map_version"), "scientific_certification": False,
        "note": "structure only; entry-snapshot shortcut filter; directed paths; paths persist because snapshots are append-only",
        "per_snapshot": per_snapshot, "transitions": transitions, "cohorts": cohorts,
        "panel_observations_query_x_transition": {
            "2hop_all": obs[2], "3hop_all": obs[3],
            "2hop_per_head_cap": {str(c): obs_capped[c][2] for c in PER_HEAD_CAPS},
            "3hop_per_head_cap": {str(c): obs_capped[c][3] for c in PER_HEAD_CAPS}},
        "mde_status": "NOT_COMPUTED: needs an outcome-variance estimate that cannot be taken from downstream results (INV-06)"}
    write_json(pkg / "reports/graph_sufficiency.json", report)
    print(f"{'snap':4} {'triples':>7} {'ents':>5} {'deg<=2':>6} {'comps':>5} {'largest':>7} {'2hop':>6} {'3hop':>6}")
    for r in per_snapshot:
        print(f"{r['snapshot_id']:4} {r['triples']:7} {r['entities']:5} {r['share_degree_le2']:6.2f} "
              f"{r['components']:5} {r['largest_component']:7} {r['paths_2hop']:6} {r['paths_3hop']:6}")
    print("anchors:", [(t["transition"], t["persistent_anchors"], t["by_pre_degree_bucket"]) for t in transitions[:2]], "...")
    print("panel observations:", report["panel_observations_query_x_transition"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
