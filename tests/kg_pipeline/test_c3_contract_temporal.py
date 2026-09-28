"""C3 checks: schema authority and independent temporal clocks."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from kg_pipeline.adjudication import adjudicate_claims, parse_extracted_date
from kg_pipeline.contract_authority import (
    audit_machine_contract,
    load_machine_contract,
    require_schema_compatible,
)
from kg_pipeline.contracts import ContractError, make_row, table_from_rows
from kg_pipeline.adjudicate import _approved_temporal_inputs
from kg_pipeline.adjudicate import run_adjudication
from kg_pipeline.cli import main as cli_main
from kg_pipeline.run import init_run, load_run_manifest
from kg_pipeline.storage import ArtifactConflict
from temporal.schema import ClaimCandidate, ContractError as TemporalContractError


ROOT = Path(__file__).resolve().parents[2]


def test_matching_retrieval_contract_round_trip():
    audit = audit_machine_contract(ROOT, ["retrievals"])
    assert audit["status"] == "PASS"
    row = make_row(
        "retrievals", retrieval_id="r1", raw_blob_sha256="a" * 64,
        source_id="s", final_url="https://example.test/a",
        retrieved_at_real="2025-02-01T12:00:00+07:00",
        strict_source_input_eligible=True,
    )
    assert table_from_rows("retrievals", [row]).to_pylist() == [row]


def test_fact_contract_drift_is_explicit_blocker():
    audit = audit_machine_contract(ROOT, ["fact_versions", "adjudication_decisions"])
    assert audit["status"] == "BLOCKED"
    fact = audit["tables"][0]
    assert "accepted_into_kg_at" in fact["missing_in_pyarrow"]
    assert "accepted_into_kg_at" in fact["missing_in_dataclass"]
    assert "ingested_at_real" in fact["undeclared_in_pyarrow"]
    with pytest.raises(ContractError, match="Authoritative schema drift"):
        require_schema_compatible(ROOT, ["fact_versions"])


def test_schema_audit_cli_exits_nonzero_on_repository_drift(capsys):
    assert cli_main(["--repo-root", str(ROOT), "audit-schema"]) == 2
    assert '"status": "BLOCKED"' in capsys.readouterr().out


def test_adjudication_runner_blocks_schema_drift_before_outputs(tmp_path, monkeypatch):
    from kg_pipeline import gates

    target = tmp_path / "config/schema.yaml"
    target.parent.mkdir()
    target.write_bytes((ROOT / "config/schema.yaml").read_bytes())
    monkeypatch.setattr(gates, "require_gate_a", lambda *args, **kwargs: {"gate": "A"})
    with pytest.raises(ContractError, match="Authoritative schema drift"):
        run_adjudication(tmp_path, "blocked_run")
    assert not (tmp_path / "runs/blocked_run/tables").exists()


def test_missing_or_malformed_machine_schema_blocks(tmp_path):
    with pytest.raises(ContractError, match="missing"):
        load_machine_contract(tmp_path)
    path = tmp_path / "config/schema.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump({"schema_version": "1.0.0", "retrievals": {"fields": ["x", "x"]}}), encoding="utf-8")
    with pytest.raises(ContractError, match="Duplicate field"):
        load_machine_contract(tmp_path)


def test_run_binds_machine_schema_version_and_hash(tmp_path):
    target = tmp_path / "config/schema.yaml"
    target.parent.mkdir()
    target.write_bytes((ROOT / "config/schema.yaml").read_bytes())
    init_run(tmp_path, "schema_bound_run", mode="inventory")
    manifest = load_run_manifest(tmp_path, "schema_bound_run")
    assert manifest["machine_schema"]["schema_version"] == "1.0.0"
    assert len(manifest["machine_schema"]["physical_sha256"]) == 64
    target.write_text(target.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    with pytest.raises(ArtifactConflict, match="Configuration differs"):
        load_run_manifest(tmp_path, "schema_bound_run")


def test_naive_or_invalid_extracted_dates_are_not_silently_accepted():
    with pytest.raises(ValueError, match="explicit timezone"):
        parse_extracted_date("2022-01-01T00:00:00")
    with pytest.raises(ValueError, match="Invalid extracted validity"):
        parse_extracted_date("not-a-date")


def test_retrieval_clock_never_replaces_ingestion_clock():
    claim = ClaimCandidate(
        claim_id="c1", body_variant_id="b1", subject_mention="Alpha",
        relation_name="is_CEO_of", object_mention="Beta",
        evidence_span_start=0, evidence_span_end=5, evidence_text_hash="evidence",
    )
    observed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ingested = datetime(2025, 1, 1, tzinfo=timezone.utc)
    accepted, _ = adjudicate_claims(
        [claim], {"c1": observed}, ingested,
        {"Alpha": "a", "Beta": "b"},
        body_to_sources={"b1": [{
            "publisher_source_id": "trusted_registry_1", "source_url": "https://example.test",
            "retrieved_at_real": "2030-01-01T00:00:00+00:00",
        }]},
    )
    assert len(accepted) == 1
    assert accepted[0].evidence_observed_at == observed
    assert accepted[0].ingested_at_real == ingested


def test_missing_approved_temporal_artifact_blocks_instead_of_defaulting(tmp_path):
    with pytest.raises(TemporalContractError, match="retrieved_at_real or archive_datetime cannot substitute"):
        _approved_temporal_inputs(tmp_path / "runs/r1", [])
