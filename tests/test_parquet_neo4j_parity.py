"""
tests/test_parquet_neo4j_parity.py
INV-05 (parquet_neo4j_set_equality).
Bước 1: test khung với dữ liệu giả lập. Từ giai đoạn materialize (sau Bước 11,
dùng src/12_materialize_neo4j.py + src/13_check_parity.py) sẽ thay bằng đọc
thật data/snapshots/*.parquet và query Neo4j để lấy set ID thật.
"""
from src.invariants import is_set_equal


def test_set_equality_pass_when_identical():
    parquet_ids = {"e1", "e2", "e3"}
    neo4j_ids = {"e1", "e2", "e3"}
    assert is_set_equal(parquet_ids, neo4j_ids) is True


def test_set_equality_detects_missing_in_neo4j():
    parquet_ids = {"e1", "e2", "e3"}
    neo4j_ids = {"e1", "e2"}
    assert is_set_equal(parquet_ids, neo4j_ids) is False


def test_set_equality_detects_extra_in_neo4j():
    parquet_ids = {"e1", "e2"}
    neo4j_ids = {"e1", "e2", "e3"}
    assert is_set_equal(parquet_ids, neo4j_ids) is False


# TODO (sau src/13_check_parity.py chạy thật): parametrize theo từng
# snapshot_id trong data/manifests/snapshot_manifest.json và assert
# is_set_equal(...) is True cho MỌI snapshot trước khi bàn giao.