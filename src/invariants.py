"""
src/invariants.py
Các hàm kiểm tra 6 hard invariant (Mục 4.1 - Bản 3).
QUAN TRỌNG: file này được IMPORT bởi:
  - các script pipeline thật (01_crawl_rss.py ... 14_train_transe.py)
    để CHẶN dữ liệu vi phạm ngay khi chạy.
  - các file test trong tests/ để kiểm tra logic của chính các hàm này.

Không sửa logic các hàm này sau khi đã dùng cho main corpus mà không
bump version trong config/protocol.yaml (INV liên quan: deterministic_rebuild).
"""
from datetime import date, datetime
from typing import Set


def no_future_evidence(evidence_observed_at: date, cutoff: date) -> bool:
    """INV-01: evidence không được công khai sau cutoff của snapshot."""
    return evidence_observed_at <= cutoff


def no_future_entity_mapping(mapping_available_at: date, known_at: date) -> bool:
    """INV-02: entity mapping không được có hiệu lực sau known_at."""
    return mapping_available_at <= known_at


def is_append_only(existing_ids: Set[str], new_record_id: str) -> bool:
    """INV-03: record mới phải là ID mới, không được trùng (ghi đè) ID cũ."""
    return new_record_id not in existing_ids


def is_deterministic(hash_run_1: str, hash_run_2: str) -> bool:
    """INV-04: chạy lại cùng input/config phải ra cùng hash."""
    return hash_run_1 == hash_run_2


def is_set_equal(parquet_ids: Set[str], neo4j_ids: Set[str]) -> bool:
    """INV-05: tập ID trong Parquet và Neo4j phải bằng nhau."""
    return parquet_ids == neo4j_ids


# Các đặc trưng KHÔNG được dùng để lọc/chọn dữ liệu (vì lấy từ kết quả downstream)
FORBIDDEN_FILTER_FEATURES = {
    "sed_plus", "rr_score", "drift_magnitude", "anchor_suitability",
    "entity_frequency_across_snapshots",
}


def no_outcome_tuning(filter_features: Set[str]) -> bool:
    """INV-06: bộ đặc trưng lọc/anchor không được chứa đặc trưng downstream cấm dùng."""
    return filter_features.isdisjoint(FORBIDDEN_FILTER_FEATURES)