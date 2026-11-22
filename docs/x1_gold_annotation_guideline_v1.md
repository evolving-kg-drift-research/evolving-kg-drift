# Hướng dẫn gán nhãn gold — pilot X1 (v1)

Áp dụng cho `configs/x1_reextraction_pilot_v34.yaml`. Hai người gán **độc lập**, không xem kết quả
Gemini hay claim cũ (`v1_local`), không trao đổi cho tới khi cả hai nộp bản gán.

## 1. Đơn vị gán nhãn
Mỗi dòng là một quan hệ `(chủ thể, quan hệ, khách thể)` mà **bài báo khẳng định**, giữa hai thực thể **có tên**.
Đọc toàn bài, không chỉ tiêu đề/sapo. Không dùng kiến thức ngoài bài.

## 2. Bảng gán (một tệp CSV mỗi người)
| Cột | Nội dung |
|---|---|
| `article_id` | `body_variant_id` trong manifest mẫu |
| `subject` | tên riêng chép nguyên văn từ bài |
| `relation` | một trong 10 quan hệ ở mục 3 |
| `object` | tên riêng chép nguyên văn từ bài |
| `evidence_text` | một câu nguyên văn làm bằng chứng |
| `is_speculative` | `true` nếu kế hoạch / tin đồn / dự kiến |
| `is_negative` | `true` nếu bài phủ nhận |
| `note` | tùy chọn, ghi ca khó |

Bài không có quan hệ nào: ghi một dòng chỉ có `article_id` và `note = NO_FACT` (để phân biệt với bài quên gán).

## 3. Quan hệ (ontology 1.1)
| Quan hệ | Chủ thể → Khách thể | Gán khi | Không gán khi |
|---|---|---|---|
| `is_CEO_of` | Người → Tổ chức | CEO, tổng giám đốc điều hành | chủ tịch HĐQT, phó TGĐ (→ `works_at`) |
| `works_at` | Người → Tổ chức | giữ chức vụ / làm việc / "cựu …" nếu bài nêu rõ | đã gán `is_CEO_of` cho cùng cặp |
| `acquired_by` | Tổ chức/Sản phẩm → Tổ chức mua | thương vụ mua lại được công bố | chỉ là đầu tư một phần (→ `invested_in`) |
| `released_by` | Mô hình/Sản phẩm/Phần mềm → Tổ chức | tổ chức phát triển hoặc ra mắt | chỉ phân phối/bán lại |
| `version_of` | X → dòng Y | X là phiên bản/biến thể của Y ("GPT-4o" → "GPT-4") | hai sản phẩm khác dòng |
| `succeeded_by` | X → Y | Y là bản kế nhiệm của X | chỉ so sánh hai sản phẩm |
| `partners_with` | Tổ chức ↔ Tổ chức | hợp tác, ký kết, đồng tổ chức (gán một chiều, thứ tự bất kỳ) | quan hệ khách hàng mua sản phẩm thông thường |
| `invested_in` | Tổ chức/Người → Tổ chức | rót vốn, góp vốn | tài trợ nghiên cứu, quyên góp |
| `integrated_into` | Mô hình/Sản phẩm/Phần mềm → Sản phẩm/Phần mềm/Nền tảng | X được đưa vào bên trong Y | Y chỉ "hỗ trợ" X |
| `based_on` | Mô hình/Sản phẩm/Phần mềm → Mô hình/Phần mềm | X xây dựng trên / chạy bằng Y | chỉ "lấy cảm hứng" |

Chú ý chiều: `released_by` và `acquired_by` có chủ thể là sản phẩm/công ty bị mua, không phải tổ chức ra mắt/đi mua.

## 4. Thực thể
- **Chỉ tên riêng.** Không gán đại từ ("ông", "bà", "công ty này") hay danh từ chung ("chatbot", "laptop mới",
  "trợ lý AI"). Nếu đại từ chỉ một người/tổ chức **được nêu tên ở chỗ khác trong cùng bài**, gán bằng tên đó.
- Chép tên đúng một dạng xuất hiện trong bài; không cần thống nhất alias (bộ chấm điểm chuẩn hóa bằng
  `entity_map_v2`).
- Mã model trong ngoặc giữ nguyên ("Zenbook 14 (UM3406GA)").

## 5. Ca khó
- Một câu nêu nhiều đối tác ("hợp tác với A, B, C") → một dòng cho mỗi cặp.
- Tin "dự kiến mua lại", "đang đàm phán" → gán với `is_speculative = true`.
- Không chắc → vẫn gán và ghi `note`; ca này sẽ được phân xử.

## 6. Phân xử
Sau khi cả hai nộp: tính F1 giữa hai người (theo quy tắc khớp của bộ chấm điểm). F1 < 0,70 → dừng, sửa hướng dẫn,
không chấm. Nếu đạt: hai người thảo luận từng bất đồng; chưa thống nhất thì người thứ ba quyết. Giữ nguyên hai bản
gán gốc; bản sau phân xử được khóa bằng SHA-256 trước khi chấm Gemini.
