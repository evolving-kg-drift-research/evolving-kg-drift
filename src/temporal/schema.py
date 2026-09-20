from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class ContractError(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    """A claim proposed by extraction, before adjudication."""
    claim_id: str
    source_id: str
    subject_mention: str
    relation_name: str
    object_mention: str
    evidence_span_start: int
    evidence_span_end: int
    evidence_text_hash: str
    valid_from_extracted: Optional[str] = None
    valid_to_extracted: Optional[str] = None
    is_negative: bool = False
    is_speculative: bool = False

    def __post_init__(self):
        if self.evidence_span_start is None or self.evidence_span_end is None:
            raise ContractError("Evidence span offsets are mandatory to prevent hallucinations.")
        if self.evidence_span_start >= self.evidence_span_end:
            raise ContractError("Evidence span start must be strictly less than end.")
        if not self.evidence_text_hash:
            raise ContractError("Evidence text hash is mandatory.")


@dataclass(frozen=True)
class FactVersion:
    fact_version_id: str
    logical_fact_id: str

    subject_id: str
    relation_id: str
    object_id: str

    valid_from: datetime
    valid_to: Optional[datetime]

    evidence_observed_at: datetime
    ingested_at_real: datetime

    supersedes_version_id: Optional[str]
    revision_type: str

    source_id: str
    source_url: str

    evidence_span_start: int
    evidence_span_end: int
    evidence_text_hash: str

    extractor_version: str = ""
    entity_map_version: str = ""

    confidence: Optional[float] = None
    adjudication_status: Optional[str] = None

    def __post_init__(self):
        if self.valid_from.tzinfo is None:
            raise ContractError("valid_from must be timezone-aware.")
        if self.valid_to is not None and self.valid_to.tzinfo is None:
            raise ContractError("valid_to must be timezone-aware.")
        if self.evidence_span_start is None or self.evidence_span_end is None:
            raise ContractError("FactVersion requires evidence span offsets.")
        if self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ContractError("valid_from must be strictly before valid_to if valid_to is set.")
        if self.evidence_observed_at.tzinfo is None:
            raise ContractError("evidence_observed_at must be timezone-aware.")
        if self.ingested_at_real.tzinfo is None:
            raise ContractError("ingested_at_real must be timezone-aware.")

