# M2 data 3.1 — cấu hình ứng viên và kiểm chứng reuse checkpoint

Ngày: 21/10/2026. Tiền đề: M1 đã PASS theo chỉ đạo người dùng.
Phạm vi lượt này: review phần chuẩn bị, cụ thể hóa cấu hình và kiểm tra checkpoint
trên artifacts thật. Không nghiệm thu lại M1 hoặc thay đổi tiêu chí G3.

## Kết quả và quyết định kỹ thuật

**30/30 tổ hợp snapshot–seed đủ điều kiện tái sử dụng về kỹ thuật cho đúng cấu
hình huấn luyện đã kiểm.** Không cần mặc định huấn luyện lại vì thay estimator
nhiễu hoặc chuyển cách tính cosine. Provenance gốc được giữ nguyên; việc bind
data3.1 là bằng chứng mới, không sửa checkpoint thành một lần training mới.

Đã thêm `configs/m2_data_3_1_candidate_v2.yaml`,
`scripts/inspect_m2_reuse.py` và `tests/test_m2_reuse_readiness.py`.
Cấu hình có trạng thái **CANDIDATE_NOT_ACTIVE**; công cụ chỉ đọc checkpoint,
metadata và nguồn. Các flags không cho phép training, measurement, overwrite
hoặc tự chuyển stage. Default scientific runner chưa đổi.

| Nội dung cấu hình | Giá trị/phạm vi | Tình trạng |
|---|---|---|
| Backbone để kiểm reuse | TransE-L2, d64; seeds13/37/101; epochs50; lr0.01; margin1; normalize entities; batch_size32 | Khớp chính xác ba saved runtime configs; batch_size được giữ trong hash, code cũ cập nhật SGD từng triple |
| Dữ liệu | T01–T10 canonical Parquet của release3.1, full snapshot | Bytes và full mappings khớp đầu vào training đã lưu |
| Cosine ứng viên | Affine `(x-mu_s)Q+mu_t` so với `y` | Theo (14)/(26) PDF; chưa tích hợp/chạy lại distances |
| Null ứng viên | Median6/entity rồi LTO theo entity | Engine v2 đã fixture-tested ở lượt trước; chưa real-data execution |
| Support ứng viên | Ít nhất50 reference entities sau LTO; group51 để mọi target đủ50 | Theo hướng PDF; sparse policy cần đăng ký hoàn chỉnh |
| Diagnostics ứng viên | Relative Frobenius residual; orthogonality/d; rank fraction>=0.90; orth/d<=1e-6 | Chưa đổi runner; residual/gap operating range còn thiếu |
| Tham số kế thừa Dev | Epsilon1e-4, MADfloor1e-12, bins3/6, fit101/holdout66, rank tolerance1e-6 | Đề xuất tường minh, chưa scientific freeze |
| Conditioning/merge | Frequency chưa định nghĩa; adjacent merge cần thứ tự cố định | Không tự dùng degree làm frequency; không tự chọn merge bằng drift outcomes |

Các giá trị trên tạo một cấu hình có thể review; không là biên bản phê duyệt
khoa học. Giữ `configs/protocol_v1.yaml`, source lock và decision log nguyên vẹn.

## Kiểm chứng trên artifacts thật

Run mới: `outputs/m2_reuse_readiness/20261021T060328Z_96561ac8/`.
Backbone gốc: `outputs/m2_backbone/20261014T034042Z_65c464ba/`.

| Kiểm tra | Kết quả |
|---|---|
| Snapshot canonical3.1 so với frozen training inputs | 10/10 physical SHA-256 khớp; dựng lại snapshot semantic hashes và full mappings |
| Coverage snapshot×seed | 30/30, không thiếu/trùng hoặc seed ngoài13/37/101 |
| Checkpoint vật lý và sidecar | 60/60 hợp lệ; 30 saved replay pairs khớp từng byte |
| Manifest per-seed | 30/30 bind đúng checkpoint/config/input/git |
| Hash artifacts của backbone gốc | 176/176 khớp |
| Producer source code | 18/18 archived hashes khớp; 18/18 current files cũng khớp |
| Runtime | Python3.11.9, NumPy2.2.6, PyArrow23.0.0 và Windows platform khớp run gốc |
| Protected inputs từ mốc lượt trước | 43/43 không đổi |

Script chính dùng lại verifier checkpoint đã audit: kiểm physical/semantic
hashes, mappings, finite vectors/losses, full-snapshot metrics và provenance.
`recheck.py` trong run tính lại hashes, saved replay bytes, snapshot/mappings
từ Parquet và lineage bằng đường độc lập, không import production M2 code.
Phạm vi kiểm chứng độc lập này được ghi rõ trong receipt, không gọi nó là
fresh training replication hoặc scientific certification.

Không có huấn luyện mới trong lượt này. Q, raw noise distances và temporal
distances cũ chưa được chứng nhận reuse. Nếu dùng affine cosine, cần tính lại
noise/temporal distances; việc giữ Q vẫn phải kiểm anchors và diagnostics mới.

## Hai điểm còn chặn kích hoạt scientific measurement

### M2-REG-001 — original scientific sources chưa đầy đủ

- **Severity:** GOVERNANCE. **Files:** `sources/Research_Execution_Plan_v1.0.md`,
  `sources/Research_Execution_Plan_v1.1_Patch.md`,
  `data/manifests/sources.lock.json`, `docs/adr/0007-preserve-original-source-baseline.md`.
- **Expected:** ba original sources đúng hash ở cả lock và protocol.
- **Actual/Evidence:** PDF khớp; hai original MD ở root thiếu. Search Git bounded
  đúng hai paths tìm được hai blobs nhưng SHA-256 cũng khác baseline; không
  restore các substitutes này. `report.json.source_readiness.ready=false`.
- **Confirmed cause:** thiếu đúng original bytes trong checkout và các blobs
  tìm được. Không kết luận originals không tồn tại ở nơi khác.
- **Reproduction:** chạy CLI phía dưới; kiểm `source_readiness` và `local_source_history`.
- **Minimal remedy:** bổ sung đúng originals, hoặc xử lý thay nguồn qua amendment
  có thẩm quyền, giữ baseline cũ. Không sửa lock để khớp file đang có.
- **Regression:** tests exact/missing/substituted/protocol_conflict.
- **Remaining blocker:** chưa có originals đúng hash hoặc approved amendment;
  không đánh dấu RESOLVED. Đây là readiness nguồn của M2, không mở lại M1.

### M2-REG-002 — cấu hình khoa học còn những trường chưa đăng ký

- **Severity:** GOVERNANCE. **Files:** `configs/m2_data_3_1_candidate_v2.yaml`,
  `docs/M2_SPEC_RECONCILIATION_V3_1.md`, `scripts/inspect_m2_reuse.py`.
- **Expected:** estimand, structural conditioning/merge và operating range có
  registration rõ trước scientific execution; không chọn theo SED/QA/H1.
- **Actual/Evidence:** candidate ghi rõ frequency/merge order/residual limits
  chưa có; epsilon/MAD/bins/anchors/rank tolerance là carry-forward proposals.
  `execution_blockers` xuất từng lý do; scientific execution vẫn false.
- **Confirmed cause:** các scientific choices này chưa được chốt trong hồ sơ
  hiện hành; đây không phải lỗi checkpoint và không được chữa bằng train lại.
- **Reproduction:** CLI/read `execution_blockers`; fixtures không thay thế registration.
- **Minimal remedy:** hoàn tất hồ sơ D-SOURCE/D-COS/D-NULL/D-DIAG, đăng ký sparse
  policy/operating range; sau đó tích hợp runner và verifier với config phiên bản mới.
- **Regression:** từ chối active/training/measurement flags, thay seed/release,
  bỏ binding hoặc thay saved model config; kiểm blockers không mất chỉ vì source ready.
- **Remaining blocker:** registration và integration; chưa RESOLVED hoặc G3 PASS.

## Tests, diff và mức xác minh

| Kiểm tra | Kết quả |
|---|---|
| Reuse readiness + backbone regression | 37 passed, gồm20 cases mới |
| Full repository suite | **574 passed, 10 skipped** |
| Ruff toàn repository | PASS |
| `git diff --check` | PASS |

Reproduce-first: collection fail vì module mới chưa tồn tại; sau implementation
các tests PASS. Một lần fixture setup gặp lỗi TEMP parent chưa tồn tại; đã tạo
workspace TEMP/TMP và chạy lại nguyên kiểm thử, không đổi scientific thresholds.
10 skips là scaffolds hiện có; không tính là G3 PASS. Chưa test runtime Python3.10.

JUnit gốc: `outputs/m2_reuse_tests/targeted_final_results.xml`,
`outputs/m2_reuse_tests/full_final_results.xml`; bản sao và source/patch evidence
được lưu trong run mới, có completion manifest riêng.

Lệnh tái kiểm:

```powershell
.venv-m1/Scripts/python.exe -B scripts/inspect_m2_reuse.py
.venv-m1/Scripts/python.exe -B outputs/m2_reuse_readiness/20261021T060328Z_96561ac8/recheck.py
.venv-m1/Scripts/python.exe -m pytest -q tests/test_m2_reuse_readiness.py tests/test_m2_backbone_workflow.py
.venv-m1/Scripts/python.exe -m ruff check --no-cache .
git diff --check
```

CLI tạo run mới; recheck chỉ đọc. Khi test trên host này, đặt TEMP/TMP và
`--basetemp` trong workspace như lệnh được lưu trong test evidence.

| Tier | Phạm vi đạt được |
|---|---|
| IMPLEMENTED | Cấu hình ứng viên, reuse inspector, guards và báo cáo |
| TESTED | 20 cases mới và full regression; không là scientific gate |
| EXECUTED | Inspection trên10 snapshots/30 checkpoint configurations thật; không training hoặc measurement |
| VERIFIED | Hashes, mappings, saved replay/config/code/lineage trong phạm vi đã nêu; không scientific estimator/G3 |

Bước tiếp theo của scientific workflow là hoàn tất registration còn thiếu và
tích hợp runner v2, sau đó chạy stage alignment/null bị ảnh hưởng trong namespace
mới. Không mặc định train lại30 models; không tự chuyển stage trong lượt này.
AGENTS.md §2.2/§8.2 yêu cầu dừng scientific activation khi thiếu quyết định về
semantics và kết thúc stage bằng báo cáo. Các công việc kỹ thuật độc lập đã xong.

Branch vẫn `codex/m2-drift-workflow`; HEAD `abeb425385f8b19bb05db30c84c4bb05371e8640`,
working tree dirty. Không commit/push hoặc sửa provenance/artifacts lịch sử.
