"""
tests/test_no_duplicate_sources.py
INV-03 (append_only_provenance): raw_source_id không được ghi đè.
Bước 1: test khung. Từ Bước 4 (src/02_fetch_articles.py) trở đi, thêm test
đọc thật data/raw/articles.json để đảm bảo mọi content_hash mới sinh
raw_source_id mới, không update in-place bản ghi cũ.
"""
from src.invariants import is_append_only


def test_append_only_allows_new_id():
    existing = {"raw_001", "raw_002"}
    assert is_append_only(existing, "raw_003") is True


def test_append_only_rejects_overwrite():
    existing = {"raw_001", "raw_002"}
    assert is_append_only(existing, "raw_001") is False  # trùng ID = vi phạm


# TODO (Bước 4): load data/raw/articles.json thật, group theo content_hash,
# assert mỗi content_hash chỉ map với đúng 1 raw_source_id bất biến
# (không có 2 bản ghi khác retrieved_at_real nhưng cùng raw_source_id).