# M2 data 3.1 — tích hợp phép đo v2 và kiểm tra đăng ký cấu hình

Ngày: 21/10/2026. M1-PASS là tiền đề người dùng; không nghiệm thu lại M1.
Phạm vi: thực hiện phần kỹ thuật của bước tiếp theo, giữ scientific activation
đóng khi sources hoặc scientific registration chưa đầy đủ.

## Kết quả

Đã nối checkpoints và saved alignments qua một đường hình học tường minh dùng
chung cho noise và temporal displacement, rồi vào median6/entity, LTO, median/MAD
và SED+. Hai stage **null** và **drift** được gọi riêng; không tự chạy stage kế tiếp.

Đường v1 và các artifacts/configs lịch sử được giữ nguyên. Đường v2 có contract
JSON riêng; chưa thay default runner cũ, chưa xuất bảng dùng cho scientific M4.
Các output v2 đều ghi `scientific_certification=false`; test PASS không cấp G3.

| File mới/sửa trong lượt này | Vai trò |
|---|---|
| `src/drift/measurement_v2.py` | Geometry, normalized diagnostics, binding và hai stage APIs |
| `scripts/run_m2_measurement_v2.py` | Gated CLI, physical file loader, canonical snapshot checks, immutable manifests/code archives |
| `scripts/verify_m2_measurement_v2.py` | Tính lại bằng NumPy từ checkpoints; không gọi production geometry/reducer/calibration |
| `configs/m2_measurement_v2_candidate.yaml` | Candidate mới, hash-bind parent cũ; trường chưa đăng ký để null |
| `configs/schemas/m2_measurement_v2.schema.yaml` | Contract stage/row v2, phân biệt physical/content hashes và availability |
| `tests/test_m2_measurement_v2.py` | 45 cases mới: numerical, corruption, file-backed integration và activation guards |
| `docs/PROGRESS.md` và báo cáo này | Trạng thái mới, bằng chứng, giới hạn; giữ lịch sử trước đó |

## Hành vi được triển khai

1. Caller phải truyền đầy đủ settings; không lấy mặc định Dev để lấp trường thiếu.
   Affine cosine dùng `(x-mu_s)Q+mu_t` với `y`; centered cosine dùng `(x-mu_s)Q`
   với `y-mu_t`. Một cấu hình duy nhất áp dụng cho cả null và temporal distances.
   Việc hỗ trợ hai estimands không đăng ký cả hai làm phương pháp chính.
2. Fit means được đối chiếu đúng fit anchors. Diagnostics tính lại covariance,
   spectrum/rank, relative Frobenius residuals và orthogonality/d từ vectors.
   Holdout dùng means của fit; denominator suy biến trả unavailable. Có guard
   kiểm objective SVD, vì Q trực giao chưa đủ chứng minh Q giải bài toán Procrustes.
3. Gap phải khai báo statistic rõ ràng; chưa chọn ngầm signed/absolute/positive
   gap. Numerical comparison tolerance của verifier/objective guard là kiểm tra
   số học của implementation; không dùng thay operating range G3.
4. Loader bắt buộc physical SHA-256 và checkpoint sidecars, kiểm canonical
   snapshot hashes/full mappings, model config và coverage sáu endpoint checkpoints.
   External anchor/bucket plans được bind bằng hashes, không tự chọn/gộp theo drift.
5. Null stage chỉ đánh giá sáu endpoint/seed-pair comparisons. Drift stage cần
   ba parallel-seed comparisons và đối chiếu lại attached null artifact với inputs.
   Việc xác minh artifact trước không tạo/ghi một production stage mới.
6. Null alignment không hợp lệ: null unavailable; không silently drop entities.
   Temporal alignment hợp lệ vẫn giữ raw distances/median, nhưng signed excess
   và SED+ null nếu null alignment hỏng. Temporal alignment hỏng: giữ đầy đủ rows,
   delta/signed excess/SED+ null cùng reason. Zero/near-zero cosine norms gây lỗi,
   không tạo khoảng cách giả. Reference thiếu support/zero MAD tiếp tục theo v2
   availability contract đã có; epsilon không cứu phép đo unavailable.
7. Stage JSON dùng row version `saved_checkpoint_drift_row_v2`, tách khỏi
   calibration core `entity_reference_longitudinal_drift_v2`. Không nhét rows có
   delta null do alignment failure vào historical Parquet schema bắt delta hữu hạn.

## Activation và input-plan contract

CLI chỉ thực hiện stage khi cấu hình/parent cho phép, sources đúng baseline,
scientific settings khớp authority và frozen input-plan hash đã đăng ký.
Máy kiểm registration tại `configs/protocol_v1.yaml:drift.measurement_v2`;
đây là engineering contract cho runner mới, không tự thêm tiêu chí G3.
Protocol hiện hành **không bị sửa** trong lượt này. Extension/registration thực
tế phải theo quy trình có thẩm quyền trước khi scientific execution.

Input-plan JSON gồm `transition_id`, `anchor_plan`, `bucket_plan`, `checkpoints`
và `alignments`. Mỗi file có path tương đối và physical SHA-256. Anchor descriptor
có thể chọn đúng transition trong historical multi-transition anchor plan.
Drift config còn phải bind `null_stage` artifact. Không có default input plan,
không private snapshots, không tự freeze một bucket plan từ outputs đã quan sát.

Plan phải cover đúng adjacent transition và toàn bộ persistent population; seed
mapping/snapshot/config phải nhất quán. Loader đọc canonical package3.1 qua
adapter đã có. Source/code/input bytes được kiểm lại trước khi lưu run mới.

## Finding M2-INT-001 — physical hash và canonical content hash

- **Severity:** HIGH. **Affected:** `src/drift/measurement_v2.py`,
  `scripts/run_m2_measurement_v2.py`, `scripts/verify_m2_measurement_v2.py`.
- **Expected:** hash bytes tệp dùng cho physical lineage; canonical JSON hash
  dùng để nhận diện nội dung, không giả định hai giá trị bằng nhau.
- **Actual:** implementation đầu so physical hash với canonical JSON hash;
  file-backed integration trên Windows từ chối JSON hợp lệ có CRLF/format khác.
- **Evidence:** `outputs/m2_measurement_v2_tests/integration_results.xml` ghi
  1 failed/39 passed, failure tại saved alignment physical/semantic lineage guard.
- **Confirmed root cause:** đồng nhất hai đơn vị hash; không phải checkpoint
  hay canonical snapshots của M1 bị sai.
- **Reproduction:** file-backed runner test với JSON được ghi qua Windows text
  mode; hoặc serialized JSON khác whitespace nhưng cùng decoded values.
- **Minimal fix:** input alignment giữ riêng record, physical SHA và canonical
  content SHA; loader xác minh bytes thật, engine kiểm content identity; outputs
  giữ riêng `alignment_hashes` và `alignment_content_hashes`.
- **Regression:** explicit physical/content separation case và file-backed
  null→drift handoff; corruption tests vẫn bắt semantic/physical checkpoint mismatch.
- **Status:** IMPLEMENTED/TESTED; chưa EXECUTED/VERIFIED measurement thật.
  Không đánh dấu scientific workflow RESOLVED từ kết quả fixture.

## Kiểm thử và thực thi thực tế

Reproduce-first collection fail vì module v2 chưa tồn tại. Sau implementation,
26 core cases PASS; file-backed test phát hiện M2-INT-001. Đã sửa bằng tách hashes,
không sửa ngưỡng để làm test qua. Review bổ sung objective guard và giữ raw temporal
khi null alignment hỏng; kết quả cuối dưới đây gồm các regression cases này.

| Kiểm tra revision cuối | Kết quả |
|---|---|
| Các tests geometry/integration mới | 45 cases, nằm trong targeted/full suite |
| Targeted v2 + historical null/drift + centered-cosine regression | **138 passed** |
| Full repository suite | **619 passed, 10 skipped** |
| Ruff toàn repository / `git diff --check` | PASS |
| Runtime đã kiểm | Python3.11.9; chưa chạy Python3.10 |

Tests dùng synthetic checkpoints/sources/registration trong pytest tmp_path,
bao gồm positive path chạy null rồi drift riêng với physical files thật của
fixtures. Không có fake approval/default được ghi vào production config.
10 skips là scaffolds sẵn có, không tính là G3 PASS.

CLI trên repo thật:

```powershell
.venv-m1/Scripts/python.exe -B scripts/run_m2_measurement_v2.py --check-only
```

Run: `outputs/m2_measurement_v2_readiness/20261021T064255Z_677b20b7/`.
Kết quả **BLOCKED**, native exit2 đúng thiết kế; không có `artifact.json` phép đo.
Run trước review cuối được giữ tại `20261021T063929Z_6394a126`, không overwrite.

Readiness chỉ ra15 blockers, gom thành: original sources thiếu; registration
cosine/conditioning/merge/support/calibration/anchors chưa hoàn tất; norm và
denominator floors/gap definition/residual operating range chưa chốt; input plan
chưa đăng ký và execution flags chưa mở. Không tự thay protocol/source lock,
không ghi decision/amendment giả, không chạy alignment pilot hoặc null/drift thật.

JUnit cuối: `outputs/m2_measurement_v2_tests/targeted_reviewed_results.xml` và
`full_reviewed_results.xml`. Source snapshots, scope patch, test receipts và
completion manifest được lưu kèm run readiness cuối; rehash kiểm artifacts,
current code/input bindings và43 protected inputs từ mốc trước.

## Tier và bước còn lại

| Tier | Phạm vi |
|---|---|
| IMPLEMENTED | Stage APIs, gated file-backed runner, independent verifier, candidate/schema |
| TESTED | 45 cases mới +138 targeted +619 full regression; synthetic stage executions |
| EXECUTED | Chỉ preflight registration/readiness trên repo thật, chưa real-data measurement |
| VERIFIED | Hashes/manifests/protected inputs của preflight; chưa estimator/G3 trên data thật |

Phần kỹ thuật độc lập đã hoàn thành. Còn cần đúng originals hoặc amendment,
scientific definitions/parameters và input plan được đăng ký trước pilot/rerun.
Pilot xác lập operating range cần có thiết kế được đăng ký riêng, chỉ dùng
diagnostics hình học/structural inputs, không dùng SED/QA/H1 để chọn thresholds.
Không suy ra ngưỡng G3 từ fixtures hoặc tái dùng RMSE thresholds cho relative residuals.

AGENTS.md §2.2: “If information is insufficient for an issue affecting scientific
semantics, data population, or temporal behavior: STOP and request user clarification.”
§8.2 còn yêu cầu “Stage Report → STOP”. Vì nguồn và parameters còn thiếu, kết
thúc lượt này tại engineering implementation + readiness report; không cấp G3.

M1-PASS vẫn là tiền đề. Giữ dữ liệu canonical, protocol, source lock, decision log,
old configs và historical artifacts; không train lại, commit/push hoặc đổi branch.
