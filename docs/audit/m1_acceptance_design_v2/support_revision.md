# C6-SUPPORT-01 — Source support và append-only revisions

Version: 1. Status: **PROPOSED / NOT APPROVED**.
Findings: M1-006/007/015 và M1-PKG-007.

## Đề xuất cần duyệt

- SourceClaim định danh mỗi provenance path; giữ nhiều publishers/retrievals
  của cùng nội dung. Exact body dedup không xóa source membership.
- Nhóm nguồn độc lập dựa vào evidence origin/copy chain đã attested; hai URL
  hoặc hai domains không tự chứng minh hai nguồn độc lập. Unknown independence
  không được tính đủ support cho auto-accept.
- Không suy near-duplicate/independence chỉ từ embedding similarity. Có thể
  tạo candidate review; quyết định sử dụng phải versioned và có provenance.
- Rule accept đề xuất: reviewer chấp nhận rõ căn cứ, hoặc rule riêng theo
  relation đã được đăng ký. Bỏ hardcoded trusted source whitelist khỏi quyền
  quyết định production sau khi rule thay thế được duyệt. Không tự chọn số
  nguồn tối thiểu; policy per-relation phải khai báo requirement cụ thể.
- Support cùng proposition/interval/scope ghi append-only support event, không
  sửa supporting_claim_ids của FactVersion cũ hoặc sinh correction giả.
- Correction/retraction chỉ từ evidence chỉ rõ phủ định/thay thế, cùng
  LogicalFactID theo ontology; không dùng “bài mới hơn = sự thật”.
- Conflict thiếu căn cứ hoặc nhiều revisions cạnh tranh: pending có reason.
  Không tự đóng valid_to của bản cũ để tăng precision.
- Mọi claim phải có decision; snapshot triple unique, provenance multiplicity
  ở support tables. Engineering conservation không thay quality evaluation.

## Ví dụ và kiểm chứng

- Hai bài copy thông cáo: hai provenance paths, một source-origin group.
- Một bài hỗ trợ thêm fact F: giữ F và thêm support event, graph edge count
  không đổi. Thêm source không được tăng số triple đưa vào TransE.
- Correction biết tháng 6 nhưng hiệu lực tháng 7: snapshot tháng 6 giữ fact cũ.
- Tests: copied source, missing independence, no prior parent, cross-run
  support, revision cycle, retraction, competing siblings, claim conservation.

Migration: schema cho source/support events cần approval; từ adjudication
rebuild events, boundary feasibility, snapshots và certificates nếu nghĩa graph
change bị ảnh hưởng. Old facts/support luôn giữ nguyên. Blocker: chưa có
source-independence evidence và per-relation rules đã được duyệt.
