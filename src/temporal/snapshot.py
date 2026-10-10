from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime

from .schema import FactVersion


def build_snapshot(
    fact_versions: Iterable[FactVersion],
    cutoff: datetime,
) -> tuple[list[FactVersion], str]:
    """Builds a deterministic KG snapshot at a specific point in time."""
    
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must be timezone-aware.")

    # 1. Known Filter: only consider facts where evidence was observed <= cutoff.
    known_facts = [f for f in fact_versions if f.evidence_observed_at <= cutoff]
    
    # Map by logical_fact_id to a list of versions
    logical_groups: dict[str, list[FactVersion]] = {}
    for f in known_facts:
        logical_groups.setdefault(f.logical_fact_id, []).append(f)
        
    resolved_facts: list[FactVersion] = []
    
    for lfid, versions in logical_groups.items():
        # 2. Validity filter FIRST: only facts valid at cutoff
        valid_versions = [
            v for v in versions
            if v.valid_from <= cutoff and (v.valid_to is None or cutoff < v.valid_to)
        ]

        # 3. Resolve supersession chains among valid versions (including retractions)
        superseded_by: dict[str, str] = {}
        version_map: dict[str, FactVersion] = {v.fact_version_id: v for v in valid_versions}

        for v in valid_versions:
            if v.supersedes_version_id and v.supersedes_version_id in version_map:
                existing_winner_id = superseded_by.get(v.supersedes_version_id)
                if not existing_winner_id:
                    superseded_by[v.supersedes_version_id] = v.fact_version_id
                else:
                    existing = version_map[existing_winner_id]
                    if (v.evidence_observed_at, v.fact_version_id) > (existing.evidence_observed_at, existing.fact_version_id):
                        superseded_by[v.supersedes_version_id] = v.fact_version_id

        winning_supersessions = set(superseded_by.values())
        for v in valid_versions:
            current_id = v.fact_version_id
            is_superseded = current_id in superseded_by
            lost_tiebreaker = (v.supersedes_version_id is not None) and (current_id not in winning_supersessions)

            if not is_superseded and not lost_tiebreaker:
                # 4. Filter out retractions: retractions supersede prior facts but are never emitted themselves
                if v.revision_type != "retraction":
                    resolved_facts.append(v)

    # 4. Canonical deterministic sort
    resolved_facts.sort(key=lambda x: (
        x.subject_id,
        x.relation_id,
        x.object_id,
        x.valid_from.isoformat(),
        x.logical_fact_id,
        x.fact_version_id
    ))
    
    # 5. Canonical hash
    import hashlib
    snapshot_dicts = []
    for f in resolved_facts:
        snapshot_dicts.append({
            "fact_version_id": f.fact_version_id,
            "logical_fact_id": f.logical_fact_id,
            "subject_id": f.subject_id,
            "relation_id": f.relation_id,
            "object_id": f.object_id,
            "valid_from": f.valid_from.isoformat(),
            "valid_to": f.valid_to.isoformat() if f.valid_to else None,
            "evidence_observed_at": f.evidence_observed_at.isoformat(),
            "source_id": f.source_id
        })
    canonical_json = json.dumps(snapshot_dicts, separators=(',', ':'), sort_keys=True).encode("utf-8")
    semantic_sha256 = hashlib.sha256(canonical_json).hexdigest()
    
    return resolved_facts, semantic_sha256
