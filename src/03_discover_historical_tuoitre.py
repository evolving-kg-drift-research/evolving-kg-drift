from __future__ import annotations

import argparse
import html
import json
import re
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait,
)
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter


# ============================================================
# CONFIG
# ============================================================

DEFAULT_SITEMAP = (
    "https://tuoitre.vn/StaticSitemaps/"
    "sitemaps-2025-3-1-5.xml"
)

EXPECTED_DOMAIN = "tuoitre.vn"
EXPECTED_SECTION = "Công nghệ"

SOURCES_CONFIG = Path("config/sources.yaml")

TRANSIENT_HTTP_STATUS = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

_thread_local = threading.local()


# ============================================================
# TIME
# ============================================================

def utc_now() -> str:
    """
    Project/discovery time.

    Đây KHÔNG phải evidence_observed_at.
    """
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


# ============================================================
# GLOBAL RATE LIMITER
# ============================================================

class GlobalRateLimiter:
    """
    Giới hạn tổng tốc độ bắt đầu HTTP request
    trên toàn bộ worker.

    Ví dụ rate=3:
        tối đa khoảng 3 request được bắt đầu / giây.

    Nhiều request vẫn có thể chờ response đồng thời.
    """

    def __init__(
        self,
        rate_per_second: float,
    ):
        if rate_per_second < 0:
            raise ValueError(
                "rate_per_second phải >= 0"
            )

        self.rate = rate_per_second

        if rate_per_second == 0:
            self.interval = 0.0
        else:
            self.interval = (
                1.0 / rate_per_second
            )

        self.lock = threading.Lock()
        self.next_allowed = 0.0

    def acquire(self) -> None:
        if self.interval <= 0:
            return

        with self.lock:
            now = time.monotonic()

            wait_seconds = (
                self.next_allowed
                - now
            )

            if wait_seconds > 0:
                time.sleep(
                    wait_seconds
                )

            now = time.monotonic()

            self.next_allowed = (
                max(
                    self.next_allowed,
                    now,
                )
                + self.interval
            )


# ============================================================
# RUN CONTEXT
# ============================================================

def build_run_context(
    sitemap_url: str,
) -> dict:
    filename = Path(
        urlparse(
            sitemap_url
        ).path
    ).name

    match = re.fullmatch(
        r"sitemaps-"
        r"(\d{4})-"
        r"(\d{1,2})-"
        r"(\d{1,2})-"
        r"(\d{1,2})"
        r"\.xml",
        filename,
        flags=re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            "Tên sitemap không đúng format "
            "StaticSitemaps của Tuổi Trẻ: "
            f"{filename}"
        )

    year = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    day_start = int(
        match.group(3)
    )

    day_end = int(
        match.group(4)
    )

    label = (
        f"{year:04d}_"
        f"{month:02d}_"
        f"{day_start:02d}_"
        f"{day_end:02d}"
    )

    output_dir = (
        Path("data/discovery/pilot")
        / f"tuoitre_{label}"
    )

    return {
        "label": label,
        "output_dir": output_dir,
        "discovered_path": (
            output_dir
            / "discovered_urls.parquet"
        ),
        "archive_path": (
            output_dir
            / "archive_candidates.parquet"
        ),
        "log_path": (
            output_dir
            / "discovery_log.jsonl"
        ),
        "summary_path": (
            output_dir
            / "summary.json"
        ),
        "discovery_run_id": (
            f"pilot_tuoitre_{label}_v1"
        ),
    }


# ============================================================
# APPEND-ONLY LOG
# ============================================================

def append_log(
    log_path: Path,
    event: dict,
) -> None:
    """
    Hàm này chỉ được gọi từ main thread.
    """

    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with log_path.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                event,
                ensure_ascii=False,
            )
            + "\n"
        )


def load_log_state(
    log_path: Path,
):
    discovered = {}
    checked = {}

    if not log_path.exists():
        return discovered, checked

    with log_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                event = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            url = event.get(
                "url"
            )

            if not url:
                continue

            event_type = event.get(
                "event_type"
            )

            if (
                event_type
                == "url_discovered"
            ):
                discovered[url] = event

            elif (
                event_type
                == "article_checked"
            ):
                # Event cuối cùng là current state.
                checked[url] = event

    return discovered, checked


# ============================================================
# SOURCE REGISTRY
# ============================================================

def normalize_domain(
    value: str,
) -> str:
    value = str(
        value or ""
    ).strip().lower()

    value = value.removeprefix(
        "https://"
    )

    value = value.removeprefix(
        "http://"
    )

    value = value.removeprefix(
        "www."
    )

    return value.rstrip("/")


def get_source_id() -> str:
    if not SOURCES_CONFIG.exists():
        raise FileNotFoundError(
            f"Không tìm thấy "
            f"{SOURCES_CONFIG}"
        )

    with SOURCES_CONFIG.open(
        "r",
        encoding="utf-8",
    ) as f:
        config = (
            yaml.safe_load(f)
            or {}
        )

    sources = config.get(
        "sources",
        {},
    )

    if not isinstance(
        sources,
        dict,
    ):
        raise RuntimeError(
            "config/sources.yaml: "
            "'sources' phải là mapping."
        )

    source = sources.get(
        "tuoitre_congnghe"
    )

    if source is None:
        raise RuntimeError(
            "Không tìm thấy "
            "'tuoitre_congnghe'."
        )

    if not isinstance(
        source,
        dict,
    ):
        raise RuntimeError(
            "'tuoitre_congnghe' "
            "phải là mapping."
        )

    if not source.get(
        "enabled",
        True,
    ):
        raise RuntimeError(
            "'tuoitre_congnghe' "
            "đang disabled."
        )

    domain = normalize_domain(
        source.get(
            "domain",
            "",
        )
    )

    if domain != EXPECTED_DOMAIN:
        raise RuntimeError(
            "Domain không đúng. "
            f"Expected={EXPECTED_DOMAIN}, "
            f"actual={domain}"
        )

    source_id = source.get(
        "source_id"
    )

    if not source_id:
        raise RuntimeError(
            "'tuoitre_congnghe' "
            "thiếu source_id."
        )

    return str(
        source_id
    )


# ============================================================
# HTTP SESSION
# ============================================================

def build_session() -> requests.Session:
    """
    Không cấu hình automatic retry ở urllib3.

    Retry article được xử lý thủ công để
    mọi attempt đều đi qua global rate limiter.
    """

    session = requests.Session()

    adapter = HTTPAdapter(
        max_retries=0,
        pool_connections=4,
        pool_maxsize=4,
    )

    session.mount(
        "https://",
        adapter,
    )

    session.mount(
        "http://",
        adapter,
    )

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/128 Safari/537.36"
            ),
            "Accept-Language": (
                "vi-VN,vi;q=0.9,en;q=0.8"
            ),
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
    )

    return session


def get_worker_session() -> requests.Session:
    """
    Mỗi worker thread dùng Session riêng.

    requests.Session không được share trực tiếp
    giữa nhiều thread.
    """

    session = getattr(
        _thread_local,
        "session",
        None,
    )

    if session is None:
        session = build_session()
        _thread_local.session = session

    return session


# ============================================================
# SITEMAP XML
# ============================================================

def local_name(
    tag: str,
) -> str:
    if "}" in tag:
        return tag.split(
            "}",
            1,
        )[1]

    return tag


def child_text(
    node: ET.Element,
    wanted: str,
):
    for child in node:
        if (
            local_name(
                child.tag
            )
            == wanted
        ):
            if child.text:
                return (
                    child.text.strip()
                )

    return None


def parse_sitemap(
    xml_bytes: bytes,
):
    root = ET.fromstring(
        xml_bytes
    )

    rows = []

    for node in root.iter():
        if (
            local_name(
                node.tag
            )
            != "url"
        ):
            continue

        loc = child_text(
            node,
            "loc",
        )

        lastmod = child_text(
            node,
            "lastmod",
        )

        if not loc:
            continue

        rows.append(
            {
                "url": loc,
                "source_declared_timestamp": (
                    lastmod
                ),
            }
        )

    return rows


def download_and_parse_sitemap(
    url: str,
    max_attempts: int = 6,
):
    """
    Sitemap vẫn tải tuần tự vì chỉ có một file XML.
    """

    session = build_session()
    last_error = None

    try:
        for attempt in range(
            1,
            max_attempts + 1,
        ):
            print(
                "Sitemap download attempt "
                f"{attempt}/{max_attempts}..."
            )

            try:
                with session.get(
                    url,
                    timeout=(15, 90),
                    stream=True,
                ) as response:
                    response.raise_for_status()

                    chunks = []

                    for chunk in (
                        response.iter_content(
                            chunk_size=(
                                128 * 1024
                            )
                        )
                    ):
                        if chunk:
                            chunks.append(
                                chunk
                            )

                    xml_bytes = b"".join(
                        chunks
                    )

                if not xml_bytes:
                    raise RuntimeError(
                        "Sitemap response empty."
                    )

                rows = parse_sitemap(
                    xml_bytes
                )

                if not rows:
                    raise RuntimeError(
                        "Sitemap không có URL."
                    )

                print(
                    "Sitemap bytes:",
                    len(xml_bytes),
                )

                print(
                    "Sitemap URLs:",
                    len(rows),
                )

                return rows

            except (
                requests.exceptions.RequestException,
                ET.ParseError,
                RuntimeError,
            ) as exc:
                last_error = exc

                print(
                    "Sitemap attempt failed:",
                    type(exc).__name__,
                    str(exc),
                )

                if attempt < max_attempts:
                    wait_seconds = min(
                        2 ** (
                            attempt - 1
                        ),
                        10,
                    )

                    print(
                        "Retrying in "
                        f"{wait_seconds}s..."
                    )

                    time.sleep(
                        wait_seconds
                    )

    finally:
        session.close()

    raise RuntimeError(
        "Không thể tải sitemap "
        f"sau {max_attempts} lần."
    ) from last_error


# ============================================================
# JSON-LD
# ============================================================

def walk_json(value):
    if isinstance(
        value,
        dict,
    ):
        yield value

        for child in value.values():
            yield from walk_json(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for child in value:
            yield from walk_json(
                child
            )


def normalize_text(
    value: str,
) -> str:
    value = html.unescape(
        str(
            value or ""
        )
    )

    return " ".join(
        value.split()
    ).strip()


def get_meta(
    soup: BeautifulSoup,
    key: str,
):
    tag = soup.find(
        "meta",
        attrs={
            "property": key
        },
    )

    if tag is None:
        tag = soup.find(
            "meta",
            attrs={
                "name": key
            },
        )

    if tag:
        value = tag.get(
            "content"
        )

        if value:
            return normalize_text(
                value
            )

    return None


# ============================================================
# BREADCRUMB
# ============================================================

def extract_breadcrumb(
    soup: BeautifulSoup,
):
    names = []
    urls = []

    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    for script in scripts:
        raw = (
            script.string
            or script.get_text()
            or ""
        ).strip()

        if not raw:
            continue

        try:
            data = json.loads(
                raw
            )
        except Exception:
            continue

        for obj in walk_json(
            data
        ):
            obj_type = obj.get(
                "@type"
            )

            if isinstance(
                obj_type,
                list,
            ):
                types = {
                    str(x).lower()
                    for x
                    in obj_type
                }
            else:
                types = {
                    str(
                        obj_type
                    ).lower()
                }

            if (
                "breadcrumblist"
                not in types
            ):
                continue

            elements = obj.get(
                "itemListElement",
                [],
            )

            temp_names = []
            temp_urls = []

            for element in elements:
                if not isinstance(
                    element,
                    dict,
                ):
                    continue

                item = element.get(
                    "item"
                )

                name = element.get(
                    "name"
                )

                item_url = None

                if isinstance(
                    item,
                    dict,
                ):
                    name = (
                        item.get(
                            "name"
                        )
                        or name
                    )

                    item_url = (
                        item.get(
                            "@id"
                        )
                        or item.get(
                            "url"
                        )
                    )

                elif isinstance(
                    item,
                    str,
                ):
                    item_url = item

                if name:
                    temp_names.append(
                        normalize_text(
                            name
                        )
                    )

                if item_url:
                    temp_urls.append(
                        normalize_text(
                            item_url
                        )
                    )

            if temp_names:
                names = temp_names
                urls = temp_urls
                break

        if names:
            break

    return names, urls


def determine_section(
    names,
):
    if not names:
        return None

    if (
        len(names) >= 2
        and names[0].casefold()
        == "trang chủ".casefold()
    ):
        return names[1]

    return names[0]


def is_technology_section(
    names,
    urls,
) -> bool:
    expected = (
        EXPECTED_SECTION.casefold()
    )

    for name in names:
        if (
            normalize_text(
                name
            ).casefold()
            == expected
        ):
            return True

    for value in urls:
        try:
            path = urlparse(
                value
            ).path.lower()
        except Exception:
            continue

        if (
            path == "/cong-nghe.htm"
            or path.startswith(
                "/cong-nghe/"
            )
        ):
            return True

    return False


# ============================================================
# RETRY / BACKOFF
# ============================================================

def get_backoff_seconds(
    attempt: int,
    response=None,
) -> float:
    """
    Ưu tiên Retry-After nếu server cung cấp.
    """

    if response is not None:
        retry_after = response.headers.get(
            "Retry-After"
        )

        if retry_after:
            try:
                value = float(
                    retry_after
                )

                return min(
                    max(value, 1.0),
                    60.0,
                )
            except ValueError:
                pass

    return min(
        2 ** (
            attempt - 1
        ),
        10,
    )


# ============================================================
# ARTICLE WORKER
# ============================================================

def inspect_article(
    url: str,
    rate_limiter: GlobalRateLimiter,
    max_attempts: int,
):
    """
    Worker function.

    Worker:
      HTTP GET
      parse HTML
      parse breadcrumb
      return dict

    Worker KHÔNG ghi discovery_log.jsonl.
    """

    session = get_worker_session()

    last_error = None

    for attempt in range(
        1,
        max_attempts + 1,
    ):
        checked_at = utc_now()

        try:
            # Mọi network attempt đều phải
            # qua global rate limiter.
            rate_limiter.acquire()

            response = session.get(
                url,
                timeout=(15, 60),
            )

            status = (
                response.status_code
            )

            # --------------------------------------------
            # Success
            # --------------------------------------------

            if status == 200:
                try:
                    soup = BeautifulSoup(
                        response.text,
                        "html.parser",
                    )

                    (
                        names,
                        breadcrumb_urls,
                    ) = extract_breadcrumb(
                        soup
                    )

                    section = (
                        determine_section(
                            names
                        )
                    )

                    is_candidate = (
                        is_technology_section(
                            names,
                            breadcrumb_urls,
                        )
                    )

                    if names:
                        check_status = "ok"
                    else:
                        check_status = (
                            "no_breadcrumb"
                        )

                    return {
                        "event_type": (
                            "article_checked"
                        ),
                        "url": url,
                        "final_url": (
                            response.url
                        ),
                        "checked_at_real": (
                            checked_at
                        ),
                        "http_status": (
                            status
                        ),
                        "category_check_status": (
                            check_status
                        ),
                        "publisher_section": (
                            section
                        ),
                        "breadcrumb_path": (
                            " > ".join(names)
                            if names
                            else None
                        ),
                        "is_scope_candidate": (
                            is_candidate
                        ),
                        "published_at_declared": (
                            get_meta(
                                soup,
                                "article:published_time",
                            )
                        ),
                        "modified_at_declared": (
                            get_meta(
                                soup,
                                "article:modified_time",
                            )
                        ),
                        "request_attempts": (
                            attempt
                        ),
                        "error": None,
                    }

                except Exception as exc:
                    last_error = exc

                    # HTML có thể bị tải thiếu.
                    # Retry nếu còn attempt.
                    if attempt < max_attempts:
                        time.sleep(
                            get_backoff_seconds(
                                attempt
                            )
                        )
                        continue

                    return {
                        "event_type": (
                            "article_checked"
                        ),
                        "url": url,
                        "final_url": (
                            response.url
                        ),
                        "checked_at_real": (
                            checked_at
                        ),
                        "http_status": (
                            status
                        ),
                        "category_check_status": (
                            "parse_error"
                        ),
                        "publisher_section": None,
                        "breadcrumb_path": None,
                        "is_scope_candidate": False,
                        "published_at_declared": None,
                        "modified_at_declared": None,
                        "request_attempts": (
                            attempt
                        ),
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    }

            # --------------------------------------------
            # Transient HTTP
            # --------------------------------------------

            if (
                status
                in TRANSIENT_HTTP_STATUS
                and attempt
                < max_attempts
            ):
                time.sleep(
                    get_backoff_seconds(
                        attempt,
                        response,
                    )
                )

                continue

            # --------------------------------------------
            # Permanent / exhausted HTTP error
            # --------------------------------------------

            return {
                "event_type": (
                    "article_checked"
                ),
                "url": url,
                "final_url": (
                    response.url
                ),
                "checked_at_real": (
                    checked_at
                ),
                "http_status": (
                    status
                ),
                "category_check_status": (
                    "http_error"
                ),
                "publisher_section": None,
                "breadcrumb_path": None,
                "is_scope_candidate": False,
                "published_at_declared": None,
                "modified_at_declared": None,
                "request_attempts": (
                    attempt
                ),
                "error": (
                    f"HTTP {status}"
                ),
            }

        except (
            requests.exceptions.RequestException
        ) as exc:
            last_error = exc

            if attempt < max_attempts:
                time.sleep(
                    get_backoff_seconds(
                        attempt
                    )
                )

                continue

    return {
        "event_type": (
            "article_checked"
        ),
        "url": url,
        "final_url": None,
        "checked_at_real": (
            utc_now()
        ),
        "http_status": None,
        "category_check_status": (
            "request_error"
        ),
        "publisher_section": None,
        "breadcrumb_path": None,
        "is_scope_candidate": False,
        "published_at_declared": None,
        "modified_at_declared": None,
        "request_attempts": (
            max_attempts
        ),
        "error": (
            f"{type(last_error).__name__}: "
            f"{last_error}"
            if last_error
            else "Unknown request error"
        ),
    }


# ============================================================
# RESUME POLICY
# ============================================================

def needs_retry(
    url: str,
    checked_state: dict,
) -> bool:
    previous = checked_state.get(
        url
    )

    if previous is None:
        return True

    status = previous.get(
        "category_check_status"
    )

    http_status = previous.get(
        "http_status"
    )

    if status in {
        "request_error",
        "parse_error",
    }:
        return True

    if (
        status == "http_error"
        and http_status
        in TRANSIENT_HTTP_STATUS
    ):
        return True

    return False


# ============================================================
# DISCOVERED TABLE
# ============================================================

def build_discovered_dataframe(
    sitemap_rows,
    discovered_state,
    checked_state,
    source_id: str,
    sitemap_url: str,
    discovery_run_id: str,
):
    records = []

    for sitemap_row in sitemap_rows:
        url = sitemap_row[
            "url"
        ]

        discovered_event = (
            discovered_state.get(
                url,
                {},
            )
        )

        check = checked_state.get(
            url,
            {},
        )

        records.append(
            {
                "discovery_run_id": (
                    discovery_run_id
                ),
                "source_id": (
                    source_id
                ),
                "url": url,
                "final_url": (
                    check.get(
                        "final_url"
                    )
                ),
                "discovery_method": (
                    "publisher_static_sitemap"
                ),
                "sitemap_url": (
                    sitemap_url
                ),
                "discovered_at_real": (
                    discovered_event.get(
                        "discovered_at_real"
                    )
                ),
                "source_declared_timestamp": (
                    sitemap_row.get(
                        "source_declared_timestamp"
                    )
                ),
                "http_status": (
                    check.get(
                        "http_status"
                    )
                ),
                "category_check_status": (
                    check.get(
                        "category_check_status",
                        "pending",
                    )
                ),
                "publisher_section": (
                    check.get(
                        "publisher_section"
                    )
                ),
                "breadcrumb_path": (
                    check.get(
                        "breadcrumb_path"
                    )
                ),
                "is_scope_candidate": (
                    check.get(
                        "is_scope_candidate"
                    )
                ),
                "published_at_declared": (
                    check.get(
                        "published_at_declared"
                    )
                ),
                "modified_at_declared": (
                    check.get(
                        "modified_at_declared"
                    )
                ),
                "request_attempts": (
                    check.get(
                        "request_attempts"
                    )
                ),
                "error": (
                    check.get(
                        "error"
                    )
                ),
            }
        )

    return pd.DataFrame(
        records
    )


# ============================================================
# ARCHIVE CANDIDATES
# ============================================================

def write_archive_candidates(
    archive_path: Path,
):
    """
    Archive recovery sẽ được hoàn thiện riêng.

    Pilot hiện tại chỉ giữ schema artifact.
    """

    columns = [
        "discovery_run_id",
        "source_id",
        "url",
        "archive_uri",
        "archive_datetime",
        "discovery_method",
        "discovered_at_real",
    ]

    pd.DataFrame(
        columns=columns
    ).to_parquet(
        archive_path,
        index=False,
    )


# ============================================================
# SUMMARY
# ============================================================

def build_summary(
    discovered_df: pd.DataFrame,
    sitemap_url: str,
    sitemap_rows,
    source_id: str,
    discovery_run_id: str,
    workers: int,
    rate: float,
):
    checked_df = (
        discovered_df[
            discovered_df[
                "category_check_status"
            ]
            != "pending"
        ]
    )

    candidates = (
        checked_df[
            checked_df[
                "is_scope_candidate"
            ]
            == True
        ]
    )

    errors = (
        checked_df[
            checked_df[
                "category_check_status"
            ].isin(
                [
                    "http_error",
                    "request_error",
                ]
            )
        ]
    )

    no_breadcrumb = (
        checked_df[
            checked_df[
                "category_check_status"
            ]
            == "no_breadcrumb"
        ]
    )

    parse_errors = (
        checked_df[
            checked_df[
                "category_check_status"
            ]
            == "parse_error"
        ]
    )

    checked_count = len(
        checked_df
    )

    candidate_count = len(
        candidates
    )

    if checked_count:
        candidate_ratio = (
            candidate_count
            / checked_count
        )
    else:
        candidate_ratio = 0.0

    section_counts = {}

    if checked_count:
        section_series = (
            checked_df[
                "publisher_section"
            ]
            .fillna("<null>")
            .value_counts()
        )

        section_counts = {
            str(key): int(value)
            for key, value
            in section_series.items()
        }

    return {
        "discovery_run_id": (
            discovery_run_id
        ),
        "source_id": (
            source_id
        ),
        "sitemap_url": (
            sitemap_url
        ),
        "sitemap_url_count": (
            len(sitemap_rows)
        ),
        "checked_count": (
            checked_count
        ),
        "technology_candidate_count": (
            candidate_count
        ),
        "technology_candidate_ratio": (
            candidate_ratio
        ),
        "http_or_request_error_count": (
            len(errors)
        ),
        "no_breadcrumb_count": (
            len(no_breadcrumb)
        ),
        "parse_error_count": (
            len(parse_errors)
        ),
        "workers": (
            workers
        ),
        "global_rate_limit_rps": (
            rate
        ),
        "publisher_section_counts": (
            section_counts
        ),
        "generated_at_real": (
            utc_now()
        ),
    }


# ============================================================
# CONCURRENT EXECUTION
# ============================================================

def process_concurrently(
    pending_rows,
    workers: int,
    rate: float,
    max_attempts: int,
    progress_every: int,
    log_path: Path,
    checked_state: dict,
    discovery_run_id: str,
    source_id: str,
):
    """
    Worker chỉ GET + parse.

    Main thread:
        nhận result
        append log
        cập nhật state

    Không submit toàn bộ hàng chục nghìn Future
    cùng lúc. Chỉ giữ một lượng nhỏ Future
    đang in-flight.
    """

    total = len(
        pending_rows
    )

    if total == 0:
        return

    limiter = GlobalRateLimiter(
        rate
    )

    pending_iter = iter(
        pending_rows
    )

    completed = 0
    technology_count = 0
    error_count = 0
    no_breadcrumb_count = 0

    start_time = (
        time.monotonic()
    )

    # Tối đa khoảng 3 batch Future
    # cho mỗi worker.
    max_inflight = max(
        workers * 3,
        workers,
    )

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

        inflight = {}

        def submit_one() -> bool:
            try:
                row = next(
                    pending_iter
                )
            except StopIteration:
                return False

            url = row[
                "url"
            ]

            future = executor.submit(
                inspect_article,
                url,
                limiter,
                max_attempts,
            )

            inflight[
                future
            ] = url

            return True

        # Initial queue
        for _ in range(
            min(
                max_inflight,
                total,
            )
        ):
            if not submit_one():
                break

        while inflight:
            done, _ = wait(
                inflight,
                return_when=(
                    FIRST_COMPLETED
                ),
            )

            for future in done:
                url = inflight.pop(
                    future
                )

                try:
                    result = (
                        future.result()
                    )
                except Exception as exc:
                    # Safety net:
                    # worker exception vẫn được
                    # ghi provenance thay vì mất URL.
                    result = {
                        "event_type": (
                            "article_checked"
                        ),
                        "url": url,
                        "final_url": None,
                        "checked_at_real": (
                            utc_now()
                        ),
                        "http_status": None,
                        "category_check_status": (
                            "worker_error"
                        ),
                        "publisher_section": None,
                        "breadcrumb_path": None,
                        "is_scope_candidate": False,
                        "published_at_declared": None,
                        "modified_at_declared": None,
                        "request_attempts": None,
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    }

                result[
                    "discovery_run_id"
                ] = discovery_run_id

                result[
                    "source_id"
                ] = source_id

                # Chỉ MAIN THREAD ghi log.
                append_log(
                    log_path,
                    result,
                )

                checked_state[
                    url
                ] = result

                completed += 1

                status = result.get(
                    "category_check_status"
                )

                if result.get(
                    "is_scope_candidate"
                ):
                    technology_count += 1

                if status in {
                    "http_error",
                    "request_error",
                    "worker_error",
                    "parse_error",
                }:
                    error_count += 1

                if (
                    status
                    == "no_breadcrumb"
                ):
                    no_breadcrumb_count += 1

                # Giữ queue đầy nhưng có giới hạn.
                submit_one()

                should_print = (
                    completed == total
                    or (
                        progress_every > 0
                        and completed
                        % progress_every
                        == 0
                    )
                )

                if should_print:
                    elapsed = (
                        time.monotonic()
                        - start_time
                    )

                    if elapsed > 0:
                        throughput = (
                            completed
                            / elapsed
                        )
                    else:
                        throughput = 0.0

                    print(
                        "PROGRESS "
                        f"{completed}/{total}"
                        " | technology="
                        f"{technology_count}"
                        " | errors="
                        f"{error_count}"
                        " | no_breadcrumb="
                        f"{no_breadcrumb_count}"
                        " | throughput="
                        f"{throughput:.2f} url/s"
                    )


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Concurrent Tuoi Tre historical "
            "URL discovery using public sitemap "
            "+ public article HTML breadcrumb."
        )
    )

    parser.add_argument(
        "--sitemap",
        type=str,
        default=DEFAULT_SITEMAP,
        help=(
            "Static sitemap URL."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "Số URL tối đa. "
            "0 = toàn sitemap."
        ),
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help=(
            "Số worker concurrent. "
            "Khuyến nghị bắt đầu bằng 6."
        ),
    )

    parser.add_argument(
        "--rate",
        type=float,
        default=3.0,
        help=(
            "Global request starts / giây. "
            "Khuyến nghị bắt đầu bằng 3."
        ),
    )

    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help=(
            "Số attempt tối đa/article "
            "trong một lần chạy."
        ),
    )

    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help=(
            "In progress sau mỗi N URL."
        ),
    )

    args = parser.parse_args()

    if args.limit < 0:
        raise ValueError(
            "--limit phải >= 0"
        )

    if args.workers < 1:
        raise ValueError(
            "--workers phải >= 1"
        )

    if args.workers > 12:
        raise ValueError(
            "--workers > 12 không được "
            "khuyến nghị cho crawler này."
        )

    if args.rate < 0:
        raise ValueError(
            "--rate phải >= 0"
        )

    if args.attempts < 1:
        raise ValueError(
            "--attempts phải >= 1"
        )

    sitemap_url = (
        args.sitemap.strip()
    )

    context = build_run_context(
        sitemap_url
    )

    output_dir = (
        context[
            "output_dir"
        ]
    )

    discovered_path = (
        context[
            "discovered_path"
        ]
    )

    archive_path = (
        context[
            "archive_path"
        ]
    )

    log_path = (
        context[
            "log_path"
        ]
    )

    summary_path = (
        context[
            "summary_path"
        ]
    )

    discovery_run_id = (
        context[
            "discovery_run_id"
        ]
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_id = (
        get_source_id()
    )

    print(
        "SOURCE_ID:",
        source_id,
    )

    print(
        "DISCOVERY_RUN_ID:",
        discovery_run_id,
    )

    print(
        "SITEMAP:",
        sitemap_url,
    )

    print(
        "OUTPUT_DIR:",
        output_dir,
    )

    print(
        "WORKERS:",
        args.workers,
    )

    print(
        "GLOBAL RATE:",
        args.rate,
        "request starts/sec",
    )

    # --------------------------------------------------------
    # SITEMAP
    # --------------------------------------------------------

    print(
        "\nDownloading sitemap..."
    )

    sitemap_rows = (
        download_and_parse_sitemap(
            sitemap_url
        )
    )

    print(
        "URLs in sitemap:",
        len(sitemap_rows),
    )

    # --------------------------------------------------------
    # LOAD RESUME STATE
    # --------------------------------------------------------

    (
        discovered_state,
        checked_state,
    ) = load_log_state(
        log_path
    )

    # --------------------------------------------------------
    # APPEND DISCOVERY EVENTS
    # --------------------------------------------------------

    new_discovery_count = 0

    for row in sitemap_rows:
        url = row[
            "url"
        ]

        if url in discovered_state:
            continue

        event = {
            "event_type": (
                "url_discovered"
            ),
            "discovery_run_id": (
                discovery_run_id
            ),
            "source_id": (
                source_id
            ),
            "url": url,
            "sitemap_url": (
                sitemap_url
            ),
            "discovery_method": (
                "publisher_static_sitemap"
            ),
            "discovered_at_real": (
                utc_now()
            ),
            "source_declared_timestamp": (
                row.get(
                    "source_declared_timestamp"
                )
            ),
        }

        append_log(
            log_path,
            event,
        )

        discovered_state[
            url
        ] = event

        new_discovery_count += 1

    print(
        "New discovery log rows:",
        new_discovery_count,
    )

    # --------------------------------------------------------
    # TARGET
    # --------------------------------------------------------

    if args.limit > 0:
        target_rows = (
            sitemap_rows[
                :args.limit
            ]
        )
    else:
        target_rows = (
            sitemap_rows
        )

    pending_rows = [
        row
        for row in target_rows
        if needs_retry(
            row["url"],
            checked_state,
        )
    ]

    print(
        "Target URLs:",
        len(target_rows),
    )

    print(
        "Already resolved/non-retry:",
        (
            len(target_rows)
            - len(pending_rows)
        ),
    )

    print(
        "Pending/retry:",
        len(pending_rows),
    )

    # --------------------------------------------------------
    # CONCURRENT ARTICLE PROCESSING
    # --------------------------------------------------------

    print(
        "\nStarting concurrent article checks..."
    )

    process_concurrently(
        pending_rows=(
            pending_rows
        ),
        workers=(
            args.workers
        ),
        rate=(
            args.rate
        ),
        max_attempts=(
            args.attempts
        ),
        progress_every=(
            args.progress_every
        ),
        log_path=(
            log_path
        ),
        checked_state=(
            checked_state
        ),
        discovery_run_id=(
            discovery_run_id
        ),
        source_id=(
            source_id
        ),
    )

    # --------------------------------------------------------
    # RELOAD FROM APPEND-ONLY LOG
    # --------------------------------------------------------

    (
        discovered_state,
        checked_state,
    ) = load_log_state(
        log_path
    )

    # --------------------------------------------------------
    # MATERIALIZE
    # --------------------------------------------------------

    discovered_df = (
        build_discovered_dataframe(
            sitemap_rows=(
                sitemap_rows
            ),
            discovered_state=(
                discovered_state
            ),
            checked_state=(
                checked_state
            ),
            source_id=(
                source_id
            ),
            sitemap_url=(
                sitemap_url
            ),
            discovery_run_id=(
                discovery_run_id
            ),
        )
    )

    discovered_df.to_parquet(
        discovered_path,
        index=False,
    )

    write_archive_candidates(
        archive_path
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = build_summary(
        discovered_df=(
            discovered_df
        ),
        sitemap_url=(
            sitemap_url
        ),
        sitemap_rows=(
            sitemap_rows
        ),
        source_id=(
            source_id
        ),
        discovery_run_id=(
            discovery_run_id
        ),
        workers=(
            args.workers
        ),
        rate=(
            args.rate
        ),
    )

    with summary_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "PILOT SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print(
        "\nOUTPUT FILES"
    )

    print(
        "-" * 70
    )

    print(
        discovered_path
    )

    print(
        archive_path
    )

    print(
        log_path
    )

    print(
        summary_path
    )


if __name__ == "__main__":
    main()