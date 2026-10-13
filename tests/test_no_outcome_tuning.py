"""
tests/test_no_outcome_tuning.py  (file MỚI, không có sẵn trong khung của bạn)
INV-06 (no_outcome_tuning): filter/anchor không được dùng đặc trưng downstream.
Bước 1: test khung. Từ Bước 6 (src/03_filter_domain.py) trở đi, thêm test
đọc thật tập cột dùng trong logic filter và assert không dính đặc trưng cấm.
"""
from src.invariants import no_outcome_tuning, FORBIDDEN_FILTER_FEATURES


def test_clean_features_pass():
    features = {"domain", "source_type", "publish_time_window"}
    assert no_outcome_tuning(features) is True


def test_forbidden_feature_detected():
    features = {"domain", "drift_magnitude"}
    assert no_outcome_tuning(features) is False


def test_all_forbidden_features_individually_rejected():
    for f in FORBIDDEN_FILTER_FEATURES:
        assert no_outcome_tuning({f}) is False


# TODO (Bước 6): import thật danh sách cột dùng trong hàm filter của
# src/03_filter_domain.py (không phải danh sách viết tay ở đây) rồi assert
# no_outcome_tuning(real_filter_columns) is True.