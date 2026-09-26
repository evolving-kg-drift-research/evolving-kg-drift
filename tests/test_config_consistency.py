from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(relative: str):
    with (ROOT / relative).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_kge_config_matches_protocol():
    protocol = load_yaml("configs/protocol_v1.yaml")
    kge = load_yaml("configs/kge.yaml")

    assert kge["model"] == protocol["kge"]["model"]
    assert kge["norm"] == protocol["kge"]["norm"]
    assert kge["dimension"] == protocol["kge"]["dimension"]
    assert kge["seeds"] == protocol["kge"]["seeds"]


def test_statistics_config_matches_protocol():
    protocol = load_yaml("configs/protocol_v1.yaml")
    stats = load_yaml("configs/statistics.yaml")

    assert stats["primary_model"] == protocol["statistics"]["primary_model"]
    assert stats["primary_inference"] == protocol["statistics"]["primary_inference"]
    assert stats["falsification"] == protocol["statistics"]["falsification"]


def test_data_as_of_contract_matches_protocol():
    protocol = load_yaml("configs/protocol_v1.yaml")
    data = load_yaml("configs/data.yaml")

    assert data["fact_versioning"]["scientific_as_of_field"] == protocol["temporal"]["as_of_axis"]
    assert data["fact_versioning"]["world_validity_fields"] == protocol["temporal"]["world_validity_fields"]
    assert data["fact_versioning"]["ingestion_field"] == protocol["temporal"]["real_ingestion_field"]


def test_snapshot_cutoffs_separates_fixtures_and_operational():
    """A29: Verify config/snapshot_cutoffs.yaml separates operational cutoffs from synthetic fixture cutoffs."""
    cutoffs = load_yaml("config/snapshot_cutoffs.yaml")
    assert "operational_snapshots" in cutoffs
    assert "fixture_snapshots" in cutoffs

    op = cutoffs["operational_snapshots"]
    assert op["target_snapshots"] == 10
    assert op["allowed_range"] == [8, 12]
    # Operational cutoffs are in 2025-2026
    for c in op["provisional_cutoffs"]:
        assert c["cutoff"].startswith("2025") or c["cutoff"].startswith("2026")

    # Fixture cutoffs are in 2021-2023
    fix = cutoffs["fixture_snapshots"]
    assert "S1" in fix and fix["S1"]["cutoff"].startswith("2021")
    assert "S2" in fix and fix["S2"]["cutoff"].startswith("2022")
    assert "S3" in fix and fix["S3"]["cutoff"].startswith("2023")


def test_protocol_authority_precedence():
    """A30: Verify configs/protocol_v1.yaml is master protocol authority."""
    protocol_master = load_yaml("configs/protocol_v1.yaml")
    assert protocol_master["protocol_version"] == "v1-draft"
    assert "hard_invariants" not in protocol_master or protocol_master.get("hard_invariants") is not None
