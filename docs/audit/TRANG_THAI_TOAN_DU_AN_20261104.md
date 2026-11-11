# Kiểm tra trạng thái toàn dự án

Ngày 04/11/2026. Nhánh `codex/validation-remediation`, commit nền `eadf22abc436dcbe2f12ae850ed9a5e4382dc714`.

## 1. Kết luận

**M1 đã bàn giao V3.1 trong phạm vi Stage 4.18.** Bản phát hành hiện có khớp toàn bộ danh mục. Lần kiểm tra này xác nhận cần phân biệt việc giữ và sử dụng gói bàn giao với yêu cầu chứng nhận G1/G2 của lần chạy khoa học. Chưa có bằng chứng từ lượt quét cho thấy cần dựng lại toàn bộ M1.

**Backbone TransE-L2 cũ còn nguyên và đọc được. Việc tái sử dụng hiện có điều kiện.** Mã và môi trường của nhánh hiện tại khác bản huấn luyện lưu trong hồ sơ. Gói căn chỉnh cũ cũng còn nguyên các tệp đầu ra, nhưng kiểm tra đầy đủ dừng do mã băm giao thức khác bản đã dùng. Vì vậy, cần giải quyết chuỗi nguồn gốc của các kết quả trước khi quyết định huấn luyện lại hoặc dùng tiếp để đo độ trôi.

**M4 có kết quả khảo sát lịch sử.** H1 chưa cho thấy mối liên hệ rõ, đối chứng độ trôi giả cần thay bằng bằng chứng thực nghiệm cùng snapshot, và H2 chưa có đáp án ngoài tập đã thấy ở T01. W7 chưa khóa nên lần chạy xác nhận W8 chưa sẵn sàng.

## 2. Quy trình rà soát

1. Kiểm kê toàn cây tệp được Git theo dõi, thay đổi đang có, nhánh và thẻ. Đọc giao thức, bản kê, trạng thái và mã thực thi ở các điểm bàn giao M1–M4. Tổng kiểm kê gồm **402 tệp được theo dõi**, trong đó có 63 tệp dưới `src/`, 48 dưới `scripts/`, 86 dưới `tests/` và 112 dưới `docs/`. Ban đầu có 12 tệp đã sửa và 25 tệp mới chưa theo dõi. Các tệp báo cáo và công cụ mới của lượt kiểm tra được bổ sung sau mốc đó.
2. Chạy toàn bộ kiểm thử trên Python 3.11.9, Ruff, kiểm tra khoảng trắng Git, xác minh W1 nghiêm ngặt, kiểm tra mã G1 và xác minh W7 nghiêm ngặt. Gọi bộ kiểm tra khoa học G1/G2 với định danh sản xuất ghi trong gói.
3. Tính lại kích thước và SHA-256 của toàn bộ tệp được liệt kê trong V3.1. Đọc báo cáo đối chiếu Neo4j đã lưu. Kiểm tra sự hiện diện của dữ liệu thô ở đúng đường dẫn tham chiếu. Phần kiểm tra này dùng dữ liệu và hồ sơ cục bộ.
4. Chạy kiểm tra chỉ đọc cho backbone, cấu hình phép đo và gói căn chỉnh. Đối chiếu tệp kết quả nhiễu, độ trôi, hỏi đáp và thống kê của các lần chạy được chỉ đích danh. Tính lại MRR và số đáp án ngoài tập đã thấy từ bảng hỏi đáp.
5. Kiểm tra riêng từng run con của pilot T01 và đối chiếu mã băm của pilot, phép đối chứng hồi cứu và hồ sơ kiểm thử tiến cứu. Dữ liệu khóa nằm ngoài phạm vi đọc. Trạng thái lần này phản ánh kiểm toán và kiểm tra kỹ thuật, chưa có lần thực thi khoa học mới.

## 3. Bảng trạng thái hiện tại

| Phần | Kết quả đã xác minh | Điều còn mở |
|---|---|---|
| **Nền tảng và kiểm thử** | W1 nghiêm ngặt đạt và xác minh đủ ba tài liệu nguồn. Python 3.11.9 có **688 kiểm thử đạt, 10 bỏ qua**. Ruff và kiểm tra diff đạt. Kiểm tra mã G1 đạt 4/4 | 10 kiểm thử bỏ qua nằm trong bộ bất biến, gồm 8 cho KGE/căn chỉnh/nhiễu/độ trôi/hỏi đáp, một cho Arm C và một cho bảo vệ tập khóa. Python 3.10 có trong cấu hình CI, chưa được chạy lại tại máy này |
| **M1 — bàn giao V3.1** | **4.871/4.871** tệp trong bản kê khớp kích thước và SHA-256. Báo cáo đọc lại Neo4j đã lưu ghi **10/10** snapshot khớp tập nút và cạnh. Stage 4.18 có trạng thái đạt trong báo cáo bàn giao | Gói phát hành ghi phạm vi chứng nhận toàn M1 là `NOT_CERTIFIED_BY_THIS_PACKAGE`. Phép kiểm tra này đối chiếu báo cáo Neo4j đã lưu. Trong **5.168** tham chiếu dữ liệu thô bên ngoài gói, **0** tệp có mặt ở đúng đường dẫn đã khai báo trong checkout này. Con số đó chỉ phản ánh các đường dẫn tham chiếu, chưa kết luận về các bản phục hồi hoặc kho nguồn khác |
| **M1 — chứng nhận khoa học** | Kiểm tra hợp đồng xác nhận **9/17 bảng** lệch trường. Cả G1 và G2 trả trạng thái bị chặn cho `production_v3`, với 0 kiểm tra khoa học được thực hiện vì thiếu run manifest và hồ sơ nghiệm thu tương ứng | Cần đối chiếu bằng chứng producer cho đoạn nguồn, ánh xạ theo cutoff và tái tạo snapshot. Phân biệt sai lệch hợp đồng của mã hiện tại với lỗi trong chính snapshot bàn giao |
| **M2 — backbone** | **30 tổ hợp snapshot–seed**, **60 tệp checkpoint** và **176 tệp trong bản kê** khớp. 30 cặp tệp đã lưu từ hai lần lặp khớp byte. Ba checkpoint T01 có validation thuộc một gói pilot riêng | Công cụ hiện trả `SAVED_ARTIFACTS_VALID_REUSE_CONDITIONAL`. Bốn tệp mã khác bản đã lưu là `scripts/inspect_m2_inputs.py`, `src/kge/checkpoint.py`, `src/kge/model.py`, `src/kge/trainer.py`. Bản Windows hiện tại cũng khác. Tính tương thích khi đọc checkpoint đã được kiểm tra. Việc xác nhận dùng lại cho phiên mới vẫn cần đầu vào và thiết kế đã duyệt |
| **M2 — căn chỉnh, nhiễu và độ trôi** | **269 tệp căn chỉnh** khớp mã băm. Các gói nhiễu và độ trôi v2 lịch sử đều khớp **11/11 tệp** trong bản kê tương ứng. Các bảng lịch sử ghi 6.897 quan sát thực thể qua 9 chuyển tiếp | Trình kiểm tra căn chỉnh dừng vì giao thức hiện tại khác mã băm đã lưu. Đăng ký phép đo v2 vẫn bị chặn bởi **12 điều kiện**. Ngưỡng sai số trực giao ghi `1e-5` trong quyết định và `1e-6` trong cấu hình ứng viên |
| **M3 — mô-đun hỗ trợ** | Kiểm kê `src/paths/` và `src/auditor/` cho thấy mỗi mô-đun mới có tệp khai báo | Arm C, quy tắc quay về B và kiểm toán ngữ nghĩa chưa có chuỗi đánh giá được kiểm chứng. Đây là nhánh hỗ trợ. QLoRA thuộc phần mở rộng |
| **M4 — hỏi đáp và thống kê** | Bảng được lưu có **147 truy vấn** gồm 121 một bước, 26 hai bước, **9 chuyển tiếp và 1.323 dòng**. Có thể tính lại MRR từ thứ hạng đã lưu. Hệ số H1 lịch sử là **−0,003665**, với **p = 0,574** | Tập hiện tại có 0 dòng đáp án ngoài T01. Cần kiểm chứng quy tắc đủ thực thể hỗ trợ, tách quần thể H2, tạo đối chứng độ trôi giả từ quan sát cùng snapshot và có quy trình chấm và thống kê riêng với đầu vào được ràng buộc |
| **W7/W8 — khóa và xác nhận** | Mẫu bản kê W7 và công cụ kiểm tra có mặt. Chế độ CI kiểm tra khung W7 đạt | W7 nghiêm ngặt dừng ở giá trị chưa chốt trong `configs/kge.yaml`. Chưa có `w7_freeze.yaml` và thẻ `protocol-v1-frozen`. Cần hoàn tất hồ sơ này cùng các kiểm tra áp dụng trước W8 |
| **Đánh giá chất lượng embedding bổ sung** | Tính lại **150 epoch và 6.000 dòng thứ hạng xác thực** cho pilot T01. Gói đối chứng hồi cứu trên 52 truy vấn và hồ sơ tiến cứu khớp mã băm đầu ra | Kết quả hồi cứu giới hạn ở 26 bộ ba đủ định danh. Nguồn kiểm thử độc lập mới ở mức dự thảo, với quy trình thu và phân vai đã diễn tập bằng dữ liệu mô phỏng |

## 4. Các phát hiện cần xử lý

### STATUS-01 · Cao · Bàn giao và chứng nhận M1

- **Tệp liên quan.** `data/evolving_kg_downstream_v3_1/release_manifest.json`, `config/schema.yaml`, `src/kg_pipeline/gates.py`, `runs/production_v3/run_manifest.yaml`.
- **Yêu cầu.** Chứng nhận khoa học cần bản kê producer, mốc thời gian và ánh xạ theo cutoff cùng bằng chứng G1/G2.
- **Bằng chứng và nguyên nhân xác nhận.** Bản kê bàn giao khớp 4.871 tệp. Bộ kiểm tra G1/G2 dừng ở run chưa được khởi tạo và hợp đồng M1 còn lệch trường. Các kiểm tra này chưa xác định công đoạn sản xuất nào cần chạy lại.
- **Tái hiện, xử lý và kiểm tra tiếp.** Chạy công cụ kiểm kê bên dưới. Ưu tiên yêu cầu hoặc tìm hồ sơ producer và quyết định về trường lệch. Chỉ mở lại công đoạn bị ảnh hưởng khi có bằng chứng cụ thể. Chứng nhận lại cần kiểm tra dữ liệu thật, tái tạo snapshot và đối chiếu theo phạm vi áp dụng.

### STATUS-02 · Cao · Khả năng tái sử dụng và nguồn gốc M2

- **Tệp liên quan.** `configs/m2_data_3_1_candidate_v2.yaml`, `configs/m2_measurement_v2_candidate.yaml`, `configs/protocol_v1.yaml`, `decisions/decision_log.jsonl`, các bản kê backbone và căn chỉnh.
- **Yêu cầu.** Đầu vào, mã và cấu hình của phép đo cần có phiên bản truy vết được và nhất quán với quyết định đã duyệt.
- **Bằng chứng và nguyên nhân xác nhận.** Trình kiểm tra backbone xác nhận tệp còn nguyên nhưng phát hiện khác mã và môi trường. Trình kiểm tra căn chỉnh dừng ở `configs/protocol_v1.yaml`. Mã băm giao thức cũ `61d1eb47…` khớp các bản Git `cc411c6` và `abeb425`. Bản hiện tại là `fafd8f34…`. Có 32 đường dẫn đầu vào dưới gói V3 cũ không còn ở vị trí đã lưu. Tại vị trí tương ứng trong V3.1, 30 tệp snapshot và bản kê đi kèm cùng tệp ranh giới khớp mã băm cũ. Tệp cấu hình downstream có mã băm khác. Đây là khác biệt phiên bản và vị trí được xác nhận, chưa phải bằng chứng sai số hình học. Ngưỡng trực giao khác giữa quyết định và cấu hình vẫn chưa được hòa giải.
- **Tái hiện, xử lý và kiểm tra tiếp.** Dùng công cụ kiểm kê và bản kê đã lưu. Đối chiếu gói căn chỉnh với bản đầu vào lịch sử đúng mã băm hoặc tạo lần căn chỉnh mới với thiết kế được duyệt. Sau khi chốt quy tắc tiếp nhận checkpoint, kiểm tra trường hợp đầu vào thay đổi và xác minh lại phép đo trước khi dùng cho M4.

### STATUS-03 · Cao · Chuỗi bàn giao của các kết quả lịch sử

- **Tệp liên quan.** Bốn bản kê của nhiễu v2, độ trôi v2, hỏi đáp và thống kê được liệt kê trong tệp kết quả kiểm tra.
- **Yêu cầu.** Kết quả dùng cho lần xác nhận cần commit cụ thể, mã băm đầu vào và đầu ra, cùng điều kiện bàn giao đã kiểm chứng.
- **Bằng chứng và nguyên nhân xác nhận.** Tất cả **24 tệp đầu ra** được bốn bản kê liệt kê đều khớp. Bốn bản kê ghi Git là `HEAD` và mô tả đầu vào bằng đường dẫn hoặc cấu hình, thiếu bản đồ mã băm đầu vào theo hợp đồng hiện tại. Việc tính lại mã băm ở lượt này xác nhận tệp hiện tại và không phục hồi các ràng buộc lúc tạo kết quả.
- **Tái hiện, xử lý và kiểm tra tiếp.** Chạy kiểm kê để đối chiếu từng tệp. Giữ các kết quả làm bằng chứng lịch sử. Với lần chạy mới, kiểm tra từ chối khi đổi đầu vào hoặc thiếu hồ sơ xác minh của công đoạn trước.

### STATUS-04 · Cao · Diễn giải H2 và phép đối chứng H1

- **Tệp liên quan.** `outputs/m4_eval/20261028T070316Z_064921be/recurring_qa_panel_evaluation.parquet`, `outputs/m4_stats/20261028T070316Z_064921be/h1_h2_econometric_results.json`, `reports/report_latex_final/chapters/04_empirical_results.tex`, `reports/report_latex_final/chapters/06_conclusion.tex`.
- **Yêu cầu.** Diễn giải đúng chiều chênh lệch MRR và đúng quần thể. Phép đối chứng độ trôi giả cần xuất phát từ các phép so cùng snapshot.
- **Bằng chứng.** Tính lại trên bảng đã lưu cho kết quả Arm A cố định **0,6609**, Arm B cập nhật **0,5225** trên tập ứng viên đã thấy ở T01. Mở rộng ứng viên làm MRR của B còn **0,4955**, trong khi mọi đáp án vẫn đã có ở T01. Tệp thống kê JSON cũ diễn giải theo hướng tăng hiệu năng do độ bao phủ. Bảng LaTeX ghi đúng chiều giảm và gọi phần chênh lệch là phạt OOV do có thêm ứng viên. Kết quả này đo ảnh hưởng của việc mở rộng tập ứng viên trên các câu hỏi có đáp án đã thấy ở T01. Đối chứng cũ dùng biến giả sinh từ Gaussian, như đã tái hiện ở RERUN-01. Giá trị p của phép chạy đó chưa xác nhận điều kiện đối chứng theo giao thức.
- **Tái hiện, xử lý và kiểm tra tiếp.** Đối chiếu trung bình hạng nghịch đảo theo Arm và cờ `is_gold_seen_at_t1`. Trước khi xuất kết luận mới, kiểm tra chiều B trừ A, tập ứng viên, nhóm đáp án mới, điều kiện đủ thực thể hỗ trợ và dấu vết tạo biến độ trôi giả. Hoàn thiện phép chạy xác nhận trước khi thay số liệu khoa học trong báo cáo chính.

## 5. Thứ tự công việc từ trạng thái hiện tại

1. **Chốt phạm vi sử dụng V3.1 và backbone.** Lập đối chiếu giữa điều kiện khoa học còn thiếu và hồ sơ M1 đã có. Đồng thời quyết định điều kiện tái sử dụng checkpoint và phép đo trên đúng dữ liệu đã được duyệt. Đây là bước ra quyết định từ bằng chứng, trước việc huấn luyện lại.
2. **Hòa giải đăng ký M2.** Chốt bản cấu hình có thẩm quyền và ràng buộc mã băm đầu vào. Sau đó mới xác định công đoạn M2 nào cần tính lại. Nếu checkpoint được thay, xác định lại các kết quả phụ thuộc theo chuỗi căn chỉnh, nhiễu, độ trôi và hỏi đáp.
3. **Chuẩn bị M4 và bản báo cáo khoa học.** Hoàn thiện quần thể, phép đối chứng thực nghiệm và hai công đoạn chấm và thống kê tách riêng. Ghi rõ giới hạn của các số liệu lịch sử trong báo cáo đang lưu hành.
4. **Hoàn tất điều kiện W7 trước lần xác nhận W8.** Đợt thu kiểm thử liên kết tiến cứu có thể được xem xét riêng theo mục tiêu bổ sung.

## 6. Bằng chứng và tái lập

Đã thực hiện và xác minh (**EXECUTED / VERIFIED**) trong phạm vi kiểm kê, đối chiếu mã băm, kiểm tra khả năng đọc và tính lại các số đếm được mô tả. Bản kê của lượt kiểm tra ràng buộc 57 tệp đầu vào và một tệp kết quả. Bộ kiểm thử dự án đạt mức **TESTED**. Kết quả này chưa cấp cổng khoa học. [Tệp kết quả](../../outputs/project_status_audit/20261104_v2/trang_thai_kiem_tra.json) · [Bản kê kiểm tra](../../outputs/project_status_audit/20261104_v2/experiment_manifest.json)

```powershell
.venv-m1/Scripts/python.exe scripts/audit_project_status.py outputs/project_status_audit/tai_lap_01
.venv-m1/Scripts/python.exe -m pytest -q -rs
.venv-m1/Scripts/ruff.exe check .
.venv-m1/Scripts/python.exe scripts/verify_w1.py
.venv-m1/Scripts/python.exe scripts/verify_g1.py --ci --code-checks
.venv-m1/Scripts/python.exe scripts/verify_w7.py
```

Các hồ sơ tham chiếu theo phạm vi gồm [bàn giao V3.1](../../reports/v3_1_stage_report_vi.md), [rà soát tiếp nhận V3.1](M1_V3_1_INTAKE_REVIEW_20261021.md), [kiểm toán trước khi chạy lại](PRE_RERUN_CODEBASE_REVIEW_20261103.md), [cổng nghiệm thu và khóa giao thức](../gates_and_freeze.md) và [báo cáo đánh giá embedding](KGE_EVALUATION_REPORT_20261104.md).

## 7. Chọn V3.1 và ngừng thực thi V3

### 7.1 Bằng chứng và quyết định

1. Đối chiếu 32 tham chiếu đầu vào V3 trong bản kê căn chỉnh cũ với các tệp ở vị trí tương ứng trong V3.1. **31/32** khớp SHA-256, gồm 10 Parquet chuẩn, 20 bản kê đi kèm và tệp ranh giới snapshot. Tệp `config/downstream_transe_config.yaml` có mã băm khác. Không tìm được bản gốc V3 của tệp này trong kho hiện tại để so sánh từng trường. Mốc cutoff và định danh snapshot của V3.1 đã được kiểm tra theo bản phát hành hiện hành.
2. Theo lựa chọn của người dùng, **V3.1 là gói đầu vào chuẩn duy nhất cho các lần chạy M2 mới trong luồng này**. Kiểm tra đầu vào mặc định đọc cấu hình, bản kê phát hành và các bảng bổ trợ trực tiếp từ V3.1. Công cụ kiểm tra validation T01 từ chối thư mục khác trước khi đọc snapshot.
3. Chặn tám đường chạy từng thực thi theo phạm vi V3, gồm pilot, backbone, căn chỉnh, nhiễu, độ trôi và ba lệnh huấn luyện, đánh giá, chẩn đoán T01 cũ. Giữ các bản kê, mã đã lưu, đường dẫn lịch sử và quyền phê duyệt cũ để phục vụ truy vết. Các lệnh rà soát kết quả lịch sử vẫn tham chiếu đường dẫn trong bản kê gốc. Khi cần tái lập, dùng phiên bản mã đi kèm lần chạy.
4. Trạng thái lựa chọn nguồn chỉ áp dụng cho dữ liệu và cấu hình gói. Điều kiện đăng ký phép đo M2, tái sử dụng căn chỉnh, nghiệm thu G1/G2 và khóa W7 vẫn được kiểm tra theo giao thức hiện có.

### 7.2 Kiểm chứng sau chuyển đổi

| Kiểm tra | Kết quả |
|---|---|
| Kiểm tra đầu vào trực tiếp trên V3.1 | Đạt phạm vi kỹ thuật. **10 snapshot, 9 chuyển tiếp, 37 tệp đầu vào** khớp bản kê kiểm tra. Tất cả đường dẫn đầu vào thuộc V3.1 |
| Cấu hình validation T01 đã duyệt trước đây | Chế độ kiểm tra đọc đúng 101 bộ ba huấn luyện, 20 bộ ba xác thực và ba seed. Kết quả ghi `executed=false` |
| Đường chạy V3 | Cả tám lệnh thoát với thông báo V3 đã ngừng sử dụng. Kiểm thử hồi quy xác nhận cấu hình V3 bị từ chối trước khi đọc snapshot |
| Bộ kiểm thử và định dạng | **689 đạt, 10 bỏ qua** trên Python 3.11.9. Ruff và kiểm tra khoảng trắng Git đạt |

Đã triển khai và kiểm thử thay đổi đường chạy (**IMPLEMENTED / TESTED**). Đã thực hiện và kiểm chứng kiểm tra đầu vào trên V3.1 thật (**EXECUTED / VERIFIED** trong phạm vi kỹ thuật). Kết quả không phải lần chạy huấn luyện hoặc phép đo khoa học mới. [Bản kê kiểm tra V3.1](../../outputs/m2_preflight/20261104T014424Z_79e57c2b/experiment_manifest.json)

```powershell
.venv-m1/Scripts/python.exe scripts/inspect_m2_inputs.py
.venv-m1/Scripts/python.exe scripts/run_kge_validation.py --config outputs/kge_validation_registration/20261103_t01_dev_v1/approved.yaml --check-only
.venv-m1/Scripts/python.exe -m pytest -q
```
