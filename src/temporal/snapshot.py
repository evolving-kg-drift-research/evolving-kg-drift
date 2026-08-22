from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .schema import FactVersion


def build_snapshot(
    fact_versions: Iterable[FactVersion],
    cutoff: Any,
) -> tuple[list[FactVersion], str]:
    """Day-2 implementation target.

    Required scientific semantics:
      1. evidence_observed_at <= cutoff
      2. latest observed version per LogicalFactID
      3. valid_from <= cutoff < valid_to (when valid_to exists)
      4. exclude retracted latest versions
      5. assert no future evidence
      6. assert no future entity mapping
      7. canonical deterministic sort
      8. SHA-256 of canonical serialized snapshot

    This scaffold intentionally refuses to fabricate a provisional implementation.
    """
    raise NotImplementedError(
        "Implement temporal snapshot semantics before ingesting real experiment data."
    )
