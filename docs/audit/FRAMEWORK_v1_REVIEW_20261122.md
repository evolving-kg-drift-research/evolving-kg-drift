# Review phương pháp: khung chuẩn bộ dữ liệu KG tiến hóa, bản v1.0-draft

| | |
|---|---|
| Đối tượng | [docs/EVOLVING_KG_DATASET_AND_DRIFT_FRAMEWORK_v1.md](../EVOLVING_KG_DATASET_AND_DRIFT_FRAMEWORK_v1.md), bản v1.0-draft |
| Ngày | 2026-11-22 |
| Người review | Claude, **cùng tác giả** với bản nháp. Vì vậy review này **không độc lập hoàn toàn** (xem RV-27) |
| Cách làm | Đọc lại toàn văn qua 5 lăng kính khác với lúc viết. Đối chiếu từng thẻ [ĐK] với file gốc: `configs/protocol_v1.yaml`, `configs/s5_drift_v33.yaml`, `configs/n1_h1_deg3_v33.yaml`, `configs/x1_reextraction_pilot_v34.yaml`, `config/ontology.yaml`, `decisions/decision_log.jsonl` (23 mục) và `AGENTS.md` |
| Kết quả | **28 phát hiện**: 5 cao, 11 trung bình, 11 thấp, 1 quản trị. **26 đã sửa** trong v1.1-draft, **2 còn mở** và cần người dùng quyết định |
| Giới hạn | Không chạy mô phỏng hay dữ liệu nào: Python trong `.venv` đang bị Windows Application Control chặn. Các ngưỡng [ĐX] chưa được kiểm bằng số liệu |

## 1. Năm lăng kính

| Lăng kính | Câu hỏi đặt ra |
|---|---|
| A. Hội đồng phản biện khoa học | Khung có đo đúng cái cần đo không? Có lập luận vòng tròn, biến gây nhiễu, kết luận quá mức không? |
| B. Nhà thống kê | Mục tiêu về sức mạnh thống kê có ý nghĩa không? Cách suy luận có hợp lệ với thiết kế không? |
| C. Kỹ sư vận hành | Với máy, thời gian và nhân lực hiện có thì làm được không? Thứ tự các bước có chạy được không? |
| D. Kiểm tra tuân thủ | Có khớp protocol, các config đã đăng ký, decision log và AGENTS.md không? Mỗi thẻ [ĐK] có đúng nguồn không? |
| E. Luật sư của quỷ | Nếu khung này sai từ gốc thì sai ở đâu? Có cách rẻ hơn đạt cùng mục tiêu không? |

## 2. Bảng phát hiện

Mức: **CAO** · **TB** (trung bình) · **THẤP** · **QT** (quản trị). Cột "Vị trí" trỏ tới bản v1.0.

| ID | Mức | Lăng kính | Vị trí | Vấn đề | Cách sửa | Trạng thái |
|---|---|---|---|---|---|---|
| RV-01 | CAO | B | G12, chỉ số A1 | A1 "bậc trung bình của quần thể phân tích" **tự thỏa mãn**: quần thể đã được lọc theo bậc ≥ k\* nên bậc trung bình luôn ≥ k\* | A1 thành bậc trung bình **toàn đồ thị** (chỉ báo cáo, có mốc tài liệu). Thêm A1b: **kích thước quần thể lõi** mỗi transition ≥ N_core [MP] làm cổng | Đã sửa v1.1 |
| RV-02 | CAO | B | G0 bước 3 | SESOI tính "theo mỗi đơn vị SED⁺" phụ thuộc phân phối của biến phơi nhiễu. Ở N1, độ lệch chuẩn của D chỉ 0,03–0,11, nên β = 0,05 trên mỗi đơn vị chỉ tương đương ~0,005 RR trên mỗi độ lệch chuẩn. Mục tiêu MDE vì vậy không so được giữa các bộ dữ liệu | Định nghĩa SESOI trên **thang chuẩn hóa**: chênh RR giữa phân vị 75 và 25 của D, hoặc theo mỗi độ lệch chuẩn của D. Báo cáo cả hai thang | Đã sửa v1.1 |
| RV-03 | CAO | A | G16 (lúc soạn) | Đối chứng "trộn thời gian" của Dubossarsky **không phải đối chứng âm** với KG tích lũy: trộn dấu thời gian thì đồ thị vẫn lớn lên giữa các snapshot, nên vẫn có thay đổi thật | Bỏ đối chứng này; giữ NC1 và NC2; ghi chú lý do | Đã xử lý ngay khi soạn v1.0 |
| RV-04 | CAO | C | Mục 2; G1–G3; G6 | **Thứ tự vòng tròn.** G1 (p_attach, sản lượng), G2 (fact ngoài ontology) và G3 (fact/bài) cần số liệu từ G6, nhưng G6 đứng sau G5. Ngoài ra, nếu đổi ontology sau khi gán gold thì gold không đo được quan hệ mới | Tách G6 thành **G6a** (pilot trên kho bài đã có, theo X1, chạy trước khi chốt G2/G3) và **G6b** (gold mới nếu ontology hoặc nguồn đổi, chạy trước G7). Cập nhật luồng | Đã sửa v1.1 |
| RV-05 | CAO | C | G13–G16; Phụ lục E | **Khối lượng huấn luyện lại quá lớn.** Mỗi kịch bản × cường độ × transition × 3 seed × 3 mức E là một lần huấn luyện lại. Ví dụ PC1 và PC2 mỗi cái 3 cường độ, ở 9 transition: 9 × 6 × 3 × 3 = 486 lần, chưa kể 90 lần huấn luyện gốc. Bộ huấn luyện hiện tại là Python thuần chạy CPU, nên ước lượng "1–2 tuần" ở Phụ lục E không thực tế | Thêm Phụ lục H: công thức ngân sách tính toán, **gói tối thiểu** (chỉ các mục BB), gộp nhiều kịch bản vào tập đích rời nhau trong cùng một lần huấn luyện lại (ghi rủi ro nhiễu chéo), và bắt buộc kiểm tương đương cho bộ huấn luyện nhanh trước G1 | Đã sửa v1.1 |
| RV-06 | TB | B, D | G18 bước 5 | Đưa biến "độ bất ổn nền" vào **mô hình chính**. N1 cố ý để mô hình chính không có biến kiểm soát vì wild bootstrap hạn chế chỉ hợp lệ khi đó (`model_primary` trong `n1_h1_deg3_v33.yaml`). Protocol xếp biến kiểm soát vào phân tích độ vững (`one_pre_specified_covariance`) | Chuyển thành **mô hình phụ đăng ký trước**, chiếu Frisch–Waugh như `model_control` của N1, gắn với `one_pre_specified_covariance` | Đã sửa v1.1 |
| RV-07 | TB | D | G18 bước 4 | Thiếu hai phân tích độ vững mà protocol đã liệt kê: `delta_RR_stable_subset` và `mean_max_query_drift` | Liệt kê đủ toàn bộ `statistics.sensitivity` của protocol | Đã sửa v1.1 |
| RV-08 | TB | D | Mục 2 | Chưa nêu chế độ thực thi khoa học (AGENTS §8.2): mỗi lần một giai đoạn, có báo cáo giai đoạn rồi DỪNG, không tự sang bước sau; thao tác rủi ro cao (thu thập, xử lý lại toàn kho) cần người dùng duyệt rõ | Thêm mục 2.2 | Đã sửa v1.1 |
| RV-09 | TB | D | G0 bước 4; G8; G9; G17 bước 4 | **Thẻ [ĐK] sai nguồn.** (i) "decision D3" và "decision D5" chỉ là mục trong bảng của kế hoạch, không có trong decision log; ngữ nghĩa tích lũy được thể hiện một phần ở `s1_tie_safe_boundaries_and_valid_from_20261118`, còn panel cohort được đăng ký trong N1 (`panel_unit`). (ii) G8 ghi "loại ≤ 5% [ĐX; v3.3 đang 7,1%]", nhưng thực tế đã đăng ký **mỗi nguyên nhân ≤ 5%**, tổng 7,1% chỉ công bố, không chặn (`s2_quarantine_thresholds_per_cause_20261118`). (iii) G9 chưa trích `s1_evidence_time_basis_20261118` | Sửa từng thẻ theo nguồn đúng | Đã sửa v1.1 |
| RV-10 | TB | A | G1 bước 1; G12 A2 | "p_attach ≈ 0,42" và "58% đầu cạnh mới là thực thể mới" thực ra là **cận**, không phải giá trị điểm. Một thực thể mới có thể xuất hiện ở nhiều cạnh mới, nên p_attach ≤ 0,42 và tỷ lệ thực thể mới ≥ 58% | Ghi rõ "tối đa" và "ít nhất" | Đã sửa v1.1 |
| RV-11 | TB | A | G16 PC1 | Chưa nói cách chọn đầu kia của cạnh bơm thêm. Chọn đều ngẫu nhiên không giống tăng trưởng thật, vốn dồn vào hub và có cơ cấu quan hệ riêng | Lấy đầu cạnh và quan hệ theo **phân phối thực nghiệm của fact mới thật** trong transition đó (chỉ dùng cấu trúc, mù kết quả). Báo thêm kết quả khi chọn đều | Đã sửa v1.1 |
| RV-12 | TB | B | G1 bước 4 | "β biết trước" chưa nói cách cài. Có nguy cơ ai đó dùng phương sai RR của v4 để tính sức mạnh, tức dùng kết quả để thiết kế (INV-06) | Chỉ cài hiệu ứng trên **kết quả tổng hợp**: RR_sim lấy từ mô hình trên đồ thị tổng hợp, cộng β·D_sim. Cấm dùng RR của dữ liệu thật | Đã sửa v1.1 |
| RV-13 | TB | A | G7, G8 (cổng ra) | **Cổng tự thỏa mãn.** "0 thực thể chung chung" luôn đúng sau khi đã chặn; "0 vi phạm kiểu" luôn đúng sau khi đã lọc | Đo bằng kiểm toán: tỷ lệ thực thể chung chung trong 100 thực thể lấy ngẫu nhiên ≤ 1% [ĐX]; tỷ lệ claim vi phạm kiểu **trước khi lọc** được báo cáo và ≤ 5% [ĐX] | Đã sửa v1.1 |
| RV-14 | TB | C | G11 | Thiếu đánh đổi giữa K và M: tổng số sự kiện cố định, chia càng nhiều mốc thì mỗi transition càng ít thay đổi | Thêm đánh đổi vào G11; đưa cả K và M vào lưới mô phỏng G1 | Đã sửa v1.1 |
| RV-15 | TB | E | Mục 2 | Thiếu **cổng đầu tư**: chưa có điểm quyết định có nên dựng v4 hay không, trước khi bỏ công sức vào G7–G10 | Thêm cổng đầu tư sau G1 và G6a: nếu nhánh A không thể vào vùng khả thi ngay cả khi trích xuất lại đầy đủ, thì chỉ làm nhánh C | Đã sửa v1.1 |
| RV-16 | TB | B | G15 (SED⁺) | SED⁺ chỉ lấy phần dương nên **phần lớn quan sát bằng 0**. Biến phơi nhiễu D vì thế có phương sai rất nhỏ (N1: độ lệch chuẩn 0,03–0,11), làm mất sức mạnh thống kê. Đây là lựa chọn của protocol (`standardization: positive_part_median_MAD`) | Ghi rõ rủi ro trong G15. Phương án: dùng excess chuẩn hóa có dấu làm biến phơi nhiễu chính hoặc phụ. Việc này cần [AM] | **Còn mở**: cần người dùng quyết |
| RV-17 | THẤP | A | G15 lưu ý; Phụ lục C | Ngưỡng tần suất của embedding từ (500 lần xuất hiện) không chuyển được sang bậc KG về mặt số học | Ghi rõ đó chỉ là phép so sánh định tính | Đã sửa v1.1 |
| RV-18 | THẤP | — | Mục 2 so với G12 | Bảng mục 2 ghi "A1–A8 đạt", nhưng G12 ghi A2 và A6 chỉ cần báo cáo | Sửa cho thống nhất | Đã sửa v1.1 |
| RV-19 | THẤP | A | Tóm tắt, điểm 1 | Ghi "NELL165 quá thưa" là nói quá. NELL165 vừa thưa vừa nhiễu (precision 0,35) | Sửa thành "thưa và nhiễu" | Đã sửa v1.1 |
| RV-20 | THẤP | A | G16 mục 5 | Cụm "như N1 đã làm" có thể bị hiểu là N1 đăng ký mù. Thực tế N1 đăng ký **sau** khi đã thấy kết quả S6 theo nhóm bậc, và đã công bố điều đó | Viết lại cho chính xác | Đã sửa v1.1 |
| RV-21 | THẤP | C | G8 | Thiếu các vấn đề thực thể đặc thù tiếng Việt: tên có/không dấu, tên tiếng Việt/tiếng Anh của cùng tổ chức, viết tắt trong ngoặc | Bổ sung vào phần sự cố của G8 | Đã sửa v1.1 |
| RV-22 | THẤP | A | G12 A7 | Ngưỡng thành phần liên thông lớn nhất thiếu lý do | Thêm lý do: các đảo nhỏ ít ràng buộc với nhau, căn chỉnh toàn cục dễ đặt sai, sinh drift giả; và câu hỏi đa bước cần liên thông | Đã sửa v1.1 |
| RV-23 | THẤP | D | Phụ lục G | Tên bài và tác giả của Mohamed 2020, venue của Ali 2021 lấy từ trí nhớ, chưa kiểm | Đánh dấu "cần kiểm" | Đã sửa v1.1 |
| RV-24 | THẤP | D | G10 | Thiếu lệnh kiểm theo AGENTS §11: `python scripts/verify_g1.py --ci --code-checks` | Thêm vào cổng ra | Đã sửa v1.1 |
| RV-25 | THẤP | — | Toàn văn | Có nhiều hệ mã (G, F, L, R, A, NC, PC, DC, RV), chưa có bảng giải thích | Thêm bảng mã ở mục 0 | Đã sửa v1.1 |
| RV-26 | THẤP | D | G16 NC1; Phụ lục B | Khi [ĐX] chặt hơn [ĐK] (NC1: ≤ 0,05 so với ≤ 0,10), chưa nói giá trị nào có hiệu lực | Thêm luật ở mục 0: [ĐK] có hiệu lực cho tới khi được thay | Đã sửa v1.1 |
| RV-27 | QT | — | Cả review | Review do chính tác giả bản nháp làm, nên không độc lập | Đề nghị một người review độc lập (người hướng dẫn hoặc thành viên nhóm) trước khi duyệt. Nếu người dùng yêu cầu, có thể dùng thêm một agent khác review | **Còn mở** |
| RV-28 | THẤP | A | G19 | Datasheet thiếu thông tin cá nhân (thực thể Person) và giấy phép nội dung | Bổ sung | Đã sửa v1.1 |

## 3. Chi tiết các phát hiện mức CAO (theo khuôn AGENTS.md §6.1)

### RV-01: Chỉ số A1 tự thỏa mãn
- **Bất biến kỳ vọng:** một cổng phải có khả năng trượt khi dữ liệu không đạt.
- **Thực tế:** A1 tính trên quần thể đã lọc theo bậc ≥ k\*, nên luôn ≥ k\*. Một bộ dữ liệu chỉ có 20 thực thể đủ bậc vẫn qua cổng.
- **Bằng chứng:** định nghĩa "quần thể lõi" ngay trên bảng G12, đối chiếu với cột A1 của chính bảng đó.
- **Nguyên nhân:** xác nhận (lỗi định nghĩa).
- **Sửa:** A1 thành chỉ số báo cáo cho toàn đồ thị. Cổng mới A1b: kích thước quần thể lõi mỗi transition ≥ N_core [MP].
- **Kiểm lại:** cổng mới trượt được khi quần thể lõi nhỏ.

### RV-02: SESOI phụ thuộc thang đo
- **Bất biến kỳ vọng:** mục tiêu MDE phải so sánh được giữa các bộ dữ liệu và các mức E.
- **Thực tế:** β "trên mỗi đơn vị SED⁺" thay đổi ý nghĩa theo phân phối của D. Ở N1, độ lệch chuẩn của D là 0,03–0,11.
- **Bằng chứng:** `docs/RESEARCH_REEXECUTION_PLAN_20261117.md` §10.3.
- **Nguyên nhân:** xác nhận.
- **Sửa:** dùng SESOI chuẩn hóa (chênh RR giữa P75 và P25 của D, hoặc theo mỗi độ lệch chuẩn của D), giữ thang gốc để đối chiếu.

### RV-03: Đối chứng trộn thời gian không dùng được cho KG tích lũy
- **Bất biến kỳ vọng:** đối chứng âm không chứa thay đổi thật.
- **Thực tế:** với snapshot tích lũy, trộn dấu thời gian sự kiện thì vẫn tạo một chuỗi đồ thị lớn dần, nên thực thể vẫn được thêm cạnh.
- **Nguyên nhân:** xác nhận bằng lập luận. Kho văn bản trộn của Dubossarsky không có tăng trưởng tích lũy, KG thì có.
- **Sửa:** đã bỏ khỏi G16 ngay khi soạn v1.0 và ghi chú lý do.

### RV-04: Thứ tự giai đoạn vòng tròn
- **Bất biến kỳ vọng:** mỗi giai đoạn chỉ dùng đầu ra của các giai đoạn đứng trước.
- **Thực tế:** G1, G2, G3 cần fact/bài, p_attach và số fact ngoài ontology, nhưng các số này chỉ có từ G6.
- **Nguyên nhân:** xác nhận (lỗi sắp xếp).
- **Sửa:** G6a là pilot trên kho bài đã có, dùng chính X1, chạy sớm. G6b là gold mới khi ontology hoặc nguồn thay đổi. Cập nhật luồng ở mục 2.
- **Còn lại:** G6a phụ thuộc O3 (người gán) và API key.

### RV-05: Ngân sách tính toán
- **Bất biến kỳ vọng:** kế hoạch phải chạy được với tài nguyên hiện có.
- **Thực tế:** chỉ riêng các mục BB đã cần khoảng 576 lần huấn luyện (90 lần gốc và 486 lần cho đối chứng dương, tính trên 10 snapshot và 9 transition). Bộ huấn luyện là Python thuần chạy CPU.
- **Nguyên nhân:** xác nhận số lần huấn luyện bằng phép đếm. Thời gian cho mỗi lần huấn luyện trên dữ liệu v4 **chưa đo**, đây mới là giả thuyết.
- **Sửa:** thêm Phụ lục H (công thức, gói tối thiểu, gộp kịch bản, kiểm tương đương cho bộ huấn luyện nhanh).

## 4. Những điểm làm tốt, giữ nguyên
- Mọi thẻ [ĐK] về đo lường (S5, N1, X1, R1) khớp từng con số với config gốc. Ba thẻ sai nguồn (RV-09) đều thuộc phần quản trị.
- Có cổng cấu trúc đồ thị (G12) chỉ dùng cấu trúc, nên dừng sớm được mà không vi phạm INV-06.
- Bắt buộc đối chứng dương "thêm cạnh" (PC1). Đây là điểm sửa đúng nhất cho rủi ro R25.
- Có quy tắc rẽ nhánh đăng ký trước cho mọi cổng.
- Sổ rủi ro lấy từ lỗi đã thật sự gặp, không phải liệt kê chung chung.

## 5. Kết luận review
Sau các sửa đổi, bản v1.1-draft dùng được làm **bản nháp đăng ký**. Trước khi duyệt cần:
1. Người dùng quyết RV-16 (biến phơi nhiễu có dấu, cần amendment) và các ngưỡng [ĐX].
2. Một người review độc lập (RV-27).
3. Chạy G1 (mô phỏng) để thay các giá trị [MP]. Chưa có G1 thì không mục nào trong G11–G16 có số cụ thể.

## 6. Bổ sung trước khi đưa lên kho công khai (cùng ngày)

Khi đối chiếu lại các trích dẫn tài liệu với những trang PDF vừa đọc, có 4 điều chỉnh. Chúng không tính vào 28 phát hiện ở trên, và đã sửa trong cùng bản v1.1-draft.

| ID | Vấn đề | Cách sửa |
|---|---|---|
| BS-1 | Khung diễn giải Pujara 2017 là "mật độ trên mỗi thực thể quan trọng hơn số loại quan hệ". Bài kết luận về **mật độ triple trên mỗi quan hệ** (thí nghiệm `stable` so với `sparse`) và không tách riêng mật độ theo thực thể | Viết lại đúng với bài, và nêu rằng T10 của v3.3 có trung bình khoảng 110 triple mỗi quan hệ, thấp hơn mốc 220 mà bài gọi là "tương đối cao". Chỉ số A8 (G12) theo dõi mật độ theo quan hệ |
| BS-2 | Khung viết Shoemark 2019 "chỉ xét từ ≥ 500 lần mỗi khoảng", gộp hai điều kiện khác nhau | Tách thành tần suất tối thiểu khi huấn luyện (500 mỗi khoảng) và điều kiện chọn ứng viên (≥ 500 lần ở ít nhất 75% số khoảng) |
| BS-3 | Phụ lục G ghi "đọc toàn văn" bốn bài, nhưng thực tế chỉ đọc 2–4 trang mỗi bài | Ghi rõ từng bài đã đọc trang nào, và phần còn lại chỉ là tóm tắt hoặc nguồn thứ cấp |
| BS-4 | Số triple của ICEWS14 (~90.700) lấy từ trí nhớ, không có trong kết quả tìm kiếm của phiên | Đánh dấu "từ trí nhớ, chưa kiểm"; bậc trung bình ~25 ghi là suy ra từ số đó |
