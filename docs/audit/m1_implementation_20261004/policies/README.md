# Hồ sơ P2 cần duyệt — phiên bản 1, 2026-10-04

Trạng thái toàn bộ: **PROPOSED / NOT APPROVED**. Các file trong thư mục này là
đề xuất, không phải runtime configuration, amendment có hiệu lực hay decision log.
Yêu cầu triển khai kế hoạch không đồng nghĩa phê duyệt các semantics mới bên dưới.

| ID | Hồ sơ | Quyết định đề xuất |
|---|---|---|
| C3-CONTRACT-01 | [Contract](contract.md) | Giữ tên công khai; serializer tường minh; mở rộng schema có version |
| C3-TEMPORAL-01 | [Temporal](temporal.md) | Evidence/public capture có hash; acceptance là earliest sufficient evidence |
| C4-IDENTITY-01 | [Identity](identity.md) | Mention IDs theo text/span; canonical identity từ quyết định có basis |
| C6-SUPPORT-01 | [Support/revision](support_revision.md) | Nhóm nguồn attested; support append-only; conflict thiếu evidence thì pending |
| G2-QUALITY-01 | [Quality](quality.md) | Gold độc lập, coverage minh bạch; chưa có ngưỡng số được phê duyệt |
| C7-BOUNDARY-01 | [Boundaries](boundaries.md) | Gộp timestamp ties; event-balanced outcome-blind; giữ window hiện tại |

`manifest.json` ghi version, status và SHA-256 của từng hồ sơ. Khi cần sửa đề
xuất, tạo revision mới và giữ manifest cũ; phê duyệt phải trỏ đúng revision/hash.
Chỉ người có thẩm quyền khoa học mới quyết định. Bản implementation hiện tại
không ghi approval vào decision log và không chuyển draft thành APPROVED.

Thứ tự review: amendment nguồn → contract/temporal/identity → support → quality
và boundaries. Có thể duyệt độc lập các hồ sơ, nhưng stage chỉ chạy khi đủ mọi
dependency và artifact thật. Quality còn cần pilot/gold để khóa ngưỡng; không
có ngưỡng số trong bản này và không được coi phê duyệt procedure là phê duyệt
một threshold do người triển khai tự chọn.

Để triển khai P3–P7, approval phải chỉ rõ từng policy ID/hash, lựa chọn được
duyệt, người duyệt, ngày, nguồn thẩm quyền và ảnh hưởng reprocess. Thiếu mục nào
thì phần semantic tương ứng tiếp tục BLOCKED. Giữ scope 01/03/2025–31/08/2026,
không chỉnh ZIP, không backdate clocks, không mở locked test.
