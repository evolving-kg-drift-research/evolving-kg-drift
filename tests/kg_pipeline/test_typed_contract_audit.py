from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kg_pipeline.contract_authority import audit_machine_contract
from kg_pipeline.contracts import FOREIGN_KEYS, PRIMARY_KEYS, TABLE_SCHEMAS


def _contract(root: Path) -> tuple[Path, dict]:
    schema = TABLE_SCHEMAS["retrievals"]
    fields = [field for field in schema if field.name != "schema_version"]
    document = {"schema_version": "fixture-typed-v1", "retrievals": {
        "fields": [field.name for field in fields],
        "columns": {field.name: {"arrow_type": str(field.type), "nullable": field.nullable} for field in fields},
        "primary_key": PRIMARY_KEYS["retrievals"],
        "foreign_keys": {field: list(target) for field, target in FOREIGN_KEYS.get("retrievals", {}).items()},
    }}
    path = root / "config/schema.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path, document


@pytest.mark.parametrize("mutation", ["type", "nullable", "missing", "primary", "foreign"])
def test_declared_physical_contract_is_not_ignored(tmp_path: Path, mutation: str):
    path, document = _contract(tmp_path)
    declaration = document["retrievals"]
    if mutation == "type":
        declaration["columns"]["retrieval_id"]["arrow_type"] = "int64"
    elif mutation == "nullable":
        declaration["columns"]["retrieval_id"]["nullable"] = not TABLE_SCHEMAS["retrievals"].field("retrieval_id").nullable
    elif mutation == "missing":
        del declaration["columns"]["retrieval_id"]
    elif mutation == "primary":
        declaration["primary_key"] = ["raw_blob_sha256"]
    else:
        declaration["foreign_keys"] = {"source_id": ["missing_table", "missing_id"]}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    result = audit_machine_contract(tmp_path)
    assert result["status"] == "BLOCKED"


def test_matching_typed_contract_and_legacy_scope_are_distinguished(tmp_path: Path):
    path, document = _contract(tmp_path)
    result = audit_machine_contract(tmp_path)
    assert result["status"] == "PASS"
    assert result["tables"][0]["physical_contract"]["status"] == "PASS"
    del document["retrievals"]["columns"]
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    assert audit_machine_contract(tmp_path)["tables"][0]["physical_contract"]["status"] == "UNDECLARED"
