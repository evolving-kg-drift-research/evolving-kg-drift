"""Snapshot execution stage producing deterministic point-in-time SnapshotEdge and support tables."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .contracts import CONTRACT_VERSION
from .hashing import utc_now_iso
from .run import get_run_dir, resolve_run_table_path
from .storage import read_yaml, write_parquet_immutable, write_yaml_immutable
from temporal.schema import FactVersion
from temporal.snapshot import build_snapshot_edges_and_support

logger = logging.getLogger(__name__)


def _parse_tz_datetime(val: Any, *, field: str, required: bool = False) -> datetime | None:
    if val is None or val == "":
        if required:
            raise ValueError(f"Missing required snapshot field: {field}")
        return None
    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid {field} timestamp: {val}") from exc
    else:
        raise ValueError(f"Invalid {field} timestamp type: {type(val).__name__}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} timestamp must include an explicit timezone")
    return dt


def _required(row: dict[str, Any], field: str) -> Any:
    value = row.get(field)
    if value is None or value == "":
        raise ValueError(f"Missing required snapshot field: {field}")
    return value


def _required_int(row: dict[str, Any], field: str) -> int:
    value = _required(row, field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid required snapshot field: {field}")
    return value


def run_snapshot(
    repo_root: Path,
    run_id: str,
    *,
    cutoff_iso: str | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    run_dir = get_run_dir(repo_root, run_id)
    (run_dir / "tables").mkdir(parents=True, exist_ok=True)
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)

    # 1. Resolve fact_versions table
    fact_versions_path = resolve_run_table_path(repo_root, run_id, "fact_versions")
    if not fact_versions_path.is_file():
        raise FileNotFoundError(f"Missing {fact_versions_path} for run {run_id}")

    table = pq.read_table(fact_versions_path)
    fact_rows = table.to_pylist()
    facts: list[FactVersion] = []
    fact_id_by_claim: dict[str, str] = {}
    claim_ids_by_fact: dict[str, list[str]] = {}

    for row in fact_rows:
        valid_from = _parse_tz_datetime(row.get("valid_from"), field="valid_from")
        valid_to = _parse_tz_datetime(row.get("valid_to"), field="valid_to")
        ev_obs = _parse_tz_datetime(
            row.get("evidence_observed_at"), field="evidence_observed_at", required=True
        )
        ing_dt = _parse_tz_datetime(
            row.get("ingested_at_real"), field="ingested_at_real", required=True
        )

        source_id = _required(row, "source_id")
        source_url = _required(row, "source_url")
        evidence_hash = _required(row, "evidence_text_hash")
        if evidence_hash in {"placeholder", "placeholder_hash"}:
            raise ValueError("Invalid required snapshot field: evidence_text_hash")
        span_start = _required_int(row, "evidence_span_start")
        span_end = _required_int(row, "evidence_span_end")
        if span_start >= span_end:
            raise ValueError("Invalid evidence span: evidence_span_start must be less than evidence_span_end")
        if not _required(row, "extractor_version"):
            raise ValueError("Missing required snapshot field: extractor_version")
        if not _required(row, "entity_map_version"):
            raise ValueError("Missing required snapshot field: entity_map_version")

        fact_version_id = _required(row, "fact_version_id")
        supporting_claim_ids = row.get("supporting_claim_ids")
        if isinstance(supporting_claim_ids, str):
            try:
                supporting_claim_ids = json.loads(supporting_claim_ids)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid supporting_claim_ids JSON") from exc
        if not isinstance(supporting_claim_ids, list) or not supporting_claim_ids:
            raise ValueError("Missing required snapshot field: supporting_claim_ids")
        if any(not isinstance(claim_id, str) or not claim_id for claim_id in supporting_claim_ids):
            raise ValueError("Invalid supporting_claim_ids entry")
        if len(set(supporting_claim_ids)) != len(supporting_claim_ids):
            raise ValueError(f"Duplicate supporting_claim_ids for fact version {fact_version_id}")
        for claim_id in supporting_claim_ids:
            if claim_id in fact_id_by_claim:
                raise ValueError(f"Claim {claim_id} links to multiple fact versions")
            fact_id_by_claim[claim_id] = fact_version_id
        claim_ids_by_fact[fact_version_id] = supporting_claim_ids
        facts.append(
            FactVersion(
                fact_version_id=fact_version_id,
                logical_fact_id=_required(row, "logical_fact_id"),
                subject_id=_required(row, "subject_id"),
                relation_id=_required(row, "relation_id"),
                object_id=_required(row, "object_id"),
                valid_from=valid_from,
                valid_to=valid_to,
                evidence_observed_at=ev_obs,
                ingested_at_real=ing_dt,
                supersedes_version_id=row.get("supersedes_version_id"),
                revision_type=_required(row, "revision_type"),
                source_id=source_id,
                source_url=source_url,
                evidence_span_start=span_start,
                evidence_span_end=span_end,
                evidence_text_hash=evidence_hash,
                extractor_version=row["extractor_version"],
                entity_map_version=row["entity_map_version"],
                confidence=row.get("confidence"),
                adjudication_status=_required(row, "adjudication_status"),
                supporting_claim_ids=tuple(supporting_claim_ids),
            )
        )

    # 2. Build the exact fact-version-to-claim provenance map.
    claim_provenance_path = resolve_run_table_path(repo_root, run_id, "claim_provenance")
    if not claim_provenance_path.is_file():
        raise FileNotFoundError(f"Missing {claim_provenance_path} for run {run_id}")
    provenance_map: dict[str, list[dict[str, str]]] = {}
    for p in pq.read_table(claim_provenance_path).to_pylist():
        cid = p.get("claim_id")
        source_version_id = p.get("source_version_id")
        membership_id = p.get("membership_id")
        provenance_id = p.get("provenance_id")
        retrieval_id = p.get("retrieval_id")
        raw_blob_sha256 = p.get("raw_blob_sha256")
        if not all((provenance_id, cid, source_version_id, membership_id, retrieval_id, raw_blob_sha256)):
            raise ValueError(
                "Claim provenance rows require provenance_id, claim_id, membership_id, "
                "source_version_id, retrieval_id, and raw_blob_sha256"
            )
        if len(raw_blob_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in raw_blob_sha256):
            raise ValueError(f"Invalid claim provenance raw_blob_sha256 for claim {cid}")
        fact_version_id = fact_id_by_claim.get(cid)
        if fact_version_id is None:
            raise ValueError(f"Claim provenance does not resolve to a fact version for claim {cid}")
        provenance_map.setdefault(fact_version_id, []).append({
            "provenance_id": provenance_id,
            "claim_id": cid,
            "membership_id": membership_id,
            "source_version_id": source_version_id,
            "retrieval_id": retrieval_id,
            "raw_blob_sha256": raw_blob_sha256,
        })

    missing_provenance = sorted(
        (fact_version_id, claim_id)
        for fact_version_id, claim_ids in claim_ids_by_fact.items()
        for claim_id in claim_ids
        if not any(
            row["claim_id"] == claim_id
            for row in provenance_map.get(fact_version_id, [])
        )
    )
    if missing_provenance:
        raise ValueError(f"Missing claim provenance links: {missing_provenance[:5]}")
    for fact_version_id, rows in provenance_map.items():
        rows.sort(key=lambda row: (
            row["provenance_id"], row["claim_id"], row["membership_id"],
            row["source_version_id"], row["retrieval_id"], row["raw_blob_sha256"],
        ))
        keys = [tuple(row[field] for field in (
            "provenance_id", "claim_id", "membership_id", "source_version_id",
            "retrieval_id", "raw_blob_sha256",
        )) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate claim provenance rows for fact version {fact_version_id}")
    for fact_version_id, claim_ids in claim_ids_by_fact.items():
        extra_claim_ids = {
            row["claim_id"] for row in provenance_map.get(fact_version_id, [])
        } - set(claim_ids)
        if extra_claim_ids:
            raise ValueError(
                f"Unexpected provenance claims for fact version {fact_version_id}: "
                f"{sorted(extra_claim_ids)}"
            )

    # 3. Determine cutoffs
    target_cutoffs: list[tuple[str, datetime]] = []
    if cutoff_iso:
        dt = _parse_tz_datetime(cutoff_iso, field="cutoff", required=True)
        if not dt:
            raise ValueError(f"Invalid cutoff timestamp: {cutoff_iso}")
        sid = snapshot_id or f"snap_{dt.strftime('%Y%m%d')}"
        target_cutoffs.append((sid, dt))
    else:
        cfg_path = repo_root / "config" / "snapshot_cutoffs.yaml"
        if cfg_path.is_file():
            cfg_data = read_yaml(cfg_path)
            prov_list = cfg_data.get("operational_snapshots", {}).get("provisional_cutoffs", [])
            for c_entry in prov_list:
                cid = c_entry.get("id")
                c_str = c_entry.get("cutoff")
                c_dt = _parse_tz_datetime(c_str, field="operational snapshot cutoff")
                if not cid or not c_dt:
                    raise ValueError("Operational snapshot cutoff entries require an id and cutoff")
                target_cutoffs.append((cid, c_dt))

        if not target_cutoffs:
            raise ValueError("No explicit cutoff or configured operational snapshot cutoffs are available")

    # 4. Execute snapshot building across cutoffs
    all_edges: list[dict[str, Any]] = []
    all_supports: list[dict[str, Any]] = []
    all_exclusions: list[dict[str, Any]] = []
    seen_edge_keys: set[tuple[str, str, str, str]] = set()

    for s_id, s_cutoff in target_cutoffs:
        edges, supports, exclusions = build_snapshot_edges_and_support(
            fact_versions=facts,
            cutoff=s_cutoff,
            snapshot_id=s_id,
            provenance_map=provenance_map,
        )

        for e in edges:
            key = (e.snapshot_id, e.subject_id, e.relation_id, e.object_id)
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                all_edges.append({
                    "edge_id": e.edge_id,
                    "subject_id": e.subject_id,
                    "relation_id": e.relation_id,
                    "object_id": e.object_id,
                    "snapshot_id": e.snapshot_id,
                })

        for s in supports:
            all_supports.append({
                "support_id": s.support_id,
                "provenance_id": s.provenance_id,
                "edge_id": s.edge_id,
                "fact_version_id": s.fact_version_id,
                "claim_id": s.claim_id,
                "source_version_id": s.source_version_id,
                "raw_blob_sha256": s.raw_blob_sha256,
            })

        for ex in exclusions:
            all_exclusions.append({
                "exclusion_id": ex.exclusion_id,
                "record_id": ex.record_id,
                "fact_version_id": ex.fact_version_id,
                "reason_code": ex.reason_code,
                "severity": ex.severity,
                "stage": ex.stage,
                "field": ex.field,
                "detail": ex.detail,
            })

    # 5. Write immutable Parquet artifacts
    write_parquet_immutable(
        run_dir / "tables" / "snapshot_edges.parquet",
        "snapshot_edges",
        all_edges,
    )
    write_parquet_immutable(
        run_dir / "tables" / "snapshot_edge_support.parquet",
        "snapshot_edge_support",
        all_supports,
    )
    write_parquet_immutable(
        run_dir / "tables" / "snapshot_exclusions.parquet",
        "snapshot_exclusions",
        all_exclusions,
    )

    manifest_data = {
        "schema_version": CONTRACT_VERSION,
        "run_id": run_id,
        "created_at_real": utc_now_iso(),
        "cutoffs": [
            {"snapshot_id": sid, "cutoff": dt.isoformat()}
            for sid, dt in target_cutoffs
        ],
        "total_unique_edges": len(all_edges),
        "total_edge_supports": len(all_supports),
        "total_exclusions": len(all_exclusions),
    }
    write_yaml_immutable(
        run_dir / "reports" / "snapshot_manifest.yaml",
        manifest_data,
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "cutoffs_count": len(target_cutoffs),
        "total_edges": len(all_edges),
        "total_supports": len(all_supports),
        "total_exclusions": len(all_exclusions),
    }
