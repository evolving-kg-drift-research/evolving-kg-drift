from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import yaml


ROOT = Path(__file__).resolve().parents[1]

SOURCES_FILE = ROOT / "config" / "sources.yaml"
DISCOVERED_FILE = ROOT / "data" / "intermediate" / "discovered_urls.parquet"
DISCOVERY_LOG = ROOT / "logs" / "discovery_log.jsonl"

START_DATE = pd.Timestamp("2025-03-01", tz="UTC")
END_DATE = pd.Timestamp("2026-08-31 23:59:59", tz="UTC")

HEADERS = {
    "User-Agent": "Mozilla/5.0 evolving-ai-kg research"
}

# Sitemap fallback dự kiến.
SITEMAP_CANDIDATES = {
    "vnexpress_sohoa": [
        "https://vnexpress.net/sitemap.xml",
    ],
    "tuoitre_congnghe": [
        "https://tuoitre.vn/sitemap.xml",
    ],
}


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def append_log(record):
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def clean_tag(tag):
    return tag.split("}")[-1]


def fetch_xml(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def parse_sitemap(url, visited=None, depth=0, max_depth=2):
    if visited is None:
        visited = set()

    if url in visited:
        return []

    if depth > max_depth:
        return []

    visited.add(url)

    try:
        content = fetch_xml(url)
        root = ET.fromstring(content)
    except Exception as e:
        print(f"[WARN] Sitemap failed: {url}")
        print(f"       {e}")
        return []

    root_type = clean_tag(root.tag)

    results = []

    # Sitemap index -> sitemap con
    if root_type == "sitemapindex":

        children = []

        for node in root:
            loc = None
            lastmod = None

            for child in node:
                tag = clean_tag(child.tag)

                if tag == "loc":
                    loc = child.text

                elif tag == "lastmod":
                    lastmod = child.text

            if loc:
                children.append((loc.strip(), lastmod))

        print(
            f"[INDEX] {url} -> "
            f"{len(children)} child sitemaps"
        )

        for child_url, lastmod in children:

            # Nếu sitemap con có lastmod thì dùng để
            # tránh tải những sitemap rõ ràng ngoài window.
            if lastmod:
                dt = pd.to_datetime(
                    lastmod,
                    errors="coerce",
                    utc=True,
                )

                if not pd.isna(dt):
                    # Cho phép sitemap nằm trong hoặc sát window
                    if dt < START_DATE - pd.Timedelta(days=60):
                        continue

            results.extend(
                parse_sitemap(
                    child_url,
                    visited=visited,
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )

    # Sitemap chứa URL
    elif root_type == "urlset":

        for node in root:
            loc = None
            lastmod = None

            for child in node:
                tag = clean_tag(child.tag)

                if tag == "loc":
                    loc = child.text

                elif tag == "lastmod":
                    lastmod = child.text

            if loc:
                results.append(
                    {
                        "url": loc.strip(),
                        "lastmod": lastmod,
                    }
                )

    return results


def valid_domain(source_id, url):
    host = urlparse(url).netloc.lower()

    if source_id == "vnexpress_sohoa":
        return host.endswith("vnexpress.net")

    if source_id == "tuoitre_congnghe":
        return host.endswith("tuoitre.vn")

    return False


def likely_article(source_id, url):
    path = urlparse(url).path.lower()

    if source_id == "vnexpress_sohoa":
        return path.endswith(".html")

    if source_id == "tuoitre_congnghe":
        return path.endswith(".htm")

    return False


def main():
    sources_config = load_yaml(SOURCES_FILE)

    discovered_at = datetime.now(
        timezone.utc
    ).isoformat()

    new_rows = []

    for source_id, sitemap_urls in SITEMAP_CANDIDATES.items():

        if source_id not in {
            x["source_id"]
            for x in sources_config["sources"].values()
        }:
            print(f"[SKIP] Unknown source: {source_id}")
            continue

        source_count = 0

        for sitemap_url in sitemap_urls:

            print(f"[SITEMAP] {source_id}: {sitemap_url}")

            items = parse_sitemap(sitemap_url)

            print(
                f"[INFO] Raw sitemap URLs: {len(items)}"
            )

            for item in items:

                url = item["url"]
                lastmod = item["lastmod"]

                if not valid_domain(source_id, url):
                    continue

                if not likely_article(source_id, url):
                    continue

                dt = pd.to_datetime(
                    lastmod,
                    errors="coerce",
                    utc=True,
                )

                # Nếu có lastmod thì lọc theo historical window.
                if not pd.isna(dt):

                    if dt < START_DATE or dt > END_DATE:
                        continue

                    declared_timestamp = dt.isoformat()

                else:
                    # Không có timestamp vẫn giữ URL để bước fetch
                    # sau kiểm tra publication date.
                    declared_timestamp = None

                new_rows.append(
                    {
                        "url": url,
                        "source_id": source_id,
                        "discovered_at_real": discovered_at,
                        "discovery_method": "sitemap",
                        "source_declared_timestamp": declared_timestamp,
                        "rss_url": None,
                        "target_window_start": "2025-03-01",
                        "target_window_end": "2026-08-31",
                    }
                )

                source_count += 1

        append_log(
            {
                "source_id": source_id,
                "discovery_method": "sitemap",
                "discovered_at_real": discovered_at,
                "urls_found": source_count,
            }
        )

        print(
            f"[OK] {source_id}: "
            f"{source_count} sitemap records"
        )

    if not new_rows:
        print("[WARN] No sitemap URLs discovered.")
        return

    new_df = pd.DataFrame(new_rows)

    new_df = new_df.drop_duplicates(
        subset=["source_id", "url"]
    )

    if DISCOVERED_FILE.exists():
        old_df = pd.read_parquet(DISCOVERED_FILE)

        df = pd.concat(
            [old_df, new_df],
            ignore_index=True,
        )
    else:
        df = new_df

    # Cùng URL có thể tồn tại ở RSS/Wayback/Sitemap.
    # Không xóa giữa các discovery_method vì cần provenance.
    df = df.drop_duplicates(
        subset=[
            "source_id",
            "url",
            "discovery_method",
        ],
        keep="first",
    )

    df = df.sort_values(
        [
            "source_id",
            "url",
            "discovery_method",
        ]
    ).reset_index(drop=True)

    df.to_parquet(
        DISCOVERED_FILE,
        index=False,
    )

    print()
    print(
        f"[OK] New sitemap records: {len(new_df)}"
    )
    print(
        f"[OK] Total discovery records: {len(df)}"
    )
    print(
        f"[OK] Unique URLs: {df['url'].nunique()}"
    )
    print(f"[LOG] {DISCOVERY_LOG}")


if __name__ == "__main__":
    main()