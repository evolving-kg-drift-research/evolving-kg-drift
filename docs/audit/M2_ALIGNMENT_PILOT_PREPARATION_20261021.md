# M2 data 3.1 — hồ sơ chuẩn bị pilot căn chỉnh v2

Ngày: 21/10/2026. M1-PASS là tiền đề người dùng.
Trạng thái: **PREPARED, NOT SCIENTIFICALLY REGISTERED; PILOT NOT EXECUTED**.

## Phạm vi và đầu vào cụ thể

Đã lập candidate và inventory đủ81 saved comparisons, bind bằng physical hashes.
Run: `outputs/m2_alignment_pilot_plan/20261021T072021Z_e4934444/`.
Các files chính: `proposed_inventory.json`, `resolved_config.json`,
`source_search.json`, `readiness.json`, `experiment_manifest.json`.

| Đầu vào đề xuất | Phạm vi |
|---|---|
| Canonical data3.1 | T01–T10;10 physical hashes khớp frozen training inputs |
| Checkpoints | 30 descriptors, seeds13/37/101, giữ provenance/hashes gốc |
| Transitions | Đủ9 adjacent transitions T01→T02 đến T09→T10 |
| Cross-time | 3 mỗi transition; tổng27 |
| Same-snapshot cross-seed | 6 mỗi transition; tổng54 |
| Anchors | Đúng9 saved plans, fit101/holdout66 mỗi plan; không chọn lại |
| Rehash lịch sử | 176 backbone +269 alignment artifacts |

Lấy toàn bộ registered jobs, không lọc theo old availability hoặc outcomes.
Inventory được gắn hash để review, không tự trở thành scientific registration.
Các Dev results cũ đã tồn tại; không gọi hồ sơ này là preregistration hồi tố.
Chưa train, refit Q, tính cosine/noise/SED, chạy QA/H1 hoặc mở stage kế tiếp.

## Thiết kế collection

Đã tách `collect_alignment_geometry_v2` khỏi phần áp gate policy. Nó không
đòi epsilon/MAD/support, residual/gap limits hoặc lựa chọn gap statistic.

| Thống kê | Hành vi |
|---|---|
| Spectrum | Giữ raw và relative singular values từ covariance của fit anchors |
| Numerical rank/rank fraction | Chỉ tính khi truyền tolerance; thiếu thì null, không mặc định1e-6 |
| Rfit/Rhold | Relative Frobenius residual; holdout dùng fit means |
| Denominator0 | Ratio null; giữ numerator/denominator và undefined reason |
| Gap | Giữ cả signed và absolute, mô tả độc lập với quyết định G3 |
| Orthogonality | Raw Frobenius norm và norm/d |
| Gate status | Không có available/G3_pass/SED_plus trong raw collection |

Kiểm đúng fit means, checkpoint semantics và objective Procrustes. Nonfinite
inputs/outputs bị từ chối. Gate wrapper cũ vẫn dùng explicit floor/operating
ranges, không đổi ngưỡng hoặc output contract để làm nhiều trường hợp PASS.

Trước scientific pilot còn cần: exact originals hoặc approved source amendment;
anchor/frequency design; pilot authorization; rank tolerance nếu báo numerical
rank; và quy trình quyết định operating range đăng ký trước khi xem collection.
Giá trị giới hạn residual/gap cuối không là điều kiện để thu raw statistics.
Không tự lấy percentile95, max quan sát hoặc tỷ lệ PASS mong muốn làm ngưỡng.

Saved anchor plans là legacy pretransition-degree design. Giữ IDs không chứng
minh joint degree/frequency conformance; nếu thiết kế được duyệt cần đổi anchors,
phải lập plan và fit Q mới theo stage riêng. Không gán nhãn lại Q cũ.

## Nguồn còn thiếu

PDF khớp lock/protocol; hai root MD originals chưa có:

| File | SHA-256 baseline |
|---|---|
| `sources/Research_Execution_Plan_v1.0.md` | `c61d08fc6a5a63658e2b99c1245867b9221a3f84c04fa9d872bad8fbbb638b94` |
| `sources/Research_Execution_Plan_v1.1_Patch.md` | `3f1bc9fd9d3dca2bb47eadc59c0ec6266a12794612761ce6b7ffb204fccb31a5` |

Git search bounded đúng hai paths tìm2 blobs. Kiểm18 encoding/newline candidates
cho v1.0 và26 cho patch: không bản nào khớp baseline. Package MDs đúng bằng Git
bytes chuyển CRLF; điều đó giải thích package/Git hashes khác nhau nhưng không
giải quyết locked original hashes. Không restore substitutes hoặc sửa source lock.
Tìm thêm theo tên/hash trong các tệp đã lưu chưa resolve được originals; không
mở các kết quả gợi ý không liên quan, không kết luận files không tồn tại nơi khác.

ADR0007: “Missing, substituted, malformed or mismatched originals keep source
readiness BLOCKED.” AGENTS.md §2.2 yêu cầu STOP khi thiếu scientific semantics;
§8.2 yêu cầu stage report rồi STOP. Vì vậy chưa chạy pilot thật/G3.

## Files và kiểm thử

Thêm `scripts/prepare_m2_alignment_pilot_v2.py`,
`configs/m2_alignment_pilot_v2_candidate.yaml`,
`configs/schemas/m2_alignment_geometry_statistics_v2.schema.yaml`,
`tests/test_m2_alignment_pilot_v2.py`; sửa `src/drift/measurement_v2.py` để tách
raw statistics/gate policy, cập nhật PROGRESS và báo cáo này.

**Finding M2-PILOT-001 — MEDIUM:** collection trước đây nằm trong gate helper,
đòi limits/epsilon/MAD/support dù chỉ cần quan sát geometry. Root cause confirmed:
statistics và policy bị ghép chung. Reproduce: gọi `geometry_diagnostics_v2`
thiếu full settings bị `validate_settings` từ chối. Minimal fix: raw collector
riêng, giữ gate wrapper. Regression: NumPy oracle, optional/invalid tolerance,
zero denominator, legacy availability, contract và full suite. IMPLEMENTED/TESTED;
chưa RESOLVED cho scientific workflow, còn source/design registration.

| Kiểm tra cuối | Kết quả |
|---|---|
| Cases mới | 20 |
| Targeted pilot/v2/historical null-drift/centered-cosine | **158 passed** |
| Full repository | **639 passed, 10 skipped** |
| Ruff toàn repo / git diff --check | PASS |
| Runtime | Python3.11.9; chưa chạy Python3.10 |

Reproduce-first collection fail vì API chưa tồn tại; sau patch PASS. NumPy oracle
tính spectrum/residual từ vectors; inventory tests kiểm missing/duplicate jobs,
seed sai, outcome fields, missing hashes và overlapping anchors. 10 skips là
scaffolds sẵn có, không tính G3. JUnit cuối ở
`outputs/m2_alignment_pilot_v2_tests/targeted_final_results.xml`,
`full_final_results.xml`; copies/source/patch evidence được lưu cùng run chuẩn bị.

```powershell
.venv-m1/Scripts/python.exe -B scripts/prepare_m2_alignment_pilot_v2.py
.venv-m1/Scripts/python.exe -B outputs/m2_alignment_pilot_plan/20261021T072021Z_e4934444/recheck.py
.venv-m1/Scripts/python.exe -m ruff check --no-cache .
git diff --check
```

CLI chỉ chuẩn bị run mới, không có execute switch; exit0 không là pilot PASS.
IMPLEMENTED/TESTED phần engineering; EXECUTED/VERIFIED chỉ inventory/source/hash
scope, không collection thật hoặc G3. Cần hai originals đúng hash hoặc chỉ đạo
amendment có thẩm quyền, rồi hoàn tất pilot registration. Giữ M1-PASS premise,
data/protocol/source lock/decision log và lịch sử; chưa commit/push/đổi branch.
Scope patch PROGRESS có cả các thay đổi trước được giữ nguyên.
