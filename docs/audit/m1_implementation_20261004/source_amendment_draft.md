# Hồ sơ đánh giá thay thế nguồn — SOURCE-AMEND-DRAFT-20261004

Version: 1. **REVIEW REQUIRED / NOT APPROVED / NOT APPLIED**.
Finding M1-RV-001, severity GOVERNANCE. Hồ sơ đặt trong docs/audit, không đặt
trong amendments đang có hiệu lực; không ghi approval vào decision log.

## Bằng chứng và kết luận

Candidate commit `e19fe25d2325a53ebf49ada27cff4692aa1c6638`. Hash đầy đủ ở
`recovery_inventory.json:source_candidates`.

| Role | Exact candidate SHA-256 | Kết quả |
|---|---|---|
| proposal | d9e6d74b84fabdff880698eb6a5774bed8445897539b3713ba1e0594a446ea6f | MATCH baseline hiện hành và lock nhánh Hương |
| execution_plan | 12e492387dc562e623fba098ae3956c65411f4420fdb3c368848b72521f24bc5 | Khác cả baseline hiện hành và hash nhánh Hương khai báo |
| patch | faae34f40f6380fe6222374f682335bedbe69ba5779b9d00b6222875080e1611 | Khác cả baseline hiện hành và hash nhánh Hương khai báo |

Hai Markdown originals hiện hành không có trong hai checkout được kiểm kê.
Không thể chứng minh candidate tương đương originals. Candidate execution plan
tự ghi là kế hoạch môn học; decision nhánh ghi nguồn DOCX, nhưng chưa có exact
DOCX/transform manifest để kiểm chứng provenance này. `approved_by: user`
trong Git không được lấy làm approval mới cho lượt hiện tại.

## Đối chiếu nội dung đã đọc

Proposal PDF đúng hash được đọc bằng pypdf; so sánh theo nội dung, không theo
layout. Tài liệu candidate là Git blobs, chưa được restore vào sources/.

| Chủ đề | Proposal đã khóa | Candidate execution plan / patch | Protocol hiện hành |
|---|---|---|---|
| Scope thí nghiệm | Có A/B/C/D, Full Pipeline/auditor contribution; Path Utility/Noisy-OR | MVR A/B, SUPPORT paths/ICL; bỏ auditor ranking arm và complex Path Utility | A/B/C optional, exact-B fallback, QLoRA stretch |
| Snapshots | Abstract nêu 10–12; phần limits nhắc 8–12 | MVR 8–10, 11–12 stretch nếu algorithm chọn | allowed 8–12, target 10 |
| Hạ tầng/ưu tiên | Python 3.10+, 1 T4; QLoRA/ICL gates | CORE M1/M2/M4 trước SUPPORT/STRETCH | Phù hợp CORE priority trong AGENTS |
| Alignment failure | Relative Landmark fallback được nhắc | Có d64→d32/bucket merge/Relative Landmark fallback | Không tự mở fallback hoặc tune theo outcomes; vẫn cần approved config |
| Clocks/append-only | Bitemporal và chống future leakage | Patch ngắn xác nhận evidence axis/append-only/event balancing | Temporal parameters được khai báo chi tiết hơn |
| G2 | Chất lượng upstream là giới hạn nghiên cứu | Metrics/procedure khóa, relation-specific audit/QA feasibility | Ngưỡng số chưa được khóa trong runtime |

Có khác biệt phạm vi thực nghiệm giữa proposal và candidate; đây không chỉ
là đổi hash/encoding. Các lựa chọn giảm scope trong candidate gần với protocol
hiện hành, nhưng không được tự coi là amendment đã thông qua. Theo AGENTS §2.2,
những xung đột này phải được người có thẩm quyền giải quyết; không port semantic
change vào runtime trong lúc review. Patch 783 bytes quá ngắn để một mình
chứng minh toàn bộ các điều chỉnh đã được tác giả phê duyệt.

## Đề xuất xử lý để duyệt

1. Giữ proposal đúng bytes và giữ toàn bộ baseline cũ. Xác minh exact DOCX,
   Markdown conversion/version hoặc người chịu trách nhiệm nhận nội dung mới.
2. Nếu thay nguồn, duyệt **bytes cụ thể** có hash ở trên hoặc candidate revision
   mới; không chỉ duyệt tên file. Ghi vì sao thay thế và nội dung superseded.
3. Amendment phải quy định precedence cho từng khác biệt: arms, số snapshots,
   support scope, fallback và gates. Không thay trực tiếp các giá trị khoa học
   chỉ để source lock PASS. Giữ window hiện hành như user đã chọn.
4. Chỉ sau duyệt, tạo baseline version mới và cập nhật protocol/lock đồng bộ;
   ghi supersession/invalidation của run dùng baseline khác. Không xóa lịch sử.

## Ảnh hưởng, regression và trạng thái

Affected: source lock/protocol, config approval, run fingerprints và certificates
mọi stage; claims/facts/boundaries chỉ reprocess nếu rule cụ thể bị thay đổi.
Chưa được kết luận `requires_reprocess=false` trước impact assessment.

Repro: chạy `scripts/audit_m1_recovery.py` với ref ở trên; so candidate byte hashes
với hai source locks. Tests cần giữ source-byte mismatch, missing originals,
stale approval và changed config làm BLOCKED.

Root cause confirmed: exact candidate Markdown bytes không khớp hai locks;
không xác nhận giả thuyết tác giả/công cụ nào gây khác biệt. Thẩm quyền và
provenance chuyển đổi chưa xác minh. Không sửa lock/protocol, chưa RESOLVED.

**Khuyến nghị hiện tại:** chưa phê duyệt thay thế chỉ từ gói đang có. Hoàn thiện
nguồn gốc candidate và ma trận precedence trước; code độc lập được tiếp tục.
