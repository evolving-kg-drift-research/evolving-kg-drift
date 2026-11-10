"""Strict contracts at rerun handoffs, using only fixture data."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from src.evaluation.support import aggregate_complete_support
from src.kg_pipeline.experiment_manifest import bound_file, validate_manifest


def test_complete_support_deduplicates_and_never_imputes_missing():
    rows = {("T1->T2", "a"): {"available": True, "SED_plus": 0.8, "signed_excess": -0.2}}
    assert aggregate_complete_support(["a", "a"], "T1->T2", rows)["SED_plus"] == 0.8
    for support in (["a", "missing"], ["missing"], []):
        result = aggregate_complete_support(support, "T1->T2", rows)
        assert result["eligible"] is False
        assert result["SED_plus"] is None
    rows["T1->T2", "a"]["available"] = False
    assert not aggregate_complete_support(["a"], "T1->T2", rows)["eligible"]


def test_nonfinite_support_is_ineligible():
    rows = {("T", "a"): {"available": True, "SED_plus": float("nan"), "signed_excess": 0}}
    assert aggregate_complete_support(["a"], "T", rows)["SED_plus"] is None


@pytest.mark.parametrize("name", ["null", "drift"])
def test_unregistered_v2_legacy_wrapper_cannot_read_old_runs(name: str, monkeypatch, tmp_path: Path):
    runner = importlib.import_module(f"scripts.run_m2_{name}_v2_all_transitions")
    monkeypatch.setattr(runner, "OUT_BASE", tmp_path / "out", raising=False)
    if hasattr(runner, "inspect_package"):
        monkeypatch.setattr(runner, "inspect_package", lambda *args: pytest.fail("No production reads"))
    with pytest.raises(PermissionError, match="registered"):
        getattr(runner, f"run_{name}_stage_all")()


def test_bound_file_rejects_escape_locked_data_and_wrong_hash(tmp_path: Path):
    with pytest.raises(ValueError, match="root|locked_test"):
        bound_file(tmp_path, {"path": "../outside", "sha256": "a" * 64})
    with pytest.raises(ValueError, match="locked_test"):
        bound_file(tmp_path, {"path": "data/locked_test/never-open", "sha256": "a" * 64})
    (tmp_path / "fixture").write_text("fixture", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        bound_file(tmp_path, {"path": "fixture", "sha256": "a" * 64})


def test_strict_manifest_rejects_commit_alias():
    import yaml

    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / "experiments/MANIFEST_TEMPLATE.yaml").read_bytes())
    manifest["git"]["commit"] = "HEAD"
    with pytest.raises(ValueError, match="commit"):
        validate_manifest(manifest)
