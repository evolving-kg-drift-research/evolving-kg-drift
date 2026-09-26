"""
tests/test_deterministic_rebuild.py  (file MỚI, không có sẵn trong khung của bạn)
INV-04 (deterministic_rebuild): cùng input+config phải ra cùng hash.
Bước 1: test khung. Từ Bước 11 (src/11_build_snapshots.py) trở đi, thêm test
chạy build_snapshot() 2 lần trên cùng input/config và so sha256 output.
"""
from src.invariants import is_deterministic


def test_same_hash_pass():
    assert is_deterministic("abc123", "abc123") is True


def test_different_hash_detected():
    assert is_deterministic("abc123", "def456") is False


# TODO (Bước 11): gọi thật src/11_build_snapshots.py hai lần với cùng
# config/snapshot_cutoffs.yaml, so sánh sha256 của 2 file snapshot parquet
# sinh ra - phải giống hệt nhau (byte-for-byte hoặc theo canonical_sort).