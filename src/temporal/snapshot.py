from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from .schema import FactVersion, EntityMappingVersion, ContractError


@dataclass(frozen=True)
class SnapshotEdge:
    edge_id: str
    subject_id: str
    relation_id: str
    object_id: str
    snapshot_id: str


@dataclass(frozen=True)
class SnapshotEdgeSupport:
    support_id: str
    edge_id: str
    fact_version_id: str
    claim_id: str
    source_version_id: str
    raw_blob_sha256: str


@dataclass(frozen=True)
class SnapshotExclusion:
    exclusion_id: str
    record_id: str
    fact_version_id: str
    reason_code: str
    severity: str
    stage: str
    field: str
    detail: str


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_id: str
    cutoff: str
    graph_semantic_hash: str
    support_semantic_hash: str
    fact_store_hash: str
    entity_mapping_hash: str
    resolved_config_hash: str
    code_fingerprint: str
    edge_count: int
    support_count: int
    exclusion_count: int
    created_at_real: str
    snapshot_manifest_hash: str = ""


def compute_graph_semantic_hash(edges: Iterable[SnapshotEdge]) -> str:
    sorted_edges = sorted(edges, key=lambda e: (e.subject_id, e.relation_id, e.object_id))
    hasher = hashlib.sha256()
    for e in sorted_edges:
        hasher.update(f"{e.subject_id}\t{e.relation_id}\t{e.object_id}\n".encode("utf-8"))
    return hasher.hexdigest()


def compute_support_semantic_hash(support_records: Iterable[SnapshotEdgeSupport]) -> str:
    sorted_supp = sorted(support_records, key=lambda s: (s.edge_id, s.fact_version_id, s.claim_id, s.source_version_id, s.raw_blob_sha256))
    hasher = hashlib.sha256()
    for s in sorted_supp:
        hasher.update(f"{s.edge_id}\t{s.fact_version_id}\t{s.claim_id}\t{s.source_version_id}\t{s.raw_blob_sha256}\n".encode("utf-8"))
    return hasher.hexdigest()


def compute_fact_store_hash(facts: Iterable[FactVersion] | None) -> str:
    if not facts:
        return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    sorted_facts = sorted(facts, key=lambda f: (f.subject_id, f.relation_id, f.object_id, f.fact_version_id))
    hasher = hashlib.sha256()
    for f in sorted_facts:
        vf = f.valid_from.isoformat() if f.valid_from else ""
        vt = f.valid_to.isoformat() if f.valid_to else ""
        hasher.update(f"{f.fact_version_id}\t{f.logical_fact_id}\t{f.subject_id}\t{f.relation_id}\t{f.object_id}\t{vf}\t{vt}\t{f.evidence_observed_at.isoformat()}\t{f.source_id}\n".encode("utf-8"))
    return hasher.hexdigest()


def create_snapshot_manifest(
    snapshot_id: str,
    cutoff: datetime,
    edges: list[SnapshotEdge],
    support_records: list[SnapshotEdgeSupport],
    exclusions: list[SnapshotExclusion],
    fact_versions: list[FactVersion] | None = None,
    entity_mapping_hash: str = "none",
    resolved_config_hash: str = "none",
    code_fingerprint: str = "none",
) -> SnapshotManifest:
    graph_hash = compute_graph_semantic_hash(edges)
    support_hash = compute_support_semantic_hash(support_records)
    fact_hash = compute_fact_store_hash(fact_versions)
    created_at = datetime.now(timezone.utc).isoformat()
    cutoff_str = cutoff.isoformat()

    semantic = {
        "snapshot_id": snapshot_id,
        "cutoff": cutoff_str,
        "graph_semantic_hash": graph_hash,
        "support_semantic_hash": support_hash,
        "fact_store_hash": fact_hash,
        "entity_mapping_hash": entity_mapping_hash,
        "resolved_config_hash": resolved_config_hash,
        "code_fingerprint": code_fingerprint,
        "edge_count": len(edges),
        "support_count": len(support_records),
        "exclusion_count": len(exclusions),
    }
    manifest_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode("utf-8")).hexdigest()

    return SnapshotManifest(
        snapshot_id=snapshot_id,
        cutoff=cutoff_str,
        graph_semantic_hash=graph_hash,
        support_semantic_hash=support_hash,
        fact_store_hash=fact_hash,
        entity_mapping_hash=entity_mapping_hash,
        resolved_config_hash=resolved_config_hash,
        code_fingerprint=code_fingerprint,
        edge_count=len(edges),
        support_count=len(support_records),
        exclusion_count=len(exclusions),
        created_at_real=created_at,
        snapshot_manifest_hash=manifest_hash,
    )


def compute_logical_fact_id(
    subject: str,
    relation: str,
    object_: str,
    ontology_rules: dict[str, Any] | None = None,
) -> str:
    """Compute deterministic LogicalFactID respecting relation-specific functional dependency."""
    rules = (ontology_rules or {}).get(relation, {})
    logical_key = rules.get("logical_key")
    if logical_key:
        components = []
        for k in logical_key:
            if k == "subject":
                components.append(subject)
            elif k == "relation":
                components.append(relation)
            elif k == "object":
                components.append(object_)
            else:
                components.append(str(k))
        raw_key = "|".join(components)
    else:
        raw_key = f"{subject}|{relation}|{object_}"

    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def resolve_entity_at_cutoff(
    mention: str,
    mappings: list[EntityMappingVersion] | None,
    cutoff: datetime
) -> str:
    """Point-in-time entity resolution: only mappings available on or before cutoff are valid."""
    if not mappings:
        return mention

    available = [
        m for m in mappings
        if m.mention.lower() == mention.lower() and m.mapping_available_at <= cutoff
    ]
    if not available:
        return mention

    # If multiple mappings are available, resolve supersession chain or take latest
    superseded_ids = {m.supersedes_mapping_id for m in available if m.supersedes_mapping_id}
    active_mappings = [m for m in available if m.entity_mapping_id not in superseded_ids]

    active_mappings.sort(key=lambda m: (m.mapping_available_at, m.entity_map_version), reverse=True)
    return active_mappings[0].canonical_entity_id


def build_snapshot_edges_and_support(
    fact_versions: Iterable[FactVersion],
    cutoff: datetime,
    snapshot_id: str = "snapshot",
    entity_mappings: list[EntityMappingVersion] | None = None,
    ontology_rules: dict[str, Any] | None = None,
) -> tuple[list[SnapshotEdge], list[SnapshotEdgeSupport], list[SnapshotExclusion]]:
    """Build separated SnapshotEdge (unique triples) and SnapshotEdgeSupport (provenance lineage),

    quarantining excluded records into SnapshotExclusion.
    """
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must be timezone-aware.")

    exclusions: list[SnapshotExclusion] = []
    known_facts: list[FactVersion] = []

    # 1. Observation filter: only consider facts where evidence was observed <= cutoff.
    for f in fact_versions:
        if f.evidence_observed_at > cutoff:
            exclusions.append(
                SnapshotExclusion(
                    exclusion_id=f"ex_{f.fact_version_id}_future_obs",
                    record_id=f.fact_version_id,
                    fact_version_id=f.fact_version_id,
                    reason_code="FUTURE_EVIDENCE_OBSERVED_AT",
                    severity="INFO",
                    stage="snapshot_builder",
                    field="evidence_observed_at",
                    detail=f"Evidence observed at {f.evidence_observed_at.isoformat()} > cutoff {cutoff.isoformat()}"
                )
            )
        else:
            known_facts.append(f)

    # 2. Point-in-time entity resolution
    resolved_facts: list[FactVersion] = []
    for f in known_facts:
        resolved_subject = resolve_entity_at_cutoff(f.subject_id, entity_mappings, cutoff)
        resolved_object = resolve_entity_at_cutoff(f.object_id, entity_mappings, cutoff)
        if resolved_subject != f.subject_id or resolved_object != f.object_id:
            # Recreate with resolved entity IDs
            f = FactVersion(
                fact_version_id=f.fact_version_id,
                logical_fact_id=f.logical_fact_id,
                subject_id=resolved_subject,
                relation_id=f.relation_id,
                object_id=resolved_object,
                valid_from=f.valid_from,
                valid_to=f.valid_to,
                evidence_observed_at=f.evidence_observed_at,
                ingested_at_real=f.ingested_at_real,
                supersedes_version_id=f.supersedes_version_id,
                revision_type=f.revision_type,
                source_id=f.source_id,
                source_url=f.source_url,
                evidence_span_start=f.evidence_span_start,
                evidence_span_end=f.evidence_span_end,
                evidence_text_hash=f.evidence_text_hash,
                extractor_version=f.extractor_version,
                entity_map_version=f.entity_map_version,
                confidence=f.confidence,
                adjudication_status=f.adjudication_status
            )
        resolved_facts.append(f)

    # 3. Group by logical_fact_id and resolve revision/supersession chains
    logical_groups: dict[str, list[FactVersion]] = {}
    for f in resolved_facts:
        logical_groups.setdefault(f.logical_fact_id, []).append(f)

    active_facts: list[FactVersion] = []

    for lfid, versions in logical_groups.items():
        superseded_by: dict[str, str] = {}
        version_map: dict[str, FactVersion] = {v.fact_version_id: v for v in versions}

        for v in versions:
            if v.supersedes_version_id and v.supersedes_version_id in version_map:
                existing_winner_id = superseded_by.get(v.supersedes_version_id)
                if not existing_winner_id:
                    superseded_by[v.supersedes_version_id] = v.fact_version_id
                else:
                    existing = version_map[existing_winner_id]
                    if (v.evidence_observed_at, v.fact_version_id) > (existing.evidence_observed_at, existing.fact_version_id):
                        superseded_by[v.supersedes_version_id] = v.fact_version_id

        winning_supersessions = set(superseded_by.values())
        for v in versions:
            current_id = v.fact_version_id
            is_superseded = current_id in superseded_by
            lost_tiebreaker = (v.supersedes_version_id is not None) and (current_id not in winning_supersessions)

            if is_superseded or lost_tiebreaker:
                exclusions.append(
                    SnapshotExclusion(
                        exclusion_id=f"ex_{v.fact_version_id}_superseded",
                        record_id=v.fact_version_id,
                        fact_version_id=v.fact_version_id,
                        reason_code="SUPERSEDED_BY_REVISION",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="supersedes_version_id",
                        detail=f"Superseded by {superseded_by.get(current_id, 'winning_version')}"
                    )
                )
                continue

            if v.revision_type == "retraction":
                exclusions.append(
                    SnapshotExclusion(
                        exclusion_id=f"ex_{v.fact_version_id}_retraction",
                        record_id=v.fact_version_id,
                        fact_version_id=v.fact_version_id,
                        reason_code="RETRACTED",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="revision_type",
                        detail="Fact version is a retraction"
                    )
                )
                continue

            # World validity filter: valid_from <= cutoff < valid_to
            if v.valid_from is not None and v.valid_from > cutoff:
                exclusions.append(
                    SnapshotExclusion(
                        exclusion_id=f"ex_{v.fact_version_id}_future_validity",
                        record_id=v.fact_version_id,
                        fact_version_id=v.fact_version_id,
                        reason_code="FUTURE_WORLD_VALIDITY",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="valid_from",
                        detail=f"valid_from {v.valid_from.isoformat()} > cutoff {cutoff.isoformat()}"
                    )
                )
                continue

            if v.valid_to is not None and cutoff >= v.valid_to:
                exclusions.append(
                    SnapshotExclusion(
                        exclusion_id=f"ex_{v.fact_version_id}_expired_validity",
                        record_id=v.fact_version_id,
                        fact_version_id=v.fact_version_id,
                        reason_code="EXPIRED_WORLD_VALIDITY",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="valid_to",
                        detail=f"valid_to {v.valid_to.isoformat()} <= cutoff {cutoff.isoformat()}"
                    )
                )
                continue

            active_facts.append(v)

    # 4. Group active facts by canonical triple (subject_id, relation_id, object_id) to separate edges from support
    edge_groups: dict[tuple[str, str, str], list[FactVersion]] = {}
    for f in active_facts:
        key = (f.subject_id, f.relation_id, f.object_id)
        edge_groups.setdefault(key, []).append(f)

    edges: list[SnapshotEdge] = []
    support_records: list[SnapshotEdgeSupport] = []

    for (s_id, r_id, o_id), supporting_facts in edge_groups.items():
        edge_hash = hashlib.sha256(f"{s_id}|{r_id}|{o_id}".encode("utf-8")).hexdigest()[:16]
        edge_id = f"edge_{edge_hash}"
        edges.append(
            SnapshotEdge(
                edge_id=edge_id,
                subject_id=s_id,
                relation_id=r_id,
                object_id=o_id,
                snapshot_id=snapshot_id
            )
        )

        for fv in supporting_facts:
            support_id = f"supp_{edge_id}_{fv.fact_version_id}"
            support_records.append(
                SnapshotEdgeSupport(
                    support_id=support_id,
                    edge_id=edge_id,
                    fact_version_id=fv.fact_version_id,
                    claim_id=fv.fact_version_id,
                    source_version_id=fv.source_id,
                    raw_blob_sha256=fv.evidence_text_hash
                )
            )

    # 5. Deterministic sorting
    edges.sort(key=lambda e: (e.subject_id, e.relation_id, e.object_id, e.edge_id))
    support_records.sort(key=lambda s: (s.edge_id, s.fact_version_id, s.support_id))
    exclusions.sort(key=lambda x: (x.fact_version_id, x.reason_code, x.exclusion_id))

    return edges, support_records, exclusions


def build_snapshot(
    fact_versions: Iterable[FactVersion],
    cutoff: datetime,
) -> tuple[list[FactVersion], str]:
    """Builds a deterministic KG snapshot at a specific point in time (FactVersion view)."""
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
        superseded_by: dict[str, str] = {}
        version_map: dict[str, FactVersion] = {v.fact_version_id: v for v in versions}

        for v in versions:
            if v.supersedes_version_id and v.supersedes_version_id in version_map:
                existing_winner_id = superseded_by.get(v.supersedes_version_id)
                if not existing_winner_id:
                    superseded_by[v.supersedes_version_id] = v.fact_version_id
                else:
                    existing = version_map[existing_winner_id]
                    if (v.evidence_observed_at, v.fact_version_id) > (existing.evidence_observed_at, existing.fact_version_id):
                        superseded_by[v.supersedes_version_id] = v.fact_version_id

        active_versions = []
        winning_supersessions = set(superseded_by.values())
        for v in versions:
            current_id = v.fact_version_id
            is_superseded = current_id in superseded_by
            lost_tiebreaker = (v.supersedes_version_id is not None) and (current_id not in winning_supersessions)

            if not is_superseded and not lost_tiebreaker:
                active_versions.append(v)

        for v in active_versions:
            if v.revision_type == "retraction":
                continue

            if v.valid_from is None or v.valid_from <= cutoff:
                if v.valid_to is None or cutoff < v.valid_to:
                    resolved_facts.append(v)

    # 4. Canonical deterministic sort
    resolved_facts.sort(key=lambda x: (
        x.subject_id,
        x.relation_id,
        x.object_id,
        x.valid_from.isoformat() if x.valid_from else "",
        x.logical_fact_id,
        x.fact_version_id
    ))

    # 5. Canonical hash
    snapshot_dicts = []
    for f in resolved_facts:
        snapshot_dicts.append({
            "fact_version_id": f.fact_version_id,
            "logical_fact_id": f.logical_fact_id,
            "subject_id": f.subject_id,
            "relation_id": f.relation_id,
            "object_id": f.object_id,
            "valid_from": f.valid_from.isoformat() if f.valid_from else None,
            "valid_to": f.valid_to.isoformat() if f.valid_to else None,
            "evidence_observed_at": f.evidence_observed_at.isoformat(),
            "source_id": f.source_id
        })
    canonical_json = json.dumps(snapshot_dicts, separators=(',', ':'), sort_keys=True).encode("utf-8")
    semantic_sha256 = hashlib.sha256(canonical_json).hexdigest()

    return resolved_facts, semantic_sha256
