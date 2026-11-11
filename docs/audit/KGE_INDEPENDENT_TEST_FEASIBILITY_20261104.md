# Rà soát khả năng lập tập kiểm thử độc lập — 04/11/2026

Đã thực hiện và kiểm chứng bước rà soát trong phạm vi **gói canonical data3.1 T01–T10** và các run có manifest liên kết. Chưa xác lập được tập kiểm thử độc lập đủ điều kiện trong phạm vi này.

## Kết quả

| Kiểm tra | Kết quả |
|---|---:|
| Snapshot có lịch sử huấn luyện backbone toàn snapshot | 10/10 |
| Job backbone khớp hash snapshot và seed | 30/30 |
| Triple canonical phân biệt từng xuất hiện trong huấn luyện backbone | 1.205/1.205 |
| Triple xuất hiện lần đầu trong chuỗi snapshot sau T01 | 1.084 |
| Triple trong nhóm trên có cả hai thực thể và quan hệ trong train T01 | 26 |
| Triple trong nhóm trên có ít nhất một ID ngoài train T01 | 1.058 |

Run backbone đã dùng toàn snapshot với tỷ lệ validation bằng 0. Pilot chọn số chiều dùng validation T01 và kiểm tra khả năng căn chỉnh T01/T02. Pilot ngày 03/11 dùng lại đúng 101 triple train và 20 triple validation T01. Trong 26 triple có đủ ID đã thấy, 2 triple thuộc T02 và 24 thuộc T03–T10. Hai triple trong nhóm 26 có ít nhất một khóa truy vấn head hoặc tail trùng với validation cũ, dù bản thân triple khác.

26 triple này nằm ngoài train và validation của các checkpoint pilot T01. Chúng có thể phục vụ **đối chứng hồi cứu với checkpoint T01 cố định** sau khi chốt thiết kế, với độ bao phủ chỉ 2,4% số triple xuất hiện lần đầu sau T01. Các triple này đã xuất hiện trong các run backbone khác. Phép đếm dựa trên lần xuất hiện đầu tiên trong chuỗi snapshot, nên chỉ xác định quan hệ thành viên giữa snapshot. Mốc evidence observation cần xác minh riêng nếu dùng làm tiêu chí tuyển chọn test.

## Finding KGE-TEST-001 — HIGH

| Trường | Nội dung |
|---|---|
| Thành phần ảnh hưởng | `data/evolving_kg_downstream_v3_1/config/downstream_transe_config.yaml`, `outputs/m2_pilot/20261014T031822Z_9b722664/design.json`, `outputs/m2_backbone/20261014T034042Z_65c464ba/registered_jobs.json`, `outputs/kge_validation_dev/20261103_t01_three_seed_v1/` |
| Hành vi mong đợi | Có nguồn test được giữ riêng và xác minh được lịch sử sử dụng, khóa memberships và quy tắc chấm trước khi đọc điểm |
| Quan sát | T01 validation đã phục vụ chọn cấu hình. Cả 10 snapshot canonical đều có lịch sử huấn luyện toàn snapshot. Chưa có bằng chứng về một partition độc lập đã đăng ký trong các đầu vào được rà soát |
| Bằng chứng | `audit.json` và `snapshot_counts.csv` trong thư mục kết quả. Mỗi job backbone khớp semantic snapshot hash và checkpoint có trong manifest |
| Nguyên nhân xác nhận và giới hạn | Lịch sử phơi nhiễm trong các run có hash đã được xác nhận. Lịch sử phơi nhiễm của dữ liệu ngoài phạm vi audit chưa được thiết lập |
| Tái hiện | Chạy `audit.py` từ thư mục kết quả với Python của `.venv-m1`, trong một thư mục kết quả mới để giữ báo cáo cũ |
| Sửa tối thiểu đề xuất | Xác định một nguồn dữ liệu giữ riêng có provenance và lịch sử sử dụng kiểm chứng được. Sau khi chốt phạm vi, khóa tập test, checkpoint, candidate universe, filtered positives, tie rules và baseline tần suất chỉ dùng tập train |
| Kiểm chứng | Đếm lại bằng PyArrow với thứ tự duyệt ngược và xác nhận 1.205 triple phân biệt, 1.084 triple sau T01, 26 triple đủ ID và 1.058 triple có ID ngoài train. Khớp 74 input hashes và 3 audit artifact hashes. Ruff và kiểm tra diff đạt |
| Việc còn lại | D02–D04 cần nguồn test và thiết kế đối chứng phù hợp. Quyền truy cập test khóa tiếp tục theo điều kiện W8 |

## Bàn giao

Kết quả kiểm kê nằm tại `outputs/kge_independent_test_feasibility/20261104_v1/`. Ba manifest lịch sử đã đối chiếu tổng cộng 790 artifact refs. CSV chỉ chứa số đếm theo snapshot và chưa chốt memberships cho một tập test.

Phạm vi **EXECUTED/VERIFIED** là rà soát lịch sử sử dụng, kiểm hash và đếm coverage trên dữ liệu thật. Phép chấm TransE-L2 so với baseline đang chờ thiết kế đánh giá được chốt. Đợt này chỉnh báo cáo và `docs/PROGRESS.md`. Bằng chứng tái hiện nằm trong thư mục kết quả. Xem `git diff -- docs/PROGRESS.md` và báo cáo mới.
