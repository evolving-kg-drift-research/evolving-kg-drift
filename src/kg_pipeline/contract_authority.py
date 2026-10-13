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

from .contracts import FOREIGN_KEYS, PRIMARY_KEYS, TABLE_SCHEMAS, ContractError
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


def _audit_physical_declaration(name: str, definition: dict[str, Any]) -> dict[str, Any]:
    """Check explicit declarations only; never infer or approve a missing policy."""
    columns = definition.get("columns")
    if columns is None:
        return {"status": "UNDECLARED", "issues": ["PHYSICAL_TYPES_AND_NULLABILITY_UNDECLARED"]}
    issues = []
    declared = set(definition["fields"])
    if not isinstance(columns, dict) or set(columns) != declared:
        return {"status": "BLOCKED", "issues": ["COLUMN_DECLARATIONS_MUST_MATCH_FIELDS"]}
    runtime = TABLE_SCHEMAS.get(name)
    for field_name, specification in columns.items():
        if (
            not isinstance(specification, dict)
            or set(specification) != {"arrow_type", "nullable"}
            or not isinstance(specification.get("arrow_type"), str)
            or type(specification.get("nullable")) is not bool
        ):
            issues.append(f"INVALID_COLUMN_DECLARATION:{field_name}")
            continue
        if runtime is None or field_name not in runtime.names:
            issues.append(f"MISSING_RUNTIME_COLUMN:{field_name}")
            continue
        field = runtime.field(field_name)
        if str(field.type) != specification["arrow_type"]:
            issues.append(f"ARROW_TYPE_MISMATCH:{field_name}")
        if field.nullable != specification["nullable"]:
            issues.append(f"NULLABILITY_MISMATCH:{field_name}")
    primary = definition.get("primary_key")
    if (
        not isinstance(primary, list) or not primary
        or any(not isinstance(key, str) or key not in declared for key in primary)
        or len(primary) != len(set(primary)) or primary != PRIMARY_KEYS.get(name)
    ):
        issues.append("PRIMARY_KEY_MISMATCH_OR_UNDECLARED")
    foreign = definition.get("foreign_keys")
    expected = {field: list(target) for field, target in FOREIGN_KEYS.get(name, {}).items()}
    if not isinstance(foreign, dict) or foreign != expected:
        issues.append("FOREIGN_KEYS_MISMATCH_OR_UNDECLARED")
    else:
        for field, (target_table, target_field) in foreign.items():
            target = TABLE_SCHEMAS.get(target_table)
            if field not in declared or target is None or target_field not in target.names:
                issues.append(f"INVALID_FOREIGN_KEY:{field}")
    return {"status": "BLOCKED" if issues else "PASS", "issues": issues}


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
        physical = _audit_physical_declaration(name, defined) if isinstance(defined, dict) else {
            "status": "UNDECLARED", "issues": ["MISSING_IN_CONFIG_SCHEMA"],
        }
        if physical["status"] == "BLOCKED":
            blockers.append("PHYSICAL_CONTRACT_MISMATCH")
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
            "physical_contract": physical,
        })
    return {
        "status": "PASS" if all(item["status"] == "PASS" for item in entries) else "BLOCKED",
        "schema_version": document["schema_version"],
        "physical_contract_status": (
            "PASS" if all(item["physical_contract"]["status"] == "PASS" for item in entries)
            else "BLOCKED"
        ),
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
