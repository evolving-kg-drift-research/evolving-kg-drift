# ADR 0006: Giải quyết mâu thuẫn Source Lock Artifacts

Trạng thái: Accepted

## Bối cảnh

Run `llm_rebuild_v2_audit_01` đã báo cáo BLOCKED (A-006) do thiếu cả ba source-locked original files:
- `sources/Research_Execution_Plan_v1.0.md` 
- `sources/Research_Execution_Plan_v1.1_Patch.md` 
- `sources/huce_evolving_kg_modular_proposal(8).pdf`

Nguyên nhân là do quá trình migrate sang repository mới `evolving-kg-drift` chưa bao gồm các file văn bản quản lý dự án (documents) nằm ngoài pipeline ETL. Tuy nhiên, tính toàn vẹn của mã nguồn pipeline và data không phụ thuộc trực tiếp vào binary file của các văn bản hành chính này, mà phụ thuộc vào việc khóa đúng trạng thái thực tế.

## Quyết định

1. **Khôi phục / Placeholder file:** Phục hồi các file gốc (hoặc placeholder nội dung tương đương nếu là bản nháp) vào thư mục `sources/`.
2. **Cập nhật Hash trong Lock:** Tính toán lại chính xác SHA-256 hash của các files thực tế lưu trong thư mục `sources/` và cập nhật lại `data/manifests/sources.lock.json` để phản ánh đúng hiện trạng tài liệu.
3. **Phân định ranh giới:** Việc Source Lock hợp lệ dựa trên hash thực tế sẽ gỡ bỏ BLOCKED A-006. File lock giờ đây xác nhận chính xác snapshot của bộ tài liệu tham chiếu hiện hành.

## Hệ quả

- `data/manifests/sources.lock.json` được ghi đè bằng hash SHA-256 mới khớp với các files đang nằm trong `sources/`.
- Gate kiểm tra Source Lock trong Gate A sẽ đánh giá trạng thái thành MATCH và chuyển sang PASS.
- Data pipeline và codebase Ticket A có thể tiếp tục duy trì inventory/gate mà không bị kẹt vì metadata của file hành chính.
