# Hướng dẫn chấm quan hệ M2 V3.1

**Phiên bản v2.0-hiệu-chuẩn · 11/11/2026 · Chờ người phân xử xác nhận**

Mỗi phiếu nêu một bộ ba ứng viên và dẫn đến một phiên bản thân bài đã lưu. Người phân xử ghi riêng căn cứ cho quan hệ, kiểu của hai thực thể và vị trí đoạn quyết định. Các nhãn A/B được giữ để đối chiếu cách hiểu tiêu chí cũ. Chỉ dùng phiếu này cho 10 ca đã chọn.

## 1. Căn cứ trong bài

| Nhãn | Khi áp dụng |
| --- | --- |
| Hỗ trợ | Đoạn dẫn xác định đúng hai thực thể, đúng vai trò và chiều quan hệ, đúng trạng thái hay sự kiện mà bộ ba biểu đạt. |
| Không hỗ trợ | Đoạn dẫn có căn cứ bác bỏ mệnh đề, chẳng hạn nguồn gắn sự kiện đó với đối tượng khác, nêu chiều ngược lại hoặc phủ định quan hệ. Ghi rõ chi tiết bác bỏ. |
| Chưa đủ căn cứ | Nội dung đã xem còn mơ hồ, chỉ nói về một quan hệ khác, hoặc chỉ nêu khả năng hay dự kiến. Nêu thông tin còn thiếu để xác nhận bộ ba. |

Với `released_by`, xác nhận một lần phát hành, ra mắt hoặc đưa đúng sản phẩm ra cung cấp bởi đúng tổ chức. Chấp nhận cách diễn đạt tương đương khi câu văn xác lập được sự kiện. Thông tin sở hữu, phát triển, nghiên cứu, thử nghiệm, giá, kế hoạch hoặc phát hành một sản phẩm khác tự thân chưa đủ để suy ra sự kiện đang xét.

## 2. Kiểu của hai thực thể

Chọn kiểu của thực thể đầu và cuối dựa trên đối tượng thật sự được nói đến trong bài. Giải thích căn cứ cho cả hai và ghi cách bài gọi đối tượng nếu đối tượng nằm ngoài danh mục. Phiếu so sánh hai lựa chọn với kiểu đầu và cuối cho phép trong ontology 1.1.

- **Đúng kiểu** khi cả hai kiểu đã xác minh thuộc phạm vi của quan hệ.
- **Sai kiểu** khi xác minh được ít nhất một kiểu nằm ngoài phạm vi. Kết quả này vẫn áp dụng nếu kiểu còn lại chưa xác minh.
- **Chưa xác minh kiểu** khi chưa thấy kiểu nào sai nhưng còn ít nhất một kiểu chưa đủ căn cứ.

Giữ kết quả về quan hệ ở mục 1 ngay cả khi kiểu thực thể sai hoặc chưa xác minh. Kiểu trong phiếu mô tả đối tượng của câu báo. Hiệu lực ánh xạ thực thể tại từng mốc cắt được kiểm tra riêng.

## 3. Vị trí đoạn quyết định

Với nhãn hỗ trợ hoặc không hỗ trợ, bôi đen đoạn liên tục ngắn nhất đủ để một người khác hiểu căn cứ. Giữ thêm câu liền kề nếu cần làm rõ tên, đại từ hoặc hành động. Phiếu ghi vị trí bắt đầu (tính từ 0) và vị trí kết thúc (loại trừ), đếm theo điểm mã Unicode trong đúng thân bài. Phiếu xác định vị trí theo thứ tự sau.

1. **Đoạn gốc** nếu phần đã chọn nằm trọn trong một đoạn trích gốc.
2. **Ngữ cảnh liền kề** nếu phần đã chọn nằm trọn trong một vùng gồm đoạn gốc và ngữ cảnh đã cung cấp cho A/B, sau khi xét trường hợp trên.
3. **Đoạn khác cùng bản lưu** nếu phần đã chọn nằm ở vị trí khác trong cùng thân bài.
4. **Chưa có đoạn đủ** nếu chọn nhãn chưa đủ căn cứ. Nêu điều còn thiếu trong lý do và để trống đoạn quyết định.

Hai vị trí tìm lại được chỉ là gợi ý. Hãy kiểm tra câu dẫn, đúng đối tượng và hướng quan hệ trước khi dùng. Sau khi nhận tệp, người phụ trách sẽ đối chiếu lại nguyên văn với vị trí đã ghi, tính SHA-256 của đoạn và giữ mã băm thân bài, mã bản lưu và mốc quan sát. Đoạn bổ sung chỉ có thể dùng cho một snapshot nếu bản lưu chứa đoạn đó có mốc quan sát không muộn hơn mốc cắt của snapshot.

## 4. Nộp và ghi nhận hiệu chuẩn

Điền mã người phân xử, hoàn thành cả 10 ca và ghi kết luận về hướng dẫn. Nếu cần sửa, nêu điều khoản và mã ca khiến cách áp dụng chưa rõ. Tải tệp `m2_hieu_chuan_v2.json` và gửi riêng cho người phụ trách. Có thể lưu một bản nháp trên máy rồi nạp lại bằng chính phiếu đã phát. Mỗi tệp mang mã bộ hiệu chuẩn và mã băm hướng dẫn để kiểm tra khi nhận.

Đây là nhóm ca đã xem, chọn có chủ đích để làm rõ ranh giới của tiêu chí. Giữ riêng kết quả hiệu chuẩn và phiếu A/B ban đầu. Sau khi xác minh 10 ca và chốt hướng dẫn, đánh giá cách áp dụng trên nhóm chưa chấm trước khi quyết định mở rộng.
