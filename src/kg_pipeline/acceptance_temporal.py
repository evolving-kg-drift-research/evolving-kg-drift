"""Deterministic occurrence identity, reviewed clocks and independent snapshot reconstruction."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .acceptance_contract import utc_timestamp
from .evidence import EvidenceSpan
from .hashing import sha256_json, stable_id
from .rebuild_artifacts import RebuildBlocked


def occurrence_id(body_variant_id: str, text: str, start: int, end: int, *,
                  normalization_version: str, mention_rule_version: str) -> str:
    if not body_variant_id or not mention_rule_version:
        raise RebuildBlocked("Occurrence identity requires explicit body/rule versions")
    span = EvidenceSpan.from_text(text, start, end, normalization_version)
    return stable_id("mention", {"body_variant_id": body_variant_id, "body_sha256": span.clean_text_sha256,
                                "start": start, "end": end, "normalization_version": normalization_version,
                                "mention_rule_version": mention_rule_version})


def observed_at(proof: dict[str, Any], *, body_sha256: str, policy: dict[str, Any]) -> str:
    allowed = policy.get("observation_basis")
    if not isinstance(allowed, list) or not allowed or proof.get("basis") not in allowed:
        raise RebuildBlocked("Unregistered observation basis")
    if (proof.get("body_sha256") != body_sha256 or not proof.get("proof_ref")
            or not proof.get("content_version_id") or not proof.get("original_url")):
        raise RebuildBlocked("Observation proof must bind exact public content version")
    return utc_timestamp(proof.get("observed_at"))


def acceptance_at(supports: list[dict[str, Any]], mappings: list[dict[str, Any]],
                  review: dict[str, Any]) -> str:
    if (review.get("decision") != "accept" or not review.get("reviewer_id")
            or not review.get("basis_ref") or not supports or not mappings):
        raise RebuildBlocked("Explicit reviewer acceptance and support/mapping proofs required")
    ids = [s["claim_id"] for s in supports]
    if len(set(ids)) != len(ids) or sorted(ids) != review.get("sufficient_support_claim_ids"):
        raise RebuildBlocked("Selected sufficient supports differ from reviewed support set")
    origins = [s.get("independent_origin_id") for s in supports]
    if any(not origin for origin in origins) or len(set(origins)) != len(origins):
        raise RebuildBlocked("Selected supports need attested independent origins")
    times = []
    for support in supports:
        if not support.get("proof_ref") or not support.get("origin_basis_ref"):
            raise RebuildBlocked("Missing support observation/independence evidence")
        times.append(utc_timestamp(support.get("observed_at")))
    for mapping in mappings:
        if not mapping.get("availability_basis_ref"):
            raise RebuildBlocked("Missing mapping availability evidence")
        times.append(utc_timestamp(mapping.get("mapping_available_at")))
    # datetime comparison also handles timestamps whose fractional-second precision differs.
    result = max(times, key=datetime.fromisoformat)
    if review.get("accepted_into_kg_at") != result:
        raise RebuildBlocked("Reviewed acceptance clock differs from sufficient-support availability")
    return result


def snapshot_triples(
    facts: list[dict[str, Any]], mappings: list[dict[str, Any]], cutoff: str, *,
    policy: dict[str, Any],
) -> tuple[list[tuple[str, str, str]], list[dict[str, str]]]:
    """Reconstruct from registered fact-to-mapping links, never a current name catalog.

    The caller verifies schemas, evidence refs and policy approvals before using
    this independent reconstruction as one part of G1.
    """
    at = datetime.fromisoformat(utc_timestamp(cutoff))
    revisions = policy.get("revision_types")
    tombstones = policy.get("tombstone_types")
    if (not isinstance(revisions, list) or not revisions or not isinstance(tombstones, list)
            or not set(tombstones) <= set(revisions)):
        raise RebuildBlocked("Registered revision/tombstone semantics required")
    index = {}
    for fact in facts:
        fid = fact.get("FactVersionID")
        if not fid or fid in index or fact.get("revision_type") not in revisions:
            raise RebuildBlocked("Invalid fact/revision identity")
        index[fid] = fact
    for fid, fact in index.items():
        visited = {fid}
        parent = fact.get("supersedes_version_id")
        while parent is not None:
            if parent not in index or parent in visited or index[parent]["LogicalFactID"] != fact["LogicalFactID"]:
                raise RebuildBlocked("Missing/cyclic/cross-fact revision parent")
            if datetime.fromisoformat(utc_timestamp(index[parent]["evidence_observed_at"])) > datetime.fromisoformat(
                    utc_timestamp(fact["evidence_observed_at"])):
                raise RebuildBlocked("Revision parent was not observable before child")
            visited.add(parent)
            parent = index[parent].get("supersedes_version_id")
    mapping_index = {}
    for mapping in mappings:
        mid = mapping.get("entity_mapping_id")
        if not mid or mid in mapping_index or not mapping.get("availability_basis_ref"):
            raise RebuildBlocked("Mapping identity/availability proof missing or duplicated")
        utc_timestamp(mapping.get("mapping_available_at"))
        mapping_index[mid] = mapping
    eligible = {}
    excluded = []
    for fid, fact in index.items():
        observed = datetime.fromisoformat(utc_timestamp(fact.get("evidence_observed_at")))
        accepted = datetime.fromisoformat(utc_timestamp(fact.get("accepted_into_kg_at")))
        start = datetime.fromisoformat(utc_timestamp(fact.get("valid_from")))
        end = datetime.fromisoformat(utc_timestamp(fact["valid_to"])) if fact.get("valid_to") is not None else None
        if accepted < observed or (end is not None and end <= start):
            raise RebuildBlocked("Invalid acceptance/validity interval")
        reason = None
        if observed > at:
            reason = "FUTURE_EVIDENCE"
        elif accepted > at:
            reason = "NOT_ACCEPTED_AS_OF"
        elif start > at or (end is not None and at >= end):
            reason = "NOT_WORLD_VALID_AS_OF"
        if reason:
            excluded.append({"FactVersionID": fid, "reason_code": reason})
        else:
            eligible[fid] = fact
    superseded = {f["supersedes_version_id"] for f in eligible.values() if f.get("supersedes_version_id") in eligible}
    active = [f for fid, f in eligible.items() if fid not in superseded]
    logical = {}
    triples = set()
    for fact in active:
        key = fact["LogicalFactID"]
        if key in logical:
            raise RebuildBlocked("Competing active revisions require adjudication")
        logical[key] = fact["FactVersionID"]
        if fact["revision_type"] in tombstones:
            excluded.append({"FactVersionID": fact["FactVersionID"], "reason_code": "TOMBSTONE"})
            continue
        if fact.get("object_id") is None:
            excluded.append({"FactVersionID": fact["FactVersionID"], "reason_code": "LITERAL_NOT_KGE_ENTITY"})
            continue
        mapping_ok = True
        for role in ("subject", "object"):
            mapping = mapping_index.get(fact.get(f"{role}_mapping_id"))
            if mapping is None or mapping.get("canonical_entity_id") != fact.get(f"{role}_id"):
                raise RebuildBlocked("Fact-to-mapping support is missing or inconsistent")
            if datetime.fromisoformat(utc_timestamp(mapping["mapping_available_at"])) > at:
                mapping_ok = False
        if not mapping_ok:
            excluded.append({"FactVersionID": fact["FactVersionID"], "reason_code": "FUTURE_MAPPING"})
            continue
        if not all(isinstance(fact.get(f), str) and fact[f] for f in ("subject_id", "relation_id", "object_id")):
            raise RebuildBlocked("Missing canonical triple identifier")
        triples.add((fact["subject_id"], fact["relation_id"], fact["object_id"]))
    return sorted(triples), sorted(excluded, key=lambda r: (r["FactVersionID"], r["reason_code"]))


def event_boundaries(events: list[dict[str, Any]], *, target: int, allowed: tuple[int, int]) -> dict[str, Any]:
    if type(target) is not int or not allowed[0] <= target <= allowed[1]:
        raise RebuildBlocked("Invalid registered boundary target/range")
    groups: dict[str, set[str]] = {}
    seen = set()
    for event in events:
        eid = event.get("event_id")
        if not eid or eid in seen or not event.get("time_basis_ref"):
            raise RebuildBlocked("Event requires unique identity and temporal basis")
        seen.add(eid)
        stamp = utc_timestamp(event.get("graph_effective_at"))
        groups.setdefault(stamp, set()).add(eid)
    ordered = sorted(groups, key=datetime.fromisoformat)
    total = len(events)
    if not total:
        raise RebuildBlocked("No graph change events")
    cumulative = []
    count = 0
    for stamp in ordered:
        count += len(groups[stamp])
        cumulative.append((stamp, count))
    selected = []
    for position in range(1, target + 1):
        # Integer distances avoid float/platform tie changes. Earlier time wins exact ties.
        stamp, _ = min(cumulative, key=lambda pair: (abs(pair[1] * target - total * position),
                                                    datetime.fromisoformat(pair[0])))
        selected.append(stamp)
    if len(set(selected)) != target:
        raise RebuildBlocked("INSUFFICIENT_DISTINCT_EVENT_BOUNDARIES")
    semantic = {"algorithm": "atomic-event-quantiles-v1", "target": target, "allowed": list(allowed),
                "events": sorted(events, key=lambda e: e["event_id"]), "cutoffs": selected}
    return {**semantic, "boundary_sha256": sha256_json(semantic)}
