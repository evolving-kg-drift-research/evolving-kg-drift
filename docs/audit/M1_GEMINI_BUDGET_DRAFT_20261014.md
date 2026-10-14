# Dự toán Gemini extraction — chưa là ngân sách được duyệt

Ngày: 14/10/2026. Model được user chọn: `gemini-3.8-flash`.
**PLANNING SCENARIOS ONLY — không kích hoạt API capture.**

Theo [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), standard
paid text input/output đến 31/12/2026 lần lượt là USD 0,75/3,75 mỗi triệu tokens;
output gồm thinking tokens. Kiểm tra lại giá và quyền truy cập trước capture.

Pool recovered v3 có 4.745 bodies, tổng 13.461.224 characters, median 2.614,
max 21.039; 50 bài dài nhất có tổng 741.702 characters. Đây là thống kê pool
để lập dự toán, không phải eligibility/corpus selection hoặc pilot IDs đã khóa.

Công thức mỗi attempt:

```text
cost = input_tokens / 1e6 × input_price
     + billed_output_tokens / 1e6 × output_price
```

Ví dụ planning với 4.096 output tokens và 2.000 prompt/schema overhead tokens
mỗi bài, ước lượng text tokens ≈ characters/3:

| Scenario | Ước lượng USD một attempt/bài |
|---|---:|
| 50 bài có độ dài median của pool | Khoảng 0,88 tổng |
| 50 bài dài nhất của pool | Khoảng 1,03 tổng |
| 600 bài ở median | Khoảng 10,51 tổng |
| 900 bài ở median | Khoảng 15,77 tổng |
| Toàn pool 4.745 bodies | Khoảng 83,37 tổng |

Đây không phải tokenization thật, quote bảo đảm hoặc quyết định main corpus.
Ba attempts có thể làm các số trên tăng khoảng ba lần. Output cap/overhead và
text-token approximation chỉ là assumptions của bảng, chưa là frozen config.

Trước execution cần: approved eligible article inventory, exact request payload,
actual provider token-count/capability check có log, giới hạn output/thinking,
pricing version, reserve bound/attempt và trần pilot/main được duyệt. Unknown
billing/timeouts vẫn giữ reservation; không miễn phí giả hoặc bỏ attempt lỗi.

Budget/config không có default. Những bài vượt input bounds cần review;
không truncate để khớp chi phí. Không có Gemini request nào đã được gửi trong
lượt dựng engineering này.
