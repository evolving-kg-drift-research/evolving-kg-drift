# Biên bản phân xử thẩm định bằng chứng M2 V3.1

**Bản dự thảo ngày 11/11/2026 · Chờ xác nhận**

Biên bản áp dụng cho lượt chấm độc lập V2 trên 24 phiếu. Nội dung cần xác nhận gồm **4 quyết định về quan hệ hoặc kiểu thực thể** và **5 quyết định chọn đoạn dẫn**. Vị trí đoạn tính theo điểm mã Unicode trong đúng thân bài đã lưu. Khoảng `[a, b)` gồm vị trí `a` và kết thúc ngay trước `b`. [Kết quả đối chiếu A/B](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v2/doi_chieu_v2.json) · [Nguyên văn và mã băm các đoạn](../../outputs/m2_anchor_semantic_review/20261111_de_xuat_phan_xu_ab_v2/de_xuat_phan_xu_v2.json)

## 1. Quyết định về quan hệ và kiểu thực thể

| Mục | Mã phiếu và bộ ba | Quyết định đề nghị | Căn cứ |
| --- | --- | --- | --- |
| 1 | `M2-759AA44258A04166` · Optimus → `released_by` → Tesla | **Chưa đủ căn cứ** | Đoạn `[1608, 1708)` nêu Optimus đang phát triển và chưa triển khai thương mại. Câu này để ngỏ khả năng sản phẩm đã được giới thiệu hoặc ra mắt. |
| 2 | `M2-8FC77F91E1071645` · Fengdeng → `released_by` → Phòng thí nghiệm Quốc gia vịnh Tam Á | **Chưa đủ căn cứ** | Đoạn `[821, 1047)` xác định phòng thí nghiệm là bên phát triển và mô tả công dụng của mô hình. Vai trò của phòng thí nghiệm trong việc phát hành hoặc đưa mô hình ra cung cấp còn thiếu căn cứ. |
| 3 | `M2-61A62F7BF1AF62CF` · Alpha 7 IV → `succeeded_by` → Alpha 7 V | **Chưa đủ căn cứ** | Đoạn `[0, 415)` nêu V là thế hệ thứ năm và so sánh hiệu năng với IV. Bài xác nhận V đã mở bán. Việc V kế nhiệm chính IV vẫn dựa vào suy luận từ tên và phép so sánh. |
| 4 | `M2-603BF982B58FB310` · Android → `based_on` → Linux | **Hỗ trợ quan hệ. Chưa xác minh kiểu Android. Linux là `Software`.** | Đoạn `[2395, 2571)` nêu Linux vận hành Android. Cách gọi “nền tảng Android” trong bài còn để ngỏ cách phân định `Software` và `Platform` theo ontology 1.1. |

Ở mục 1–3, vị trí trong bảng ghi đoạn đã đối chiếu khi phân xử. Trường đoạn quyết định để trống theo nhãn *chưa đủ căn cứ*. Mục 4 dùng đoạn `[2395, 2571)` làm căn cứ cho quan hệ, với trạng thái kiểu *chưa xác minh*.

## 2. Chọn đoạn dẫn cho năm ca còn lại

| Mục | Mã phiếu và bộ ba | Đoạn đề nghị | Lý do |
| --- | --- | --- | --- |
| 5 | `M2-4B8BF98567370412` · Jensen Huang → `is_CEO_of` → NVIDIA | B · `[1952, 1980)` | Đoạn ngắn xác định đúng Jensen Huang và chức CEO tại NVIDIA. |
| 6 | `M2-E0E4DD5A5F513CA6` · Altman → `invested_in` → Reddit | B · `[948, 1097)` | Bài dẫn hồ sơ SEC và nêu trực tiếp khoản đầu tư của Altman vào Reddit. |
| 7 | `M2-AB4115954B44E7A6` · Neo → `released_by` → Neuracle Medical Technology | A · `[1327, 1593)` | Đoạn nêu Neo đã được thương mại hóa và hệ thống của Neuracle được chấp thuận bán ra thị trường. |
| 8 | `M2-4DD3AE2E00273F7F` · NIC → `partners_with` → FPT | A · `[2020, 2142)` | Đoạn nêu đích danh hai bên đã cùng triển khai các dự án bán dẫn. |
| 9 | `M2-2EDF43C1577473FB` · Mô hình → `integrated_into` → ChatGPT | A · `[16, 289)` | Đoạn gọi tên GPT-5.2 rồi xác nhận mô hình được tích hợp vào ChatGPT. |

## 3. Xác nhận

- ☐ Chốt cả 9 mục theo dự thảo.
- ☐ Chốt sau khi điều chỉnh các mục sau đây …………………………

**Người xác nhận** …………………………

**Ngày xác nhận** …………………………
