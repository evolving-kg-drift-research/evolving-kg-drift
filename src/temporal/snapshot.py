from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .schema import ContractError, FactVersion, EntityMappingVersion

SNAPSHOT_BUILDER_VERSION = "snapshot-builder-bitemporal-v2"


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
    provenance_id: str
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
    snapshot_builder_version: str
    cutoff: str
    graph_semantic_hash: str
    support_semantic_hash: str
    fact_store_hash: str
    accepted_clock_hash: str
    entity_mapping_hash: str
    resolved_config_hash: str
    boundary_hash: str
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
    sorted_supp = sorted(support_records, key=lambda s: (s.provenance_id, s.edge_id, s.fact_version_id, s.claim_id, s.source_version_id, s.raw_blob_sha256))
    hasher = hashlib.sha256()
    for s in sorted_supp:
        hasher.update(f"{s.provenance_id}\t{s.edge_id}\t{s.fact_version_id}\t{s.claim_id}\t{s.source_version_id}\t{s.raw_blob_sha256}\n".encode("utf-8"))
    return hasher.hexdigest()


def compute_fact_store_hash(
    facts: Iterable[FactVersion] | None,
    accepted_at_by_fact_id: dict[str, datetime] | None = None,
) -> str:
    if not facts:
        return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    sorted_facts = sorted(facts, key=lambda f: (f.subject_id, f.relation_id, f.object_id, f.fact_version_id))
    semantic_rows = []
    for fact in sorted_facts:
        row = asdict(fact)
        for name, value in row.items():
            if isinstance(value, datetime):
                row[name] = value.isoformat()
            elif isinstance(value, tuple):
                row[name] = list(value)
        accepted_at = (accepted_at_by_fact_id or {}).get(fact.fact_version_id)
        row["accepted_into_kg_at"] = accepted_at.isoformat() if accepted_at is not None else None
        semantic_rows.append(row)
    encoded = json.dumps(semantic_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_entity_mapping_hash(mappings: Iterable[EntityMappingVersion] | None) -> str:
    rows = []
    for mapping in mappings or ():
        rows.append({
            "entity_mapping_id": mapping.entity_mapping_id,
            "mention": mapping.mention,
            "canonical_entity_id": mapping.canonical_entity_id,
            "mapping_available_at": mapping.mapping_available_at.isoformat(),
            "entity_map_version": mapping.entity_map_version,
            "supersedes_mapping_id": mapping.supersedes_mapping_id,
            "mapping_basis": mapping.mapping_basis,
            "mapping_confidence": mapping.mapping_confidence,
        })
    rows.sort(key=lambda row: (row["mention"].casefold(), row["mapping_available_at"], row["entity_mapping_id"]))
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
    boundary_hash: str = "none",
    accepted_at_by_fact_id: dict[str, datetime] | None = None,
) -> SnapshotManifest:
    for name, value in (
        ("entity_mapping_hash", entity_mapping_hash),
        ("resolved_config_hash", resolved_config_hash),
        ("boundary_hash", boundary_hash),
        ("code_fingerprint", code_fingerprint),
    ):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ContractError(f"Snapshot manifest requires a verified SHA-256 {name}; got {value!r}.")
    facts = list(fact_versions or ())
    accepted_clocks = accepted_at_by_fact_id or {}
    fact_ids = {fact.fact_version_id for fact in facts}
    if facts and set(accepted_clocks) != fact_ids:
        raise ContractError(
            "Snapshot manifest acceptance clocks must bind every FactVersion exactly once."
        )
    if any(value.tzinfo is None or value.utcoffset() is None for value in accepted_clocks.values()):
        raise ContractError("Snapshot manifest acceptance clocks must be timezone-aware.")

    graph_hash = compute_graph_semantic_hash(edges)
    support_hash = compute_support_semantic_hash(support_records)
    fact_hash = compute_fact_store_hash(facts, accepted_at_by_fact_id)
    created_at = datetime.now(timezone.utc).isoformat()
    cutoff_str = cutoff.isoformat()

    semantic = {
        "snapshot_id": snapshot_id,
        "snapshot_builder_version": SNAPSHOT_BUILDER_VERSION,
        "cutoff": cutoff_str,
        "graph_semantic_hash": graph_hash,
        "support_semantic_hash": support_hash,
        "fact_store_hash": fact_hash,
        "accepted_clock_hash": hashlib.sha256(
            json.dumps(
                {
                    fact_id: accepted_at.isoformat()
                    for fact_id, accepted_at in sorted((accepted_at_by_fact_id or {}).items())
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "entity_mapping_hash": entity_mapping_hash,
        "resolved_config_hash": resolved_config_hash,
        "boundary_hash": boundary_hash,
        "code_fingerprint": code_fingerprint,
        "edge_count": len(edges),
        "support_count": len(support_records),
        "exclusion_count": len(exclusions),
    }
    manifest_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode("utf-8")).hexdigest()

    return SnapshotManifest(
        snapshot_id=snapshot_id,
        snapshot_builder_version=SNAPSHOT_BUILDER_VERSION,
        cutoff=cutoff_str,
        graph_semantic_hash=graph_hash,
        support_semantic_hash=support_hash,
        fact_store_hash=fact_hash,
        accepted_clock_hash=semantic["accepted_clock_hash"],
        entity_mapping_hash=entity_mapping_hash,
        resolved_config_hash=resolved_config_hash,
        boundary_hash=boundary_hash,
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


def resolve_entity_mapping_at_cutoff(
    mention: str,
    mappings: list[EntityMappingVersion] | None,
    cutoff: datetime
) -> EntityMappingVersion | None:
    """Return the unique active, evidenced mapping available at ``cutoff``.

    Mapping history is append-only. Missing history leaves the mention unresolved;
    competing active decisions are an integrity/policy blocker and are never
    settled by sorting version labels.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("Entity mapping cutoff must be timezone-aware.")
    if not mention or not mention.strip():
        raise ValueError("Entity mapping lookup requires a non-empty mention.")
    if not mappings:
        return None

    ids: dict[str, EntityMappingVersion] = {}
    for mapping in mappings:
        if mapping.entity_mapping_id in ids:
            raise ContractError(f"Duplicate entity_mapping_id: {mapping.entity_mapping_id}")
        ids[mapping.entity_mapping_id] = mapping

    matching = [m for m in mappings if m.mention.casefold() == mention.casefold()]
    for mapping in matching:
        parent_id = mapping.supersedes_mapping_id
        if parent_id:
            parent = ids.get(parent_id)
            if parent is None:
                raise ContractError(
                    f"Mapping {mapping.entity_mapping_id} supersedes missing mapping {parent_id}"
                )
            if parent.mention.casefold() != mapping.mention.casefold():
                raise ContractError(
                    f"Mapping {mapping.entity_mapping_id} supersedes a decision for another mention"
                )
            if parent.mapping_available_at > mapping.mapping_available_at:
                raise ContractError(
                    f"Mapping {mapping.entity_mapping_id} predates its superseded decision"
                )

    available = [m for m in matching if m.mapping_available_at <= cutoff]
    if not available:
        return None

    available_ids = {m.entity_mapping_id for m in available}
    superseded_ids = {
        m.supersedes_mapping_id
        for m in available
        if m.supersedes_mapping_id in available_ids
    }
    active = [m for m in available if m.entity_mapping_id not in superseded_ids]
    if len(active) != 1:
        raise ContractError(
            f"Ambiguous as-of entity mapping for {mention!r} at {cutoff.isoformat()}: "
            f"{sorted(m.entity_mapping_id for m in active)}"
        )

    # A supersession cycle has no active decision. The explicit check makes the
    # failure clear even when a malformed cycle also produces multiple roots.
    visited: set[str] = set()
    current: EntityMappingVersion | None = active[0]
    while current is not None:
        if current.entity_mapping_id in visited:
            raise ContractError(f"Entity mapping supersession cycle for {mention!r}")
        visited.add(current.entity_mapping_id)
        parent_id = current.supersedes_mapping_id
        current = ids.get(parent_id) if parent_id and parent_id in available_ids else None
    return active[0]


def resolve_entity_at_cutoff(
    mention: str,
    mappings: list[EntityMappingVersion] | None,
    cutoff: datetime,
) -> str:
    """Resolve a mention using only the unique mapping decision known by cutoff."""
    selected = resolve_entity_mapping_at_cutoff(mention, mappings, cutoff)
    return selected.canonical_entity_id if selected is not None else mention



def build_snapshot_edges_and_support(
    fact_versions: Iterable[FactVersion],
    cutoff: datetime,
    snapshot_id: str = "snapshot",
    entity_mappings: list[EntityMappingVersion] | None = None,
    ontology_rules: dict[str, Any] | None = None,
    provenance_map: dict[str, list[dict[str, str]]] | None = None,
    accepted_at_by_fact_id: dict[str, datetime] | None = None,
    require_accepted_clock: bool = False,
) -> tuple[list[SnapshotEdge], list[SnapshotEdgeSupport], list[SnapshotExclusion]]:
    """Build separated SnapshotEdge (unique triples) and SnapshotEdgeSupport (provenance lineage),

    quarantining excluded records into SnapshotExclusion.
    """
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must be timezone-aware.")

    exclusions: list[SnapshotExclusion] = []
    known_facts: list[FactVersion] = []

    # 1. Known/accepted filter. The accepting clock is distinct from evidence
    # observation; locked callers must supply it rather than infer a default.
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

    accepted_facts: list[FactVersion] = []
    for fact in known_facts:
        accepted_at = (accepted_at_by_fact_id or {}).get(fact.fact_version_id)
        if accepted_at is None:
            if require_accepted_clock:
                raise ContractError(
                    f"Missing accepted_into_kg_at for fact version {fact.fact_version_id}."
                )
            accepted_facts.append(fact)
            continue
        if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
            raise ContractError(f"accepted_into_kg_at must be timezone-aware: {fact.fact_version_id}")
        if accepted_at > cutoff:
            exclusions.append(SnapshotExclusion(
                exclusion_id=f"ex_{fact.fact_version_id}_future_acceptance",
                record_id=fact.fact_version_id,
                fact_version_id=fact.fact_version_id,
                reason_code="FUTURE_KG_ACCEPTANCE",
                severity="INFO",
                stage="snapshot_builder",
                field="accepted_into_kg_at",
                detail=f"Accepted at {accepted_at.isoformat()} > cutoff {cutoff.isoformat()}",
            ))
        else:
            accepted_facts.append(fact)

    # 2. World validity precedes revision selection by contract.
    valid_facts: list[FactVersion] = []
    for fact in accepted_facts:
        if fact.valid_from is not None and fact.valid_from > cutoff:
            exclusions.append(SnapshotExclusion(
                exclusion_id=f"ex_{fact.fact_version_id}_future_validity",
                record_id=fact.fact_version_id,
                fact_version_id=fact.fact_version_id,
                reason_code="FUTURE_WORLD_VALIDITY",
                severity="INFO",
                stage="snapshot_builder",
                field="valid_from",
                detail=f"valid_from {fact.valid_from.isoformat()} > cutoff {cutoff.isoformat()}",
            ))
            continue
        if fact.valid_to is not None and cutoff >= fact.valid_to:
            exclusions.append(SnapshotExclusion(
                exclusion_id=f"ex_{fact.fact_version_id}_expired_validity",
                record_id=fact.fact_version_id,
                fact_version_id=fact.fact_version_id,
                reason_code="EXPIRED_WORLD_VALIDITY",
                severity="INFO",
                stage="snapshot_builder",
                field="valid_to",
                detail=f"valid_to {fact.valid_to.isoformat()} <= cutoff {cutoff.isoformat()}",
            ))
            continue
        valid_facts.append(fact)

    # 3. Group by logical_fact_id and resolve append-only revision chains.
    accepted_by_id = {fact.fact_version_id: fact for fact in accepted_facts}
    for fact in accepted_facts:
        if not fact.supersedes_version_id:
            continue
        parent = accepted_by_id.get(fact.supersedes_version_id)
        if parent is None:
            raise ContractError(
                f"FactVersion {fact.fact_version_id} supersedes a parent that is missing "
                "or not known/accepted by this snapshot cutoff."
            )
        if parent.logical_fact_id != fact.logical_fact_id:
            raise ContractError(
                f"FactVersion {fact.fact_version_id} supersedes a different LogicalFactID."
            )

    # Retractions are tombstones, not ordinary world-state assertions. Keep
    # only tombstones already known/accepted and effective by the cutoff; their
    # target may have expired from the world-valid set above.
    retracted_version_ids = {
        fact.supersedes_version_id
        for fact in accepted_facts
        if fact.revision_type == "retraction"
        and fact.supersedes_version_id
        and (fact.valid_from is None or fact.valid_from <= cutoff)
    }

    logical_groups: dict[str, list[FactVersion]] = {}
    for f in valid_facts:
        logical_groups.setdefault(f.logical_fact_id, []).append(f)

    active_facts: list[FactVersion] = []

    for versions in logical_groups.values():
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

        for v in versions:
            current_id = v.fact_version_id
            is_superseded = current_id in superseded_by
            parent_id = v.supersedes_version_id
            lost_tiebreaker = (
                parent_id is not None
                and parent_id in superseded_by
                and current_id != superseded_by[parent_id]
            )

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
                        reason_code="RETRACTION_TOMBSTONE",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="revision_type",
                        detail="Retraction is retained as a tombstone, not materialized as a fact edge"
                    )
                )
                continue

            if v.fact_version_id in retracted_version_ids:
                exclusions.append(
                    SnapshotExclusion(
                        exclusion_id=f"ex_{v.fact_version_id}_retracted",
                        record_id=v.fact_version_id,
                        fact_version_id=v.fact_version_id,
                        reason_code="RETRACTED",
                        severity="INFO",
                        stage="snapshot_builder",
                        field="supersedes_version_id",
                        detail="A known, effective retraction supersedes this fact version"
                    )
                )
                continue

            active_facts.append(v)

    # 4. Apply the cutoff-specific mapping only after knowledge, validity,
    # revisions, and tombstones. Never rewrite FactVersion or LogicalFactID.
    edge_groups: dict[tuple[str, str, str], list[FactVersion]] = {}
    for f in active_facts:
        subject_mapping = resolve_entity_mapping_at_cutoff(f.subject_id, entity_mappings, cutoff)
        object_mapping = resolve_entity_mapping_at_cutoff(f.object_id, entity_mappings, cutoff)
        subject_id = subject_mapping.canonical_entity_id if subject_mapping else f.subject_id
        object_id = object_mapping.canonical_entity_id if object_mapping else f.object_id
        key = (subject_id, f.relation_id, object_id)
        edge_groups.setdefault(key, []).append(f)

    edges: list[SnapshotEdge] = []
    support_records: list[SnapshotEdgeSupport] = []

    for (s_id, r_id, o_id), supporting_facts in edge_groups.items():
        edge_hash = hashlib.sha256(f"{s_id}|{r_id}|{o_id}".encode("utf-8")).hexdigest()[:16]
        edge_id = f"edge_{snapshot_id}_{edge_hash}"
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

            if provenance_map is None:
                raw_hash = fv.evidence_text_hash if len(fv.evidence_text_hash) == 64 else ("0" * 64)
                claim_ids = fv.supporting_claim_ids or (f"claim_{fv.fact_version_id}",)
                for cid in claim_ids:
                    support_records.append(
                        SnapshotEdgeSupport(
                            support_id=f"{support_id}_{cid}",
                            provenance_id=f"prov_{cid}",
                            edge_id=edge_id,
                            fact_version_id=fv.fact_version_id,
                            claim_id=cid,
                            source_version_id=fv.source_id,
                            raw_blob_sha256=raw_hash,
                        )
                    )
                continue

            if fv.fact_version_id not in provenance_map:
                raise ValueError(
                    f"Missing claim provenance for active fact version {fv.fact_version_id}"
                )
            provenance_rows = provenance_map[fv.fact_version_id]
            if not isinstance(provenance_rows, list) or not provenance_rows:
                raise ValueError(
                    f"Invalid claim provenance rows for active fact version {fv.fact_version_id}"
                )
            provenance_claim_ids = {row.get("claim_id") for row in provenance_rows}
            if provenance_claim_ids != set(fv.supporting_claim_ids):
                raise ValueError(
                    f"Claim provenance does not exactly match supporting claims for fact "
                    f"version {fv.fact_version_id}"
                )
            for prov in provenance_rows:
                required = (
                    "claim_id",
                    "membership_id",
                    "source_version_id",
                    "provenance_id",
                    "retrieval_id",
                    "raw_blob_sha256",
                )
                missing = [field for field in required if not prov.get(field)]
                if missing:
                    raise ValueError(
                        f"Incomplete claim provenance for fact version {fv.fact_version_id}: {missing}"
                    )
                provenance_claim_id = prov["claim_id"]
                if provenance_claim_id not in fv.supporting_claim_ids:
                    raise ValueError(
                        f"Provenance claim {provenance_claim_id} is not a supporter of fact "
                        f"version {fv.fact_version_id}"
                    )
                provenance_hash = prov["raw_blob_sha256"]
                if len(provenance_hash) != 64 or any(
                    ch not in "0123456789abcdef" for ch in provenance_hash
                ):
                    raise ValueError(
                        f"Invalid raw_blob_sha256 for fact version {fv.fact_version_id}"
                    )
                support_records.append(
                    SnapshotEdgeSupport(
                        support_id=(
                            f"{support_id}_"
                            f"{hashlib.sha256(prov['provenance_id'].encode('utf-8')).hexdigest()[:16]}"
                        ),
                        provenance_id=prov["provenance_id"],
                        edge_id=edge_id,
                        fact_version_id=fv.fact_version_id,
                        claim_id=provenance_claim_id,
                        source_version_id=prov["source_version_id"],
                        raw_blob_sha256=provenance_hash,
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

    for versions in logical_groups.values():
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
