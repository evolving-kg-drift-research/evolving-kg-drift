"""Typed public contracts for new runs; never implicitly activate a draft schema."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
import re
from pathlib import Path
from typing import Any

import pyarrow as pa
import yaml


class PublicContractError(ValueError):
    """An explicit public contract or row is incomplete or inconsistent."""


TYPES = {"string": pa.string(), "int64": pa.int64(), "double": pa.float64(),
         "bool": pa.bool_(), "list<item: string>": pa.list_(pa.string())}


def utc_timestamp(value: str | datetime) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublicContractError("Invalid UTC timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise PublicContractError("Timestamp requires an explicit timezone")
    return value.astimezone(timezone.utc).isoformat()


class PublicContract:
    """Validate exact names/types/PK/FK and lossless, explicit serializers.

    This engine can inspect a candidate specification. Constructing it is not
    schema approval, migration, or production certification.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        self.document = deepcopy(document)
        if not isinstance(document.get("schema_version"), str) or not document["schema_version"]:
            raise PublicContractError("Explicit schema_version required")
        self.schemas: dict[str, pa.Schema] = {}
        for name, definition in document.items():
            if name == "schema_version":
                continue
            fields, columns = definition.get("fields"), definition.get("columns")
            if not isinstance(fields, list) or not fields or len(set(fields)) != len(fields):
                raise PublicContractError(f"Invalid fields: {name}")
            if not isinstance(columns, dict) or set(columns) != set(fields):
                raise PublicContractError(f"Missing physical columns: {name}")
            primary = definition.get("primary_key")
            if not isinstance(primary, list) or not primary or len(set(primary)) != len(primary):
                raise PublicContractError(f"Missing primary key: {name}")
            if not set(primary) <= set(fields) or not isinstance(definition.get("foreign_keys"), dict):
                raise PublicContractError(f"Invalid keys: {name}")
            mapping = definition.get("serializer", {})
            if not isinstance(mapping, dict) or not set(mapping) <= set(fields):
                raise PublicContractError(f"Invalid serializer: {name}")
            model_fields = [mapping.get(f, f) for f in fields]
            if any(not isinstance(f, str) or not f for f in model_fields) or len(set(model_fields)) != len(fields):
                raise PublicContractError(f"Colliding serializer: {name}")
            domains = definition.get("domains", {})
            if not isinstance(domains, dict) or not set(domains) <= set(fields):
                raise PublicContractError(f"Invalid domains: {name}")
            if any(value not in {"utc_timestamp", "confidence", "sorted_unique_ids", "sha256"}
                   for value in domains.values()):
                raise PublicContractError(f"Unregistered domain validator: {name}")
            arrow_fields = []
            for field in fields:
                spec = columns[field]
                if spec.get("arrow_type") not in TYPES or type(spec.get("nullable")) is not bool:
                    raise PublicContractError(f"Undeclared physical type/nullability: {name}.{field}")
                if field in primary and spec["nullable"]:
                    raise PublicContractError(f"Nullable primary key: {name}.{field}")
                arrow_fields.append(pa.field(field, TYPES[spec["arrow_type"]], nullable=spec["nullable"]))
            self.schemas[name] = pa.schema(arrow_fields)
        for name, definition in self.tables.items():
            for field, target in definition["foreign_keys"].items():
                if (field not in definition["fields"] or not isinstance(target, list) or len(target) != 2
                        or target[0] not in self.schemas or target[1] not in self.schemas[target[0]].names):
                    raise PublicContractError(f"Invalid foreign key declaration: {name}.{field}")
                if self.schemas[name].field(field).type != self.schemas[target[0]].field(target[1]).type:
                    raise PublicContractError(f"Foreign key type mismatch: {name}.{field}")

    @property
    def tables(self) -> dict[str, Any]:
        return {k: v for k, v in self.document.items() if k != "schema_version"}

    @classmethod
    def load(cls, path: Path) -> PublicContract:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def validate(self, name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        definition = self.tables[name]
        primary = definition["primary_key"]
        seen = set()
        for row in rows:
            if set(row) != set(definition["fields"]):
                raise PublicContractError(f"Exact fields required: {name}")
            for field in self.schemas[name]:
                value = row[field.name]
                if value is None:
                    if not field.nullable:
                        raise PublicContractError(f"Null required field: {name}.{field.name}")
                    continue
                valid = (
                    (pa.types.is_string(field.type) and isinstance(value, str))
                    or (pa.types.is_boolean(field.type) and type(value) is bool)
                    or (pa.types.is_int64(field.type) and type(value) is int and -(2**63) <= value < 2**63)
                    or (pa.types.is_float64(field.type) and type(value) in {int, float} and math.isfinite(value))
                    or (pa.types.is_list(field.type) and isinstance(value, list)
                        and all(isinstance(v, str) for v in value))
                )
                if not valid:
                    raise PublicContractError(f"Wrong physical value: {name}.{field.name}")
                domain = definition.get("domains", {}).get(field.name)
                if domain == "utc_timestamp" and utc_timestamp(value) != value:
                    raise PublicContractError(f"Noncanonical UTC timestamp: {name}.{field.name}")
                if domain == "confidence" and not 0 <= value <= 1:
                    raise PublicContractError(f"Confidence out of range: {name}.{field.name}")
                if domain == "sha256" and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)):
                    raise PublicContractError(f"Invalid SHA-256: {name}.{field.name}")
                if domain == "sorted_unique_ids" and (value != sorted(set(value)) or any(not v for v in value)):
                    raise PublicContractError(f"Noncanonical ID collection: {name}.{field.name}")
            key = tuple(row[f] for f in primary)
            if any(v in (None, "") for v in key) or key in seen:
                raise PublicContractError(f"Invalid/duplicate primary key: {name}")
            seen.add(key)
        return deepcopy(rows)

    def table(self, name: str, rows: list[dict[str, Any]]) -> pa.Table:
        return pa.Table.from_pylist(self.validate(name, rows), schema=self.schemas[name])

    def validate_bundle(self, bundle: dict[str, list[dict[str, Any]]]) -> None:
        for name, rows in bundle.items():
            self.validate(name, rows)
            for field, (target_table, target_field) in self.tables[name]["foreign_keys"].items():
                if target_table not in bundle:
                    raise PublicContractError(f"Missing foreign key target table: {target_table}")
                self.validate(target_table, bundle[target_table])
                keys = {r[target_field] for r in bundle[target_table]}
                if any(r[field] is not None and r[field] not in keys for r in rows):
                    raise PublicContractError(f"Dangling foreign key: {name}.{field}")

    def serialize(self, name: str, model: dict[str, Any]) -> dict[str, Any]:
        definition = self.tables[name]
        mapping = {f: definition.get("serializer", {}).get(f, f) for f in definition["fields"]}
        if set(model) != set(mapping.values()):
            raise PublicContractError(f"Serializer would omit/invent fields: {name}")
        row = {f: model[m] for f, m in mapping.items()}
        for field, domain in definition.get("domains", {}).items():
            if row[field] is None:
                continue
            if domain == "utc_timestamp":
                row[field] = utc_timestamp(row[field])
            elif domain == "sorted_unique_ids":
                if not isinstance(row[field], (list, tuple)) or any(not isinstance(v, str) for v in row[field]):
                    raise PublicContractError(f"Invalid ID collection: {field}")
                row[field] = sorted(set(row[field]))
        return self.validate(name, [row])[0]

    def deserialize(self, name: str, row: dict[str, Any]) -> dict[str, Any]:
        self.validate(name, [row])
        definition = self.tables[name]
        return {definition.get("serializer", {}).get(f, f): deepcopy(v) for f, v in row.items()}
