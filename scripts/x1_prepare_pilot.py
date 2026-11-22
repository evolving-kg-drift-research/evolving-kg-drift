"""X1 pilot: build the sampling frames, draw the gold/dev samples and export article texts.

No network, no LLM, no annotation. Follows configs/x1_reextraction_pilot_v34.yaml; reads the v3.1 package read-only.
Output: outputs/x1_reextraction_pilot/<utc>_<config sha8>/ (refuses to overwrite).
"""

from __future__ import annotations

import csv
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from drift.fixed_anchors import largest_remainder_allocation  # noqa: E402
from inspect_m2_inputs import provenance, sha, write_json  # noqa: E402
from kg_pipeline.tuoitre_parser_v2 import PARSER_VERSION, ParseError, matches_domain_keywords, parse_tuoitre  # noqa: E402

CONFIG = ROOT / "configs/x1_reextraction_pilot_v34.yaml"
PACKAGE = ROOT / "data/evolving_kg_downstream_v3_1"
TABLES = ("body_variants", "filter_decisions", "source_versions", "raw_inventory", "document_memberships")
GOLD = {"vnexpress": 40, "tuoitre": 10}
DEV = {"vnexpress": 8, "tuoitre": 2}


def order_key(item_id: str) -> str:
    return hashlib.sha256(f"x1_pilot_v1|{item_id}".encode()).hexdigest()


def tertile(lengths: pd.Series) -> tuple[pd.Series, list[float]]:
    cuts = [float(q) for q in np.quantile(lengths, [1 / 3, 2 / 3])]
    return pd.Series(np.select([lengths <= cuts[0], lengths <= cuts[1]], [0, 1], 2), index=lengths.index), cuts


def draw(frame: pd.DataFrame, n_gold: int, n_dev: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Largest-remainder allocation over tertiles; gold = first ids by order_key, dev = the next ones."""
    counts = {int(k): int(v) for k, v in frame.tertile.value_counts().items()}
    gold_n = largest_remainder_allocation(counts, n_gold)
    dev_n = largest_remainder_allocation(counts, n_dev)
    gold, dev = [], []
    for t, group in frame.sort_values("order_key").groupby("tertile"):
        if gold_n[int(t)] + dev_n[int(t)] > len(group):
            raise ValueError("Stratum too small for gold + dev")
        gold.append(group.iloc[: gold_n[int(t)]])
        dev.append(group.iloc[gold_n[int(t)]: gold_n[int(t)] + dev_n[int(t)]])
    return pd.concat(gold), pd.concat(dev)


def main() -> int:
    config_bytes = CONFIG.read_bytes()
    policy = yaml.safe_load((ROOT / "config/filter_policy_v1.yaml").read_bytes())
    keywords, window = policy["domain_keywords"], policy["time_window"]
    start, end = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
    t = {n: pq.read_table(PACKAGE / f"tables/{n}.parquet").to_pandas() for n in TABLES}

    # VnExpress frame: the v3.1 filter decision as-is (registered).
    bv = t["body_variants"].merge(t["filter_decisions"][["body_variant_id", "decision"]], on="body_variant_id")
    src = (t["document_memberships"][["body_variant_id", "raw_blob_sha256"]]
           .merge(t["source_versions"][["raw_blob_sha256", "source_id"]].dropna().drop_duplicates(), on="raw_blob_sha256")
           .groupby("body_variant_id").source_id.agg(lambda s: "|".join(sorted(set(s)))))
    bv["source_id"] = bv.body_variant_id.map(src)
    long_vne = bv[(bv.text_char_count >= 200) & (bv.source_id == "vnexpress_sohoa")].copy()
    long_vne["text"] = [(PACKAGE / p).read_text(encoding="utf-8") for p in long_vne.body_blob_relative_path]
    long_vne["keyword_match"] = [bool(matches_domain_keywords(x, keywords)) for x in long_vne.text]
    agreement = pd.crosstab(long_vne.decision, long_vne.keyword_match).to_dict()
    vne = long_vne[long_vne.decision == "include"].copy()
    vne["item_id"], vne["source"], vne["chars"] = vne.body_variant_id, "vnexpress", vne.text_char_count
    vne["tertile"], vne_cuts = tertile(vne.chars)

    # Tuoi Tre frame: parser v2 on every distinct raw page; exclusions keep a reason.
    pages = (t["source_versions"][t["source_versions"].source_id == "tuoitre_congnghe"]
             .drop_duplicates("raw_blob_sha256")
             .merge(t["raw_inventory"][["raw_blob_sha256", "relative_path"]], on="raw_blob_sha256"))
    rows, excluded = [], {}
    for page in pages.sort_values("raw_blob_sha256").itertuples():
        try:
            parsed = parse_tuoitre((ROOT / page.relative_path).read_bytes().decode("utf-8"))
        except (ParseError, UnicodeDecodeError) as exc:
            excluded[page.raw_blob_sha256] = str(exc)
            continue
        day = datetime.fromisoformat(parsed["published_at"]).date()  # publisher offset (+07:00) kept
        reason = ("OUTSIDE_TIME_WINDOW" if not start <= day <= end else
                  "TEXT_LT_200_CHARS" if len(parsed["text"]) < 200 else
                  "NO_DOMAIN_KEYWORD" if not matches_domain_keywords(parsed["text"], keywords) else None)
        if reason:
            excluded[page.raw_blob_sha256] = reason
            continue
        rows.append({"item_id": f"tuoitre_v2:{page.raw_blob_sha256}", "raw_blob_sha256": page.raw_blob_sha256,
                     "url": page.canonical_or_final_url, "published_at": parsed["published_at"],
                     "text": parsed["text"], "chars": len(parsed["text"])})
    tt = pd.DataFrame(rows)
    tt["text_sha256"] = [sha(x.encode()) for x in tt.text]
    dup = tt.duplicated("text_sha256", keep="first")  # rows are sorted by raw_blob_sha256
    excluded.update({r: "DUPLICATE_TEXT" for r in tt[dup].raw_blob_sha256})
    tt = tt[~dup].copy()
    tt["source"] = "tuoitre"
    tt["tertile"], tt_cuts = tertile(tt.chars)

    samples = {}
    for name, frame in (("vnexpress", vne), ("tuoitre", tt)):
        frame["order_key"] = frame.item_id.map(order_key)
        frame["text_sha256"] = [sha(x.encode()) for x in frame.text]
        samples[name] = draw(frame, GOLD[name], DEV[name])
    gold = pd.concat([samples[s][0] for s in GOLD]).sort_values("order_key").reset_index(drop=True)
    dev = pd.concat([samples[s][1] for s in DEV]).sort_values("order_key").reset_index(drop=True)
    assert len(gold) == 50 and len(dev) == 10 and not set(gold.item_id) & set(dev.item_id)
    gold["file"] = [f"gold/G{i + 1:02d}.txt" for i in range(len(gold))]
    dev["file"] = [f"dev/D{i + 1:02d}.txt" for i in range(len(dev))]

    config_sha = sha(config_bytes)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "outputs/x1_reextraction_pilot" / f"{stamp}_{config_sha[:8]}"
    (out / "gold").mkdir(parents=True)
    (out / "dev").mkdir()
    for df in (gold, dev):
        for r in df.itertuples():
            (out / r.file).write_bytes(r.text.encode("utf-8"))
    def listing(df: pd.DataFrame) -> list[dict[str, object]]:
        return [{"item_id": r.item_id, "source": r.source, "tertile": int(r.tertile), "chars": int(r.chars),
                 "order_key": r.order_key, "text_sha256": r.text_sha256, "file": r.file,
                 "published_at": r.published_at if isinstance(r.published_at, str) else None}
                for r in df.itertuples()]

    sample = {"config_sha256": config_sha, "parser_version": PARSER_VERSION,
              "frames": {"vnexpress": {"n": len(vne), "tertile_cuts_chars": vne_cuts},
                         "tuoitre": {"n_pages": len(pages), "n": len(tt), "tertile_cuts_chars": tt_cuts}},
              "gold": listing(gold), "dev": listing(dev)}
    write_json(out / "sample_manifest.json", sample)
    reasons = pd.Series(excluded).value_counts().to_dict()
    write_json(out / "frame_report.json", {
        "tuoitre_exclusions_by_reason": {k: int(v) for k, v in reasons.items()},
        "tuoitre_exclusions": dict(sorted(excluded.items())),
        "vnexpress_v31_decision_vs_keyword_rule": {str(k): {str(a): int(b) for a, b in v.items()}
                                                   for k, v in agreement.items()}})
    with (out / "gold_template.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["article_id", "file", "subject", "relation", "object", "evidence_text",
                         "is_speculative", "is_negative", "note"])
        for r in gold.itertuples():
            writer.writerow([r.item_id, r.file, "", "", "", "", "", "", ""])
    inputs = {str(CONFIG.relative_to(ROOT)): config_sha,
              **{f"tables/{n}.parquet": sha((PACKAGE / f"tables/{n}.parquet").read_bytes()) for n in TABLES}}
    outputs = {p.relative_to(out).as_posix(): sha(p.read_bytes()) for p in sorted(out.rglob("*")) if p.is_file()}
    write_json(out / "run_manifest.json", {"stage": "x1_pilot_sampling", "created_at": stamp, **provenance(),
                                           "config_hash": config_sha, "inputs": inputs, "outputs": outputs,
                                           "seed": "sha256 order key 'x1_pilot_v1|<id>' (no RNG)"})
    print(out.relative_to(ROOT).as_posix())
    print(f"frames: vnexpress {len(vne)}, tuoitre {len(tt)}/{len(pages)} pages; exclusions {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
