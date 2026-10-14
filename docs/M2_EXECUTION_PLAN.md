# Kế hoạch M2 — nhánh codex/m2-drift-workflow

Ngày: 14/10/2026. Base: `2860235`, kế thừa code hiện tại; giữ nguyên các thay đổi
M1 đang mở của người dùng. Người dùng yêu cầu bỏ tiêu chí M1 và xác nhận hướng
**pilot lựa chọn dimension bằng validation/alignment**.

## Phạm vi và thẩm quyền

Chạy M2 Dev trên gói Parquet có sẵn `data/KG_lan2/evolving_kg_downstream_v3/`.
Không lấy việc nghiệm thu M1 làm điều kiện cho pilot được người dùng cho phép.
Ghi rõ ngoại lệ này trong manifests; không sửa adapter production, protocol,
source lock, dữ liệu lịch sử hoặc đổi nhãn gate hiện có. Các input checks dưới
đây kiểm sự nhất quán kỹ thuật của gói, không chứng nhận identity/temporal M1.

M2 vẫn giữ TransE-L2, seeds 13/37/101, outcome blindness, mapping parity,
centered Procrustes, null 6 cặp và Leave-Target-Out. Không điều chỉnh thresholds
theo drift/MRR locked/H1. Không đọc `data/locked_test/`, không chạy M3/M4.

## Trình tự thực hiện

| Bước | Công việc | Artifacts và tiêu chí hoàn tất | Điểm dừng |
|---|---|---|---|
| 1 — Input preflight | Đọc 10 canonical snapshots theo config của gói; kiểm physical/semantic sidecar SHA-256, count, ID, uniqueness, cutoff order; xuất mapping/histogram/persistent entities. Inventory bốn bảng vừa bổ sung, không dùng làm triples training. | `outputs/m2_preflight/<run>/report.json`, `mappings.json`, experiment manifest. Gói không đổi sau đọc; mọi mismatch phải fatal. | Nếu thiếu file, sidecar, ID hoặc metadata không khớp. |
| 2 — Pilot Dev | So sánh dimensions 32/64 bằng cùng split T01, ba seeds; train T01/T02 từ đầu để chẩn đoán alignment. Replay mỗi checkpoint hai lần. | Design/split/anchors lưu trước training, 18 checkpoint configurations × 2 repeats, validation ranks, 18 alignment diagnostics, hashes/manifests. | Báo cáo pilot và đề xuất cấu hình; không tự train T03–T10 hoặc tính drift. |
| 3 — Chốt cấu hình M2 | Người dùng duyệt dimension, optimizer parameters, anchors và null rules từ proposal cụ thể. Lưu resolved config có version/hash. | Cấu hình M2 đủ giá trị, không placeholders; phân biệt Dev configuration với scientific protocol freeze. Nếu cần thay protocol thì xử lý amendment riêng. | Thiếu quyết định M2 thì không chạy measurement. |
| 4 — Controlled backbone | Train lại độc lập trên toàn bộ mỗi snapshot T01–T10, ba seeds = 30 runs; không warm-start. | Checkpoints entity/relation, map/config/input/code hashes, finite losses, replay bytes và mapping parity; experiment manifests. | Một seed thiếu, hash/finite/replay lỗi thì dừng. Báo cáo backbone trước bước 5. |
| 5 — Alignment | Mỗi transition chọn persistent canonical IDs, stratify chỉ bằng degree pretransition; deterministic disjoint fit/holdout đã đăng ký. Căn chỉnh ba cặp parallel seeds và ba cross-seed pairs tại mỗi endpoint. | Q, source/target means, fit/holdout IDs/hash, singular values/rank, orthogonality, residual/gap, validity reason. | Rank/gap/orthogonality lỗi: alignment unavailable, không ép SED+. |
| 6 — Empirical null | Pool (13,37), (13,101), (37,101) ở hai endpoint = 6 observations/entity. Buckets chỉ bằng degree pretransition. LTO loại toàn bộ 6 observations của entity target. | Null observations, endpoint/pair IDs, bucket assignments, median/MAD/count, adjacent merges và reasons; manifest bound checkpoints/alignment/config. | Thiếu cặp hoặc null degenerate: unavailable có reason; không đổi epsilon/merge để tạo PASS. |
| 7 — Drift và bàn giao | `delta_time`: median ba parallel seeds của `1-cos((x-mu_prev)Q, y-mu_next)`; `r = delta_time - median(null_LTO)`; `SED+ = max(0,r)/(1.4826*MAD_LTO+epsilon)`. | Entity×Transition Parquet, signed excess, diagnostics/availability, hashes và M2→M4 manifest. Không đưa RR/H1 vào quyết định M2. | Không tự chạy M4. Cần independent artifact validation trước G3/scientific claims. |

Mỗi bước thực thi dữ liệu thật có báo cáo trước khi tiến sang bước tiếp theo.
Lượt hiện tại được cho phép hoàn thành preflight và pilot; dừng ở proposal.

### Cập nhật phê duyệt và bước tiếp theo — 14/10/2026

Sau báo cáo pilot, người dùng xác nhận: **"Hãy thực hiện kế hoạch trên."**
Đã chốt các giá trị trong proposal vào `configs/m2_external_dev_v1.yaml`,
status APPROVED_FOR_DEV_EXECUTION, bind exact SHA-256 của proposal ban đầu.
Đây là config Dev riêng; không thay `configs/protocol_v1.yaml` hoặc cấp G3.
Lượt tiếp theo thực hiện bước 3 (resolved configuration) và **chỉ stage backbone
training** ở bước 4, kiểm artifacts và Stage Report rồi STOP trước alignment.

Lệnh backbone: `.venv-m1/Scripts/python.exe scripts/run_m2_backbone.py`.
Lệnh kiểm độc lập: `.venv-m1/Scripts/python.exe scripts/verify_m2_backbone.py
--run outputs/m2_backbone/<run>`. 30 configurations × 2 repeats = 60 executions,
không reuse checkpoints pilot làm đầu vào hoặc warm-start models.

## Thiết kế pilot đã đăng ký

Cấu hình: `configs/m2_pilot.yaml`, version `m2_pilot_v1`, Dev, không certification.

- Dimensions `[32,64]`; seeds `[13,37,101]`; 50 epochs; learning rate 0.01;
  margin 1.0; entity normalization theo backbone hiện có. Các giá trị training
  này giữ mức pilot legacy hiện có, chưa được tuyên bố là optimal/frozen.
- Validation dùng **T01 Dev**, không phải locked QA. Hash salt mới
  `m2-pilot-validation-v1`; greedy theo hash, target 20%, chỉ bỏ triple nếu mọi
  entity và relation vẫn còn trong train. Nếu cấu trúc không cho đủ 20%, lưu
  số thực tế và giới hạn population; không tạo synthetic triples hoặc OOV.
- Train từ train partition riêng cho mỗi dimension/seed. Rank head và tail,
  candidates = training entities; lọc các positives của T01 tại evaluation;
  exact ties dùng average rank. Không dùng validation để chọn anchors/buckets.
- Sáu full-snapshot models/dimension phục vụ kiểm alignment, tách khỏi models
  đánh giá validation. Không lấy MRR từ checkpoint đã train toàn T01.
- Same-snapshot alignments tại T01 và T02 chỉ dùng cùng persistent universe
  của transition. Chia fit/holdout theo **exact degree** tại snapshot liên quan;
  cross-time luôn degree T01. Ratio pilot 0.6, hash salt/version lưu trước train.
  Degree stratum singleton vào fit, các strata lớn có holdout. Đây là feasibility
  diagnostic, chưa chốt anchor count cho measurement toàn bộ transitions.
- Mỗi dimension có 6 same-snapshot và 3 cross-time alignment checks. Giữ các
  giới hạn diagnostic đang có trong code; pilot còn yêu cầu numerical rank
  đầy đủ dimension. Không hạ thresholds sau khi thấy kết quả.
- Dimension chỉ được đề xuất nếu cả 9 alignments khả dụng. Trong các dimension
  khả dụng, chọn mean validation MRR của ba seeds cao hơn; tie chọn dimension
  nhỏ hơn. Nếu cả hai không khả dụng: proposal dimension = unavailable.
- Không tính drift, SED+, pooled null hoặc H1 trong pilot. Null buckets, merge
  policy, epsilon và anchor counts chưa được tự freeze từ defaults.

## Kiểm tra engineering cần hoàn tất

Fixture tests cho input tampering/path escape/locked-test rejection, cutoff
order/count/hash mismatch, split coverage/determinism, stratified anchor
disjointness, fail-closed dimension selection và exact checkpoint replay.
Chạy các regressions KGE/Procrustes/null/three-seed median và adapter guards.
Toàn repo phải đạt Ruff. Môi trường local Python 3.11; không suy ra đã tested
Python 3.10 nếu chưa chạy trên interpreter đó.

Independent pilot verifier đọc lại saved checkpoints/ranks và tính Procrustes
bằng NumPy riêng để đối chiếu means/Q/singular values/residuals/rank. Kiểm toàn
bộ input/output/code hashes và pre-registered selection. Verification chỉ
bao phủ pilot artifacts; không tự cấp G3 hoặc xác nhận M1 temporal semantics.

## Các rủi ro đã biết cần thể hiện trong báo cáo

T01 rất nhỏ, validation coverage-preserving thiên về entities có nhiều cạnh;
không đại diện cho toàn corpus hay QA multi-hop. Pilot T01→T02 chưa chứng minh
mọi transition sau có alignment ổn định. Cutoff T07–T10 và upstream semantics
thuộc gói bên ngoài; vẫn giữ nguyên và đánh dấu uncertified theo ngoại lệ người
dùng yêu cầu. Các placeholders protocol phải được xử lý trước scientific freeze.

Code drift hiện có cần review ở bước 5–7 trước execution: serialization của
unavailable metrics, lineage completeness, anchor stratification và kiểm
validity mọi same-snapshot pair. Fixture baseline không thay thế review này.

## Lệnh tái lập

```powershell
.venv-m1/Scripts/python.exe scripts/inspect_m2_inputs.py
.venv-m1/Scripts/python.exe scripts/run_m2_pilot.py --preflight outputs/m2_preflight/<run>
.venv-m1/Scripts/python.exe scripts/verify_m2_pilot.py --run outputs/m2_pilot/<run>
.venv-m1/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=outputs/<unique_test_dir> tests/test_m2_pilot_workflow.py tests/scientific/ tests/test_kge_contract.py tests/test_kge_training.py tests/test_procrustes_controlled.py tests/test_drift_pipeline.py
.venv-m1/Scripts/python.exe -m ruff check .
```

Không dùng một wrapper tự động chạy tất cả các stages. Không commit/push dữ
liệu hoặc artifacts generated. Báo cáo cuối phải nêu rõ IMPLEMENTED/TESTED/
EXECUTED/VERIFIED cho từng phạm vi và blockers chưa xác minh.

## Alignment stage được yêu cầu tiếp — 14/10/2026

Backbone đã hoàn tất/verify ở run `outputs/m2_backbone/20261014T034042Z_65c464ba/`.
User tiếp tục yêu cầu **"Hãy làm bước này."** cho alignment. Stage-specific
`configs/m2_alignment_v1.yaml` ghi authorization mới và bind config/backbone
hashes, giữ approved backbone config/history nguyên vẹn. Thực hiện chỉ bước 5:
fixed anchors 101/66, shared pretransition-degree stratification, 81 comparisons,
2 repeats/comparison, independent SVD/anchor/lineage verification rồi Stage Report.

Chi tiết allocation version trước outcomes và báo cáo:
`docs/audit/M2_ALIGNMENT_REPORT_20261014.md`. Lệnh:

```powershell
.venv-m1/Scripts/python.exe scripts/run_m2_alignment.py
.venv-m1/Scripts/python.exe scripts/verify_m2_alignment.py --run outputs/m2_alignment/<run>
```

Không tự chạy empirical null/LTO/drift sau alignment.

## Empirical-null stage được yêu cầu tiếp — 14/10/2026

Alignment đã hoàn tất/verify ở `outputs/m2_alignment/20261014T040001Z_96d9ccbc/`.
User yêu cầu **"Hãy thực hiện bước tiếp theo"**; `configs/m2_null_v1.yaml` ghi
stage authorization, bind approved config/alignment manifest/independent
receipt hashes. Thực hiện chỉ bước 6: 6 endpoint-pair observations/entity,
pretransition-degree buckets, pooled adjacent merges, full-six target exclusion,
median/MAD/scale và availability; giữ mọi tham số đã duyệt.

```powershell
.venv-m1/Scripts/python.exe scripts/run_m2_null.py
.venv-m1/Scripts/python.exe scripts/verify_m2_null.py --run outputs/m2_null/<run>
```

Output analysis tables `noise_observations.parquet` và `lto_statistics.parquet`,
per-transition JSON/manifests/replays và independent report. Dừng sau Stage
Report `docs/audit/M2_NULL_REPORT_20261014.md`, không auto-run temporal drift.

## Longitudinal drift được yêu cầu tiếp — 14/10/2026

User yêu cầu **"Hãy thực hiện bước tiếp theo."** sau null/LTO verified.
Chỉ thực hiện bước 7 và đóng gói handoff Dev; dừng trước M4.
Stage config `configs/m2_drift_v1.yaml` bind approved configuration,
null manifest `7bdd6de62fc0f506661957e15909a9ecc43bdcfe935227425d22635436976b89`
và exact independent receipt hash. Giữ nguyên checkpoints, Q/fit means,
anchors, population, buckets, LTO references và epsilon đã duyệt.

1. Kiểm lại upstream input/artifact hashes và receipt verifier fingerprint.
2. Ghi jobs/population/config/code hashes trước đo drift: 9 transitions,
   6.897 persistent entity×transition, seeds 13/37/101.
3. Tính `1-cos((x_previous-mu_source)Q, y_next-mu_target)` cho 3 parallel
   seeds; delta_time là median ba values, không cross-seed temporal pairs.
4. Giữ `r = delta_time - LTO_median` kể cả âm;
   `SED_plus = max(0,r)/(1.4826*LTO_MAD + 1e-4)` chỉ khi reference available.
   Undefined cosine hoặc invalid alignment fatal; missing/null reference
   không sinh defaults/NaN/Inf và không dùng epsilon để cứu ZERO_MAD.
5. Chạy hai computation repeats/transition và hai Parquet serializations.
   Lưu `temporal_displacements.parquet` (20.691 rows), `entity_drift.parquet`
   (6.897 rows), support counts, raw JSON, manifests và Dev handoff hashes.
6. Independent NumPy verifier đo lại từ raw saved checkpoints/Q, kiểm median,
   r/SED+, negative values, population, JSON/Parquet, lineage và handoff.
7. Stage Report và progress; không tự chạy QA, MRR, H1 hoặc M4.

Engineering assumption: package `src/statistics` che Python stdlib module;
dùng deterministic median helper sẵn có, verifier dùng NumPy độc lập.
Không thay scientific semantics hoặc thông số. Tests bao phủ median-vs-mean,
translation invariance, signed-negative/positive, missing seeds/identities,
invalid references và nullable Parquet; Ruff toàn repo và full suite trước run.
Độ support thấp T01 high bucket được giữ trong bảng và báo cáo, không đổi
buckets/ngưỡng sau khi thấy outcomes. Đây vẫn là external-package Dev M2,
không G3 hoặc M1 certification.

```powershell
.venv-m1/Scripts/python.exe scripts/run_m2_drift.py
.venv-m1/Scripts/python.exe scripts/verify_m2_drift.py --run outputs/m2_drift/<run>
```

Stage đã EXECUTED/VERIFIED trong Dev scope:
`outputs/m2_drift/20261014T044648Z_ae9f0401/`, 20.691 temporal rows,
6.897 drift rows, 9 exact JSON replays, independent arithmetic/lineage/handoff
PASS. Full suite 505 passed/10 skipped, Ruff PASS. Báo cáo:
`docs/audit/M2_DRIFT_REPORT_20261014.md`. M2 Dev implementation/execution
đã hoàn tất đến entity drift và handoff; dừng, không auto-execute M4.

## Báo cáo và trực quan hóa bổ sung — 14/10/2026

User yêu cầu viết lại toàn bộ quy trình, trực quan hóa training logs/drift
và các đánh giá đã có. Chỉ đọc immutable stages, không train/re-align/đổi
measurement parameters hoặc advance M3/M4. Report run:
`outputs/m2_report/20261014T061101Z_a624c271/`, 10 PNG/SVG figures,
1.500 epoch loss rows, 6.897 joined drift rows và HTML tra cứu offline.
Independent source/log/quantile/HTML validation và browser QA PASS.
Full report: `docs/audit/M2_FULL_WORKFLOW_REPORT_20261014.md`.
