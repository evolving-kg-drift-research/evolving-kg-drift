"""Entity map v2: deterministic, per-mention canonical keys (S2, candidate).

Every function here depends only on the mention string itself. A mapping therefore never uses
information that appears later than the mention (INV-02), and an entity id is identical in every
snapshot. Links that need two mentions seen together (e.g. "AWS" <-> "Amazon Web Services (AWS)")
are NOT applied here; they are only proposed, with the time they became knowable.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

ENTITY_MAP_VERSION = "entity_map_v2"

# Leading class words that only describe the entity ("tập đoàn FPT" -> "FPT"). Official names that
# start with other class words (Ngân hàng Nhà nước, Viện ..., Trung tâm ...) are deliberately kept.
CLASSIFIER_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("tập", "đoàn"), ("công", "ty"), ("hãng",), ("ông",), ("bà",),
)
# Place names that begin with a class word and must not lose it ("Bà Rịa" is a province, not "bà").
NO_STRIP_BEFORE: frozenset[tuple[str, str]] = frozenset({("bà", "rịa")})
LEGAL_SUFFIXES = frozenset({"corporation", "corp", "inc", "ltd", "llc", "plc", "group", "co"})

# Anaphora and bare class nouns that identify no entity. Compared on the lowercase key.
GENERIC_STOPLIST = frozenset({
    "ông", "bà", "anh", "chị", "cô", "em", "họ", "hắn", "nó", "người này", "người đó",
    "công ty", "hãng", "tập đoàn", "doanh nghiệp", "startup", "công ty này", "hãng này",
    "chatbot", "mô hình", "ai", "học viện", "trường", "ứng dụng", "sản phẩm", "hệ thống",
    "nền tảng", "dịch vụ", "công cụ", "tính năng", "người dùng",
})

_PAREN_TAIL = re.compile(r"\s*\(([^()]*)\)\s*$")
_QUOTES = re.compile("[\"'“”‘’]+")
_DASHES = re.compile("[‐-―_\\-]+")
_SPACES = re.compile(r"\s+")


def _strip_digitless_parentheticals(name: str) -> str:
    """Drop trailing "(...)" groups that contain no digit; keep codes such as "(A05)" or "(M3407GA)"."""
    current = name
    while True:
        match = _PAREN_TAIL.search(current)
        if not match or any(ch.isdigit() for ch in match.group(1)):
            return current
        stripped = current[: match.start()].rstrip()
        if not stripped:
            return current
        current = stripped


def canonical_key(name: str) -> str:
    """Canonical lowercase key of one mention (NFC, format-normalised, class/legal words stripped)."""
    text = _strip_digitless_parentheticals(unicodedata.normalize("NFC", name).strip())
    text = _SPACES.sub(" ", _QUOTES.sub("", _DASHES.sub(" ", text))).strip(" .,;:")
    tokens = text.split(" ")
    lowered = [t.lower() for t in tokens]
    for prefix in CLASSIFIER_PREFIXES:
        n = len(prefix)
        if (tuple(lowered[:n]) == prefix and len(tokens) > n
                and (tokens[n][0].isupper() or tokens[n][0].isdigit())
                and (prefix[-1], lowered[n]) not in NO_STRIP_BEFORE):
            tokens, lowered = tokens[n:], lowered[n:]
            break
    if len(tokens) > 1 and lowered[-1].rstrip(".") in LEGAL_SUFFIXES:
        lowered = lowered[:-1]
    return " ".join(lowered)


def is_generic_mention(name: str) -> bool:
    """True when the mention names no specific entity (anaphora, bare class noun, lowercase descriptor)."""
    text = _SPACES.sub(" ", unicodedata.normalize("NFC", name).strip().lower())
    if text in GENERIC_STOPLIST:
        return True
    tokens = _SPACES.sub(" ", unicodedata.normalize("NFC", name).strip()).split(" ")
    return len(tokens) >= 2 and name.strip()[0].islower() and all(t.isalpha() and t.islower() for t in tokens)


def entity_id_v2(key: str) -> str:
    return "ent2_" + hashlib.sha256(f"{ENTITY_MAP_VERSION}|{key}".encode()).hexdigest()[:8]
