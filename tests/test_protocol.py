import json
from pathlib import Path
import yaml


def test_protocol_yaml_exists_and_valid():
    repo_root = Path(__file__).resolve().parent.parent
    protocol_path = repo_root / "config" / "protocol.yaml"
    assert protocol_path.is_file(), f"Missing {protocol_path}"
    with open(protocol_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "protocol_version" in data


def test_decision_log_valid_jsonl():
    repo_root = Path(__file__).resolve().parent.parent
    decision_log_path = repo_root / "decisions" / "decision_log.jsonl"
    assert decision_log_path.is_file(), f"Missing {decision_log_path}"
    lines = decision_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    for line in lines:
        if line.strip():
            record = json.loads(line)
            assert isinstance(record, dict)


def test_sources_yaml_exists_and_valid():
    repo_root = Path(__file__).resolve().parent.parent
    sources_path = repo_root / "config" / "sources.yaml"
    assert sources_path.is_file(), f"Missing {sources_path}"
    with open(sources_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
