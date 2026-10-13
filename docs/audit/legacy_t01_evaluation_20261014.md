# Đánh giá TransE legacy T01 101/20 — 2026-10-14

## Thiết kế đã được user chốt

User chốt thiết kế ở chat trước execution. Split giữ nguyên witness đã review:
101 train, 20 held-out, 167 training entities, 10 training relations. Không
tuning, không thay split theo kết quả. Split SHA-256:
`c334701a0d2bece4be155af467832eaaa7ee1f416f58e3446f1702b193fd90cd`.

Input `data/KG_lan2/evolving_kg_downstream_v3/snapshots/snapshot_T01_canonical.parquet`;
SHA-256 `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e`.
Run `outputs/legacy_evaluation/20261013T170623Z_e7a3592e/` (UTC trong tên run;
ngày địa phương Asia/Bangkok là 14/10/2026). Design/split được ghi exclusive-create
trước training và metric computation. Không ghi vào `data/locked_test/` hoặc
decision log khoa học, không thay protocol hay guard M2 production.

- Huấn luyện từ đầu chỉ trên 101 train triples, mapping xây từ training.
- TransE-L2 dimension 32, 50 epochs, lr 0.01, margin 1.0, seeds 13/37/101;
  normalize entities bật theo cấu hình trước. SGD của repo, không warm-start.
- 40 queries: head và tail của mỗi held-out triple; candidates là toàn bộ
  167 entities, không lọc type. Đủ seen entities/relations, không loại query.
- Filtered ranking loại các positive khác trong toàn bộ 121 triples T01,
  luôn giữ gold target. Held-out positives chỉ được sử dụng ở evaluation;
  negative sampling training chỉ được truyền 101 training triples.
- Điểm TransE: âm khoảng cách L2, càng lớn càng tốt. Tie bằng đúng floating
  score dùng hạng trung bình: `1 + n_better + (n_tied_including_gold - 1)/2`.
  MRR dùng nghịch đảo hạng này, Hits@k kiểm hạng này <= k; không dùng tie-break
  lạc quan hoặc expected Hits cho tie.
- Baseline: tần suất entity xuất hiện ở head + tail trong 101 training triples,
  không điều kiện hóa theo relation. Cùng candidates/filter/ties với TransE.
- 7/10 relations ở held-out; 4/20 triples có entity pair đã có cạnh khác trong
  train. Không bỏ các triple này sau khi xem điểm. 40 queries không phải 40
  quan sát độc lập; đây không phải QA panel chính thức.

## Kết quả

| Model | MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---:|---:|---:|---:|
| Frequency baseline | 0.056464 | 0% | 7.5% | 20% |
| TransE seed 13 | 0.104897 | 0% | 15% | 30% |
| TransE seed 37 | 0.084878 | 0% | 10% | 25% |
| TransE seed 101 | 0.093864 | 0% | 10% | 22.5% |

Mean MRR mô tả qua ba seeds: 0.094546. Tất cả seeds cao hơn baseline trên
split này; không suy ra ý nghĩa thống kê hoặc chất lượng chung của graph.
Hits@1 bằng 0 cho thấy chưa có gold ở rank 1 trong các lượt chấm này. Không
chọn seed tốt nhất làm kết quả chính hoặc retune bằng held-out.

Results JSON có điểm tách head/tail. Từng ranking row lưu candidate scores,
target score, số bị filter, số tốt hơn và số tie để kiểm lại độc lập.

## Xác minh và lineage

- IMPLEMENTED: `scripts/evaluate_legacy_t01.py`, `tests/test_legacy_ranking.py`.
- TESTED: 8 tests ranking + split audit PASS. Ruff toàn repo không có lỗi,
  có ba warning quyền đọc thư mục fixture cũ. Diff check PASS.
- EXECUTED: Training/evaluation legacy trên T01 thật; không chạy production stage.
- VERIFIED: Tính lại độc lập **160 ranking rows** (baseline + ba seeds) từ
  checkpoint/frequencies, dựng lại candidate/filter và tính rank bằng vị trí
  trong sorted scores. Scores/ranks/MRR/Hits khớp. Hash artifacts, manifest
  required fields và checkpoint round-trip đạt. Input giữ nguyên hash.

Manifests từng seed có commit, dirty_state, data/train/query/mapping/config/split
hashes, environment và output hashes. Code thực tế được copy vào run kèm hash.
Base commit `6ef3ff5`, working tree dirty, chưa commit/push trong lượt này.
Python 3.12.10; chưa kiểm tra trên Python 3.10/3.11 hoặc hệ khác. RAM không đo,
ghi null rõ ràng. Chưa chạy repeat training cho phép đánh giá 101/20; kết quả
replay ở báo cáo trước chỉ áp dụng cho smoke experiment dùng đủ 121 triples.

## Giới hạn và điểm dừng

Mẫu nhỏ, coverage constraint thiên về repeated entities, chỉ một split. Các
blocker mapping `v1_mock`, upstream provenance và certification của v3 còn
nguyên. Không suy ra khả năng drift/alignment, temporal validity, multi-hop QA,
hay mở gate. Gate A/G1/G2 và M2 production tiếp tục BLOCKED.

Dừng sau báo cáo; không tự tuning, mở snapshot tiếp theo hoặc merge main.
Tái hiện bằng `python scripts/evaluate_legacy_t01.py` sẽ tạo run mới, yêu cầu
đúng hash input và witness audit đã review; không ghi đè artifacts cũ.
