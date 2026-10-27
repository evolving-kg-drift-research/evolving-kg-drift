# Báo cáo nghiệm thu gói dữ liệu Evolving KG V3.1

**Mã phát hành:** `evolving_kg_downstream_v3.1`  
**Ngày kiểm định:** 18-10-2026  
**Kết quả:** **PASS trong phạm vi gói đầu vào canonical cho TransE và bàn giao Stage 4.18**  
**Ngoài phạm vi kết luận:** chứng nhận lại toàn bộ M1/Ticket A và huấn luyện TransE.

## 1. Kết luận

Gói V3.1 đạt các kiểm tra đóng gói và bàn giao dữ liệu được nêu trong báo cáo kiểm định. Mười snapshot Parquet canonical có thể được dùng làm đầu vào downstream theo cấu hình và manifest trong gói. Kiểm tra đọc lại Neo4j cục bộ xác nhận tập node và edge khớp chính xác với Parquet cho cả 10 snapshot.



## 2. Bất biến V3 và định danh gói

- ZIP V3 gốc được giữ nguyên từng byte; SHA-256: `53a0b59517cf5f621136637123fe3a093a7b003364f0144d28dc0300692e3d29`.
- ZIP V3.1: 21.497.702 byte, 4.872 thành viên; CRC và inventory hash đã được kiểm tra.
- SHA-256 V3.1: `a6acd988e81c9ab99bdd76e7a1f450f6f9360a7a5404cc53d33c4af8ba04915d`.
- Báo cáo đối chiếu Neo4j được ghi nhận là chỉ đọc; không có thao tác ghi vào cơ sở dữ liệu trong lần kiểm định.

## 3. Kết quả kiểm tra dữ liệu

| Hạng mục | Kết quả |
| --- | --- |
| Snapshot canonical | PASS — đủ 10 snapshot T01–T10, Parquet đọc được |
| Số edge theo T01–T10 | 121, 247, 362, 483, 604, 724, 844, 964, 1.084, 1.205 |
| Số entity theo T01–T10 | 167, 343, 503, 646, 787, 936, 1.057, 1.176, 1.282, 1.389 |
| Triple duy nhất và tăng đơn điệu | PASS |
| Ràng buộc thời gian / không dùng bằng chứng tương lai | PASS — 0 vi phạm theo kiểm tra trong báo cáo |
| Bằng chứng Neo4j so với Parquet | PASS — tập node và edge bằng nhau chính xác ở cả 10 snapshot |
| Body CAS | PASS — 4.745 blob, 17.472.140 byte; hash nội dung khớp |
| Raw blob tham chiếu | PASS — 5.168 file, 1.662.329.089 byte; hash khớp trong workspace |
| Raw blob trong ZIP | Không nhúng bản sao; gói chứa manifest tham chiếu và hash |
| Nguồn có thẩm quyền | PASS theo source lock và protocol hiện hành — 3 vai trò nguồn |

## 4. Cách sử dụng

Chỉ dùng các file `snapshots/snapshot_Txx_canonical.parquet` làm snapshot đầu vào TransE. Không dùng `tables/extracted_claims_partial.parquet` để huấn luyện; file này chỉ có mục đích chẩn đoán. Các raw blob vẫn nằm trong source store của dự án; đối chiếu qua `inputs/raw_blob_reference_manifest.json`.

## 5. Phạm vi chưa được chứng nhận

`full_m1_acceptance` trong báo cáo kiểm định là `NOT_CERTIFIED_BY_THIS_PACKAGE`. Các hash cấu hình ứng viên Ticket A được giữ làm metadata lịch sử, không tự ý cập nhật source lock hoặc đổi hash. Muốn chứng nhận toàn M1 cần khôi phục và xác minh các bản gốc có thẩm quyền, đối chiếu sai khác theo đặc tả và quyết định dự án, rồi chạy các gate liên quan. Không được sửa V3/V3.1 tại chỗ để làm cho hash khớp.

TransE training, M2 drift workflow và historical Stage 4.3 acquisition không được chạy trong đợt phát hành này.

## 6. Hồ sơ kiểm chứng chi tiết

- `reports/v3_1_package_validation_report.json` — kết quả kiểm định cấu trúc, hash và phạm vi phát hành.
- `reports/v3_1_exact_neo4j_readback_parity.json` — kết quả đối chiếu chính xác Parquet–Neo4j theo từng snapshot.
- `data/evolving_kg_downstream_v3_1.sha256.txt` — checksum của ZIP V3.1.

