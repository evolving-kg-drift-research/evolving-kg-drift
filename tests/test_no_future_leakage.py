"""
tests/test_no_future_leakage.py
INV-01 (no_future_evidence) + INV-02 (no_future_entity_mapping).
Ở Bước 1: test khung, chưa có data thật, chỉ kiểm tra logic hàm.
Từ Bước 4/Bước 8 trở đi: thêm test đọc thật data/raw/, data/manifests/entity_map_v1.json
để chặn snapshot dùng evidence/mapping tương lai.
"""
from datetime import date
from src.invariants import no_future_evidence, no_future_entity_mapping


def test_no_future_evidence_pass():
    cutoff = date(2026, 6, 1)
    assert no_future_evidence(date(2026, 5, 1), cutoff) is True


def test_no_future_evidence_detects_violation():
    cutoff = date(2026, 6, 1)
    assert no_future_evidence(date(2026, 7, 1), cutoff) is False


def test_no_future_entity_mapping_pass():
    known_at = date(2026, 6, 1)
    assert no_future_entity_mapping(date(2026, 5, 1), known_at) is True


def test_no_future_entity_mapping_detects_violation():
    known_at = date(2026, 6, 1)
    assert no_future_entity_mapping(date(2026, 6, 15), known_at) is False


# TODO (Bước 4 - Mục 4.4): thêm test đọc data/raw/articles.json thật,
# so retrieved_at_real vs published_at_declared, đảm bảo không backdate.

# TODO (Bước 8 - Mục 4.8): thêm test đọc data/manifests/entity_map_v1.json thật,
# kiểm tra mapping_available_at <= known_at cho MỌI dòng.