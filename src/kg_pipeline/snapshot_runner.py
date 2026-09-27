"""Snapshot execution stage producing deterministic point-in-time SnapshotEdge and support tables."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .claims import resolve_claim_provenance
from .contracts import CONTRACT_VERSION
from .hashing import stable_id, utc_now_iso
from .run import create_stage_manifest, get_run_dir, resolve_run_table_path
from .storage import read_yaml, write_parquet_immutable, write_yaml_immutable
from temporal.schema import ClaimCandidate, EntityMappingVersion, FactVersion
from temporal.snapshot import build_snapshot_edges_and_support, create_snapshot_manifest

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
        if ev_obs is None or ing_dt is None:
            raise ValueError("evidence_observed_at and ingested_at_real are required")

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
    provenance_rows = pq.read_table(claim_provenance_path).to_pylist()
    upstream_tables = {
        name: resolve_run_table_path(repo_root, run_id, name)
        for name in ("extracted_claims", "document_memberships", "retrievals", "source_versions")
    }
    for table_name, path in upstream_tables.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing required {table_name} provenance table: {path}")

    claim_rows = pq.read_table(upstream_tables["extracted_claims"]).to_pylist()
    memberships = pq.read_table(upstream_tables["document_memberships"]).to_pylist()
    retrievals = pq.read_table(upstream_tables["retrievals"]).to_pylist()
    source_versions = pq.read_table(upstream_tables["source_versions"]).to_pylist()
    claim_by_id = {row.get("claim_id"): row for row in claim_rows}
    if None in claim_by_id or len(claim_by_id) != len(claim_rows):
        raise ValueError("Duplicate or missing claim_id in extracted_claims table")
    missing_claim_ids = set(fact_id_by_claim) - set(claim_by_id)
    if missing_claim_ids:
        raise ValueError(
            f"Fact-version supporting claim IDs are missing from extracted_claims: {sorted(missing_claim_ids)}"
        )
    expected_provenance = resolve_claim_provenance(
        claims=[
            ClaimCandidate(
                claim_id=row["claim_id"],
                body_variant_id=row.get("body_variant_id") or "",
                subject_mention=row.get("subject_mention") or "",
                relation_name=row.get("relation_name") or "",
                object_mention=row.get("object_mention") or "",
                evidence_span_start=int(row["evidence_span_start"]) if row.get("evidence_span_start") is not None else 0,
                evidence_span_end=(
                    int(row["evidence_span_end"])
                    if row.get("evidence_span_end") is not None and int(row["evidence_span_end"]) > (int(row["evidence_span_start"]) if row.get("evidence_span_start") is not None else 0)
                    else ((int(row["evidence_span_start"]) if row.get("evidence_span_start") is not None else 0) + 1)
                ),
                evidence_text_hash=row.get("evidence_text_hash") or ("a" * 64),
            )
            for row in claim_rows
        ],
        memberships=memberships,
        retrievals=retrievals,
        source_versions=source_versions,
    )
    expected_by_id: dict[str, dict[str, str]] = {}
    for prov in expected_provenance:
        row = {
            "claim_id": prov.claim_id,
            "membership_id": prov.membership_id,
            "source_version_id": prov.source_version_id,
            "retrieval_id": prov.retrieval_id,
            "raw_blob_sha256": prov.raw_blob_sha256,
            "publisher_source_id": prov.publisher_source_id,
            "source_url": prov.source_url,
        }
        row["provenance_id"] = stable_id("claimprovenance", {
            "claim_id": prov.claim_id,
            "membership_id": prov.membership_id,
            "source_version_id": prov.source_version_id,
            "retrieval_id": prov.retrieval_id,
            "raw_blob_sha256": prov.raw_blob_sha256,
        })
        if row["provenance_id"] in expected_by_id:
            raise ValueError(f"Duplicate canonical claim provenance identity {row['provenance_id']}")
        expected_by_id[row["provenance_id"]] = row

    actual_by_id: dict[str, dict[str, str]] = {}
    for p in provenance_rows:
        provenance_id = p.get("provenance_id")
        if not provenance_id or provenance_id in actual_by_id:
            raise ValueError("Duplicate or missing provenance_id in claim_provenance table")
        actual_by_id[provenance_id] = {
            field: p.get(field)
            for field in (
                "claim_id", "membership_id", "source_version_id", "retrieval_id",
                "raw_blob_sha256", "publisher_source_id", "source_url", "provenance_id",
            )
        }
    if actual_by_id != expected_by_id:
        raise ValueError("claim_provenance does not match canonical membership/retrieval/source-version chain")

    provenance_map: dict[str, list[dict[str, str]]] = {}
    for p in provenance_rows:
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
            continue
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

    # Load entity mappings if available
    entity_mappings: list[EntityMappingVersion] = []
    ent_map_path = run_dir / "tables" / "entity_mappings.parquet"
    if not ent_map_path.is_file():
        try:
            ent_map_path = resolve_run_table_path(repo_root, run_id, "entity_mappings")
        except Exception:
            pass
    if ent_map_path.is_file():
        ent_table = pq.read_table(ent_map_path).to_pylist()
        for erow in ent_table:
            avail_dt = _parse_tz_datetime(erow.get("mapping_available_at"), field="mapping_available_at")
            if avail_dt:
                entity_mappings.append(
                    EntityMappingVersion(
                        entity_mapping_id=erow.get("entity_mapping_id", ""),
                        mention=erow.get("mention", ""),
                        canonical_entity_id=erow.get("canonical_entity_id", ""),
                        mapping_available_at=avail_dt,
                        entity_map_version=erow.get("entity_map_version", "ticket_a_v1"),
                        supersedes_mapping_id=erow.get("supersedes_mapping_id"),
                        mapping_basis=erow.get("mapping_basis", "catalog"),
                        mapping_confidence=float(erow.get("mapping_confidence", 1.0)),
                    )
                )

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
            entity_mappings=entity_mappings,
            provenance_map=provenance_map,
        )

        snapshot_dir = run_dir / "snapshots" / s_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snap_edges_rows = []
        for e in edges:
            row = {
                "schema_version": CONTRACT_VERSION,
                "edge_id": e.edge_id,
                "subject_id": e.subject_id,
                "relation_id": e.relation_id,
                "object_id": e.object_id,
                "snapshot_id": e.snapshot_id,
            }
            snap_edges_rows.append(row)
            key = (e.snapshot_id, e.subject_id, e.relation_id, e.object_id)
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                all_edges.append(row)

        snap_supports_rows = []
        for s in supports:
            row = {
                "schema_version": CONTRACT_VERSION,
                "support_id": s.support_id,
                "provenance_id": s.provenance_id,
                "edge_id": s.edge_id,
                "fact_version_id": s.fact_version_id,
                "claim_id": s.claim_id,
                "source_version_id": s.source_version_id,
                "raw_blob_sha256": s.raw_blob_sha256,
            }
            snap_supports_rows.append(row)
            all_supports.append(row)

        snap_exclusions_rows = []
        for ex in exclusions:
            ex_id = f"{s_id}_{ex.exclusion_id}" if not ex.exclusion_id.startswith(f"{s_id}_") else ex.exclusion_id
            row = {
                "schema_version": CONTRACT_VERSION,
                "exclusion_id": ex_id,
                "record_id": ex.record_id,
                "fact_version_id": ex.fact_version_id,
                "reason_code": ex.reason_code,
                "severity": ex.severity,
                "stage": ex.stage,
                "field": ex.field,
                "detail": ex.detail,
            }
            snap_exclusions_rows.append(row)
            all_exclusions.append(row)

        # 5a. Write isolated per-snapshot Parquet and manifest
        write_parquet_immutable(
            snapshot_dir / "snapshot_edges.parquet",
            "snapshot_edges",
            snap_edges_rows,
        )
        write_parquet_immutable(
            snapshot_dir / "snapshot_edge_support.parquet",
            "snapshot_edge_support",
            snap_supports_rows,
        )
        write_parquet_immutable(
            snapshot_dir / "snapshot_exclusions.parquet",
            "snapshot_exclusions",
            snap_exclusions_rows,
        )

        s_manifest = create_snapshot_manifest(
            snapshot_id=s_id,
            cutoff=s_cutoff,
            edges=edges,
            support_records=supports,
            exclusions=exclusions,
            fact_versions=facts,
        )
        write_yaml_immutable(
            snapshot_dir / "snapshot_manifest.yaml",
            asdict(s_manifest),
        )

    # 5b. Write combined Parquet artifacts in tables/ for backward compatibility
    edges_parquet = run_dir / "tables" / "snapshot_edges.parquet"
    supports_parquet = run_dir / "tables" / "snapshot_edge_support.parquet"
    exclusions_parquet = run_dir / "tables" / "snapshot_exclusions.parquet"

    write_parquet_immutable(
        edges_parquet,
        "snapshot_edges",
        all_edges,
    )
    write_parquet_immutable(
        supports_parquet,
        "snapshot_edge_support",
        all_supports,
    )
    write_parquet_immutable(
        exclusions_parquet,
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

    create_stage_manifest(
        repo_root,
        run_id,
        "snapshot_stage",
        input_artifacts=[
            {"table": "fact_versions", "path": str(fact_versions_path)},
            {"table": "claim_provenance", "path": str(claim_provenance_path)},
        ],
        output_artifacts=[
            {"table": "snapshot_edges", "path": str(edges_parquet), "count": len(all_edges)},
            {"table": "snapshot_edge_support", "path": str(supports_parquet), "count": len(all_supports)},
            {"table": "snapshot_exclusions", "path": str(exclusions_parquet), "count": len(all_exclusions)},
        ],
        conservation_metrics={
            "cutoffs_count": len(target_cutoffs),
            "fact_versions_count": len(facts),
            "unique_edges_count": len(all_edges),
            "edge_supports_count": len(all_supports),
            "exclusions_count": len(all_exclusions),
        },
    )

    return {
        "status": "COMPLETED",
        "run_id": run_id,
        "cutoffs_count": len(target_cutoffs),
        "total_edges": len(all_edges),
        "total_supports": len(all_supports),
        "total_exclusions": len(all_exclusions),
    }
