# Báo cáo tổng hợp đánh giá embedding TransE-L2

Cập nhật ngày 04/11/2026. Báo cáo theo dõi chất lượng dự đoán liên kết của embedding, từ hàm mất mát khi huấn luyện đến phép đối chứng hồi cứu. Mục tiêu nghiên cứu chính về độ trôi biểu diễn và hỏi đáp nhiều bước có các bước đánh giá riêng.

## 1. Nhật ký các bước và bằng chứng

| Bước | Thực hiện | Kết quả và nơi tra cứu |
|---|---|---|
| Rà soát huấn luyện trước đây | Kiểm tra backbone TransE-L2 d64 trên 10 snapshot T01–T10 với ba seed 13, 37, 101. Mỗi tổ hợp snapshot và seed là một lần huấn luyện, tổng cộng 30 lần | Loss train giảm trong quá trình tối ưu. Các run toàn snapshot dùng tỷ lệ validation bằng 0. [Rà soát trước khi chạy lại](PRE_RERUN_CODEBASE_REVIEW_20261103.md) |
| Chuẩn bị quy trình lưu validation | Giữ lại đúng phân hoạch T01 cũ gồm 101 triple train và 20 triple validation. Chốt ngân sách 50 epoch và pool negative validation cố định cho pilot Dev | [Thiết kế pilot](KGE_VALIDATION_CANDIDATE_T01_20261103.md) và [kiểm thử công cụ](KGE_VALIDATION_RUNNER_20261103.md) |
| Chạy và kiểm chứng pilot T01 | Huấn luyện TransE-L2 d64 mới ở ba seed. Lưu checkpoint, loss và thứ hạng validation từng epoch | 150 checkpoint và 6.000 dòng xếp hạng. Trung bình epoch 1→50, train loss 1,0034→0,4087, validation loss 0,9835→0,8680 và validation MRR 0,0300→0,1229. Cuối run, Hits@1 bằng 0% và Hits@10 trung bình 32,5%. Tập validation này từng dùng để chọn số chiều. [Báo cáo pilot](KGE_VALIDATION_PILOT_T01_20261103.md) |
| Rà soát nguồn test độc lập | Đối chiếu nguồn canonical data3.1 với các run lịch sử và kiểm tra phạm vi ID đã thấy ở T01 | Chưa xác lập được nguồn test độc lập trong gói rà soát. Có 1.084 triple xuất hiện lần đầu sau T01, trong đó 26 triple có đủ ID thuộc train T01. [Báo cáo khả thi](KGE_INDEPENDENT_TEST_FEASIBILITY_20261104.md) |
| Chuẩn bị đối chứng hồi cứu | Lưu danh sách bộ ba, truy vấn, ứng viên, bộ lọc, trạng thái mô hình đã lưu và quy tắc đối chứng trước khi tính điểm | Gói thiết kế `outputs/kge_retrospective_t01_candidate/20261104_t01_v2/` đã kiểm chứng kỹ thuật |
| Chấm và kiểm chứng đối chứng hồi cứu | Chấm đủ 52 truy vấn bằng đối chứng tần suất và ba bản TransE-L2 ở vòng 50 | Cả ba lần khởi tạo có MRR và Hits@10 thấp hơn đối chứng. Hits@1 bằng 0% ở cả bốn phương pháp. Xem mục 4 |

## 2. Thiết kế đối chứng hồi cứu ngày 04/11

- **Mẫu.** Từ các snapshot canonical theo thứ tự cutoff, lấy lần xuất hiện đầu tiên của mỗi triple sau T01. Giữ triple nếu head, relation và tail đều có mặt trong đúng 101 triple train của pilot. Tất cả 26 triple đủ điều kiện được giữ lại, kể cả hai triple có khóa truy vấn trùng với validation trước đây. Ghi cờ overlap theo phía head và tail. Mỗi triple tạo một truy vấn head và một truy vấn tail tại snapshot xuất hiện lần đầu, tổng cộng 52 truy vấn.
- **Checkpoint.** Dùng TransE-L2 d64 tại epoch 50 của cả ba seed 13, 37 và 101 trong run `20261103_t01_three_seed_v1`. Điểm cao hơn tương ứng với khoảng cách L2 nhỏ hơn, tức `-||h + r - t||₂`.
- **Baseline.** Điểm của mỗi ứng viên bằng số lần ID đó xuất hiện ở đầu hoặc cuối của đúng 101 triple train, theo quy tắc trong `scripts/evaluate_legacy_t01.py`. Phương pháp dùng chung một bộ điểm cho cả ba lần so sánh.
- **Ứng viên và lọc.** Hai phương pháp bắt đầu từ cùng 167 thực thể trong train T01, không giới hạn theo kiểu thực thể. Với mỗi truy vấn, loại các ứng viên khác đáp án mục tiêu nếu triple sau thay thế có trong snapshot của truy vấn. Luôn giữ đáp án mục tiêu. Các snapshot sau cutoff của truy vấn nằm ngoài phạm vi lọc. Đề xuất lọc này được ghi vào thiết kế Dev để xem xét trước khi chấm.
- **Hạng và tổng hợp.** Khi điểm bằng nhau chính xác, dùng hạng trung bình. MRR lấy trung bình nghịch đảo hạng trên 52 truy vấn. Hits@1 và Hits@10 lần lượt là tỷ lệ truy vấn có hạng trung bình không vượt quá 1 và 10. Báo cáo chỉ số của baseline và của từng seed, chênh lệch từng seed trên cùng 52 truy vấn, rồi trung bình số học của ba chênh lệch. Đây là so sánh mô tả trên một mẫu cố định, với ba lần huấn luyện dùng cùng mẫu truy vấn.

| Snapshot xuất hiện lần đầu | T02 | T03 | T04 | T05 | T06 | T07 | T08 | T09 | T10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Triple đủ cả ba ID | 2 | 0 | 5 | 1 | 2 | 5 | 3 | 4 | 4 |

## 3. Kiểm chứng và tái lập

1. Kiểm tra hash và danh tính của các snapshot theo manifest bản phát hành và báo cáo khả thi. Xác nhận cả 6.638 dòng Parquet qua 10 snapshot có timestamp quan sát hợp lệ và không vượt cutoff tương ứng. Kiểm tra này dùng timestamp có sẵn trong artifact. Việc chứng nhận lịch sử quan sát và mapping thuộc các gate của pipeline.
2. Đối chiếu phân hoạch T01 và mapping với ba manifest seed. Kiểm tra hash tệp, sidecar, hash nội dung, epoch, seed và kích thước vector của ba checkpoint.
3. Tái lập danh sách bằng cách đọc trực tiếp các cột ID trong Parquet và tìm snapshot sớm nhất chứa từng triple. Tính lại bộ lọc cho từng khóa truy vấn bằng cách duyệt các triple đúng tại snapshot đó. Khớp 26 thành viên, 52 truy vấn và 52 bộ lọc với gói lưu. Có 34 lượt loại ứng viên trên toàn bộ 52 truy vấn. Đây là số lượt lọc, không phải số ứng viên phân biệt.
4. Chạy lại chế độ đọc và đối chiếu byte của bốn tệp kết quả cùng 61 hash đầu vào. Xác nhận chế độ tạo gói từ chối thư mục đã tồn tại.
5. Chạy bộ kiểm thử repository trên Python 3.11.9. Kết quả 688 đạt và 10 bỏ qua. Ruff và kiểm tra khoảng trắng của Git đạt. Thay đổi của bước này gồm công cụ `scripts/prepare_kge_retrospective_t01.py`, báo cáo này và mục tiến độ mới trong `docs/PROGRESS.md`.

| Tệp trong gói v2 | Nội dung |
|---|---|
| `design.json` | Thiết kế, tập ứng viên, ba checkpoint và cách tính chỉ số |
| `members.json` | 26 triple, snapshot, cutoff và cờ overlap |
| `queries.json` | 52 truy vấn, đáp án và danh sách ID phải lọc |
| `preflight.json` | Số đếm và kết quả kiểm tra |
| `experiment_manifest.json` | Git commit, trạng thái working tree, seed và hash của đầu vào và kết quả |

SHA-256 của thiết kế theo dạng JSON chuẩn hóa của dự án là
`c7119f3ef44e8fc4c7919137bbe47b3c5e0e71b0b68caf8d31415c1d4079467c`.

Kiểm tra lại gói từ thư mục gốc repository bằng lệnh sau.

```powershell
.venv-m1/Scripts/python.exe scripts/prepare_kge_retrospective_t01.py outputs/kge_retrospective_t01_candidate/20261104_t01_v2
```

Để tái tạo, dùng cùng lệnh với đường dẫn mới dưới `outputs/` và thêm `--write`. Gói v1 được giữ lại làm dấu vết của lần chạy đầu. Gói đó dừng khi so sánh cấu trúc Python với JSON đã đọc lại, do khóa số nguyên của histogram chuyển thành chuỗi. Gói v2 so sánh byte JSON đã tuần tự hóa và vượt qua kiểm tra đọc lại. Chỉ dùng v2 để xem xét thiết kế.

## 4. Kết quả đối chứng hồi cứu

| Phương pháp | MRR | Hits@1 | Hits@10 | Chênh lệch MRR | Chênh lệch Hits@10 |
|---|---:|---:|---:|---:|---:|
| Đối chứng tần suất | 0,1180 | 0,00% | 44,23% (23/52) | — | — |
| TransE-L2, mã khởi tạo 13 | 0,0623 | 0,00% | 15,38% (8/52) | −0,0557 | −28,85 điểm phần trăm |
| TransE-L2, mã khởi tạo 37 | 0,0817 | 0,00% | 21,15% (11/52) | −0,0363 | −23,08 điểm phần trăm |
| TransE-L2, mã khởi tạo 101 | 0,0552 | 0,00% | 21,15% (11/52) | −0,0628 | −23,08 điểm phần trăm |
| **Trung bình ba lần khởi tạo TransE-L2** | **0,0664** | **0,00%** | **19,23%** | **−0,0516** | **−25,00 điểm phần trăm** |

Chênh lệch lấy giá trị TransE-L2 trừ giá trị đối chứng trên cùng 52 truy vấn. Chênh lệch Hits@1 bằng 0 điểm phần trăm ở cả ba lần khởi tạo. MRR là trung bình nghịch đảo thứ hạng. Hits@k là tỷ lệ đáp án có thứ hạng không vượt quá k sau khi xử lý đồng hạng.

![So sánh kết quả dự đoán liên kết trên 26 bộ ba xuất hiện sau T01](../../outputs/kge_retrospective_t01_scoring/20261104_t01_v2/doi_chung_t01.png)

**Diễn giải.** Trên mẫu hồi cứu này, cả ba bản TransE-L2 ở vòng 50 xếp hạng đáp án kém hơn đối chứng tần suất theo MRR và Hits@10. Việc hàm mất mát giảm và MRR tăng trên tập xác thực T01 cho thấy cải thiện trong phạm vi pilot. Khi chuyển sang nhóm bộ ba xuất hiện sau T01, cải thiện đó chưa mang lại lợi thế so với tần suất.

Nhóm hồi cứu bao phủ 26/1.084 bộ ba xuất hiện lần đầu sau T01, khoảng 2,4%. Các bộ ba này từng có mặt trong những lần huấn luyện backbone khác và hai bộ ba chia sẻ khóa truy vấn với tập xác thực cũ. Kết luận trên áp dụng cho các trạng thái mô hình T01 đã chấm và nhóm đủ định danh đã thấy. Đánh giá độc lập vẫn cần nguồn dữ liệu giữ riêng có lịch sử sử dụng kiểm chứng được. Kết quả này cũng chưa đo độ trôi biểu diễn hoặc chất lượng hỏi đáp nhiều bước.

## 5. Nhật ký chấm và kiểm chứng

1. Tái lập thiết kế v2 trước khi chấm. Xác nhận mã SHA-256 và thử truyền mã sai. Công cụ từ chối mã sai trước khi tạo thư mục kết quả.
2. Tính điểm bằng công thức khoảng cách L2 và quy tắc tần suất trong thiết kế. Dùng cùng bộ lọc và quy tắc đồng hạng cho mọi phương pháp. Lưu toàn bộ 208 dòng thứ hạng cùng điểm từng ứng viên còn lại.
3. Tính lại 34.600 điểm ứng viên bằng phép tính mảng NumPy. Đối chiếu từng ứng viên, thứ hạng, chỉ số và chênh lệch. Đọc lại các thứ hạng đã lưu để kiểm tra thêm MRR bằng phân số và đếm đáp án trong nhóm 1 và 10 hạng đầu.
4. Giữ kết quả v1 và tạo kết quả v2 để ngắt dòng nhãn dưới trục biểu đồ. Ba tệp chứa thứ hạng, chỉ số và kiểm chứng của hai lần chạy trùng SHA-256. Bản kê v2 ràng buộc 67 tệp đầu vào và bốn tệp kết quả.

| Tệp kết quả | Nội dung |
|---|---|
| [`thu_hang.json`](../../outputs/kge_retrospective_t01_scoring/20261104_t01_v2/thu_hang.json) | Thứ hạng và điểm ứng viên theo truy vấn |
| [`chi_so.json`](../../outputs/kge_retrospective_t01_scoring/20261104_t01_v2/chi_so.json) | Chỉ số và chênh lệch từng lần khởi tạo |
| [`kiem_chung.json`](../../outputs/kge_retrospective_t01_scoring/20261104_t01_v2/kiem_chung.json) | Số dòng và số điểm đã tính lại |
| [`experiment_manifest.json`](../../outputs/kge_retrospective_t01_scoring/20261104_t01_v2/experiment_manifest.json) | Mã Git, môi trường, mã thiết kế và mã băm tệp |

Lệnh tái lập từ thư mục gốc dự án. Chọn đường dẫn kết quả mới mỗi lần. Lần chấm này dùng Python 3.12 có NumPy và Matplotlib.

```powershell
python scripts/evaluate_kge_retrospective_t01.py outputs/kge_retrospective_t01_scoring/tai_lap_01 --design-hash c7119f3ef44e8fc4c7919137bbe47b3c5e0e71b0b68caf8d31415c1d4079467c
```

## 6. Mức xác minh

- **IMPLEMENTED.** Có công cụ tạo gói và công cụ chấm đối chứng theo mã thiết kế.
- **TESTED.** Đã thử tái lập từ Parquet, đối chiếu bộ lọc, chặn ghi đè gói thiết kế và chặn mã thiết kế sai khi chấm.
- **EXECUTED / VERIFIED.** Đã chấm và tính lại kết quả trên dữ liệu thật trong phạm vi đối chứng hồi cứu phục vụ phát triển. Bước này kết thúc sau khi lưu và kiểm chứng kết quả.

Sau khi thêm công cụ chấm, bộ kiểm thử dự án có 688 kiểm thử đạt và 10 kiểm thử bỏ qua. Ruff và kiểm tra khoảng trắng của Git đạt. Các tệp thay đổi trong bước này gồm `scripts/evaluate_kge_retrospective_t01.py`, báo cáo này và mục tiến độ trong `docs/PROGRESS.md`.

## 7. Rà soát tập hồi cứu và bộ truy vấn trước khi chuyển bước

**Kết luận sử dụng.** Tập hiện tại phù hợp để so sánh hồi cứu hai cách xếp hạng trên các bộ ba có định danh đã thấy ở T01. Phạm vi kiểm thử độc lập vẫn chưa đạt điều kiện về lịch sử giữ riêng, độ bao phủ và đơn vị tổng hợp. Bộ truy vấn đang xét là dự đoán liên kết một bước, gồm dự đoán thực thể đầu hoặc cuối của một bộ ba. Đánh giá hỏi đáp nhiều bước cần bộ truy vấn và kiểm tra riêng theo giao thức đề tài.

### 7.1 Tính toàn vẹn và độ bao phủ

| Nội dung | Kết quả rà soát |
|---|---|
| Thành viên và mốc quan sát | Cả 26 bộ ba nằm ngoài 101 bộ ba huấn luyện và 20 bộ ba xác thực của pilot T01. Tất cả xuất hiện lần đầu trong chuỗi ở đúng snapshot đã ghi. Mốc quan sát ghi trong Parquet của 26 bộ ba đều sau cutoff T01 và không vượt cutoff tương ứng. Phép kiểm này dựa vào các mốc đã ghi trong dữ liệu |
| Độ bao phủ | 26/1.084 bộ ba đủ định danh, tương đương 2,4%. Trong 1.058 bộ ba còn lại, 282 có một đầu thực thể ngoài tập huấn luyện và 776 có cả hai đầu ngoài tập huấn luyện. Cả 10 loại quan hệ đều đã có trong tập huấn luyện |
| Mất cân đối theo quan hệ | Mẫu chỉ có 7/10 loại quan hệ. Quan hệ hợp tác (`partners_with`) và phát hành (`released_by`) chiếm 16/26 bộ ba (61,5%), so với 423/1.084 (39,0%) trong nhóm xuất hiện lần đầu sau T01 |
| Mất cân đối theo đáp án | 52 dòng có 31 thực thể đáp án phân biệt. Hai thực thể xuất hiện thường xuyên nhất cộng lại là 12/52 dòng |
| Đáp án và lọc | Mỗi bộ ba có đúng một dòng dự đoán đầu và một dòng dự đoán cuối. 52/52 đáp án và bộ lọc khớp Parquet tại snapshot truy vấn. Có 22 dòng áp dụng lọc, tổng cộng 34 lượt loại. Còn 163–167 ứng viên mỗi dòng. Danh sách ứng viên đã chấm khớp giữa cả bốn phương pháp |

### 7.2 Khóa truy vấn và cách đọc chỉ số

Khóa truy vấn gồm phía cần dự đoán và hai định danh đã biết. Có 52 dòng phân biệt khi tính cả đáp án. Khi gom theo khóa truy vấn, còn **49 khóa kèm snapshot** hoặc **42 khóa nếu bỏ snapshot**. Ba khóa kèm snapshot có hai đáp án đúng. Quy tắc lọc hiện tại xử lý từng đáp án theo thiết kế, nên các dòng cùng khóa vẫn có thể phụ thuộc nhau. Hai phía của cùng một bộ ba cũng chia sẻ dữ liệu đầu vào.

Có **12 dòng** trùng khóa với tập huấn luyện T01 và **2 dòng** trùng khóa với tập xác thực cũ, trong đó **1 dòng** trùng cả hai. Khóa trùng nghĩa là đã gặp cùng cặp định danh ở phía được cung cấp. Đáp án đang chấm thuộc một bộ ba khác. Các số đếm này giải thích giới hạn của mẫu hiện tại và giữ nguyên tập đã chấm.

Đối chứng tần suất có 9/52 dòng mà đáp án đồng điểm cao nhất. Quy tắc hạng trung bình đẩy các đáp án đó xuống dưới hạng 1, nên Hits@1 vẫn bằng 0%. Ở 25/52 dòng, đáp án đồng điểm với ít nhất 100 ứng viên khác. Khi đọc Hits@1 của đối chứng, cần giữ rõ quy tắc đồng hạng đang áp dụng.

### 7.3 Phát hiện và điều kiện bàn giao

| Trường | KGE-TEST-001 · Cao · phạm vi và độ bao phủ | KGE-QUERY-002 · Trung bình · phụ thuộc giữa truy vấn |
|---|---|---|
| Thành phần | `outputs/kge_independent_test_feasibility/20261104_v1/audit.json` và `outputs/kge_retrospective_t01_candidate/20261104_t01_v2/members.json` | `outputs/kge_retrospective_t01_candidate/20261104_t01_v2/queries.json` và tập huấn luyện, xác thực được gói thiết kế tham chiếu |
| Yêu cầu khi dùng để xác nhận | Có nguồn giữ riêng kiểm chứng được và xác định phạm vi định danh ngoài tập huấn luyện trước khi chấm | Đăng ký trước đơn vị tổng hợp và cách xử lý nhiều đáp án, khóa trùng và phụ thuộc trong phép so sánh |
| Quan sát và bằng chứng | Chỉ 26/1.084 bộ ba đủ định danh. Rà soát trước đã xác nhận 10/10 snapshot có lịch sử huấn luyện backbone toàn snapshot | 52 dòng, 49 khóa kèm snapshot, 42 khóa khi bỏ snapshot. Có 13 dòng trùng khóa với ít nhất một trong hai tập cũ |
| Nguyên nhân đã xác nhận | Điều kiện đủ định danh và lịch sử sử dụng của bản phát hành giới hạn phạm vi hồi cứu | Thiết kế tạo hai truy vấn từ mỗi bộ ba và chấm từng đáp án riêng. Các bộ ba khác nhau có thể chia sẻ khóa |
| Tái hiện và kiểm tra | Chạy lệnh bên dưới để tính lại độ bao phủ từ Parquet và đối chiếu mã băm | Cùng lệnh kiểm tra khóa, đáp án, bộ lọc và ứng viên. Đã đếm lại số khóa và mức trùng bằng phép nhóm độc lập |
| Xử lý đề xuất và phần còn thiếu | Trước khi xác nhận hiệu quả độc lập, xác minh lịch sử giữ riêng của nguồn và đăng ký cách xử lý định danh ngoài tập huấn luyện | Trước lần chấm xác nhận, quy định cách gom nhóm theo khóa và snapshot, xử lý nhiều đáp án và báo cáo phần trùng với tập cũ |

Đã thực hiện và kiểm chứng trên dữ liệu thật (**EXECUTED / VERIFIED**) trong phạm vi rà soát. Đối chiếu 111 mã băm đầu vào và một tệp kết quả. Ruff và kiểm tra khoảng trắng Git đạt. Tệp số liệu nằm tại [kiểm toán truy vấn](../../outputs/kge_retrospective_query_audit/20261104_t01_v1/kiem_toan_truy_van.json). Lệnh tái lập dùng thư mục kết quả mới.

```powershell
.venv-m1/Scripts/python.exe scripts/audit_kge_retrospective_queries.py outputs/kge_retrospective_query_audit/tai_lap_01
```

## 8. Rà soát nguồn cho tập kiểm thử độc lập

**Kết quả.** Trong các gói cục bộ đã nhận diện, chưa xác lập được nguồn bộ ba có lịch sử giữ riêng kiểm chứng được. Số bộ ba mới từ các bảng dữ kiện và sự kiện so với T01–T10 là **0**. Số truy vấn khả dụng từ một nguồn kiểm thử độc lập vẫn **chưa xác định**, do chưa có nguồn vượt qua bước kiểm tra nguồn gốc.

### 8.1 Quy trình thực hiện

1. **Khoanh phạm vi.** Kiểm kê thư mục dữ liệu, bản kê, các gói phục hồi và kết quả đã đăng ký trong kho dự án. Đối chiếu với báo cáo rà soát khả thi trước đó và quy định truy cập W8. Phạm vi lần này là các gói cục bộ được phép đọc. Chưa thu thập dữ liệu mới, chưa mở dữ liệu khóa và chưa chạy chấm.
2. **Xác lập dữ liệu đã dùng.** Kiểm tra SHA-256 của 10 tệp Parquet chuẩn theo cả bản kê V3.1 và lần rà soát trước. Hợp các bộ ba theo đúng định danh thực thể đầu, quan hệ và thực thể cuối. Thu được **1.205 bộ ba phân biệt**. Lần rà soát trước đã đối chiếu các snapshot này với 30 lần huấn luyện backbone toàn snapshot.
3. **Tìm phần dữ liệu ngoài các snapshot.** Đọc bảng lịch sử dữ kiện và bảng sự kiện của V3.1 rồi so sánh tập bộ ba theo hai chiều với T01–T10. Bảng dữ kiện có **1.803 dòng phiên bản** và đúng **1.205 bộ ba phân biệt**. Bảng sự kiện có **1.205 dòng** và cùng tập bộ ba. Bảng dữ kiện có **0 dòng** với mốc quan sát được ghi sau cutoff T10. Cột mốc quan sát được dùng nguyên trạng, tách biệt với thời điểm thu thập và thời gian hiệu lực.
4. **Đối chiếu các gói và bản xuất khác.** So SHA-256 của bốn tệp trong gói kiểm tra dữ kiện với bốn bảng V3.1. Kiểm tra loại phát hành và SHA-256 của gói phục hồi. Kiểm tra số dòng và quy trình tạo bản xuất hỏi đáp. Kết quả theo từng gói nằm ở mục 8.2.
5. **Áp điều kiện tiếp nhận.** Chỉ đếm độ bao phủ, khóa truy vấn trùng và trường hợp nhiều đáp án đúng của tập kiểm thử xác nhận sau khi một nguồn có lịch sử giữ riêng, dữ liệu chuẩn và ánh xạ định danh kiểm chứng được. Trong lượt này chưa có gói đạt điều kiện để xây bộ truy vấn độc lập. Số liệu của bộ 52 truy vấn hồi cứu vẫn được báo cáo ở mục 7.
6. **Kiểm tra lại và lưu dấu vết.** Đọc lại Parquet theo thứ tự T10 đến T01 bằng phép đếm riêng. Xác nhận tập hợp của T01–T10 bằng đúng tập bộ ba T10, bảng dữ kiện và bảng sự kiện. Đối chiếu **36 mã băm đầu vào và một tệp kết quả**. Ruff và kiểm tra khoảng trắng Git đạt.

### 8.2 Quyết định theo nguồn

| Nguồn đã xét | Bằng chứng | Kết luận cho kiểm thử độc lập |
|---|---|---|
| V3.1, snapshot T01–T10 | 1.205 bộ ba, đã xuất hiện trong huấn luyện backbone toàn snapshot | Dùng làm tập đối chiếu lịch sử và nguồn cho kết quả hồi cứu |
| Bảng lịch sử dữ kiện và sự kiện V3.1 | Tập bộ ba bằng đúng tập T01–T10, không có bộ ba bổ sung | Không có phần bộ ba mới để lập tập riêng |
| Gói kiểm tra dữ kiện `data/transe_fact_check_package/` | Cả 4/4 tệp có SHA-256 trùng với bảng tương ứng trong V3.1 | Bản sao của dữ liệu đã xét |
| Bảng trích xuất một phần của V3.1 | 1.860 dòng, bản phát hành ghi mục đích chẩn đoán. Các cột thực thể là cụm từ trích xuất | Chưa có bộ ba chuẩn hay bản kê tập giữ riêng cho bảng này |
| Gói phục hồi `pre-gate-a-audit-v1` | Tệp nén khớp bản kê. Bản kê phân loại chỉ dùng cho kiểm toán và phục hồi dữ liệu thô, với Gate A bị chặn tại thời điểm đóng gói | Chưa có phân hoạch kiểm thử KGE chuẩn có thể đối chiếu lịch sử giữ riêng |
| Bản xuất 147 câu hỏi | Công cụ xuất dùng T01–T10 và kết quả hỏi đáp đã có để dựng câu hỏi | Phục vụ xem xét bộ câu hỏi của dự án. Cần đánh giá riêng theo giao thức hỏi đáp |
| Bốn tệp kê khai nguồn, snapshot, quan hệ và ánh xạ ở `data/manifests/` | Cả bốn đều rỗng | Chưa cung cấp bằng chứng về một nguồn giữ riêng |

### 8.3 Bàn giao

Phát hiện **KGE-TEST-001** vẫn mở. Bằng chứng bổ sung xác nhận các bảng V3.1 và gói kiểm tra dữ kiện không mở rộng tập bộ ba đã biết. Lượt rà soát đạt mức **EXECUTED / VERIFIED** cho các nguồn cục bộ đã nêu. Kết luận về lịch sử sử dụng của dữ liệu ngoài phạm vi này vẫn để ngỏ.

Để tiếp tục, cần xác định một nguồn ứng viên cụ thể có bản kê nội dung, mốc quan sát và lịch sử giữ riêng có thể kiểm chứng. Khi có nguồn đó, trước hết đối chiếu với đầu vào các lần huấn luyện, xác thực và chọn cấu hình đã biết. Sau đó mới tính độ bao phủ theo định danh, kiểm tra khóa trùng và nhiều đáp án, rồi chốt thiết kế trước khi chấm.

[Kết quả kiểm kê](../../outputs/kge_local_test_source_audit/20261104_v1/kiem_ke_nguon.json) và [bản kê kiểm chứng](../../outputs/kge_local_test_source_audit/20261104_v1/experiment_manifest.json). Lệnh tái lập dùng thư mục kết quả mới.

```powershell
.venv-m1/Scripts/python.exe scripts/audit_kge_local_test_sources.py outputs/kge_local_test_source_audit/tai_lap_01
```

## 9. Đề xuất nguồn cho kiểm thử độc lập

**Đề xuất ưu tiên VnExpress Số Hóa**, mã nguồn `vnexpress_sohoa`, cho một đợt kiểm thử dự đoán liên kết tiến cứu. Đối tượng dự kiến là các bài công khai được quan sát qua RSS Số Hóa trong một cửa sổ cố định sau khi đăng ký thiết kế. Mục tiêu là đánh giá TransE-L2 T01 đã cố định trên bằng chứng mới, với đối chứng tần suất học từ cùng tập huấn luyện T01. Đây là đề xuất nguồn để xem xét. Chất lượng mẫu, độ bao phủ và khả năng chấm xác nhận còn phụ thuộc kết quả tiếp nhận dữ liệu.

### 9.1 Các bước phân tích trước khi đề xuất

1. **Xác định thẩm quyền và ranh giới thời gian.** Đối chiếu `configs/protocol_v1.yaml`, `data/manifests/sources.lock.json`, `config/sources.yaml`, cấu hình Stage 4.3 và đặc tả thu thập. Cả ba tài liệu khóa của dự án khớp SHA-256 với bản kê và giao thức. VnExpress Số Hóa và Tuổi Trẻ Công Nghệ đều có trong danh mục nguồn. T10 kết thúc lúc **02:13:25 UTC ngày 07/09/2026**. Mốc này dùng để đối chiếu lịch sử của gói V3.1. Cửa sổ tiến cứu bắt đầu sau thời điểm đăng ký và đủ điều kiện triển khai, vì chỉ nằm sau T10 vẫn chưa đủ chứng minh dữ liệu từng được giữ riêng.
2. **So sánh phương án theo nguồn gốc, khả năng giữ riêng và tính khả thi.** Ưu tiên nguồn đã có trong danh mục, có kênh phát hiện công khai và có thể tách đợt thu thập mới khỏi dữ liệu lịch sử. Không dùng kết quả MRR, Hits@k, drift hoặc hỏi đáp để chọn nguồn hoặc thời điểm.

   | Phương án | Căn cứ và đánh đổi | Quyết định đề xuất |
   |---|---|---|
   | Tập đã được bên quản lý giữ riêng | Có thể giảm thời gian thu thập nếu có bản kê, nhật ký truy cập và định danh để đối chiếu. Rà soát cục bộ ở mục 8 chưa tìm được gói có bằng chứng này | Xem xét khi có gói cụ thể và lịch sử sử dụng kiểm chứng được |
   | VnExpress Số Hóa, thu tiến cứu qua RSS | Đã có mã nguồn và RSS trong danh mục, phù hợp phạm vi công nghệ. Giới hạn một chuyên mục giúp mô tả rõ tập đích. RSS có thể bỏ sót bài giữa hai lần kiểm tra. Khoảng cách thời gian với T01 có thể làm tăng số thực thể chưa thấy | Ưu tiên cho đề xuất hiện tại |
   | Tuổi Trẻ Công Nghệ, thu tiến cứu qua RSS | Nguồn đã có trong danh mục và có thể lập đợt tiến cứu riêng. Khối 108 lần thu lịch sử thuộc Stage 4.3 đã hoàn thành và được khóa. Phương án tiến cứu chỉ có giá trị khi có kế hoạch và dấu vết riêng cho cửa sổ mới | Phương án dự phòng. Xem xét bằng một đề xuất riêng dựa trên lý do vận hành đã ghi lại |

3. **Kiểm tra khả năng tiếp cận ở mức hồ sơ.** Đọc công khai hai tệp robots. Cả hai có nhóm quy tắc chung và khai báo sơ đồ trang. Lượt này mới đối chiếu chính sách công khai ở mức sơ bộ. Trước khi vận hành cần lưu bản quy tắc tại thời điểm thu, kiểm tra đúng định danh trình thu thập, đường dẫn RSS và bài viết, điều khoản sử dụng và khả năng lưu bằng chứng. [robots.txt VnExpress](https://vnexpress.net/robots.txt) · [robots.txt Tuổi Trẻ](https://tuoitre.vn/robots.txt)
4. **Ước lượng giới hạn của phương án.** Kết quả 26/1.084 của dữ liệu hồi cứu cho thấy việc tìm đủ bộ ba có thực thể và quan hệ đã thấy ở T01 có thể khó. Tỷ lệ này mô tả dữ liệu cũ, chưa đủ để ước lượng lượng truy vấn từ riêng RSS VnExpress. Cửa sổ tiến cứu giảm rủi ro dùng lại bằng chứng, đồng thời có thể làm mẫu đủ định danh nhỏ hơn. Vì vậy quyết định tiếp nhận dựa vào độ bao phủ và thành phần mẫu được báo cáo trước khi đọc điểm.
5. **Ghi quyết định ở mức đề xuất.** Lưu cấu hình ứng viên cùng bản kê ràng buộc 16 đầu vào và một tệp kết quả. Chưa có mốc thu cụ thể, bản đăng ký khoa học hoặc dữ liệu bài báo thu cho đợt này.

### 9.2 Phạm vi vận hành dự kiến

- **Kênh phát hiện.** RSS đã đăng ký `https://vnexpress.net/rss/so-hoa.rss` và trang HTML công khai được mục RSS dẫn tới. Dùng phạm vi công nghệ và quy tắc phân loại đã được duyệt. Giữ nhật ký URL phát hiện, chuẩn hóa, loại trừ, lỗi và mục nghi trùng, để xác định chính xác phần dữ liệu quan sát được.
- **Cửa sổ và giới hạn dự thảo.** Bắt đầu lúc **00:00 giờ Việt Nam của thứ Hai đầu tiên sau khi đủ điều kiện và đăng ký**, kéo dài **28 ngày**, đọc RSS mỗi **6 giờ**, với trần **200 URL bài phân biệt**. Các giá trị này là giả định vận hành để giới hạn đợt thu. Chốt ngày giờ tuyệt đối và cách xử lý gián đoạn trước khi triển khai. Nếu chạm trần hoặc có lỗ hổng thu thập, ghi nhận độ bao phủ và đưa đợt thu về xem xét trước khi diễn giải mẫu. Phạm vi suy luận gắn với những bài quan sát được qua RSS trong cửa sổ, vì kênh này có thể không phản ánh toàn bộ bài đã đăng.
- **Giữ riêng và kiểm tra trùng.** Trước khi mở cửa sổ, ràng buộc ba trạng thái TransE-L2 T01 ở vòng 50, 101 bộ ba huấn luyện, danh sách định danh, cấu hình đối chứng và bản kê lịch sử đã biết. Tách quyền truy cập dữ liệu giữ riêng khỏi công việc phát triển và chọn cấu hình. Khi tiếp nhận, đối chiếu URL chuẩn, mã băm nội dung, bài đăng lại hoặc gần trùng, định danh bộ ba và khóa truy vấn với các tập đã dùng. Lưu nhật ký truy cập và lý do xử lý từng nhóm trùng.
- **Mốc thời gian và nguồn gốc.** Ghi riêng mốc bằng chứng có thể quan sát, thời gian dữ kiện có hiệu lực và thời điểm hệ thống thu được nội dung. Lưu bằng chứng cho mốc công bố hoặc quan sát, bản sửa đổi, mã băm nội dung và căn cứ ánh xạ sẵn có tại cutoff. Trường hợp mốc hoặc ánh xạ không xác minh được cần cách ly theo hợp đồng pipeline. Điều kiện thời gian áp dụng cho cả đáp án và các bộ ba dùng để lọc.

### 9.3 Điều kiện trước khi chuyển bước

| Thứ tự | Điều kiện và đầu ra |
|---|---|
| Trước thu thập | Xác nhận thẩm quyền đối với đợt thu tiến cứu và các điều kiện M1 áp dụng. Duyệt giới hạn, cửa sổ, cách xử lý thiếu dữ liệu, tiêu chí đủ mẫu và quy tắc lưu trữ. Đối chiếu robots và điều khoản theo cấu hình thực tế |
| Khi tiếp nhận dữ liệu | Xác minh lịch sử giữ riêng, bằng chứng quan sát và định danh. Tạo bản kê nội dung, ghi lý do loại trừ, đối chiếu trùng với dữ liệu cũ. Ghi số bộ ba đủ định danh, thực thể hoặc quan hệ chưa thấy, độ tập trung theo quan hệ, số khóa trùng và nhiều đáp án |
| Trước chấm điểm | Chốt phạm vi xác nhận, đơn vị tổng hợp, cách xử lý định danh chưa thấy và nhiều đáp án, tập ứng viên, bộ lọc theo cutoff và tiêu chí đủ mẫu. Nếu mẫu thiếu độ bao phủ thì ghi nhận giới hạn để xem xét, giữ nguyên trạng thái mô hình và lịch sử đợt thu. Việc sử dụng tập khóa theo W8 phụ thuộc các điều kiện của W7 và W8 |

Đợt kiểm thử đề xuất có phạm vi dự đoán liên kết của trạng thái mô hình T01 trên một nguồn và cửa sổ cụ thể. Độ bao phủ định danh, phân bố quan hệ và khoảng cách thời gian cần được báo cáo cùng kết quả. Kết luận về độ trôi và hỏi đáp nhiều bước tiếp tục theo các bước đánh giá riêng.

[Cấu hình đề xuất](../../outputs/kge_independent_source_proposal/20261104_v1/de_xuat_nguon.json) · [Bản kê đầu vào](../../outputs/kge_independent_source_proposal/20261104_v1/experiment_manifest.json)

## 10. Phân tích trước khi triển khai đợt thu tiến cứu

**Quyết định đề xuất.** Giữ VnExpress Số Hóa làm nguồn ưu tiên và xem kế hoạch 28 ngày, tối đa 200 URL là **đợt đánh giá khả thi**. Ngày 09/11/2026 là mốc dự thảo sớm nhất. Đợt thu thật cần điều kiện M1 phù hợp với phạm vi, người quản lý dữ liệu và bản đăng ký thiết kế được xác nhận trước. Việc chấm xác nhận còn cần đủ độ bao phủ, đủ nhóm bằng chứng và các điều kiện truy cập áp dụng.

### 10.1 Kiểm tra lại lý do chọn nguồn và khả năng có đủ định danh

Đọc 10 Parquet chuẩn đã đối chiếu mã băm. Với mỗi bộ ba, lấy bản ghi tại snapshot xuất hiện đầu tiên, lần theo mã nội dung đại diện qua bảng thành viên tài liệu tới bảng lượt thu, rồi lấy nhãn nguồn duy nhất được khai báo. Đếm độ bao phủ theo đúng 101 bộ ba huấn luyện của pilot T01. Đối chiếu lại số bộ ba theo nguồn bằng cách nối theo mã băm nội dung thô và duyệt ngược T10 về T01.

| Nguồn của bằng chứng đại diện trong V3.1 | Bộ ba ở T01 | Bộ ba xuất hiện lần đầu sau T01 | Có đủ hai thực thể và quan hệ trong tập huấn luyện T01 |
|---|---:|---:|---:|
| VnExpress Số Hóa | 121 | 1.038 | 26 (2,50%) |
| Tuổi Trẻ Công Nghệ | 0 | 46 | 0 (0%) |

Trong 26 bộ ba đủ định danh có 25 bản nội dung đại diện phân biệt. Một bản nội dung có thể hỗ trợ nhiều bộ ba. Nhiều bản nội dung cũng có thể cùng nhóm bài đăng lại, cùng sự kiện hoặc cùng khóa truy vấn. Do đó 52 dòng chấm từ 26 bộ ba chỉ cho biết số lần xếp hạng. Mức độ độc lập cần kiểm tra theo nhóm bằng chứng.

Kết quả lịch sử củng cố lựa chọn VnExpress cho mô hình T01 đã cố định. Phép nối chỉ phản ánh nhãn nguồn của bằng chứng đại diện trong V3.1 và chưa chứng nhận độc lập toàn bộ nguồn gốc lịch sử. Số liệu 2,50% cũng chưa dự báo lượng truy vấn từ RSS mới. Mẫu lịch sử có cách tuyển và khung thời gian khác. Mốc mở dự thảo cách cutoff T01 hơn 17 tháng, nên tỷ lệ thực thể mới là yếu tố cần đo riêng.

### 10.2 Tách ngày thu, thời điểm quan sát và cutoff chấm

1. **Cửa sổ dự thảo.** Từ 00:00 ngày 09/11/2026 đến trước 00:00 ngày 07/12/2026 theo giờ Việt Nam. Tương ứng từ 17:00 UTC ngày 08/11 đến trước 17:00 UTC ngày 06/12. Bốn lượt RSS mỗi ngày tạo 112 khung lấy mẫu dự kiến. Nếu điều kiện mở chưa đủ, đăng ký lại cả cửa sổ trước khi thu theo cùng quy tắc thứ Hai.
2. **Phạm vi quan sát.** Ghi mọi lượt RSS, kể cả khi lỗi hoặc không có mục mới. Lưu mốc phát hiện, mục RSS gốc, URL chuẩn, trạng thái tải và dấu vết phiên bản. Một bài cũ xuất hiện lại trong RSS cần kiểm tra xem có bằng chứng mới có thể xác minh hay chỉ là hiển thị lại. Lần đầu thấy trong RSS là dấu vết vận hành. Mốc quan sát khoa học cần căn cứ riêng theo Stage 4.10.
3. **Gián đoạn hoặc chạm trần.** Giữ bản ghi những khung bị thiếu và thời điểm chạm 200 URL. Ghi các mục RSS đã quan sát nhưng nằm ngoài phần được tải theo giới hạn. Đánh giá thiếu bao phủ trước khi dùng mẫu. Việc mở rộng sang cửa sổ hoặc nguồn khác cần đề xuất được ghi nhận trước khi xem điểm.
4. **Cutoff chấm dự thảo.** Dùng một cutoff chung tại thời điểm đóng cửa sổ để đơn giản hóa quy tắc nhiều đáp án. Đăng ký trước điều kiện bộ ba đủ tư cách tại cutoff đó. Cả đáp án và tập bộ ba dùng để lọc phải dựa trên bằng chứng, trạng thái hiệu lực và ánh xạ sẵn có tại cutoff. Tách bảng bộ ba đã dùng trong lịch sử để xác định tính mới khỏi bảng sự thật đã biết để lọc các đáp án đúng khác. Chốt các bảng và quy tắc trước khi chấm.

### 10.3 Độ đủ mẫu theo mục tiêu

Phép so sánh chính dự thảo là chênh lệch MRR ghép cặp giữa TransE-L2 và đối chứng tần suất trên cùng tập ứng viên. Tính trung bình ba lần khởi tạo trên cùng khóa truy vấn rồi đối chiếu với đối chứng. Với nhiều đáp án, đề xuất tính trung bình nghịch đảo hạng của từng đáp án hợp lệ trong khóa, rồi tổng hợp qua các khóa phân biệt ở cutoff. Đăng ký trước cách gom nhóm phụ thuộc theo bằng chứng, sự kiện và khóa chung. Báo cáo đồng thời số bài, số nhóm, số bộ ba, số khóa, số đáp án và tỷ lệ ngoài tập huấn luyện.

Hai mục tiêu dưới đây cho các yêu cầu khác nhau. Mục tiêu độ chính xác là khoảng tin cậy 95% với nửa độ rộng 0,05 MRR. Mục tiêu phát hiện là lực kiểm định 80% khi chênh lệch thật là 0,05 và so với mốc 0 bằng kiểm định hai phía ở mức 5%. Các giá trị đều minh họa, chưa là ngưỡng của giao thức. Nếu cần kết luận lợi thế **ít nhất 0,05**, cần thiết kế riêng để đánh giá cận dưới so với 0,05. [Công thức khoảng tin cậy cho trung bình của NIST](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm)

| Độ lệch chuẩn giả định của chênh lệch theo nhóm | Số nhóm cho nửa độ rộng 0,05 | Số nhóm để có 80% lực phát hiện chênh lệch 0,05 |
|---:|---:|---:|
| 0,10 | 16 | 32 |
| 0,15 | 35 | 71 |
| 0,20 | 62 | 126 |
| 0,30 | 139 | 283 |
| 0,40 | 246 | 503 |

Bảng dùng xấp xỉ chuẩn cho các nhóm độc lập, trọng số bằng nhau. Với độ lệch chuẩn giả định là `s`, số nhóm được làm tròn lên từ `(1,96 × s / 0,05)²` cho độ chính xác và `((1,96 + 0,842) × s / 0,05)²` cho lực phát hiện, với các phân vị đầy đủ trong công cụ tính. Phương sai là giả định minh họa, không lấy từ điểm đã chấm. Khi nhóm khác kích thước hoặc chia sẻ dữ liệu, cần dự tính lại theo cấu trúc phụ thuộc và cách tính chỉ số đã đăng ký. Các số đếm bài và truy vấn chỉ là đầu vào của bước kiểm tra độ đủ mẫu.

### 10.4 Quy tắc trùng lặp, lưu trữ và người chịu trách nhiệm

| Trường hợp | Xử lý đề xuất |
|---|---|
| Cùng mã bài, URL sau chuyển hướng hoặc nội dung trùng chính xác | Lưu tất cả lượt thu và bản gốc. Gom vào cùng bản nhận dạng bài hoặc nhóm nội dung. Bản sửa đổi có thay đổi bằng chứng được lưu riêng, liên kết với phiên bản trước |
| Gần trùng, đăng lại hoặc bài về cùng sự kiện | Dùng quy tắc so khớp đã có phiên bản. Lưu quyết định gom và lý do, với bước xem xét của người quản lý cho trường hợp mơ hồ. Giữ bằng chứng mới nếu có. Ghi các liên kết phụ thuộc để tính độ đủ mẫu |
| Bộ ba trùng dữ liệu từng dùng | Gắn cờ theo tập huấn luyện, xác thực, chọn cấu hình hoặc backbone lịch sử. Loại bộ ba đã dùng khỏi nhóm xác nhận liên kết mới theo quy tắc được đăng ký. Vẫn dùng các đáp án đúng khác để lọc khi chúng đủ điều kiện tại cutoff |
| Khóa trùng nhưng đáp án mới | Lưu cờ trùng khóa riêng với trùng bộ ba. Đăng ký trước phạm vi kết luận đối với khóa từng gặp và cách tổng hợp nhiều đáp án |
| Giữ riêng trước chấm | Chỉ định người quản lý độc lập với việc tinh chỉnh mô hình. Dùng kho giới hạn quyền đọc cho nội dung và nhãn. Trước giờ mở, lưu dấu vết phân quyền, mã băm checkpoint và thiết kế. Dùng chế độ chỉ bổ sung cho bản gốc và nhật ký truy cập. Nhóm phát triển nhận số liệu tổng hợp về độ bao phủ và chất lượng. Quy trình chấm được chỉ định chỉ nhận gói có bản kê đã ký nhận khi đủ điều kiện |

### 10.5 Quyết định chuyển bước và bằng chứng

- **Điều kiện đang mở.** Phép rà soát hợp đồng M1 trên checkout hiện tại vẫn trả trạng thái bị chặn, có **9/17 bảng lệch trường**. Lần kiểm tra cũng chưa thấy bản kê W7 chính thức trong thư mục bản kê. Hai trạng thái này cần được xử lý theo phạm vi áp dụng. Phép rà soát chỉ kiểm tra hợp đồng và sự hiện diện của bản kê. [Quy định cổng kiểm tra và khóa giao thức](../gates_and_freeze.md)
- **Bước chuẩn bị có thể tách riêng.** Hoàn thiện bản đăng ký với người quản lý dữ liệu, phạm vi áp dụng của M1, mục tiêu thống kê và điều kiện dừng. Sau đó thử luồng đọc RSS, xử lý trùng, dấu thời gian và quyền truy cập bằng dữ liệu mẫu. Phép thử chuẩn bị có thể dùng dữ liệu mô phỏng hoặc dữ liệu cũ đã được phép sử dụng.
- **Điều kiện thu và chấm.** Chỉ mở đợt thật khi các điều kiện trước thu ở mục 9.3 được xác nhận. Sau thu, người quản lý đối chiếu nguồn gốc, dữ liệu trùng, định danh chưa thấy, số nhóm độc lập dự kiến và phạm vi bao phủ trước khi mở điểm. Phép chấm xác nhận cần thêm điều kiện đăng ký, dữ liệu và quyền truy cập tương ứng. Nếu độ đủ mẫu chưa đạt, đầu ra của đợt là báo cáo khả thi.

**Mức xác minh.** Đã thực hiện và kiểm chứng phép đếm cấu trúc lịch sử cùng các kịch bản tính cỡ mẫu (**EXECUTED / VERIFIED** trong phạm vi phân tích). Đối chiếu 26 mã băm đầu vào, đọc lại phân bố nguồn qua mã băm nội dung thô và kiểm tra chuyển đổi giờ của cửa sổ dự thảo. Đợt phân tích sử dụng cấu trúc dữ liệu lịch sử và giả định minh họa. Chưa có dữ liệu thu mới hay kết quả kiểm thử tiến cứu. [Kết quả phân tích](../../outputs/kge_prospective_readiness/20261104_v1/phan_tich_kha_thi.json) · [Bản kê](../../outputs/kge_prospective_readiness/20261104_v1/experiment_manifest.json)

```powershell
.venv-m1/Scripts/python.exe scripts/audit_kge_prospective_readiness.py outputs/kge_prospective_readiness/tai_lap_01
```

## 11. Dự thảo đăng ký và diễn tập quy trình

### 11.1 Nội dung đã đưa vào dự thảo

1. Xác định VnExpress Số Hóa qua RSS là nguồn cho **đợt đánh giá khả thi**. Cửa sổ 09/11 đến trước 07/12/2026 giờ Việt Nam, bốn lượt mỗi ngày và trần 200 URL vẫn là tham số dự thảo. Mốc thực tế cần được duyệt lại nếu điều kiện mở chưa đủ.
2. Đối chiếu bản kê của đề xuất nguồn, phân tích khả thi và gói thiết kế T01. Gắn dự thảo với mã băm của ba checkpoint vòng 50, tệp kiểm tra đi kèm và tập 101 bộ ba dùng cho đối chứng tần suất.
3. Ghi phép so sánh chính dự thảo là chênh lệch MRR ghép cặp, tổng hợp trên khóa truy vấn. Độ chính xác hoặc lực kiểm định, số nhóm cần thiết, quy tắc gom phụ thuộc và phạm vi định danh chưa thấy vẫn cần quyết định trước khi triển khai. Nếu mẫu thiếu, đầu ra là báo cáo khả thi.
4. Mô tả trách nhiệm giữ riêng. Người quản lý có quyền đọc dữ liệu gốc và lưu bản kê. Nhóm phát triển nhận số đếm. Quy trình chấm nhận bản kê khi đủ điều kiện bàn giao.

### 11.2 Các phép thử và kết quả

| Phép thử | Kết quả bằng dữ liệu mô phỏng |
|---|---|
| Lịch đọc RSS và lỗi | Ghi đủ 112 khung dự kiến. Một khung có lỗi giả lập và vẫn hiện trong nhật ký. Năm mục trong RSS mẫu cho bốn URL phân biệt |
| Biên thời gian | Mốc mở được tính trong cửa sổ, mốc đóng nằm ngoài. Kiểm tra thêm một giây trước mỗi mốc và trường hợp thiếu bằng chứng thời gian. Trường hợp thiếu được chuyển sang cách ly |
| Trùng lặp và bản sửa đổi | Gom URL lặp và đối chiếu mã băm nội dung trùng. Bản sửa đổi có mã băm riêng và tham chiếu bản trước. Tình huống gần trùng chờ duyệt bị giữ lại, còn tình huống có quyết định mô phỏng được đưa vào bản kê theo quyết định đã nhập |
| Trần URL | Kiểm tra quy tắc ở 199, 200 và 201 URL. Chỉ trường hợp còn dưới trần được xét thêm URL |
| Phân vai và bàn giao | Vai trò phát triển chỉ nhận số đếm. Vai trò quản lý đọc được dữ liệu mô phỏng. Vai trò chấm bị từ chối khi chưa có phê duyệt mô phỏng và nhận bản kê khi được phê duyệt. Vai trò không xác định bị từ chối |

Đã đối chiếu 18 mã băm đầu vào và hai tệp đầu ra. Chạy lại phần diễn tập cho đúng chuỗi byte của kết quả đã lưu. Ruff và kiểm tra khoảng trắng Git đạt.

### 11.3 Phạm vi xác minh và điều kiện tiếp theo

**Mức xác minh là IMPLEMENTED / TESTED cho dự thảo và diễn tập.** RSS, phiên bản bài, quyết định gần trùng và vai trò đều là tình huống giả lập. Phép thử phân vai chỉ kiểm tra đầu ra của từng vai trò trong chương trình mô phỏng. Quyền truy cập kho thật, nhật ký thật, khả năng đọc RSS thực tế và quy tắc phát hiện gần trùng vẫn cần kiểm tra ở môi trường được chỉ định. Phép thử thời gian dùng mốc đã cho sẵn và chưa xác minh cách suy ra mốc quan sát khoa học từ bài thật.

Trước đợt thu thật, cần chỉ định người quản lý dữ liệu, xác nhận điều kiện M1 áp dụng, kiểm tra quyền trên kho được chỉ định, duyệt quy tắc mốc quan sát và gần trùng, rồi đăng ký lịch cùng tiêu chí đủ mẫu. Gói hiện tại có trạng thái **DỰ THẢO CHƯA ĐĂNG KÝ** và dùng cho xem xét nội bộ.

[Bản đăng ký dự thảo](../../outputs/kge_prospective_registration_rehearsal/20261104_v1/dang_ky_du_thao.json) · [Kết quả diễn tập](../../outputs/kge_prospective_registration_rehearsal/20261104_v1/ket_qua_dien_tap.json) · [Bản kê](../../outputs/kge_prospective_registration_rehearsal/20261104_v1/experiment_manifest.json)

Lệnh tái lập với thư mục kết quả mới.

```powershell
.venv-m1/Scripts/python.exe scripts/rehearse_kge_prospective_registration.py outputs/kge_prospective_registration_rehearsal/tai_lap_01
```

## 12. Chuẩn bị huấn luyện lại M2 có xác thực

### 12.1 Phân biệt hai mục đích huấn luyện

**Phương án đề xuất là tách hai lượt.** Lượt đánh giá chất lượng giữ riêng một phần bộ ba của từng snapshot và lưu xác thực theo từng epoch. Lượt huấn luyện mô hình nền để đo độ trôi dùng toàn bộ snapshot và lưu chẩn đoán huấn luyện. Kết quả xác thực gắn với checkpoint của lượt giữ riêng. Phương án này giữ ý nghĩa của phép đo độ trôi giữa các đồ thị đầy đủ, đồng thời cho biết mô hình học được gì trên phần giữ riêng.

Phương án dùng trực tiếp checkpoint của lượt giữ riêng để đo độ trôi sẽ đo biểu diễn của các đồ thị đã loại một số bộ ba. Cách đó cần quy tắc chọn phần giữ riêng nhất quán giữa các mốc và đăng ký lại quần thể phép đo. Tập neo, nhiễu tham chiếu và phép đo độ trôi cũng phải nhất quán với dữ liệu thực tế đã huấn luyện.

Phạm vi dự kiến của mỗi lượt là T01–T10 và ba lần khởi tạo 13, 37, 101. Cấu hình để xem xét là TransE-L2, 64 chiều, 50 epoch, tốc độ học 0,01 và biên 1,0 theo cấu hình ứng viên đã có. Đây là giá trị dự thảo. Quy tắc chọn epoch và lịch lưu cần được đăng ký trước khi đọc kết quả mới.

### 12.2 Kiểm tra khả thi từ dữ liệu V3.1

1. Đọc 10 snapshot chuẩn và đối chiếu cấu hình, ranh giới, Parquet và bản kê với bản phát hành V3.1.
2. Chạy thử phép chia theo thứ tự mã băm và quy tắc giữ đủ thực thể, quan hệ trong tập huấn luyện. Tham số **mục tiêu 20%** và salt lấy từ pilot cũ để so khả thi. Tập xác thực thực tế nhỏ hơn mục tiêu khi việc giữ thêm bộ ba sẽ làm thiếu định danh. Các tập thành viên thử không được xuất để dùng làm tập đã đăng ký.
3. Thử tạo một cặp âm cố định cho mỗi bộ ba xác thực bằng phương thức hiện có. Tất cả snapshot tạo đủ cặp trong phép thử. Quy tắc chính thức về mẫu âm, phạm vi lọc và lịch xếp hạng vẫn thuộc bản thiết kế trước khi huấn luyện.

| Snapshot | Tổng bộ ba | Huấn luyện trong phép thử | Xác thực trong phép thử |
|---|---:|---:|---:|
| T01 | 121 | 101 | 20 |
| T02 | 247 | 208 | 39 |
| T03 | 362 | 305 | 57 |
| T04 | 483 | 402 | 81 |
| T05 | 604 | 491 | 113 |
| T06 | 724 | 586 | 138 |
| T07 | 844 | 676 | 168 |
| T08 | 964 | 772 | 192 |
| T09 | 1.084 | 868 | 216 |
| T10 | 1.205 | 964 | 241 |

Một lượt có 30 tổ hợp snapshot–seed. Nếu lưu vector mỗi epoch trong 50 epoch của lượt xác thực, sẽ có **1.500 checkpoint**, ước khoảng **2,26 GB** cho riêng tệp vector JSON theo checkpoint mẫu T01. Xếp hạng đầy đủ mỗi epoch sẽ tạo khoảng **379.500 dòng thứ hạng**, với gần **399,3 triệu lượt xét ứng viên trước lọc**. Đây là ước tính khối lượng, chưa đo thời gian chạy. Có thể giữ loss theo từng epoch và định trước các mốc xếp hạng nếu thời gian là giới hạn. Mọi mốc cần được chốt trước khi xem điểm.

### 12.3 Bằng chứng cần lưu và cách đọc

| Câu hỏi | Dữ liệu cần lưu | Cách đánh giá |
|---|---|---|
| Mô hình có tối ưu được mục tiêu huấn luyện? | Loss trong lúc cập nhật, số bộ ba dương, mẫu âm hợp lệ và bị bỏ qua, số vi phạm biên, số cập nhật | Tìm giá trị không hữu hạn, epoch thiếu mẫu âm, mất cân đối số đếm hoặc đường loss bất thường. Loss huấn luyện cho biết diễn biến tối ưu |
| Embedding có xếp đúng các liên kết giữ riêng? | Loss xác thực trên cặp cố định, thứ hạng head/tail, MRR, Hits@1/3/10, tập ứng viên và số trường hợp ngoài định danh | So sánh với đối chứng tần suất tính từ tập train, dùng cùng truy vấn, bộ lọc và đồng hạng. Báo cáo mức chênh lệch theo snapshot và seed. Xác thực giữ riêng phục vụ đánh giá phát triển |
| Có dấu hiệu quá khớp hoặc nhạy với khởi tạo? | Đường cong cho từng seed, trung bình và khoảng dao động, epoch cố định và mọi mốc được xem xét | Xem loss huấn luyện cùng xu hướng xác thực và thứ hạng. Công cụ hiện có lưu loss huấn luyện trong lúc cập nhật. Nếu cần so hai loss trên cùng một trạng thái mô hình sau epoch, bổ sung loss chấm lại trên một mẫu train cố định và đặt tên riêng |
| Kết quả có đúng và tái lập được? | Checkpoint, mã băm dữ liệu, tập chia, mẫu âm, ánh xạ, cấu hình, mã nguồn, môi trường và kết quả kiểm tra độc lập | Nạp lại checkpoint, kiểm tra kích thước và vector hữu hạn, ánh xạ nhất quán giữa seed, tính lại loss xác thực và thứ hạng từ các vector đã lưu |
| Có dùng được để đo độ trôi? | Checkpoint toàn snapshot, thống kê huấn luyện và kiểm tra căn chỉnh ở bước sau | Kiểm tra tính nhất quán đầu vào giữa các lần khởi tạo. Áp dụng tiêu chí căn chỉnh và nhiễu theo đăng ký phép đo M2 |

Công cụ hiện tại đã hỗ trợ lưu loss huấn luyện, loss xác thực cố định, chẩn đoán mẫu âm, thứ hạng, chỉ số và checkpoint mỗi epoch cho một snapshot. Lần chạy 10 snapshot cần chốt cách tổ chức lượt chạy và thêm báo cáo đối chứng theo cùng quy tắc trước khi dùng kết quả làm căn cứ quyết định. Dữ liệu T01 từng dùng chọn cấu hình và V3.1 từng dùng trong các lần huấn luyện lịch sử. Mọi kết luận từ thiết kế này cần ghi rõ phạm vi xác thực phát triển.

### 12.4 Trạng thái

Đã thực hiện và kiểm chứng rà soát khả thi trên dữ liệu thật (**EXECUTED / VERIFIED** trong phạm vi chuẩn bị). Đã đối chiếu 42 mã băm đầu vào, số lượng phân hoạch và số cặp âm thử. Chưa tạo lượt huấn luyện mới. Việc còn cần chốt là vai trò checkpoint có xác thực, phân hoạch và quy tắc chấm. Khi dùng backbone cho lần xác nhận, các điều kiện khoa học M1/M2 và khóa giao thức tiếp tục được áp dụng.

[Số liệu khả thi](../../outputs/m2_retraining_preparation/20261104_v1/kha_thi_xac_thuc.json) · [Bản kê](../../outputs/m2_retraining_preparation/20261104_v1/experiment_manifest.json)

```powershell
.venv-m1/Scripts/python.exe scripts/inspect_m2_retraining_feasibility.py outputs/m2_retraining_preparation/tai_lap_01
```

## 13. Thực hiện cách 1, lượt đánh giá embedding có xác thực

### 13.1 Thiết kế đã sử dụng

Người dùng chọn cách 1, gồm lượt đánh giá giữ riêng và lượt tạo backbone toàn snapshot. Lượt được thực hiện trong phần này là **đánh giá chất lượng trong môi trường phát triển**. Đầu vào là V3.1 từ T01 đến T10. Mỗi snapshot chạy độc lập với ba seed 13, 37 và 101. Mỗi lần dùng TransE-L2, 64 chiều, 50 epoch cố định, tốc độ học 0,01, biên 1,0 và chuẩn hóa vector thực thể.

1. Tái lập phân hoạch theo quy tắc giữ đủ định danh, với mục tiêu 20% và salt từ pilot đã rà soát ở mục 12. Đối chiếu số lượng từng snapshot, lưu tập thành viên và mã băm trước khi huấn luyện.
2. Lưu một mẫu âm cố định cho mỗi bộ ba xác thực với seed tạo mẫu 13, dùng chung cho ba seed huấn luyện và mọi epoch. Quá trình huấn luyện lọc mẫu âm theo tập huấn luyện. Chấm xác thực lọc các bộ ba đúng đã biết trong chính snapshot đang chấm.
3. Đăng ký trước đối chứng tần suất từ tập huấn luyện. Dùng cùng truy vấn dự đoán thực thể đầu và cuối, cùng ứng viên, bộ lọc và hạng trung bình khi đồng điểm. Epoch 50 là điểm so sánh mô tả cố định. Không chọn epoch dựa trên kết quả đã chấm.
4. Lưu loss trong quá trình cập nhật, loss xác thực, số mẫu, MRR, Hits@1/3/10, thứ hạng từng truy vấn và checkpoint ở mọi epoch. Công cụ kiểm tra nạp checkpoint, xác minh nguồn gốc và tính lại loss xác thực và thứ hạng bằng phép sắp xếp độc lập. Kiểm tra loss huấn luyện theo số đếm và tổng loss đã lưu. Hai đường loss có cách tính khác nhau, nên phần diễn giải xét xu hướng riêng của từng đường.

Để chấm đủ mọi epoch với tập ứng viên lớn, phép tính điểm ứng viên dùng mảng NumPy. Phía chấm dùng lại bộ tính điểm từng ứng viên ở trường hợp sát đồng điểm. Phía kiểm tra dùng cách sắp xếp và xác định vị trí đồng hạng. Đối chiếu thêm 78 truy vấn tại T08–T10 với cách tính từng ứng viên cho cùng thứ hạng và số ứng viên. Kiểm tra lại 50 epoch của một seed từ pilot T01 đã lưu cũng đạt. Bộ kiểm thử hiện tại có 689 đạt và 10 bỏ qua, Ruff đạt.

| Hồ sơ | Vị trí |
|---|---|
| Đăng ký lượt xác thực | [Kế hoạch và liên kết tới từng thiết kế](../../outputs/m2_quality_validation_registration/20261104_v1/ke_hoach.json) |
| Gói huấn luyện | [Bản kê lượt xác thực V3.1](../../outputs/m2_quality_validation_v31/20261104_v1/experiment_manifest.json) |

Lệnh tái lập với hai thư mục mới. Python 3.11 được dùng để huấn luyện và kiểm chứng.

```powershell
.venv-m1/Scripts/python.exe scripts/run_m2_quality_validation_v31.py --registration outputs/m2_quality_validation_registration/tai_lap_01
.venv-m1/Scripts/python.exe scripts/run_m2_quality_validation_v31.py --registration outputs/m2_quality_validation_registration/tai_lap_01 --output outputs/m2_quality_validation_v31/tai_lap_01 --workers 3
```

### 13.2 Kết quả sau 50 epoch

Các số dưới đây lấy trung bình ba seed trong từng snapshot. MRR đối chứng được tính lại độc lập từ tần suất trong tập huấn luyện và các bộ lọc đã đăng ký.

| Snapshot | Bộ ba xác thực | MRR vòng 1 | MRR vòng 50 | MRR đối chứng | Chênh lệch ở vòng 50 |
|---|---:|---:|---:|---:|---:|
| T01 | 20 | 0,0300 | 0,1229 | 0,0565 | +0,0664 |
| T02 | 39 | 0,0228 | 0,0922 | 0,0514 | +0,0408 |
| T03 | 57 | 0,0135 | 0,0986 | 0,0656 | +0,0330 |
| T04 | 81 | 0,0141 | 0,1070 | 0,0905 | +0,0165 |
| T05 | 113 | 0,0105 | 0,0858 | 0,0893 | −0,0034 |
| T06 | 138 | 0,0086 | 0,0981 | 0,1140 | −0,0159 |
| T07 | 168 | 0,0054 | 0,0938 | 0,1089 | −0,0151 |
| T08 | 192 | 0,0071 | 0,0997 | 0,1129 | −0,0132 |
| T09 | 216 | 0,0058 | 0,1023 | 0,1021 | +0,0002 |
| T10 | 241 | 0,0058 | 0,1085 | 0,0872 | +0,0213 |
| **Trung bình đều qua 10 snapshot** | — | **0,0124** | **0,1009** | **0,0878** | **+0,0131** |

- Trung bình đều qua các snapshot, hàm mất mát huấn luyện giảm từ **1,0011 xuống 0,4558** và hàm mất mát xác thực giảm từ **0,9925 xuống 0,8321**. MRR xác thực ở vòng 50 cao hơn vòng 1 ở cả 10 snapshot.
- MRR trung bình ba seed cao hơn đối chứng ở **6/10 snapshot**, trong đó T09 chênh khoảng **+0,0002**. T01–T04 và T10 cao hơn ở cả ba seed. Tổng cộng **18/30** tổ hợp snapshot–seed cao hơn đối chứng. T05–T08 có MRR trung bình thấp hơn đối chứng. Những con số này là so sánh mô tả trên tập xác thực. Chúng cho thấy chất lượng xếp hạng cải thiện trong quá trình học, với lợi thế so với đối chứng thay đổi theo snapshot.
- Các đường xác thực gắn với đúng checkpoint học trên phần huấn luyện của từng snapshot. Tập xác thực từng phần của V3.1 phục vụ đánh giá phát triển. Phép đối chứng hồi cứu trên 26 bộ ba ở mục 4 dùng quần thể khác, nên diễn giải kết quả đó theo phạm vi riêng.

![Hàm mất mát huấn luyện và xác thực qua 50 vòng cho 10 snapshot V3.1](../../outputs/m2_quality_validation_v31_report/20261104_v2/ham_mat_mat.png)

![MRR xác thực và đối chứng tần suất cho 10 snapshot V3.1](../../outputs/m2_quality_validation_v31_report/20261104_v2/thu_hang_xac_thuc.png)

### 13.3 Kiểm chứng, khôi phục bản kê và bàn giao

Đã huấn luyện và kiểm chứng **30/30 lần**, **1.500 checkpoint**, **1.500 giá trị loss xác thực** và **379.500 dòng thứ hạng**. Số mẫu âm huấn luyện bị bỏ qua là **0** trong các log đã lưu. Tệp vector JSON chiếm khoảng **2,25 GB**. Bản kê của 10 snapshot ràng buộc tổng cộng **5.130 tệp**. Khi đối chiếu riêng T01 với pilot trước, vector thực thể và quan hệ ở epoch 50 khớp chính xác cho cả ba seed. Phép kiểm tra độc lập tính lại loss xác thực và thứ hạng từ checkpoint, đồng thời đối chiếu phép tính loss huấn luyện với số đếm và tổng đã lưu.

Lệnh điều phối ban đầu dừng khi in tiếng Việt bằng mã hóa mặc định trên Windows. Tất cả 10 gói con đã hoàn tất. Bản mã điều phối ban đầu được lưu lại theo đúng SHA-256 và công cụ được sửa để dùng thông báo tiến độ tương thích. Chế độ hoàn tất bản kê kiểm tra lại từng gói con, tập đầu vào và biên nhận xác minh rồi tạo bản kê tổng từ các tệp đã có. Lần xuất biểu đồ đầu thiếu trường hệ điều hành trong bản kê. Bản báo cáo v2 bổ sung trường này và chỉnh khoảng cách giữa chú giải với tiêu đề ô. Các khắc phục trên hoàn tất ở bước đóng gói kết quả.

**Mức xác minh là EXECUTED / VERIFIED cho lượt xác thực phát triển.** Lượt tạo backbone trên toàn snapshot là công đoạn tiếp theo của cách 1. Trước khi chạy công đoạn đó, cần chốt cấu hình huấn luyện từ hồ sơ lượt đánh giá và áp dụng các điều kiện đăng ký của phạm vi chạy. Kết quả xác thực ở đây không chuyển sang checkpoint sẽ học trên toàn snapshot.

| Tệp | Nội dung |
|---|---|
| [Tổng hợp kết quả](../../outputs/m2_quality_validation_v31_report/20261104_v2/tong_hop.json) | Loss, MRR, Hits@1/3/10, từng seed và đối chứng |
| [Đường cong theo epoch](../../outputs/m2_quality_validation_v31_report/20261104_v2/duong_cong.json) | Chuỗi giá trị đã dùng để vẽ |
| [Bản kê báo cáo và biểu đồ](../../outputs/m2_quality_validation_v31_report/20261104_v2/experiment_manifest.json) | Ràng buộc nguồn và các tệp báo cáo |

## 14. Kiểm tra trước khi chốt backbone toàn snapshot

### 14.1 Kiểm tra lại lượt xác thực

1. Đối chiếu bản đăng ký, bản kê của 10 snapshot và báo cáo. Đọc lại **5.130 tệp** theo mã băm và xác nhận **1.500 epoch, 379.500 thứ hạng**, với **0 mẫu âm bị bỏ qua** trong nhật ký huấn luyện. Bản đăng ký ban đầu tham chiếu mã điều phối trước khi sửa lỗi in tiếng Việt. Đã kiểm đúng bản sao mã điều phối cũ theo mã băm trong hồ sơ khôi phục.
2. Tính lại loss xác thực và thứ hạng từ vector đã lưu cho seed 13 ở T01 và T10, hai đầu của dãy snapshot. Đã kiểm lại **100 epoch và 26.100 thứ hạng** ở hai lần chạy này. Các biên nhận kiểm chứng trước đây của cả 30 lần huấn luyện khớp bản kê.
3. Kiểm tra đoạn cuối đường cong từ các log đã lưu. Từ vòng 40 đến 50, MRR trung bình qua 10 snapshot tăng từ **0,0880 lên 0,1009** và loss xác thực trung bình giảm từ **0,8482 xuống 0,8321**. MRR vòng 50 cao hơn vòng 40 ở cả 10 snapshot. T02 và T08 có MRR trung bình quan sát được cao nhất ở vòng 48. Mốc 50 là ngân sách đã dùng để đối chiếu, chưa xác lập điểm hội tụ hoặc số epoch tối ưu.

### 14.2 Nội dung cần chốt

Chốt cấu hình là ghi trước các thông số và quy tắc áp dụng chung cho cả 30 lần huấn luyện backbone, kèm mã băm để mỗi kết quả truy về đúng thiết kế. Đề xuất dùng cấu hình đã kiểm tra ở lượt xác thực làm cấu hình đối chiếu có kiểm soát cho backbone.

| Thành phần | Giá trị đề xuất |
|---|---|
| Đầu vào | Toàn bộ bộ ba Parquet chuẩn của từng snapshot V3.1, T01–T10. Ghi mã băm snapshot, ánh xạ và cutoff |
| Mô hình | TransE-L2, 64 chiều, tốc độ học 0,01, biên 1,0 và chuẩn hóa vector thực thể |
| Khởi tạo | Huấn luyện từ đầu, độc lập cho mỗi tổ hợp snapshot và seed 13, 37, 101 |
| Lấy mẫu âm | Thay thực thể đầu hoặc cuối, lọc bộ ba dương của cùng snapshot. Giữ cùng cách lấy mẫu giữa các tổ hợp |
| Ngân sách và checkpoint | Dùng 50 epoch chung, checkpoint vòng 50 cho mỗi tổ hợp, lưu loss và số đếm theo từng epoch. Dùng cùng một ngân sách để các mốc thời gian có điều kiện huấn luyện nhất quán |
| Cách cập nhật | SGD theo từng bộ ba. Trường `batch_size=32` giữ trong cấu hình để tái lập danh tính, mã hiện tại không gom gradient theo lô 32 |

Lượt backbone dùng toàn snapshot nên không có phần giữ riêng của snapshot đó. Điểm xác thực vẫn thuộc về các checkpoint đã chấm ở mục 13. Nếu cần chọn ngân sách vì mục tiêu tối đa hóa chất lượng dự đoán, có thể thiết kế phép thử thêm ở lượt đánh giá, với cùng lịch kiểm tra đã đăng ký. Khi ưu tiên phép so sánh độ trôi, 50 epoch chung là lựa chọn có căn cứ từ lượt đã kiểm và dễ tái lập.

### 14.3 Điều kiện thực thi

Cấu hình backbone dưới đây đang ở trạng thái **dự thảo**. Cần trình chạy mới cho V3.1 với đầu vào và cấu hình đã đăng ký, lưu checkpoint toàn snapshot và kiểm tra độc lập. Trình chạy backbone V3 cũ đã ngừng. Việc xác định ngưỡng căn chỉnh và các tham số nhiễu thuộc đăng ký phép đo M2 sau đó. Kiểm tra hiện tại vẫn ghi 12 điều kiện chưa đủ cho phép đo M2. Các cổng khoa học áp dụng tiếp tục được đánh giá theo phạm vi lần chạy.

Đã đối chiếu **115 mã băm đầu vào và hai tệp kết quả**. Mức **EXECUTED / VERIFIED** chỉ áp dụng cho lượt kiểm tra lại. Chưa huấn luyện backbone ở lượt này. [Cấu hình backbone dự thảo](../../outputs/m2_backbone_design_review/20261104_v1/cau_hinh_backbone_du_thao.json) · [Kết quả kiểm lại](../../outputs/m2_backbone_design_review/20261104_v1/kiem_tra_lai.json)

```powershell
.venv-m1/Scripts/python.exe scripts/check_m2_backbone_design.py outputs/m2_backbone_design_review/tai_lap_01
```

## 15. Tìm số chiều và số epoch bằng tập xác thực

### 15.1 Căn cứ của lựa chọn trước đây

Trong pilot cũ, 32 chiều đạt MRR xác thực T01 **0,110916** và 64 chiều đạt **0,122906**, trung bình ba seed. Cả hai phương án đạt 9/9 phép căn chỉnh trong phạm vi pilot T01/T02. Quy tắc chọn đã ghi trước ưu tiên điều kiện căn chỉnh rồi đến MRR. Kết quả đó là căn cứ đề xuất 64 chiều từ pilot. Ngân sách 50 epoch là mốc cố định của pilot. Lượt sau cho thấy MRR trung bình vẫn tăng từ **0,0880 ở vòng 40** lên **0,1009 ở vòng 50**, tạo căn cứ để khảo sát thêm. [Báo cáo pilot chọn số chiều](M2_PILOT_REPORT_20261014.md)

Huấn luyện TransE-L2 với 128 chiều là khả thi về mặt định nghĩa mô hình. Trong thiết kế căn chỉnh hiện tại, ma trận 101 neo sau khi trừ trung bình có hạng tối đa 100. Với 128 chiều và tỷ lệ hạng tối thiểu 90% đang được dùng trong cấu hình ứng viên, phép căn chỉnh cần hạng ít nhất 116. Vì vậy 128 chiều nằm ngoài lưới hiện tại và vướng một giới hạn cấu trúc với cách bố trí neo này. Mở rộng lưới để dùng 128 chiều trong nghiên cứu chính cần một thiết kế neo có căn cứ, được duyệt và kiểm chứng riêng.

Bài báo TransE gốc chọn siêu tham số và thời điểm dừng dựa trên hiệu năng xác thực. Kết quả của bài báo cho thấy lựa chọn khác nhau theo tập dữ liệu. Lượt này áp dụng nguyên tắc so sánh trên tập xác thực với MRR theo mục tiêu dự án. [Bordes và cộng sự, TransE](https://proceedings.neurips.cc/paper_files/paper/2013/file/1cecc7a77928ca8133fa24680a88d2f9-Paper.pdf)

### 15.2 Thiết kế tìm kiếm

1. Giữ nguyên 10 snapshot V3.1, tập huấn luyện và xác thực, ba seed, cặp âm cố định, tập ứng viên, bộ lọc và quy tắc đồng hạng từ lượt trước. Tốc độ học 0,01, biên 1,0, chuẩn L2 và cách chuẩn hóa thực thể được giữ để cô lập ảnh hưởng của số chiều và ngân sách huấn luyện.
2. Chạy 32 và 64 chiều đến 250 epoch, với **60 lần huấn luyện từ đầu**. Chấm tại epoch 1 và mỗi 5 epoch đến 250. Lưu loss huấn luyện ở mọi epoch, loss xác thực, chỉ số, thứ hạng và checkpoint tại mọi mốc chấm. Tính lại loss xác thực và thứ hạng bằng vector đọc từ checkpoint.
3. Tính trung bình MRR của ba seed trong từng snapshot, rồi lấy trung bình đều qua 10 snapshot. Chọn một số chiều và một epoch chung theo MRR cao nhất trong lưới. Nếu bằng điểm chính xác, ưu tiên chiều nhỏ hơn rồi epoch sớm hơn. Dữ liệu đo độ trôi, hỏi đáp và H1/H2 nằm ngoài phép chọn này.
4. Diễn giải kết quả theo phạm vi xác thực phát triển. Mốc được chọn là tốt nhất trong lưới với các thông số còn lại đã cố định. Vị trí cực đại sát trần, dao động giữa seed và chênh lệch giữa snapshot cần được xem cùng đường cong trước khi chốt backbone.

Trước lượt chính đã thử 5 epoch cho T10 ở 32 chiều và kiểm lại hai mốc chấm. Lệnh khởi động song song đầu tiên dừng trước khi các tiến trình con huấn luyện do tên mô-đun `statistics` trùng với mô-đun của Python. Đã thay phép lấy trung bình bằng phép tổng tường minh và chạy ở thư mục kết quả mới.

### 15.3 Kết quả và cấu hình đề xuất

| Số chiều | MRR ở epoch 50 | Epoch có MRR cao nhất trong lưới | MRR cao nhất | MRR ở epoch 250 |
|---:|---:|---:|---:|---:|
| 32 | 0,06980 | 115 | 0,10040 | 0,09705 |
| **64** | **0,10090** | **85** | **0,11846** | **0,10227** |

**Đề xuất cho lượt backbone là TransE-L2 64 chiều và 85 epoch chung**, tốc độ học 0,01, biên 1,0, chuẩn hóa vector thực thể và seed 13, 37, 101. Đây là cấu hình có MRR xác thực cao nhất trong **102 tổ hợp số chiều và mốc chấm**. Với 64 chiều, MRR vòng 90 là 0,11821, vòng 100 là 0,11749 và vòng 250 là 0,10227. Đỉnh xuất hiện trong khoảng đã khảo sát. Mốc 85 hơn mốc 50 khoảng **0,01756 MRR**, tương đương **17,4%** theo phép so sánh mô tả. Chênh lệch với vòng 90 khoảng **0,00025**, nên kết quả cần được đọc cùng độ phân giải 5 epoch và độ dao động qua các snapshot.

Ở mốc được chọn, đối chứng tần suất có MRR trung bình **0,08784**. TransE-L2 cao hơn đối chứng ở **8/10 snapshot**. T06 và T07 vẫn thấp hơn. Trung bình đều qua seed và snapshot, Hits@1 đạt **2,01%**, Hits@3 đạt **17,61%** và Hits@10 đạt **26,13%**. Việc thử nhiều mốc và chọn mốc cao nhất dùng chính tập xác thực phát triển, nên các số này dùng cho chọn cấu hình và diễn giải phát triển.

![So sánh MRR xác thực theo số chiều và số vòng huấn luyện](../../outputs/m2_dimension_epoch_search_report/20261104_v1/so_sanh_MRR_theo_epoch.png)

### 15.4 Kiểm chứng và bàn giao

Đã thực hiện **60/60 lần huấn luyện**, tổng **15.000 epoch**. Đã tính lại loss xác thực và **774.180 dòng thứ hạng** tại **3.060 checkpoint** đọc từ đĩa. Bước tổng hợp độc lập tính lại MRR và Hits@k từ thứ hạng, đối chiếu phép chọn trong lưới và xác nhận vector **30/30 checkpoint 64 chiều ở epoch 50** khớp chính xác với lượt xác thực trước. Toàn bộ kiểm thử có 689 đạt và 10 bỏ qua. Ruff và kiểm tra khoảng trắng Git đạt.

Mức **EXECUTED / VERIFIED** áp dụng cho tìm kiếm cấu hình trên tập xác thực phát triển. Cấu hình 64 chiều, 85 epoch là đề xuất dùng cho lượt backbone toàn snapshot. Độ phù hợp hình học của backbone mới cần kiểm chứng ở công đoạn căn chỉnh. Quy tắc và tham số phép đo độ trôi được đăng ký riêng.

[Thiết kế và bản kê lượt tìm kiếm](../../outputs/m2_dimension_epoch_search/20261104_v2/experiment_manifest.json) · [Kết quả đầy đủ của lưới](../../outputs/m2_dimension_epoch_search/20261104_v2/ket_qua_tim_kiem.json) · [Kiểm tra độc lập phép chọn](../../outputs/m2_dimension_epoch_search_report/20261104_v1/kiem_tra_chon_cau_hinh.json)

## 16. Huấn luyện mô hình nền M2 trên toàn snapshot V3.1 — 2026-11-10

### 16.1 Cơ sở chọn thiết kế và cấu hình

Đối tượng cần so sánh ở M2 là biểu diễn của **hai đồ thị đầy đủ tại hai cutoff**. Vì vậy, lượt này huấn luyện lại từ đầu trên toàn bộ Parquet chuẩn của từng snapshot. Lượt giữ riêng bộ ba ở mục 15 cung cấp bằng chứng chọn cấu hình và đánh giá dự đoán liên kết trên tập xác thực phát triển. Điểm xác thực đó thuộc các checkpoint giữ riêng. Mỗi checkpoint toàn snapshot đã học cả những bộ ba từng được giữ riêng.

| Quyết định | Cơ sở và bằng chứng |
| --- | --- |
| **TransE với chuẩn L2** | Giao thức M2 quy định TransE-L2 làm mô hình nền kiểm soát. Năng lượng của bộ ba là \(\lVert h+r-t\rVert_2\), càng thấp càng phù hợp với phép tịnh tiến. Bài báo gốc mô tả mô hình tịnh tiến, huấn luyện theo biên và chọn cấu hình bằng tập xác thực. [Giao thức](../../configs/protocol_v1.yaml) · [Bordes và cộng sự, 2013](https://proceedings.neurips.cc/paper_files/paper/2013/file/1cecc7a77928ca8133fa24680a88d2f9-Paper.pdf) |
| **64 chiều** | MRR xác thực tốt nhất của 64 chiều là **0,11846** tại vòng 85. Với 32 chiều, mức tốt nhất là **0,10040** tại vòng 115. Không gian được phép dò là 32 và 64. Với thiết kế neo ứng viên 101 điểm khớp, ma trận sau định tâm có hạng tối đa 100. Điều kiện hạng 90% ở 128 chiều đòi ít nhất 116, vượt giới hạn này. Khả năng căn chỉnh của checkpoint 64 chiều mới cần được đo riêng. [Chính sách KGE](../../configs/kge.yaml) · [Thiết kế neo ứng viên](../../configs/m2_data_3_1_candidate_v2.yaml) · [Biên nhận phép chọn](../../outputs/m2_dimension_epoch_search_report/20261104_v1/kiem_tra_chon_cau_hinh.json) |
| **85 epoch chung** | Quy tắc chọn là MRR đã lọc, trung bình đều ba seed trong mỗi snapshot rồi trung bình đều 10 snapshot. Trong 102 tổ hợp đã chấm, 64 chiều tại vòng 85 đạt **0,11846**, so với **0,10090** ở vòng 50, **0,11821** ở vòng 90 và **0,10227** ở vòng 250. Mốc 85 vượt đối chứng tần suất ở 8/10 snapshot. Chênh lệch nhỏ với vòng 90, độ phân giải 5 vòng và việc sử dụng cùng tập xác thực để chọn mốc giới hạn phạm vi của kết luận. Giữ 85 vòng chung giúp tránh đưa quy tắc dừng riêng cho từng snapshot vào phép đo độ trôi. [Lưới xác thực](../../outputs/m2_dimension_epoch_search/20261104_v2/ket_qua_tim_kiem.json) |
| **Tốc độ học 0,01, biên 1,0 và chuẩn hóa vector thực thể** | Giữ các điều kiện của lượt dò để kết quả chọn số chiều và số vòng có cùng cơ sở so sánh. Giá trị 0,01 quy định độ lớn bước cập nhật, còn biên 1,0 đặt khoảng cách mong muốn giữa năng lượng bộ ba dương và âm. Chuẩn hóa thực thể kiểm soát thang vector. Các giá trị này được giữ cố định trong lưới và chưa được tối ưu riêng trên V3.1. Trường `batch_size=32` dùng cho tương thích cấu hình. Bộ tối ưu hiện cập nhật theo từng bộ ba. [Thiết kế tìm kiếm](../../outputs/m2_dimension_epoch_search/20261104_v2/thiet_ke_tim_kiem.json) · [Cài đặt mô hình](../../src/kge/model.py) |
| **Seed 13, 37 và 101, huấn luyện từ đầu** | Giao thức cố định bộ seed để có ba lần khởi tạo trên cùng dữ liệu và cặp seed tương ứng khi so sánh theo thời gian. Các checkpoint của snapshot trước không được dùng để khởi tạo snapshot sau, nhờ vậy lịch sử huấn luyện không thay đổi giữa các mốc. Mỗi tổ hợp chạy lặp với chính seed đó để kiểm tra tái lập trong cùng môi trường. [Giao thức](../../configs/protocol_v1.yaml) · [Bản đăng ký](../../outputs/m2_backbone_v31/20261110_dang_ky_v1/dang_ky.json) |
| **Mẫu âm từ chính snapshot** | Thay thực thể đầu hoặc cuối rồi loại các bộ ba dương đã biết của cùng snapshot. Bộ lọc giới hạn thông tin ở đồ thị tương ứng. Mẫu âm còn lại được hiểu là bộ ba chưa có trong snapshot, vì đồ thị có thể chưa đầy đủ. [Cài đặt lấy mẫu](../../src/kge/model.py) |

Lượt chọn dùng thứ hạng xác thực, không dùng độ trôi, kết quả hỏi đáp hay hệ số H1. Tập xác thực đã phục vụ chọn cấu hình. Các snapshot có thể lặp lại bộ ba qua thời gian, nên chênh lệch MRR được báo cáo mô tả, không xem 10 snapshot là 10 mẫu độc lập.

### 16.2 Trình tự và tiêu chí kiểm tra trước khi xem kết quả

1. **Khóa đầu vào của lượt phát triển.** Đối chiếu 10 Parquet và tệp đi kèm với bản phát hành và hồ sơ kiểm tra đầu vào. Kiểm tra cutoff tăng dần và đọc cột `evidence_observed_at` của toàn bộ 6.638 dòng. Các mốc đều có múi giờ và không vượt cutoff. Tổng 6.638 đếm theo từng snapshot, bao gồm dữ kiện xuất hiện ở nhiều mốc. Lưu mã băm dữ liệu, cấu hình, mã chạy và ánh xạ thực thể, quan hệ. Phạm vi kiểm tra thời gian là giá trị đã ghi trong gói Parquet. Chứng nhận ánh xạ lịch sử và nguồn bằng chứng gốc thuộc G1/G2. [Dấu vết đầu vào](../../outputs/m2_backbone_v31/20261110_dang_ky_v1/dau_vao.json) · [Bản kê đăng ký](../../outputs/m2_backbone_v31/20261110_dang_ky_v1/experiment_manifest.json)
2. **Huấn luyện cùng quy tắc ở mọi mốc.** Với mỗi cặp snapshot–seed, ghi loss trực tuyến từng epoch, số bộ ba, số mẫu âm hợp lệ, số lần bỏ qua và số cặp vi phạm biên. Loss là tổng \(\max(0, 1 + E_{dương} - E_{âm})\) của các cặp được chấm tại lúc cập nhật, chia cho số bộ ba dương của epoch. Loss có thể dao động vì thứ tự và mẫu âm thay đổi qua mỗi vòng. Kiểm tra đủ 85 epoch và mỗi bộ ba có một mẫu âm hợp lệ. [Mã huấn luyện](../../src/kge/trainer.py) · [Định nghĩa loss và bộ đếm](../../src/kge/model.py)
3. **Đọc và kiểm chứng checkpoint sau khi lưu.** Kiểm tra SHA-256, cấu hình theo seed, tập định danh thực thể và quan hệ, số chiều, giá trị hữu hạn, mẫu số loss và sự nhất quán giữa nhật ký với bộ ba trong Parquet. Hai lần chạy cùng seed phải trùng byte. Đây là kiểm tra tái lập trên cùng mã và môi trường. Mức biến thiên giữa các seed khác nhau được dành cho công đoạn nhiễu cùng snapshot sau khi căn chỉnh. [Trình kiểm chứng](../../scripts/run_m2_backbone_v31.py) · [Kiểm tra checkpoint độc lập](../../scripts/verify_m2_backbone.py)

### 16.3 Kết quả và bằng chứng kiểm chứng

| Kiểm tra | Kết quả quan sát |
| --- | --- |
| Dữ liệu và dấu vết | Đối chiếu **63 mã băm đầu vào**, gồm 37 tệp V3.1 đã gắn trong kiểm tra đầu vào, các hồ sơ chọn cấu hình và mã chạy. Kiểm lại **142 tệp đầu ra**, gồm checkpoint, tệp SHA-256, ánh xạ, cấu hình và bản lưu mã. Bản kê ghi commit `eadf22abc436dcbe2f12ae850ed9a5e4382dc714`, trạng thái cây làm việc có thay đổi và mã băm từng tệp liên quan. |
| Hoàn thành và tái lập | **30/30 tổ hợp**, **60 lần huấn luyện từ đầu** tính cả lượt lặp. Có **30/30 cặp checkpoint trùng từng byte**, bao gồm vector và nhật ký. Bộ kiểm chứng chạy sau huấn luyện từ tệp lưu và Parquet. |
| Số vòng và lấy mẫu | **2.550 epoch** ở 30 checkpoint chính, **5.100** nếu tính cả lượt lặp. Nhật ký chính ghi **1.692.690 mẫu âm hợp lệ**, bằng tổng số bộ ba dương qua các epoch. Số mẫu âm bỏ qua bằng **0**. Đã đối chiếu số đếm và công thức loss với nhật ký; các cặp âm và trạng thái vector tại từng lần cập nhật không được lưu để chấm lại toàn bộ SGD. |
| Tính nhất quán của vector | Tất cả vector hữu hạn, đủ 64 tọa độ, đầy đủ thực thể và quan hệ theo từng snapshot. Ánh xạ trùng giữa các seed. Chuẩn L2 của vector thực thể nằm trong khoảng \([0{,}9999999999999994;\ 1{,}0000000000000007]\), phù hợp với chuẩn hóa trong sai số số học. |
| Kiểm thử mã | **689 kiểm thử đạt**, **10 bỏ qua**. Ruff và kiểm tra khoảng trắng Git đạt. Đã thử lại với đường dẫn kết quả đã tồn tại và xác nhận lệnh bị từ chối, mã băm bản kê giữ nguyên. Lượt huấn luyện và xác minh dùng Python 3.11.9, PyArrow 23.0.0. |

[Bản kê lượt huấn luyện](../../outputs/m2_backbone_v31/20261110_huan_luyen_v1/experiment_manifest.json) · [Biên nhận kiểm chứng](../../outputs/m2_backbone_v31/20261110_kiem_chung_v1/kiem_chung.json) · [Nhật ký loss](../../outputs/m2_backbone_v31/20261110_kiem_chung_v1/loss_theo_epoch.json)

Loss trung bình đều qua 30 tổ hợp giảm từ **0,99811** tại vòng 1 xuống **0,45350** tại vòng 50 và **0,20296** tại vòng 85, tương ứng giảm **79,7%** từ vòng 1 đến 85. Cả **30/30 tổ hợp** có loss cuối thấp hơn loss đầu. Loss này cho biết mục tiêu tối ưu trên dữ liệu huấn luyện giảm. Bằng chứng về dự đoán liên kết giữ riêng là MRR và Hits@k ở mục 15. MRR xác thực **0,11846** được dùng để chọn cấu hình trong lưới và không phải điểm kiểm thử độc lập. Hai snapshot T06 và T07 thấp hơn đối chứng tần suất ở cấu hình đã chọn, nên ưu thế xác thực thay đổi theo snapshot.

![Loss huấn luyện theo snapshot và seed](../../outputs/m2_backbone_v31/20261110_bao_cao_v1/mat_mat_huan_luyen_theo_snapshot.png)

[Bản kê biểu đồ](../../outputs/m2_backbone_v31/20261110_bao_cao_v1/experiment_manifest.json)

Để tái lập quy trình từ thư mục gốc, dùng tên đích mới cho từng công đoạn. Bốn lệnh tương ứng với đăng ký, chạy, kiểm chứng và vẽ biểu đồ.

```powershell
$goc_m2 = "outputs/m2_backbone_v31"
.venv-m1/Scripts/python.exe scripts/run_m2_backbone_v31.py register "$goc_m2/tai_lap_dang_ky"
.venv-m1/Scripts/python.exe scripts/run_m2_backbone_v31.py train "$goc_m2/tai_lap_dang_ky" "$goc_m2/tai_lap_huan_luyen" --workers 6
.venv-m1/Scripts/python.exe scripts/run_m2_backbone_v31.py verify "$goc_m2/tai_lap_huan_luyen" "$goc_m2/tai_lap_kiem_chung"
python scripts/report_m2_backbone_v31.py "$goc_m2/tai_lap_kiem_chung" "$goc_m2/tai_lap_bao_cao"
```

### 16.4 Phạm vi kết luận và bằng chứng cần có ở các công đoạn kế tiếp

Lượt mô hình nền đạt **IMPLEMENTED / TESTED / EXECUTED / VERIFIED trong phạm vi phát triển V3.1**. Bàn giao 30 checkpoint chính có tên `seed_<seed>_repeat_1.json`. Tệp `repeat_2` là đối chứng tái lập của cùng seed. Cổng G3 còn cần chẩn đoán căn chỉnh trên checkpoint mới. Các điều kiện chứng nhận G1/G2 và khóa W7 vẫn theo hồ sơ riêng. [Trạng thái khoa học của dự án](TRANG_THAI_TOAN_DU_AN_20261104.md)

| Công đoạn | Câu hỏi cần trả lời | Bằng chứng phải lưu |
| --- | --- | --- |
| Căn chỉnh Procrustes | Phép xoay có xác định được và có áp dụng tốt cho thực thể ngoài tập dùng để khớp? | Danh sách và mã băm neo khớp và giữ riêng, hạng, phổ giá trị kỳ dị, sai số trực giao, phần dư và khoảng chênh giữa hai tập. Chốt quy tắc và ngưỡng từ hồ sơ có thẩm quyền trước khi chạy. |
| Nhiễu cùng snapshot | Cùng đồ thị mà đổi seed tạo ra mức dao động bao nhiêu? | Các cặp theo giao thức, số quan sát theo nhóm, trung vị, MAD và kiểm tra loại chính thực thể đang được đánh giá khỏi tập tham chiếu. |
| Độ trôi và đối chứng | Chênh lệch qua thời gian còn bao nhiêu sau khi tham chiếu mức nhiễu? | Dịch chuyển thô, phần vượt nhiễu có dấu, SED+ và phép đối chứng độ trôi giả từ huấn luyện lại cùng snapshot. |

Điểm dừng của lượt này là kiểm chứng mô hình nền. Hồ sơ đăng ký phép đo M2 còn 12 điều kiện mở theo lượt rà soát gần nhất, gồm khác biệt ngưỡng trực giao giữa quyết định và cấu hình ứng viên. [Kết quả rà soát phép đo](TRANG_THAI_TOAN_DU_AN_20261104.md)

## 17. Phân tích trước khi căn chỉnh Procrustes trên V3.1 — 2026-11-10

### 17.1 Vai trò của căn chỉnh trong phép đo

Hai lần huấn luyện TransE-L2 có thể dùng các hệ trục khác nhau. Nếu cùng nhân các vector thực thể và quan hệ với một ma trận trực giao, chuẩn L2 của tổng \(h+r-t\) được bảo toàn. Vì vậy, khác biệt tọa độ giữa hai checkpoint có thể xuất hiện ngay cả khi điểm bộ ba không đổi. Procrustes trực giao tìm phép biến đổi tối thiểu hóa sai số bình phương giữa các cặp neo. Trong thiết kế M2, lấy trung bình của **tập neo khớp** tại hai đầu, định tâm hai ma trận neo và phân rã \(X_c^\top Y_c=U\Sigma V^\top\) để lấy \(Q=UV^\top\). Tập neo giữ riêng dùng đúng hai trung bình và \(Q\) đã khớp. [Đề cương, phương trình (12)–(24)](<../../sources/huce_evolving_kg_modular_proposal(8).pdf>) · [Schönemann, 1966](https://doi.org/10.1007/BF02289451)

Đề tài đã chọn cosine affine, tức là so sánh \((x-\mu_{nguồn})Q+\mu_{đích}\) với \(y\) khi đo độ dịch chuyển. Đây là quyết định về cách chấm sau căn chỉnh. Định tâm khi khớp \(Q\) vẫn dùng tập neo khớp. Neo tồn tại ở hai mốc vẫn có thể thay đổi cấu trúc. Vì vậy kết quả độ trôi sẽ được hiểu theo hệ quy chiếu của tập neo, và cần nhiễu cùng snapshot để diễn giải. [Quyết định ngày 28/10 về cosine](../../decisions/decision_log.jsonl#L8)

### 17.2 Bằng chứng khả thi trước khi nhìn hình học mới

- **Đầu vào.** Đối chiếu lại 142 tệp của lượt mô hình nền với bản kê. Kiểm đủ 30 checkpoint chính từ T01 đến T10 với seed 13, 37, 101 và cấu hình 64 chiều, 85 vòng. Ánh xạ khớp với Parquet chuẩn V3.1. Cả ba nguồn khoa học hiện hành khớp SHA-256 trong khóa nguồn và giao thức, sau `AMEND-2026-001`. [Biên nhận đầu vào](../../outputs/m2_alignment_v31_readiness/20261110_v1/kiem_tra_truoc_can_chinh.json) · [Amendment nguồn](../../amendments/AMEND-2026-001.yaml)
- **Neo lịch sử.** Tái lập độc lập **9/9** bộ neo theo bậc tại snapshot trước từ định danh chuẩn và Parquet. Mỗi bộ đủ **101 neo khớp và 66 neo giữ riêng**, hai tập rời nhau. Quần thể chung nhỏ nhất là **167** ở T01→T02 nên thiết kế dùng toàn bộ ứng viên của cặp đầu. Cặp cuối có **1.282** ứng viên, còn **1.115** thực thể ngoài cả hai tập neo. Ở cả chín cặp, **73–79/101** neo khớp và **48–52/66** neo giữ riêng có bậc 1. Việc khớp đúng theo bậc cho thấy thiết kế cũ tái lập được. Độ phủ nhóm bậc hiếm của tập giữ riêng và việc bổ sung tần suất cần xem khi chốt thiết kế khoa học. [Hồ sơ 9 chuyển tiếp](../../outputs/m2_alignment_v31_readiness/20261110_v1/kiem_tra_truoc_can_chinh.json)
- **Ma trận so sánh.** Có **27 phép qua thời gian** (ba seed ghép cùng seed ở mỗi cặp snapshot kề nhau) và **54 phép cùng snapshot** (ba cặp seed ở mỗi đầu của từng chuyển tiếp). Cả chín phép trong một chuyển tiếp dùng cùng bộ neo để giữ điều kiện căn chỉnh nhất quán. Với snapshot ở giữa chuỗi, một cặp seed có thể xuất hiện ở hai chuyển tiếp với bộ neo khác nhau. Tổng 54 phép cùng snapshot dùng 30 bộ định danh snapshot–cặp seed khác nhau. Các phép này dùng để hiệu chỉnh nhiễu, có sự phụ thuộc do dùng chung checkpoint. Chiều seed được cố định theo thứ tự \(s<s'\) như công thức (27), vì cosine sau biến đổi affine có thể phụ thuộc chiều. [Đề cương, phương trình (26)–(28)](<../../sources/huce_evolving_kg_modular_proposal(8).pdf>) · [Mã lập danh sách so sánh](../../scripts/run_m2_alignment.py)

Về số lượng, 101 hàng neo sau định tâm cho hạng tối đa \(\min(101-1,64)=64\). Điều đó làm 64 chiều khả thi về cấu trúc. Hạng thực tế phụ thuộc phổ giá trị kỳ dị của từng cặp checkpoint. Điều kiện tỷ lệ 90% tương ứng tối thiểu **58/64** chiều có hạng số theo quy tắc đếm đã chốt. Cần lưu cả phổ và hạng để đọc được các chiều yếu. Tập 66 neo giữ riêng kiểm tra việc áp dụng phép căn chỉnh lên định danh ngoài tập khớp; các neo này vẫn nằm trong dữ liệu đã huấn luyện TransE.

### 17.3 Pilot cũ và các điều kiện cần chốt

Đã tổng hợp lại từ 81 bản ghi pilot dùng checkpoint **50 vòng**. Hạng số đều là **64/64** với dung sai tương đối khi đếm hạng \(10^{-6}\). Phần dư tương đối trên neo giữ riêng nằm trong **1,2533–1,3940**, khoảng chênh tuyệt đối giữa phần dư hai tập trong **0,4558–0,5651**. Sai số trực giao chuẩn hóa lớn nhất là **\(3,43\times10^{-16}\)**. Trung vị phần dư giữ riêng là **1,3627** ở cặp qua thời gian và **1,3706** ở cặp cùng snapshot. Phần dư được chia cho độ lớn của vector đích đã định tâm bằng trung bình tập khớp. Giá trị 1 tương ứng với mốc diễn giải dự đoán mọi vector bằng trung bình đích; đây là mốc tham chiếu để đọc thang đo. Các giá trị pilot cho thấy phép căn chỉnh có thể trực giao tới sai số số học trong khi sai lệch trên neo giữ riêng vẫn đáng kể. Pilot chỉ cung cấp bối cảnh cho ngưỡng và không xác nhận kết quả của checkpoint 85 vòng. [Bản ghi pilot](../../outputs/m2_alignment_pilot_run/m2_alignment_pilot_statistics_v2.json) · [Tổng hợp lại theo loại so sánh](../../outputs/m2_alignment_v31_readiness/20261110_v1/kiem_tra_truoc_can_chinh.json)

| Phát hiện | Bằng chứng và ảnh hưởng | Việc cần chốt trước khi xem kết quả 85 vòng |
| --- | --- | --- |
| **M2-ALIGN-01 · GOVERNANCE. Ngưỡng trực giao có hai giá trị** | Đề cương ở cổng Geometry/Path, hai cấu hình ứng viên và mục tiến độ 28/10 ghi \(10^{-6}\) cho \(\lVert Q^\top Q-I\rVert_F/d\). Quyết định `d_diag_g3_thresholds_20261028` ghi \(10^{-5}\) cho cùng chỉ số. Kế hoạch v1.0 yêu cầu G3 dùng khoảng vận hành khóa từ pilot nhưng không ghi số để giải quyết khác biệt này. | Xác nhận hiệu lực của hai ngưỡng theo phạm vi cổng. Đề xuất lấy \(10^{-6}\) theo đề cương nếu dùng một ngưỡng chung và chưa có hồ sơ phê duyệt thay ngưỡng đề cương. Nếu giữ \(10^{-5}\) riêng cho G3, cần ghi rõ quan hệ với tiêu chí Geometry/Path. Giữ ngưỡng phần dư giữ riêng **1,50**, khoảng chênh tuyệt đối **0,65** và tỷ lệ hạng **0,90** từ quyết định 28/10. [Quyết định](../../decisions/decision_log.jsonl#L9) · [Cấu hình phép đo](../../configs/m2_measurement_v2_candidate.yaml) |
| **M2-ALIGN-02 · HIGH. Quy tắc phân tầng còn thiếu định nghĩa tần suất** | Đề cương dùng cả \(\log(1+\mathrm{bậc})\) và \(\log(1+\mathrm{tần\ suất})\) ở snapshot nguồn. Bộ neo tái lập ở trên phân tầng chỉ theo bậc. Cấu hình ứng viên để `frequency_definition: null`. | Chốt đơn vị đếm, bảng bằng chứng, khóa chống đếm trùng và mốc as-of. Một phương án để thẩm định là đếm số bài nguồn phân biệt có bằng chứng đã quan sát cho thực thể tại cutoff nguồn. Cần kiểm tra khả năng nối nguồn và phân bố trước khi dùng. Nếu phạm vi được duyệt chỉ là chạy phát triển với neo cũ theo bậc, ghi rõ phạm vi đó. [Đề cương, mục 3.2.2](<../../sources/huce_evolving_kg_modular_proposal(8).pdf>) · [Cấu hình ứng viên](../../configs/m2_data_3_1_candidate_v2.yaml#L61) |
| **M2-ALIGN-03 · HIGH. Tham số và đầu vào chưa được đăng ký cho lần chạy mới** | Giao thức còn chỗ trống ở số chiều và số neo. Dung sai đếm hạng tương đối \(10^{-6}\) đã dùng trong pilot. Sàn mẫu số phần dư \(10^{-12}\) là giá trị ứng viên. Trình căn chỉnh cũ gắn với backbone lịch sử và dùng RMSE, chuẩn trực giao thô cùng quy tắc hạng khác. | Đăng ký thiết kế riêng cho V3.1 và 30 checkpoint mới, gồm nguồn của bộ neo, dung sai hạng, cách xử lý mẫu số suy biến và các ngưỡng trên đúng thang đo. Kiểm tra độc lập các phép tính và không trộn quy tắc v1 với chỉ số v2. [Giao thức](../../configs/protocol_v1.yaml#L28) · [Mã chẩn đoán v2](../../src/drift/measurement_v2.py#L78) |

Các phát hiện tái lập bằng cách đối chiếu nguồn, bản kê, quy tắc chia neo và thống kê pilot đã lưu trong [mã kiểm tra](../../outputs/m2_alignment_v31_readiness/20261110_v1/kiem_tra.py). Hồ sơ phép đo v2 hiện báo **12 điều kiện mở**. Một số thuộc nhiễu và chuẩn hóa ở công đoạn sau, ví dụ quy tắc gộp nhóm, MAD và epsilon. Chúng cần cho phép đo đầy đủ. Đăng ký của riêng lượt căn chỉnh cần xác định neo, phép khớp, chẩn đoán và trạng thái bàn giao trước.

### 17.4 Trình tự đề xuất và điểm dừng

1. Hòa giải ngưỡng trực giao và chốt thiết kế neo từ nguồn có thẩm quyền. Đăng ký đầu vào và mã băm của cả 9 bộ neo, 30 checkpoint chính, 81 phép so sánh và quy tắc đánh giá trước khi tính SVD.
2. Chạy riêng lượt căn chỉnh. Lưu \(Q\), hai trung bình trên neo khớp, phổ giá trị kỳ dị, hạng, hai phần dư tương đối, tử số và mẫu số của chúng, chênh lệch có dấu và tuyệt đối, sai số trực giao thô và chuẩn hóa. Lưu riêng lý do khi phép căn chỉnh không khả dụng.
3. Đọc lại tệp và tính độc lập từ vector với NumPy. Kiểm tính rời nhau và mã băm của neo, chiều nguồn–đích, nghiệm tối ưu trên tập khớp và phần dư giữ riêng. Tổng hợp riêng cặp qua thời gian và cặp cùng snapshot. Khi có trường hợp không đạt, giữ bằng chứng và báo rõ ảnh hưởng đến phép đo thay vì điều chỉnh tiêu chí sau khi thấy kết quả.

**Đã thực hiện và xác minh trong phạm vi rà soát trước khi chạy.** Bản kê gắn **125 mã băm đầu vào**. Có **88 kiểm thử liên quan đạt**, gồm nghiệm đã biết, tách neo, hạng suy biến và điều kiện không khả dụng. Các con số về hình học ở mục 17.3 thuộc pilot 50 vòng. Lượt 85 vòng vẫn ở điểm dừng đăng ký. Kết luận G3 còn phụ thuộc cả căn chỉnh và kiểm tra nhiễu theo giao thức. [Bản kê rà soát](../../outputs/m2_alignment_v31_readiness/20261110_v1/experiment_manifest.json) · [Tiêu chí G3](../gates_and_freeze.md)

```powershell
.venv-m1/Scripts/python.exe scripts/search_m2_dimension_epochs.py outputs/m2_dimension_epoch_search/tai_lap_01 --workers 5
python scripts/report_m2_dimension_epochs.py outputs/m2_dimension_epoch_search/tai_lap_01 outputs/m2_dimension_epoch_search_report/tai_lap_01
```

## 18. Xác nhận thiết kế và kiểm tra bằng chứng bài nguồn cho bộ neo — 2026-11-10

### 18.1 Hai lựa chọn đã xác nhận

- **Trực giao.** Dùng ngưỡng chung **\(10^{-6}\)** cho \(\lVert Q^\top Q-I\rVert_F/d\) ở lượt căn chỉnh checkpoint V3.1 85 vòng, theo đề cương. Quyết định mới giải quyết phần trực giao ghi **\(10^{-5}\)** trong quyết định ngày 28/10 cho phạm vi lượt mới. Nhật ký bổ sung theo kiểu ghi nối tiếp, có bản sao nguyên byte của phần lịch sử trước khi bổ sung. [Nhật ký quyết định](../../decisions/decision_log.jsonl) · [Bản ghi lựa chọn](../../outputs/m2_anchor_article_readiness/20261110_v1/lua_chon_da_xac_nhan.json)
- **Tần suất.** Dùng đồng thời bậc và số **bài nguồn phân biệt có bằng chứng cho thực thể đã được quan sát đến cutoff của snapshot nguồn**. Điều kiện nghiệm thu dữ liệu là truy được từng bài về bản nguồn và đoạn trích có thời điểm quan sát và căn cứ xác định thời điểm. Đếm một lần theo cặp thực thể–bài sau khi áp dụng điều kiện cutoff. Nhiều lần thu, nhiều đoạn trích hoặc nhiều phiên bản đủ điều kiện của cùng bài vẫn là một bài đối với thực thể đó. [Bản ghi lựa chọn](../../outputs/m2_anchor_article_readiness/20261110_v1/lua_chon_da_xac_nhan.json)

### 18.2 Kết quả đối chiếu trên V3.1

1. **Đối chiếu dữ kiện.** Đọc hai bản snapshot cho từng cutoff và đối chiếu với kho `fact_versions`. Bản đầy đủ và bản canonical có cùng tập bộ ba. Bản đầy đủ giữ được nhiều phiên bản dữ kiện cùng bộ ba, ví dụ **127 phiên bản cho 121 bộ ba tại T01**. Có đủ **1.803 phiên bản dữ kiện** trong hợp của 10 bản đầy đủ. Mọi mốc quan sát đã ghi của các hàng thuộc snapshot đều không vượt cutoff. Đây là kiểm tra phép chiếu và giá trị lưu, còn căn cứ quan sát cần gắn với từng bài nguồn. [Biên nhận theo snapshot](../../outputs/m2_anchor_article_readiness/20261110_v1/kiem_tra_bai_nguon.json)
2. **Thử khóa bài nguồn.** Từ `fact_versions.source_id` nối đến `body_variants`, `document_memberships`, `retrievals` và `source_versions`. Kiểm tra mã băm raw và sự nhất quán giữa địa chỉ của lần thu và phiên bản nguồn. Trên nhánh có metadata thu đã xác minh, dùng cặp **nguồn xuất bản–mã bài** lấy từ đường dẫn gốc của hai báo, bóc lớp Wayback khi có. Trong **994 phiên bản thân bài**, có **70** nối tới hơn một URL thô. Sau chuẩn hóa, **18** thân bài vẫn nối tới hơn một mã bài. Có **683 khóa bài ứng viên** và **332** khóa nối tới nhiều phiên bản thân bài. Kết quả cho thấy đếm URL hoặc đếm thân bài sẽ sai đơn vị. Các số này mô tả đường nối, chưa phải tần suất đủ điều kiện theo cutoff. [Bằng chứng kiểm tra khóa bài](../../outputs/m2_anchor_article_readiness/20261110_v1/kiem_tra_bai_nguon.json)
3. **Kiểm tra đoạn trích và thời điểm.** Đọc 994 thân bài theo mã băm của gói và tính lại SHA-256 của đúng đoạn Unicode theo offset. Chỉ **15/1.803** phiên bản dữ kiện khớp hash đoạn trích. T01–T06 có **0** phiên bản đạt kiểm tra này, kể cả khi dùng bản snapshot đầy đủ. Từ T07 trở đi, 15 phiên bản khớp chỉ liên quan đến **28 thực thể**. Bản kê gói không có `claim_provenance`, `snapshot_edge_support` hoặc `entity_mapping_versions`. `source_versions` lưu mốc thu và mốc lưu trữ. Gói hiện thiếu căn cứ đã xác minh để gán một `evidence_observed_at` cho từng cặp bằng chứng–bài, đặc biệt ở 18 thân bài có nhiều mã bài. Do đó không chuyển mốc thu hoặc mốc lưu trữ thành thời điểm quan sát và không gán một timestamp của FactVersion cho mọi bài nối được. [Mã kiểm tra đoạn trích và thời điểm](../../outputs/m2_anchor_article_readiness/20261110_v1/kiem_tra.py) · [Rà soát bằng chứng M1 V3.1](M1_V3_1_INTAKE_REVIEW_20261021.md)

### 18.3 Điều kiện bàn giao để đăng ký bộ neo

**Phát hiện M2-ALIGN-04 · HIGH.** Đã xác nhận đường nối từ dữ kiện đến URL ứng viên, đồng thời xác nhận thiếu bằng chứng đạt yêu cầu ở cấp bài và đoạn trích. Nguyên nhân xác minh được là trường hash của phần lớn dữ kiện khớp thân bài trong lần rà soát M1 trước, còn không khớp đoạn đã khai báo khi tính lại. Gói chưa đủ để chứng minh từng bài nối được đã cung cấp đúng bằng chứng trước cutoff. Chưa có căn cứ xác định lỗi tạo hash nằm ở hàm producer nào. [Phát hiện gốc M1-V31-002](M1_V3_1_INTAKE_REVIEW_20261021.md) · [Bản kê kiểm tra](../../outputs/m2_anchor_article_readiness/20261110_v1/experiment_manifest.json)

Hồ sơ tối thiểu cần bổ sung là bảng truy vết có mã bài chuẩn, phiên bản nguồn, định danh thực thể hoặc dữ kiện, mã băm thân bài và đoạn trích, thời điểm quan sát có múi giờ, căn cứ xác định thời điểm và bằng chứng ánh xạ có hiệu lực tại cutoff. Cần kiểm chứng các trường hợp một bài có nhiều phiên bản, một thân bài nối nhiều mã bài, bằng chứng đúng cutoff và bằng chứng sau cutoff trước khi sinh tần suất. Bảng bổ sung phải có phiên bản và bản kê đầu vào. Nếu bằng chứng bổ sung khớp định danh và bộ ba canonical hiện tại, có thể dùng cho phân tầng mà vẫn dùng checkpoint hiện có. Nếu phát hiện thay đổi tập bộ ba hoặc ánh xạ, đánh giá ảnh hưởng trước khi chọn phạm vi cần chạy lại. [Đặc tả truy vết](../data_pipeline_spec.md) · [Hợp đồng bảng dữ liệu](../../config/schema.yaml)

**Mức xác minh đạt được là EXECUTED / VERIFIED cho rà soát chỉ đọc** trên **1.068 mã băm đầu vào**. Trạng thái bộ neo là **chưa đủ điều kiện đăng ký**. Kết quả dừng ở hồ sơ kiểm tra, trước khi tính tần suất chính thức, chọn neo hoặc tính SVD. [Bản kê và đầu ra rà soát](../../outputs/m2_anchor_article_readiness/20261110_v1/experiment_manifest.json)

Khi đối chiếu lại hồ sơ mục 17, dùng bản sao nhật ký trước khi bổ sung cho mã băm lịch sử của `decision_log.jsonl`. Đã kiểm tra bản sao khớp mã băm cũ và khớp từng byte với phần đầu của nhật ký hiện tại. [Nhật ký lịch sử đã lưu](../../outputs/m2_anchor_article_readiness/20261110_v1/quyet_dinh_truoc_bo_sung.jsonl)

## 19. Khôi phục hồ sơ truy vết bài nguồn từ kho M1 gốc — 2026-11-10

Đã tìm thấy kho M1 gốc tại `../evolving-kg-drift-m1/evolving-kg-drift`. Nhận định ở mục 18 áp dụng cho gói phát hành V3.1. Lượt này mở rộng phạm vi đối chiếu sang kho gốc đã có, với quyền chỉ đọc. Các kết quả được lưu thành hồ sơ bổ sung có bản kê riêng.

### 19.1 Phạm vi và trình tự

1. **Khóa đúng dữ liệu bàn giao.** Đối chiếu theo SHA-256 các tệp Parquet của `production_v3` với V3.1, gồm 10 snapshot canonical và các bảng dùng để truy vết. Chỉ giữ các blob đã được tham chiếu bởi phiên bản dữ kiện trong V3.1. Bản kê SHA-256 của kho gốc ghi đường dẫn tương đối theo đúng kho chứa blob. [Bản kê blob của bản phát hành](../../data/evolving_kg_downstream_v3_1/inputs/raw_blob_reference_manifest.json)
2. **Khôi phục đường nối và đoạn trích.** Lấy ID claim từ hậu tố của `fact_version_id` theo quy tắc trong mã nguồn đã lưu, rồi kiểm tra lại thân bài, quan hệ, offset và mã băm cũ. Nối claim → thân bài → lần thu → bài xuất bản → dòng nhật ký. Xác minh tệp HTML gốc và tái tạo văn bản thân bài. Lưu mã băm đoạn Unicode tính lại song song với giá trị cũ để truy vết. Việc tính lại hash chứng minh lát cắt văn bản khôi phục được. Việc xác nhận lát cắt thực sự hỗ trợ quan hệ là bước kiểm tra nội dung riêng.
3. **Tách các đồng hồ.** Lưu mốc nhà xuất bản khai báo, mốc thu thật, mốc bản lưu và giá trị `evidence_observed_at` đã ghi trong FactVersion. Với Wayback, kiểm tra URL gốc, mốc trong URL replay, header `Memento-Datetime`, mốc trong log và SHA-256 của nội dung. Đây là chứng cứ cho phiên bản được lưu tại mốc đó. Quyết định Stage 4.3 về thời gian replay thuộc khâu phát hiện nguồn. Chuẩn hóa thời điểm quan sát cấp bài để đếm tần suất thuộc Stage 4.10 và cần quy tắc cùng căn cứ đã chốt. [Đặc tả thời gian](../data_pipeline_spec.md) · [Quyết định Stage 4.3](../../decisions/decision_log.jsonl#L3)

### 19.2 Kết quả và giới hạn sử dụng

| Kiểm tra | Kết quả xác minh |
| --- | --- |
| Đồng nhất với V3.1 | **17/17 tệp Parquet khớp SHA-256**, gồm 7 bảng phục vụ truy vết và 10 snapshot canonical. Các bảng có cùng dữ liệu là căn cứ nối hồ sơ M1 về đúng gói đã huấn luyện. |
| HTML và lần thu | **1.074/1.074 HTML** khớp SHA-256 và tái tạo đúng thân bài. Đã xác minh **1.094 bản ghi thu** trong **23 nhật ký** theo mã băm, số dòng, địa chỉ và mã băm HTML. Trong đó, **516/516 bản ghi Wayback** khớp mốc trong URL replay, header và log, đồng thời tái tạo đúng thân bài. |
| Đoạn trích | Nối được **1.803/1.803 FactVersion** tới claim theo ID. Hash cũ của cả 1.803 hàng khớp thân bài, trong khi **15/1.803** khớp đoạn theo offset. Đã lưu cả hash tính lại và hash cũ trong bảng mới. Có **799/1.803** đoạn chứa cả hai tên thực thể theo so khớp chuỗi. Đây là kiểm tra hình thức để hỗ trợ rà nội dung. |
| Đồng hồ trong dữ liệu cũ | Tái lập đúng **1.803/1.803** giá trị đã ghi bằng logic thân bài của mã nguồn M1 tìm được. Có **851** hàng khớp `archive_datetime` và **952** hàng khớp `retrieved_at_real`. Phép tái lập giải thích nguồn gốc của số liệu cũ. Hai loại mốc được giữ riêng trong bảng truy vết. |
| Định danh thực thể | Tái lập được cả hai mã thực thể từ hai mention cho **1.803/1.803** dữ kiện bằng quy tắc băm đã thấy trong mã M1. Trong **1.389 mã** quan sát được, không có mã chung giữa hai chuỗi mention khác nhau sau chuẩn hóa của phép kiểm này. Hồ sơ ánh xạ lịch sử có thời điểm hiệu lực vẫn còn thiếu. |

[Bảng truy vết Parquet](../../outputs/m2_anchor_article_recovery/20261110_v1/bang_truy_vet_ung_vien.parquet) · [Kết quả phục hồi](../../outputs/m2_anchor_article_recovery/20261110_v1/ket_qua.json) · [Biên nhận kiểm chứng độc lập](../../outputs/m2_anchor_article_recovery/20261110_kiem_chung_v1/bien_nhan_kiem_chung.json)

Bảng gồm **1.958 dòng** ở cấp FactVersion–membership–lần thu. Một dữ kiện có thể có nhiều dòng. Khi có dữ liệu đủ điều kiện, phép đếm tần suất phải áp dụng cutoff trước rồi gộp theo thực thể–mã bài. Bảng truy vết hiện giữ hai trường thời điểm đã xác minh ở dạng timestamp UTC với giá trị trống và gắn lý do cho từng dòng. Trạng thái này phản ánh phần bằng chứng cấp bài và ánh xạ còn cần chuẩn hóa. [Lược đồ và trạng thái trong bản kê](../../outputs/m2_anchor_article_recovery/20261110_v1/experiment_manifest.json)

Độ phủ sau đây chỉ đếm các thực thể xuất hiện trong dữ kiện có ít nhất một bản Wayback khớp HTML và được lưu trước hoặc đúng cutoff. Bảng dùng để xác định phần cần bổ sung hồ sơ. Các số này chưa phải tần suất đủ điều kiện cho bộ neo.

| Snapshot | Thực thể có bản Wayback đến cutoff | Tổng thực thể | Số thực thể chưa có bản Wayback đến cutoff |
| --- | ---: | ---: | ---: |
| T01–T06 | Đủ tại từng mốc | 167–936 | 0 tại từng mốc |
| T07 | 971 | 1.057 | 86 |
| T08 | 974 | 1.176 | 202 |
| T09 | 982 | 1.282 | 300 |
| T10 | 986 | 1.389 | 403 |

### 19.3 Bàn giao và điểm dừng

- **Đã thực hiện và xác minh phần khôi phục kỹ thuật.** Bộ kiểm tra độc lập đọc lại Parquet, kiểm đủ ID, tính lại hash đoạn trích, kiểm cột thời gian và trạng thái từng dòng, đối chiếu **1.075 mã băm trong workspace** và **1.118 mã băm từ kho M1 gốc**. Có **17 kiểm thử liên quan đạt**, cùng Ruff toàn kho và kiểm tra khoảng trắng Git. [Bản kê kiểm chứng](../../outputs/m2_anchor_article_recovery/20261110_kiem_chung_v1/experiment_manifest.json) · [Bản kê đường dẫn M1](../../outputs/m2_anchor_article_recovery/20261110_v1/dau_vao_m1.json)
- **Chưa đủ điều kiện tính tần suất hoặc đăng ký bộ neo.** Lượt `production_v3` tìm được vẫn thiếu bản kê run, bảng thời điểm quan sát cấp bài và lịch sử hiệu lực ánh xạ. Bước tiếp theo là làm hồ sơ Stage 4.10 cho hai nhóm bằng chứng gồm bản Wayback khớp đúng phiên bản và bài có lần thu trực tiếp, xác nhận đoạn hỗ trợ quan hệ và gắn thời điểm có hiệu lực cho ánh xạ. Việc chỉ dùng Wayback cần xử lý phần thiếu ở T07–T10 theo quy tắc đã đăng ký. Sau khi có bảng bổ sung đạt điều kiện, đối chiếu lại tập bộ ba và ánh xạ với bản đã huấn luyện để quyết định sử dụng 30 checkpoint hiện có. [Quy tắc về bằng chứng và cutoff](../data_pipeline_spec.md)

## 20. Kiểm tra căn cứ thời gian độc lập theo cutoff — 2026-11-10

### 20.1 Quy tắc đã được chọn

Người dùng chọn **yêu cầu bằng chứng thời gian độc lập cho bài thu trực tiếp**. Ngày công bố hoặc cập nhật phải gắn được với đúng phiên bản chứa đoạn bằng chứng. Dòng thiếu căn cứ giữ trạng thái **chưa xác minh**. Với Wayback, mốc bản lưu đã đối chiếu nội dung cho biết đoạn bằng chứng đã xuất hiện chậm nhất vào lúc bản đó được lưu. Mốc bằng cutoff được chấp nhận trong phép kiểm thời gian. Quy tắc được ghi nối tiếp trong nhật ký trước khi tạo bảng đánh giá. Phạm vi lần này là chuẩn bị và kiểm chứng căn cứ thời gian cho bảng bổ sung. [Quyết định đã ghi](../../decisions/decision_log.jsonl#L14) · [Đặc tả Stage 4.10](../data_pipeline_spec.md)

### 20.2 Phân biệt ngày khai báo với bằng chứng về phiên bản

1. **Đối chiếu HTML và hồ sơ phát hiện bài.** Trong **578 bản thu trực tiếp**, cả 578 ngày công bố và ngày cập nhật trong nhật ký đều tìm thấy trong metadata HTML. Có **69** bản thu có ngày công bố trùng metadata Stage 4.3 và **69** bản có ngày cập nhật trùng metadata đó. Đã đối chiếu **946 quan sát Stage 4.3** theo ID bài. Bảng quan sát thiếu mã băm nội dung cấp bài nên các giá trị trùng xác nhận metadata, còn thời điểm đoạn trích xuất hiện cần chứng cứ phiên bản. Hồ sơ Stage 4.4 v2 khớp **1.090/1.094** bản thu đã kiểm. Bốn bản còn lại truy vết từ nhật ký gốc và HTML đã xác minh. Cả **60** liên kết giữa phiên bản ở Stage 4.4 v2 ghi trạng thái `unknown`. [Kết quả đối chiếu metadata](../../outputs/m2_anchor_temporal_review/20261110_v1/bao_phu_cutoff.json)
2. **Tìm bản lưu cùng thân bài.** Nối theo nguồn xuất bản, mã bài và SHA-256 của văn bản thân bài đã tái tạo. Trong 578 bản thu trực tiếp, **43** có bản lưu cùng bài và cùng thân bài, **331** có bản lưu của cùng bài với thân bài khác trong bảng truy vết ban đầu, **204** không có bản lưu cùng bài trong bảng đó. Cả 43 trường hợp đều có HTML thô khác SHA-256 giữa hai lần thu. Bằng chứng gắn với văn bản thân bài trùng khớp và mốc của bản Wayback. [Bảng căn cứ thời gian cấp bài](../../outputs/m2_anchor_temporal_review/20261110_v1/bang_can_cu_thoi_gian.parquet)
3. **Tìm nguyên văn đoạn trích trong bản lưu khác thân bài.** Với 535 bài còn thiếu bản lưu cùng thân bài, xét **482 bản lưu Stage 4.4 v2** của **453 bài**. Đối chiếu lại nhật ký, URL, header, SHA-256 HTML và thân bài cho các trường hợp trùng đoạn. Tìm được **568 liên kết** cho **545 FactVersion** thuộc **310 bài**, từ **314 HTML bản lưu đã xác minh**. Trong đó có **66 HTML** được tái tạo thân bài lần đầu ở lượt này. Với **9 liên kết** có nhiều vị trí trùng, lưu tất cả offset. Mốc bổ sung thuộc bản Wayback có nguyên văn đoạn trích. Trường ngày của bản thu trực tiếp vẫn được lưu riêng. [Bảng đối chiếu đoạn trích](../../outputs/m2_anchor_temporal_review/20261110_doan_trich_v1/bang_doan_trich_trong_ban_luu_khac.parquet) · [Quy tắc so khớp](../../outputs/m2_anchor_temporal_review/20261110_doan_trich_v1/quy_tac_doi_chieu.json)

### 20.3 Độ phủ khi áp dụng cutoff

Tính số FactVersion, bộ ba và thực thể có ít nhất một căn cứ thời gian đến cutoff. Khi nhiều bản lưu cùng hỗ trợ một FactVersion, lấy mốc sớm nhất đã xác minh. Sau đó hợp tập bộ ba và thực thể trong từng snapshot để tránh đếm lại. Các số dưới đây đo **độ phủ về thời điểm**, trước thẩm định ngữ cảnh và ánh xạ.

| Snapshot | FactVersion có mốc đến cutoff sau bổ sung | FactVersion chưa có mốc | Bộ ba có mốc đến cutoff | Thực thể có mốc đến cutoff trước → sau bổ sung |
| --- | ---: | ---: | ---: | ---: |
| T01–T06 | Đủ tại từng mốc | 0 | Đủ tại từng mốc | Đủ tại từng mốc |
| T07 | 927/1.005 | 78 | 786/844 | 971 → 1.001 trên 1.057 |
| T08 | 1.105/1.261 | 156 | 865/964 | 974 → 1.085 trên 1.176 |
| T09 | 1.258/1.526 | 268 | 932/1.084 | 982 → 1.143 trên 1.282 |
| T10 | 1.425/1.803 | 378 | 1.000/1.205 | 986 → 1.207 trên 1.389 |

Phân loại riêng mốc sau cutoff với trường hợp chưa có mốc. Trong lượt này, toàn bộ số thiếu trong bảng là **chưa có căn cứ xác minh**. Điều đó chưa đủ để kết luận bài vắng mặt ở thời điểm đó. T09 là snapshot nguồn cuối trong chín chuyển tiếp dùng để lập neo. Theo chỉ số thời gian trên toàn snapshot T09, còn **139 thực thể** chưa có mốc. [Độ phủ theo từng cutoff](../../outputs/m2_anchor_temporal_review/20261110_doan_trich_v1/bao_phu_bo_sung.json) · [Phân loại trước khi bổ sung đoạn trích](../../outputs/m2_anchor_temporal_review/20261110_v1/bang_cutoff_fact_version.parquet)

### 20.4 Kiểm chứng và bàn giao

Đã đọc lại **1.958 dòng căn cứ cấp bài**, tính lại mã băm đoạn trích cho **568 liên kết bổ sung** và đối chiếu **8.430 hàng FactVersion–snapshot** ở 10 cutoff. Bài kiểm tra biên xác nhận thời điểm bằng cutoff được tính và thời điểm muộn hơn được tách nhóm, kể cả khi biểu diễn bằng hai múi giờ. Có **17 kiểm thử liên quan đạt**. Mức **EXECUTED / VERIFIED** áp dụng cho bằng chứng thời gian và độ phủ được báo cáo. [Biên nhận kiểm chứng độc lập](../../outputs/m2_anchor_temporal_review/20261110_kiem_chung_v1/bien_nhan_kiem_chung.json)

Điều kiện còn lại trước khi tính tần suất là thẩm định đoạn trích thực sự hỗ trợ quan hệ trong phiên bản tương ứng, xác minh ánh xạ có hiệu lực và xử lý phần thiếu thời gian. Bảng giữ trạng thái đủ điều kiện tính tần suất bằng `false` ở mọi dòng. Phép so khớp nguyên văn giúp khoanh phạm vi thẩm định và ưu tiên các bản đã có bằng chứng thời gian. [Bản kê kiểm chứng](../../outputs/m2_anchor_temporal_review/20261110_kiem_chung_v1/experiment_manifest.json)

## 21. Lập hàng chờ và phiếu thử thẩm định quan hệ — 2026-11-10

### 21.1 Khôi phục đoạn trong đúng ngữ cảnh

Gắn từng ứng viên với FactVersion, claim, hai định danh và tên thực thể, quan hệ, mã bài, ID bản thu, URL Wayback, mốc bản lưu và SHA-256 thân bài, HTML và đoạn trích. Đọc đoạn từ **thân bài của bản Wayback dùng làm bằng chứng**. Với bản lưu khác thân bài, sử dụng offset đã khôi phục trong bản đó. Lưu toàn bộ vị trí trùng, nguyên văn đoạn trích và ngữ cảnh tối đa 420 ký tự mỗi phía. Gộp trùng theo FactVersion, nguồn, mã bài, mã băm thân bài và các vị trí đoạn. Khi cùng một nội dung có nhiều bản thu, giữ mốc bản lưu sớm nhất đã xác minh cho phiếu. [Bảng hàng chờ](../../outputs/m2_anchor_semantic_review/20261110_v1/hang_cho_tham_dinh.parquet)

Kết quả gồm **1.425 phiếu từ 543 bài**, với 880 phiếu bản lưu cùng thân bài và 545 phiếu tìm nguyên văn đoạn trích trong bản lưu khác thân bài. Bảng có **1.434 vị trí đoạn trích** vì một số bản lưu chứa cùng đoạn nhiều lần. Đối chiếu thời điểm của các phiếu khớp với số FactVersion có căn cứ đến từng cutoff ở mục 20. **378 FactVersion** còn thiếu căn cứ đến T10 có danh sách riêng để xử lý tiếp. Phạm vi phiếu đã có mốc chỉ gồm VnExpress. [Thiết kế và số đếm](../../outputs/m2_anchor_semantic_review/20261110_v1/thiet_ke_phieu.json) · [Danh sách chờ căn cứ thời gian](../../outputs/m2_anchor_semantic_review/20261110_v1/fact_version_cho_can_cu_thoi_gian.json)

### 21.2 Tiêu chí và chọn phiếu thử

| Nhãn | Điều kiện và căn cứ phải ghi |
| --- | --- |
| **Hỗ trợ** | Đoạn trích trong ngữ cảnh khẳng định đúng hai thực thể và quan hệ. Với quan hệ có hướng, kiểm tra vai trò đầu–cuối theo ontology. Quan hệ đối tác là đối xứng theo cấu hình. |
| **Không hỗ trợ** | Đoạn hoặc ngữ cảnh chỉ rõ một thực thể khác, quan hệ khác, chiều ngược đối với quan hệ có hướng, hoặc phủ định bộ ba. Ghi câu hoặc từ quyết định. |
| **Chưa đủ căn cứ** | Đoạn chỉ nhắc tên, là giả định, hoặc ngữ cảnh chưa đủ để nhận định. Với nhiều vị trí, ghi vị trí dùng để đưa ra kết luận. |

Đợt thử gồm **24 phiếu từ 24 bài và 24 FactVersion khác nhau**, chia **12/12** cho hai loại bản lưu. Mỗi nhóm có một phiếu cho từng loại trong 10 quan hệ của ontology và hai ca thực hành thêm. Các ca thực hành ưu tiên đoạn xuất hiện nhiều lần hoặc đoạn thiếu một trong hai tên. Dùng thứ tự SHA-256 cố định, xử lý tầng ít ứng viên trước và kiểm không lặp bài. Phiếu cho người đọc hiển thị bộ ba cần kiểm tra, đoạn trích, ngữ cảnh và liên kết bản lưu. Kết quả cũ, nhóm chọn mẫu và chỉ số downstream được giữ ngoài phiếu. Thiết kế này phục vụ thử cách áp dụng tiêu chí, với độ phủ theo quan hệ có chủ đích. [Ontology](../../config/ontology.yaml) · [Phiếu thử HTML](../../outputs/m2_anchor_semantic_review/20261110_v1/phieu_tham_dinh_thu.html)

### 21.3 Kiểm chứng và bàn giao

Bộ kiểm chứng đọc lại **1.425 phiếu**, tính lại hash của **1.434 vị trí**, đối chiếu **10 cutoff**, xác nhận đúng 24 bài phân biệt và đủ quan hệ trong cả hai nhóm. Đã kiểm cú pháp mã phiếu HTML và diễn tập bằng hai tệp giả lập để bắt bất đồng, từ chối phiếu thiếu dòng và từ chối hai lượt khai cùng mã người đọc. **20 kiểm thử liên quan đạt**, cùng Ruff và kiểm tra khoảng trắng Git. Kết quả giả lập dùng để kiểm luồng, không đi vào hàng chờ hoặc nhãn khoa học. [Biên nhận kiểm chứng](../../outputs/m2_anchor_semantic_review/20261110_kiem_chung_v1/bien_nhan_kiem_chung.json)

**Mức xác minh đạt được là EXECUTED / VERIFIED cho khâu lập phiếu và kiểm tra kỹ thuật.** Hiện có **0 nhãn khoa học**. Quy định dự án yêu cầu nhãn độc lập và giới hạn quyết định khoa học tự động của LLM. Hai người đọc độc lập mở cùng tệp HTML, điền mã khác nhau, chọn lượt A hoặc B, ghi lý do cho đủ 24 phiếu rồi tải JSON. Khi có hai tệp, trình đối chiếu tạo bảng đếm theo nhãn và danh sách bất đồng để người phân xử xem. Sau khi chốt tiêu chí từ đợt thử mới mở rộng thẩm định hàng chờ và báo độ phủ nội dung theo cutoff. [Quy trình nhãn độc lập](m1_acceptance_design_v2/quality.md) · [Quy định LLM của dự án](../../AGENTS.md#L209) · [Bản kê bộ phiếu](../../outputs/m2_anchor_semantic_review/20261110_v1/experiment_manifest.json)

## 22. Chấm thử tham khảo trên 24 phiếu — 2026-11-10

Theo yêu cầu chấm thử, trợ lý AI đã đọc 24 phiếu đã khóa và ghi lý do từng nhãn. Lượt này lưu riêng với hai lượt đọc độc lập A/B. Căn cứ lấy từ đoạn trích và ngữ cảnh của bản Wayback đã gắn phiếu. Đối với hai trường hợp có câu liên quan ở phần khác của bài, lưu vị trí đó như ứng viên kiểm tra lại offset. Việc kiểm tra quan hệ dùng chiều đầu–cuối và kiểu thực thể trong ontology 1.1. [Bảng chấm thử](../../outputs/m2_anchor_semantic_review/20261110_tham_khao_v1/bang_cham_thu.md) · [Bản kê](../../outputs/m2_anchor_semantic_review/20261110_tham_khao_v1/experiment_manifest.json)

| Nhóm phiếu | Hỗ trợ | Không hỗ trợ | Chưa đủ căn cứ |
| --- | ---: | ---: | ---: |
| Bản lưu cùng thân bài | 6 | 2 | 4 |
| Bản lưu khác thân bài | 8 | 2 | 2 |
| **Tổng** | **14** | **4** | **6** |

- Trong **11/14 phiếu chấm hỗ trợ**, ít nhất một câu căn cứ đã dẫn nằm ngoài offset gốc và trong ngữ cảnh của phiếu. Ví dụ phần ngữ cảnh nêu trực tiếp xAI mua X, còn offset hiện tại cắt vào câu về khoản đầu tư của SpaceX.
- Hai phiếu về khoản đầu tư của **Redpoint Ventures vào Irregular** và **Microsoft vào OpenAI** có câu nêu khoản đầu tư ở phần khác trong bản lưu. Cả hai được chấm **chưa đủ căn cứ** với đoạn đang xét. Mã phiếu, câu dẫn và các vị trí mới được lưu để người đọc kiểm tra.
- Có bốn phiếu chấm **không hỗ trợ theo kiểu thực thể của ontology**. Hai phiếu dùng quan hệ phiên kế nhiệm của sản phẩm, phần mềm hoặc mô hình cho người hay thế hệ mạng. Hai phiếu dùng kiến trúc bộ xử lý hoặc tập lệnh làm đích của quan hệ `based_on`. Lượt thử cũng ghi riêng các cách đọc còn cần người thẩm định thống nhất, như chức chủ tịch có đủ cho `works_at` và ngữ cảnh nào đủ để giải nghĩa từ gọi chung “chatbot”. [Nhãn và căn cứ theo phiếu](../../outputs/m2_anchor_semantic_review/20261110_tham_khao_v1/ket_qua_tham_khao.json)

Đã đối chiếu **24 mã phiếu và 33 vị trí câu dẫn** với thân bài theo mã băm. Các số đếm mô tả riêng bộ phiếu thử có phân tầng. Hai lượt A/B tiếp tục nhận bộ phiếu chưa gắn nhãn, và số nhãn khoa học hiện là **0**. Việc kiểm chứng lượt này áp dụng cho dấu vết của câu dẫn và phạm vi của bảng chấm tham khảo. [Bộ phiếu A/B](../../outputs/m2_anchor_semantic_review/20261110_v1/experiment_manifest.json)

## 23. Chuẩn bị bàn giao hai lượt đọc độc lập A và B — 2026-11-10

Người dùng xác nhận có thể bố trí hai người chưa xem bảng chấm tham khảo. Đã tạo hai tệp HTML gán sẵn lượt **A** và **B**, cùng lấy dữ liệu từ bộ **24 phiếu đã khóa**. Hai tệp chứa cùng mã bộ phiếu, cùng thứ tự và nội dung. Người tổ chức chuyển mỗi tệp cho đúng người, giữ riêng phiếu đã điền đến khi cả hai lượt nộp. [Hướng dẫn bàn giao](../../outputs/m2_anchor_semantic_review/20261110_ban_giao_ab_v1/huong_dan_ban_giao.md)

| Lượt | Tệp cho người đọc | Tệp cần nộp |
| --- | --- | --- |
| A | [Phiếu lượt A](../../outputs/m2_anchor_semantic_review/20261110_ban_giao_ab_v1/phieu_tham_dinh_luot_A.html) | `m2_tham_dinh_luot_A.json` |
| B | [Phiếu lượt B](../../outputs/m2_anchor_semantic_review/20261110_ban_giao_ab_v1/phieu_tham_dinh_luot_B.html) | `m2_tham_dinh_luot_B.json` |

Đã kiểm thử giả lập thao tác điền và xuất tệp. Mỗi bản yêu cầu đủ nhãn và lý do cho 24 phiếu, xuất đúng tên tệp, mã lượt, mã bộ phiếu và danh sách mã phiếu. Trạng thái hiện tại là **sẵn sàng bàn giao và chờ hai tệp đã chấm**. Khi nhận đủ, đối chiếu theo mã phiếu, tính mức đồng thuận và chuyển các bất đồng cho người phân xử. [Biên nhận bàn giao](../../outputs/m2_anchor_semantic_review/20261110_ban_giao_ab_v1/bien_nhan_ban_giao.json) · [Bản kê](../../outputs/m2_anchor_semantic_review/20261110_ban_giao_ab_v1/experiment_manifest.json)

## 24. Đối chiếu hai lượt chấm thật trên 24 phiếu — 2026-11-11

Hai tệp JSON đã qua kiểm tra mã bộ phiếu, mã lượt và đủ **24 mã phiếu phân biệt** ở mỗi lượt. Cả hai tệp có nhãn, lý do và xác nhận tự đọc độc lập. Mã người đọc khác nhau. Hai bản lưu kết quả khớp từng byte với hai tệp nộp. Tính lại độc lập theo mã phiếu cho kết quả khớp ma trận của trình đối chiếu. [Kết quả đối chiếu](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v1/doi_chieu.json) · [Biên nhận tính lại](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/kiem_chung_ab.json)

| Nhãn | Lượt A | Lượt B | Cùng nhãn |
| --- | ---: | ---: | ---: |
| Hỗ trợ | 22 | 22 | 22 |
| Không hỗ trợ | 0 | 0 | 0 |
| Chưa đủ căn cứ | 2 | 2 | 2 |

Hai lượt trùng **24/24 nhãn (100%)**, **0 phiếu bất đồng**. Cả hai nhóm cùng thân bài và khác thân bài đạt **12/12** nhãn trùng, mỗi nhóm có 11 hỗ trợ và 1 chưa đủ căn cứ. Cohen κ không trọng số là **1,00**, với tỷ lệ trùng kỳ vọng theo phân bố nhãn là **84,72%**. Kết quả mô tả đồng thuận trên 24 phiếu thử theo tầng. Nhãn *không hỗ trợ* có số quan sát bằng 0 ở cả hai lượt, nên bộ phiếu này chưa có dữ liệu để đánh giá cách áp dụng nhãn đó. [Ma trận và số đếm theo nhóm](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/kiem_chung_ab.json)

### 24.1 Các trường hợp cần làm rõ trước khi mở rộng

1. **Căn cứ cho sự kiện phát hành.** Bốn phiếu `released_by` về Claude, Mythos 5, DeepSeek-Chat và Exynos 2600 cùng được chấm hỗ trợ. Lý do của hai lượt dựa vào cụm chỉ chủ sở hữu hoặc nhà phát triển, công bố nghiên cứu, bảng giá hay việc hãng thiết kế và sử dụng chip. Cần chốt mức bằng chứng đủ để gắn sự kiện phát hành với đúng đối tượng của bộ ba. [Ontology 1.1](../../config/ontology.yaml#L36)
2. **Kiểu thực thể của quan hệ.** Cả hai lượt đánh dấu hỗ trợ cho hai người kế nhiệm chức vụ trong `succeeded_by`, dù cấu hình giới hạn kiểu đầu và cuối ở mô hình AI, sản phẩm hoặc phần mềm. Ba phiếu về 5G và 6G, kiến trúc ARM và LoongArch cũng cần xem lại kiểu thực thể theo quan hệ được khai báo. Danh sách rà tiêu chí ghi riêng **8 phiếu đồng thuận** và giữ nhãn của cả hai lượt. [Chi tiết các phiếu cần làm rõ](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/phieu_can_lam_ro_tieu_chi.json)
3. **Vị trí đoạn trích.** Hai lượt cùng chấm *chưa đủ căn cứ* cho Redpoint Ventures–Irregular và Microsoft–OpenAI vì đoạn trên phiếu và ngữ cảnh liền kề thiếu thông tin đầu tư. Đã đối chiếu với thân bài theo mã băm và ghi hai vị trí ứng viên ở đoạn khác. Người phân xử có thể dùng các vị trí đó để kiểm tra lại căn cứ. [Vị trí ứng viên và nhãn đã nộp](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/phieu_can_lam_ro_tieu_chi.json)

**Mức xác minh đạt được là EXECUTED / VERIFIED cho đối chiếu A/B trên 24 phiếu thử.** Bước kế tiếp là chốt quy tắc chấm cho các nhóm trên và cách chọn đoạn hỗ trợ trước khi mở rộng thẩm định. [Bản kê kết quả](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v1/experiment_manifest.json) · [Bản kê kiểm chứng](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/experiment_manifest.json)

## 25. Phân tích bước hiệu chuẩn tiêu chí thẩm định — 2026-11-11

**Bước đề xuất là chốt một phiên bản hướng dẫn chấm mới rồi kiểm tra cách áp dụng trên các ca ranh giới.** Hai lượt trùng 24/24 nhãn với hướng dẫn hiện tại. Cả hai có thể hiểu giống nhau một câu báo trong khi áp dụng rộng hơn phạm vi kiểu của ontology. Hai lượt cũng dùng thông tin về sản phẩm thuộc một hãng, hoạt động nghiên cứu hoặc bảng giá làm căn cứ phát hành. Vì vậy, cần ghi riêng phần mà câu báo hỗ trợ và điều kiện để đưa quan hệ đó vào đồ thị. [Kết quả hai lượt](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/kiem_chung_ab.json) · [Các phiếu minh họa](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/phieu_can_lam_ro_tieu_chi.json)

### 25.1 Ba tiêu chí cần thống nhất

| Tiêu chí | Quy tắc đề xuất | Ca minh họa |
| --- | --- | --- |
| **Căn cứ cho quan hệ** | Xét đúng hai thực thể, chiều, trạng thái và loại quan hệ. Với `released_by`, yêu cầu câu hoặc các câu liền kề xác định đúng sản phẩm và tổ chức gắn với một lần đã ra mắt, phát hành hoặc đưa sản phẩm đó ra cung cấp. Có thể dùng cách diễn đạt tương đương. Nếu nguồn chỉ nêu hãng phát triển, kết quả thử nghiệm, giá hoặc dự kiến mà chưa xác định sự kiện của đúng sản phẩm, ghi **chưa đủ căn cứ** cho quan hệ phát hành. | Công bố nghiên cứu sử dụng Mythos 5 xác định hoạt động thử nghiệm. Bản tin Exynos 2600 cần tách việc công bố điện thoại Galaxy S26 khỏi việc phát hành chip. |
| **Kiểu của hai thực thể** | Đối chiếu kiểu đầu và cuối với ontology 1.1 và lưu kết quả riêng gồm **đúng kiểu**, **sai kiểu** hoặc **chưa xác minh kiểu**. Một câu có thể hỗ trợ mệnh đề theo nghĩa thông thường nhưng rơi ngoài kiểu quan hệ đã khai báo. | Bản tin xác nhận kế nhiệm chức bộ trưởng giữa hai người. `succeeded_by` của đồ thị cho phép mô hình AI, sản phẩm và phần mềm. Với ARM, LoongArch và 5G–6G, ghi cách nguồn mô tả đối tượng và yêu cầu đối chiếu kiểu trước khi chốt. |
| **Vị trí đoạn làm căn cứ** | Người đọc dẫn đoạn tối thiểu đủ hiểu chủ thể, quan hệ và đối tượng. Khi câu quyết định nằm cạnh đoạn gốc, ghi phạm vi trích đủ ngữ cảnh. Khi nằm ở chỗ khác, tạo vị trí ứng viên riêng với mã phiên bản, offset Unicode, mã băm đoạn và thời điểm của đúng bản chứa đoạn. Nhãn đã nộp đi cùng đoạn mà người đọc đã xem. | Hai phiếu đầu tư có câu xác nhận ở đoạn khác của bản lưu. Có thể đưa các vị trí này cho người phân xử xác minh và ghi quyết định bổ sung. |

[Ontology 1.1](../../config/ontology.yaml) · [Chi tiết lý do và vị trí ứng viên](../../outputs/m2_anchor_semantic_review/20261111_kiem_chung_ab_v1/phieu_can_lam_ro_tieu_chi.json)

### 25.2 Thứ tự thực hiện sau khi chốt

1. **Ghi phiên bản hướng dẫn và hiệu chuẩn.** Dùng 8 ca đồng thuận đã gắn cờ và 2 ca cần tìm lại đoạn để minh họa cách ghi nhãn theo ba tiêu chí. Lưu riêng nhãn A/B ban đầu và quyết định của người phân xử, với lý do và câu dẫn cho mỗi ca. Nhóm 10 ca này được chọn để làm rõ ranh giới của hướng dẫn.
2. **Kiểm tra khả năng áp dụng trên phiếu chưa chấm.** Chọn trước một nhóm nhỏ từ hàng chờ, có ca đủ căn cứ, ca cần phân biệt sự kiện với sở hữu hay thử nghiệm, ca có kiểu cần kiểm và ca cần ngữ cảnh. Hai người đọc áp dụng hướng dẫn đã khóa. Rà các bất đồng theo từng tiêu chí trước khi quyết định mở rộng. Điều kiện bàn giao là hướng dẫn và quyết định phân xử có thể truy vết, cùng bằng chứng cho thấy các ca đủ, thiếu và sai căn cứ được ghi nhất quán. [Quy trình đánh giá độc lập](m1_acceptance_design_v2/quality.md)
3. **Tính lại độ phủ theo cutoff khi đã có thẩm định.** Tách số thực thể có bằng chứng được chấp nhận khỏi số thực thể còn thiếu dữ liệu hoặc thiếu hiệu lực ánh xạ. T01 có đúng **167 thực thể chung**, bằng tổng **101 neo khớp và 66 neo giữ riêng**. T09 có **1.143/1.282 thực thể có căn cứ thời gian** trước khi xét nội dung và ánh xạ. Việc còn thiếu tần suất phải được định lượng trước khi đăng ký bộ neo. [Số ứng viên neo](../../outputs/m2_alignment_v31_readiness/20261110_v1/kiem_tra_truoc_can_chinh.json) · [Độ phủ thời gian](../../outputs/m2_anchor_temporal_review/20261110_doan_trich_v1/bao_phu_bo_sung.json)

Đối chiếu tập bộ ba và ánh xạ theo từng snapshot sau khi có hồ sơ thẩm định. Nếu phần bổ sung chỉ thay vị trí bằng chứng và các đầu vào huấn luyện vẫn khớp, 30 checkpoint hiện có có thể tiếp tục được dùng sau khi xác minh truy vết. Nếu việc xác nhận làm đổi bộ ba hoặc ánh xạ, lập danh sách snapshot bị ảnh hưởng để quyết định phạm vi xử lý. [Kết quả mô hình nền](../../outputs/m2_backbone_v31/20261110_kiem_chung_v1/kiem_chung.json)

**Trạng thái hiện tại là phân tích và đề xuất quy tắc.** Việc chốt cần người có thẩm quyền xác nhận trước khi dùng hướng dẫn để chấm một nhóm mới hoặc mở rộng hàng chờ.

## 26. Chuẩn bị hiệu chuẩn hướng dẫn chấm M2 V3.1 — 2026-11-11

1. **Ghi phiên bản hướng dẫn.** Hướng dẫn v2.0-hiệu-chuẩn ghi riêng mức hỗ trợ quan hệ, kiểu của từng thực thể và vị trí đoạn quyết định. Phiếu áp dụng đúng phạm vi kiểu của ontology 1.1. Người phân xử giải thích căn cứ về quan hệ và kiểu theo từng ca. [Hướng dẫn chấm](M2_HUONG_DAN_CHAM_QUAN_HE_V2.md) · [Ontology 1.1](../../config/ontology.yaml)
2. **Đóng gói các ca đã đối chiếu.** Phiếu gồm 4 ca về căn cứ phát hành, 4 ca về phạm vi kiểu và 2 ca tìm lại đoạn trích. Mỗi ca có nhãn và lý do A/B để đối chiếu, đoạn gốc và ngữ cảnh đã cung cấp, toàn bộ thân bài của đúng bản lưu và mốc quan sát. Người phân xử có thể lưu bản nháp, chọn nguyên văn đoạn quyết định và tải tệp kết quả có mã bộ hiệu chuẩn. Nhóm 10 ca được chọn để kiểm tra cách hiểu tiêu chí. [Phiếu hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/phieu_hieu_chuan_v2.html) · [Biên nhận chuẩn bị](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/bien_nhan_chuan_bi.json)
3. **Kiểm chứng gói bàn giao.** Đã đối chiếu đủ 10 mã phiếu, nhãn và lý do A/B, vị trí của 11 đoạn gốc và 2 đoạn gợi ý. Đã kiểm mã băm của 18 tệp đầu vào trực tiếp và 3 tệp đầu ra. Kiểm thử giả lập xác nhận phiếu chặn xuất kết quả khi còn thiếu trường, lưu và nạp lại bản nháp, từ chối đoạn bị sửa sai vị trí và xuất đủ 10 quyết định với vị trí Unicode đúng. [Bản kê kiểm chứng](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/experiment_manifest.json)
4. **Bàn giao người phân xử.** Người phân xử điền cả 10 ca và chọn đồng ý hoặc yêu cầu sửa hướng dẫn, kèm lý do. Khi nhận tệp `m2_hieu_chuan_v2.json`, kiểm lại mã bộ, đoạn trích, mã băm và kết luận theo từng ca. Sau khi chốt hướng dẫn mới chọn nhóm phiếu chưa chấm để hai người áp dụng độc lập. [Phiếu hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/phieu_hieu_chuan_v2.html)

Để tái lập, chạy `python scripts/prepare_m2_semantic_calibration.py <thư_mục_kết_quả_mới>` từ thư mục dự án. Thư mục mới phải nằm trong `outputs/m2_anchor_semantic_review`. [Trình chuẩn bị](../../scripts/prepare_m2_semantic_calibration.py)

Gói đã được tạo trên hồ sơ thật (**EXECUTED**) và kiểm chứng về truy vết (**VERIFIED**). Thao tác trên phiếu đạt kiểm thử giả lập (**TESTED**). Hiện có **0/10 quyết định của người phân xử**. Độ tin cậy của tiêu chí phiên bản mới và độ phủ bằng chứng dùng cho neo vẫn chờ kết quả thẩm định.

## 27. Phân tích lượt chấm độc lập trên phiếu mới — 2026-11-11

Người dùng xác nhận đã đọc và đồng ý với hướng dẫn V2. Hướng dẫn và hồ sơ từng ca phục vụ hai mục đích. Ý kiến đồng ý ghi nhận việc chấp thuận cách chấm. Hồ sơ 10 ca ghi cách áp dụng vào các trường hợp cụ thể, gồm căn cứ quan hệ, kiểu hai thực thể và vị trí đoạn quyết định khi có. Cần nhận và kiểm tra tệp hiệu chuẩn để hoàn tất phần hồ sơ. [Hướng dẫn V2](M2_HUONG_DAN_CHAM_QUAN_HE_V2.md) · [Biên nhận chuẩn bị](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/bien_nhan_chuan_bi.json)

Đã đọc các trường truy vết và phân tầng từ hàng chờ đã kiểm mã băm. Loại mọi phiếu trùng bài theo cặp nguồn và mã bài, mã băm thân bài, mã FactVersion hoặc mã mệnh đề trích xuất với bất kỳ phiếu nào trong 24 ca cũ. Còn **1.332/1.425 phiếu**, gồm **834** ca thuộc nhóm cùng thân bài và **498** ca thuộc nhóm khác thân bài. Cả 10 quan hệ đều có ứng viên trong cả hai nhóm. Tất cả ứng viên còn lại thuộc nguồn VnExpress Số hóa. [Bản kê hàng chờ](../../outputs/m2_anchor_semantic_review/20261110_v1/experiment_manifest.json) · [Thiết kế lượt cũ](../../outputs/m2_anchor_semantic_review/20261110_v1/thiet_ke_phieu.json)

| Thành phần đề xuất | Mỗi nhóm | Tổng |
| --- | ---: | ---: |
| Một ca cho mỗi quan hệ trong 10 quan hệ | 10 | 20 |
| Ca bổ sung về sự kiện phát hành `released_by` | 1 | 2 |
| Ca bổ sung thuộc `succeeded_by` hoặc `based_on`, có ít nhất một tên không xuất hiện trong đoạn trích gốc đầu tiên | 1 | 2 |
| Tổng | 12 | 24 |

Đã kiểm tra sự tồn tại của một bộ đủ 24 vị trí mà không trùng bài, thân bài, FactVersion hoặc mã mệnh đề trong nội bộ bộ phiếu. Nhóm ca bổ sung về kiểu và ngữ cảnh có lần lượt 22 và 17 ứng viên ở hai nhóm. Dấu hiệu thiếu tên dùng để tăng cơ hội kiểm tra cách đọc ngữ cảnh. Nó chưa xác định nhãn quan hệ của ca. Số 24 là quy mô thử cách áp dụng tiêu chí, được chọn để phủ đủ quan hệ và hai nhóm bằng chứng, với bốn vị trí dành cho những vấn đề đã thấy ở lượt cũ.

Sau khi nhận hồ sơ hiệu chuẩn, khóa phiên bản hướng dẫn, thứ tự chọn tái lập theo mã băm và danh sách phiếu trước khi chấm. Hai lượt nhận cùng dữ liệu gốc và hướng dẫn, nộp riêng. Giữ nhãn A/B cũ, hồ sơ phân xử hiệu chuẩn và bảng chấm tham khảo ngoài gói phiếu mới. [Quy trình đề xuất đánh giá độc lập](m1_acceptance_design_v2/quality.md)

Khi thu đủ hai lượt, báo cáo số lượng và tỷ lệ đồng thuận riêng về nhãn quan hệ, kiểu của từng thực thể và nhóm vị trí đoạn. Đối chiếu từng đoạn với thân bài và mốc quan sát. Người phân xử xem liệu hai đoạn khác nhau có cùng đủ căn cứ hay không và ghi rõ nguồn bất đồng. Nếu hướng dẫn vẫn dẫn đến cách hiểu khác nhau có hệ thống, sửa và thử phiên bản mới trên nhóm khác. Nếu lượt thử thiếu một nhãn hoặc một dạng ca cần kiểm, ghi giới hạn đó trước khi xem xét mở rộng. Quyết định mở rộng dựa vào hồ sơ phân xử và độ bao phủ của các tiêu chí trong lượt thử. Kết quả của lượt này có phạm vi là độ nhất quán khi thẩm định bằng chứng, còn G2, G3 và hiệu quả embedding có bộ kiểm tra riêng.

**Trạng thái:** Đã kiểm tra tính khả thi của thiết kế trên hàng chờ thật. Hồ sơ 10 ca đang chờ nộp và danh sách phiếu mới chưa được khóa.

## 28. Chuẩn bị đối chiếu tệp hiệu chuẩn M2 V3.1 — 2026-11-11

1. Kiểm tra thư mục tải xuống đã biết và thư mục bàn giao. Chưa tìm thấy tệp kết quả. Ý kiến đồng ý với hướng dẫn V2 đã được ghi ở mục 27. Trạng thái hồ sơ theo từng ca vẫn là chờ nộp.
2. Bổ sung trình tiếp nhận. Trình kiểm tra mã bộ phiếu, mã băm hướng dẫn và đủ 10 quyết định có mã phân biệt. Trình kiểm tra lý do theo từng ca, đối chiếu loại thực thể với trạng thái kiểu, và xác minh nguyên văn, vị trí Unicode và thông tin đúng bản lưu cho từng đoạn được dẫn. Trình tính SHA-256 của đoạn, lưu nguyên tệp nộp và ghi biên nhận ở một thư mục mới. Kết luận về hướng dẫn do người phân xử ghi trong phiếu. [Trình đối chiếu](../../scripts/verify_m2_semantic_calibration.py)
3. Kiểm thử luồng tiếp nhận bằng quyết định giả lập trên gói phiếu đã phát. Tệp hợp lệ cho 10 quyết định và 9 đoạn dẫn trong kiểm thử. Trình từ chối bản nháp, sai mã hướng dẫn, thiếu hoặc lặp quyết định, thiếu lý do, sai trạng thái kiểu, sai bản lưu và sai vị trí. Đã kiểm chứng bản sao tệp nộp khớp từng byte và thư mục có sẵn được bảo vệ khỏi ghi đè. Biên nhận kiểm thử được tạo trong thư mục tạm.

Lệnh tiếp nhận là `python scripts/verify_m2_semantic_calibration.py <gói_đã_phát> <tệp_đã_nộp> <thư_mục_kết_quả_mới>`. Khi có biên nhận hợp lệ, đọc kết luận và căn cứ của người phân xử để xác định hướng dẫn có thể khóa hay cần sửa trước khi phát 24 phiếu mới.

**Trạng thái:** Trình tiếp nhận đã triển khai (**IMPLEMENTED**) và kiểm thử (**TESTED**). Chờ tệp `m2_hieu_chuan_v2.json` để đối chiếu quyết định thật. [Phiếu hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_hieu_chuan_v2/phieu_hieu_chuan_v2.html)

## 29. Kết quả hiệu chuẩn trên 10 ca đã đối chiếu — 2026-11-11

Đã tiếp nhận đủ **10 quyết định**. Bản lưu tệp nộp khớp từng byte với bản người dùng gửi. Đã đối chiếu mã hướng dẫn, mã phiếu, trạng thái kiểu và nguyên văn của **7 đoạn dẫn** tại các vị trí đã ghi. Trong số đó có 4 đoạn ở ngữ cảnh liền kề và 3 đoạn khác trong cùng bản lưu. Ba ca còn lại ghi chưa đủ căn cứ và để trống đoạn quyết định. [Biên nhận](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json) · [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/experiment_manifest.json)

| Kết quả theo người phân xử | Số ca | Căn cứ được ghi |
| --- | ---: | --- |
| Từ hỗ trợ sang chưa đủ căn cứ | 3 | Claude, Mythos 5 và DeepSeek-Chat. Bài nêu sở hữu, nghiên cứu hoặc giá và còn thiếu sự kiện phát hành của đúng sản phẩm. |
| Từ chưa đủ căn cứ sang hỗ trợ | 2 | Redpoint Ventures–Irregular và Microsoft–OpenAI. Đoạn quyết định nằm ở chỗ khác trong chính thân bài đã lưu. |
| Giữ nhãn hỗ trợ | 5 | Exynos 2600 và bốn ca mà người phân xử đánh dấu sai kiểu dù câu báo hỗ trợ quan hệ theo nghĩa thông thường. |

Tổng cộng có **7 hỗ trợ, 3 chưa đủ căn cứ và 0 không hỗ trợ**. Phân theo kiểu có **6 đúng kiểu, 4 sai kiểu và 0 chưa xác minh kiểu**. Ba ca được chấm đồng thời hỗ trợ và đúng kiểu. Trong đó, người phân xử ghi rõ Exynos 2600 còn có cách hiểu khác về việc phát hành linh kiện cùng thiết bị chủ. Các số đếm mô tả nhóm 10 ca chọn có chủ đích. Nhãn A/B ban đầu và quyết định hiệu chuẩn được lưu riêng. [Kết quả A/B](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v1/doi_chieu.json) · [Hồ sơ hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json)

Người phân xử chọn **cần sửa hướng dẫn**. Có bốn nhóm cần xử lý trước khi khóa phiên bản.

1. **Ranh giới của quan hệ.** Làm rõ việc giới thiệu linh kiện trong buổi ra mắt thiết bị với ca Exynos, và thứ tự thế hệ so với sự kế nhiệm đã xảy ra với ca 5G–6G. Bổ sung ví dụ áp dụng cho `succeeded_by`, `based_on` và `invested_in`. Dùng định nghĩa đã được phê duyệt nếu có. Trường hợp cần quyết định mới về phạm vi quan hệ phải ghi riêng để xác nhận.
2. **Cách nhận diện kiểu.** Ontology 1.1 liệt kê `Product` và phạm vi kiểu cho từng quan hệ. Tệp này chưa có định nghĩa diễn giải riêng cho `Product`. Người phân xử yêu cầu làm rõ cách áp dụng với chip, dòng chip và kiến trúc tập lệnh. [Ontology 1.1](../../config/ontology.yaml)
3. **Đoạn trùng trong cùng bản lưu.** Đã kiểm lại đoạn Exynos có nguyên văn giống nhau tại ba vị trí bắt đầu 1118, 1634 và 2150. Người phân xử chọn lần đầu. Cần ghi quy tắc chọn vị trí khi cùng câu xuất hiện nhiều lần để đối chiếu nhất quán.
4. **Độ phủ của ví dụ hiệu chuẩn.** Hai nhánh `KHONG_HO_TRO` và `CHUA_XAC_MINH_KIEU` có số quan sát bằng 0. Cần minh họa hai nhánh này khi rà hướng dẫn và giữ các ca minh họa ngoài bộ chấm độc lập.

**Trạng thái:** Đã tiếp nhận hồ sơ thật (**EXECUTED**) và kiểm chứng cấu trúc, vị trí đoạn dẫn và truy vết (**VERIFIED**). Kết luận nội dung thuộc về người phân xử. Hướng dẫn đang chờ sửa và bộ 24 phiếu mới đang chờ khóa.

## 30. Rà soát hướng dẫn chấm V2.1 — 2026-11-11

1. **Mô tả căn cứ cho đủ 10 quan hệ.** Đối chiếu danh sách và chiều quan hệ với ontology 1.1. Làm rõ trường hợp bài xác lập thông tin mâu thuẫn và trường hợp bài còn thiếu căn cứ cho chính mệnh đề đang xét. Bổ sung dấu hiệu thực hành cho `succeeded_by`, `based_on` và `invested_in` cùng các quan hệ còn lại. [Hướng dẫn V2.1](M2_HUONG_DAN_CHAM_QUAN_HE_V2_1.md) · [Ontology 1.1](../../config/ontology.yaml)
2. **Xử lý các góp ý về đoạn dẫn và ví dụ.** Bổ sung cách chọn vị trí bắt đầu nhỏ nhất trong số các lần lặp có ngữ cảnh đủ căn cứ tương đương. Kiểm lại nguyên văn đoạn Exynos ở ba vị trí 1118, 1634 và 2150 trong cùng thân bài. Thêm hai ví dụ giả định cho nhãn *không hỗ trợ* và trạng thái *chưa xác minh kiểu*. [Biên nhận rà soát](../../outputs/m2_anchor_semantic_review/20261111_ra_soat_huong_dan_v2_1/bien_nhan_ra_soat.json)
3. **Ghi đề xuất cho ba điểm có thể đổi kết quả.** Đề xuất yêu cầu căn cứ phát hành đúng linh kiện dù sự kiện diễn ra chung với thiết bị, yêu cầu căn cứ về vai trò kế nhiệm khi nguồn chỉ nêu thứ tự thế hệ, và cho phép dùng `Product` khi xác định rõ một chip hoặc dòng chip là sản phẩm phần cứng cụ thể. Bốn ca liên quan là Exynos 2600, 5G–6G, dòng M–ARM và 3A6000–LoongArch. Sau khi chốt cách diễn giải, người phân xử rà lại phần chịu ảnh hưởng của bốn ca. [Các đề xuất trong V2.1](M2_HUONG_DAN_CHAM_QUAN_HE_V2_1.md#4-ba-cách-diễn-giải-đề-xuất-để-chốt)

**Trạng thái** Đã soạn bản rà soát (**IMPLEMENTED**) và đối chiếu 10 quan hệ, hồ sơ 10 ca cùng ba vị trí đoạn lặp (**VERIFIED** trong phạm vi truy vết tài liệu). Chờ xác nhận cách diễn giải trước khi dùng hướng dẫn để khóa bộ phiếu chấm độc lập. [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_ra_soat_huong_dan_v2_1/experiment_manifest.json)

## 31. Dừng rà soát bổ sung sau 10 ca hiệu chuẩn — 2026-11-11

Người dùng chọn bỏ qua lượt rà lại bốn ca vì phần hiệu chuẩn đã thực hiện đủ cho mục đích hiện tại. Biên nhận của mục 29 là hồ sơ kết quả của 10 ca. V2.1 là bản rà soát tài liệu, với ba cách diễn giải ghi ở mức đề xuất. [Biên nhận hiệu chuẩn](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json) · [Bản rà soát V2.1](M2_HUONG_DAN_CHAM_QUAN_HE_V2_1.md)

## 32. Bỏ qua bộ phiếu chấm độc lập theo V2 — 2026-11-11

Người dùng chọn bỏ qua bộ 24 phiếu chấm độc lập theo V2. Mục 27 ghi lại thiết kế và kiểm tra tính khả thi. Hồ sơ thẩm định V2 đã nộp gồm 10 ca hiệu chuẩn ở mục 29. [Biên nhận 10 ca](../../outputs/m2_anchor_semantic_review/20261111_tiep_nhan_hieu_chuan_v2/bien_nhan_kiem_tra.json)

## 33. Bàn giao bộ 24 phiếu chấm độc lập V2 — 2026-11-11

1. **Khóa danh sách theo yêu cầu nhận bộ V2.** Từ 1.332 ứng viên còn lại sau khi loại giao với lượt cũ, chọn 24 phiếu theo thiết kế mục 27. Hai nhóm cùng thân bài và khác thân bài có 12 phiếu mỗi nhóm và đều phủ đủ 10 quan hệ. Phép chọn tái lập theo mã băm, có ràng buộc chống trùng bài, thân bài, FactVersion và mệnh đề. Đã xác minh thứ tự chọn khớp khi đảo thứ tự hàng chờ. [Thiết kế và mã bộ phiếu](../../outputs/m2_anchor_semantic_review/20261111_ban_giao_ab_v2/thiet_ke_phieu_v2.json)
2. **Tạo hai tệp cho hai người chấm.** A và B có cùng thứ tự, bản lưu, ngữ cảnh, kiểu cho phép và hướng dẫn V2. Dữ liệu đưa cho người chấm gồm bộ ba, văn bản và thông tin truy vết. Các lựa chọn chấm để trống. Mỗi lượt xuất một tệp JSON gắn mã bộ và mã lượt, có xác nhận chấm độc lập. Người phụ trách chuyển một tệp HTML cho mỗi người và thu kết quả riêng. [Phiếu A](../../outputs/m2_anchor_semantic_review/20261111_ban_giao_ab_v2/phieu_tham_dinh_v2_luot_A.html) · [Phiếu B](../../outputs/m2_anchor_semantic_review/20261111_ban_giao_ab_v2/phieu_tham_dinh_v2_luot_B.html)
3. **Kiểm chứng gói trước bàn giao.** Đã kiểm mã băm của 31 tệp đầu vào trực tiếp và xác minh nguyên văn đoạn gốc. Kiểm thử giả lập cho thấy phiếu lưu và nạp lại bản nháp đúng lượt, từ chối bản nháp của lượt còn lại hoặc đoạn có vị trí sai, và xuất đủ 24 câu trả lời với đúng tên tệp sau khi xác nhận đọc độc lập. [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_ban_giao_ab_v2/experiment_manifest.json)

Bộ phiếu được tạo trên hồ sơ thật (**EXECUTED**) và đã kiểm chứng danh sách, truy vết và nội dung A/B (**VERIFIED**). Thao tác nộp trên phiếu đạt kiểm thử giả lập (**TESTED**). Hiện có 0 phiếu đã chấm của lượt mới.

## 34. Đối chiếu hai lượt chấm độc lập V2 — 2026-11-11

Hai tệp nộp khớp mã bộ, mã hướng dẫn, mã lượt và đủ 24 mã phiếu khác nhau ở mỗi lượt. Hai lượt có mã người chấm khác nhau và xác nhận đã chấm độc lập. Đã lưu bản sao khớp từng byte và kiểm tra nguyên văn cùng vị trí của 19 đoạn do A chọn và 20 đoạn do B chọn. [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v2/experiment_manifest.json)

| Tiêu chí | Trùng cả bộ | Cùng thân bài | Khác thân bài |
| --- | ---: | ---: | ---: |
| Nhãn quan hệ | 21/24 | 12/12 | 9/12 |
| Kiểu thực thể đầu | 23/24 | 12/12 | 11/12 |
| Kiểu thực thể cuối | 24/24 | 12/12 | 12/12 |
| Trạng thái đúng, sai hoặc chưa xác minh kiểu | 23/24 | 12/12 | 11/12 |
| Nhóm vị trí đoạn dẫn | 19/24 | 11/12 | 8/12 |

Đồng thuận nhãn quan hệ là **87,5%**, Cohen κ **0,631**. Hai lượt cùng chấm hỗ trợ ở 18 ca và cùng chấm chưa đủ căn cứ ở 3 ca. Nhãn không hỗ trợ xuất hiện một lần ở lượt B. Hai lượt đều có 0 ca chưa xác minh kiểu. Các chỉ số mô tả bộ 24 phiếu được chọn theo tầng. [Ma trận đầy đủ](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v2/doi_chieu_v2.json)

| Ca cần phân xử | Lượt A | Lượt B | Điểm cần làm rõ |
| --- | --- | --- | --- |
| Optimus → `released_by` → Tesla | Chưa đủ căn cứ | Không hỗ trợ | Bài nói đang phát triển và chưa triển khai thương mại. Cần xác định câu đó có bác bỏ việc ra mắt hay chỉ để ngỏ sự kiện ra mắt. |
| Fengdeng → `released_by` → Phòng thí nghiệm Quốc gia vịnh Tam Á | Hỗ trợ | Chưa đủ căn cứ | Mức căn cứ của cụm “sự ra đời” và mô tả mô hình cung cấp thông tin cho nông dân. |
| Alpha 7 IV → `succeeded_by` → Alpha 7 V | Chưa đủ căn cứ | Hỗ trợ | Bài nêu thế hệ thứ năm và so sánh với IV. Cần xem câu văn xác lập vai trò kế nhiệm đến mức nào. |
| Android → `based_on` → Linux | `Software`, đúng kiểu | `Platform`, sai kiểu | Cả hai hỗ trợ quan hệ và chọn cùng đoạn. Cần xác định kiểu của đúng đối tượng Android mà bài nói tới. |

Trong 18 ca mà cả hai lượt chọn đoạn, **13** ca trùng chính xác khoảng ký tự và **15** ca có phần giao nhau. Hai đoạn khác vị trí vẫn có thể cùng xác lập quan hệ. Chẳng hạn hai đoạn về Jensen Huang đều xác nhận chức CEO tại NVIDIA. Với Altman–Reddit, lượt A dẫn việc bán cổ phần còn lượt B dẫn câu trực tiếp nêu khoản đầu tư. Vì vậy việc phân xử xem cả nội dung đoạn dẫn và lý do, ngoài khoảng ký tự. [Các khác biệt theo mã phiếu](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v2/doi_chieu_v2.json)

Đã đối chiếu tệp thật (**EXECUTED**) và kiểm lại bản sao, nguyên văn các đoạn dẫn cùng năm ma trận theo mã phiếu (**VERIFIED**). Bước kế tiếp là phân xử bốn bất đồng về quan hệ hoặc kiểu và đối chiếu các đoạn khác vị trí có thể ảnh hưởng đến căn cứ. Kết quả hiện tại mô tả đồng thuận của hai lượt V2 trên 24 phiếu. [Trình đối chiếu](../../scripts/compare_m2_semantic_independent_review.py)

## 35. Đề xuất phân xử và kiểm tra nguyên nhân bất đồng V2 — 2026-11-11

Đã đọc lại toàn bộ bốn thân bài có bất đồng về quan hệ hoặc kiểu. Hai lượt A/B nhận cùng nội dung của từng phiếu. Nguyên nhân được ghi theo lời giải thích của người chấm và đối chiếu với đoạn gốc trong đúng bản lưu. [Hướng dẫn V2](M2_HUONG_DAN_CHAM_QUAN_HE_V2.md) · [Đối chiếu A/B](../../outputs/m2_anchor_semantic_review/20261111_doi_chieu_ab_v2/doi_chieu_v2.json)

| Ca | Nguyên nhân bất đồng | Đề xuất sau khi đọc lại |
| --- | --- | --- |
| Optimus → `released_by` → Tesla | B xem tình trạng chưa triển khai thương mại là căn cứ bác bỏ việc phát hành. A ghi thiếu căn cứ về sự kiện. | **Chưa đủ căn cứ.** Đoạn `[1608, 1708)` xác nhận tình trạng đang phát triển và chưa triển khai thương mại. Việc giới thiệu hoặc ra mắt vẫn còn bỏ ngỏ, trong khi V2 chấp nhận cả hai dạng sự kiện. |
| Fengdeng → `released_by` → Phòng thí nghiệm Quốc gia vịnh Tam Á | A suy từ “sự ra đời” và lợi ích cho nông dân sang việc phòng thí nghiệm đã phát hành. B yêu cầu căn cứ nối tổ chức với sự kiện. | **Chưa đủ căn cứ.** Đoạn `[821, 1047)` xác định đơn vị phát triển và công dụng của mô hình. Vai trò phát hành, ra mắt hoặc đưa mô hình ra cung cấp của chính phòng thí nghiệm còn bỏ ngỏ. |
| Alpha 7 IV → `succeeded_by` → Alpha 7 V | B suy từ thứ tự IV và V cùng phép so sánh trong bài ra quan hệ kế nhiệm. A yêu cầu thêm căn cứ gắn hai mẫu. | **Chưa đủ căn cứ trên thân bài này.** Đoạn `[0, 415)` nêu V là thế hệ thứ năm và so sánh một tính năng với IV. Bài xác nhận việc mở bán V. Quan hệ kế nhiệm giữa đúng hai mẫu vẫn dựa vào suy luận từ tên và phép so sánh. |
| Android → `based_on` → Linux | Cả hai chọn đoạn `[2395, 2571)`. A đọc Android theo nghĩa phần mềm vận hành trên Linux. B dùng cách gọi “nền tảng Android” để chọn `Platform`. | **Hỗ trợ quan hệ và chưa xác minh kiểu Android.** Đoạn nêu sự phụ thuộc kỹ thuật vào Linux. Ontology cho phép `Software` ở đầu `based_on`. Thân bài chưa giúp phân định hai cách hiểu kiểu của Android theo danh mục. Kiểu `Software` của Linux có căn cứ trong bài. |

Đã rà năm ca chỉ khác đoạn. Đề xuất đoạn ngắn của B cho Jensen Huang vì cả hai đoạn đều xác nhận chức CEO tại NVIDIA. Với Altman–Reddit, ưu tiên đoạn B nêu trực tiếp khoản đầu tư. Đề xuất đoạn A cho Neo vì B lặp cùng căn cứ và thêm ngữ cảnh về thử nghiệm. Với NIC–FPT, đoạn A nêu rõ việc hai bên đã cùng triển khai các dự án bán dẫn. Với tích hợp GPT-5.2 vào ChatGPT, đoạn A đã chứa tên mô hình và câu xác nhận tích hợp. [Đoạn dẫn và mã băm theo từng ca](../../outputs/m2_anchor_semantic_review/20261111_de_xuat_phan_xu_ab_v2/de_xuat_phan_xu_v2.json)

Đã kiểm chứng nguyên văn, vị trí và mã băm của chín đoạn được viện dẫn. Kết luận nội dung trong mục này ở mức đề xuất cho người phân xử xác nhận. Chỉ số đồng thuận A/B tại mục 34 tính từ hai tệp đã nộp. [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_de_xuat_phan_xu_ab_v2/experiment_manifest.json)

Bản dự thảo biên bản ghi từng mã phiếu, quyết định, căn cứ và khoảng trích để người phân xử xác nhận cả chín mục hoặc ghi điều chỉnh theo số mục. [Dự thảo biên bản phân xử](BIEN_BAN_PHAN_XU_M2_V2_20261111.md)

## 36. Chốt biên bản phân xử bộ 24 phiếu V2 — 2026-11-11

Người dùng xác nhận “Chốt” sau khi bản JSON được đối chiếu với cả 9 mục của dự thảo biên bản. Đã kiểm lại 24 mã phiếu và nội dung từng mục, lưu nguyên bản người dùng dán, ghi thời điểm xác nhận và tạo bộ kết quả đã chốt. Trong 24 phiếu có 15 ca trùng về nhãn, kiểu và đoạn dẫn ở hai lượt, cùng 9 ca có quyết định phân xử đã được xác nhận. [Biên bản đã chốt](../../outputs/m2_anchor_semantic_review/20261111_chot_phan_xu_ab_v2/bien_ban_phan_xu_v2_da_chot.md) · [Kết quả JSON](../../outputs/m2_anchor_semantic_review/20261111_chot_phan_xu_ab_v2/phan_xu_v2_da_chot.json)

Kết quả sau phân xử có **18 phiếu hỗ trợ**, **6 phiếu chưa đủ căn cứ**. Về kiểu thực thể có **20 phiếu đúng kiểu**, **3 phiếu sai kiểu** và **1 phiếu chưa xác minh kiểu**. Có **15 phiếu đồng thời hỗ trợ quan hệ và đúng kiểu**. Số đếm này là căn cứ nội dung cho bước đối chiếu mốc quan sát, ánh xạ và bài nguồn phân biệt khi tính độ phủ cho thực thể neo. Chỉ số đồng thuận A/B ở mục 34 được tính từ hai lượt chấm trước phân xử. [Bản kê truy vết](../../outputs/m2_anchor_semantic_review/20261111_chot_phan_xu_ab_v2/experiment_manifest.json)

## 37. Độ phủ tần suất bài nguồn cho bộ neo M2 V3.1 — 2026-11-11

1. **Đối chiếu nguồn và kết quả chấm.** Kiểm lại 1.425 phiếu có căn cứ thời gian với hồ sơ bản lưu đã kiểm chứng. Nối bộ 24 phiếu đã chốt về FactVersion, mã bài và đúng phiên bản thân bài. Có 15 phiếu đạt nội dung và kiểu, với đoạn dẫn khớp nguyên văn, vị trí và SHA-256. [15 phiếu và bản lưu](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/phieu_dat_noi_dung_cho_anh_xa.json)
2. **Tính theo từng cutoff nguồn.** Lấy giao thực thể của hai snapshot canonical và bậc của từng thực thể ở snapshot nguồn. Gộp theo thực thể, nguồn xuất bản và mã bài sau khi lọc mốc bản lưu `<= cutoff`. Đối chiếu riêng việc FactVersion có xuất hiện trong snapshot đầy đủ tại mốc đó. Ca có mốc bằng cutoff T04 được tính. [Bảng theo thực thể](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/do_phu_theo_thuc_the.parquet)
3. **Kiểm tra hiệu lực ánh xạ.** Cả 1.958 dòng truy vết đều thiếu `mapping_available_at_verified`. Danh mục V3.1 thiếu bảng lịch sử ánh xạ `entity_mapping_versions`. Tần suất của 6.897 dòng thực thể–chuyển tiếp được ghi trống với trạng thái *chưa xác minh*. Tần suất bằng 0 cần hồ sơ đủ để xác nhận vắng bằng chứng trong phạm vi đếm. Hiện có 0 thực thể được xác nhận tần suất bằng 0. [Lược đồ ánh xạ](../../config/schema.yaml#L111) · [Báo cáo độ phủ](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/bao_phu_neo.json)

| Chuyển tiếp | Thực thể chung | Có mốc trong snapshot nguồn | Có bài đạt nội dung và mốc, chờ ánh xạ | Thực thể có tần suất đã xác minh |
| --- | ---: | ---: | ---: | ---: |
| T01→T02 | 167 | 167 | 8 | 0 |
| T02→T03 | 343 | 343 | 10 | 0 |
| T03→T04 | 503 | 503 | 13 | 0 |
| T04→T05 | 646 | 646 | 17 | 0 |
| T05→T06 | 787 | 787 | 18 | 0 |
| T06→T07 | 936 | 936 | 24 | 0 |
| T07→T08 | 1.057 | 1.001 | 24 | 0 |
| T08→T09 | 1.176 | 1.085 | 26 | 0 |
| T09→T10 | 1.282 | 1.143 | 26 | 0 |

**T01→T02 thiếu nhiều hồ sơ nhất so với quy mô neo yêu cầu.** Mốc nguồn là 01/06/2025 lúc 01:05:48 UTC. Bốn phiếu đạt nội dung có bản lưu đến mốc này, liên quan đến 8/167 thực thể chung. Ba phiếu gắn FactVersion có trong snapshot T01 đầy đủ. Phiếu NIC–FPT có bản lưu ngày 01/04/2025 và bộ ba đã hiện diện trong T01, nhưng FactVersion gắn với phiếu lưu mốc cũ vào tháng 09/2026. Bảng ghi hai mốc ở đúng vai trò của chúng. Nếu chỉ bổ sung ánh xạ cho 8 thực thể đã có căn cứ nội dung và mốc, vẫn còn 159 thực thể cần làm rõ để đạt quy mô 101 neo khớp và 66 neo giữ riêng. Trong phạm vi FactVersion của T01, có 123 phiếu đã có mốc nhưng chưa chấm ở lượt V2, thuộc 65 bài nguồn phân biệt. [Báo cáo độ phủ](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/bao_phu_neo.json)

Đã thực hiện trên hồ sơ thật (**EXECUTED**) và tính lại độc lập giao thực thể, bậc, phép khử trùng bài, số đếm và trường hợp bằng cutoff (**VERIFIED** trong phạm vi độ phủ). **0/9 chuyển tiếp đủ hồ sơ để khóa bộ neo.** Đầu vào còn thiếu là lịch sử ánh xạ có phiên bản và thời điểm hiệu lực, cùng hồ sơ nội dung cho phần thực thể chưa đủ căn cứ. [Trình kiểm tra](../../scripts/audit_m2_anchor_frequency_coverage.py) · [Bản kê truy vết](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/experiment_manifest.json)

## 38. Kiểm tra phương án ánh xạ trên bốn phiếu của T01 — 2026-11-11

Đã kiểm tra hai khả năng trên bốn phiếu đạt nội dung và có bản lưu đến **01/06/2025 lúc 01:05:48 UTC**. Khả năng thứ nhất là tìm bản ghi lịch sử trong kho M1 gốc. Khả năng thứ hai là tìm nguyên văn từng tên trong đúng đoạn đã chốt và tính lại mã theo quy tắc ghi trong mã nguồn M1. [Báo cáo độ phủ đầu vào](../../outputs/m2_anchor_article_readiness/20261111_do_phu_tan_suat_v1/bao_phu_neo.json)

| Phiếu | Tên trong đoạn đã chốt | Mã tính lại khớp V3.1 | Mốc hiệu lực ánh xạ đã xác minh |
| --- | --- | ---: | ---: |
| NIC–FPT | NIC, FPT | 2/2 | 0/2 |
| Images in ChatGPT–GPT-4o | Images in ChatGPT, GPT-4o | 2/2 | 0/2 |
| Redmi Note 14 Pro+ 5G–Redmi Note 14 | Redmi Note 14 Pro+ 5G, Redmi Note 14 | 2/2 | 0/2 |
| Boston Dynamics–Nvidia | Boston Dynamics, Nvidia | 2/2 | 0/2 |

Cả **8/8 mã** xuất hiện trong cả T01 và T02. Quy tắc tính mã lấy tám ký tự đầu của SHA-256 trên tên UTF-8 sau khi bỏ khoảng trắng đầu cuối và chuyển chữ thường, rồi thêm tiền tố `ent_`. Ca Redmi được đối chiếu bằng hai đoạn tên tách biệt vì tên ngắn cũng là tiền tố của tên dài. Phép thử dùng tên đã trích xuất để tìm lại đúng lát cắt trong bản lưu. Kết quả xác nhận khả năng tái lập mã trên phạm vi tám thực thể. [Lát cắt, mã và thời điểm theo từng tên](../../outputs/m2_anchor_article_readiness/20261111_kiem_tra_anh_xa_t01_v1/doi_chieu_anh_xa_t01.json)

| Trường kiểm toán | Kết quả |
| --- | --- |
| Mã và mức độ | **M2-ALIGN-05 · HIGH** |
| Thành phần | Kho M1 gốc có `data/manifests/entity_map_v1.json`, `runs/production_v3/inputs/proposed_config_bundle.yaml` và `src/kg_pipeline/adjudicate.py`. Gói V3.1 có `tables/fact_versions.parquet`. |
| Điều kiện | Hồ sơ từng tên phải có mã chuẩn, phiên bản, căn cứ ánh xạ và `mapping_available_at <= cutoff` theo Stage 4.8 và 4.14. |
| Kết quả và chứng cứ | Danh mục ánh xạ hiện tại và hai bản trong lịch sử Git đã kiểm đều có 0 byte. Cấu hình mà trình phân xử đọc thiếu danh mục thực thể. Các FactVersion của bốn phiếu có nhãn `v1_mock` và mốc nhập 28/09/2026. Mốc bản lưu ghi thời điểm quan sát đoạn báo. Trường hiệu lực ánh xạ của tám tên vẫn trống. |
| Nguyên nhân và phần chưa rõ | Mã đã xem tạo mã dự phòng từ chuỗi tên và lưu nhãn phiên bản vào FactVersion. Các hồ sơ khả dụng thiếu bản ghi có thời điểm hiệu lực cho từng tên. Việc có bản lưu khác ngoài kho đã kiểm vẫn chưa xác định. |
| Tái lập và kiểm thử | Chạy `python scripts/audit_m2_anchor_mapping_replay.py <thư_mục_kết_quả_mới>`. Đã kiểm thử trường hợp tên Redmi lồng nhau và tính lại độc lập mã, vị trí tên, giao hai snapshot và thứ tự thời gian. |
| Hướng xử lý | Tìm bản sao có lịch sử ánh xạ từng tên và căn cứ về ngày hiệu lực. Nếu chọn dùng phép tái lập cho mục đích khoa học, cần đăng ký rõ điều kiện sử dụng, cách kiểm tra va chạm và cách xử lý tên khác nhau. Ghi thời điểm tái lập thực tế riêng với thời điểm quan sát bản lưu. |

Đã thực hiện trên hồ sơ thật (**EXECUTED**) và kiểm chứng khả năng tái lập mã (**VERIFIED** trong phạm vi thử). **0/8 thực thể có mốc hiệu lực ánh xạ được xác minh.** Bốn phiếu vẫn chờ căn cứ ánh xạ trước khi dùng để tính tần suất ở T01. [Bản kê truy vết](../../outputs/m2_anchor_article_readiness/20261111_kiem_tra_anh_xa_t01_v1/experiment_manifest.json)

## 39. Thử tái lập ánh xạ cho 167 thực thể chung T01→T02 — 2026-11-11

1. **Xác định phạm vi.** Tính lại giao 167 thực thể từ hai snapshot canonical. Lấy 127 FactVersion thuộc T01 có bản lưu đến 01/06/2025 lúc 01:05:48 UTC. Kiểm tra riêng 52 phiếu bổ sung có bản lưu đến mốc và có ít nhất một thực thể thuộc giao. Các FactVersion gắn với 52 phiếu này nằm ngoài bản T01 đầy đủ. [Đối chiếu theo thực thể](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/doi_chieu_toan_bo_t01.json)
2. **Xác minh nguyên văn và tính lại mã.** Đối chiếu tên và mã giữa mệnh đề, FactVersion và hàng chờ. Kiểm SHA-256 thân bài, đoạn gốc và ngữ cảnh. Tìm chuỗi tên có ranh giới từ rồi dùng đúng lát cắt trong bản lưu để tính lại mã. Với hai tên lồng nhau, yêu cầu vị trí độc lập cho tên ngắn. Mức vị trí của mỗi thực thể dùng lần xuất hiện có căn cứ gần đoạn gốc nhất. [Vị trí tên theo phiếu](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/vi_tri_ten_theo_phieu.parquet)
3. **Kiểm tra trùng mã và truy vết.** Tính lại từ tên lưu trong hồ sơ khớp mã V3.1 ở **167/167 thực thể**. Trong phạm vi này có 0 va chạm giữa các chuỗi chuẩn hóa khác nhau, 0 chuỗi chuẩn hóa gắn nhiều mã và 0 mã gắn nhiều chuỗi chuẩn hóa. Các số đếm đo tính nhất quán của tên và mã trong dữ liệu đã kiểm. Việc phân giải hai đối tượng dùng chung một tên cần căn cứ về đối tượng. [Bản kê truy vết](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/experiment_manifest.json)

| Vị trí có tên nguyên văn độc lập | Chỉ từ FactVersion T01 | Gộp bản lưu bổ sung |
| --- | ---: | ---: |
| Đoạn trích gốc | 121 | 128 |
| Ngữ cảnh liền kề | 41 | 34 |
| Phần khác trong thân bài | 1 | 2 |
| Tổng số thực thể có tên và mã tính lại khớp | **163/167** | **164/167** |
| Còn thiếu tên độc lập | 4 | 3 |

Bản lưu bổ sung cung cấp tên **Bộ Công an** ở phần khác trong thân bài. Ba tên còn lại là **iOS, iPadOS và macOS**. Trong các phiếu tương ứng, các chuỗi này nằm trong tên phiên bản **iOS 18.4, iPadOS 18.4 và macOS 15.4**. Quy tắc thử yêu cầu vị trí độc lập nên ba tên dòng hệ điều hành giữ trạng thái cần căn cứ bổ sung. Việc suy tên dòng từ tên phiên bản cần quy tắc có căn cứ và được xác nhận trước khi dùng. [Kết quả từng thực thể](../../outputs/m2_anchor_article_readiness/20261111_tai_lap_anh_xa_toan_t01_v1/doi_chieu_toan_bo_t01.json)

Đã thực hiện trên hồ sơ thật (**EXECUTED**) và kiểm lại độc lập **342 lượt tên**, các vị trí, mã tính lại và mã băm tệp (**VERIFIED** trong phạm vi phép thử). Bảng lưu riêng thời điểm bản lưu và thời điểm thực hiện tái lập. Có **0/167** mốc hiệu lực ánh xạ lịch sử đã xác minh. Kết quả là căn cứ để xem xét phương án tái lập và cách xử lý ba tên dòng hệ điều hành trước khi tính tần suất bài nguồn. [Trình kiểm tra](../../scripts/audit_m2_anchor_mapping_t01_full.py)

## 40. Duyệt phương án tái lập ánh xạ T01→T02 — 2026-11-11

Theo xác nhận của người dùng, đã duyệt phiên bản 1 để lập và kiểm chứng hồ sơ cho 167 thực thể chung T01→T02. Quy tắc yêu cầu đúng bản lưu đến cutoff, đúng vị trí tên, cùng cách tạo mã và đối chiếu mã V3.1. Phương án ghi riêng thời điểm quan sát bản lưu, thời điểm tái lập và mốc hiệu lực ánh xạ có căn cứ. [Văn bản đã duyệt](M2_PHUONG_AN_ANH_XA_T01_20261111.md)

Với iOS, iPadOS và macOS, ưu tiên tên dòng độc lập. Có thể dùng tên phiên bản khi ngữ cảnh cùng bản lưu xác lập rõ phiên bản thuộc dòng. Ba trường hợp hiện có giữ trạng thái *chưa xác minh* vì căn cứ mới khớp chuỗi đầu trong tên phiên bản. [Quyết định đã ghi](../../decisions/decision_log.jsonl#L15)

Đã kiểm mã băm của tài liệu và biên nhận, đối chiếu nội dung quyết định với dòng mới trong nhật ký và xác minh tiền tố lịch sử khớp từng byte. Kết quả hiện có là **164/167 mã tái lập được từ bản lưu** và **0/167 mốc hiệu lực đã xác minh**. Việc tính tần suất nghiên cứu chính tiếp tục dựa vào hồ sơ có ánh xạ hiệu lực đến cutoff, thẩm định nội dung và thời gian ở cấp bài. [Biên nhận phê duyệt](../../outputs/m2_anchor_article_readiness/20261111_duyet_anh_xa_t01_v1/quyet_dinh_anh_xa_t01.json) · [Bản kê truy vết](../../outputs/m2_anchor_article_readiness/20261111_duyet_anh_xa_t01_v1/experiment_manifest.json)

## 41. Lập hồ sơ tám ánh xạ và rà tên hệ điều hành trước T01 — 2026-11-11

Đã áp dụng phương án phiên bản 1 cho tám thực thể của bốn phiếu T01. Mỗi hồ sơ có tên nguyên văn, vị trí Unicode, mã V3.1, mã tính lại, SHA-256 thân bài và đoạn, mốc bản lưu cùng mốc nhập FactVersion. Đối chiếu lại các dòng khôi phục của bốn FactVersion, tệp danh mục M1 và bảng lịch sử ánh xạ. Kết quả là **0/8 mốc hiệu lực ánh xạ có căn cứ xác minh**. Trường hiệu lực của tám hồ sơ được ghi trống. [Tám hồ sơ ánh xạ](../../outputs/m2_anchor_article_readiness/20261111_ho_so_anh_xa_t01_v1/ho_so_8_anh_xa_t01.json)

Rà các bản lưu đã kiểm ở hai lượt trước và 322 lần thu đủ điều kiện trong Stage 4.4 v2 đến cutoff T01. Sau khi gộp các bản trùng, có **314 bản lưu với 302 thân bài phân biệt**. Đã đối chiếu SHA-256 văn bản và tái tạo **11 HTML** có tên cần kiểm. Với các ứng viên từ Stage 4.4 v2, mốc bản lưu được đối chiếu với URL replay, header Memento và dòng nhật ký thu. [Vị trí tên và hồ sơ bản lưu](../../outputs/m2_anchor_article_readiness/20261111_ho_so_anh_xa_t01_v1/ban_luu_ten_he_dieu_hanh_t01.json)

| Tên dòng | Bằng chứng trong bản lưu đến cutoff | Kết quả |
| --- | --- | --- |
| iOS | Bài **4882718**, bản lưu **12/05/2025 03:51:43 UTC**, có cụm “hệ điều hành iOS” tại vị trí tên `[2506, 2509)`. | Tên độc lập, mã tính lại `ent_48ee0460` khớp V3.1. |
| macOS | Bài **4883254**, bản lưu **11/05/2025 00:15:51 UTC**, nêu “macOS nhận được bản cập nhật” tại vị trí tên `[2116, 2121)`. | Tên độc lập, mã tính lại `ent_a0c0485e` khớp V3.1. |
| iPadOS | Hai lần xuất hiện trong phạm vi rà đều đi với số phiên bản, gồm **iPadOS 18.4** và **iPadOS 19**. | Chờ tên dòng độc lập hoặc đoạn xác lập rõ phiên bản thuộc dòng. |

Hai đoạn mới bổ sung căn cứ về tên dòng từ hai bài khác. Khi gộp với phép thử mục 39, độ phủ tên nguyên văn đạt **166/167 thực thể** trong phạm vi hồ sơ đã rà. Phần cần xử lý tiếp là đoạn dẫn cho iPadOS và căn cứ hiệu lực ánh xạ theo cutoff. Tần suất nghiên cứu chính chờ đủ điều kiện đã duyệt ở mục 40. [Biên nhận và bản kê truy vết](../../outputs/m2_anchor_article_readiness/20261111_ho_so_anh_xa_t01_v1/experiment_manifest.json)

Đã thực hiện trên hồ sơ thật (**EXECUTED**) và kiểm lại nguyên văn, offset, bản ghi thu và mã băm của các đoạn cùng tám hồ sơ (**VERIFIED** trong phạm vi truy vết). [Trình kiểm tra](../../scripts/audit_m2_anchor_mapping_t01_evidence.py)
