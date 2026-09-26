import argparse
import html
import json
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/128 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def local_name(tag):
    """Bỏ namespace XML: {namespace}loc -> loc"""
    return tag.split("}")[-1].lower()


def normalize_text(text):
    if not text:
        return ""

    text = html.unescape(str(text))
    text = unicodedata.normalize("NFD", text)

    text = "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Mn"
    )

    return text.strip().lower()


def fetch_sitemap(session, sitemap_url):
    print("Fetching sitemap:")
    print(sitemap_url)

    response = session.get(
        sitemap_url,
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)

    rows = []

    for node in root.iter():
        if local_name(node.tag) != "url":
            continue

        row = {
            "url": None,
            "lastmod": None,
            "title": None,
        }

        # QUAN TRỌNG:
        # chỉ đọc các child trực tiếp của <url>
        # để không lấy nhầm <image:loc>
        for child in list(node):
            name = local_name(child.tag)
            value = (child.text or "").strip()

            if not value:
                continue

            if name == "loc":
                row["url"] = value

            elif name == "lastmod":
                row["lastmod"] = value

        # Title có thể nằm sâu trong news:news
        for descendant in node.iter():
            name = local_name(descendant.tag)

            if name != "title":
                continue

            value = (
                descendant.text or ""
            ).strip()

            if value:
                row["title"] = value
                break

        if row["url"]:
            rows.append(row)

    return rows

def walk_jsonld(obj):
    """Duyệt đệ quy JSON-LD để tìm BreadcrumbList."""

    if isinstance(obj, dict):
        obj_type = obj.get("@type")

        if obj_type == "BreadcrumbList":
            yield obj

        for value in obj.values():
            yield from walk_jsonld(value)

    elif isinstance(obj, list):
        for value in obj:
            yield from walk_jsonld(value)


def extract_section_from_breadcrumb(soup):
    """
    Trả về:
        section_name
        section_url
        breadcrumb_found
    """

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):
        raw = script.string or script.get_text()

        if not raw or not raw.strip():
            continue

        raw = html.unescape(raw)

        try:
            data = json.loads(raw)
        except Exception:
            continue

        for breadcrumb in walk_jsonld(data):
            items = breadcrumb.get(
                "itemListElement",
                [],
            )

            parsed = []

            for element in items:
                if not isinstance(element, dict):
                    continue

                position = element.get("position")

                item = element.get("item")

                name = None
                item_url = None

                if isinstance(item, dict):
                    name = item.get("name")
                    item_url = (
                        item.get("@id")
                        or item.get("url")
                    )

                elif isinstance(item, str):
                    item_url = item

                # Một số JSON-LD để name ngoài item
                if not name:
                    name = element.get("name")

                parsed.append(
                    {
                        "position": position,
                        "name": html.unescape(name)
                        if name
                        else None,
                        "url": item_url,
                    }
                )

            if not parsed:
                continue

            parsed.sort(
                key=lambda x: (
                    x["position"]
                    if isinstance(
                        x["position"],
                        int,
                    )
                    else 999
                )
            )

            # Ta đã thấy Tuổi Trẻ:
            # position 1 = Trang chủ
            # position 2 = Công nghệ / Thể thao / ...
            for item in parsed:
                if item["position"] == 2:
                    return (
                        item["name"],
                        item["url"],
                        True,
                    )

            # fallback: lấy item đầu tiên không phải Trang chủ
            for item in parsed:
                name_norm = normalize_text(
                    item["name"]
                )

                if name_norm not in {
                    "",
                    "trang chu",
                }:
                    return (
                        item["name"],
                        item["url"],
                        True,
                    )

            return None, None, True

    return None, None, False


def is_technology_section(section_name, section_url):
    """
    Chỉ dùng taxonomy của publisher.
    Không dùng title/tag/keyword bài báo.
    """

    name_norm = normalize_text(section_name)

    if name_norm == "cong nghe":
        return True

    if section_url:
        try:
            path = urlparse(section_url).path.lower()

            if path == "/cong-nghe.htm":
                return True

            if path.startswith("/cong-nghe/"):
                return True

        except Exception:
            pass

    return False


def inspect_article(session, row):
    url = row["url"]

    result = {
        "url": url,
        "sitemap_lastmod": row.get("lastmod"),
        "sitemap_title": row.get("title"),
        "retrieved_at_real": datetime.now(
            timezone.utc
        ).isoformat(),
        "http_status": None,
        "final_url": None,
        "breadcrumb_found": False,
        "section_name": None,
        "section_url": None,
        "is_technology": False,
        "error": None,
    }

    try:
        response = session.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        result["http_status"] = response.status_code
        result["final_url"] = response.url

        if response.status_code != 200:
            result["error"] = (
                f"http_{response.status_code}"
            )
            return result

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        (
            section_name,
            section_url,
            breadcrumb_found,
        ) = extract_section_from_breadcrumb(soup)

        result["breadcrumb_found"] = (
            breadcrumb_found
        )
        result["section_name"] = section_name
        result["section_url"] = section_url

        result["is_technology"] = (
            is_technology_section(
                section_name,
                section_url,
            )
        )

    except requests.RequestException as exc:
        result["error"] = (
            f"request_error:{type(exc).__name__}"
        )

    except Exception as exc:
        result["error"] = (
            f"parse_error:{type(exc).__name__}"
        )

    return result


def print_summary(results):
    total = len(results)

    http_ok = sum(
        r["http_status"] == 200
        for r in results
    )

    breadcrumb_found = sum(
        bool(r["breadcrumb_found"])
        for r in results
    )

    technology = sum(
        bool(r["is_technology"])
        for r in results
    )

    errors = sum(
        bool(r["error"])
        for r in results
    )

    non_technology = sum(
        r["http_status"] == 200
        and r["breadcrumb_found"]
        and not r["is_technology"]
        for r in results
    )

    print("\n" + "=" * 70)
    print("PILOT SUMMARY")
    print("=" * 70)

    print(f"TOTAL URLS           : {total}")
    print(f"HTTP 200             : {http_ok}")
    print(
        f"BREADCRUMB FOUND     : "
        f"{breadcrumb_found}"
    )
    print(f"TECHNOLOGY           : {technology}")
    print(
        f"NON-TECHNOLOGY       : "
        f"{non_technology}"
    )
    print(f"ERRORS               : {errors}")

    if total:
        print(
            "TECH / TOTAL         : "
            f"{technology / total:.2%}"
        )

    if http_ok:
        print(
            "BREADCRUMB / HTTP OK : "
            f"{breadcrumb_found / http_ok:.2%}"
        )

    if breadcrumb_found:
        print(
            "TECH / CLASSIFIED    : "
            f"{technology / breadcrumb_found:.2%}"
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "sitemap_url",
        help="URL của 1 static sitemap Tuổi Trẻ",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Chỉ xử lý N URL đầu để test",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0.7,
        help="Delay giữa requests, mặc định 0.7 giây",
    )

    args = parser.parse_args()

    output_dir = Path(
        "data/pilot/tuoitre"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "sitemap_category_pilot.jsonl"
    )

    session = requests.Session()

    rows = fetch_sitemap(
        session,
        args.sitemap_url,
    )

    print(f"\nURLs IN SITEMAP: {len(rows)}")

    if args.limit is not None:
        rows = rows[:args.limit]
        print(f"PILOT LIMIT: {len(rows)}")

    results = []

    with output_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        for index, row in enumerate(
            rows,
            start=1,
        ):
            print(
                f"[{index}/{len(rows)}] "
                f"{row['url']}"
            )

            result = inspect_article(
                session,
                row,
            )

            results.append(result)

            f.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                + "\n"
            )

            section = (
                result["section_name"]
                or "UNKNOWN"
            )

            print(
                f"    status="
                f"{result['http_status']} "
                f"section={section!r} "
                f"tech="
                f"{result['is_technology']} "
                f"error="
                f"{result['error']}"
            )

            time.sleep(args.delay)

    print_summary(results)

    print("\nRESULT FILE:")
    print(output_file)


if __name__ == "__main__":
    main()