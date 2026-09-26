# PROGRESS.md — evolving-ai-kg Execution State

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
