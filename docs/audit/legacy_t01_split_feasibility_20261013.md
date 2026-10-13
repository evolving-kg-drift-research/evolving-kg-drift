# T01: khả năng chia train/evaluation — 2026-10-13

## Kết luận

T01 cho phép một phép đánh giá legacy nhỏ, có điều kiện trên entities đã thấy.
Cách chia coverage-preserving theo thứ tự hash cố định tạo được **101 train /
20 held-out**, giữ đủ 167 entities và 10 relations trong training. Đây là
witness về khả năng chia, không phải split đã khóa, không phải tối ưu số lượng
held-out, và không chứng minh đủ statistical power.

Chưa huấn luyện mới, chưa tính MRR/Hits và chưa lựa chọn split theo model scores.
Không thay dữ liệu, protocol, gate hay production loader. Chưa commit/push.

## Input và cách kiểm tra

Input: `data/KG_lan2/evolving_kg_downstream_v3/snapshots/snapshot_T01_canonical.parquet`.
SHA-256: `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e`.
Gồm 121 triples, 167 entities, 10 relations. Không đọc các snapshot khác.

Entity incidence đếm số triple chứa entity, không phải số láng giềng: 121
entities chỉ xuất hiện trong một triple. Vì vậy 88/121 triples không thể giữ
riêng để đánh giá mà vẫn bảo toàn toàn bộ entity coverage trong training.
33 triples còn lại có thể giữ riêng từng triple; không có nghĩa cả 33 có thể
đồng thời chuyển sang held-out.

Hai phép kiểm tra outcome-blind:

1. Mô phỏng công thức split hiện tại trong `src/kge/trainer.py`, dùng tỷ lệ
   20% chỉ để chẩn đoán. Công thức hash trên indexed triples deterministic,
   không phải chọn ngẫu nhiên lại nhiều lần để tìm kết quả tốt.
2. Sắp triple theo SHA-256 của JSON `[legacy-t01-feasibility-v1, h, r, t]`.
   Duyệt một lần; chỉ chuyển triple sang held-out nếu cả hai entities và
   relation vẫn còn trong train. Không tuning thứ tự hoặc ngưỡng theo outcomes.

| Cách chia | Train | Held-out | Entity trong train | Held-out có entity OOV | Held-out hoàn toàn đã thấy |
|---|---:|---:|---:|---:|---:|
| Hash hiện tại, tỷ lệ 20% | 98 | 23 | 141 | 20 | 3 |
| Coverage-preserving witness | 101 | 20 | 167 | 0 | 20 |

Hash split có 26 entity IDs chỉ xuất hiện ở held-out, không có relation OOV.
Trainer hiện tạo mapping từ toàn dataset trước khi split, nên tồn tại vector
không đồng nghĩa entity có positive training evidence. Chẩn đoán ở đây xác
định seen/OOV theo membership trong training; chưa sử dụng trainer này để đánh
giá held-out và chưa sửa semantics của trainer.

## Phạm vi đại diện của witness

| Relation | Held-out triples |
|---|---:|
| integrated_into | 2 |
| invested_in | 1 |
| partners_with | 4 |
| released_by | 5 |
| succeeded_by | 1 |
| version_of | 3 |
| works_at | 4 |

Held-out chỉ phủ 7/10 relations, thiếu acquired_by, based_on và is_CEO_of.
Coverage constraint ưu tiên entities lặp lại; không suy rộng kết quả cho
toàn bộ graph hoặc entity mới. Có 4/20 triples có cùng cặp entity (không phân
biệt hướng) đã xuất hiện trong training qua triple khác. Đây là đặc điểm
split cần công bố; chưa chứng minh là inverse leakage hoặc dữ liệu sai.

Nếu chốt witness này, đánh giá head/tail tạo 40 ranking queries nhưng chúng
không phải 40 quan sát độc lập. Không tách thêm validation từ 20 triples này
để tuning. Mô hình phải được train lại từ đầu chỉ trên 101 train triples;
checkpoint trước đó đã học cả 121 triples nên không thể dùng làm held-out model.

## Finding LTS-001

- **Severity:** MEDIUM, giới hạn thiết kế phép thử legacy.
- **Affected components/files:** input T01 nêu trên; `src/kge/trainer.py` (hash split được mô phỏng, không sửa).
- **Expected behavior/invariant:** Báo rõ population được chấm và OOV; không coi mọi vector trong mapping là learned entity.
- **Actual behavior:** 20/23 held-out triples theo diagnostic hash split có entity thiếu positive training evidence.
- **Evidence:** `outputs/legacy_split_audit/20261013T165714Z_b4c0f356/report.json`, mục `naive_trainer_hash_20_percent`.
- **Root cause vs hypothesis:** Xác nhận T01 có nhiều single-incidence entities; chưa suy luận hiệu quả prediction của TransE.
- **Reproduction:** `python scripts/audit_legacy_split_t01.py`; mỗi lần tạo report ở output directory mới.
- **Proposed minimal fix:** Chốt rõ phép thử seen-entity với witness 101/20 và công bố selection bias/OOV, hoặc duyệt thiết kế khác trước khi train.
- **Regression tests:** Bốn tests mới kiểm unique entities, simultaneous coverage/partition, order invariance, OOV/parallel-pair counts và duplicate rejection.
- **Remaining blockers:** Split/candidate/filter/tie conventions chưa được khóa cho đánh giá; scientific gates vẫn BLOCKED.

## Verification và handoff

- IMPLEMENTED: `scripts/audit_legacy_split_t01.py` và `tests/test_legacy_split_audit.py`.
- TESTED: 4 tests PASS, targeted Ruff PASS; không sửa code production.
- EXECUTED: Audit chỉ đọc trên T01 thật; không training hoặc production stage.
- VERIFIED: Partition disjoint/exhaustive, zero OOV của witness, input hash
  không đổi, kết quả không phụ thuộc thứ tự rows. Chưa kiểm chứng chất lượng prediction.

Danh sách witness train/held-out được lưu trong report, chỉ để review phương án.
Không đặt vào `data/locked_test/`. Bước tiếp theo cần chốt thiết kế ranking
legacy trước khi chạy: head/tail, candidate universe, filtered positives và
cách xử lý ties; không tự nâng kết quả legacy thành QA/MRR chính thức.
