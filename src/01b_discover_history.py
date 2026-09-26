from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import json
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]

DISCOVERED_FILE = ROOT / "data" / "intermediate" / "discovered_urls.parquet"
ARCHIVE_FILE = ROOT / "data" / "intermediate" / "archive_candidates.parquet"
DISCOVERY_LOG = ROOT / "logs" / "discovery_log.jsonl"

START = "20250301"
END = "20260831"

# Các trang chuyên mục dùng để tìm article lịch sử.
# Đây là cấu hình triển khai, không phải yêu cầu nguyên văn của data001.
SECTION_PAGES = {
    "vnexpress_sohoa": [
        "https://vnexpress.net/so-hoa",
        "https://vnexpress.net/khoa-hoc-cong-nghe",
    ],
    "tuoitre_congnghe": [
        "https://tuoitre.vn/cong-nghe/nhip-song-so.htm",
    ],
}

CDX_URL = "https://web.archive.org/cdx/search/cdx"

HEADERS = {
    "User-Agent": "evolving-ai-kg-research/1.0"
}


def append_log(record):
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)

    with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_snapshots(source_id, section_url):
    params = {
        "url": section_url,
        "from": START,
        "to": END,
        "output": "json",
        "fl": "timestamp,original,statuscode,digest",
        "filter": "statuscode:200",
        # tối đa 1 archived state/ngày
        "collapse": "timestamp:8",
    }

    print(f"[CDX] {source_id}: {section_url}")

    r = requests.get(
        CDX_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()

    if len(data) <= 1:
        return []

    header = data[0]

    return [
        dict(zip(header, row))
        for row in data[1:]
    ]


def is_article_url(source_id, url):
    parsed = urlparse(url)

    if source_id == "vnexpress_sohoa":
        if parsed.netloc not in {"vnexpress.net", "www.vnexpress.net"}:
            return False

        return bool(
            re.search(r"-\d+\.html$", parsed.path)
        )

    if source_id == "tuoitre_congnghe":
        if parsed.netloc not in {"tuoitre.vn", "www.tuoitre.vn"}:
            return False

        return bool(
            re.search(r"-\d+\.htm$", parsed.path)
        )

    return False


def extract_articles(source_id, snapshot):
    timestamp = snapshot["timestamp"]
    original = snapshot["original"]

    archive_url = (
        f"https://web.archive.org/web/"
        f"{timestamp}id_/{original}"
    )

    try:
        r = requests.get(
            archive_url,
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] Cannot fetch {archive_url}: {e}")
        return [], archive_url

    soup = BeautifulSoup(r.text, "html.parser")

    urls = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()

        # URL tương đối → URL tuyệt đối theo trang gốc
        candidate = urljoin(original, href)

        # loại Wayback wrapper nếu có
        match = re.search(
            r"https?://web\.archive\.org/web/\d+(?:id_)?/(https?://.+)",
            candidate,
        )

        if match:
            candidate = match.group(1)

        candidate = candidate.split("#")[0]

        if is_article_url(source_id, candidate):
            urls.add(candidate)

    return sorted(urls), archive_url


def main():
    discovered_at = datetime.now(timezone.utc).isoformat()

    archive_rows = []
    discovered_rows = []

    for source_id, section_pages in SECTION_PAGES.items():

        for section_url in section_pages:

            try:
                snapshots = get_snapshots(
                    source_id,
                    section_url,
                )
            except Exception as e:
                print(
                    f"[WARN] CDX failed for "
                    f"{section_url}: {e}"
                )
                continue

            print(
                f"[OK] {len(snapshots)} archived "
                f"section snapshots"
            )

            for i, snapshot in enumerate(snapshots, start=1):

                timestamp = snapshot["timestamp"]

                articles, archive_url = extract_articles(
                    source_id,
                    snapshot,
                )

                archive_rows.append(
                    {
                        "source_id": source_id,
                        "section_url": section_url,
                        "archive_timestamp": timestamp,
                        "archive_url": archive_url,
                        "original_url": snapshot["original"],
                        "digest": snapshot.get("digest"),
                        "articles_found": len(articles),
                        "discovered_at_real": discovered_at,
                    }
                )

                for url in articles:
                    discovered_rows.append(
                        {
                            "url": url,
                            "source_id": source_id,
                            "discovered_at_real": discovered_at,
                            "discovery_method": "wayback_section",
                            "source_declared_timestamp": None,
                            "rss_url": None,
                            "target_window_start": "2025-03-01",
                            "target_window_end": "2026-08-31",
                        }
                    )

                print(
                    f"    [{i}/{len(snapshots)}] "
                    f"{timestamp}: {len(articles)} URLs"
                )

                # tránh gửi request quá dày
                time.sleep(0.3)

            append_log(
                {
                    "source_id": source_id,
                    "section_url": section_url,
                    "discovery_method": "wayback_section",
                    "discovered_at_real": discovered_at,
                    "snapshots_found": len(snapshots),
                }
            )

    # --------------------------
    # archive_candidates.parquet
    # --------------------------
    archive_df = pd.DataFrame(archive_rows)

    ARCHIVE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    if not archive_df.empty:
        archive_df = archive_df.drop_duplicates(
            subset=[
                "source_id",
                "section_url",
                "archive_timestamp",
            ]
        )

        archive_df.to_parquet(
            ARCHIVE_FILE,
            index=False,
        )

    # --------------------------
    # discovered_urls.parquet
    # --------------------------
    historical_df = pd.DataFrame(discovered_rows)

    if not historical_df.empty:

        historical_df = historical_df.drop_duplicates(
            subset=["source_id", "url"]
        )

        if DISCOVERED_FILE.exists():
            old_df = pd.read_parquet(DISCOVERED_FILE)

            df = pd.concat(
                [old_df, historical_df],
                ignore_index=True,
            )
        else:
            df = historical_df

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
    print(f"[OK] Archive candidates: {ARCHIVE_FILE}")
    print(
        f"[OK] Historical URLs found: "
        f"{len(historical_df)}"
    )

    if DISCOVERED_FILE.exists():
        all_df = pd.read_parquet(DISCOVERED_FILE)
        print(
            f"[OK] Total discovered records: "
            f"{len(all_df)}"
        )

    print(f"[LOG] {DISCOVERY_LOG}")


if __name__ == "__main__":
    main()