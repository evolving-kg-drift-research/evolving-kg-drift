"""Versioned clean-text normalization and exact evidence-span references."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from temporal.schema import ContractError

from .hashing import sha256_text

IDENTITY_NORMALIZATION_VERSION = "clean-text-identity-v1"
NFC_NORMALIZATION_VERSION = "clean-text-nfc-v1"


def normalize_clean_text(text: str, version: str) -> str:
    """Apply an explicitly selected normalization version; never choose a default."""
    if not isinstance(text, str):
        raise ContractError("Clean text must be a string.")
    if version == IDENTITY_NORMALIZATION_VERSION:
        return text
    if version == NFC_NORMALIZATION_VERSION:
        return unicodedata.normalize("NFC", text)
    raise ContractError(f"Unknown clean-text normalization version: {version!r}")


@dataclass(frozen=True)
class EvidenceSpan:
    """Offsets and hash into the exact versioned clean-text representation."""

    start: int
    end: int
    text_sha256: str
    clean_text_sha256: str
    normalization_version: str

    @classmethod
    def from_text(
        cls,
        clean_text: str,
        start: int,
        end: int,
        normalization_version: str,
    ) -> "EvidenceSpan":
        normalized = normalize_clean_text(clean_text, normalization_version)
        if normalized != clean_text:
            raise ContractError(
                "Stored clean text does not match its declared normalization version."
            )
        if type(start) is not int or type(end) is not int:
            raise ContractError("Evidence span offsets must be integer code-point offsets.")
        if start < 0 or end <= start or end > len(clean_text):
            raise ContractError("Evidence span offsets are out of bounds for the referenced clean text.")
        return cls(
            start=start,
            end=end,
            text_sha256=sha256_text(clean_text[start:end]),
            clean_text_sha256=sha256_text(clean_text),
            normalization_version=normalization_version,
        )
