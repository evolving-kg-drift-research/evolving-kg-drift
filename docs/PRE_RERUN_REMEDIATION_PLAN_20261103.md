# Kế hoạch chỉnh sửa trước phiên chạy mới — 03/11/2026

Trạng thái: **PROPOSED — kế hoạch để review, chưa triển khai sửa code hoặc chạy production**.

Căn cứ: [audit 14 findings](audit/PRE_RERUN_CODEBASE_REVIEW_20261103.md), checkout
`eadf22abc436dcbe2f12ae850ed9a5e4382dc714`, `configs/protocol_v1.yaml`, locked sources
hiện hành, `docs/data_pipeline_spec.md`, architecture/module contracts và amendment
AMEND-2026-001. Audit trước ghi nhận 652 passed, 10 skipped, Ruff PASS trên Python
3.11.9; đây là baseline của audit, không phải tests đã chạy lại cho kế hoạch này.

## 1. Kết quả cần đạt

1. Loại bỏ các lỗi đã tái hiện, có regression tests chứng minh sửa đúng root cause.
2. Có quy trình train–validation ghi đủ thông tin để đánh giá hội tụ và chất lượng
   dự đoán, với split/sampling/candidate universe được định danh trước khi train.
3. Mỗi stage đọc đúng inputs của phiên mới, kiểm hashes và bàn giao manifests hợp lệ.
4. M4 dùng empirical pseudo-drift, complete-support population và H2 populations
   đúng protocol; inference không tự chạy nối tiếp evaluation.
5. Chỉ chạy dữ liệu thật khi readiness của scope tương ứng được kiểm chứng. Không
   đánh dấu gate PASS từ unit tests, fixture runs hoặc exit code 0.

Không đặt mục tiêu phải làm MRR tăng hoặc H1 có ý nghĩa thống kê. Nếu implementation
đúng nhưng kết quả âm, báo cáo kết quả âm cùng các giới hạn thay vì chỉnh thiết kế
để tạo kết quả đẹp.

## 2. Hai vai trò mô hình phải tách rõ

| Vai trò | Dữ liệu train | Mục đích | Quy tắc đánh giá |
|---|---|---|---|
| `quality_validation` — tên vai trò đề xuất | Chỉ train partition đã đăng ký | Theo dõi train/validation theo epoch; đánh giá link prediction | Held-out không được tham gia gradient; test cuối độc lập với lựa chọn mô hình |
| `drift_backbone` — tên vai trò đề xuất | Snapshot canonical theo training design đã duyệt | Alignment, same-snapshot null, longitudinal drift | Giữ cùng model/seeds và budget training đã đăng ký; không gọi training triples là validation |

Khuyến nghị triển khai đánh giá chất lượng trước trên một phạm vi nhỏ như T01,
sau đó mới mở rộng theo thiết kế được duyệt. T01 hiện chỉ có 121 triples, 167
entities; báo cáo feasibility trước ghi nhận 121 entities xuất hiện trong một
triple. Witness 101 train / 20 held-out chỉ chứng minh một split hai phần khả thi,
không tự cấp quyền chia tiếp hoặc đủ statistical power.

Không tự dùng validation checkpoint thay cho full-snapshot backbone. Nếu muốn
backbone chính cũng giữ held-out, đó là thay đổi training population cần đăng ký
và tính lại mọi downstream artifact phụ thuộc embedding mới.

Giữ TransE-L2 và seeds 13/37/101. Run lịch sử dùng d64, lr0.01, margin1, 50 epochs;
không tự đổi kiến trúc, optimizer, batching hoặc tự freeze các giá trị Dev.

## 3. Những quyết định phải chốt trước execution

Các sửa kỹ thuật có thể triển khai và kiểm fixture trước. Những mục dưới đây là
điểm dừng trước thao tác phụ thuộc scientific semantics; kế hoạch không tự phê duyệt.
Không hỏi lại những quyết định đã có evidence hợp lệ, như source amendment và
Affine cosine trong decision log ngày 28/10.

| Mã | Cần chốt | Phương án/đề xuất để review | Evidence/đầu ra cần có |
|---|---|---|---|
| D01 | Scope phiên mới | Diagnostic KGE trên canonical data3.1; hoặc full certified M1→M4. Hai scope phải ghi riêng | Scope statement, input package/hash, prerequisites; không diễn giải ngoại lệ M2 Dev cũ thành full M1 PASS |
| D02 | Split và population đo chất lượng | Kiểm coverage và độ lớn trước; không áp 80/10/10 hay 101/20 mặc định. Nếu chưa đủ test độc lập thì chỉ gọi diagnostic | Explicit canonical triple memberships, split version/salt, coverage/OOV/relation report, split hash |
| D03 | Epoch budget và chọn checkpoint | Chốt max epochs, lịch validation, selection metric/tie và early-stop rule trước train. Đề xuất chọn budget chung cho drift backbone từ pilot hợp lệ | Registered training/evaluation policy; không chọn epoch từng seed/snapshot theo SED+, H1 hoặc M4 outcomes |
| D04 | Negative sampling và filtered ranking | Training filter chỉ theo training positives là phương án đề xuất; validation/test filtering phải có scope as-of rõ ràng và riêng với gradient | Sampling/filter versions, fixed evaluation negatives, candidate/hash, positive-filter artifact/hash; không dùng future positives |
| D05 | Backbone/measurement registration | Chuyển các giá trị đã được duyệt vào một resolved design, không lấy defaults thay registration | Dimension, anchors, degree/frequency definition, bucket/merge order, epsilon/MAD/support và input plan có binding |
| D06 | Diagnostics conflict | Hòa giải `1e-5` trong D-DIAG decision với `1e-6` trong config/runners bằng approval evidence và source hierarchy | Một giá trị authoritative nhất quán; không tự tăng/giảm để pass |
| D07 | Empirical pseudo-drift | Dùng đúng thuật toán same-snapshot đã khóa trong nguồn/registration. Nếu chưa đầy đủ công thức thì chốt công thức trước implementation scientific | Estimator version, raw same-snapshot observations, seed/pair/anchor lineage, calibration/reference rule và independent verifier |
| D08 | H2/open-world populations | Tách old-query candidate-expansion diagnostic khỏi secondary full-open-world/New-or-OOV population | Query-generation/eligibility rules, gold-answer/filter rules, query/candidate hashes, coverage và frozen-OOV policy |
| D09 | M1 contract và inference | Chốt physical schema/migration; chốt H1 controls, WCB seed/draws và panel balance/missingness handling theo protocol | Approved contract/version và frozen inference config; không chọn controls hoặc sample sau khi xem coefficient |

Validation cũ đã dùng để chọn dimension không trở thành independent test chỉ vì
đổi tên hoặc đổi salt. Cần ghi lịch sử sử dụng dữ liệu và giới hạn confirmatory
claims. `data/locked_test/` không được mở để thiết kế split hoặc bổ sung test trước W8.

## 4. Thứ tự chỉnh sửa và điều kiện phụ thuộc

Các gói dưới đây là thứ tự implementation/review, không phải lệnh tự chạy các
production stages. Mỗi gói giao một diff scope nhỏ, regression evidence và trạng
thái IMPLEMENTED/TESTED; execution/verification có báo cáo riêng.

| Gói | Nội dung | Findings | Phụ thuộc để nghiệm thu |
|---|---|---|---|
| P0 | Chặn entrypoints nguy hiểm và scientific fallback sai | 01, 14 | Reproducing tests; không cần dữ liệu thật |
| P1 | Manifest/input contracts và stage boundaries | 09, 10, 11 | P0; contract tests |
| P2 | Checkpoint integrity và version compatibility | 08 | P1 lineage contract |
| P3 | Split, RNG và loss diagnostics | 04, 05, 06, 07 | P2; D02–D04 trước chạy thật |
| P4 | Epoch validation/ranking logs và independent verifier | 04–07, 09, 10 | P1–P3; D02–D04 |
| P5 | M1 schema/readiness và M2 measurement registration | 09, 12, 13 | Engineering có thể chuẩn bị sớm; acceptance cần D01, D05, D06, D09 |
| P6 | M4 populations, support, empirical pseudo và statistics handoff | 01, 02, 03, 10, 11 | P1, P2; algorithms/populations cần D07–D09; execution cần M2 verified |
| P7 | Tích hợp, readiness và hồ sơ bàn giao chạy mới | Toàn bộ 14 | Các gói áp dụng đã TESTED; decisions/prerequisites của scope đã đủ |

P5 là điều kiện trước **full scientific execution**, không phải lý do để ngừng
sửa/test các lỗi engineering KGE/M4 bằng fixtures. SUPPORT/STRETCH không được
chặn các gói CORE.

## 5. P0 — Chặn thao tác phá dữ liệu và pseudo scientific fallback

**Files đích:** `scripts/import_to_neo4j.py`,
`scripts/run_m4_evaluation_and_stats.py`; tests liên quan Neo4j và M4 workflow.

1. Đưa hai audit reproductions vào regression tests thật, dùng fake DB driver và
   fixture artifacts. Tests fail trên code cũ trước khi patch.
2. Gỡ đường chạy mặc định có global `DETACH DELETE`. Legacy importer phải dừng
   trước kết nối/ghi DB hoặc chuyển sang verified materializer với explicit run.
   Không thêm reset tự động, không phát triển flow xóa DB trong remediation này.
3. M4 từ chối chạy scientific falsification khi không có verified empirical pseudo
   artifact. Bỏ Gaussian replacement và fallback MAD `0.05` trong production path.
4. Ghi rõ unavailable/blocked reason; không đổi một nhánh sai thành p-value/null
   effect có vẻ hợp lệ. Complete empirical implementation ở P6 sau D07.

**Tests:** fake-driver first action không global-delete; invalid inputs không
gọi DB; thiếu/mismatch pseudo artifact fail trước metrics; mock random draw không
thể trở thành pseudo regressor. Không gọi real Neo4j hoặc hosted LLM.

**Done:** hai defect paths được chặn, tests fail→pass; historical DB/artifacts
không đổi. Chỉ ghi IMPLEMENTED/TESTED cho guard, chưa gọi pseudo scientifically verified.

## 6. P1 — Một contract cho inputs, manifests và stage handoff

**Files đích:** `scripts/inspect_m2_inputs.py`, `scripts/run_m2_backbone.py`,
`scripts/run_m2_measurement_v2.py`, hai `scripts/run_m2_*_v2_all_transitions.py`,
`scripts/run_m4_evaluation_and_stats.py`, các verifier tương ứng.

**File mới dự kiến, chỉ trong phạm vi cần dùng:**
`src/kg_pipeline/experiment_manifest.py` để dùng chung builder/validator;
`scripts/run_m4_evaluation.py`, `scripts/run_m4_statistics.py` để tách hai stage;
tests workflow/manifest tương ứng. Tên module mới là đề xuất, chưa phải API có sẵn.

1. Tách logic builder/validator dùng lại từ code đang có, cùng
   `kg_pipeline.hashing` và immutable storage. Không tạo manifest schema thứ hai.
2. Ghi actual commit SHA, true dirty state, resolved config hash, snapshots/mappings,
   query/candidate/input artifact hashes, seed, component versions, executed code,
   environment, access và output hashes dưới `artifacts.hashes` đúng schema hiện có.
   Field không áp dụng dùng null có lý do; không tạo synthetic placeholder hashes.
3. Validator kiểm required fields, kiểu/giá trị, hash structure và stage-specific
   requirements. `HEAD`, thiếu sidecar/input hash và status-only approval không
   được coi là verified identity.
4. Thay constants trỏ run tháng 10 bằng explicit descriptors trong registered
   config/plan; resolve path an toàn trong roots cho phép, kiểm bytes trước đọc và
   recheck trước publish. Không tự chọn latest run hoặc fallback về historical run.
5. Evaluation chỉ tạo Stage 8 artifacts và Stage Report. Statistics là entrypoint
   riêng, yêu cầu evaluation manifest + independent receipt đúng hash. Combined
   entrypoint cũ không còn mặc định chạy liên tiếp hai stage.
6. Thư mục run unique, outputs append-only. Khởi tạo trước execution: resolved
   design, registered jobs, input/code hashes. Finalize manifest sau outputs;
   incomplete run không được downstream nhận như completed.

**Tests:** actual writers validate schema; wrong hash/path escape/duplicate input/
missing receipt/commit alias fail; hai fixture run IDs không bị trộn; evaluation
không gọi FE/WCB. Test input mutation giữa read/publish và output overwrite refusal.

**Done:** mọi producer mới dùng contract chung; old manifests không được sửa để
điền provenance suy đoán. Verifier chỉ đọc và ghi receipt mới, không rewrite run cũ.

## 7. P2 — Checkpoint bắt buộc integrity và giữ khả năng đọc lịch sử

**Files đích:** `src/kge/checkpoint.py`, `tests/test_kge_training.py`,
`tests/test_m2_backbone_workflow.py`, tests của các loader downstream.

1. Chế độ `verify_sidecar=True` phải reject sidecar thiếu/rỗng/malformed hoặc
   physical hash sai; kiểm recomputed semantic hash, finite vectors và dimension.
2. Dùng immutable lock/write primitive hiện có để kiểm tra và publish artifact;
   checkpoint chưa có đủ sidecar/manifest completion không đủ điều kiện handoff.
3. Training design mới được version: model-config hash, resolved training-design
   hash, split/negative/candidate hashes, role và epoch được bind ở checkpoint và
   manifest. `config_hash` của format mới phải bao phủ thiết kế thực sự đã chạy.
4. Không thêm default fields vào serialization v1 làm đổi hash v1. Dispatch theo
   version; giữ đúng phép semantic hash/rounding của v1 khi verify checkpoint cũ.
   New format có contract/version riêng, không reinterpret historical bytes.
5. Nếu cần đọc legacy unverified trong exploration, phải là opt-out tường minh;
   scientific runners không được sử dụng nhánh này.

**Tests:** finite tamper + stale semantic hash, missing/empty sidecar, wrong width,
save/load round-trip, collision/overwrite guard; retained fixture v1 có sidecar
đúng vẫn verify được. Crash trước completion không được nhận làm input hợp lệ.

**Done:** audit RERUN-08 không còn tái hiện, old valid artifacts vẫn đọc đúng;
chưa có checkpoint production mới được tạo.

## 8. P3 — Split, RNG và loss đủ tin cậy

**Files đích:** `src/kge/trainer.py`, `src/kge/model.py`,
`src/kge/contract.py`, `scripts/run_m2_pilot.py`; các tests KGE/scientific sampling.

**Module mới dự kiến:** `src/kge/splits.py` để chia sẻ split logic thay vì domain
code import ngược từ `scripts/`.

### Split và experiment identity

- Dùng canonical `(subject_id, relation_id, object_id)` và registered algorithm/
  salt để định danh membership; không dùng mutable integer mapping indices.
- Kế thừa coverage-preserving logic có sẵn ở pilot sau kiểm tra, không viết một
  thuật toán khoa học khác. Validate disjoint/exhaustive partitions, unique triples,
  counts, training entity/relation coverage và OOV policy.
- Persist memberships/hash trước initialization/gradient. Chưa có explicit split
  hợp lệ thì validation run fail; không quay về full training hoặc dùng train loss
  thay validation cho dimension/checkpoint selection.
- Full-snapshot role được khai báo validation không áp dụng; đây là mode có chủ
  đích, khác với requested-validation-but-empty. Train ratio sai miền phải fail.
- Resolved design hash chứa model parameters, snapshot/train/split identity,
  sampling/filter versions, evaluation policy và epoch selection rule.

### RNG và sampling

- Tách initialization/training/evaluation streams, giữ model seed IDs 13/37/101.
  Derivation/version của stream được lưu; evaluation không tiêu thụ training RNG.
- Validation negative pairs được tạo một lần theo D04, hash và dùng lại giữa
  epochs; cùng evaluation design cho các seed khi cần so sánh. Không tạo fixed
  negatives từ future graph/mappings.
- Không thêm validation triples vào gradient. Filtering positives/candidates tuân
  theo D04, không để helper hiện tại âm thầm quyết định policy bằng toàn dataset.

### Loss diagnostics

- Ghi `loss_sum`, denominator definition, number of positive examples, valid
  negatives, skipped/exhausted samples và margin violations. Version metric nếu
  thay denominator; không rewrite loss cũ.
- Zero usable examples/zero validation observations phải fatal hoặc unavailable
  có reason theo contract; không trả numerical zero để biểu thị không đánh giá.
- Giữ đúng TransE L2 gradient và per-triple SGD. Không sửa batch/optimizer/epsilon
  để làm curves mượt hoặc tests pass.

**Tests fail→pass:** evaluation bật/tắt không đổi weights/RNG với cùng train
partition; evaluation không mutate weights; mapping reindex/order permutation
không đổi split; explicit empty split/OOV fail; dense graph không negative không
báo successful zero loss; model/seed changes và split changes có đúng identity.

**Done:** RERUN-04–07 được sửa ở code tier; deterministic fixture replay cùng
input/config/runtime khớp bytes. Cross-platform determinism không được suy từ một OS.

## 9. P4 — Validation logs và chứng minh chất lượng embedding

**Files đích:** trainer/model và pilot/backbone runners/verifiers liên quan;
`scripts/build_m2_report.py`, `scripts/verify_m2_report.py` và template chỉ sửa
những phần tiêu thụ logging contract mới.

**Files mới dự kiến:** `src/kge/validation.py` (held-out link prediction),
`scripts/verify_kge_validation.py` (saved-artifact verifier),
`tests/test_kge_validation_workflow.py`. Tái sử dụng conventions đã có trong
`scripts/evaluate_legacy_t01.py`, không âm thầm đổi QA scoring contract.

1. Mỗi epoch của `quality_validation` lưu training objective, fixed-sample
   post-epoch train evaluation loss nếu dùng để so train/validation, fixed-sample
   validation loss và validation MRR/Hits@1/3/10. Tên trường phải phân biệt online
   training loss với loss được chấm sau epoch trên model cố định.
2. Evaluation ranks head/tail theo registered candidates, known-positive filter
   và tie rule; lưu candidate/filter hashes, OOV flags, score/rank/RR và observation
   counts. Validation metric không dùng làm upstream anchor/bucket criterion.
3. Log immutable theo epoch/chunk; checkpoint có epoch/run/seed/role và file name
   riêng. Schedule lưu checkpoints và best/final pointer được đăng ký trước; không
   overwrite `best.json` chứa weights. Best pointer là selection artifact mới.
4. Để replay đầy đủ validation curves, ưu tiên lưu checkpoint ở mọi monitored
   epoch của pilot nhỏ. Nếu chỉ lưu theo mốc, công bố rõ phần curves không thể
   recompute từ checkpoint; không claim full independent numerical replay.
5. Với 30 full-snapshot backbones, lưu train diagnostics và checkpoint schedule
   đã chốt; không tạo giả validation loss. Ước lượng storage trước khi bật lưu
   embedding mọi epoch cho cả 30 models.
6. Final test chỉ chấm model/rule đã chọn sau validation, không chấm mỗi epoch để
   chọn checkpoint. Test result và checkpoint trước full-snapshot refit được bind
   riêng; không gán held-out score đó cho checkpoint đã học lại toàn dữ liệu.
7. Báo cáo có raw curves, mean/spread giữa 3 seeds, sample coverage, baseline cùng
   candidate/filter/tie rules. Tái sử dụng frequency baseline nếu được đăng ký;
   không chọn baseline sau khi xem kết quả để làm mô hình nổi bật hơn.
8. Verifier recompute distances/loss/ranks từ serialized vectors + frozen inputs
   bằng code độc lập, không gọi lại evaluator đã sinh kết quả. Kiểm hash chain,
   selection/tie và final-test access history.

**Tests:** exact small-vector reference ranks/loss; filtered multi-answer gold
không bị loại; ties, OOV, non-finite scores, wrong candidate/filter hashes; log
tampering, missing epoch/checkpoint và best-selection mismatch bị reject.

**Done:** fixture train→log→checkpoint→independent verifier→report PASS. Bằng chứng
thật về hiệu quả chỉ có sau execution riêng; không hứa loss giảm là MRR tăng.

## 10. P5 — M1 schema và đăng ký phép đo M2

### P5a. Contract M1 — RERUN-12

**Files đích:** `config/schema.yaml`, `src/kg_pipeline/contracts.py`,
`src/temporal/schema.py`, `src/kg_pipeline/contract_authority.py`, các producers và
consumers đúng các fields bị ảnh hưởng; tests contract/temporal/handoff/parity.

1. Từ fresh diff lập bảng từng field cho 9 bảng lệch: authoritative name, runtime
   name, Arrow type, nullable, PK/FK, producer/consumer và provenance/clock meaning.
   Làm tương tự physical declarations cho đủ 17 bảng.
2. D09 phải duyệt canonical contract/migration. Không rename `FactVersionID`,
   `LogicalFactID`, timestamps hoặc bịa field values chỉ để khớp tests.
3. Version schemas và components liên quan; cập nhật dataclasses/Arrow producers/
   consumers đồng bộ sau approval. Dữ liệu thiếu đi quarantine/fatal theo contract.
4. Migration/rebuild tạo run mới từ immutable upstream evidence đã được duyệt;
   không sửa lịch sử acquisition, raw hoặc FactVersion. Không rerun Stage 4.3.
5. Fixture validation gồm axes observed/valid/acquired tách biệt, future mapping,
   revision/supersession, exact support/exclusion lineage và official M2 adapter.
   Physical source hashes đúng không thay thế temporal validation.

**Done ở code tier:** machine-contract audit không còn field/type/key/nullability
mismatch theo approved contract; existing negative guards vẫn fail đúng. Real
artifact verification và Neo4j read-back là execution stage riêng, chưa tự cấp G1/G2.

### P5b. M2 registered inputs/settings — RERUN-09, 13

**Files đích:** `scripts/run_m2_measurement_v2.py`, các v2 wrappers và verifier;
candidate configs hiện có chỉ dùng làm reference. New registered config/plan phải
có version mới; protocol update chỉ phản ánh approved decisions/amendment.

- Kế thừa guarded loader, physical/content hash separation, geometry engine và
  independent NumPy verifier đang có. Không duy trì hai đường v2 khác nhau, một
  đường strict registration và một đường hard-code bỏ qua registration.
- Bind input package hiện hành, 30 checkpoints, mapping/config hashes, anchor
  plans/alignments, buckets, settings và previous-stage receipt. Không rebind một
  old alignment vào weights mới chỉ vì entity IDs/dimension vẫn giống.
- Giữ entity-level median-six rồi LTO, ba temporal seed pairs và invalid-alignment
  unavailable; affine estimand theo quyết định đã có. Null và drift phải dùng cùng
  resolved geometry/settings và hashes.
- Một invocation chỉ một stage; có thể xử lý nhiều transitions cùng stage nếu
  plan đã đăng ký. Null stage không tự chạy drift; drift không tự chạy evaluation.
- Stage config sẵn sàng không tự bật `scientific_certification=true`. Gate evidence
  phải có scientific verifier thực sự trong scope đã duyệt.

**Tests:** inactive/missing approval/plan, conflicting thresholds, future/wrong
mapping, mixed run checkpoints/alignments, missing seed/pair, corrupted Q và stale
null receipt fail; rank/denominator/sparse null unavailable không tạo SED+ giả.

**Done:** check-only readiness không còn blocker áp dụng cho scope được duyệt;
real artifacts chưa được tính lại. Full scientific scope vẫn cần P5a/M1 evidence.

## 11. P6 — Evaluation và thống kê đúng population, có empirical pseudo

**Files đích:** `src/evaluation/qa_panel.py`, hai M4 runners tách ở P1,
`src/statistics/two_way_fixed_effects.py` chỉ khi guards/verification thực sự cần,
`configs/statistics.yaml` sau approval, tests M4 unit/workflow.

### Complete support — RERUN-02

- Deduplicate support entities theo protocol; xác nhận tất cả supports có đúng
  transition, checkpoint/drift hashes, finite values và available=true.
- Nếu một support thiếu, lưu null + structured reason + primary eligibility=false;
  không median partial list hoặc dùng zero thay missing. Giữ toàn bộ ranking rows
  và xuất population/coverage counts; scientific H1 chỉ dùng declared eligible rows.
- Nếu eligibility làm panel không còn đúng balance contract, dừng statistics và
  báo rõ; không tự drop khó queries hoặc thêm dữ liệu để làm panel cân bằng.

### Populations và OOV — RERUN-03

- H1 recurring panel và H2 primary Seen-at-T1 được giữ theo definitions đã đăng ký.
- Secondary full-open-world/New-or-OOV theo D08 có explicit query population,
  candidates và reasons, không suy luận population chỉ từ candidate expansion.
- A/B dùng cùng primary candidate universe của mỗi evaluation condition;
  frozen unseen candidates score -inf, OOV gold RR=0; không loại query để tăng MRR.
- Nếu dữ liệu thực không có eligible New/OOV queries, báo population không có
  support cho claim tương ứng; không tạo synthetic gold hoặc ép có hiệu ứng OOV.
- Lưu raw per-seed ranks/RR rồi median theo protocol; không chỉ lưu aggregate.

### Empirical pseudo và inference — RERUN-01, 10, 11

- Sau D07, implement empirical pseudo từ raw same-snapshot seed-pair artifacts
  với estimator/calibration/anchor rules đã đăng ký; giữ provenance đến mỗi distance.
- Independent verifier tính lại pseudo/query aggregation từ vectors/raw observations.
  Thiếu pseudo hoặc geometry unavailable phải block/unavailable theo policy.
- Statistics đọc verified evaluation + pseudo receipts; configs cung cấp controls,
  seed/draws/inference choices, không hard-code mặc định cho scientific run.
- Kiểm finite values, unique Query×Transition rows, declared population/balance,
  non-degenerate design, đủ cluster và bootstrap draws theo registered rule.
  Degenerate SE/cluster phải có error, không biến thành non-significant result.
- Kiểm FE bằng independent dummy-regression fixture; kiểm WCB invariants/replay
  theo thuật toán đã đăng ký. Không sửa covariance/inference chỉ vì p-value khác.
- Report nêu association observational, population/sample size và limitations.
  Không chuyển p>alpha thành chứng minh không có spurious effect; tách kết quả test
  và verdict gate theo pre-registered decision rule thực sự có.

**Tests:** complete/partial/all missing, duplicate supports; distinct old/new query
populations, positive/negative OOV fixtures, identical A/B candidate hashes;
empirical pseudo raw replay + tamper; stats-only requires receipts; missing settings,
duplicate panel rows, insufficient/degenerate clusters fail. End-to-end fixture
không dùng synthetic scientific defaults trong production path.

**Done:** Stage 8 và Stage 9 có hai manifests/verification reports riêng, no
auto-advance; RERUN-01/02/03 không còn tái hiện trên fixtures. Chưa kết luận H1/H2 thật.

## 12. P7 — Integration, CI và readiness cuối

**Files đích:** targeted tests ở trên, `tests/test_hard_invariants.py`,
`.github/workflows/ci.yml`, gate verifiers và docs/PROGRESS cần cập nhật đúng tier.

1. Chuyển audit probes thành regression tests thực sự gọi domain code/entrypoints;
   giữ audit cũ làm evidence, không dùng chính expected output của implementation
   làm independent reference.
2. Thực hiện 8 skipped CORE invariants đã có module: finite embeddings, orthogonal
   Q, disjoint anchors, diagnostics, LTO, finite drift, A/B universe và frozen OOV.
   Có thể tái sử dụng meaningful fixtures/helpers; không thêm assertions rỗng.
3. Kiểm locked-access guard bằng fake paths/fixtures, không mở real locked data.
   Arm C exact-B fallback chỉ thuộc active scope khi SUPPORT được đăng ký; optional
   tests không được ghi thành CORE scientific PASS hoặc làm chậm CORE remediation.
4. Test temp phải nằm trong thư mục run mới của workspace trên Windows; đổi
   `tests/test_kge_training.py` sang pytest `tmp_path` nếu cần cho atomic writer test.
   Không sửa checkpoint writer để né lỗi riêng của system temp.
5. Chạy targeted suite sau từng patch; chạy full suite khi hoàn tất integration,
   Ruff toàn repo, Python 3.10 và 3.11 trên interpreters/CI thật. Không suy ra
   compatibility 3.10 chỉ từ kết quả 3.11.
6. CI báo rõ code/scaffold/fixture/production verification scopes. Required gate
   test bị skip phải block gate; trước freeze, W1/W7 `--ci` vẫn chỉ scaffold.
7. File-backed integration fixture chạy tách từng stage, kiểm manifests, input
   immutability, exact replay và reject corrupted handoff. Không dùng fixture PASS
   để bỏ prerequisite scientific registration hoặc M1 acceptance.
8. Tạo readiness report với findings status, applicable decisions/prerequisites,
   protected hashes, input descriptors, code/environment/config versions và next
   authorized stage. `READY` chỉ khi không còn blockers áp dụng; không force flag.

**Done:** mọi finding có evidence/status riêng; tests required cho scope đạt,
Ruff=0 errors; scientific choices/gates còn thiếu được giữ BLOCKED. Mọi execution
tiếp theo vẫn cần yêu cầu explicit cho stage đó theo AGENTS §8.2.

## 13. Ma trận kiểm thử tối thiểu

| Contract | Kiểm chứng cần có | Dữ liệu |
|---|---|---|
| Preservation | Không global DB delete; không overwrite historical artifact; invalid input không gây side effect | Fake driver, tmp_path |
| Split | Disjoint/exhaustive, stable IDs/order invariance, coverage/OOV, requested empty split fail | KG fixtures + read-only feasibility report |
| RNG | Chạy evaluation không đổi training stream/weights; evaluation replay | Deterministic fixtures |
| Loss | Zero usable không là zero error; counts/denominators đúng; fixed-pair loss recompute | Dense/sparse small-vector fixtures |
| Ranking | Candidate/filter/tie/OOV đúng; per-seed rows và aggregate khớp independent reference | Exact small embeddings |
| Checkpoint | Sidecar và semantic/dimension checks; v1 compatibility; new-version design identity | Retained immutable fixture bytes |
| Lineage | Manifests schema + actual hashes + actual commit; corrupted receipt/input bị reject | File-backed fixtures |
| Temporal | No future evidence/mapping; clock axes; deterministic graph/support/exclusions | Temporal fixtures; production audit riêng |
| Measurement | Same settings/estimand; 6-pair entity median/LTO; invalid geometry unavailable; 3-seed temporal aggregation | Scientific fixtures + saved-artifact verifier |
| Population | Complete support, declared balanced panel, H2 universes/populations, no silent query dropping | M4 fixtures |
| Inference | Verified empirical pseudo; FE reference; WCB replay; degenerate inputs fail | Registered estimator fixtures |
| Stage control | Evaluation không gọi statistics; only correct prior-stage manifest/receipt được nhận | Orchestrator tests |

Các lệnh hiện có có thể dùng: `python -m pytest -q ... -p no:cacheprovider
--basetemp=<new-workspace-test-dir>`, `python -m ruff check .`,
`python scripts/verify_g1.py --ci --code-checks`, W1/W7 checks theo đúng scope.
CLI và filenames mới ở P1/P4 là thiết kế đề xuất; không trình bày như lệnh đã chạy.

## 14. Trình tự execution sau remediation — chỉ là runbook đề xuất

Mỗi dòng là một stage request riêng: inspect → plan → implement/test nếu cần →
execute → independent validate → Stage Report → **STOP**. Không có lệnh `run all`.

| Thứ tự | Stage | Điều kiện vào | Đầu ra để review trước bước kế |
|---|---|---|---|
| E0 | Chốt scope/design và input readiness | P0–P7 áp dụng đã TESTED, decisions đủ cho stage | Registered config, input/code hashes, split feasibility, exact allowed next stage |
| E1 | Quality-validation pilot | D02–D04 đủ; inputs as-of hợp lệ cho scope đã duyệt | 3-seed epoch curves, checkpoints/ranks, independent verifier, quality/coverage report |
| E2 | M1 remediation execution nếu full certified scope yêu cầu | Approved contract, immutable upstream evidence, stage prerequisites | New artifact-backed stage report và temporal/parity/handoff evidence; Stage 4.3 không chạy lại |
| E3 | Backbone training mới | Approved full training design, M1 prerequisites của scope đủ | 10×3 jobs nếu vẫn là registered population, checkpoint/log/manifests, independent verification |
| E4 | Alignment | New backbone verified; registered anchor plan/settings | New Q/means/spectrum/diagnostics + independent receipt |
| E5 | Empirical null | Alignment và sampling/bucket/LTO plan verified | Six-pair/entity reference artifacts + independent receipt |
| E6 | Longitudinal drift | Null verified, same settings/checkpoint lineage | delta_time, signed excess, SED+, availability/reasons + receipt |
| E7 | Empirical pseudo artifact stage nếu chưa có verified producer artifact | D07 và geometry/null prerequisites đủ | Empirical pseudo/hash/query exposure provenance + independent receipt |
| E8 | Evaluation Stage 8 | Registered panel/universes; backbone/drift/pseudo receipts đủ | Immutable per-seed ranks/RR, population flags, Query×Transition panel + receipt |
| E9 | Statistics Stage 9 | Evaluation verified, inference config đủ | H1/H2/pseudo results, WCB diagnostics, scope/limitations + Stage Report |

E2 là placeholder cho chuỗi **các stage M1 riêng biệt**, không là quyền chạy một
lệnh reprocess toàn corpus. Nếu E1 cũng yêu cầu certified data thì E2/prerequisite
M1 phải hoàn tất trước E1; chỉ diagnostic scope được phép ghi nhận ngoại lệ đúng
evidence đã duyệt. Việc chốt budget sau pilot phải theo D03 trước backbone, không
retune bằng E6–E9 outcomes. Independent test được thực hiện đúng D02/D03, không
tự mở W8 locked test trong E1.

Thay checkpoint backbone thì Q/null/drift/evaluation cũ không còn là downstream
artifacts của model mới. Giữ lại toàn bộ để audit nhưng không reuse qua phép đổi
path/hash giả. Nếu chỉ chạy diagnostic quality pilot mà không thay backbone, không
cần tự tính lại toàn bộ M2/M4.

## 15. Hồ sơ bàn giao và quản trị thay đổi

- Mỗi gói có modified-files list, regression tests/commands/results, diff reference,
  exact artifact scope và remaining blockers. Không đánh dấu RESOLVED chỉ từ patch.
- Nhánh implementation mới dùng `codex/` khi bắt đầu coding; không checkout/reset
  hoặc commit/push trong task lập kế hoạch này.
- Giữ source lock hiện hành sau AMEND-2026-001; không phục hồi blocker nguồn cũ.
  Không tự ghi decision log hoặc approved amendment từ một đề xuất trong kế hoạch.
- Không xóa/sửa historical raw, FactVersion, runs, source/config approval evidence.
  Supersession là record mới cross-reference finding/run/hash cũ và mới.
- Không acquisition mới/full-corpus reprocessing, hosted scientific decision-maker,
  QLoRA hoặc SUPPORT implementation được thêm vào critical path.
- Kế hoạch chỉ đạt **PREPARED**. Remediation IMPLEMENTED/TESTED và production
  EXECUTED/VERIFIED đều chưa được thực hiện trong lượt lập kế hoạch.

Ưu tiên bắt đầu coding: **P0 → P1 → P2 → P3 → P4**, rồi hoàn tất P5/P6/P7
trước khi xin chuyển sang stage execution cụ thể. Không cần đợi giải quyết mọi
scientific choice để viết reproducing tests và sửa các guards thuần engineering.
