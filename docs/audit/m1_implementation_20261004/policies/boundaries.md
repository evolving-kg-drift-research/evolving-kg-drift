# C7-BOUNDARY-01 — Graph events và boundaries outcome-blind

Version: 1. Status: **PROPOSED / NOT APPROVED**.
Findings: M1-019; M1-PKG-006/007; M1-RV-005.

## Đề xuất cần duyệt

- Giữ operational window 01/03/2025–31/08/2026 theo frozen config. Không lấy
  T07–T10 trong ZIP làm cutoffs đủ điều kiện; giữ toàn bộ ZIP như evidence cũ.
- Eligibility xét scientific clocks đã có basis, không lấy ngày trong filename.
  Outside-window hoặc unknown-time evidence giữ trong ledger, không xóa raw.
- Graph event là thay đổi tập canonical triples đủ điều kiện as-of; thêm source
  support mà không đổi graph state không tính như thêm triple.
- `graph_effective_at` là lúc graph change thỏa known/accepted/validity/mapping
  constraints, không mặc định world validity hay ngày chạy ETL. Event type,
  support/fact references và time basis phải truy ngược được.
- Gom toàn bộ graph events có cùng timestamp thành một nhóm nguyên tử. Chọn
  target 10 cumulative event quantiles trên nhóm; nearest cumulative count,
  nếu bằng nhau chọn timestamp sớm hơn. Không cắt giữa timestamp ties.
- Nếu targets trùng cutoff hoặc không đạt allowed snapshot range 8–12:
  BLOCKED feasibility để review, không tự sinh epsilon timestamps, đổi scope
  hoặc hạ số snapshot. Không dùng provisional monthly list làm fallback.
- Semantic hash gồm ordered event identities, frozen scope/algorithm/policy,
  inputs và selected boundaries; bỏ wall-clock created_at khỏi semantic body.
  Vẫn lưu created_at thật trong manifest audit và hash physical bytes riêng.
- Freeze chỉ sau kiểm feasibility đăng ký trước; query IDs/sampling rule được
  khóa trước scoring. Không tối ưu theo observed drift/SED/RR/MRR/H1.

## Ví dụ, tests và migration

- 100 events cùng 12:00 thuộc một cutoff, không chia thành 11:59:59 và 12:00:01.
- Hai nguồn thêm support cùng triple: support count tăng, graph event count
  không tăng. Chỉ graph change có basis mới tham gia event balancing.
- Tests: ties, insufficient distinct groups, input permutation, wall-clock
  variation, supports-only transitions, immutable resume, scope exclusions.
- Rebuild events → boundaries → snapshots → M2 manifests trong run mới sau
  approval. Không dùng quality/KGE outcomes để quyết định bỏ một transition.

Blockers: acceptance/source-support policies chưa duyệt và chưa có temporal
event lineage production. Đây chưa phải boundary algorithm được đăng ký.
