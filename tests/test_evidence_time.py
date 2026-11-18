from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from temporal.evidence_time import (
    BASIS_PUBLISHER,
    BASIS_WAYBACK,
    event_balanced_cuts,
    extract_publisher_published_at,
    parse_aware,
    resolve_document_time,
    tuoitre_url_published_at,
)

UTC = timezone.utc


def _ld(payload: str) -> bytes:
    return f'<html><script type="application/ld+json">{payload}</script></html>'.encode()


def test_parse_aware_rejects_naive_and_garbage() -> None:
    assert parse_aware("2025-07-10T19:00:00+07:00") == datetime(2025, 7, 10, 12, 0, tzinfo=UTC)
    assert parse_aware("2025-07-10T12:00:00Z") == datetime(2025, 7, 10, 12, 0, tzinfo=UTC)
    assert parse_aware("2025-07-10T19:00:00") is None
    assert parse_aware("not a date") is None


def test_jsonld_article_date_with_type_list_and_graph() -> None:
    html = _ld('{"@graph":[{"@type":"WebSite"},{"@type":["NewsArticle","Thing"],'
               '"datePublished":"2026-01-02T03:04:05+07:00"}]}')
    got = extract_publisher_published_at(html)
    assert got is not None and got[0] == datetime(2026, 1, 1, 20, 4, 5, tzinfo=UTC)
    assert got[2] == "jsonld_datePublished"


def test_jsonld_ignores_non_article_dates_and_naive_values() -> None:
    assert extract_publisher_published_at(_ld('{"@type":"Event","datePublished":"2026-01-02T03:04:05Z"}')) is None
    assert extract_publisher_published_at(_ld('{"@type":"NewsArticle","datePublished":"2026-01-02T03:04:05"}')) is None


def test_meta_fallback() -> None:
    html = b'<meta property="article:published_time" content="2025-03-17T01:02:03+00:00">'
    got = extract_publisher_published_at(html)
    assert got is not None and got[2] == "meta_article_published_time"


def test_tuoitre_url_strict_form_only() -> None:
    url = "https://tuoitre.vn/x-y-20260220140751211.htm"
    assert tuoitre_url_published_at(url) == datetime(2026, 2, 20, 7, 7, 51, tzinfo=UTC)
    assert tuoitre_url_published_at("https://tuoitre.vn/x-100260629205745473.htm") is None
    assert tuoitre_url_published_at(None) is None


def test_archive_time_wins_and_flags_later_publisher_date() -> None:
    archive = datetime(2025, 5, 1, tzinfo=UTC)
    res = resolve_document_time(archive, archive + timedelta(days=3), None)
    assert (res.observed_at, res.basis) == (archive, BASIS_WAYBACK)
    assert "PUBLISHED_AFTER_ARCHIVE_IGNORED" in res.flags


def test_publisher_time_used_without_archive_and_retrieval_is_never_evidence() -> None:
    pub = datetime(2025, 5, 1, tzinfo=UTC)
    res = resolve_document_time(None, pub, datetime(2026, 9, 7, tzinfo=UTC))
    assert (res.observed_at, res.basis) == (pub, BASIS_PUBLISHER)
    none = resolve_document_time(None, None, datetime(2026, 9, 7, tzinfo=UTC))
    assert none.observed_at is None and none.exclusion_reason == "NO_EVIDENCE_TIME_SOURCE"


def test_chrome_teaser_text_is_excluded_unless_archived() -> None:
    pub = datetime(2025, 5, 1, tzinfo=UTC)
    res = resolve_document_time(None, pub, datetime(2026, 9, 7, tzinfo=UTC), chrome_text_only=True)
    assert res.observed_at is None and res.exclusion_reason == "CHROME_TEASER_EVIDENCE_TIME_UNKNOWN"
    archived = resolve_document_time(pub, pub, None, chrome_text_only=True)
    assert archived.observed_at == pub and archived.basis == BASIS_WAYBACK


def test_publisher_time_after_retrieval_is_excluded() -> None:
    res = resolve_document_time(None, datetime(2026, 9, 8, tzinfo=UTC), datetime(2026, 9, 7, tzinfo=UTC))
    assert res.observed_at is None and res.exclusion_reason == "PUBLISHED_AFTER_RETRIEVAL"


def _times(*offsets: int) -> list[datetime]:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return [base + timedelta(days=o) for o in offsets]


def test_cuts_match_plain_rounding_when_no_ties() -> None:
    assert event_balanced_cuts(_times(*range(10)), 5) == [0, 2, 4, 6, 8, 10]


def test_cuts_move_forward_past_equal_timestamps() -> None:
    cuts = event_balanced_cuts(_times(0, 1, 2, 2, 2, 5, 6, 7, 8, 9), 2)
    assert cuts == [0, 5, 10]  # ideal index 5 sits inside no tie; tie group 2,2,2 stays whole
    cuts = event_balanced_cuts(_times(0, 1, 2, 3, 3, 3, 6, 7, 8, 9), 2)
    assert cuts == [0, 6, 10]  # ideal index 5 splits the 3,3,3 group -> moved to its end


def test_cuts_never_split_a_timestamp_group() -> None:
    times = _times(0, 0, 1, 1, 1, 2, 3, 3, 4, 5, 5, 6)
    cuts = event_balanced_cuts(times, 4)
    for c in cuts[1:-1]:
        assert times[c] != times[c - 1]


def test_degenerate_boundaries_fail_closed() -> None:
    with pytest.raises(ValueError):
        event_balanced_cuts(_times(0, 0, 0, 0, 1, 2), 3)
    with pytest.raises(ValueError):
        event_balanced_cuts(_times(0, 1), 3)
    with pytest.raises(ValueError):
        event_balanced_cuts(_times(2, 1, 3), 2)
