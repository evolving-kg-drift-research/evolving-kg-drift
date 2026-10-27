# M2 data 3.1 - Estimator nhiễu cấp thực thể v2

Ngày: 21/10/2026. Phạm vi: phần implementation đã rõ của nhóm A/B.
Tiền đề làm việc: người dùng yêu cầu xem M1 đã PASS với data3.1.

## Kết quả

Đã thêm đường tính **v2**: sáu raw distances có định danh/provenance -> một median
cho mỗi entity -> reference loại target -> median/MAD theo đơn vị entity ->
signed excess/SED+ khi reference khả dụng. V2 có schema và verifier riêng.

Các hàm/runner v1 còn phục vụ historical Dev; không tự chuyển default pipeline
sang v2, không thay output cũ và không tuyên bố toàn bộ M2 đã được sửa/xác nhận.
Cosine, scientific baseline, support/merge và diagnostics chưa được tự chọn.
Đây là phần có thể triển khai độc lập với những quyết định còn thiếu ở hồ sơ
`docs/M2_SPEC_RECONCILIATION_V3_1.md`, không là biên bản hòa giải nguồn hoàn tất.

## Các file được thêm hoặc sửa

| File | Thay đổi |
|---|---|
| `src/drift/artifact_null.py` | Thêm `build_entity_level_null`, validator count/availability v2 và version identifiers; giữ semantics hàm v1 |
| `src/drift/artifact_drift.py` | Thêm `calibrated_metrics_v2`, nhận đúng ba seed IDs và chỉ dùng reference v2 |
| `scripts/run_m2_null.py` | Thêm LTO Parquet schema v2; serializer kiểm v2 trước khi Arrow có thể bỏ field/coerce dữ liệu |
| `scripts/run_m2_drift.py` | Thêm drift Parquet schema v2; stage runner v1 không được chuyển tự động |
| `scripts/verify_m2_entity_null_v2.py` | Verifier độc lập bằng NumPy cho entity medians, LTO, counts, provenance và calibration |
| `configs/schemas/m2_entity_null_v2.schema.yaml` | Đăng ký engineering output contract; không có scientific defaults/threshold freeze |
| `tests/test_m2_entity_null_v2.py` | 49 regression cases cho đường tính v2 và wire contracts |
| `docs/PROGRESS.md` | Thêm trạng thái lượt này; giữ nội dung lịch sử và thay đổi trước đó của người dùng |
| Báo cáo này | Phạm vi, kết quả, bằng chứng và giới hạn |

## Hợp đồng và hành vi mới

`build_entity_level_null` nhận raw rows, bucket assignment và cấu hình tường minh.
Không có fallback cấu hình, không chọn bin, không merge bucket, không dựng
structural metadata và không tự quyết định centered/affine. `cosine_estimand`
chỉ là declaration do caller cung cấp; component không chứng nhận rằng raw
distances đã được tính đúng declaration đó từ checkpoints.

Mỗi entity phải có đúng sáu endpoint/seed-pair identities từ seeds13/37/101 và
hai snapshots của transition. Duplicate/missing pair, số không hữu hạn, hash
không hợp lệ, checkpoint/alignment fingerprints mâu thuẫn đều bị từ chối.
Raw rows được giữ và sắp xác định; từng entity median liên kết tới sáu row hashes.
Config, external bucket plan và raw observations có semantic SHA-256 riêng.

Trong một reference row sau khi loại target, với N entities:

| Trường | Ý nghĩa |
|---|---|
| `raw_noise_observation_count` | 6*N raw distances của các reference entities |
| `reference_entity_count` | N canonical entity IDs khác nhau |
| `reference_sample_count` | N giá trị median cấp entity |
| `removed_target_raw_observation_count` | Sáu raw target distances bị loại khỏi reference |

`reference_entity_ids` lưu membership để kiểm target exclusion và unique IDs.
V2 từ chối trường `observation_count` của v1, phiên bản không phù hợp và count
units không nhất quán. Serializer v2 từ chối thiếu/thừa fields thay vì để Arrow
bỏ trường không có trong schema. Các controls này không thay semantics v1.

Support kiểm sau LTO theo `minimum_reference_entities` được truyền vào; không
đếm sáu pair rows như sáu reference samples. `mad_threshold` và epsilon cũng
phải truyền rõ. Các tests50-entity chỉ là fixtures kiểm boundary; không đăng
ký hoặc kích hoạt ngưỡng50 cho scientific execution.

Empty reference: median/MAD/scale null, unavailable. Thiếu support: vẫn có thể
lưu center/MAD và signed excess mô tả, nhưng SED+ null. MAD suy biến: unavailable;
epsilon không cứu reference. SED+=0 chỉ dành cho phép đo khả dụng có excess
không dương; không thay unavailable bằng0.

## Regression và kiểm chứng

Đã viết tests trước implementation; bước đầu collection fail vì API v2 chưa có.
Các numerical fixtures về estimator đã có từ hồ sơ giai đoạn1.

Một reproducer riêng sau đó xác nhận serializer Arrow có thể chấp nhận/bỏ field
legacy, version sai hoặc count units sai: **3 cases FAILED với DID NOT RAISE**
trước guard. Sau sửa, cả ba cases PASS; không đổi ngưỡng/metric để qua test.

Fixture phân biệt estimator:

- Reference entity A: median sáu distances =0.5; B=0.1.
- Pooled raw distances: center0.1, MAD0.
- Entity-level reference: center0.3, MAD0.2.
- V2 và verifier NumPy tính độc lập khớp center0.3/MAD0.2.

Coverage gồm: LTO target blindness; input-order determinism; 49/50 support sau
LTO; empty/zero-MAD; missing/duplicate pairs; seed/endpoint identity; conflicting
lineage; required config; tampered results/provenance; v1 rejection; signed excess;
epsilon không cứu reference; Parquet round-trip/determinism và YAML/schema parity.

Verifier không import production reducer hoặc production reference validator.
Nó tính lại từng median bằng NumPy từ raw rows và reconstruct reference từ
external assignments, kiểm semantic hashes cùng toàn bộ membership/counts.

| Kiểm tra trên revision cuối | Kết quả |
|---|---|
| Targeted v2 + v1 null/drift + centered-cosine fixtures | 93 passed |
| Full repository suite | **554 passed, 10 skipped** |
| Ruff toàn repository | PASS |
| `git diff --check` | PASS |
| Runtime | Python3.11.9; chưa chạy runtime Python3.10 |

10 skips thuộc scaffolds sẵn có; không biến các skips này thành scientific gate
PASS. Full-suite kết quả trước guard serializer là551/10; kết quả554/10 là sau
guard và ba regression cases mới. Không cần dùng kết quả của revision cũ để
chứng minh revision cuối.

JUnit evidence nằm dưới `outputs/m2_entity_null_v2_tests/`:
`targeted_serialization_final_results.xml` và `full_serialization_final_results.xml`.

Lệnh kiểm tra chính:

```powershell
.venv-m1/Scripts/python.exe -m pytest -q tests/test_m2_entity_null_v2.py tests/test_m2_null_workflow.py tests/test_m2_drift_workflow.py tests/scientific/test_centered_cosine_estimand.py
.venv-m1/Scripts/python.exe -m pytest -q
.venv-m1/Scripts/python.exe -m ruff check --no-cache .
git diff --check
```

Trên môi trường này đã đặt TEMP/TMP và pytest basetemp vào output workspace
riêng cho từng lần chạy, tránh lỗi Windows atomic rename trước đây.

## Tier và trạng thái findings

| Phạm vi | IMPLEMENTED | TESTED | EXECUTED trên production artifacts | VERIFIED trên production artifacts |
|---|---|---|---|---|
| Entity-level reducer/count contract/calibration v2 | Có | Có, fixtures và regression | Chưa | Chưa |
| Verifier số học v2 | Có | Có, corruption tests/NumPy | Chưa | Chưa |
| Production integration, cosine/support/diagnostics registration | Chưa hoàn tất | Chưa | Chưa | Chưa |

M2-THEORY-001: phần code v2 được IMPLEMENTED/TESTED, **chưa RESOLVED cho toàn bộ
scientific workflow**. M2-THEORY-002/003/004 còn các lựa chọn/đối chiếu nguồn
chưa được chốt. G3 **chưa đánh giá**. Không có null/drift result mới trên data3.1
và không có certification dựa trên fixture PASS.

## Bước còn lại và phạm vi chạy lại

1. Chốt D-SOURCE/D-COS/D-NULL/D-DIAG trong hồ sơ giai đoạn1. Tiếp tục được xem
   là chỉ đạo triển khai phần đã rõ, không là lựa chọn ngầm giữa các estimands.
2. Bind config/registered bucket plan và raw metric đã chốt; tích hợp runner v2,
   actual-artifact verifier, availability masks/report/handoff. Chặn legacy route
   trong scientific run thay vì chỉ đổi tên số liệu v1.
3. Đánh giá reuse checkpoints/Q/raw distances theo input/code/config lineage;
   chỉ rerun phần bị ảnh hưởng trong namespace mới, theo từng stage.
4. Sau real-data execution, independent verification và đúng operating range
   đã đăng ký mới đánh giá G3. Nhóm C theo kế hoạch riêng có trace nguồn.

Giữ nguyên canonical data3.1, protocol/source lock, decision log, các historical
configs và artifacts. Branch vẫn `codex/m2-drift-workflow`; chưa commit/push.
Code evidence được lưu kèm source snapshots, hashes và implementation patch
trong run mới dưới `outputs/m2_entity_null_v2/`; không sửa run evidence giai đoạn1.

Diff reference: `git diff -- src/drift/artifact_null.py src/drift/artifact_drift.py
scripts/run_m2_null.py scripts/run_m2_drift.py`, cộng các file mới được liệt kê ở trên.
