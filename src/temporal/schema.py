from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class ContractError(Exception):
    pass


@dataclass(frozen=True, init=False)
class ClaimCandidate:
    """A claim candidate proposed by extraction on a specific body variant."""
    claim_id: str
    body_variant_id: str
    subject_mention: str
    relation_name: str
    object_mention: str
    evidence_span_start: int
    evidence_span_end: int
    evidence_text_hash: str
    valid_from_extracted: Optional[str]
    valid_to_extracted: Optional[str]
    is_negative: bool
    is_speculative: bool

    def __init__(
        self,
        claim_id: str,
        body_variant_id: str = "",
        subject_mention: str = "",
        relation_name: str = "",
        object_mention: str = "",
        evidence_span_start: int = 0,
        evidence_span_end: int = 0,
        evidence_text_hash: str = "",
        valid_from_extracted: Optional[str] = None,
        valid_to_extracted: Optional[str] = None,
        is_negative: bool = False,
        is_speculative: bool = False,
        source_id: Optional[str] = None,
    ):
        bv_id = body_variant_id or source_id or ""
        object.__setattr__(self, "claim_id", claim_id)
        object.__setattr__(self, "body_variant_id", bv_id)
        object.__setattr__(self, "subject_mention", subject_mention)
        object.__setattr__(self, "relation_name", relation_name)
        object.__setattr__(self, "object_mention", object_mention)
        object.__setattr__(self, "evidence_span_start", evidence_span_start)
        object.__setattr__(self, "evidence_span_end", evidence_span_end)
        object.__setattr__(self, "evidence_text_hash", evidence_text_hash)
        object.__setattr__(self, "valid_from_extracted", valid_from_extracted)
        object.__setattr__(self, "valid_to_extracted", valid_to_extracted)
        object.__setattr__(self, "is_negative", is_negative)
        object.__setattr__(self, "is_speculative", is_speculative)

        if self.evidence_span_start is None or self.evidence_span_end is None:
            raise ContractError("Evidence span offsets are mandatory to prevent hallucinations.")
        if self.evidence_span_start >= self.evidence_span_end:
            raise ContractError("Evidence span start must be strictly less than end.")
        if not self.evidence_text_hash:
            raise ContractError("Evidence text hash is mandatory.")

    @property
    def source_id(self) -> str:
        """Deprecated alias: returns body_variant_id for backwards compatibility."""
        return self.body_variant_id


# Backwards compatibility alias
Claim = ClaimCandidate


@dataclass(frozen=True)
class ClaimProvenance:
    """Multi-hop provenance linking a ClaimCandidate to its true source version and retrieval."""
    claim_id: str
    membership_id: str
    source_version_id: str
    retrieval_id: str
    raw_blob_sha256: str
    publisher_source_id: str
    source_url: str


@dataclass(frozen=True)
class FactVersion:
    fact_version_id: str
    logical_fact_id: str

    subject_id: str
    relation_id: str
    object_id: str

    valid_from: Optional[datetime]
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
    supporting_claim_ids: tuple[str, ...] = ()
    temporal_status: str = "VALID"
    evidence_time_basis: str = ""
    evidence_time_confidence: Optional[float] = None
    evidence_time_source: str = ""

    def __post_init__(self):
        if self.valid_from is not None and self.valid_from.tzinfo is None:
            raise ContractError("valid_from must be timezone-aware.")
        if self.valid_to is not None and self.valid_to.tzinfo is None:
            raise ContractError("valid_to must be timezone-aware.")
        if self.evidence_span_start is None or self.evidence_span_end is None:
            raise ContractError("FactVersion requires evidence span offsets.")
        if self.valid_from is not None and self.valid_to is not None and self.valid_from >= self.valid_to:
            raise ContractError("valid_from must be strictly before valid_to if valid_to is set.")
        if self.evidence_observed_at.tzinfo is None:
            raise ContractError("evidence_observed_at must be timezone-aware.")
        if self.ingested_at_real.tzinfo is None:
            raise ContractError("ingested_at_real must be timezone-aware.")
        if self.evidence_text_hash in ("placeholder_hash", "placeholder", ""):
            raise ContractError("FactVersion rejects fabricated placeholder evidence text hash.")
        if self.evidence_span_start == 0 and self.evidence_span_end == 1 and "placeholder" in self.evidence_text_hash:
            raise ContractError("FactVersion rejects fabricated dummy span [0, 1).")


@dataclass(frozen=True)
class EntityMappingVersion:
    """Versioned point-in-time entity resolution mapping."""
    entity_mapping_id: str
    mention: str
    canonical_entity_id: str
    mapping_available_at: datetime
    entity_map_version: str = "v1"
    supersedes_mapping_id: Optional[str] = None
    mapping_basis: str = "catalog"
    mapping_confidence: float = 1.0

    def __post_init__(self):
        if self.mapping_available_at.tzinfo is None:
            raise ContractError("mapping_available_at must be timezone-aware.")

