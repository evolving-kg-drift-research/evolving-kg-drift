# PROGRESS.md — evolving-ai-kg Execution State

## Checkpoint R14 — Stage 4.18 Canonical Parquet & Neo4j Parity PASS — 2026-09-28

- **Trạng thái Stage 4.18**: **PASS** (Run: production_v2).
- **Nguồn chân lý dữ liệu (Source of Truth)**: Canonical Parquet (
uns/production_v2/snapshots/snapshot_T*.parquet).
- **Tầng biểu diễn & Truy vấn Neo4j (Materialization Layer)**:
  - Sinh đầy đủ bộ 
odes.csv và 
elationships.csv theo chuẩn 
eo4j-admin import cho toàn bộ 10 snapshots tại 
uns/production_v2/neo4j_materialization/T01 -> T10.
- **Kiểm định tính đẳng cấu tập hợp (Parity Verification)**: **PASS (100% khớp tuyệt đối)**
  - SET_EQUALITY: **TRUE** (Tập cạnh và thực thể khớp 100% giữa Parquet và Neo4j qua 10/10 snapshots).
  - ROW_COUNTS_MATCH: **TRUE** (T01: 127, T02: 266, ..., T10: 1,803).
  - ENTITY_COUNTS_MATCH: **TRUE** (T01: 167, T02: 343, ..., T10: 1,389).
  - RELATION_COUNTS_MATCH: **TRUE** (10 quan hệ chuẩn phân bố đồng nhất).
  - ZERO_MANUAL_NEO4J_PATCH: **TRUE** (Không can thiệp thủ công vào dữ liệu đồ thị).
- **Khóa cấu hình TransE downstream**:
  - 
uns/production_v2/config/downstream_transe_config.yaml đã khóa 10 snapshots và tham chiếu đường dẫn Parquet.
- **Báo cáo nghiệm thu**: 
uns/production_v2/reports/parity_report.json.
- **KẾT LUẬN TOÀN PIPELINE**: **DATA PIPELINE HOÀN TẤT THÀNH CÔNG TỪ STAGE 4.3 ĐẾN STAGE 4.18. DỮ LIỆU ĐẠT CHUẨN SẴN SÀNG CHO MÔ HÌNH NHÚNG TRANSE (READY_FOR_TRANSE).**

---

## Checkpoint R13 — Stage 4.17 Bitemporal Snapshots PASS — 2026-09-28

- **Trạng thái Stage 4.17**: **PASS** (Run: production_v2).
- **Khởi tạo 10 Bitemporal Snapshots (T01 -> T10)**:
  - T01: cutoff 2025-06-01 | 127 facts | 167 entities | semantic_sha256: 75c16bb170dcfbdf...
  - T02: cutoff 2025-09-16 | 266 facts | 343 entities | semantic_sha256: b84411013ed3445...
  - T03: cutoff 2025-12-18 | 398 facts | 503 entities | semantic_sha256: 55c4bf06825c397b...
  - T04: cutoff 2026-02-27 | 537 facts | 646 entities | semantic_sha256: dc15c89c6dac7003...
  - T05: cutoff 2026-05-26 | 683 facts | 787 entities | semantic_sha256: ceb6430f6ff9c7fd...
  - T06: cutoff 2026-08-11 | 824 facts | 936 entities | semantic_sha256: 7a5e61bf2f2e9e7f...
  - T07: cutoff 2026-09-06 | 1,005 facts | 1,057 entities | semantic_sha256: 4138f271900df4d...
  - T08: cutoff 2026-09-07 | 1,261 facts | 1,176 entities | semantic_sha256: d9a683db6bcb4950...
  - T09: cutoff 2026-09-07 | 1,526 facts | 1,282 entities | semantic_sha256: 75ca6998eb5b4603...
  - T10: cutoff 2026-09-07 | 1,803 facts | 1,389 entities | semantic_sha256: 95e8dcde4f193802...
- **Kiểm định Ràng buộc Khoa học Bất biến (Hard Scientific Invariants)**: **PASS (100%)**
  - NO_FUTURE_EVIDENCE: **PASS** (0 vi phạm evidence_observed_at > cutoff).
  - STRICT_TEMPORAL_VALIDITY: **PASS** (0 vi phạm valid_from > cutoff hoặc cutoff >= valid_to).
  - DETERMINISTIC_REBUILD: **PASS** (Tái tạo mã băm khớp 100% từng byte).
  - MONOTONIC_GROWTH: **PASS** (Tập cạnh tri thức tăng trưởng đơn điệu tự nhiên qua thời gian).
- **Artifacts đã lưu**:
  - 
uns/production_v2/snapshots/snapshot_T01.parquet ... snapshot_T10.parquet
  - 
uns/production_v2/snapshots/snapshot_T01_manifest.yaml ... snapshot_T10_manifest.yaml
  - 
uns/production_v2/reports/snapshots_integrity_report.json

---

## Checkpoint R12 — Stage 4.16 Snapshot Boundaries PASS — 2026-09-28

- **Trạng thái Stage 4.16**: **PASS** (Run: production_v2).
- **Quy tắc phân định**: deterministic_event_quantile (chia đều 1,205 KG events thành 10 snapshots cân bằng, hoàn toàn mù với downstream outcomes).
- **10 Snapshots Khóa (T01 -> T10)**:
  - T01: 2025-03-18 -> 2025-06-01 (120 events, 75.0 ngày)
  - T02: 2025-06-01 -> 2025-09-16 (121 events, 107.8 ngày)
  - T03: 2025-09-16 -> 2025-12-18 (121 events, 92.5 ngày)
  - T04: 2025-12-18 -> 2026-02-27 (120 events, 70.9 ngày)
  - T05: 2026-02-27 -> 2026-05-26 (120 events, 87.9 ngày)
  - T06: 2026-05-26 -> 2026-08-11 (121 events, 77.1 ngày)
  - T07: 2026-08-11 -> 2026-09-06 (121 events, 26.6 ngày)
  - T08: 2026-09-06 -> 2026-09-07 (120 events)
  - T09: 2026-09-07 -> 2026-09-07 (120 events)
  - T10: 2026-09-07 -> 2026-09-07 (121 events)
- **Khóa mật mã ranh giới (Boundary Hash)**: ed3ce8f6ac664ef2467f5e2a6f2ee7e9a9b86b0d4441f2dcdb57ba1cb1a3b82.
- **Artifacts đã khóa bất biến**:
  - 
uns/production_v2/config/snapshot_boundaries.yaml
  - 
uns/production_v2/tables/transition_metadata.parquet

---

## Checkpoint R11 — Stage 4.15 KG Events & Feasibility PASS — 2026-09-28

- **Trạng thái Stage 4.15**: **PASS** (Run: production_v2).
- **Tổng KG Events**: **1,205 KG events** (chuyển dịch trạng thái đồ thị ssert).
  - Toàn bộ 1,803 fact versions từ nhiều bài viết đã được hợp nhất vào 1,205 state transitions duy nhất (tuân thủ nguyên tắc *Event != article count*).
  - Phân bố quan hệ: works_at (375), 
eleased_by (308), partners_with (157), is_CEO_of (96), integrated_into (95), ersion_of (52), invested_in (50), ased_on (38), succeeded_by (20), cquired_by (14).
  - Dải thời gian sự kiện: 2025-03-18T01:16:13+00:00 đến 2026-09-07T02:13:25+00:00 (~18 tháng cửa sổ quan sát thực tế) với 710 mốc thời gian độc lập.\n- **Phân tích Thực thể Neo (Anchor Feasibility)**:
  - 1,389 thực thể ứng viên được đánh giá.
  - **44 thực thể đạt HIGH_FEASIBILITY** (xuất hiện ở nhiều mốc thời gian và đa dạng quan hệ), 351 thực thể MEDIUM_FEASIBILITY.
  - Đánh giá tiềm năng đánh giá Temporal Drift & Recurring QA: **FEASIBLE**.
- **Artifacts đã lưu**:
  - 
uns/production_v2/tables/kg_events.parquet
  - 
uns/production_v2/tables/anchor_candidates_prelock.parquet
  - 
uns/production_v2/reports/feasibility_report.json

---

## Checkpoint R10 — Stage 4.14 Main Corpus Processing PASS — 2026-09-28

- **Trạng thái Stage 4.14**: **PASS** (Run: production_v2).
- **Tổng tài liệu xử lý**: 4,745 tài liệu.
- **Bước 1 (Filtering)**: 2,196 bài include (46.3%), 2,545 bài exclude (53.6%), 4 bài 
eview (0.1%). Lưu tại ilter_decisions.parquet.
- **Bước 2 (LLM Extraction)**: 1,865 claims trích xuất từ 2,196 bài viết. Lưu tại extracted_claims.parquet. Toàn bộ cache lưu tại 
uns/production_v2/llm_cache/.
- **Bước 3 (Adjudication & Fact Versioning)**: 1,803 fact versions chuẩn hóa được chấp nhận tự động (AUTO_ACCEPTED), 62 claims đưa vào hàng đợi kiểm duyệt (review queue). Lưu tại act_versions.parquet.
- **Kiểm định Chất lượng & Hard Invariants (Stage 4.14 Quality Gate)**: **PASS** (100%)
  - STRICT_SPAN_VALIDITY: **PASS** (0 invalid spans).
  - STRICT_PROVENANCE_INTEGRITY: **PASS** (0 invalid provenance links).
  - ZERO_MOCK_CONTAMINATION: **PASS** (0 mock claims).
- **Báo cáo nghiệm thu**: 
uns/production_v2/reports/quality_gate_report.json.

---

## Checkpoint R9 — Stage 4.14 Pipeline Freeze & Main Corpus In-Progress — 2026-09-27

- **Trạng thái Stage 4.14**: **IN_PROGRESS (EXTRACTION RUNNING)** (Run: `production_v2`).
- **Code Freeze**: Commit `6779bf48` (nhánh `fix/data-pipeline-compliance-cont`).
- **Decision Log**: Đã ghi nhận quyết định `stage_4_14_pipeline_freeze_v1` trong `decisions/decision_log.jsonl`.
- **Bước 1 (Filtering)**: **HOÀN THÀNH 100%** (4,745 / 4,745 tài liệu).
  - Kết quả lưu tại: `runs/production_v2/tables/filter_decisions.parquet`.
  - Phân loại: 2,196 bài `include` (46.3%), 2,549 bài `exclude` (53.7%).
- **Bước 2 (Extraction)**: **ĐANG CHẠY (IN_PROGRESS)** trên 2,196 bài `include`.
  - Kết nối: Local proxy `http://localhost:20128/v1` với model `ag/gemini-3.7-flash-low`.
  - Checkpoint: Lưu tự động mỗi 50 bài vào `tables/extracted_claims_partial.parquet`.
  - Đã có hơn 4,875 file phản hồi trong `runs/production_v2/llm_cache/`.
- **Cơ chế khôi phục (Resume)**: Khi mở lại máy, chỉ cần chạy một lệnh duy nhất:
  ```powershell
  $env:OPENAI_API_KEY = "sk-1ad27e92326fc80b-6zm0qb-d779bcb7"; .venv\Scripts\python.exe src/04_run_production_pipeline.py --run production_v2
  ```

---

## Checkpoint R8 — Stage 4.13 Pilot Quality Gate PASS — 2026-09-23

- **Trạng thái Stage 4.13**: **PASS** (
eports/quality_gate_report.json).
- **Đánh giá Thí điểm 30 Bài (pilot_real_30_final)**:
  - **Tài liệu kiểm định**: 30 tài liệu thô.
  - **Tỷ lệ lọc chấp nhận (Include Ratio)**: 43.3% (13/30 bài thuộc miền AI & Tech).
  - **Trích xuất FactVersions**: 3/3 claims được kiểm duyệt tự động (AUTO_ACCEPTED) và sinh FactVersion thành công.
- **Kiểm tra Ràng buộc Khoa học (Hard Invariant Checks)**:
  - STRICT_SPAN_VALIDITY: **PASS** (0 lỗi vị trí span).
  - STRICT_PROVENANCE_INTEGRITY: **PASS** (100% dòng dữ liệu truy vết về odyvariant_*).
  - ZERO_MOCK_CONTAMINATION: **PASS** (0 claim giả mạo).
- **Điều kiện Chuyển tiếp**: Đã đạt đủ điều kiện để chuyển sang **Stage 4.14 (Khóa Pipeline & Chạy Toàn Bộ 4,745 Bài Corpus)**.

---

## Checkpoint R7 — Fail-Closed Refactor & Empirical LLM Pilot PASS — 2026-09-23

- **Kiến trúc Fail-Closed LLM (Hoàn tất 100%)**:
  - Thay thế hoàn toàn cơ chế Fallback Mock trước đây bằng SDK chính thức google-genai (GeminiAdapter).
  - Mọi sự cố API đều thực thi cờ **Fail-Fast / Fail-Closed**, dừng run ngay lập tức thay vì tạo dữ liệu giả mạo.
  - Bổ sung cơ chế Exponential Backoff Retry cho các đợt nghẽn mạng / spike 503 / 429 tạm thời từ Google Cloud.
  - Đã nạp danh sách 10 quan hệ chuẩn từ config/ontology.yaml trực tiếp vào extraction prompt.

- **Kết quả Thử nghiệm Thực nghiệm 30 Bài (pilot_real_30)**:
  - Tập mẫu 30 tài liệu ngẫu nhiên với gemini-3.1-flash-lite.
  - Lọc nội dung: 13/30 bài được giữ lại (43.3%).
  - Trích xuất 3 sự kiện quan hệ thực tế có đầy đủ temporal span & offset: is_CEO_of(Rappaport, Wiz), works_at(Ruoming Pang, Apple), works_at(Ruoming Pang, Meta).

---

## Checkpoint R5 — Gate A Resolution & PASS — 2026-09-22

Nhánh: ix/data-pipeline-compliance-cont.
Run: llm_rebuild_v2_audit_02.
Trạng thái Gate A: **PASS** (11/11 checks PASS, 10/10 unit tests passed).

---

## Stage 4.3 - PASS trong phạm vi đã chứng minh

Bằng chứng được đọc và đối chiếu độc lập từ data/stage_4_3_runs/stage4_3_final_20260906T144016Z/ sang 
uns/llm_rebuild_v2_audit_01/reports/stage_4_3_reconciliation.json.
