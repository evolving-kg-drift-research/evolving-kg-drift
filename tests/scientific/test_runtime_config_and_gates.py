from pathlib import Path
from datetime import datetime, timezone
import pytest

from kg_pipeline.run import init_run, load_run_manifest, get_run_dir
from kg_pipeline.storage import read_yaml, write_json_immutable
from kg_pipeline.extract import run_extraction


def test_config_bundle_materializes_resolved_configs(tmp_path: Path):
    """A02: proposed_config_bundle.yaml must materialize resolved configuration."""
    # Setup some test config files
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)

    (tmp_path / "config" / "ontology.yaml").write_text("domain: test_domain\nrelations:\n  is_CEO_of:\n    temporal_semantics: state\n", encoding="utf-8")
    (tmp_path / "configs" / "kge.yaml").write_text("model: TransE\ndimension: 64\n", encoding="utf-8")

    init_run(tmp_path, "test_bundle_run", mode="inventory")
    bundle_path = tmp_path / "runs" / "test_bundle_run" / "inputs" / "proposed_config_bundle.yaml"
    assert bundle_path.is_file()

    bundle = read_yaml(bundle_path)
    assert "resolved_config" in bundle
    res_cfg = bundle["resolved_config"]
    assert "ontology" in res_cfg
    assert res_cfg["ontology"]["domain"] == "test_domain"
    assert "kge" in res_cfg
    assert res_cfg["kge"]["model"] == "TransE"
    assert "llm_adapter" in res_cfg


def test_stage_execution_permission_isolation(tmp_path: Path):
    """A03: Separate inventory run permissions from extraction run permissions."""
    # Inventory mode
    init_run(tmp_path, "inv_run", mode="inventory")
    manifest_inv = load_run_manifest(tmp_path, "inv_run")
    assert manifest_inv["mode"] == "inventory"
    assert manifest_inv["safety_scope"]["llm_calls"] == "FORBIDDEN_IN_TICKET_A"

    # Extraction mode
    init_run(tmp_path, "ext_run", mode="extraction")
    manifest_ext = load_run_manifest(tmp_path, "ext_run")
    assert manifest_ext["mode"] == "extraction"
    assert manifest_ext["safety_scope"]["llm_calls"] == "LOCAL_OR_MOCK_ONLY"


def test_downstream_gate_a_enforcement(tmp_path: Path):
    """A04: Downstream extraction must refuse execution if Gate A != PASS."""
    init_run(tmp_path, "gated_run", mode="inventory")
    run_dir = get_run_dir(tmp_path, "gated_run")

    # 1. No Gate A report evaluated -> PermissionError
    with pytest.raises(PermissionError, match="Gate A has not been evaluated|Gate A status"):
        run_extraction(tmp_path, "gated_run", enforce_gate_a=True)

    # 2. Gate A evaluated as NON-PASS (e.g. BLOCKED) -> PermissionError
    gate_a_dir = run_dir / "gates" / "A"
    gate_a_dir.mkdir(parents=True, exist_ok=True)
    bad_gate = {
        "status": "BLOCKED",
        "evaluated_at_real": datetime.now(timezone.utc).isoformat(),
        "blockers": ["MISSING_INPUTS"]
    }
    write_json_immutable(gate_a_dir / "report.json", bad_gate)

    with pytest.raises(PermissionError, match="Gate A status is BLOCKED"):
        run_extraction(tmp_path, "gated_run", enforce_gate_a=True)
