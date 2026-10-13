from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.audit_m1_recovery import category_matches, check_table_links, inventory_root, inventory_zip


def test_inventory_never_promotes_fixture_or_accesses_locked_test(tmp_path: Path):
    (tmp_path / "runs" / "pilot").mkdir(parents=True)
    (tmp_path / "runs" / "pilot" / "run_manifest.yaml").write_text("status: PASS\nmode: inventory\n")
    (tmp_path / "runs" / "locked_test").mkdir()
    (tmp_path / "runs" / "locked_test" / "heldout.json").write_text("secret")
    rows = inventory_root(tmp_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "PRESENT_UNVERIFIED"
    assert rows[0]["declared_metadata"]["status"] == "PASS"


@pytest.mark.parametrize("name", ["../raw", "/raw", "data/locked_test/test.json", "a\\..\\b"])
def test_archive_rejects_unsafe_members_before_reading(tmp_path: Path, name: str):
    path = tmp_path / "input.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, b"fixture")
    with pytest.raises(ValueError, match="Unsafe or held-out"):
        inventory_zip(path)


def test_zip_hash_is_not_scientific_certification(tmp_path: Path):
    path = tmp_path / "input.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("reports/gate.json", '{"status":"PASS"}')
    assert inventory_zip(path)[0]["status"] == "PRESENT_UNVERIFIED"


def test_sidecar_alone_does_not_count_as_table():
    assert not category_matches("tables/claims.parquet.manifest.json", "claims.parquet")


def test_inventory_detects_broken_retrieval_link_and_tampered_sidecar(tmp_path: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    tables = tmp_path / "runs/pilot/tables"
    tables.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist([{"retrieval_id": "r1"}]), tables / "retrievals.parquet")
    pq.write_table(pa.Table.from_pylist([{"retrieval_id": "missing"}]), tables / "source_versions.parquet")
    (tables / "retrievals.parquet.manifest.json").write_text('{"physical_sha256_computed_at_real":"wrong"}')
    rows = inventory_root(tmp_path)
    assert next(row for row in rows if row["path"].endswith("retrievals.parquet"))["status"] == "CONFLICTING"
    checks = check_table_links(rows)
    assert checks[0]["missing_references"] == 1
    assert checks[0]["status"] == "CONFLICTING"


def test_empty_reference_tables_do_not_count_as_verified_data(tmp_path: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    tables = tmp_path / "runs/pilot/tables"
    tables.mkdir(parents=True)
    empty = pa.table({"retrieval_id": pa.array([], type=pa.string())})
    for name in ("retrievals", "source_versions"):
        pq.write_table(empty, tables / f"{name}.parquet")
    result = check_table_links(inventory_root(tmp_path))[0]
    assert result["status"] == "PRESENT_UNVERIFIED"
    assert result["reason"] == "NO_ROWS_TO_VERIFY"
