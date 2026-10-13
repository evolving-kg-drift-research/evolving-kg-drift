from __future__ import annotations

import argparse
import calendar
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

BASE_SITEMAP_URL = (
    "https://tuoitre.vn/StaticSitemaps/"
)

CRAWLER_SCRIPT = Path(
    "src/03_discover_historical_tuoitre.py"
)

RUN_LOG_PATH = Path(
    "data/discovery/"
    "tuoitre_historical_window_run.jsonl"
)


# ============================================================
# TIME
# ============================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )


# ============================================================
# APPEND-ONLY ORCHESTRATOR LOG
# ============================================================

def append_run_log(
    event: dict,
) -> None:
    RUN_LOG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with RUN_LOG_PATH.open(
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


# ============================================================
# MONTH ITERATION
# ============================================================

def iter_months(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
):
    year = start_year
    month = start_month

    while (
        year < end_year
        or (
            year == end_year
            and month <= end_month
        )
    ):
        yield year, month

        month += 1

        if month == 13:
            month = 1
            year += 1


# ============================================================
# SITEMAP GENERATION
# ============================================================

def build_month_sitemaps(
    year: int,
    month: int,
):
    last_day = calendar.monthrange(
        year,
        month,
    )[1]

    blocks = [
        (1, 5),
        (6, 10),
        (11, 15),
        (16, 20),
        (21, 25),
        (26, last_day),
    ]

    urls = []

    for start_day, end_day in blocks:
        url = (
            BASE_SITEMAP_URL
            + f"sitemaps-"
            + f"{year}-"
            + f"{month}-"
            + f"{start_day}-"
            + f"{end_day}.xml"
        )

        urls.append(
            url
        )

    return urls


def build_window_sitemaps():
    """
    Frozen historical window:

        2025-03-01
        →
        2026-08-31
    """

    result = []

    for year, month in iter_months(
        2025,
        3,
        2026,
        8,
    ):
        result.extend(
            build_month_sitemaps(
                year,
                month,
            )
        )

    return result


# ============================================================
# RUN ONE SITEMAP
# ============================================================

def run_one_sitemap(
    sitemap_url: str,
    workers: int,
    rate: float,
    attempts: int,
) -> int:

    command = [
        sys.executable,
        str(
            CRAWLER_SCRIPT
        ),
        "--sitemap",
        sitemap_url,
        "--limit",
        "0",
        "--workers",
        str(
            workers
        ),
        "--rate",
        str(
            rate
        ),
        "--attempts",
        str(
            attempts
        ),
    ]

    print()
    print(
        "=" * 78
    )

    print(
        "RUNNING:"
    )

    print(
        sitemap_url
    )

    print(
        "=" * 78
    )

    append_run_log(
        {
            "event_type": (
                "sitemap_run_started"
            ),
            "sitemap_url": (
                sitemap_url
            ),
            "started_at_real": (
                utc_now()
            ),
            "workers": (
                workers
            ),
            "rate": (
                rate
            ),
            "attempts": (
                attempts
            ),
        }
    )

    completed = subprocess.run(
        command,
        check=False,
    )

    return_code = (
        completed.returncode
    )

    append_run_log(
        {
            "event_type": (
                "sitemap_run_finished"
            ),
            "sitemap_url": (
                sitemap_url
            ),
            "finished_at_real": (
                utc_now()
            ),
            "return_code": (
                return_code
            ),
            "status": (
                "success"
                if return_code == 0
                else "failed"
            ),
        }
    )

    return return_code


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run Tuoi Tre historical discovery "
            "for the frozen window "
            "2025-03 through 2026-08."
        )
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--rate",
        type=float,
        default=3.0,
    )

    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Chỉ in sitemap list, "
            "không crawl."
        ),
    )

    args = parser.parse_args()

    if not CRAWLER_SCRIPT.exists():
        raise FileNotFoundError(
            f"Không tìm thấy "
            f"{CRAWLER_SCRIPT}"
        )

    sitemaps = (
        build_window_sitemaps()
    )

    print(
        "Historical window:"
    )

    print(
        "  2025-03-01"
    )

    print(
        "  ->"
    )

    print(
        "  2026-08-31"
    )

    print()

    print(
        "Total sitemap blocks:",
        len(sitemaps),
    )

    print(
        "Workers:",
        args.workers,
    )

    print(
        "Global rate:",
        args.rate,
        "request starts/sec"
    )

    # --------------------------------------------------------
    # DRY RUN
    # --------------------------------------------------------

    if args.dry_run:
        for index, url in enumerate(
            sitemaps,
            start=1,
        ):
            print(
                f"{index:03d}: {url}"
            )

        return

    # --------------------------------------------------------
    # PRODUCTION RUN
    # --------------------------------------------------------

    success_count = 0
    failure_count = 0
    failed_urls = []

    overall_started_at = (
        utc_now()
    )

    append_run_log(
        {
            "event_type": (
                "historical_window_started"
            ),
            "started_at_real": (
                overall_started_at
            ),
            "window_start": (
                "2025-03-01"
            ),
            "window_end": (
                "2026-08-31"
            ),
            "sitemap_count": (
                len(sitemaps)
            ),
            "workers": (
                args.workers
            ),
            "rate": (
                args.rate
            ),
            "attempts": (
                args.attempts
            ),
        }
    )

    for index, sitemap_url in enumerate(
        sitemaps,
        start=1,
    ):
        print()
        print(
            f"SITEMAP "
            f"{index}/{len(sitemaps)}"
        )

        return_code = (
            run_one_sitemap(
                sitemap_url=(
                    sitemap_url
                ),
                workers=(
                    args.workers
                ),
                rate=(
                    args.rate
                ),
                attempts=(
                    args.attempts
                ),
            )
        )

        if return_code == 0:
            success_count += 1
        else:
            failure_count += 1

            failed_urls.append(
                sitemap_url
            )

            print()
            print(
                "WARNING: sitemap failed."
            )

            print(
                "Crawler will continue."
            )

    # --------------------------------------------------------
    # FINISH
    # --------------------------------------------------------

    append_run_log(
        {
            "event_type": (
                "historical_window_finished"
            ),
            "finished_at_real": (
                utc_now()
            ),
            "window_start": (
                "2025-03-01"
            ),
            "window_end": (
                "2026-08-31"
            ),
            "sitemap_count": (
                len(sitemaps)
            ),
            "success_count": (
                success_count
            ),
            "failure_count": (
                failure_count
            ),
            "failed_sitemaps": (
                failed_urls
            ),
        }
    )

    print()
    print(
        "=" * 78
    )

    print(
        "HISTORICAL WINDOW COMPLETE"
    )

    print(
        "=" * 78
    )

    print(
        "Total:",
        len(sitemaps),
    )

    print(
        "Success:",
        success_count,
    )

    print(
        "Failed:",
        failure_count,
    )

    if failed_urls:
        print()
        print(
            "FAILED SITEMAPS:"
        )

        for url in failed_urls:
            print(
                url
            )

        print()
        print(
            "Re-run the same command later. "
            "Per-sitemap crawler resume "
            "will avoid repeating successful URLs."
        )


if __name__ == "__main__":
    main()