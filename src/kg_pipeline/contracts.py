"""Versioned, narrow contracts for Ticket A's evidence inventory."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pyarrow as pa

CONTRACT_VERSION = "ticket_a_v1"

S = pa.string()
INT64 = pa.int64()
B = pa.bool_()


def _schema(*fields: tuple[str, pa.DataType]) -> pa.Schema:
    return pa.schema([pa.field("schema_version", S, nullable=False), *[pa.field(name, kind) for name, kind in fields]])


TABLE_SCHEMAS: dict[str, pa.Schema] = {
    "raw_inventory": _schema(
        ("inventory_row_id", S),
        ("raw_candidate_id", S),
        ("raw_kind", S),
        ("relative_path", S),
        ("raw_blob_sha256", S),
        ("filename_sha256", S),
        ("filename_hash_status", S),
        ("bytes", INT64),
        ("content_type_detected", S),
        ("content_type_basis", S),
        ("read_status", S),
        ("read_error", S),
        ("hash_computed_now", B),
        ("historical_hash_evidence_status", S),
        ("historical_hash_evidence_count", INT64),
        ("source_provenance_status", S),
        ("strict_input_eligible", B),
        ("unknown_reason", S),
    ),
    "raw_hash_audit": _schema(
        ("hash_audit_id", S),
        ("raw_candidate_id", S),
        ("relative_path", S),
        ("bytes", INT64),
        ("computed_sha256", S),
        ("hash_computed_now", B),
        ("filename_sha256", S),
        ("filename_hash_status", S),
        ("historical_hash_evidence_status", S),
        ("historical_hash_evidence_count", INT64),
        ("read_status", S),
        ("read_error", S),
    ),
    "retrievals": _schema(
        ("retrieval_id", S),
        ("raw_blob_sha256", S),
        ("source_id", S),
        ("requested_url", S),
        ("final_url", S),
        ("retrieved_at_real", S),
        ("archive_datetime", S),
        ("recorded_event_at", S),
        ("recorded_event_time_field", S),
        ("provenance_status", S),
        ("strict_source_input_eligible", B),
        ("evidence_path", S),
        ("evidence_locator", S),
        ("evidence_file_sha256", S),
        ("evidence_record_sha256", S),
    ),
    "source_versions": _schema(
        ("source_version_id", S),
        ("raw_blob_sha256", S),
        ("retrieval_id", S),
        ("source_id", S),
        ("canonical_or_final_url", S),
        ("retrieved_at_real", S),
        ("archive_datetime", S),
        ("source_version_status", S),
        ("strict_source_input_eligible", B),
        ("evidence_path", S),
        ("evidence_locator", S),
    ),
    "provenance_recovery_ledger": _schema(
        ("ledger_id", S),
        ("raw_blob_sha256", S),
        ("field_name", S),
        ("recovered_value", S),
        ("recovery_status", S),
        ("reason", S),
        ("evidence_path", S),
        ("evidence_locator", S),
        ("evidence_file_sha256", S),
    ),
    "body_variants": _schema(
        ("body_variant_id", S),
        ("body_text_sha256", S),
        ("body_blob_relative_path", S),
        ("parser_version", S),
        ("parser_fingerprint_sha256", S),
        ("decoder", S),
        ("selector", S),
        ("text_char_count", INT64),
        ("extraction_status", S),
        ("quality_flags_json", S),
    ),
    "document_memberships": _schema(
        ("membership_id", S),
        ("raw_blob_sha256", S),
        ("raw_candidate_id", S),
        ("body_variant_id", S),
        ("exact_cluster_id", S),
        ("retrieval_ids_json", S),
        ("source_provenance_status", S),
        ("strict_input_eligible", B),
        ("membership_status", S),
        ("reason", S),
    ),
    "document_clusters": _schema(
        ("cluster_id", S),
        ("cluster_type", S),
        ("body_variant_id", S),
        ("member_count", INT64),
        ("member_ids_json", S),
        ("dedup_method", S),
        ("policy_status", S),
    ),
    "lineage_edges": _schema(
        ("lineage_edge_id", S),
        ("from_source_version_id", S),
        ("to_source_version_id", S),
        ("relation_type", S),
        ("evidence_status", S),
        ("reason", S),
        ("evidence_path", S),
    ),
    "near_duplicate_candidates": _schema(
        ("candidate_id", S),
        ("left_body_variant_id", S),
        ("right_body_variant_id", S),
        ("candidate_generation_status", S),
        ("reason", S),
        ("policy_status", S),
    ),
    "missing_coverage_ledger": _schema(
        ("issue_id", S),
        ("issue_type", S),
        ("raw_candidate_id", S),
        ("raw_blob_sha256", S),
        ("severity", S),
        ("blocks_strict_input", B),
        ("reason", S),
        ("recommended_next_action", S),
    ),
    "coverage_ledger": _schema(
        ("coverage_row_id", S),
        ("upstream_scope", S),
        ("upstream_observation_count", INT64),
        ("upstream_unique_url_count", INT64),
        ("raw_blob_count", INT64),
        ("recovered_retrieval_count", INT64),
        ("strict_retrieval_count", INT64),
        ("comparison_status", S),
        ("reason", S),
    ),
}

PRIMARY_KEYS: dict[str, list[str]] = {
    "raw_inventory": ["inventory_row_id"],
    "raw_hash_audit": ["hash_audit_id"],
    "retrievals": ["retrieval_id"],
    "source_versions": ["source_version_id"],
    "provenance_recovery_ledger": ["ledger_id"],
    "body_variants": ["body_variant_id"],
    "document_memberships": ["membership_id"],
    "document_clusters": ["cluster_id"],
    "lineage_edges": ["lineage_edge_id"],
    "near_duplicate_candidates": ["candidate_id"],
    "missing_coverage_ledger": ["issue_id"],
    "coverage_ledger": ["coverage_row_id"],
}

FOREIGN_KEYS: dict[str, dict[str, tuple[str, str]]] = {
    "raw_hash_audit": {"raw_candidate_id": ("raw_inventory", "raw_candidate_id")},
    "retrievals": {"raw_blob_sha256": ("raw_inventory", "raw_blob_sha256")},
    "source_versions": {
        "raw_blob_sha256": ("raw_inventory", "raw_blob_sha256"),
        "retrieval_id": ("retrievals", "retrieval_id")
    },
    "body_variants": {},
    "document_memberships": {
        "raw_blob_sha256": ("raw_inventory", "raw_blob_sha256"),
        "raw_candidate_id": ("raw_inventory", "raw_candidate_id"),
        "body_variant_id": ("body_variants", "body_variant_id"),
        "exact_cluster_id": ("document_clusters", "cluster_id"),
    },
    "document_clusters": {"body_variant_id": ("body_variants", "body_variant_id")},
    "lineage_edges": {
        "from_source_version_id": ("source_versions", "source_version_id"),
        "to_source_version_id": ("source_versions", "source_version_id"),
    },
    "near_duplicate_candidates": {
        "left_body_variant_id": ("body_variants", "body_variant_id"),
        "right_body_variant_id": ("body_variants", "body_variant_id"),
    },
    "missing_coverage_ledger": {},
    "coverage_ledger": {},
    "provenance_recovery_ledger": {"raw_blob_sha256": ("raw_inventory", "raw_blob_sha256")},
}

class ContractError(ValueError):
    pass


def make_row(table_name: str, **values: Any) -> dict[str, Any]:
    if table_name not in TABLE_SCHEMAS:
        raise ContractError(f"Unknown Ticket A table: {table_name}")
    allowed = set(TABLE_SCHEMAS[table_name].names)
    unexpected = set(values) - allowed
    if unexpected:
        raise ContractError(f"Unexpected fields for {table_name}: {sorted(unexpected)}")
    row = {field: None for field in TABLE_SCHEMAS[table_name].names}
    row["schema_version"] = CONTRACT_VERSION
    row.update(values)
    return row


def validate_rows(table_name: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate fields shared by storage and tests before Parquet serialization."""

    import re

    normalized = []
    schema = TABLE_SCHEMAS[table_name]
    fields = set(schema.names)
    pks = PRIMARY_KEYS.get(table_name, [])

    seen_pks = set()

    for index, original in enumerate(rows):
        unexpected = set(original) - fields
        if unexpected:
            raise ContractError(f"{table_name}[{index}] has unexpected fields: {sorted(unexpected)}")
        row = {name: original.get(name) for name in schema.names}
        if row["schema_version"] != CONTRACT_VERSION:
            raise ContractError(f"{table_name}[{index}] schema_version must be {CONTRACT_VERSION}")

        # Check non-null for PKs
        pk_vals = []
        for pk in pks:
            val = row.get(pk)
            if not val:
                raise ContractError(f"{table_name}[{index}] missing required primary key: {pk}")
            pk_vals.append(val)

        if pks:
            pk_tuple = tuple(pk_vals)
            if pk_tuple in seen_pks:
                raise ContractError(f"{table_name}[{index}] duplicate primary key: {pk_tuple}")
            seen_pks.add(pk_tuple)

        # Check hash formats
        for field in fields:
            if field.endswith("_sha256") and row.get(field) is not None:
                val = row[field]
                if not isinstance(val, str) or not re.fullmatch(r"[0-9a-f]{64}", val):
                    raise ContractError(f"{table_name}[{index}] invalid hash format for {field}: {val}")

        normalized.append(row)

    if table_name == "retrievals":
        validate_retrieval_rows(normalized)
    return normalized


def validate_retrieval_rows(rows: Iterable[dict[str, Any]]) -> None:
    """Prevent an operational or discovery time being upgraded to retrieval evidence."""

    required_for_strict = ("raw_blob_sha256", "source_id", "final_url", "retrieved_at_real")
    for row in rows:
        if row.get("strict_source_input_eligible") and any(not row.get(name) for name in required_for_strict):
            missing = [name for name in required_for_strict if not row.get(name)]
            raise ContractError(
                "A strict retrieval requires raw hash, source, final URL, and retrieved_at_real; "
                f"missing {missing}"
            )
        if row.get("strict_source_input_eligible"):
            value = row["retrieved_at_real"]
            try:
                if not isinstance(value, str):
                    raise ValueError("timestamp must be a string")
                timestamp = datetime.fromisoformat(value)
                if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                    raise ValueError("explicit timezone is required")
            except (TypeError, ValueError) as exc:
                raise ContractError("Strict retrieved_at_real must be a valid timezone-aware ISO timestamp") from exc
        if row.get("recorded_event_time_field") in {"file_mtime", "published_at_declared", "inventory_at_real"}:
            raise ContractError("Ticket A must not use file or article metadata as acquisition evidence time")


def table_from_rows(table_name: str, rows: Iterable[dict[str, Any]]) -> pa.Table:
    if table_name not in TABLE_SCHEMAS:
        raise ContractError(f"Unknown Ticket A table: {table_name}")
    normalized = validate_rows(table_name, list(rows))
    return pa.Table.from_pylist(normalized, schema=TABLE_SCHEMAS[table_name])
