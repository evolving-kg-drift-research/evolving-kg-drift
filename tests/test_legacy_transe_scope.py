from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.run_legacy_transe_t01 import read_legacy_input, sha


def fixture_file(tmp_path: Path, rows: list[dict[str, str | None]]) -> tuple[Path, str]:
    path = tmp_path / "fixture.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    digest = sha(path.read_bytes())
    semantic = json.dumps({"table_name": "fixture", "contract_version": "fixture", "rows": rows},
                          ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    path.with_suffix(".parquet.manifest.json").write_text(json.dumps({
        "table_name": "fixture", "contract_version": "fixture", "row_count": len(rows),
        "physical_sha256_computed_at_real": digest, "semantic_sha256": sha(semantic),
    }), encoding="utf-8")
    return path, digest


def test_legacy_rejects_changed_bytes_before_reading_parquet(tmp_path: Path) -> None:
    path = tmp_path / "invalid.parquet"
    path.write_bytes(b"changed input")
    with pytest.raises(ValueError, match="authorized bytes"):
        read_legacy_input(path, sha(b"original input"))


@pytest.mark.parametrize("invalid", ["duplicate", "null", "sidecar"])
def test_legacy_rejects_invalid_artifacts(tmp_path: Path, invalid: str) -> None:
    row = {"subject_id": "a", "relation_id": "r", "object_id": "b"}
    rows = [row, row] if invalid == "duplicate" else [row]
    if invalid == "null":
        rows = [{**row, "subject_id": None}]
    path, digest = fixture_file(tmp_path, rows)
    if invalid == "sidecar":
        sidecar = path.with_suffix(".parquet.manifest.json")
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata["semantic_sha256"] = sha(b"tampered")
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        read_legacy_input(path, digest)


def test_legacy_preserves_ids_and_sorts_mapping(tmp_path: Path) -> None:
    path, digest = fixture_file(tmp_path, [
        {"subject_id": "z", "relation_id": "r", "object_id": "a"},
        {"subject_id": "b", "relation_id": "r", "object_id": "a"},
    ])
    dataset = read_legacy_input(path, digest)
    assert dataset.get_entity_mapping() == {"a": 0, "b": 1, "z": 2}
    assert len(dataset.triples) == 2
