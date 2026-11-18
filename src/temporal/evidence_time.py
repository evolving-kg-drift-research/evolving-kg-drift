"""Stage 4.10 evidence-time resolution and outcome-blind snapshot boundaries (S1, v3.2 candidate).

Pure functions only. Three time axes stay separate: this module produces ``evidence_observed_at``
with an explicit basis; it never uses ``retrieved_at_real`` as evidence time and never invents a
fallback timestamp (AGENTS.md INV-01 / three-axis separation).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

BASIS_WAYBACK = "wayback_archive_datetime"
BASIS_PUBLISHER = "publisher_declared_published_at"
CONF_HIGH = "high"
CONF_MEDIUM = "medium"

_LD_RE = re.compile(rb'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_META_RE = re.compile(rb'property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)', re.I)
_ARTICLE_TYPE_RE = re.compile(r"Article|Report|BlogPosting", re.I)
_TUOITRE_URL_RE = re.compile(r"-(20\d{12})\d{3}\.htm(?:$|[?#])")
_VN_TZ = timezone(timedelta(hours=7))


def parse_aware(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; naive or malformed values return None (fail closed)."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _walk_article_dates(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if isinstance(node.get("datePublished"), str) and any(
            isinstance(k, str) and _ARTICLE_TYPE_RE.search(k) for k in kinds
        ):
            found.append(node["datePublished"])
        for child in node.values():
            found.extend(_walk_article_dates(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(_walk_article_dates(child))
    return found


def extract_publisher_published_at(html: bytes) -> tuple[datetime, str, str] | None:
    """Return (utc time, raw string, source) of the article's declared publication time.

    Order: JSON-LD Article ``datePublished`` then ``article:published_time`` meta. A value without
    timezone is rejected rather than assumed.
    """
    for block in _LD_RE.findall(html):
        try:
            data = json.loads(block.decode("utf-8", errors="replace").strip())
        except json.JSONDecodeError:
            continue
        for raw in _walk_article_dates(data):
            parsed = parse_aware(raw)
            if parsed is not None:
                return parsed, raw, "jsonld_datePublished"
    match = _META_RE.search(html)
    if match:
        raw = match.group(1).decode("utf-8", errors="replace")
        parsed = parse_aware(raw)
        if parsed is not None:
            return parsed, raw, "meta_article_published_time"
    return None


def tuoitre_url_published_at(url: str | None) -> datetime | None:
    """Publication time embedded in a Tuoi Tre URL id (yyyymmddHHMMSS + ms, UTC+7); strict form only."""
    match = _TUOITRE_URL_RE.search(url or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=_VN_TZ).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass(frozen=True)
class DocumentTime:
    observed_at: datetime | None
    basis: str | None
    confidence: str | None
    flags: tuple[str, ...]
    exclusion_reason: str | None


def resolve_document_time(
    archive_at: datetime | None,
    published_at: datetime | None,
    retrieved_at: datetime | None,
    *,
    chrome_text_only: bool = False,
) -> DocumentTime:
    """Resolve one document's evidence-observed time with an explicit basis.

    Wayback ``archive_datetime`` is authoritative where it exists (decision
    stage4_3_vnexpress_archive_time_semantics). Otherwise the publisher-declared publication time is
    used, flagged as such. ``retrieved_at`` is only a sanity bound: a publication time later than
    the crawl is impossible and excludes the document. No fallback value is ever fabricated.

    ``chrome_text_only`` marks a body that is page chrome (e.g. a related-news teaser headline), not
    the article itself. A live crawl shows such text as of crawl time, so the page's publication
    date says nothing about when the text became public: without an archive capture the document
    is excluded rather than dated.
    """
    flags: list[str] = []
    if archive_at is not None:
        if published_at is not None and published_at > archive_at:
            flags.append("PUBLISHED_AFTER_ARCHIVE_IGNORED")
        return DocumentTime(archive_at, BASIS_WAYBACK, CONF_HIGH, tuple(flags), None)
    if chrome_text_only:
        return DocumentTime(None, None, None, ("CHROME_TEXT_ONLY",), "CHROME_TEASER_EVIDENCE_TIME_UNKNOWN")
    if published_at is None:
        return DocumentTime(None, None, None, (), "NO_EVIDENCE_TIME_SOURCE")
    if retrieved_at is not None and published_at > retrieved_at:
        return DocumentTime(None, None, None, ("PUBLISHED_AFTER_RETRIEVAL",), "PUBLISHED_AFTER_RETRIEVAL")
    return DocumentTime(published_at, BASIS_PUBLISHER, CONF_MEDIUM, tuple(flags), None)


def event_balanced_cuts(event_times: Sequence[datetime], n_snapshots: int) -> list[int]:
    """Slice indices (len n+1) for event-balanced snapshots, never splitting equal timestamps.

    ``event_times`` must be sorted ascending. Each ideal index ``round(k*N/n)`` (same rule as
    v3.1) is moved forward to the end of its equal-timestamp group. Outcome-blind: uses only event
    counts and timestamps.
    """
    total = len(event_times)
    if n_snapshots < 1 or total < n_snapshots:
        raise ValueError("Need at least one event per snapshot")
    if any(b < a for a, b in zip(event_times, event_times[1:])):
        raise ValueError("event_times must be sorted ascending")
    cuts = [0]
    for k in range(1, n_snapshots):
        idx = round(k * total / n_snapshots)
        while idx < total and event_times[idx] == event_times[idx - 1]:
            idx += 1
        if idx <= cuts[-1] or idx >= total:
            raise ValueError(f"Degenerate boundary {k}: equal-timestamp groups leave an empty snapshot")
        cuts.append(idx)
    cuts.append(total)
    return cuts
