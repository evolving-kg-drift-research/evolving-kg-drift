from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kg_pipeline.acceptance_contract import PublicContract, PublicContractError


def contract() -> PublicContract:
    return PublicContract({"schema_version": "1.1.0", "facts": {
        "fields": ["FactVersionID", "accepted_into_kg_at", "supporting_claim_ids", "confidence"],
        "columns": {
            "FactVersionID": {"arrow_type": "string", "nullable": False},
            "accepted_into_kg_at": {"arrow_type": "string", "nullable": False},
            "supporting_claim_ids": {"arrow_type": "list<item: string>", "nullable": False},
            "confidence": {"arrow_type": "double", "nullable": True},
        },
        "primary_key": ["FactVersionID"], "foreign_keys": {},
        "serializer": {"FactVersionID": "fact_version_id"},
        "domains": {"accepted_into_kg_at": "utc_timestamp", "confidence": "confidence",
                    "supporting_claim_ids": "sorted_unique_ids"},
    }})


def row() -> dict:
    return {"FactVersionID": "f1", "accepted_into_kg_at": "2025-05-01T00:00:00+00:00",
            "supporting_claim_ids": ["c1", "c2"], "confidence": 0.8}


def test_explicit_serializer_lossless_round_trip():
    c = contract()
    model = {"fact_version_id": "f1", "accepted_into_kg_at": datetime(2025, 5, 1, tzinfo=timezone.utc),
             "supporting_claim_ids": ("c2", "c1", "c1"), "confidence": 0.8}
    public = c.serialize("facts", model)
    assert public == row()
    assert c.serialize("facts", c.deserialize("facts", public)) == public
    assert c.table("facts", [public]).to_pylist() == [public]


@pytest.mark.parametrize("mutation", ["missing", "extra", "null", "nan", "list", "timezone", "bool"])
def test_no_synthetic_defaults_or_arrow_coercion(mutation: str):
    record = row()
    if mutation == "missing":
        record.pop("confidence")
    elif mutation == "extra":
        record["unknown"] = "x"
    elif mutation == "null":
        record["FactVersionID"] = None
    elif mutation == "nan":
        record["confidence"] = float("nan")
    elif mutation == "list":
        record["supporting_claim_ids"] = '["c1"]'
    elif mutation == "timezone":
        record["accepted_into_kg_at"] = "2025-05-01T00:00:00"
    else:
        record["confidence"] = True
    with pytest.raises(PublicContractError):
        contract().table("facts", [record])


def test_duplicate_primary_key_is_rejected():
    with pytest.raises(PublicContractError, match="primary"):
        contract().table("facts", [row(), row()])


def test_undeclared_type_and_alias_collision_are_rejected():
    c = contract().document
    c["facts"]["columns"]["confidence"]["arrow_type"] = "made-up"
    with pytest.raises(PublicContractError):
        PublicContract(c)
    c = contract().document
    c["facts"]["serializer"]["confidence"] = "fact_version_id"
    with pytest.raises(PublicContractError, match="serializer"):
        PublicContract(c)


def test_dangling_foreign_key_and_missing_target_table():
    c = contract().document
    c["facts"]["foreign_keys"] = {"FactVersionID": ["parents", "parent_id"]}
    c["parents"] = {"fields": ["parent_id"], "columns": {"parent_id": {"arrow_type": "string", "nullable": False}},
                    "primary_key": ["parent_id"], "foreign_keys": {}}
    typed = PublicContract(c)
    with pytest.raises(PublicContractError, match="target"):
        typed.validate_bundle({"facts": [row()]})
    with pytest.raises(PublicContractError, match="foreign"):
        typed.validate_bundle({"facts": [row()], "parents": [{"parent_id": "other"}]})


def test_current_runtime_cannot_certify_undeclared_physical_contract(tmp_path):
    import yaml
    from kg_pipeline.contract_authority import audit_machine_contract
    from kg_pipeline.contracts import TABLE_SCHEMAS

    p = tmp_path / "config/schema.yaml"
    p.parent.mkdir()
    p.write_text(yaml.safe_dump({"schema_version": "fixture", "retrievals": {
        "fields": [f.name for f in TABLE_SCHEMAS["retrievals"] if f.name != "schema_version"],
    }}), encoding="utf-8")
    assert audit_machine_contract(tmp_path)["status"] == "BLOCKED"
