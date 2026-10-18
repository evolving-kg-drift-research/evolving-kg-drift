# QUY TRÌNH THU THẬP VÀ XỬ LÝ DỮ LIỆU BẰNG HOSTED LLM API

**Điểm tích hợp:** cuối bước 9; tác vụ LLM đầu tiên ở bước 10.  
**Phạm vi:** từ nguồn bài viết lịch sử đến đồ thị tri thức có thời gian.  
**Ngày biên soạn:** 17/09/2026.  
**Trạng thái:** đặc tả quy trình và kiểm soát triển khai; không phải báo cáo pipeline đã chạy hoặc dữ liệu đã đạt chất lượng.

## 1. Mục tiêu, phạm vi và căn cứ

### 1.1. Mục tiêu và định hướng mới

Pipeline (chuỗi công đoạn xử lý) có nhiệm vụ chuyển các bài viết thành thông tin có cấu trúc, xác định thực thể, quan hệ, bằng chứng và thời gian, sau đó xây dựng Temporal Knowledge Graph (đồ thị tri thức có thời gian).

Phương án mới sử dụng Hosted LLM API (mô hình ngôn ngữ lớn do nhà cung cấp vận hành, được gọi qua giao diện lập trình). Ranh giới trách nhiệm được xác định như sau:

- **Bước 1–9:** mã xử lý thực hiện thu thập, bảo toàn nguồn, trích nội dung và khử trùng.
- **Cuối bước 9:** mã xử lý chuẩn bị gói đầu vào cho LLM (mô hình ngôn ngữ lớn).
- **Bước 10:** LLM đọc nội dung và hỗ trợ phân loại bài.
- **Bước 13–16:** LLM trích thông tin; mã xử lý kiểm tra và chuẩn hóa.
- **Bước 17:** quy tắc đã khóa quyết định thông tin được chấp nhận; người kiểm xử lý trường hợp chưa đủ căn cứ.
- **Bước 18–19:** mã xử lý lưu lịch sử và dựng các lát cắt đồ thị.

Việc dùng LLM thay đổi công cụ đọc hiểu văn bản, không tự động thay đổi yêu cầu khoa học của đề tài.

### 1.2. Đầu ra và điểm dừng

Đầu ra cuối cùng gồm:

1. Tập nguồn và văn bản có thể truy vết.
2. Các quyết định lọc bài.
3. Thực thể và ánh xạ thực thể có phiên bản.
4. Các phát biểu kèm bằng chứng, trạng thái và thời gian.
5. Kho thông tin được chấp nhận có phiên bản.
6. Các lát cắt KG (Knowledge Graph — đồ thị tri thức).
7. Dữ liệu Parquet chuẩn và bản biểu diễn trên Neo4j.
8. Báo cáo chất lượng, chi phí, đối chiếu và tái lập.

Nhánh này kết thúc trước phần huấn luyện mô hình biểu diễn, đo độ trôi và đánh giá suy luận đa bước. Không chuyển nhiệm vụ sang xây chatbot, hệ hỏi đáp truy xuất đồ thị hoặc tinh chỉnh LLM.

“Chạy toàn bộ tập bài” nghĩa là mọi đơn vị đầu vào trong phạm vi đều được kiểm kê và có trạng thái xử lý. Không có nghĩa mọi bài hoặc mọi phát biểu đều phải được nhận vào KG.

### 1.3. Căn cứ và giới hạn

| Căn cứ | Phần được sử dụng |
|---|---|
| Sơ đồ 19 bước A–E đã trao đổi | Cách đánh số và tổ chức giai đoạn |
| `master(1).md`, cập nhật 16/09/2026 | Phương án Hosted API, chạy lại từ nguồn, giới hạn trách nhiệm LLM, vận hành và kiểm soát agent |
| `data01.pdf`, “Quy trình dữ liệu cho đồ thị tri thức tiến hóa — Bản 3” | Nguyên tắc khoa học, thời gian, phiên bản, chất lượng, khóa cấu hình, ranh giới lát cắt và nghiệm thu |
| Đề cương Nhóm 8, phần dữ liệu, thuật toán và kế hoạch thí điểm | Phạm vi Data/KG, ưu tiên chất lượng, thí điểm 30–50 bài và miền ứng viên 8–12 lát cắt |

Báo cáo giữ số bước trên ảnh. Số này không trùng hoàn toàn số mục 4.1–4.19 của Bản 3; bảng đối chiếu nằm ở cuối tài liệu. Các công đoạn ảnh trình bày gọn được mở rộng để không bỏ sót yêu cầu.

Tài liệu chưa xác nhận trạng thái kho mã thực tế, chưa chứng nhận chất lượng dữ liệu và không tự cấp quyền gọi API. Tên tệp, tên trường bổ sung, mã cổng kiểm tra và giao diện thao tác là đề xuất cần ánh xạ với cấu trúc thật của dự án.

Quy mô 600–900 bài và 8–10 quan hệ trong đề cương là ước lượng khởi đầu. Những số của đợt chạy cũ như 48 bài thí điểm hoặc 3.326 tài liệu không phải hạn ngạch hay đáp án cho đợt mới. Nếu kho mã có bộ quan hệ đã được phê duyệt khác ước lượng khởi đầu, giữ bản được phê duyệt sau khi xác minh.

Việc thầy giáo cho phép dùng Hosted API là định hướng đã thống nhất. Nhà cung cấp, mô hình, hạn mức sử dụng và cách đáp ứng yêu cầu tái lập vẫn phải dựa trên cấu hình và quyết định thực tế.

## 2. Phân biệt agent, LLM và chương trình xử lý

| Thành phần | Vai trò | Giới hạn |
|---|---|---|
| Agent — tác nhân AI triển khai | Đọc yêu cầu, viết mã, chạy kiểm thử, điều khiển tác vụ được phép, báo cáo tiến độ | Không tự thay yêu cầu khoa học, nguồn, mô hình, ngân sách hoặc tiêu chí nghiệm thu |
| Hosted LLM trong pipeline | Đọc văn bản được gửi và đề xuất thông tin có cấu trúc | Không tự ghi KG, sửa nguồn, tạo mã định danh chuẩn hoặc bổ sung sự kiện ngoài bằng chứng |
| Mã xử lý | Kiểm tra dữ liệu, sinh mã, chuẩn hóa thời gian, áp quy tắc chấp nhận, lưu và dựng KG | Chỉ thực hiện theo cấu hình và quy tắc đã khóa |
| Người dùng/nhóm nghiên cứu/người kiểm | Chốt quyết định khoa học, kiểm chứng nhãn tham chiếu, xử lý trường hợp cần chuyên môn | Không cần duyệt lại từng tác vụ đã thuộc phạm vi được cho phép |

LLM đọc bài chỉ cần nhận nội dung và ngữ cảnh cần thiết. Nó không cần quyền chạy lệnh, sửa tệp, đọc khóa API hay truy vấn đồ thị demo cũ.

## 3. Những nguyên tắc phải giữ

| Nguyên tắc | Cách áp dụng |
|---|---|
| No future leakage — không rò rỉ thông tin tương lai | Không dùng bằng chứng hoặc ánh xạ thực thể chưa đủ điều kiện tại thời điểm đang xét |
| Append-only — chỉ bổ sung, không ghi đè lịch sử | Sửa dữ liệu bằng phiên bản mới; giữ lại phiên bản và quyết định cũ |
| Provenance — truy vết nguồn gốc | Mỗi thông tin truy được về bài, phiên bản, đoạn bằng chứng và quá trình xử lý |
| Deterministic — có tính xác định | Mã xử lý và dựng dữ liệu tuân theo quy tắc cố định; tính ổn định của lần gọi API mới được kiểm tra riêng |
| Outcome-blind — không nhìn kết quả nghiên cứu phía sau để thiết kế dữ liệu | Không dùng kết quả độ trôi, suy luận hoặc kiểm định để chọn bài, chỉnh thời gian hay chọn lát cắt |
| Reproducibility — khả năng tái lập | Lưu dữ liệu, cấu hình, phản hồi, quyết định và phiên bản để kiểm tra chạy lại |

Lời nhắc “chỉ sử dụng nội dung bài” không tự bảo đảm LLM không bị ảnh hưởng bởi kiến thức huấn luyện. Cần kết hợp giới hạn đầu vào, bằng chứng nguyên văn, kiểm tra thời gian và đánh giá ngữ nghĩa bằng mẫu có người kiểm.

## 4. Trình tự vận hành thực tế

19 bước là cách phân chia trách nhiệm. Khi triển khai, phải thử trên mẫu trước khi chạy toàn bộ.

| Chặng | Công việc | Điều kiện chuyển tiếp |
|---|---|---|
| Chuẩn bị | Kiểm tra kho mã, cấu hình, nguồn, quyền và hạn mức; dựng cơ chế kiểm soát agent | Có phạm vi chạy rõ ràng |
| Dựng đầu vào | Thực hiện bước 1–9, tạo gói gửi LLM | Nguồn và nội dung có thể truy vết |
| Kiểm tra luồng | Kiểm thử bằng phản hồi giả lập, chạy thử không gọi API, rồi thử một bài thật khi đủ điều kiện | Chứng minh luồng hoạt động |
| Thí điểm | Chọn mẫu trước lọc, thử toàn bộ chuỗi, tạo nhãn người kiểm và đánh giá | Đạt điều kiện chất lượng đã chốt |
| Khóa và chạy toàn bộ | Khóa cấu hình, xử lý toàn bộ đầu vào thuộc phạm vi | Đúng quyền, đủ ngân sách, cổng thí điểm đạt |
| Dựng và bàn giao KG | Hoàn tất lát cắt, đối chiếu và kiểm tra tái lập | Có hồ sơ nghiệm thu |

Không chạy lọc toàn bộ rồi chỉ kiểm những bài LLM đã giữ, vì cách đó bỏ qua lỗi loại nhầm bài phù hợp. Ontology đã phê duyệt phải có sẵn khi thiết kế tiêu chí lọc; bước 12 xác minh và khóa bản sử dụng, không phải chờ đến đó mới tự tạo các loại quan hệ.

## 5. Giai đoạn A — Khóa nguyên tắc và phạm vi

### Bước 1. Khóa giao thức nghiên cứu

**Mục tiêu:** xác định những yêu cầu không được tự thay đổi trong quá trình triển khai.

**Đầu vào:** đề cương, quy trình Data/KG Bản 3, quyết định cho phép Hosted API và các cấu hình đã phê duyệt.

**Thực hiện:**

1. Agent đọc hướng dẫn kho mã và xác định phiên bản giao thức đang có hiệu lực.
2. Đối chiếu sáu nguyên tắc xuyên suốt.
3. Xác định ý nghĩa các trường thời gian, cách định danh và điều kiện chấp nhận thông tin.
4. Tạo hồ sơ đợt chạy mới, tham chiếu các quy tắc đã khóa.
5. Ghi những lựa chọn còn thiếu: nhà cung cấp, mô hình, hạn mức và cách đáp ứng yêu cầu tái lập.

**Đầu ra:** giao thức được tham chiếu, hợp đồng dữ liệu và danh sách quyết định còn thiếu.

**Kiểm soát agent:** không sửa đè giao thức hoặc bài kiểm tra khoa học để làm chương trình báo đạt. Nếu phát hiện mâu thuẫn, agent trình phương án có tác động cụ thể và tiếp tục những việc độc lập không bị ảnh hưởng.

### Bước 2. Khóa danh mục nguồn

**Mục tiêu:** xác định được phép lấy bằng chứng từ đâu.

**Đầu vào:** danh sách nguồn đã phê duyệt và các nguồn đang có.

**Thực hiện:** ghi mã nguồn, tên miền, loại nguồn, phương thức thu thập, nguồn lưu trữ lịch sử và các giới hạn. Phân biệt nguồn gốc, nguồn đăng lại và nguồn dẫn lời. Xác định phạm vi dữ liệu được gửi cho nhà cung cấp API.

**Đầu ra:** danh mục nguồn có phiên bản.

**Kiểm soát agent:** chỉ thu thập trong phạm vi đã giao. Bổ sung nguồn ngoài danh mục là thay đổi phạm vi, không được tự thực hiện chỉ để tăng số bài.

### Bước 3. Khóa phạm vi tập tài liệu

**Mục tiêu:** xác định miền nội dung, ngôn ngữ, cửa sổ lịch sử và đơn vị thống kê.

**Đầu vào:** giao thức, danh mục nguồn và bộ loại thực thể/quan hệ đã phê duyệt.

**Thực hiện:**

1. Lấy phạm vi từ cấu hình thực tế, không mặc định dùng lại mốc được nhắc trong báo cáo cũ.
2. Phân biệt tài liệu logic, phiên bản nguồn và biến thể nội dung. Một tài liệu có thể có nhiều phiên bản.
3. Tách điều kiện ngày đăng thuộc phạm vi với điều kiện nội dung đã tồn tại tại mốc lịch sử.
4. Quy định xử lý bài không rõ ngày hoặc bản sửa xuất hiện muộn.

**Đầu ra:** cấu hình phạm vi và quy định đơn vị đếm.

**Kiểm soát agent:** không trộn số bài, số phiên bản, số tác vụ API và số phát biểu. Các số của demo cũ không phải chỉ tiêu bắt buộc cho lần chạy mới.

### Bước 4. Khóa chính sách lọc

**Mục tiêu:** có tiêu chí rõ để LLM phân loại và người kiểm đánh giá.

**Đầu vào:** phạm vi nghiên cứu và ontology (bộ định nghĩa loại thực thể, quan hệ và ràng buộc) đã phê duyệt.

**Thực hiện:**

- Viết rubric (bộ tiêu chí đánh giá) bài thuộc miền.
- Xác định ba nhãn: `include` (giữ), `exclude` (loại), `review` (cần xem lại).
- Định nghĩa mã lý do và bằng chứng đi kèm.
- Quy định xử lý văn bản thiếu, lỗi hoặc quá dài.
- Tách quy tắc khoa học đã khóa với tham số cần hiệu chỉnh từ thí điểm.

**Đầu ra:** chính sách lọc, hướng dẫn gửi LLM và cấu trúc phản hồi có phiên bản.

**Kiểm soát agent:** không dùng kết quả độ trôi, tần suất thực thể xuyên các lát cắt hoặc khả năng làm điểm neo căn chỉnh để giữ/loại bài. Bài lỗi trích nội dung phải vào nhánh lỗi, không được coi là bài ngoài miền. Ngưỡng chất lượng được chốt từ thí điểm, không tự đặt số để báo đạt.

## 6. Giai đoạn B — Thu thập và bảo toàn dữ liệu lịch sử

### Bước 5. Tìm và kiểm kê địa chỉ bài viết

**Mục tiêu:** lập danh sách đầy đủ các bài cần xem xét.

**Đầu vào:** danh mục nguồn, phạm vi và danh sách địa chỉ đã có.

**Thực hiện:**

1. Xác minh danh sách địa chỉ đã có.
2. Bổ sung từ RSS (luồng cập nhật bài), sitemap (sơ đồ địa chỉ website), danh sách công khai hoặc kho lưu trữ được phép.
3. Ghi cách phát hiện, thời điểm phát hiện và trạng thái thu thập.
4. Kiểm kê cả nguồn của những bài từng bị loại trong lần chạy cũ.

**Đầu ra:** danh sách địa chỉ và trạng thái xử lý.

**Kiểm soát agent:** lỗi truy cập không được làm bài biến mất khỏi thống kê. Không tải lại toàn bộ nếu nguồn hiện có vẫn đầy đủ và kiểm chứng được.

### Bước 6. Phục hồi phiên bản lịch sử

**Mục tiêu:** có bằng chứng về trạng thái nội dung tại các thời điểm quá khứ.

**Đầu vào:** danh sách bài và nguồn lưu trữ/lịch sử sửa đổi được phép.

**Thực hiện:** thu bản chụp lưu trữ hoặc bản sửa của nhà xuất bản; ghi địa chỉ phiên bản, mốc lưu trữ và quan hệ với bài gốc. Tách ngày đăng khai báo, ngày chụp lưu trữ và ngày dự án tải về. Báo riêng bài chỉ có bản hiện tại.

**Đầu ra:** các phiên bản lịch sử và báo cáo mức bao phủ bằng chứng.

**Kiểm soát agent:** không gán ngày đăng cũ cho đoạn văn hiện tại nếu chưa chứng minh đoạn đó đã tồn tại ở ngày ấy. Không dùng LLM phục dựng nội dung hoặc mốc thời gian còn thiếu. Thiếu bằng chứng lịch sử có thể cản việc đưa thông tin vào lát cắt cũ dù vẫn trích được nội dung hiện tại.

### Bước 7. Lưu nguồn bất biến và trích nội dung

**Mục tiêu:** bảo toàn dữ liệu gốc và tạo văn bản dùng cho xử lý.

**Đầu vào:** HTML (cấu trúc trang web), văn bản hoặc bản lưu trữ đã tải.

**Thực hiện:**

1. Lưu dữ liệu gốc cùng mã nguồn, địa chỉ và thời điểm tải thực tế.
2. Gắn hash (mã băm kiểm tra nội dung); xác minh trước khi tái sử dụng nguồn.
3. Dùng parser (bộ phân tích nội dung) có phiên bản để tách tiêu đề và body (phần thân bài).
4. Ghi cờ chất lượng: rỗng, thiếu nội dung, lẫn menu, lỗi mã hóa hoặc trích xuất thất bại.
5. Giữ liên kết từ văn bản đã trích về đúng nguồn.

**Đầu ra:** nguồn bất biến, bảng phiên bản, văn bản đã trích và báo cáo lỗi.

**Kiểm soát agent:** không sửa đè nguồn hoặc dùng LLM điền phần văn bản thiếu. Sửa bộ phân tích phải tạo đầu ra có phiên bản mới. Sau khi chốt chuỗi văn bản để định vị bằng chứng, không thay chuỗi mà giữ nguyên vị trí cũ.

### Bước 8. Theo dõi quan hệ nguồn gốc

**Mục tiêu:** phân biệt bản gốc, bản sửa, bài đăng lại và nguồn độc lập.

**Đầu vào:** các phiên bản nguồn, địa chỉ và thông tin quy chiếu.

**Thực hiện:** ghi source lineage (quan hệ kế thừa nguồn); liên kết bản sửa với bản trước; ghi sao chép hoặc dẫn lại khi có căn cứ; lưu phương pháp và trường hợp chưa xác định.

**Đầu ra:** bảng liên kết nguồn, phiên bản và nhóm nguồn phụ thuộc.

**Kiểm soát agent:** hai địa chỉ khác nhau không tự động là hai xác nhận độc lập. “Chưa tìm thấy quan hệ sao chép” không đồng nghĩa “đã chứng minh độc lập”. Quan hệ nguồn gốc phải đi cùng dữ liệu qua các bước sau.

## 7. Giai đoạn C — Khử trùng, lọc bằng LLM và khóa chất lượng

### Bước 9. Khử trùng lặp bằng mã xử lý

**Mục tiêu:** giảm xử lý và đếm trùng mà vẫn giữ bằng chứng.

**Đầu vào:** văn bản đã trích, mã băm, phiên bản và quan hệ nguồn gốc.

**Thực hiện:**

1. Nhóm nội dung giống hệt bằng mã băm theo quy tắc đã định nghĩa.
2. Nhóm gần trùng bằng phương pháp và ngưỡng được kiểm chứng rồi khóa từ thí điểm.
3. Phân biệt bản sao với bản sửa có thay đổi ngữ nghĩa.
4. Giữ thành viên nhóm, đại diện xử lý và căn cứ phân nhóm.
5. Kiểm tra mẫu để phát hiện gộp nhầm.

**Đầu ra:** nhóm trùng lặp, mã tài liệu logic, biến thể nội dung và liên kết về nguồn.

**Kiểm soát agent:** khử trùng là phân nhóm, không phải xóa. Hai bài nói cùng sự kiện không mặc định là bản sao. Bản sửa có thêm thông tin không bị bỏ chỉ vì giống phần lớn nội dung cũ. Trong thiết kế cơ sở, LLM không quyết định gộp hoặc loại nguồn ở bước này.

#### Cuối bước 9: đóng gói đầu vào cho Hosted LLM

Đây là tiểu công đoạn của bước 9, do mã xử lý thực hiện; chưa cần gọi LLM.

| Thành phần | Mục đích |
|---|---|
| Mã tài liệu, biến thể và phiên bản nguồn | Xác định đúng đơn vị đang xử lý |
| Tiêu đề và văn bản đầy đủ | Nội dung để LLM đọc |
| Siêu dữ liệu thời gian có căn cứ | Cung cấp mốc tham chiếu hợp lệ |
| Liên kết nguồn và mã băm | Truy vết và kiểm tra tính toàn vẹn |
| Chính sách lọc hoặc bộ quan hệ | Giới hạn nhiệm vụ được giao |
| Ngữ cảnh thực thể được phép dùng | Hỗ trợ chuẩn hóa mà không đưa thông tin tương lai |
| Cấu trúc phản hồi | Quy định trường dữ liệu, nhãn hợp lệ và cách biểu thị không biết |

Bài quá dài phải chia đoạn theo quy tắc, giữ độ bao phủ toàn văn và vị trí về văn bản gốc. Không cắt phần vượt giới hạn một cách im lặng. Không dùng bản tóm tắt LLM làm nguồn thay thế toàn văn.

Nội dung giống hệt chỉ được dùng chung kết quả khi yêu cầu suy luận tương đương. Khác ngày tham chiếu hoặc ngữ cảnh thực thể có thể cần xử lý riêng. Bằng chứng từng nguồn luôn được giữ; không lấy cách giải nghĩa “hôm qua” của nguồn A áp cho nguồn B.

### Bước 10. Lọc nội dung bằng Hosted LLM

**Mục tiêu:** xác định bài có thuộc phạm vi nghiên cứu hay không.

**Đầu vào:** gói từ cuối bước 9, chính sách lọc và bộ quan hệ liên quan.

**Thực hiện:**

1. Mã xử lý áp các điều kiện cứng có đủ căn cứ, như nguồn được phép.
2. LLM đọc nội dung, trả nhãn giữ/loại/cần xem lại.
3. Phản hồi kèm mã lý do và đoạn căn cứ phù hợp.
4. Validator (bộ kiểm tra đầu ra) kiểm tra cấu trúc, nhãn và căn cứ.
5. Ghi quyết định lọc có phiên bản.
6. Kiểm tra mẫu cả nhóm giữ, nhóm loại và nhóm cần xem lại.

**Đầu ra:** quyết định lọc, tập chuyển sang trích xuất, hàng chờ xem lại và báo cáo lỗi.

**Kiểm soát agent:** lỗi API không phải quyết định loại. `review` không tự chuyển thành `exclude`. Không dùng quyết định của một phiên bản áp mù quáng cho mọi bản sửa. Một bài được giữ vẫn có thể không chứa phát biểu đủ điều kiện đưa vào KG.

### Bước 11. Thí điểm và tạo nhãn tham chiếu mới

**Mục tiêu:** đo chất lượng trước khi chạy diện rộng.

**Đầu vào:** danh sách đầu vào mới trước lọc, hướng dẫn gán nhãn và cấu hình thử nghiệm.

**Thực hiện:**

1. Chọn khoảng 30–50 tài liệu; lưu chính sách chọn mẫu và seed (giá trị khởi tạo việc lấy mẫu).
2. Phủ các nguồn, thời gian, chất lượng văn bản và tình huống khó.
3. Không mặc định lấy lại thành viên demo 48 bài. Nếu trùng bài theo chính sách mới, vẫn tạo nhãn mới từ nguồn.
4. Người kiểm xác nhận nhãn lọc, thực thể, quan hệ, bằng chứng và thời gian.
5. Tách mẫu điều chỉnh hướng dẫn với mẫu đánh giá độc lập; giữ bài cùng nhóm sao chép/nguồn gốc trong cùng nhánh.
6. Chạy thử chuỗi xử lý tới KG; dựng ba lát cắt nhỏ trên dữ liệu thật nếu đủ bằng chứng.
7. Đo chất lượng, lượng sử dụng API, chi phí, thời gian và công người kiểm.

**Đầu ra:** tập thí điểm, nhãn có người kiểm chứng, bảng lỗi và báo cáo chất lượng.

**Kiểm soát agent:** không lấy nhãn demo cũ làm đáp án; không để LLM tự tạo đáp án rồi tự chấm. Nếu mẫu chỉ đủ để phát triển thì ghi rõ và bổ sung kiểm chứng độc lập trước khi mở rộng. Dữ liệu giả chỉ kiểm tra logic, phải tách khỏi dữ liệu nghiên cứu; không tạo sự kiện để đủ số lát cắt.

### Bước 12. Xác minh ontology và khóa cấu hình

**Mục tiêu:** bảo đảm toàn bộ tập bài được xử lý nhất quán.

**Đầu vào:** bộ thực thể/quan hệ đã phê duyệt, quy tắc định danh và kết quả thí điểm.

**Thực hiện:**

1. Xác minh từng quan hệ có định nghĩa rõ.
2. Xác định loại chủ thể, đối tượng, phạm vi và cardinality (ràng buộc một hay nhiều giá trị).
3. Phân biệt quan hệ sự kiện với quan hệ trạng thái; xác định cách phân biệt sự kiện lặp lại.
4. Giữ bộ đã phê duyệt; thay đổi khoa học phải có quyết định riêng.
5. Sau thí điểm, khóa nhà cung cấp, mô hình, hướng dẫn, cấu trúc đầu ra, tham số sinh và toàn bộ quy tắc xử lý.
6. Khóa ngưỡng chất lượng, chính sách lỗi và phiên bản bộ dựng lát cắt.

**Đầu ra:** cấu hình frozen (đã đóng băng), bộ định nghĩa và điều kiện chạy toàn bộ.

**Kiểm soát agent:** thay thành phần ảnh hưởng kết quả phải tạo phiên bản mới và xác định phạm vi xử lý lại. Nếu chưa chứng minh được phạm vi ảnh hưởng, đánh giá lại hoặc xử lý lại phạm vi rộng hơn. Không trộn bộ trích xuất khác nhau giữa các phần lịch sử. Toàn bộ tập bài, gồm cả bài thí điểm, phải qua cấu hình đã khóa; chỉ dùng lại kết quả nếu đủ điều kiện tương đương.

## 8. Giai đoạn D — Từ văn bản sang thông tin có thời gian

### Bước 13. Nhận diện và chuẩn hóa thực thể

**Mục tiêu:** xác định những tên trong bài đang chỉ đến thực thể nào.

**Đầu vào:** bài được giữ, bộ định nghĩa, danh mục ứng viên mới và ngữ cảnh đủ điều kiện theo thời gian.

**LLM thực hiện:**

- Trích mention (tên hoặc cụm từ nhắc đến thực thể).
- Đề xuất loại thực thể trong bộ cho phép.
- Hỗ trợ chọn trong danh sách ứng viên khi cần.
- Báo chưa đủ căn cứ nếu không phân giải được.

**Mã xử lý thực hiện:**

- Tạo danh sách ứng viên từ quy tắc và bí danh có bằng chứng.
- Sinh mã thực thể theo hợp đồng định danh.
- Ghi căn cứ ánh xạ và thời điểm ánh xạ được phép sử dụng.
- Giữ phiên bản khi ánh xạ được sửa.

**Đầu ra:** danh mục thực thể mới, các tên xuất hiện và ánh xạ có phiên bản.

**Kiểm soát agent:**

- Không nối thẳng vào danh mục demo cũ như đáp án.
- Không gộp hai thực thể chỉ vì tên gần giống.
- Không mặc định mọi phiên bản sản phẩm là một thực thể.
- Không dùng bí danh chỉ biết ở tương lai để phân giải ngược lịch sử.
- Danh mục phải nhất quán giữa các đợt xử lý, không tạo hệ định danh riêng cho từng đợt.

### Bước 14. Trích xuất phát biểu có cấu trúc

**Mục tiêu:** lấy các claim (phát biểu do nguồn đưa ra).

**Đầu vào:** văn bản, bộ quan hệ, hướng dẫn gán nhãn và cấu trúc phản hồi.

Một phát biểu thường gồm chủ thể, quan hệ, đối tượng, trạng thái khẳng định/phủ định, tính chất đã xảy ra/dự kiến/kỳ vọng/có điều kiện, bằng chứng và biểu thức thời gian liên quan.

LLM chỉ chọn quan hệ trong bộ đã khóa. Mã xử lý kiểm tra loại thực thể, hướng quan hệ và ràng buộc. Các bước 13–16 có thể dùng chung một tác vụ trích xuất kết hợp; thứ tự đánh số không bắt buộc mỗi bước là một lần gọi API riêng.

**Đầu ra:** danh sách phát biểu ứng viên, có thể từ 0 đến nhiều phát biểu cho một bài.

**Kiểm soát agent:** không ép bài nào cũng có phát biểu. Phân biệt phản hồi hợp lệ có 0 phát biểu với tác vụ thất bại. Không biến dự kiến thành sự kiện đã xảy ra; không dùng kiến thức sẵn có của LLM để bổ sung quan hệ không được nguồn hỗ trợ.

### Bước 15. Gắn và xác minh đoạn bằng chứng

**Mục tiêu:** mọi phát biểu đều có căn cứ trong đúng phiên bản nguồn.

**Đầu vào:** phát biểu ứng viên, đoạn trích do LLM đề xuất và văn bản gốc của đợt chạy.

**Thực hiện:**

1. LLM trả đoạn nguyên văn hỗ trợ phát biểu.
2. Mã xử lý định vị đoạn đó trong văn bản gốc.
3. Kiểm tra đoạn trích khớp vị trí đã ghi.
4. Nếu đoạn xuất hiện nhiều lần, phân giải bằng ngữ cảnh.
5. Giữ liên kết từ đoạn đã chia về toàn văn.
6. Đánh giá xem đoạn trích thực sự chứng minh phát biểu hay không.

Kiểm tra ký tự tối thiểu:

```python
body_text[start:end] == evidence_text
```

Trong đó `body_text` là văn bản nguồn đã chốt; `start` và `end` là vị trí bắt đầu/kết thúc; `evidence_text` là đoạn bằng chứng.

**Đầu ra:** đoạn bằng chứng, vị trí và liên kết nguồn.

**Kiểm soát agent:** khớp ký tự chưa chứng minh đúng ngữ nghĩa. Một đoạn nhắc A và B chưa chắc chứng minh quan hệ đề xuất giữa A và B. Bằng chứng thời gian có thể nằm ở đoạn khác với bằng chứng quan hệ; cả hai phải thuộc nguồn phù hợp và được liên kết rõ.

### Bước 16. Chuẩn hóa thời gian

**Mục tiêu:** tách các loại thời gian và xác định mốc có căn cứ.

**Đầu vào:** phát biểu, bằng chứng, biểu thức thời gian và siêu dữ liệu có căn cứ.

| Trường | Ý nghĩa |
|---|---|
| `valid_from` | Mốc bắt đầu hiệu lực theo nội dung nguồn |
| `valid_to` | Mốc kết thúc khi có căn cứ |
| `evidence_observed_at` | Mốc chứng minh đúng trạng thái nội dung đã công khai |
| `accepted_into_kg_at` | Mốc sớm nhất bằng chứng đủ theo quy tắc để chấp nhận thông tin |
| `ingested_at_real` | Thời điểm dự án thực tế nạp/xử lý dữ liệu |
| `time_basis` | Căn cứ xác định thời gian |
| `time_precision` | Độ chính xác: ngày, tháng, năm hoặc mức khác |
| `inferred` | Cho biết thời gian được suy ra theo quy tắc hay không |

Tên trường bổ sung cần ánh xạ với hợp đồng dữ liệu thực tế, không tạo cột trùng nghĩa. Thời điểm tải nguồn và thời điểm người kiểm thực sự làm việc cũng được lưu riêng để truy vết; không thay thế thời gian khoa học.

**LLM thực hiện:** tìm các biểu thức như “hôm qua”, “từ tháng 5”, “dự kiến năm sau” và đề xuất vai trò của chúng.

**Mã xử lý thực hiện:** tính ngày từ mốc quy chiếu hợp lệ; xử lý múi giờ, độ chính xác và quy tắc đã khóa.

**Đầu ra:** phát biểu có thời gian chuẩn hóa, căn cứ, mức chính xác và trạng thái đủ/chưa đủ điều kiện.

**Kiểm soát agent:**

- Ngày đăng không mặc định là ngày sự kiện có hiệu lực.
- Ngày tải không mặc định là ngày bằng chứng xuất hiện.
- Không có mốc quy chiếu thì không tự tính “hôm qua”.
- Chỉ biết tháng thì không trình bày thành ngày chính xác mà không ghi quy ước.
- `valid_to` có thể để trống khi khoảng hiệu lực chưa biết kết thúc; để trống không khẳng định tồn tại vĩnh viễn.
- Thiếu `valid_from` phải giữ chưa rõ hoặc áp đúng quy tắc suy ra đã được phê duyệt; không tự điền ngày tải, năm 1970 hoặc mốc đầu tập bài.
- Không dùng ngày bài tiếp theo hoặc ngày sản phẩm mới ra mắt để tự đóng thông tin cũ.
- Dự kiến không tự chuyển thành đã xảy ra khi đồng hồ đi qua ngày dự kiến.
- Quan hệ sự kiện và quan hệ trạng thái có quy tắc thời gian riêng; không tùy tiện biến sự kiện tức thời thành khoảng rỗng.

Thông tin thiếu điều kiện thời gian có thể được giữ để xem lại nhưng không tự động được đưa vào lát cắt nghiêm ngặt.

### Bước 17. Xét chấp nhận và giải quyết mâu thuẫn

**Mục tiêu:** phân biệt phát biểu của nguồn với thông tin được giao thức chấp nhận.

**Đầu vào:** các phát biểu đã kiểm tra, bằng chứng, quan hệ nguồn gốc và quy tắc chấp nhận.

**Thực hiện:**

1. Nhóm phát biểu liên quan theo quy tắc định danh, phạm vi và thời gian.
2. Xem xét quan hệ phụ thuộc giữa nguồn.
3. Áp quy tắc chấp nhận đã khóa.
4. Lưu bằng chứng hỗ trợ và lý do quyết định.
5. Chuyển trường hợp chưa đủ căn cứ cho người kiểm.
6. Xác định thời điểm bằng chứng đủ điều kiện chấp nhận.

LLM có thể chỉ ra mâu thuẫn hoặc đề xuất phân tích. Quyết định cuối do quy tắc của chương trình hoặc người kiểm có thẩm quyền đưa ra. Không bắt buộc người dùng duyệt từng phát biểu đã đáp ứng quy tắc, trừ khi hợp đồng đã chốt yêu cầu như vậy.

**Đầu ra:** quyết định chấp nhận, từ chối hoặc chưa giải quyết; kèm căn cứ và thời gian.

**Kiểm soát agent:**

- Không mặc định hai bài sao chép là hai nguồn xác nhận.
- Không dùng độ tự tin do LLM tự khai làm bằng chứng đúng.
- Không dùng bằng chứng xuất hiện muộn để cho thông tin vào lát cắt sớm.
- Không lấy ngày người kiểm làm việc làm ngày chấp nhận lịch sử.
- Nếu người kiểm dùng thêm bằng chứng muộn, mốc chấp nhận phải phản ánh bằng chứng đó.
- Không mặc định ngày nguồn đầu tiên là ngày đủ điều kiện chấp nhận trong mọi trường hợp.

Cần tách ba trạng thái: `accepted` (đạt quy tắc chấp nhận), `human_verified` (đã được người kiểm xác nhận), `temporal_eligible` (đủ điều kiện thời gian cho mục đích đang xét). Ba trạng thái này không đồng nghĩa.

### Bước 18. Lưu thông tin có phiên bản

**Mục tiêu:** bảo toàn lịch sử thông tin được chấp nhận.

**Đầu vào:** quyết định chấp nhận, phát biểu, ánh xạ thực thể và bằng chứng.

**Thực hiện:**

- Tạo LogicalFactID (mã thông tin logic xuyên các phiên bản).
- Tạo FactVersionID (mã phiên bản thông tin bất biến).
- Lưu thực thể, quan hệ, thời gian, bằng chứng và quyết định chấp nhận.
- Ghi quan hệ thay thế, đính chính hoặc rút lại.
- Giữ phiên bản trước để dựng lại lịch sử.

**Đầu ra:** kho phiên bản thông tin và các bảng liên kết nguồn.

**Kiểm soát agent:** không dùng cùng công thức định danh cho mọi loại quan hệ. Quan hệ đơn trị, đa trị và sự kiện lặp lại phải tuân theo định nghĩa đã khóa. Sửa trường ngữ nghĩa hoặc thời gian phải tạo phiên bản phù hợp, không sửa âm thầm tại chỗ. Không xóa bản rút lại trước khi dựng lịch sử; không sửa trực tiếp cạnh Neo4j để “chữa” kết quả mà bỏ qua nguồn và phiên bản.

## 9. Giai đoạn E — Dựng KG theo thời gian

### Bước 19. Dựng lát cắt, đối chiếu và bàn giao

**Đầu vào:** kho phiên bản thông tin, ánh xạ thực thể, các quy tắc đã khóa và kết quả kiểm tra chất lượng.

Bước này trong ảnh được trình bày gọn. Khi triển khai phải gồm các công đoạn sau.

#### 19.1. Tạo sự kiện thay đổi KG

Một sự kiện KG là thay đổi trạng thái thông tin, chẳng hạn thêm, sửa, kết thúc hoặc rút lại. Nhiều bài cùng đưa tin về một thay đổi không mặc định tạo nhiều sự kiện.

**Đầu ra:** bảng sự kiện có định danh, thời gian và liên kết tới phiên bản thông tin. Cách xác định sự kiện tuân theo ngữ nghĩa quan hệ đã khóa.

#### 19.2. Kiểm tra tính khả thi

Kiểm tra mức bao phủ bằng chứng lịch sử, số sự kiện, thay đổi cạnh, mức chồng lấp thực thể giữa các thời điểm, khả năng có thực thể làm điểm neo căn chỉnh và khả năng hỗ trợ câu hỏi suy luận lặp lại.

Đây là kiểm tra khả thi cho phần nghiên cứu tiếp theo, không phải xây toàn bộ bộ câu hỏi đánh giá. Khả năng hỗ trợ câu hỏi là điều kiện đạt/không đạt, không là mục tiêu tối ưu để chọn ranh giới.

Nếu thiếu dữ liệu, lập phương án bổ sung nguồn trong phạm vi hoặc đề xuất điều chỉnh phạm vi. Không sửa ngày, tạo sự kiện giả hoặc ưu tiên bài theo kết quả mô hình phía sau.

**Đầu ra:** báo cáo khả thi và các phần thiếu cần xử lý.

#### 19.3. Chọn và khóa ranh giới lát cắt

Áp quy tắc event quantiles (phân vị theo sự kiện) đã được đề cương lựa chọn.

- Miền ứng viên 8–12 lát cắt được xem xét cùng điều kiện khả thi hoặc theo quyết định phạm vi đã được ghi nhận.
- Không ép đủ số lát cắt bằng khoảng không có dữ liệu phù hợp.
- Lưu quy tắc xử lý trường hợp hòa hoặc không đạt.
- Ghi độ dài thời gian thực tế của từng khoảng.
- Khóa ranh giới trước khi xem kết quả độ trôi và suy luận.

**Đầu ra:** ranh giới có phiên bản, mã băm và thông tin từng khoảng chuyển tiếp. Agent không tự chọn mốc vì nhìn đồ thị đẹp hơn hoặc kết quả nghiên cứu tốt hơn.

#### 19.4. Dựng lát cắt theo hai trục thời gian

Bộ dựng nhận hai mốc: `known_at` (được phép biết thông tin tới khi nào) và `valid_at` (xét thông tin có hiệu lực tại khi nào). Trong trường hợp chính, có thể đặt hai mốc cùng bằng T nhưng vẫn phải tách ý nghĩa.

Trình tự khái niệm:

1. Xác định bằng chứng và quyết định chấp nhận đủ điều kiện tại `known_at`.
2. Xét hiệu lực tại `valid_at` theo loại quan hệ và ngữ nghĩa phiên bản đã khóa.
3. Giải quyết các phiên bản theo quy tắc sửa/thay thế.
4. Áp trạng thái rút lại đúng thứ tự.
5. Sử dụng ánh xạ thực thể đủ điều kiện tại `known_at`.
6. Sắp xếp dữ liệu theo quy tắc chuẩn và tính mã băm.

Phải kiểm tra trường hợp thông báo hôm nay nhưng thay đổi có hiệu lực tháng sau: trạng thái cũ vẫn tồn tại trước ngày thay đổi. Không chọn bản mới nhất một cách mù quáng rồi làm mất trạng thái đang có hiệu lực. Không loại bản rút lại quá sớm khiến phiên bản cũ xuất hiện trở lại.

**Đầu ra:** các lát cắt dữ liệu, mã băm và bằng chứng kiểm tra không dùng thông tin tương lai.

#### 19.5. Xuất Parquet và dựng Neo4j

- Canonical Parquet (dữ liệu Parquet chuẩn) là nguồn dữ liệu chính của thí nghiệm.
- Neo4j được dựng từ dữ liệu chuẩn để xem và truy vấn.
- Dùng vùng dữ liệu mới, không xóa demo cũ.
- Đối chiếu tập mã, cạnh, thời gian và nguồn gốc.
- Chuẩn hóa cách biểu diễn giá trị thiếu và kiểu thời gian trước khi so sánh.

Hai bên có cùng số cạnh chưa đủ để kết luận khớp nhau.

**Đầu ra:** dữ liệu chuẩn, bản Neo4j và parity report (báo cáo đối chiếu tương đương dữ liệu).

#### 19.6. Nghiệm thu và bàn giao

Bàn giao lát cắt, ánh xạ thực thể, kho phiên bản, cấu hình, mã băm và báo cáo. Mỗi mục phân biệt rõ: đã chạy và đạt; đã chạy nhưng không đạt; chưa chạy; bị chặn vì thiếu điều kiện.

Không ghi “hoàn tất” chỉ vì Neo4j hiển thị được đồ thị. Phần còn thiếu bằng chứng hoặc chưa đạt phải được ghi trong hồ sơ bàn giao.

## 10. Cách tổ chức các lần gọi LLM

Không cần gọi API riêng cho từng bước 13, 14, 15 và 16. Thiết kế cơ sở gồm:

| Tác vụ | Nội dung |
|---|---|
| Phân loại | Đọc bài và đề xuất giữ/loại/cần xem lại |
| Trích xuất kết hợp | Lấy tên thực thể, quan hệ, bằng chứng, trạng thái phát biểu và biểu thức thời gian |
| Hỗ trợ ca khó khi cần | Phân giải thực thể hoặc phân tích mâu thuẫn trong phạm vi quy tắc |

Sau mỗi tác vụ, mã xử lý kiểm tra và ghi kết quả. Một tác vụ trích xuất có thể cần nhiều yêu cầu API nếu bài dài. Việc chia đoạn phải giữ đủ nội dung và ngăn lấy bằng chứng bài này cho bài khác.

Nội dung bài là dữ liệu. Chỉ dẫn có trong bài như “bỏ qua yêu cầu trước” không được coi là lệnh cho LLM hoặc agent. Ví dụ hướng dẫn trích xuất phải được soạn mới và kiểm chứng từ nguồn, không lấy nhãn demo cũ để ép kết quả mới giống đợt cũ.

Ví dụ giả định: “Công ty A dự kiến phát hành mô hình B vào tháng 12/2026”. LLM có thể đề xuất A, B, quan hệ phát hành, trạng thái dự kiến và mốc tháng 12/2026 nếu phù hợp bộ định nghĩa. Hệ thống không được biến câu này thành “A đã phát hành B”, kể cả khi tháng 12 đã trôi qua; cần bằng chứng phù hợp cho trạng thái đã xảy ra.

## 11. Kiểm soát agent khi triển khai

### 11.1. Lập hồ sơ phạm vi trước khi chạy

Mỗi đợt chạy có run manifest (hồ sơ mô tả đợt chạy), tối thiểu gồm:

| Nhóm | Thông tin |
|---|---|
| Phạm vi | Mã đợt chạy, chế độ, các công đoạn được phép |
| Đầu vào | Danh sách tài liệu/phiên bản và mã băm |
| Đầu ra | Vị trí ghi riêng cho đợt mới |
| Phiên bản | Mã chương trình, cấu hình, hướng dẫn, cấu trúc dữ liệu |
| Hosted API | Nhà cung cấp, mô hình, phiên bản khả dụng, điểm truy cập và khu vực |
| Hạn mức | Số bài, tác vụ, yêu cầu, lượng sử dụng và ngân sách |
| Chính sách lỗi | Số lần thử lại, điều kiện cách ly và điều kiện dừng |
| Điều kiện chuyển bước | Các cổng kiểm tra bắt buộc |

Hồ sơ chỉ lưu tên biến môi trường chứa khóa API, không lưu giá trị khóa. Các giá trị phải lấy từ quyền và cấu hình thực tế. Agent không tự điền ngân sách hoặc cho rằng có khóa API nghĩa là được phép chạy toàn bộ.

Các chế độ đề xuất: `smoke` (thử luồng trên một tài liệu), `pilot` (thí điểm 30–50 tài liệu), `full` (toàn bộ đầu vào đã chốt). Đây là giao diện cần triển khai theo kho mã thực tế, không khẳng định lệnh đã có sẵn. Nếu chỉ được giao thí điểm thì không tự chuyển thành toàn bộ.

### 11.2. Bảo vệ nguồn và kết quả cũ

Trước khi sửa mã, agent kiểm tra trạng thái kho mã và bảo toàn thay đổi đang có của người dùng. Những phần cần bảo vệ gồm:

- Nguồn thô và danh sách phát hiện bài.
- Giao thức, bộ định nghĩa và quy tắc đã khóa.
- Bộ kiểm tra khoa học đã phê duyệt.
- Nhật ký quyết định.
- Kết quả và đồ thị demo cũ.

Đợt mới có đầu ra riêng. Không dùng quyết định lọc, nhãn, ánh xạ, phát biểu hoặc lát cắt cũ làm đáp án chuẩn. Nguồn cũ được tái sử dụng sau xác minh. Mã tiện ích có thể tái sử dụng nếu phù hợp hợp đồng dữ liệu.

Nếu môi trường cho phép, đặt phần nguồn được bảo vệ ở chế độ chỉ đọc và tách quyền ghi đầu ra. Lưu mã băm trước/sau các mốc quan trọng để phát hiện thay đổi. Lời nhắc, lịch sử Git và mã băm không phải ranh giới quyền cứng nếu agent vẫn được sửa mọi tệp.

### 11.3. Phân loại quyền của agent

| Hành động | Cách xử lý |
|---|---|
| Viết mã trong phạm vi đã giao | Tự thực hiện và kiểm thử |
| Chạy kiểm thử bằng dữ liệu giả lập | Tự thực hiện, tách khỏi dữ liệu nghiên cứu |
| Gọi API trong phạm vi và hạn mức đã duyệt | Tự tiếp tục khi điều kiện đạt |
| Thử lại lỗi tạm thời trong giới hạn | Tự thực hiện và ghi lịch sử |
| Chuyển từ thí điểm sang toàn bộ | Chỉ thực hiện nếu phạm vi toàn bộ đã được cho phép và cổng thí điểm đạt |
| Thay nhà cung cấp hoặc mô hình | Cần quyết định phù hợp, phiên bản mới và kiểm chứng lại |
| Thay định nghĩa quan hệ, thời gian, định danh hoặc ngưỡng khoa học | Chuẩn bị phương án để nhóm quyết định |
| Xóa nguồn, sửa lịch sử, lấy nhãn cũ làm chuẩn | Không thuộc phạm vi phương án này |
| Tự ghi đã được người kiểm xác nhận | Không được phép |

Các mốc bàn giao là mốc báo cáo và kiểm chứng, không mặc định là các lần xin phép mới. Nếu quyền đã đủ, agent tiếp tục khi điều kiện đạt. Nếu thiếu quyết định, agent chuẩn bị phương án cụ thể rồi hỏi đúng phần còn thiếu; không hỏi lại sau từng lệnh hoặc từng mã băm.

### 11.4. Cổng kiểm tra do chương trình thực thi

Gate (cổng kiểm tra) là điều kiện chương trình phải xác minh trước khi chuyển sang công đoạn phụ thuộc.

| Cổng đề xuất | Nội dung |
|---|---|
| G0 — Phạm vi | Đúng đầu vào, cấu hình, quyền và giới hạn |
| G1 — Nguồn | Nguồn tồn tại, mã băm đúng, văn bản và quan hệ nguồn có thể truy vết |
| G2 — Luồng API | Yêu cầu/phản hồi được lưu, lỗi được phân loại, đầu ra được kiểm tra |
| G3 — Thí điểm | Chất lượng được đo bằng nhãn người kiểm; ngưỡng và cấu hình được khóa |
| G4 — Chạy toàn bộ | Không bỏ sót đơn vị, không trộn phiên bản, không vượt phạm vi |
| G5 — Thời gian và tính khả thi | Không dùng thông tin tương lai; dữ liệu đủ cho phương án lát cắt |
| G6 — Đối chiếu | Parquet và Neo4j khớp dữ liệu theo hợp đồng |
| G7 — Tái lập và bàn giao | Có bằng chứng chạy lại và báo cáo đúng giới hạn |

Mỗi kết quả cổng ghi mã kiểm tra, đầu vào, cấu hình, phiên bản mã, thời điểm chạy, lệnh/bộ kiểm tra thực thi và đường dẫn bằng chứng. Trạng thái gồm:

- `PASS`: đã kiểm tra và đạt.
- `FAIL`: đã kiểm tra và không đạt.
- `NOT_RUN`: chưa chạy.
- `BLOCKED`: thiếu điều kiện để chạy hoặc nghiệm thu.

Không lấy báo cáo đạt của cấu hình cũ dùng cho cấu hình mới. Agent không được tự viết trạng thái đạt thay cho việc chạy phép kiểm. Thay đổi đầu vào hoặc cấu hình làm mất hiệu lực kết quả kiểm tra phụ thuộc; phải chạy lại theo phạm vi ảnh hưởng và giữ lịch sử báo cáo.

Cổng kỹ thuật không chứng minh ngữ nghĩa đúng. Chất lượng thực thể, quan hệ và thời gian phải đối chiếu với nguồn trên mẫu có người kiểm. Không đổi nhãn tham chiếu hoặc giảm ngưỡng chỉ để vượt cổng.

### 11.5. Phân biệt lỗi một bài với lỗi toàn đợt

| Tình huống | Hành động |
|---|---|
| Một bài tải lỗi hoặc phản hồi sai cấu trúc | Thử lại có giới hạn hoặc cách ly bài; giữ trạng thái |
| Thiếu căn cứ cho một phát biểu | Đưa vào hàng chờ hoặc từ chối theo quy tắc |
| Phát hiện bằng chứng tương lai | Chặn đầu ra phụ thuộc và điều tra phạm vi ảnh hưởng |
| Nguồn được bảo vệ bị thay đổi | Dừng công đoạn phụ thuộc; không nghiệm thu |
| Cấu hình hoặc mô hình lệch bản khóa | Xử lý theo chính sách đã chốt; không trộn kết quả âm thầm |
| Sắp hết ngân sách | Dừng nhận tác vụ mới, lưu tiến độ |
| Thiếu nhãn người kiểm | Chặn nghiệm thu chất lượng; tiếp tục việc kỹ thuật độc lập |

Agent không được biến lỗi thành kết quả rỗng để làm báo cáo đẹp. Các tác vụ độc lập có thể tiếp tục nếu chính sách cho phép, nhưng không được chứng nhận bàn giao đạt khi nguyên tắc bắt buộc vẫn bị vi phạm.

## 12. Kiểm soát API, chi phí và khả năng tiếp tục

### 12.1. Lưu tác vụ bền vững

Cần job ledger (sổ theo dõi tác vụ) để biết mỗi đơn vị đang ở đâu. Trạng thái tối thiểu: chờ xử lý, đang chạy, hoàn tất, thất bại/cách ly, chờ người kiểm.

Trong cùng công đoạn và cùng đơn vị đếm, mỗi mã chỉ có một trạng thái chính. Lịch sử chuyển trạng thái được giữ riêng. Thống kê tài liệu, biến thể nội dung, tác vụ, yêu cầu API và phát biểu ở các cột riêng.

### 12.2. Thử lại có giới hạn

Áp dụng retry/backoff (thử lại và tăng thời gian chờ) cho lỗi tạm thời như giới hạn tốc độ hoặc lỗi máy chủ. Lưu số lần thử, lỗi và quy tắc chọn phản hồi cuối. Không thử vô hạn.

Nếu yêu cầu hết thời gian chờ nhưng chưa biết nhà cung cấp đã xử lý hoặc tính phí chưa, ghi trạng thái chưa chắc chắn; kiểm tra theo khả năng API trước khi gửi lại. Việc tránh ghi dữ liệu trùng không tự bảo đảm nhà cung cấp không tính phí cho nhiều lần gửi.

### 12.3. Kiểm soát ngân sách

Giới hạn bao gồm cả yêu cầu đang chạy, không chỉ chi phí đã hoàn tất. Trước khi gửi, chương trình kiểm tra ngân sách còn lại và phần dự kiến dành cho yêu cầu mới; giới hạn đầu vào, đầu ra và số lần thử lại.

Chi phí toàn bộ được ước lượng từ mức sử dụng đo trên thí điểm và giá thực tế của dịch vụ đã chọn. Lưu thời điểm áp dụng bảng giá và căn cứ tính. Không tự bịa giá, hệ số tăng tốc hoặc coi mọi lần dùng lại kết quả là không phát sinh chi phí nếu chưa xác minh.

Chương trình phải dừng nhận tác vụ mới trước khi vượt trần dự kiến; lưu tiến độ và đối chiếu chi phí thực tế khi có dữ liệu. Không tự tăng trần.

### 12.4. Dùng lại kết quả đúng điều kiện

Cache (bộ nhớ kết quả đã xử lý) gắn với toàn bộ yêu cầu liên quan: nội dung, siêu dữ liệu, ngữ cảnh thực thể, nhà cung cấp, mô hình, hướng dẫn, cấu trúc đầu ra và tham số sinh.

Không dùng địa chỉ bài làm khóa duy nhất. Kết quả đã chuẩn hóa phải theo dõi thêm phiên bản mã xử lý. Không dùng kết quả demo cũ như kết quả mới.

### 12.5. Tiếp tục sau gián đoạn

Resume (tiếp tục đợt chạy) nạp lại cùng hồ sơ đầu vào và cấu hình, chỉ xử lý phần chưa hoàn tất. Ghi kết quả phải tránh trạng thái viết dở; nạp lại không tạo bản ghi trùng.

Nếu cấu hình đổi, xử lý như phiên bản mới thay vì tiếp tục âm thầm. Không tự đổi sang mô hình rẻ hơn, nhà cung cấp khác hoặc mô hình cục bộ khi hết hạn mức. Đường suy luận vận hành trong phương án này chỉ dùng Hosted API đã được duyệt.

## 13. Chính sách dữ liệu với nhà cung cấp Hosted API

Đây là phần bổ sung cần được chốt trước khi gửi dữ liệu thật. Việc được phép dùng Hosted API không tự xác định toàn bộ chính sách của một nhà cung cấp cụ thể.

### 13.1. Những thông tin phải xác minh

| Nội dung | Điều cần ghi nhận |
|---|---|
| Phạm vi dữ liệu gửi | Nội dung bài, siêu dữ liệu và ngữ cảnh nào cần cho tác vụ; loại bỏ phần không liên quan |
| Data retention — thời gian lưu dữ liệu | Nhà cung cấp lưu yêu cầu/phản hồi bao lâu, có cấu hình khác nhau theo dịch vụ/tài khoản hay không |
| Training opt-out — không dùng dữ liệu để huấn luyện | Chính sách mặc định và cấu hình thực tế của tài khoản/API; không suy đoán từ sản phẩm chat khác |
| Data residency — khu vực lưu và xử lý | Khu vực/điểm truy cập được chọn và mức bảo đảm nhà cung cấp công bố |
| Điều khoản sử dụng phù hợp | Căn cứ cho phép sử dụng nội dung nguồn theo phạm vi dự án và gửi tới dịch vụ đã chọn |
| Xác thực và phân quyền | Khóa API được cung cấp qua cơ chế bí mật phù hợp; giới hạn quyền và quyền truy cập nhật ký |
| Lưu hồ sơ trong dự án | Phạm vi yêu cầu/phản hồi cần giữ để kiểm chứng, quyền đọc và chính sách lưu phù hợp |

Agent lưu tham chiếu chính sách, ngày kiểm tra và cấu hình tài khoản liên quan. Không ghi “không lưu dữ liệu” hoặc “không dùng để huấn luyện” nếu chưa có căn cứ phù hợp với dịch vụ và tài khoản thật.

### 13.2. Quy tắc thực thi

1. Chỉ gửi phần cần cho tác vụ; không gửi khóa API, thông tin xác thực, tệp cấu hình bí mật hoặc toàn bộ kho mã.
2. Không ghi khóa hoặc header xác thực (trường thông tin xác thực trong yêu cầu mạng) vào Git, nhật ký, bộ nhớ kết quả hay hồ sơ bàn giao.
3. Lưu yêu cầu/phản hồi nghiệp vụ đủ để truy vết sau khi loại bỏ thông tin xác thực; vẫn áp quyền truy cập phù hợp cho nội dung nguồn.
4. Nếu điều kiện sử dụng nguồn và chính sách lưu phản hồi để tái lập mâu thuẫn, báo cụ thể để nhóm quyết định; không âm thầm bỏ hồ sơ tái lập hoặc gửi dữ liệu vượt quyền.
5. Nếu thiếu điều kiện gửi dữ liệu thật, agent vẫn có thể viết mã, kiểm thử giả lập và chạy thử không gọi API. Công đoạn gửi thật ở trạng thái `BLOCKED` (bị chặn) cho đến khi có căn cứ.

Chính sách trong mục này là yêu cầu cần xác minh khi chọn dịch vụ; báo cáo không khẳng định nhà cung cấp cụ thể đã đáp ứng.

## 14. Bốn mốc người dùng cần nhận báo cáo

| Mốc | Hồ sơ cần xem |
|---|---|
| Một bài chạy xuyên suốt | Nguồn, yêu cầu/phản hồi đã che thông tin xác thực, phát biểu, bằng chứng, thời gian, kiểm tra và mức sử dụng |
| Thí điểm 30–50 bài | Nhãn người kiểm, bảng lỗi, chất lượng, ngưỡng, cấu hình khóa và ước lượng chi phí toàn bộ |
| Chạy toàn bộ | Tiến độ, lỗi, hàng chờ, chi phí, kết quả kiểm tra mẫu và khả năng tiếp tục |
| Bàn giao KG | Mức bao phủ lịch sử, lát cắt, đối chiếu, mã băm, tái lập và các giới hạn còn lại |

Báo cáo tiến độ lấy số từ sổ tác vụ và hồ sơ dữ liệu, không lấy từ ước lượng bằng lời của agent. Không cần xây giao diện quản trị mới chỉ để báo cáo nếu bảng thống kê và nhật ký đã đủ.

Mỗi báo cáo nêu: mã đợt chạy; công đoạn; phiên bản mô hình/cấu hình; số đơn vị ở từng trạng thái; các cổng đạt/không đạt/chưa chạy/bị chặn; chi phí đã đo và hạn mức còn lại; việc tiếp theo; quyết định người dùng cần xử lý.

Người dùng cần có các thao tác:

- **Xem trạng thái:** chỉ đọc hồ sơ, không gọi LLM.
- **Tạm dừng:** dừng nhận tác vụ mới, lưu tiến độ và báo rõ yêu cầu đang chạy. Không giả định yêu cầu đã gửi có thể hủy hoặc không tính phí.
- **Tiếp tục:** giữ nguyên phạm vi và cấu hình phù hợp.
- **Xem hàng chờ:** trình nguồn, đề xuất và lý do cần người quyết định; lưu người kiểm, quyết định và căn cứ.
- **Bàn giao:** chỉ nghiệm thu phần đã vượt các điều kiện bắt buộc.

Hồ sơ kiểm tra mẫu phải cho xem cạnh nhau văn bản nguồn, phiên bản, quan hệ đề xuất, bằng chứng nguyên văn, các mốc thời gian, trạng thái phát biểu và quyết định. Lưu đầy đủ lỗi/chưa biết, không chỉ chọn ví dụ đẹp.

## 15. Kiểm tra chất lượng và tái lập

### 15.1. Các nhóm chất lượng cần đo

| Nhóm | Nội dung đánh giá |
|---|---|
| Lọc bài | Giữ nhầm, loại nhầm, ca chưa giải quyết |
| Thực thể | Nhận diện đúng, gộp nhầm, tách nhầm, nhất quán giữa các đợt |
| Quan hệ | Trích đúng và bỏ sót so với nhãn người kiểm |
| Bằng chứng | Đúng nguyên văn và thực sự hỗ trợ phát biểu |
| Thời gian | Đúng mốc, đúng độ chính xác, không điền ngày vô căn cứ |
| Lịch sử | Bằng chứng đủ điều kiện cho các lát cắt |
| Vận hành | Lỗi API, số lần thử lại, mức sử dụng, thời gian và chi phí |

Mỗi chỉ tiêu có mẫu số, cách chọn mẫu và nguồn nhãn. Không coi tỷ lệ trường thời gian có giá trị là thước đo chất lượng: ngày được điền đầy đủ vẫn có thể sai. Báo riêng ngày có chứng cứ, ngày suy ra theo quy tắc, khoảng mở hợp lệ, chưa biết và ngày không có căn cứ.

Ngưỡng chất lượng phụ thuộc dữ liệu được chọn từ thí điểm và khóa trước mở rộng. Các nguyên tắc không được vi phạm như dùng bằng chứng tương lai, mất nguồn gốc, ghi đè lịch sử, sai định danh/mã băm hoặc sai đối chiếu không được coi là sai số chấp nhận được chỉ để đạt tỷ lệ tổng thể.

### 15.2. Các ca kiểm tra bắt buộc

| Ca kiểm tra | Kết quả mong đợi |
|---|---|
| Đoạn bằng chứng không tồn tại | Bị chặn |
| Đoạn tồn tại nhưng không chứng minh quan hệ | Bị phát hiện trong kiểm tra ngữ nghĩa |
| Không có phát biểu hợp lệ | Vẫn có bản ghi hoàn tất và mức bao phủ |
| API lỗi | Không biến thành bài có 0 phát biểu |
| “Hôm qua” thiếu mốc tham chiếu | Giữ chưa rõ hoặc chuyển người kiểm |
| Thiếu ngày kết thúc | Cho phép khoảng mở nếu đúng quy tắc |
| Thiếu ngày bắt đầu | Không tự điền ngày tải hoặc ngày mặc định |
| Phát biểu dự kiến | Không tự chuyển thành đã xảy ra |
| Sự kiện cũ, bằng chứng mới | Không xuất hiện trong lát cắt biết thông tin quá sớm |
| Bí danh biết muộn | Không dùng để phân giải ngược lịch sử trái quy tắc |
| Thông báo có hiệu lực tương lai | Giữ trạng thái cũ trước ngày hiệu lực |
| Đính chính/rút lại | Không làm phiên bản cũ sống lại sai |
| Hai nguồn sao chép | Không tính là hai xác nhận độc lập |
| Thay trường ngữ nghĩa hoặc thời gian | Có phiên bản mới; không sửa đè lịch sử |
| Dừng và tiếp tục | Không mất tác vụ hoặc tạo dữ liệu trùng |
| Phản hồi sai cấu trúc | Bị chặn; chỉ sửa/thử lại theo chính sách có phiên bản |
| Mô hình trả về lệch cấu hình | Chặn hoặc cảnh báo theo chính sách đã khóa, không trộn âm thầm |
| Vượt hạn mức | Dừng nhận tác vụ mới theo cơ chế kiểm soát |
| Thông tin xác thực trong nhật ký | Bị phát hiện và xử lý; không nằm trong hồ sơ bàn giao |
| Thống kê toàn bộ đầu vào | Mỗi đơn vị có trạng thái, không bị bỏ im lặng |
| Parquet và Neo4j | Khớp tập dữ liệu, không chỉ tổng số |
| Thay cấu hình | Không dùng lại kết quả kiểm tra cũ không còn phù hợp |
| Dựng lại từ phản hồi đã khóa | Mã băm dữ liệu chuẩn giống nhau theo hợp đồng |

### 15.3. Hai phép kiểm tái lập khác nhau

**Frozen replay (phát lại từ kết quả đã đóng băng):** dùng nguồn, cấu hình, phản hồi LLM và quyết định đã lưu để dựng lại dữ liệu. Kiểm tra mã băm dữ liệu chuẩn có giống nhau không. Thời điểm vận hành của lần chạy lại được lưu ở nhật ký riêng, không làm thay đổi vô nghĩa nội dung khoa học được băm.

**Fresh extraction (trích xuất lại bằng lần gọi API mới):** gửi lại đầu vào và đo mức độ giống kết quả trước. Tham số sinh ít ngẫu nhiên hoặc giá trị khởi tạo cố định không bảo đảm API luôn trả kết quả giống hệt; tên mô hình có thể trỏ tới phiên bản thay đổi phía nhà cung cấp.

Hai phép kiểm báo riêng. Không ghi phát lại đạt thành gọi mới đạt. Nếu giao thức hiện tại yêu cầu từ nguồn đến KG phải giống tuyệt đối ngay cả khi gọi API mới, agent báo phần chưa đáp ứng và trình phương án để nhóm chốt. Không tự thay yêu cầu đó bằng phát lại phản hồi đã lưu.

## 16. Hồ sơ bàn giao cuối

Bộ bàn giao tối thiểu gồm:

1. Danh sách nguồn, phiên bản, mã băm và lỗi.
2. Văn bản đã trích cùng phiên bản bộ phân tích.
3. Nhóm trùng lặp và quan hệ nguồn gốc.
4. Quyết định lọc và báo cáo kiểm tra mẫu.
5. Yêu cầu/phản hồi LLM, phiên bản mô hình và mức sử dụng; không chứa thông tin xác thực.
6. Nhãn thí điểm do người kiểm xác nhận.
7. Thực thể và ánh xạ có phiên bản.
8. Phát biểu, bằng chứng, thời gian và quyết định chấp nhận.
9. Kho thông tin có phiên bản và hàng chờ chưa giải quyết.
10. Cấu hình đã khóa và báo cáo chạy toàn bộ.
11. Sự kiện KG, kiểm tra tính khả thi và ranh giới lát cắt.
12. Lát cắt Parquet, bản Neo4j và báo cáo đối chiếu.
13. Báo cáo tái lập, mã băm và hướng dẫn chạy lại.
14. Bảng trạng thái nghiệm thu cùng giới hạn chưa xử lý.
15. Hồ sơ cấu hình dịch vụ API, chính sách dữ liệu và hạn mức đã được xác nhận.

Tên tệp và giao diện lệnh cần phù hợp kho mã thực tế. Không mô tả lệnh đề xuất như lệnh đã tồn tại. Báo cáo cuối chỉ ghi đạt cho kiểm tra đã chạy với bằng chứng thật.

## 17. Quy ước giao việc cho agent

Nhiệm vụ triển khai cần chứa đầy đủ:

1. **Mục tiêu:** dựng pipeline Hosted LLM từ nguồn đến KG; điểm bàn giao cho LLM ở cuối bước 9.
2. **Phạm vi hiện tại:** chỉ thiết kế, chạy thử một bài, thí điểm hay toàn bộ.
3. **Nguồn được phép:** danh sách nguồn và dữ liệu đầu vào cụ thể.
4. **Phần phải bảo vệ:** nguồn, giao thức, quy tắc, bài kiểm tra và kết quả cũ.
5. **Quyền gọi API:** nhà cung cấp, mô hình, chính sách dữ liệu và hạn mức đã chốt.
6. **Điều kiện chuyển bước:** các cổng kiểm tra và bằng chứng cần có.
7. **Cách báo cáo:** tiến độ từ dữ liệu thực, chất lượng, lỗi, chi phí và quyết định còn thiếu.
8. **Điều kiện dừng:** vượt phạm vi, thiếu nguồn lực, vi phạm nguyên tắc hoặc cần quyết định khoa học mới.

Agent tự chủ thực hiện công việc kỹ thuật trong phạm vi đó. Khi gặp vấn đề, phải nêu đang vướng điều gì, ảnh hưởng phần nào và phương án xử lý, đồng thời tiếp tục phần độc lập nếu được phép.

Việc bàn giao hoàn tất khi dữ liệu và hồ sơ kiểm chứng đáp ứng các điều kiện đã chốt, không phải khi agent thông báo “đã chạy xong”.

## 18. Những phần phải cụ thể hóa trước khi chạy toàn bộ

Báo cáo này đầy đủ ở mức quy trình A–Z và khung kiểm soát agent. Các giá trị phụ thuộc kho mã, dịch vụ hoặc dữ liệu không được tự điền để biến nó thành cấu hình chạy thật.

| Phần cần chốt | Hồ sơ cần có trước công đoạn phụ thuộc |
|---|---|
| Dịch vụ LLM | Nhà cung cấp, mô hình/phiên bản khả dụng, ngân sách và chính sách dữ liệu đã xác minh |
| Hợp đồng dữ liệu | Trường bắt buộc, kiểu dữ liệu, nhãn hợp lệ, quy tắc định danh, ontology và quy tắc thời gian thực tế |
| Hướng dẫn cho LLM | Hướng dẫn phân loại/trích xuất, ví dụ đã kiểm chứng, cấu trúc phản hồi và phiên bản |
| Chất lượng | Nhãn người kiểm, cách chọn mẫu, cách tính chỉ tiêu, ngưỡng được chốt và kết quả thí điểm |
| Kiểm soát thực thi | Cơ chế giới hạn quyền ghi, kiểm tra phạm vi, ngân sách, dừng/tiếp tục và cổng kiểm tra đã được cài đặt, thử nghiệm |
| Tái lập | Định nghĩa nghiệm thu phát lại và gọi mới được nhóm xác nhận nếu giao thức hiện tại chưa rõ hoặc chưa đáp ứng |

Điều kiện mở chạy toàn bộ: phạm vi toàn bộ đã được cho phép; cấu hình được khóa; thí điểm và các cổng bắt buộc đạt; dữ liệu/API/ngân sách đủ điều kiện. Thiếu điều kiện nào thì chặn phần phụ thuộc và ghi rõ trạng thái, không tự vượt qua.

## 19. Đối chiếu với 19 mục của Data/KG Bản 3

Bảng này xác nhận độ bao phủ của tài liệu, không phải chứng nhận dữ liệu thực tế đã đạt.

| Mục trong Bản 3 | Vị trí tương ứng trong báo cáo này |
|---|---|
| 4.1. Khóa giao thức và nguyên tắc bắt buộc | Bước 1; mục 3 và 11 |
| 4.2. Danh mục nguồn và phạm vi | Bước 2–4 |
| 4.3. Tìm địa chỉ và phục hồi lịch sử | Bước 5–6 |
| 4.4. Nguồn bất biến và thời gian nguồn | Bước 7; bước 16 |
| 4.5. Khử trùng và quan hệ nguồn gốc | Bước 8–9 |
| 4.6. Lọc bài độc lập với kết quả phía sau | Bước 4 và 10 |
| 4.7. Thí điểm, ontology và định danh thông tin | Bước 11–12; bước 18 |
| 4.8. Nhận diện và ánh xạ thực thể có phiên bản | Bước 13 |
| 4.9. Trích phát biểu và bằng chứng | Bước 14–15 |
| 4.10. Chuẩn hóa thời gian | Bước 16 |
| 4.11. Xét chấp nhận theo thông tin đã biết | Bước 17 |
| 4.12. Kho phiên bản chỉ bổ sung | Bước 18 |
| 4.13. Cổng chất lượng trước mở rộng | Bước 11–12; mục 11.4 và 15 |
| 4.14. Khóa và xử lý lại toàn bộ tập bài | Mục 4; bước 12; mục 12 và 18 |
| 4.15. Sự kiện KG và tính khả thi | Bước 19.1–19.2 |
| 4.16. Khóa ranh giới theo phân vị sự kiện | Bước 19.3 |
| 4.17. Dựng lát cắt theo hai trục thời gian | Bước 19.4 |
| 4.18. Parquet và đối chiếu Neo4j | Bước 19.5 |
| 4.19. Nghiệm thu và bàn giao | Bước 19.6; mục 15–18 |

Trong lần triển khai cụ thể, mọi trạng thái đạt/không đạt phải được thay bằng bằng chứng thực thi của chính đợt chạy đó; tài liệu thiết kế không thay thế kết quả kiểm chứng.
