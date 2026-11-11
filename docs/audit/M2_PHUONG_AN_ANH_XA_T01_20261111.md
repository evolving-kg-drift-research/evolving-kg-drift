# Phương án tái lập ánh xạ thực thể cho M2 V3.1

**Phiên bản 1 · Đã duyệt phương án ngày 11/11/2026**

Phạm vi áp dụng là **167 thực thể chung của T01→T02**, với mốc nguồn **01/06/2025 lúc 01:05:48 UTC**. Phê duyệt dựa trên yêu cầu của người dùng “Hãy thực hiện bước tiếp theo và duyệt luôn phương án”. Mục đích là lập hồ sơ cho từng ánh xạ và kiểm tra điều kiện dùng bằng chứng khi đếm bài nguồn cho bộ neo. [Phép thử trên 167 thực thể](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/doi_chieu_toan_bo_t01.json)

## 1. Quy tắc tái lập mã đã duyệt

1. Dùng đúng bản lưu có mốc quan sát trước hoặc bằng mốc cắt T01. Ghi nguồn, mã bài, mã bản lưu, SHA-256 thân bài, nguyên văn tên và khoảng Unicode của tên trong đúng thân bài.
2. Tạo mã từ tên UTF-8 sau `strip().lower()`, lấy tám ký tự đầu của SHA-256 và thêm tiền tố `ent_`. Đối chiếu với mã V3.1 trong cả hai snapshot. Đưa trường hợp không khớp, va chạm mã, tên mơ hồ hoặc nghi trùng đối tượng vào danh sách cần xác minh. Việc hợp nhất bí danh cần căn cứ riêng cho đúng đối tượng và thời điểm.
3. Ghi riêng mốc quan sát của bản lưu, thời điểm thực hiện tái lập và `mapping_available_at`. Trường hiệu lực chỉ được điền từ hồ sơ có căn cứ xác định ánh xạ của đúng lần xuất hiện tên tới đúng thực thể. Căn cứ cần truy vết được và có thời điểm hiệu lực trước hoặc đúng cutoff. Ngày lưu bài ghi vào trường quan sát, còn mã băm khớp ghi vào kết quả tái lập. [Đặc tả Stage 4.8 và 4.14](../data_pipeline_spec.md) · [Lược đồ ánh xạ](../../config/schema.yaml#L111)

## 2. Tên dòng hệ điều hành

Ưu tiên đoạn trước hoặc đúng mốc T01 có tên dòng hệ điều hành xuất hiện độc lập. Chấp nhận căn cứ từ một tên phiên bản khi câu hoặc ngữ cảnh cùng bản lưu nêu rõ phiên bản đó thuộc dòng nào. Ghi nguyên văn cả phần xác lập quan hệ phiên bản và vị trí tương ứng. Nếu căn cứ hiện có chỉ là chuỗi đầu của tên phiên bản, giữ trạng thái **chưa xác minh** cho tên dòng.

Áp dụng cách xử lý này cho **iOS**, **iPadOS** và **macOS**. Ba trường hợp đang chờ đoạn dẫn xác lập rõ tên dòng. Các phiếu hiện có ghi **iOS 18.4**, **iPadOS 18.4** và **macOS 15.4**. [Đối chiếu vị trí tên theo phiếu](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/vi_tri_ten_theo_phieu.parquet)

## 3. Điều kiện dùng trong nghiên cứu chính

Một bài chỉ được tính khi đoạn bằng chứng đạt thẩm định nội dung và kiểu, đúng bản lưu đã quan sát đến cutoff, và cả hai ánh xạ có căn cứ xác minh hiệu lực đến mốc đó. Đếm một lần cho mỗi cặp thực thể–bài, trong đó bài được nhận diện bằng nguồn xuất bản và mã bài. Hồ sơ còn thiếu được ghi là *chưa xác minh*. [Quyết định về tần suất bài nguồn](../../decisions/decision_log.jsonl) · [Bảng độ phủ trước khi áp dụng](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/bao_phu_neo.json)

Hiện có **164/167 thực thể tái lập được mã từ tên trong bản lưu** và **0/167 mốc hiệu lực ánh xạ đã xác minh**. Phương án đã duyệt để lập và kiểm chứng hồ sơ T01. Điều kiện dùng tần suất trong nghiên cứu chính vẫn chờ căn cứ ở cấp ánh xạ và cấp bài. Lượt tiếp nhận tiếp theo cần ghi mã phiên bản, căn cứ, thời điểm và trạng thái của từng ánh xạ.
