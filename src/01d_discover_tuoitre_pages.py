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

DISCOVERED_FILE = (
    ROOT / "data" / "intermediate" / "discovered_urls.parquet"
)

DISCOVERY_LOG = ROOT / "logs" / "discovery_log.jsonl"

SOURCE_ID = "tuoitre_congnghe"

BASE_URL = "https://tuoitre.vn"

FIRST_PAGE = "https://tuoitre.vn/cong-nghe.htm"

PAGE_TEMPLATE = (
    "https://tuoitre.vn/cong-nghe/trang-{page}.htm"
)

MAX_PAGES = 200

SLEEP_SECONDS = 0.7

TARGET_START = "2025-03-01"
TARGET_END = "2026-08-31"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/128 Safari/537.36"
    )
}


def append_log(record):
    DISCOVERY_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        DISCOVERY_LOG,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            + "\n"
        )


def is_article_url(url):
    parsed = urlparse(url)

    host = parsed.netloc.lower()

    if host not in {
        "tuoitre.vn",
        "www.tuoitre.vn",
    }:
        return False

    path = parsed.path.lower()

    # Không lấy pagination/category URL.
    if "/trang-" in path:
        return False

    # Article Tuổi Trẻ hiện có numeric ID dài
    # ở cuối URL, ví dụ:
    # ...-100260808135310527.htm
    return bool(
        re.search(
            r"-\d{12,}\.htm$",
            path,
        )
    )


def extract_article_urls(html, page_url):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    urls = set()

    for tag in soup.find_all(
        "a",
        href=True,
    ):
        href = tag["href"].strip()

        if not href:
            continue

        url = urljoin(
            page_url,
            href,
        )

        url = url.split("#")[0]
        url = url.split("?")[0]

        if is_article_url(url):
            urls.add(url)

    return sorted(urls)


def fetch_page(page_number):
    if page_number == 1:
        url = FIRST_PAGE
    else:
        url = PAGE_TEMPLATE.format(
            page=page_number
        )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    print(
    f"[HTTP] requested={url} "
    f"final={response.url} "
    f"status={response.status_code}"
)

    response.raise_for_status()

    return url, response.text


def main():
    discovered_at = datetime.now(
        timezone.utc
    ).isoformat()

    rows = []

    seen_urls = set()

    consecutive_empty_pages = 0

    pages_success = 0
    pages_failed = 0

    for page_number in range(
        1,
        MAX_PAGES + 1,
    ):
        try:
            page_url, html = fetch_page(
                page_number
            )

        except requests.RequestException as e:
            print(
                f"[WARN] Page {page_number}: {e}"
            )

            pages_failed += 1

            time.sleep(
                SLEEP_SECONDS
            )

            continue

        articles = extract_article_urls(
            html,
            page_url,
        )

        new_articles = [
            url
            for url in articles
            if url not in seen_urls
        ]

        seen_urls.update(
            new_articles
        )

        print(
            f"[PAGE {page_number}] "
            f"{len(articles)} article URLs, "
            f"{len(new_articles)} new"
        )

        pages_success += 1

        if not new_articles:
            consecutive_empty_pages += 1
        else:
            consecutive_empty_pages = 0

        for url in new_articles:
            rows.append(
                {
                    "url": url,
                    "source_id": SOURCE_ID,
                    "discovered_at_real": discovered_at,
                    "discovery_method": (
                        "publisher_pagination"
                    ),
                    # Chưa dùng ngày suy ra từ URL.
                    # Publication timestamp sẽ lấy
                    # từ chính article ở bước fetch.
                    "source_declared_timestamp": None,
                    "rss_url": None,
                    "target_window_start": TARGET_START,
                    "target_window_end": TARGET_END,
                }
            )

        # Nếu 5 trang liên tục không có URL mới,
        # khả năng pagination đã hết / bị redirect.
        if consecutive_empty_pages >= 5:
            print(
                "[STOP] 5 consecutive pages "
                "without new article URLs."
            )
            break

        time.sleep(
            SLEEP_SECONDS
        )

    append_log(
        {
            "source_id": SOURCE_ID,
            "discovery_method": (
                "publisher_pagination"
            ),
            "discovered_at_real": discovered_at,
            "pages_success": pages_success,
            "pages_failed": pages_failed,
            "urls_found": len(rows),
            "max_pages": MAX_PAGES,
        }
    )

    if not rows:
        print(
            "[WARN] No Tuoi Tre historical "
            "URLs discovered."
        )
        return

    new_df = pd.DataFrame(
        rows
    )

    new_df = new_df.drop_duplicates(
        subset=[
            "source_id",
            "url",
        ]
    )

    if DISCOVERED_FILE.exists():

        old_df = pd.read_parquet(
            DISCOVERED_FILE
        )

        df = pd.concat(
            [
                old_df,
                new_df,
            ],
            ignore_index=True,
        )

    else:
        df = new_df

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
    ).reset_index(
        drop=True
    )

    DISCOVERED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_parquet(
        DISCOVERED_FILE,
        index=False,
    )

    print()
    print(
        f"[OK] Tuoi Tre pagination URLs: "
        f"{len(new_df)}"
    )

    print(
        f"[OK] Total discovery records: "
        f"{len(df)}"
    )

    print(
        f"[OK] Unique URLs overall: "
        f"{df['url'].nunique()}"
    )

    print(
        f"[LOG] {DISCOVERY_LOG}"
    )


if __name__ == "__main__":
    main()