# ADR 0005: Đóng băng cấu hình Stage A và chính sách Deduplication

Trạng thái: Accepted

## Bối cảnh

Dự án có sự mâu thuẫn giữa các file cấu hình tại thư mục `config/` và `configs/` trong giai đoạn trước:
- `config/protocol.yaml` dùng trường `retrieved_at_real` (thời điểm thu thập thực).
- `configs/protocol_v1.yaml` dùng trường `ingested_at_real` (thời điểm nhập liệu vào hệ thống).
- `config/ontology.yaml` khai báo 10 quan hệ (relations), nhưng dữ liệu lịch sử ghi nhận 11 quan hệ do có một quan hệ tạm thời được thêm vào trong quá trình thử nghiệm.
- Quá trình deduplication chưa có chính sách rõ ràng về việc ưu tiên sử dụng exact deduplication (giữ nguyên 100% variant và cluster theo SHA-256 text) hay áp dụng thuật toán near-duplicate/fuzzy matching.

## Quyết định

1. **Trường thời gian (Time fields):** 
   - Giữ nguyên ranh giới định nghĩa nghiêm ngặt:
     - `retrieved_at_real`: Thời điểm thu thập dữ liệu (provenance acquisition).
     - `ingested_at_real`: Thời điểm hệ thống bắt đầu xử lý nội bộ.
   - Không gộp (alias) hai trường này vào nhau, không ánh xạ trực tiếp thành các biến cố thời gian thực (`valid_time`) trong Knowledge Graph. Bất kỳ suy luận thời gian thực tế nào đều phải dựa trên LLM extraction tại Giai đoạn B.
2. **Ontology (Quan hệ đồ thị):**
   - Đóng băng ontology theo cấu hình 10 active relations đã có khai báo `domain` và `range` cụ thể trong `config/ontology.yaml` (v1.1). Quan hệ thứ 11 chưa được chứng minh tính chính danh sẽ bị loại bỏ khỏi Stage A.
3. **Chính sách Deduplication (Deduplication Policy):**
   - Đóng băng cấu hình Deduplication của Stage A ở mức **Exact-body CAS Deduplication**.
   - Mọi phiên bản có cùng SHA-256 normalized text sẽ được xếp chung vào một exact cluster và giữ nguyên mọi memberships (URLs/source_versions). 
   - Không áp dụng logic near-duplicate inference hay fuzzy matching tại Stage A để đảm bảo tính toàn vẹn và xác định của dữ liệu đầu vào. Near-duplicate policies sẽ được dời sang Stage C (Pilot) sau khi có ground truth.

## Hệ quả

- `run.py` sẽ đánh dấu trạng thái config bundle từ `PROPOSED_UNFROZEN` sang `FROZEN`.
- Stage A sẽ được vận hành với policy khử trùng lặp xác định 100% dựa trên Content-Addressed Storage (CAS) hash, cho phép bảo toàn dữ liệu phục vụ audit (Gate A PASS).
- Các Gate kiểm thử sẽ đánh giá hợp lệ việc sử dụng 10 relations và tách bạch `retrieved_at_real` / `ingested_at_real`.
