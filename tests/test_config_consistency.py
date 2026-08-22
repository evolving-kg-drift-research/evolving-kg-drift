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
