# C3-TEMPORAL-01 — Evidence và acceptance clocks

Version: 1. Status: **PROPOSED / NOT APPROVED**.
Findings: M1-004/005/020, M1-RV-002. Authority: Stage 4.10–4.12 và 4.17.

## Đề xuất cần duyệt

1. `evidence_observed_at` dùng thời điểm public capture/revision có thể kiểm
   chứng, liên kết đến đúng bytes/text version. Đây là thời điểm có bằng chứng
   quan sát được, không phải khẳng định lần đầu thông tin từng được công bố.
2. Historical archive record phải có capture timestamp, original URL, payload
   hash và record locator. Timestamp yêu cầu replay không thay actual capture.
   Không suy thời gian lịch sử từ current GET, mtime, event date hoặc ZIP time.
3. Declared publication/update chỉ là metadata hỗ trợ. Khi không có căn cứ đã
   duyệt cho scientific observation, ghi `TIME_BASIS_UNVERIFIED`, pending.
4. `accepted_into_kg_at` là min t mà tập source supports và identity decisions
   khả dụng tại t thỏa rule đã duyệt. Không tính từ ngày máy chạy review.
   Một rule cần nhiều nguồn dùng thời điểm support cuối cùng cần thiết có thể
   quan sát; không backdate về thời điểm của nguồn sớm nhất trong tập.
5. `adjudicated_at_real`, `retrieved_at_real`, `ingested_at_real` lấy từ sự kiện
   engineering thực và giữ riêng. Không dùng một clock để bù clock còn thiếu.
6. `valid_from/to` lấy từ evidence về world validity; không clamp về observed.
   Mọi parse/inference phải có parser version, basis và eligibility decision.
7. Stage 4.10 output tham chiếu claim ID, scientific times, basis/confidence,
   exact evidence refs và policy hash. Acceptance quyết định ở Stage 4.11,
   không tự sinh từ temporal parser. Snapshot xét cả observed và acceptance.

## Ví dụ

- Nguồn A capture 01/05, nguồn B độc lập capture 04/05; rule cần cả A/B và
  mapping có từ 02/05: proposed acceptance là 04/05; adjudication ngày 04/10
  vẫn ghi 04/10 ở engineering clock. Không đủ source evidence thì không tính.
- Bài nói CEO bắt đầu 01/01 nhưng archive quan sát 01/03: world validity có thể
  là 01/01, evidence là 01/03; snapshot tháng 2 không được dùng bằng chứng này.
- Không hợp lệ: current fetch tháng 9 cộng page date tháng 5 tự trở thành
  observation tháng 5; confidence=0.9 cố định để thay basis.

## Blockers, migration, tests

Chưa có archive/raw chain hoặc source support rule đủ thẩm quyền để áp dụng
công thức acceptance. Reader production tiếp tục fail-closed; không bỏ guard.
Sau duyệt: temporal → adjudication → facts → events → snapshots và mọi
certificate downstream tạo mới. Tests phải bao gồm basis thiếu, timezone thiếu,
late support/mapping, inferred validity, future-effective correction và clock
round-trip. Không claim historical replay chỉ nhờ các fixture này pass.
