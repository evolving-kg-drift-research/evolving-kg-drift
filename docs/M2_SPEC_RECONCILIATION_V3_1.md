# M2 data 3.1 - Hòa giải đặc tả và kế hoạch sửa phép đo

Ngày: 21/10/2026. Giai đoạn: **1 - Hòa giải đặc tả**.

Trạng thái: **ĐÃ LẬP HỒ SƠ ĐỐI CHIẾU; CHƯA HOÀN TẤT HÒA GIẢI KHOA HỌC**.
Các quyết định còn thiếu được ghi cụ thể ở mục 5. Chưa chuyển sang giai đoạn 2.

## 1. Phạm vi đã thống nhất

- Theo chỉ đạo người dùng, **lấy M1 đã PASS với data 3.1 làm tiền đề**.
  Đây là cơ sở làm việc M2; báo cáo này không kiểm lại hay viết lại gate M1.
- Giữ TransE-L2, Procrustes, nhiễu nền median/MAD và SED+ làm phương pháp chính;
  ba seed chính là 13, 37, 101.
- Nhóm A: đúng đặc tả khoa học. Nhóm B: kiểm chứng implementation.
  Nhóm C: đánh giá độ bền vững có kế hoạch riêng.
- Giữ sáu khoảng cách nhiễu thô và provenance; mỗi entity đóng góp một median
  vào reference; loại target trước khi tính support và thống kê reference.
- Giữ signed excess, trạng thái khả dụng và lý do unavailable bên cạnh SED+.
- Lấy mẫu lại reference trước mắt chỉ là độ nhạy; phân vị không tự là p-value;
  can thiệp cấu trúc KG không là nhãn chuẩn drift ngữ nghĩa.
- Không tự thêm tiêu chí G3 hoặc chỉnh ngưỡng sau khi xem kết quả.

Sự đồng ý về hướng phát triển không tự chọn centered/affine cosine, định nghĩa
frequency, bucket policy hay các giới hạn số học chưa được đăng ký cụ thể.
Các tên trường mới bên dưới là dự thảo, chưa được kích hoạt trong runtime.

## 2. Nguồn và phạm vi thẩm quyền

Checkout thực tế: `codex/m2-drift-workflow`, HEAD
`abeb425385f8b19bb05db30c84c4bb05371e8640`; cây làm việc đã có thay đổi người dùng.
Chưa tạo được nhánh yêu cầu `M2-data-3.1` trong phiên trước; báo cáo này không
thử vượt giới hạn ghi Git metadata và không commit/push.

Thứ tự áp dụng theo AGENTS.md: scientific protocol và locked sources; kiến trúc/
module contracts; runtime; progress/audits. Audit và tests mô tả implementation,
không tự sửa định nghĩa ở nguồn khoa học.

| Vai trò | Nguồn ở repository | Bản trong package 3.1 | Kết quả kiểm lại |
|---|---|---|---|
| Đề cương PDF | `sources/huce_evolving_kg_modular_proposal(8).pdf` | Cùng tên trong `data/evolving_kg_downstream_v3_1/sources/` | Hai bản khớp SHA-256 đã khóa |
| Kế hoạch v1.0 | `sources/Research_Execution_Plan_v1.0.md` chưa có | Có file cùng tên | Hash khác lock repository; chưa thay thế bản gốc |
| Patch v1.1 | `sources/Research_Execution_Plan_v1.1_Patch.md` chưa có | Có file cùng tên | Hash khác lock repository; chưa thay thế bản gốc |

PDF khớp hash `d9e6d74b84fabdff880698eb6a5774bed8445897539b3713ba1e0594a446ea6f`.
Hash kỳ vọng và hash thực tế đầy đủ của mọi nguồn nằm trong `evidence.json`.
Protocol trong package cũng tham chiếu hai hash MD khác protocol repository;
không tự chọn bản package chỉ vì release M1 đã được lấy làm PASS.

ADR `docs/adr/0007-preserve-original-source-baseline.md` và decision log đã
yêu cầu giữ baseline gốc. Bản MD khác hash không được coi là original đã phục hồi.
Đây là giới hạn xác định đặc tả M2, không là kết luận nghiệm thu lại dữ liệu M1.

Đã trích lại từ PDF hiện tại các physical pages 6, 7, 13; render và xem trực
quan cả ba trang để xác nhận công thức (12)-(32) và bảng gate. Text và PNG nằm trong run evidence.
PDF pages 6/7/13 tương ứng các printed pages 5/6/12.

## 3. Ma trận đề cương - protocol - implementation

| Chủ đề | Đề cương có hash hợp lệ | Giao thức repository | Implementation Dev hiện tại | Trạng thái cho lần sửa |
|---|---|---|---|---|
| Backbone | TransE-L2 và kiểm soát nhiễu nhiều seed | `configs/kge.yaml`: seeds 13/37/101, dimension còn placeholder | Dev dùng d64, 50 epochs, lr0.01, margin1 | Giữ model/seeds; không tự biến cấu hình Dev thành scientific freeze |
| Fit Procrustes | Center fit means, SVD và Q=UV^T, (18)-(21) | Persistent anchors, deterministic disjoint split | Đã có centered fit và lưu Q/means | Kế thừa sau kiểm input/code/config lineage |
| Cosine | (14), (26): affine-aligned source `(x-mu_s)Q+mu_t` so với `y` | `one_minus_cosine_after_alignment`, chưa chỉ rõ vector | `artifact_null.py` và `artifact_drift.py` dùng `(x-mu_s)Q` so với `y-mu_t`; A19 test cũng yêu cầu centered | **Chưa chọn**, xem D-COS; liên quan M2-THEORY-003 |
| Đơn vị null | (27): median sáu distances/entity; (28): reference từ các entity khác | Same-snapshot cross-seed conditional | `artifact_null.py` và verifier flatten sáu distances của mỗi entity | Hướng sửa đã thống nhất: entity-level median; M2-THEORY-001 chưa được sửa |
| LTO và support | (28) loại target; sau (31) nêu dưới 50 entity-level observations phải mở rộng | Bucket merge còn placeholder | Loại sáu target distances; guard 5 pooled observations | Cần đăng ký policy cụ thể; support kiểm sau LTO, xem D-NULL |
| MAD và SED+ | (29): positive excess/(1.4826*MAD+epsilon); không Gaussian z-score | Epsilon còn placeholder; signed excess phải giữ | Formula có sẵn; epsilon1e-4, MAD floor1e-12 là giá trị Dev | Giữ formula; không tự kích hoạt các giá trị Dev cho scientific run |
| Residuals | (22)-(23): chia chuẩn Frobenius của target đã center bằng fit mean | Không có operating range số hoàn chỉnh | RMSE trên fit/holdout; gap là trị tuyệt đối | Cần thống nhất đơn vị và limits; xem D-DIAG, M2-THEORY-004 |
| Orthogonality và rank | (24): norm Frobenius chia d; bảng gate nêu rank fraction >=0.90, Eorth<=1e-6 | G3 dùng operating range khóa từ pilot | Norm thô; approved Dev dùng rank64, orth<=1e-4, holdout<=2, gap<=1 | Không chuyển ngưỡng giữa hai thang đo hoặc kết luận PASS/FAIL bằng cách so trực tiếp |
| Structural conditioning | (17), sau (31): degree/frequency; kNN là một khả năng fallback | Anchor pretransition stratified; merge policy chưa freeze | Fixed anchors/buckets degree-only; `SnapshotDataset.create` mặc định frequency=degree | Chưa chứng minh tương đương định nghĩa frequency của nguồn; cần xác định ý nghĩa/nguồn, không tự chế metadata |
| Quantile và seed sensitivity | (30)-(31) có Q0.95/tail statistic; đoạn kế tiếp nêu m3/m5; bảng B1 nhắc criterion khi pilot được chạy | Primary seeds vẫn 3; G3 range từ pilot | Chưa có hồ sơ pilot m3/m5 scientific hoàn chỉnh | Không gộp mọi nội dung này thành tùy chọn mới; cần ánh xạ theo nguồn, không tự thêm mọi thử nghiệm nhóm C vào G3 |

Bảng gate của PDF dùng nhãn B1/C và còn ghép Geometry/Path. Không đồng nhất nguyên
bảng đó với G3 repository hay tự nhập thêm path vào phạm vi nghiệm thu M2.
Kết luận G3 cần trace từng criterion tới nguồn áp dụng và cấu hình đã đăng ký.

## 4. Hợp đồng null cấp entity - dự thảo để review

Với một transition và target e, gọi R là tập reference entities sau LTO,
N=|R|. Mỗi u trong R phải có đúng sáu distances hữu hạn, định danh theo endpoint
và seed pair. Mỗi u đóng góp đúng một `median(six_distances)`.

| Trường dự thảo trong một reference row | Ý nghĩa và quan hệ kiểm tra |
|---|---|
| `raw_noise_observation_count` | Số distances thô của reference sau LTO; bằng 6*N khi đầy đủ |
| `reference_entity_count` | Số canonical entity IDs khác nhau trong R; bằng N |
| `reference_sample_count` | Số scalar entity medians trong reference; bằng N |

`raw_noise_observation_count` ở đây không bao gồm sáu distances của target và
không là tổng observation của cả transition. Sáu distances của target vẫn được
giữ ở bảng raw provenance riêng. Không tái sử dụng tên `observation_count` của
v1 với nghĩa mới mà thiếu version/schema discriminator rõ ràng.

Ở phương pháp chính đầy đủ, `reference_sample_count == reference_entity_count`
và `raw_noise_observation_count == 6 * reference_entity_count`. Minimum support
phải kiểm trên entities/samples cấp entity, không kiểm trên raw distances.
Trường hợp bootstrap có entity lặp thuộc schema sensitivity riêng; số lần lấy
mẫu không được coi là số entity độc lập mới hoặc dùng để mở gate support.

Phải lưu entity medians cùng liên kết tới sáu raw rows; không chỉ lưu tổng count.
Phân biệt empty reference, thiếu support, MAD suy biến, cosine không xác định,
missing seed/pair và alignment invalid. Null/SED unavailable có reason, không
đổi thành 0 hoặc dùng epsilon để cứu reference không hợp lệ.

Mọi output mới có schema/component/config versions, input/code hashes và manifest.
Giữ nguyên v1/historical outputs; adapter v2 phải từ chối artifact sai version
thay vì đoán ý nghĩa count. Không sửa schema M1 để chứa schema output M2.

## 5. Các quyết định còn cần chốt cụ thể

| ID | Lựa chọn cần quyết định | Phương án và tác động có thể review |
|---|---|---|
| D-SOURCE | Nguồn scientific baseline M2 | Giữ baseline hiện hành và phục hồi hai originals đúng hash; hoặc lập hồ sơ thay nguồn có version/amendment, giữ baseline cũ. Chưa có phê duyệt thay nguồn trong trao đổi này. |
| D-COS | Vector dùng cho cosine | **Affine**: theo (14)/(26) PDF; sửa cả temporal/noise và tests tương ứng. **Centered**: giữ invariance hiện tại; cần đăng ký rõ khác biệt với PDF. Cả hai vẫn dùng centered Procrustes để fit; không lấy SED/MRR để chọn. |
| D-NULL | Support, structural features và sparse policy | PDF hiện có nêu mốc50 entity samples. Một phương án để duyệt: kiểm >=50 sau LTO; lập merge plan chung theo structural counts trước LTO, group cần >=51 entities để mọi target còn >=50; merge adjacent, tie-break cố định. Bins3/6, degree-only, frequency semantics, epsilon/MAD floor và merge priority chưa tự được freeze. Nếu chọn kNN phải đăng ký features, scaling, distance, k và tie-break. |
| D-DIAG | Statistic và operating range G3 | PDF dùng relative residual và orth/d, với rank fraction/orth limits nêu trên; Dev dùng RMSE/raw norm. Cần xác định bộ áp dụng, rank tolerance, residual/gap limits và xử lý denominator suy biến. Không mang ngưỡng RMSE2/gap1 sang relative residual. |

D-NULL là phương án cụ thể để review, không là thuật toán đã được chấp thuận.
Việc đếm support50 không tự bảo đảm các reference entities độc lập hoặc có power.
Nếu chưa đủ support sau policy đã đăng ký, giữ unavailable có lý do.

Các tham số backbone/anchor counts, salts và dimension có thể kế thừa sau đánh
giá reuse; chúng cũng phải được ghi trong resolved config của lần chạy mới.
Chưa ghi decision log hay amendment như thể các lựa chọn ở bảng này đã được duyệt.

## 6. Phạm vi sửa đồng bộ sau khi hòa giải

| Chuỗi | Các file cần review/sửa có giới hạn |
|---|---|
| Raw noise, entity medians, bucket/LTO | `src/drift/artifact_null.py`, `scripts/run_m2_null.py`, `scripts/verify_m2_null.py` |
| Calibrated drift và count guards | `src/drift/artifact_drift.py`, `scripts/run_m2_drift.py`, `scripts/verify_m2_drift.py` |
| Geometry/conditioning nếu quyết định yêu cầu | `src/drift/procrustes.py`, `src/drift/fixed_anchors.py`, `src/kge/contract.py`, alignment runner/verifier |
| Entry points khác đang dùng semantics cũ | `src/drift/null.py`, `src/drift/metrics.py`, `src/drift/pipeline.py`; phải chọn route v2 hoặc từ chối scientific use của route v1 |
| Báo cáo/handoff | `scripts/build_m2_report.py`, `scripts/verify_m2_report.py`, versioned M2 output contracts/configs |
| Regression | `tests/test_m2_null_workflow.py`, `tests/test_m2_drift_workflow.py`, scientific LTO/merge/six-pair/centered-cosine tests và geometry tests liên quan |

Không sửa toàn bộ file theo danh sách một cách máy móc; implementation stage
phải xác định các consumers thực tế trước, giữ compatibility có version.
Verifier phải dựng lại entity medians/reference bằng tính toán độc lập từ raw
observations, không gọi helper production rồi coi đó là đối chiếu độc lập.

Regression tối thiểu: fixture phân biệt pooled/entity medians; target exclusion;
count units; missing/duplicate seed pair; 49/50 support sau LTO nếu chọn50;
merge adjacency/ties/order; empty/zero-MAD; cosine cases phân biệt hai estimands;
normalized residual/orth units; tampered provenance và schema-v1 rejection.

## 7. Reuse, chạy lại và nhóm C

Kiểm lại 10 canonical snapshot files: SHA-256 thực tế khớp cả preflight cũ và
preflight V3.1. Snapshot/mapping records cũng trùng; Parquet row counts được
đọc lại. Đây chưa là kiểm chứng tái sử dụng checkpoints.

- Chỉ sửa entity-level estimator/count/merge: sau khi xác nhận các input khác
  không đổi, có thể giữ checkpoint/Q/raw distances và chạy lại null/LTO/drift,
  verifiers/report. Không mặc định train lại30 mô hình.
- Đổi cosine: raw noise và temporal distances bị ảnh hưởng; không dùng lại
  distances cũ. Q có thể giữ nếu fit/anchors/validity criteria không đổi và đã
  kiểm chứng lại.
- Đổi anchor/structural conditioning: cần tạo plan và alignment artifacts mới;
  không mặc định thay training checkpoints.
- Đổi training config/dimension/code/mapping: đánh giá checkpoint nào mất điều
  kiện reuse; chạy mới theo version, không sửa provenance checkpoint cũ.

Nhóm C tách thử nghiệm reference/anchor/training; giữ ba seed chính cố định.
Đối chứng số học dùng nhóm bất biến của estimand đã chọn; KG không đổi cần
training variation thực sự; KG can thiệp nằm trong bộ thử riêng.
Không can thiệp canonical data3.1 để tạo đối chứng. Không dùng kết quả nhóm C
để lựa chọn lại phương pháp chính theo SED/H1/QA đã quan sát.
Q0.95, m3/m5 và các yêu cầu có sẵn trong nguồn phải được ánh xạ trước khi phân
loại là G3 hoặc extended diagnostics. Không báo FPR5% chỉ vì dùng Q0.95.

## 8. Bằng chứng và mức kiểm chứng của giai đoạn 1

Run evidence:
`outputs/m2_spec_reconciliation/20261021T050958Z_b8d8b9c9/`.

- `evidence.json`: hash inventory, exact code traces và sáu numerical fixture probes.
- `reproduce.py`: script không training, không scientific gate evaluation;
  `--check-only` tính lại evidence và đối chiếu bản đã lưu.
- `proposal_page_6.txt`, `proposal_page_7.txt`, `proposal_page_13.txt` và ba
  PNG tương ứng: trích/render từ PDF hiện tại có hash hợp lệ.
- `experiment_manifest.json`: provenance/inputs/config/output hashes của run đối chiếu.
- `completion_manifest.json`: kết quả kiểm tra cuối cùng; không là G3 certificate.

Lệnh tái kiểm evidence:

```powershell
.venv-m1/Scripts/python.exe -B outputs/m2_spec_reconciliation/20261021T050958Z_b8d8b9c9/reproduce.py --check-only
```

Sáu probes thuộc fixture: pooled center0.1/MAD0 so với entity center0.3/MAD0.2;
target exclusion; count units12 raw/2entities/2samples; centered1 so với
affine1-220/221; orth raw so với orth/d; support boundary dự thảo49/50/51.
Không có implementation regression mới của estimator đã sửa vì chưa sửa code.

| Tier | Phạm vi đạt được |
|---|---|
| IMPLEMENTED | Hồ sơ đối chiếu, dự thảo count contract, impact/reuse plan và bằng chứng; chưa implementation patch |
| TESTED | Numerical fixtures và kiểm tra tài liệu/evidence; kết quả chi tiết ở completion manifest |
| EXECUTED | Chỉ thao tác đọc/đối chiếu sources, metadata và fixtures; chưa scientific production stage |
| VERIFIED | Hash nguồn/10 snapshots, code traces và numerical differences trong phạm vi evidence; chưa xác minh phương pháp đã sửa |

**G3: CHƯA ĐÁNH GIÁ trong giai đoạn này.** M1-PASS là tiền đề người dùng;
không tự tạo certificate hoặc sửa gates. Findings M2-THEORY-001 đến -004 chưa
được đánh dấu RESOLVED. Đã chuẩn bị hồ sơ giai đoạn1; cần giải quyết D-SOURCE,
D-COS, D-NULL và D-DIAG trước khi xác nhận hòa giải hoàn tất và sang giai đoạn2.
