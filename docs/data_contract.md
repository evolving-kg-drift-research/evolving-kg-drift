# Data Contract - Bước 1 (Mục 4.1)

**protocol_version:** 0.1.0
**Domain:** AI và Công nghệ

## Phạm vi dữ liệu
- Quy mô khởi đầu: 600-900 bài, 8-10 loại quan hệ, 8-12 lát cắt (ước lượng, không phải quota cứng).
- Pilot: 30-50 bài, 3 tiny snapshots.

## 6 hard invariants (xem chi tiết + code trong config/protocol.yaml và src/invariants.py)
INV-01 no_future_evidence · INV-02 no_future_entity_mapping · INV-03 append_only_provenance ·
INV-04 deterministic_rebuild · INV-05 parquet_neo4j_set_equality · INV-06 no_outcome_tuning

## Trục thời gian bắt buộc phân biệt
| Trục | Trường | Dùng ở script |
|---|---|---|
| valid_at | valid_from / valid_to | 10_build_fact_versions.py |
| known_at | evidence_observed_at | 10_build_fact_versions.py |
| known_at | accepted_into_kg_at | 08_adjudicate.py |
| project_time | retrieved_at_real | 02_fetch_articles.py |
| project_time | adjudicated_at_real | 08_adjudicate.py |

## Điều kiện Pass Bước 1
Mọi trường thời gian có định nghĩa không mâu thuẫn; test khung ở
tests/test_no_future_leakage.py, tests/test_parquet_neo4j_parity.py,
tests/test_no_duplicate_sources.py, tests/test_deterministic_rebuild.py,
tests/test_no_outcome_tuning.py đã được viết (chưa cần data thật).
