# Kiểm tra codebase trước phiên chạy mới — 03/11/2026

**Kết luận: NOT READY cho một lần chạy lại toàn bộ có chứng nhận khoa học.**

Checkout được kiểm: `eadf22abc436dcbe2f12ae850ed9a5e4382dc714`; working tree
sạch lúc bắt đầu. Không sửa source/config, không train production, không chạy
acquisition, không truy cập `data/locked_test/`, không ghi Neo4j và không đổi
protocol/source lock/decision log. Chỉ thêm báo cáo và bằng chứng audit mới.

## Phạm vi và bằng chứng

- Inventory và AST syntax check: **192 Python files, 32.818 dòng** trong
  `src/`, `scripts/`, `tests/`. Đây không phải chứng nhận đúng từng dòng.
- Review thủ công đường CORE: temporal/contracts/gates, KGE training và checkpoint,
  alignment/null/drift v2 và runners, recurring QA, FE/WCB, manifests và CI.
- Đối chiếu protocol, module contracts, schema, amendment và decision log mới nhất.
- Full tests Python **3.11.9**: **652 passed, 10 skipped** sau khi đặt thư mục
  tạm trong workspace. Lượt đầu: 651 passed, 10 skipped, 1 failed do Windows
  từ chối atomic rename trong system temp; cùng source đạt khi đổi temp location.
- `ruff check . --no-cache`: PASS. G1 code checks: 4 passed, **không scientific G1**.
- `verify_w1.py --ci` và `verify_w7.py --ci`: scaffold scope do chưa có freeze
  tags; không dùng exit 0 để kết luận gates khoa học PASS.
- `verify_w7.py` strict: FAIL vì `TO_BE_FROZEN` trong `configs/kge.yaml`.
- Source-byte inspection: **3/3 khớp current lock** sau AMEND-2026-001. Không
  lặp lại blocker thiếu original đã được supersede bằng amendment hiện hành.
- Machine schema: 9/17 bảng thiếu/lệch fields; 17/17 chưa có physical declarations
  đầy đủ, nên overall BLOCKED. Không chứng nhận lại dữ liệu M1.

Bằng chứng: `outputs/pre_rerun_audit_20261103_v1/` gồm `pytest.log`,
`pytest_local_temp.log`, `ruff.log`, các gate logs, `schema_audit.json`,
`source_inventory.json`, `reproduction_results.json`, `experiment_manifest.json`.
Script tái hiện: `reproduce_findings.py` trong thư mục đó. Script chỉ tạo fixtures
trong output audit; thao tác DB được mock; không gọi production runners.

Tái hiện probes: `.venv-m1/Scripts/python.exe outputs/pre_rerun_audit_20261103_v1/reproduce_findings.py`.
Các regression tests đề xuất dưới đây **chưa được thêm vào suite** trong scope review.

## Danh sách findings

| ID | Severity | Vấn đề | Phạm vi ảnh hưởng |
|---|---|---|---|
| RERUN-01 | CRITICAL | Pseudo-drift là số ngẫu nhiên, vẫn được kết luận falsification PASS | M4 scientific inference |
| RERUN-02 | HIGH | Thiếu support bị biến thành drift 0 hoặc median của phần còn lại | M4 H1 population |
| RERUN-03 | HIGH | Panel chỉ có gold Seen-at-T1, không có population New/OOV | Diễn giải H2 |
| RERUN-04 | HIGH | Validation dùng chung RNG với training | KGE rerun với validation |
| RERUN-05 | HIGH | Split validation có thể bị tắt âm thầm | KGE validation validity |
| RERUN-06 | HIGH | Config hash không bao gồm thiết kế split | KGE experiment lineage |
| RERUN-07 | MEDIUM | Không có negative hợp lệ vẫn báo loss 0 | Training/evaluation diagnostics |
| RERUN-08 | HIGH | Loader nhận checkpoint thiếu sidecar và semantic hash sai | Artifact integrity |
| RERUN-09 | HIGH | Runners trỏ cố định run cũ; backbone cũ không còn load được inputs | Phiên chạy mới |
| RERUN-10 | HIGH | Manifests v2/M4 không đúng schema và ghi commit là HEAD | Analysis lineage |
| RERUN-11 | HIGH | Runner M4 tự chạy cả Stage 8 và Stage 9 | Stage discipline |
| RERUN-12 | HIGH | Schema M1 tiếp tục BLOCKED | Full-pipeline production readiness |
| RERUN-13 | GOVERNANCE | Registration/freeze còn thiếu và giá trị diagnostics chưa thống nhất | Scientific readiness |
| RERUN-14 | CRITICAL | Script import Neo4j bắt đầu bằng xóa toàn bộ graph | Database preservation |

### RERUN-01 — Pseudo-drift tổng hợp thay cho empirical retraining noise

- **Files:** `scripts/run_m4_evaluation_and_stats.py:145`, `:146`, `:255`;
  `configs/protocol_v1.yaml:83`, `configs/statistics.yaml`.
- **Expected:** falsification dùng same-snapshot pseudo-drift từ artifacts có
  provenance, theo thiết kế đã đăng ký; không tạo synthetic scientific regressor.
- **Actual:** `rng.normal(0, mad_val)` rồi positive-part/scale. Không dùng entity
  same-snapshot distances để tạo D_pseudo. Thiếu MAD còn fallback `0.05`.
  Summary ghi `falsification_passed=true` nếu p>0.05.
- **Evidence:** probe `m4_pseudo_drift_is_random`; saved stats 065503Z ghi p=0.438,
  run mới hơn 070316Z ghi p=0.381, cùng diễn giải PASS retraining-noise falsification.
- **Root cause:** confirmed synthetic draw trong production-facing runner;
  không phải giả thuyết về numerical noise. Chưa quy kết H1 coefficient do lỗi này.
- **Reproduction:** audit probe trích đúng aggregation statements bằng AST;
  đọc hai saved stats JSON, không chạy thống kê lại.
- **Minimal fix:** chặn scientific falsification khi thiếu registered empirical
  pseudo artifacts; thực hiện estimator đúng protocol trong task riêng. Giữ nguyên
  historical outputs và ghi supersession nếu chạy lại.
- **Regression:** yêu cầu artifact/hash pseudo; thiếu dữ liệu phải fail; seed RNG
  không được tự sinh replacement regressor. So sánh độc lập với raw distances.
- **Remaining blockers:** thiết kế empirical pseudo và inference config cần chốt;
  p>0.05 riêng lẻ cũng không chứng minh không tồn tại hiệu ứng giả.

### RERUN-02 — Complete-support population không được enforce

- **Files:** `scripts/run_m4_evaluation_and_stats.py:128`, `:135`, `:139`;
  `configs/protocol_v1.yaml:57`, `:60`.
- **Expected:** primary H1 chỉ complete-support, unavailable giữ lý do/coverage;
  không biến unavailable thành measured zero.
- **Actual:** bỏ các giá trị missing/non-finite rồi median; nếu hết thì trả `0.0`.
  `available` trong drift lookup không được dùng để enforce population.
- **Evidence:** probe một support SED+=0.8 và một missing vẫn trả 0.8;
  tất cả missing trả 0.0, record tiếp tục vào FE.
- **Root cause:** confirmed partial-list aggregation và numeric defaults.
- **Reproduction:** probe `m4_missing_support_fails_open` chạy đúng statements
  của runner với fixture support missing; không tính lại production panel.
- **Minimal fix:** validate toàn bộ unique supports trước aggregation; xuất
  eligibility/reason và enforce registered population; không tự thay denominator.
- **Regression:** partial/all missing, available=false, NaN và duplicate support.
- **Remaining blockers:** chốt cách báo cáo coverage/quarantine, giữ population rules.
  Current saved drift đầy đủ không chứng minh nhánh missing đã an toàn.

### RERUN-03 — H2 không có new/OOV gold population

- **Files:** `src/evaluation/qa_panel.py:18`, `:24`, `:38`;
  `scripts/run_m4_evaluation_and_stats.py:158`, `:264`;
  `configs/protocol_v1.yaml:66`–`:72`.
- **Expected:** các population Seen-at-T1 và full open-world/New-or-OOV được
  phân biệt; inference về OOV cần có evidence đúng population.
- **Actual:** queries dựng từ intersection triples của tất cả snapshots. Gold
  đều đã ở T01. Chỉ mở rộng candidates không tạo new/OOV gold queries. Runner
  gọi chênh lệch này `oov_bias_gap` và có thể diễn giải là gains do entity coverage.
- **Evidence:** saved panel 070316Z: 147 queries, 1.323 rows, **0 unseen-gold rows**.
- **Root cause:** confirmed một query population tái sử dụng cho hai universes.
  Không phủ nhận giá trị mô tả candidate-expansion trên old-query panel.
- **Reproduction:** probe `m4_no_new_or_oov_gold_population`; đọc flag và code builder.
- **Minimal fix:** ghi đúng giới hạn của old-query contrast; thiết kế secondary
  population theo protocol, chốt trước lần chạy mới; không chọn queries theo điểm.
- **Regression:** fixtures có new gold và OOV; phân biệt query population/candidates;
  kiểm đủ population và RR=0 cho frozen gold không có embedding.
- **Remaining blockers:** registration query panel/candidate universes chưa freeze.

### RERUN-04 — Validation thay đổi trajectory huấn luyện

- **Files:** `src/kge/trainer.py:54`, `:60`, `:63`;
  `src/kge/model.py:214`.
- **Expected:** theo dõi validation không làm thay đổi training sampling; các epoch
  validation so sánh trên evaluation design có thể tái lập.
- **Actual:** `train_epoch` và `evaluate_loss` dùng cùng `rng`; validation tiêu thụ
  RNG nên epoch train sau có shuffle/negatives khác. Mẫu âm validation cũng đổi mỗi epoch.
- **Evidence:** cùng fixture, seed, split, config; chỉ restore RNG sau evaluate
  đã làm final entity coordinate khác tối đa **0.0305511581** sau 4 epochs.
- **Root cause:** confirmed RNG coupling; không phải thay đổi optimizer/hyperparameter.
- **Reproduction:** probe `validation_rng_changes_training`.
- **Minimal fix:** tách training/evaluation RNG; lưu/định danh validation negatives
  hoặc evaluation stream độc lập theo thiết kế được chốt. Không sửa old runs.
- **Regression:** bật/tắt evaluation callback với cùng train data không đổi weights;
  evaluation không mutate embeddings hoặc training RNG.
- **Remaining blockers:** cần chốt validation design; không dùng kết quả downstream để tuning.

### RERUN-05 — Validation rỗng bị chuyển về full training

- **Files:** `src/kge/trainer.py:40`–`:51`, `:207`–`:208`.
- **Expected:** khi yêu cầu validation nhưng split không khả thi phải fail rõ;
  không dùng training loss thay cho validation quality mà không báo.
- **Actual:** nếu một partition rỗng thì train toàn dataset, `dev_triples=[]`.
  Dimension helper tiếp tục fallback từ final_dev_loss sang final_loss.
- **Evidence:** fixture 2 triples, requested ratio 1e-12: train trả checkpoint
  bình thường, 4 training losses, **0 validation losses**. Đây là boundary probe,
  không khẳng định approved T01 pilot bị rỗng.
- **Root cause:** confirmed fallback. Ratio không có range guard và không kiểm
  train entity/relation coverage cho held-out trong generic helper.
- **Reproduction:** probe `empty_requested_validation_silently_disabled`.
- **Minimal fix:** validate ratio/partitions/coverage và fail với lý do khi
  validation được yêu cầu; selection không nhận train-loss substitute.
- **Regression:** empty split, ratio ngoài miền, validation-only entity/relation,
  và yêu cầu validation nhưng không có metrics.
- **Remaining blockers:** split algorithm và coverage policy phải chốt trước train.

### RERUN-06 — Split không có trong config identity

- **Files:** `src/kge/trainer.py:23`, `:38`–`:48`, `:67`–`:68`;
  `src/kge/checkpoint.py:21`.
- **Expected:** semantics-affecting split phải có resolved identity/hash và
  frozen membership để phân biệt thí nghiệm.
- **Actual:** config hash chỉ `asdict(TransEConfig)`; `dev_split_ratio` là tham số
  ngoài config. Full snapshot và 20% dev có cùng config hash. Membership dựa
  integer mapping indices, chưa lưu explicit split/hash trong provenance.
- **Evidence:** probe `split_omitted_from_config_hash`: cùng hash
  `30750031fa5bdcaf5f3cb20b4df697d99f46c9037623509ed34fa29ea26686ee`,
  nhưng dev histories dài 0 và 4. Training metrics có ratio nên không mất toàn bộ
  thông tin; lỗi là config/split identity không đủ.
- **Root cause:** confirmed omitted argument và absent explicit split artifact.
- **Reproduction:** train fixture cùng cfg với ratio 0 và 0.2, so config hashes.
- **Minimal fix:** versioned resolved training design chứa split/membership/hash,
  sampling/evaluation version; verify downstream đúng training population.
- **Regression:** đổi membership/ratio phải đổi design identity; same split rebuild
  deterministic; integer-index changes không âm thầm đổi registered membership.
- **Remaining blockers:** cần phân biệt evaluation-trained model và full-snapshot
  backbone theo protocol, không tự thay population scientific backbone.

### RERUN-07 — Loss 0 khi không có sample được đánh giá

- **Files:** `src/kge/model.py:158`, `:212`, `:253`, `:271`.
- **Expected:** diagnostics phân biệt zero violation và zero usable examples.
- **Actual:** không tìm được negative thì skip; train chia cho toàn bộ positives;
  evaluation count=0 chia `max(1, eval_count)`, trả 0.
- **Evidence:** dense fixture 2 entities × 1 relation có đủ 4 positives: zero
  valid negatives, train reports **0.0** dù không có learning update.
- **Root cause:** confirmed skipped samples được biểu diễn như zero loss.
- **Reproduction:** probe `no_valid_negative_reports_zero_loss`.
- **Minimal fix:** lưu usable/skipped/active-margin counts và numerator/denominator;
  fail hoặc unavailable nếu zero usable. Không đổi metric âm thầm cho old runs.
- **Regression:** dense graph, empty input, sampling exhaustion và all-margin-satisfied.
- **Remaining blockers:** hiện chưa chứng minh lỗi này xảy ra trong 30 production
  checkpoints; old logs không lưu skip counts để xác nhận retrospective.

### RERUN-08 — Checkpoint loader fail-open khi thiếu sidecar

- **Files:** `src/kge/checkpoint.py:122`–`:150`.
- **Expected:** chế độ verify từ chối thiếu/mismatch physical hash và semantic
  hash; downstream không tin checkpoint bị sửa.
- **Actual:** sidecar chỉ được check nếu file tồn tại; không đối chiếu stored
  `artifact_hash` với recomputed semantic hash. `verify_finite()` không thay thế
  integrity check.
- **Evidence:** thêm +10 vào entity coordinate của fixture, giữ old artifact_hash,
  lưu sang file mới không sidecar; `load(..., verify_sidecar=True)` vẫn chấp nhận.
- **Root cause:** confirmed optional sidecar condition và omitted semantic check.
- **Reproduction:** probe `checkpoint_loader_accepts_unverified_changed_file`.
- **Minimal fix:** strict loader bắt buộc sidecar, verify semantic hash/dimensions;
  nếu cần legacy opt-out phải explicit và không dùng scientific path.
- **Regression:** missing/empty sidecar, finite tamper, wrong vector width,
  semantic hash mismatch. Strong outer runner guards hiện có phải được giữ.
- **Remaining blockers:** direct M4 loader phụ thuộc loader này; không khẳng định
  checkpoints thật đã bị tamper (lượt review loss trước đã rehash đúng).

### RERUN-09 — Chạy phiên mới vẫn đọc run cũ hoặc thiếu inputs

- **Files:** `scripts/run_m2_backbone.py:29`, `:69`, `:156`;
  `scripts/run_m2_null_v2_all_transitions.py:28`,
  `scripts/run_m2_drift_v2_all_transitions.py:28`,
  `scripts/run_m4_evaluation_and_stats.py:39`–`:40`;
  `configs/m2_external_dev_v1.yaml`.
- **Expected:** mỗi stage nhận explicit new-run inputs và bind hashes; training
  với validation cần design mới, không giả định runner cũ đã hỗ trợ.
- **Actual:** v2/M4 constants trỏ checkpoint/alignment/null/drift từ tháng 10.
  Backbone runner vẫn bind approved full-snapshot proposal và không có validation
  CLI. Preflight cũ tham chiếu package `data/KG_lan2/...` hiện thiếu file.
- **Evidence:** gọi read-only `load_registered_inputs` thất bại vì
  `data/KG_lan2/evolving_kg_downstream_v3/config/downstream_transe_config.yaml`.
- **Root cause:** confirmed historical hard-coded bindings; không phải lỗi Parquet mới.
- **Reproduction:** probe `backbone_registered_inputs`; đọc constants runners.
- **Minimal fix:** thiết kế config/run mới, explicit input manifest descriptors;
  bind canonical package hiện hành qua verified preflight mới trong stage riêng.
  Không redirect alias run cũ hoặc sửa historical manifests.
- **Regression:** chỉ định two run fixtures phải load đúng run; stale hash/mixed
  backbone-alignment phải fail; no implicit latest-run choice.
- **Remaining blockers:** scientific training/validation design và upstream readiness.

### RERUN-10 — Manifests gần đây vi phạm lineage contract

- **Files:** `scripts/run_m2_null_v2_all_transitions.py` manifest block;
  `scripts/run_m2_drift_v2_all_transitions.py` manifest block;
  `scripts/run_m4_evaluation_and_stats.py:273`–`:301`;
  `configs/schemas/experiment_manifest.schema.yaml`.
- **Expected:** actual git commit, `dirty_state`, resolved config/input/mapping
  hashes, `artifacts.hashes`, access/environment/hardware fields đúng schema.
- **Actual:** commit literal `HEAD`, key `dirty`; inputs chủ yếu paths;
  artifacts là flat map; required fields bị thiếu. M4 không có environment/access.
- **Evidence:** probe kiểm 4 saved manifests null v2, drift v2, M4 eval/stats
  070316Z; danh sách missing fields đầy đủ trong `reproduction_results.json`.
- **Root cause:** confirmed ad-hoc manifest writers bỏ shared validator.
- **Reproduction:** probe `new_runner_manifests_violate_schema`.
- **Minimal fix:** dùng canonical manifest builder/validator, hash inputs trước
  metrics, lưu exact executed code/config và verify sau stage; version new outputs.
- **Regression:** actual writer outputs phải validate; changed input hash và
  `git.commit='HEAD'` phải bị reject trong scientific mode.
- **Remaining blockers:** không thể sửa old provenance bằng cách đoán commit;
  cần retained code/evidence hoặc new versioned run.

### RERUN-11 — Evaluation tự chạy tiếp statistics

- **Files:** `scripts/run_m4_evaluation_and_stats.py:44`, `:198`–`:223`, `:307`.
- **Expected:** AGENTS §8.2: một stage, validate/report/STOP; Stage N+1 cần yêu cầu.
- **Actual:** một `run_m4_pipeline()` vừa tạo Stage 8 panel vừa chạy Stage 9
  FE/WCB, trước khi có independent stage report và next-stage authorization.
- **Evidence:** direct call sequence trong function và entrypoint cuối file.
- **Root cause:** confirmed combined runner; không suy đoán từ tên script.
- **Reproduction:** static call-path review, không execute runner.
- **Minimal fix:** tách entrypoints/config stage; statistics chỉ nhận immutable,
  verified evaluation manifest. Preflight stage phải xong trước allocation outputs.
- **Regression:** evaluation-only không gọi fit/bootstrap; stats không chạy khi
  thiếu evaluation verification receipt.
- **Remaining blockers:** RERUN-01/02/03/10 và frozen inference choices.

### RERUN-12 — M1 machine contract chưa đủ cho full rerun

- **Files:** `config/schema.yaml`, `src/kg_pipeline/contracts.py`,
  `src/temporal/schema.py`, `src/kg_pipeline/contract_authority.py`.
- **Expected:** runtime fields/types/nullability/keys khớp authoritative schema;
  temporal evidence và handoff được verified độc lập trên artifacts.
- **Actual:** fresh audit vẫn 9/17 field-table mismatches; 17/17 physical declarations
  UNDECLARED. Guard block đúng; chưa có căn cứ để gỡ blocker.
- **Evidence:** `schema_audit.json`, schema version 1.0.0 và hash
  `48ad42f86088ae0e9ca8b8cbb158017bf8ec14e0d450fdeff523bf59e6902840`.
- **Root cause:** confirmed machine/runtime divergence được biết từ C3; không
  suy luận mọi artifact data3.1 bị sai chỉ từ schema audit.
- **Reproduction:** gọi `audit_machine_contract(Path.cwd())`.
- **Minimal fix:** approved contract migration hoặc runtime remediation trong
  scope riêng; verify producer/consumer + temporal/parity evidence sau đó.
- **Regression:** existing contract tests tiếp tục bảo vệ fail-closed; thêm exact
  schema tests sau khi có approved definitions, không đổi tests để che drift.
- **Remaining blockers:** approved schema và real upstream certification. Nếu chỉ
  chạy M2 Dev trên data3.1 thì cần scope đó explicit; không gọi là full pipeline PASS.

### RERUN-13 — Registration và freeze chưa sẵn sàng

- **Files:** `configs/protocol_v1.yaml`, `configs/kge.yaml`,
  `configs/statistics.yaml`, `configs/m2_data_3_1_candidate_v2.yaml`,
  `configs/m2_measurement_v2_candidate.yaml`, `decisions/decision_log.jsonl`,
  `scripts/run_m2_null_v2_all_transitions.py`, `scripts/run_m2_drift_v2_all_transitions.py`.
- **Expected:** approved scientific settings được biểu diễn thống nhất, explicit
  stage plan và frozen inputs; code-check PASS không cấp scientific approval.
- **Actual:** guarded registration trả **BLOCKED với 12 reasons** (source readiness
  đã true); candidate inactive/input plan null, protocol còn placeholders.
  Decision D-DIAG ghi orthogonality max `1e-5`, configs/runners/PROGRESS ghi `1e-6`;
  chưa tự chọn một giá trị. WCB seed/draws chưa freeze nhưng runner hard-code 101/999.
- **Evidence:** `measurement_registration` trong probe results; `w7_strict.log`;
  decision text và runner settings. W1/W7 CI chỉ scaffold scope.
- **Root cause:** confirmed registration chưa tích hợp; không khẳng định không có
  user approval trong quá khứ, cũng không xem comment 'locked' là machine approval.
- **Reproduction:** read-only `inspect_registration` và strict W7 verifier.
- **Minimal fix:** hòa giải design/thresholds theo source hierarchy với quyết định
  thật; version config/plan và verifier cùng nhau. Không tự sửa protocol/ledger.
- **Regression:** registered settings phải khớp mọi producer/consumer; inactive/null
  plan, missing approval và settings conflict phải fail trước computation.
- **Remaining blockers:** cần quyết định scientific semantics; audit này dừng ở
  báo cáo, không tự resolve authority conflict hoặc bắt đầu production.

### RERUN-14 — Legacy Neo4j importer xóa graph trước kiểm tra inputs

- **Files:** `scripts/import_to_neo4j.py:10`–`:14`.
- **Expected:** giữ immutable states, explicit scoped target, validate canonical
  inputs/parity trước materialization; không xóa toàn bộ DB khi rerun.
- **Actual:** first database action là `MATCH (n) DETACH DELETE n`, trước đọc CSV,
  không có input/run binding hoặc explicit deletion approval guard.
- **Evidence:** mocked driver ghi đúng query đầu này; exception dừng trước mọi
  file read tiếp theo. **Không có kết nối hoặc ghi database thật.**
- **Root cause:** confirmed destructive legacy entrypoint, không phải official
  append-only `src/kg_pipeline/neo4j_materializer.py`.
- **Reproduction:** probe `legacy_import_first_database_action_is_delete_all`.
- **Minimal fix:** loại khỏi rerun entrypoints; dùng official verified materializer.
  Nếu cần reset DB riêng, thiết kế thao tác tách biệt có explicit scope/approval.
- **Regression:** approved rerun không phát sinh global delete; validate inputs
  trước DB actions; fake driver kiểm preservation của các run khác.
- **Remaining blockers:** real DB parity chưa được kiểm lại trong audit này.

## Những việc cần hoàn tất trước phiên mới

1. Sửa các lỗi engineering ở validation/RNG/split identity/loss diagnostics,
   checkpoint integrity, explicit run inputs và manifest contracts; thêm regression
   tests trước khi sửa. Giữ nguyên historical runs.
2. Chốt thiết kế evaluation trước training: split theo canonical triple IDs,
   coverage, validation sampling, lịch MRR/Hits và checkpoint, số epoch/selection
   rule, independent final test. Không truy cập locked-test để thiết kế split.
3. Phân biệt pilot đánh giá chất lượng với full-snapshot scientific backbone.
   Việc thêm held-out làm thay đổi training population; không tự áp dụng cho M2
   drift backbone mà chưa có approved design. Batch_size hiện là metadata,
   trainer vẫn per-triple SGD; không tự đổi optimizer/batching.
4. Sửa M4 pseudo/support/population và tách Stage 8/9. Không dùng output H1,
   SED+ hoặc QA để lựa chọn upstream rules/hyperparameters.
5. Resolve schema/readiness/registration theo scope thực tế. Source lock hiện khớp;
   giữ amendment trail. Không tự gỡ các gate hoặc dùng skipped scaffolds làm PASS.
6. SUPPORT: `src/paths/` và `src/auditor/` hiện chỉ có module docstrings. Chưa có
   Arm C/exact-B fallback implementation ở đó. Không chặn CORE vì optional support;
   nếu đăng ký Arm C thì phải có implementation + contract tests trước execution.

## Verification tiers và giới hạn

- **IMPLEMENTED (remediation): NO.** Chỉ tạo audit/report/probes, không patch production.
- **TESTED:** 652 existing tests PASS, 10 skipped; Ruff PASS; isolated defect probes
  reproduce các nhánh ghi trong report. Python 3.10 chưa chạy local.
- **EXECUTED (new production run): NO.** Chỉ chạy test/inspection, không pipeline stage.
- **VERIFIED:** inventory/hashes theo audit manifest, fresh schema/source-byte checks,
  và các reproductions cụ thể. Không certify toàn bộ data population, temporal
  validity, Neo4j parity, G3/G4/W7, H1/H2 hoặc hiệu quả embedding.

Full tests hiện không trực tiếp kiểm orchestrators v2/M4 theo scientific
registration/provenance contract; tests unit M4 hiện có không thay thế các probes
trong report này. Cả codebase xanh không có nghĩa scientific readiness.

**Không finding nào được đánh dấu RESOLVED.** Không commit/push hoặc rerun pipeline.
Stage tiếp theo là remediation và chốt thiết kế trong phạm vi được yêu cầu riêng.
