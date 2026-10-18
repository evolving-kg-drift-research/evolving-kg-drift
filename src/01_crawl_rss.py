from pathlib import Path
from datetime import datetime, timezone
import json

import feedparser
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]

SOURCES_FILE = ROOT / "config" / "sources.yaml"
CORPUS_SCOPE_FILE = ROOT / "config" / "corpus_scope.yaml"

DISCOVERED_FILE = ROOT / "data" / "intermediate" / "discovered_urls.parquet"
DISCOVERY_LOG = ROOT / "logs" / "discovery_log.jsonl"


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def append_log(record):
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(record, ensure_ascii=False)
            + "\n"
        )


def main():
    sources_config = load_yaml(SOURCES_FILE)
    scope_config = load_yaml(CORPUS_SCOPE_FILE)

    start_date = scope_config["historical_window"]["start"]
    end_date = scope_config["historical_window"]["end"]

    discovered_at = datetime.now(
        timezone.utc
    ).isoformat()

    rows = []

    for source_key, source in sources_config["sources"].items():

        if not source.get("enabled", True):
            continue

        rss_url = source.get("rss")

        if not rss_url:
            continue

        print(f"[RSS] Reading {source['source_id']}")

        feed = feedparser.parse(rss_url)

        if feed.bozo:
            print(
                f"[WARN] RSS parse warning: "
                f"{source['source_id']}"
            )

        for entry in feed.entries:

            url = entry.get("link")

            if not url:
                continue

            declared_time = (
                entry.get("published")
                or entry.get("updated")
            )

            rows.append(
                {
                    "url": url,
                    "source_id": source["source_id"],
                    "discovered_at_real": discovered_at,
                    "discovery_method": "rss_current",
                    "source_declared_timestamp": declared_time,
                    "rss_url": rss_url,
                    "target_window_start": start_date,
                    "target_window_end": end_date,
                }
            )

        append_log(
            {
                "source_id": source["source_id"],
                "discovery_method": "rss_current",
                "rss_url": rss_url,
                "discovered_at_real": discovered_at,
                "entries_found": len(feed.entries),
            }
        )

    if not rows:
        print("[WARN] No URLs discovered.")
        return

    new_df = pd.DataFrame(rows)

    # loại URL trùng trong cùng lần discovery
    new_df = new_df.drop_duplicates(
        subset=["source_id", "url"]
    )

    # Discovery log/data phải có tính append-only.
    # Nếu file cũ tồn tại thì nối thêm, không ghi đè lịch sử.
    if DISCOVERED_FILE.exists():
        old_df = pd.read_parquet(DISCOVERED_FILE)

        df = pd.concat(
            [old_df, new_df],
            ignore_index=True
        )

        # Một URL có thể được thấy nhiều lần.
        # Giữ lần discovery đầu tiên theo source + method + URL.
        df = df.drop_duplicates(
            subset=[
                "source_id",
                "url",
                "discovery_method",
            ],
            keep="first",
        )
    else:
        df = new_df

    df = df.sort_values(
        [
            "source_id",
            "url",
            "discovered_at_real",
        ]
    ).reset_index(drop=True)

    DISCOVERED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_parquet(
        DISCOVERED_FILE,
        index=False,
        engine="pyarrow",
    )

    print(f"[OK] {DISCOVERED_FILE}")
    print(
        f"[OK] New RSS URLs this run: {len(new_df)}"
    )
    print(
        f"[OK] Total discovered URLs: {len(df)}"
    )
    print(f"[LOG] {DISCOVERY_LOG}")


if __name__ == "__main__":
    main()