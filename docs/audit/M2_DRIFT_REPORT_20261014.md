# M2 — longitudinal drift và Dev handoff — 14/10/2026

Đã hoàn tất bước 7 trên nhánh `codex/m2-drift-workflow`, base `2860235`,
theo yêu cầu **"Hãy thực hiện bước tiếp theo."** sau null/LTO stage verified.
Run: `outputs/m2_drift/20261014T044648Z_ae9f0401/`.
Toàn bộ **6.897 entity×transition** có delta_time, signed excess và SED+
khả dụng theo approved Dev rules. Independent artifact validation PASS.
Đã đóng gói M2→M4 Dev handoff; dừng sau Stage Report, chưa chạy M4.

## Thiết kế trước execution

Stage config `configs/m2_drift_v1.yaml` ghi authorization mới và bind approved
configuration SHA-256, null manifest và independent null receipt SHA-256.
Không sửa configs/protocol đã dùng ở các stages trước hoặc artifact lịch sử.
Producer kiểm lại tất cả hashes của upstream inputs/artifacts và fingerprint
của verifier đã cấp receipt trước khi đo drift.

- Population: persistent canonical entity IDs của 9 adjacent transitions
  T01→T02 đến T09→T10; đủ 6.897 entity×transition, không lọc theo outcomes.
- Chỉ sử dụng 27 saved cross-time alignments cùng seed 13/37/101; không
  retrain, re-align hoặc chọn lại anchors. Saved Q và fit means đã verified.
- Mỗi seed: `delta_seed = 1-cos((x_previous-mu_source)Q, y_next-mu_target)`.
  `delta_time = median(delta_13, delta_37, delta_101)`; không lấy mean hoặc
  thêm cross-seed temporal comparisons.
- `r = delta_time - LTO_null_median`, giữ nguyên dấu âm.
  `SED_plus = max(0,r)/(1.4826*LTO_MAD + 0.0001)` khi null available.
  Epsilon, MAD guard 1e-12, min reference observations 5, degree bins 3/6
  và target exclusion đều giữ nguyên approved config.
- Undefined centered cosine/invalid alignment fatal trước khi xuất drift.
  Missing entities/seeds/identities hoặc malformed LTO support/scale fatal.
  Registered unavailable null giữ reason, SED+=None, r chỉ tính khi median
  có thật; không sinh defaults/NaN/Inf hoặc dùng epsilon cứu ZERO_MAD.
- Registered jobs/population/config/code hashes được ghi trước computation.
  Hai computation repeats/transition, hai exact Parquet serializations.
  Component version `saved_alignment_longitudinal_drift_v1`.

Engineering detail: repository package `src/statistics` che stdlib cùng tên;
dùng deterministic median helper sẵn có, luôn kiểm nonempty input. Independent
verifier dùng NumPy median. Đây là lựa chọn kỹ thuật, không đổi estimand.

## Engineering verification

Full suite **505 passed, 10 skipped** trên Python 3.11.9, gồm **26 tests mới**
của drift workflow. 75 targeted workflow/scientific tests đã PASS trước hai
support-consistency cases cuối; bản cuối được full suite kiểm đầy đủ.
Ruff toàn repo PASS, `git diff --check` PASS.

Tests kiểm median-vs-mean, signed negative được giữ/SED+ zero, positive excess
với đúng scale/epsilon, centering translation invariance, missing seed/entity,
wrong snapshot/cross-seed/semantic hash, unavailable alignment, nonfinite Q,
zero centered norm, missing/zero-MAD/insufficient null references, sai support
count/exclusion/scale và fabricated empty references. Nullable Parquet giữ
None, required fields không được null, serialization deterministic. Verifier
fixture phát hiện signed clipping, mean thay median và fabricated SED+.

10 skips là placeholder tests hiện có trong `tests/test_hard_invariants.py`;
không chuyển các skip hoặc CI green thành scientific gate PASS. Python 3.10
chưa được chạy local; nguồn giữ cú pháp tương thích 3.10/3.11.

## Execution trên artifacts thật

Lệnh: `.venv-m1/Scripts/python.exe scripts/run_m2_drift.py`.
Run hoàn tất computation/serialization trong **19,64 giây**, sau upstream
checks/load. Có **20.691 temporal observations** và **6.897 entity drift rows**,
không unavailable trên run này. **9/9** transition computation replays exact
bytes; cả **2/2** Parquet files serialize lặp lại exact bytes.

| Transition | Entities | Median delta_time | Median signed r | Median SED+ | r>0 |
|---|---:|---:|---:|---:|---:|
| T01→T02 | 167 | 0.358799 | -0.030598 | 0.000000 | 75 |
| T02→T03 | 343 | 0.833742 | 0.012604 | 0.046436 | 178 |
| T03→T04 | 503 | 0.892596 | 0.019016 | 0.089150 | 266 |
| T04→T05 | 646 | 0.927986 | 0.017416 | 0.096690 | 351 |
| T05→T06 | 787 | 0.924675 | 0.005515 | 0.032297 | 407 |
| T06→T07 | 936 | 0.938494 | 0.005733 | 0.036846 | 489 |
| T07→T08 | 1.057 | 0.942547 | 0.010263 | 0.065713 | 566 |
| T08→T09 | 1.176 | 0.948712 | 0.017000 | 0.110744 | 655 |
| T09→T10 | 1.282 | 0.942291 | 0.001978 | 0.013052 | 653 |

Tổng **3.640** rows có signed excess dương; **3.257** rows âm được giữ nguyên
và có SED+=0, không có r bằng zero. SED+ lớn nhất 5.219441. Đây là thống kê mô tả;
`r>0` không phải significance test hoặc kết luận H1/ảnh hưởng QA. Không thay
dimension/anchors/buckets/epsilon/null guards sau khi thấy các outcomes này.

## Independent validation và lineage

Lệnh:
`.venv-m1/Scripts/python.exe scripts/verify_m2_drift.py --run outputs/m2_drift/20261014T044648Z_ae9f0401`.
Verifier độc lập với production arithmetic helpers: đọc raw checkpoint JSON
và saved Q/means, dùng NumPy matrix multiplication/norm/cosine và median.
Đo lại **20.691** temporal values và **6.897** delta_time/r/SED+ rows; giữ
nullable availability, signed-negative semantics, exact persistent population,
parallel seed identity, LTO statistics/support counts và degree conditioning.

Đã kiểm **549 input hashes, 57 artifact hashes, 9 transition manifests**, raw
JSON–Parquet equality, 9 exact JSON replays, Parquet field types/nullability/
metadata và exact serialization replays. Aggregate snapshot/mapping/config/code
hashes, upstream null receipt và hash catalogs đầy đủ. Dev handoff kiểm đúng
table hashes/row counts/schema IDs, seeds/population, parent lineage, query
hash=None, M4_executed=False và scientific_certification=False.

Receipt: `independent_verification_20261014T044723Z_0f2a3d8a.json` trong run.
Status: `DRIFT_ARTIFACT_VERIFICATION_PASS`.
Receipt SHA-256:
`d1cd98a6deae0e3e031a26d5e4fd66d5ee4b72bd77abe64149181fb67f104015`.
Stage config SHA-256:
`118fc74cd09ab4ff305e56daab5e831e3d5827e083fe2561c2e2a7630ab90852`.
Verifier SHA-256:
`4bc4c8a1e76641b34b88ac8559e01ce36ed6c51987d6fcec9b74fcafe2b99c13`.

Aggregate manifest SHA-256:
`e35ff8ee51a9ee1126325d5e995f8d62e30adb4d488325d963e83d187826eeda`.
Resolved config SHA-256:
`ec81e17a9a06a36973de443e0c65b30c47e102c1547c2844fc109a448a3bd953`.

| Artifact | Rows | SHA-256 |
|---|---:|---|
| `entity_drift.parquet` | 6.897 | `749f45019e76a760cbd9515ce214e344e9f5a22d65a6a8f63063af4961c64148` |
| `temporal_displacements.parquet` | 20.691 | `ceafb2acd353bf469c51f567a343d67f5f588822216c0a854e23c7d44ce53328` |

`handoff_manifest.json` version `m2_to_m4_dev_handoff_v1` trỏ tới hai bảng
và frozen approved/null/alignment hashes. Experiment manifests mang git commit/
dirty state, input/output/config/mapping/code hashes, seed identifiers trong
registered jobs/rows, environment và access=dev. Outputs mới append-only;
upstream inputs không đổi qua run.

## Trạng thái và giới hạn

| Tier | Phạm vi đạt |
|---|---|
| IMPLEMENTED | Strict saved-artifact temporal/calibrated drift, stage config, Parquet contracts, manifests/handoff và independent verifier |
| TESTED | Fixture/scientific regressions và full suite/Ruff; không scientific gate certification |
| EXECUTED | 9 transitions trên real artifact-backed checkpoints/Q/LTO references trong external-package Dev mode |
| VERIFIED | Independent temporal arithmetic/calibration, population, lineage, replays và Dev handoff; không xác minh thêm upstream M1 temporal semantics |

M1 G1/G2 và official handoff vẫn BLOCKED/uncertified theo trạng thái trước;
không cấp scientific G3 hoặc protocol freeze. T01 high bucket chỉ có **1**
reference entity sau LTO, với **6 correlated pair observations**. Giữ support
counts trong từng drift row và limitation trong handoff; numerical availability
theo approved Dev rules không tương đương đủ statistical support cho inference.

Chưa chạy QA panel, Arms A/B/C, MRR, H1/H2, WCB hoặc pseudo-drift falsification.
Next stage là **M4 readiness**: kiểm recurring QA panel, Seen-at-T1/candidate
universes và hợp đồng nối drift→evaluation trước execution được user yêu cầu.
Không tự chạy stage đó. Không đọc locked_test hoặc rerun M1 acquisition.

## Files và diff reference

Files mới: `configs/m2_drift_v1.yaml`, `src/drift/artifact_drift.py`,
`scripts/run_m2_drift.py`, `scripts/verify_m2_drift.py`,
`tests/test_m2_drift_workflow.py`, báo cáo này. Cập nhật execution plan và
progress; giữ công việc M1 đang mở. Diff là working tree trên
`codex/m2-drift-workflow` với base `2860235`; các files M2 mới vẫn untracked,
chưa commit/push/merge và không đưa generated artifacts vào Git.
