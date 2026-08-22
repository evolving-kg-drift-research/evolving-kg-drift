from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


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

    evidence_span_start: Optional[int] = None
    evidence_span_end: Optional[int] = None
    evidence_text_hash: str = ""

    extractor_version: str = ""
    entity_map_version: str = ""

    confidence: Optional[float] = None
    adjudication_status: Optional[str] = None
