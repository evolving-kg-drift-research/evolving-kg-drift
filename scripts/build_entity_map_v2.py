"""S2: build entity_map_v2 (v1 entity id -> v2 id | BLOCK) plus review proposals.

Mapping = pure per-mention rules (src/kg_pipeline/entity_map_v2.py); it reads no downstream result.
Rules that need two mentions seen together are written to the review CSV only, never applied.
Writes a NEW directory; refuses to overwrite.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from inspect_m2_inputs import encode, provenance, sha, write_json  # noqa: E402
from kg_pipeline.entity_map_v2 import (  # noqa: E402
    ENTITY_MAP_VERSION, canonical_key, entity_id_v2, is_generic_mention,
)

ACRONYM = re.compile(r"^[A-Z][A-Z/\-]{1,9}$")
PAREN_TAIL = re.compile(r"\s*\(([^()]*)\)\s*$")
CORPORATE_WORDS = frozenset({"technology", "technologies", "platforms", "systems", "labs", "motors",
                             "electronics", "semiconductor", "semiconductors", "holdings", "international"})
HEX8 = re.compile(r"^ent_[0-9a-f]{8}$")


def v1_id(mention: str) -> str:
    import hashlib
    return "ent_" + hashlib.sha256(mention.strip().lower().encode()).hexdigest()[:8]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", default="data/evolving_kg_downstream_v3_1")
    ap.add_argument("--retimed", default="data/evolving_kg_downstream_v3_2")
    ap.add_argument("--out", default="data/entity_map_v2")
    args = ap.parse_args()
    package, retimed, out = ROOT / args.package, ROOT / args.retimed, ROOT / args.out
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {out}")

    claims = pq.read_table(package / "tables/extracted_claims.parquet").to_pandas()
    events = pq.read_table(package / "tables/kg_events.parquet").to_pandas()
    fv = pq.read_table(retimed / "tables/fact_versions_v3_2.parquet").to_pandas()
    needed = set(events.subject_id) | set(events.object_id)

    surfaces: dict[str, Counter] = defaultdict(Counter)
    for mention in pd.concat([claims.subject_mention, claims.object_mention]).astype(str):
        mention = mention.strip()
        if mention and mention != "None":
            surfaces[v1_id(mention)][mention] += 1
    missing = sorted(needed - set(surfaces))
    if missing:
        raise SystemExit(f"{len(missing)} v1 entity ids have no surface form (first: {missing[:3]})")

    first_time: dict[str, str] = {}
    for r in fv[fv.evidence_observed_at_v32.notna()].itertuples(index=False):
        for e in (r.subject_id, r.object_id):
            if e not in first_time or r.evidence_observed_at_v32 < first_time[e]:
                first_time[e] = r.evidence_observed_at_v32

    rows, conflicts = [], []
    for eid in sorted(needed):
        counts = surfaces[eid]
        primary = sorted(counts, key=lambda s: (-counts[s], len(s), s))[0]
        keys = {canonical_key(s) for s in counts}
        generic = is_generic_mention(primary)
        if len(keys) > 1 or any(is_generic_mention(s) != generic for s in counts):
            conflicts.append({"v1_entity_id": eid, "surfaces": sorted(counts)})
        key = canonical_key(primary)
        rows.append({"v1_entity_id": eid, "primary_surface": primary, "surface_forms": json.dumps(sorted(counts), ensure_ascii=False),
                     "canonical_key": key, "action": "BLOCK" if generic else "KEEP",
                     "block_reason": "GENERIC_MENTION" if generic else None,
                     "v2_entity_id": None if generic else entity_id_v2(key)})
    table = pd.DataFrame(rows)
    live = table[table.action == "KEEP"]
    size = live.groupby("v2_entity_id").v1_entity_id.transform("size")
    table.loc[live.index, "action"] = ["MERGE" if n > 1 else "KEEP" for n in size]
    collisions = live.groupby("v2_entity_id").canonical_key.nunique()
    if (collisions > 1).any():
        raise SystemExit("entity_id_v2 hash collision between distinct keys")

    # ---- proposals needing review (NOT applied) ----
    keyed = {r.v1_entity_id: r for r in table.itertuples(index=False)}
    by_key: dict[str, list[str]] = defaultdict(list)
    for r in table[table.action != "BLOCK"].itertuples(index=False):
        by_key[r.canonical_key].append(r.v1_entity_id)
    proposals: list[dict[str, object]] = []

    def add(kind: str, a: str, b: str | None, note: str) -> None:
        ra, rb = keyed[a], (keyed[b] if b else None)
        proposals.append({"kind": kind, "v1_id_a": a, "name_a": ra.primary_surface,
                          "first_seen_a": first_time.get(a), "v2_id_a": ra.v2_entity_id,
                          "v1_id_b": b, "name_b": rb.primary_surface if rb else None,
                          "first_seen_b": first_time.get(b) if b else None,
                          "v2_id_b": rb.v2_entity_id if rb else None, "note": note})

    for r in table[table.action != "BLOCK"].itertuples(index=False):
        for form in json.loads(r.surface_forms):
            m = PAREN_TAIL.search(form)
            if m and not any(c.isdigit() for c in m.group(1)):
                inner = m.group(1).strip()
                other = by_key.get(canonical_key(inner), [])
                if ACRONYM.match(inner) and other:
                    for o in other:
                        if o != r.v1_entity_id and keyed[o].v2_entity_id != r.v2_entity_id:
                            a_t, b_t = first_time.get(o), first_time.get(r.v1_entity_id)
                            note = "retroactive: acronym seen before the link became knowable" if (
                                a_t and b_t and a_t < b_t) else "acronym first seen after the link"
                            add("acronym_alias", o, r.v1_entity_id, f'link from "{form}"; {note}')
            if m and any(c.isdigit() for c in m.group(1)):
                base = canonical_key(form[: m.start()])
                for o in by_key.get(base, []):
                    if keyed[o].v2_entity_id != r.v2_entity_id:
                        add("code_in_parenthesis", r.v1_entity_id, o, "parenthetical has digits (model code or sub-unit); kept apart")
    keys = sorted(k for k in by_key if len(k) >= 8)
    for i, k in enumerate(keys):
        for j in range(i + 1, len(keys)):
            k2 = keys[j]
            if k2[:2] != k[:2] and k2[0] != k[0]:
                continue
            if abs(len(k) - len(k2)) <= 2 and difflib.SequenceMatcher(None, k, k2).ratio() >= 0.93:
                add("near_duplicate_key", by_key[k][0], by_key[k2][0], f'keys "{k}" vs "{k2}"')
    for k in by_key:
        parts = k.split(" ")
        if len(parts) > 1 and parts[-1] in CORPORATE_WORDS and " ".join(parts[:-1]) in by_key:
            add("corporate_suffix", by_key[k][0], by_key[" ".join(parts[:-1])][0], f'"{k}" extends "{" ".join(parts[:-1])}"')
    for r in table[table.action != "BLOCK"].itertuples(index=False):
        if r.primary_surface[:1].islower():
            add("lowercase_start_not_blocked", r.v1_entity_id, None, "review: brand name or descriptor?")

    out.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), out / "entity_map_v2.parquet", compression="snappy")
    pd.DataFrame(proposals).to_csv(out / "review_proposals.csv", index=False, encoding="utf-8-sig")
    live2 = table[table.action != "BLOCK"]
    report = {
        "entity_map_version": ENTITY_MAP_VERSION, "scientific_certification": False,
        "review_status": "PROPOSED_UNREVIEWED",
        "v1_entities": len(table), "blocked": int((table.action == "BLOCK").sum()),
        "v2_entities": int(live2.v2_entity_id.nunique()),
        "merged_away": int(len(live2) - live2.v2_entity_id.nunique()),
        "merge_groups": int((live2.groupby("v2_entity_id").size() > 1).sum()),
        "surface_conflicts_within_v1_id": conflicts,
        "proposals_by_kind": dict(Counter(p["kind"] for p in proposals)),
        "blocked_entities": [{"v1_entity_id": r.v1_entity_id, "name": r.primary_surface}
                             for r in table[table.action == "BLOCK"].itertuples(index=False)],
        "merge_groups_detail": [
            {"v2_entity_id": v2, "members": sorted(g.primary_surface)}
            for v2, g in live2.groupby("v2_entity_id") if len(g) > 1],
    }
    write_json(out / "mapping_report.json", report)
    manifest = {"artifact": "entity_map_v2", "created_at_real": datetime.now(timezone.utc).isoformat(),
                "git": provenance(), "inputs": {
                    "extracted_claims": sha((package / "tables/extracted_claims.parquet").read_bytes()),
                    "kg_events": sha((package / "tables/kg_events.parquet").read_bytes()),
                    "fact_versions_v3_2": sha((retimed / "tables/fact_versions_v3_2.parquet").read_bytes()),
                    "rules_module": sha((ROOT / "src/kg_pipeline/entity_map_v2.py").read_bytes()),
                    "script": sha(Path(__file__).read_bytes())},
                "outputs": {n: sha((out / n).read_bytes()) for n in ("entity_map_v2.parquet", "review_proposals.csv", "mapping_report.json")}}
    manifest["manifest_hash"] = sha(encode(manifest["outputs"]))
    write_json(out / "manifest.json", manifest)
    print(json.dumps({k: v for k, v in report.items() if k not in ("blocked_entities", "merge_groups_detail")},
                     indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
