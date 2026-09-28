"""Machine-readable comparison with the repository's authoritative schema file.

This module reports drift; it does not translate field names or invent a new
scientific schema when config/schema.yaml and the runtime disagree.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from temporal.schema import FactVersion

from .contracts import TABLE_SCHEMAS, ContractError
from .hashing import sha256_file


def load_machine_contract(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "config" / "schema.yaml"
    if not path.is_file():
        raise ContractError(f"Authoritative machine schema is missing: {path}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("schema_version"), str):
        raise ContractError("config/schema.yaml requires a schema_version")
    for table_name, definition in document.items():
        if table_name == "schema_version":
            continue
        if not isinstance(definition, dict) or not isinstance(definition.get("fields"), list):
            raise ContractError(f"Invalid field declaration for {table_name}")
        declared = definition["fields"]
        if not declared or any(not isinstance(name, str) or not name for name in declared):
            raise ContractError(f"Invalid field name in {table_name}")
        if len(declared) != len(set(declared)):
            raise ContractError(f"Duplicate field in {table_name}")
    return document


def audit_machine_contract(repo_root: Path, table_names: list[str] | None = None) -> dict[str, Any]:
    """Check exact names. A proposed alias is a scientific decision, not a cast."""
    document = load_machine_contract(repo_root)
    targets = table_names or [name for name in document if name != "schema_version"]
    entries = []
    for name in targets:
        defined = document.get(name)
        runtime = TABLE_SCHEMAS.get(name)
        expected = set(defined["fields"]) if isinstance(defined, dict) else set()
        actual = set(runtime.names) - {"schema_version"} if runtime is not None else set()
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        blockers = []
        if defined is None:
            blockers.append("MISSING_IN_CONFIG_SCHEMA")
        if runtime is None:
            blockers.append("MISSING_PYARROW_SCHEMA")
        if missing:
            blockers.append("PYARROW_MISSING_DECLARED_FIELDS")
        if extra:
            blockers.append("PYARROW_UNDECLARED_FIELDS")
        dataclass_missing: list[str] = []
        if name == "fact_versions":
            model_fields = {field.name for field in fields(FactVersion)}
            dataclass_missing = sorted(expected - model_fields)
            if dataclass_missing:
                blockers.append("DATACLASS_MISSING_DECLARED_FIELDS")
        entries.append({
            "table": name,
            "status": "PASS" if not blockers else "BLOCKED",
            "blockers": blockers,
            "missing_in_pyarrow": missing,
            "undeclared_in_pyarrow": extra,
            "missing_in_dataclass": dataclass_missing,
        })
    return {
        "status": "PASS" if all(item["status"] == "PASS" for item in entries) else "BLOCKED",
        "schema_version": document["schema_version"],
        "schema_physical_sha256": sha256_file(repo_root / "config" / "schema.yaml"),
        "tables": entries,
    }


def require_schema_compatible(repo_root: Path, table_names: list[str]) -> dict[str, Any]:
    result = audit_machine_contract(repo_root, table_names)
    if result["status"] != "PASS":
        detail = "; ".join(
            f"{item['table']}: {','.join(item['blockers'])}"
            for item in result["tables"] if item["status"] != "PASS"
        )
        raise ContractError(f"Authoritative schema drift blocks this stage: {detail}")
    return result
