"""Tuoi Tre article parser v2 and keyword domain rule (X1 pilot, candidate).

Parser v1 used the selector ``article`` and captured a related-news teaser (45-85 chars, finding F12).
v2 reads the publisher's own article fields: headline, sapo and the paragraphs of the content block.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime

from bs4 import BeautifulSoup

PARSER_VERSION = "tuoitre_parser_v2"
# Boxes inside the content block that are not article text: photos/videos/related-news/author/reaction widgets.
_NOISE_CLASS = re.compile(r"VCSortableInPreviewMode|relatedbox|PhotoCMS_Caption|box-author|reactdetail|readmore")
_CASE_SENSITIVE = frozenset({"AI", "LLM"})
_SPACES = re.compile(r"\s+")


class ParseError(ValueError):
    """The page lacks a required article field; the page is excluded, never defaulted."""


def _clean(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def parse_tuoitre(html: str) -> dict[str, str]:
    """Return title, sapo, body, text (title + sapo + body) and published_at (ISO with offset)."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h1.detail-title")
    content = soup.select_one('div[data-role="content"]')
    if title is None or content is None:
        raise ParseError("TUOITRE_ARTICLE_FIELDS_MISSING")
    published = None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and isinstance(item.get("datePublished"), str):
                published = item["datePublished"]
                break
        if published:
            break
    if not published:
        raise ParseError("TUOITRE_DATE_PUBLISHED_MISSING")
    if datetime.fromisoformat(published).utcoffset() is None:
        raise ParseError("TUOITRE_DATE_PUBLISHED_NO_TIMEZONE")
    for node in content.find_all(class_=_NOISE_CLASS):
        node.decompose()
    paragraphs = [_clean(p.get_text(" ")) for p in content.find_all(["p", "h2", "h3"])]
    body = "\n".join(p for p in paragraphs if p)
    sapo_node = soup.select_one("p.detail-sapo, h2.detail-sapo")
    sapo = _clean(sapo_node.get_text(" ")) if sapo_node else ""
    title_text = _clean(title.get_text(" "))
    text = "\n".join(part for part in (title_text, sapo, body) if part)
    return {"title": title_text, "sapo": sapo, "body": body, "text": text, "published_at": published}


def matches_domain_keywords(text: str, keywords: Iterable[str]) -> list[str]:
    """Keywords of filter_policy_v1 found as whole words; AI/LLM are case-sensitive (avoid 'ai' = 'who')."""
    hits = []
    for keyword in keywords:
        flags = 0 if keyword in _CASE_SENSITIVE else re.IGNORECASE
        if re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text, flags):
            hits.append(keyword)
    return hits
