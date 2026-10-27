# Review các nhánh M1 sau đồng bộ remote — 14/10/2026

## 1. Kết luận

Tiếp tục engineering trên `codex/m1-acceptance-rebuild` tại `2860235`.
Không có nhánh nào trong phạm vi review được chứng minh đủ điều kiện nghiệm thu
M1 hoặc bàn giao production cho M2. Không merge toàn bộ các nhánh pipeline cũ
vào nhánh acceptance: chúng có các đường xử lý thiếu evidence/identity/gates.

Phát hiện mới trên nhánh acceptance: quality component chưa đối chiếu nội dung
gold cuối với nội dung adjudication. Fixture có hai annotations và adjudication
đều không chứa fact, nhưng gold được chấm chứa một fact, vẫn nhận component PASS.
Final G1/G2 vẫn BLOCKED; fixture này không mở scientific gate.

## 2. Đồng bộ và phạm vi

- `git fetch origin --prune` thành công; `git ls-remote --heads origin` xác minh
  đầy đủ 9 remote branches. Không có remote tip mới so với trước fetch.
- Nhánh hiện tại chưa có upstream cùng tên. `git pull --ff-only origin
  codex/transe-legacy-exploration` trả `Already up to date`; giữ nguyên ba commit
  local `92a3ecb`, `a715a21`, `2860235`. Không đổi HEAD, reset, merge hoặc push.
- Working tree trước review: chỉ proposal PDF untracked. Giữ nguyên file này.
- Rà 8 nhánh remote có M1 và nhánh acceptance local: source, config/authority,
  temporal/evidence/identity, quality/gates, parity, và M1→M2 loader.
- Đối chiếu thêm `origin/main`/`Duc-AnhTp/dottyback` tại `9544e41`, local `main`/
  `feature/kge-drift-core` tại `d69bb8a`; đây là baseline/scaffold hoặc M2,
  không phải một bản M1 acceptance khác.
- Local `m1-acceptance-rebuild` tại `684dc6b` là alias của legacy, khác nhánh
  `codex/m1-acceptance-rebuild` tại `2860235`. Không tự cập nhật checkout của
  chat/worktree khác.

Inventory đủ SHA và ancestry: `outputs/m1_branch_review_20261014/branch_inventory.json`.
Các tests dùng bản sao code đúng Git bytes dưới `outputs/.../snapshots/<sha>/`;
không checkout các nhánh khác, không copy research data vào bản sao.

## 3. Ma trận các nhánh

Tests dưới đây là tập M1/temporal/adapter có sẵn ở mỗi nhánh, không cùng số lượng
hay cùng coverage. Không so chất lượng scientific bằng số tests PASS.
Ruff ở bảng chỉ kiểm `src/kg_pipeline` và `src/temporal`.

| Nhánh | Tip | Tests được chạy lại | Ruff | Đánh giá tích hợp |
|---|---|---|---|---|
| `feature/data_try` | `4c24da2` | 7 passed | 1 error | Inventory-only; temporal snapshot còn NotImplementedError; đã nằm trong ancestry hiện tại |
| `fix/data-pipeline-compliance` | `05d0eb5` | 58 passed, 1 failed | 2 errors | Legacy clocks/evidence/revision/empty-quality còn lỗi; đã nằm trong ancestry |
| `feature/integrated-kge-drift` | `286368e` | 60 passed | 5 errors | M2 loader đọc Parquet không chứng nhận; temporal fallbacks; không merge wholesale |
| `reconcile/pipeline-drift-compliance` | `6000f38` | 192 passed, 1 failed | PASS | Có guards, nhưng FactVersion helper còn lỗi revision và public single-file loader còn bypass; đã được nhánh mới kế thừa/sửa một phần |
| `fix/data-pipeline-compliance-cont` | `e19fe25` | 69 passed, 1 failed | 7 errors | Quality không gold vẫn PASS, parity chỉ CSV, revision lỗi; không merge wholesale |
| `feature/remediation-and-parity` | `74a1f14` | 79 passed | 7 errors | Sửa future-effective filtering nhưng competing revisions, clock/mapping/evidence, quality và parity còn lỗi; không merge wholesale |
| `codex/m1-thu-huong-remediation` | `6ef3ff5` | 263 passed | PASS | Nền guards tốt hơn; schema/authority/production vẫn BLOCKED; đã nằm trong ancestry |
| `codex/transe-legacy-exploration` | `684dc6b` | 266 passed | PASS | Giữ làm legacy/audit T01; không phải certified dataset; là base của acceptance |
| `codex/m1-acceptance-rebuild` | `2860235` | 329 passed; full regression 408 passed, 10 skipped | PASS | Nền engineering nên tiếp tục; BR-M1-001 và prerequisites/backend/certification chưa hoàn tất |

Ancestry chính:

```text
feature/data_try → fix/data-pipeline-compliance
  → reconcile/pipeline-drift-compliance
  → codex/m1-thu-huong-remediation
  → codex/transe-legacy-exploration
  → codex/m1-acceptance-rebuild
```

Các nhánh `fix/data-pipeline-compliance-cont`/`feature/remediation-and-parity`
phân nhánh riêng từ compliance. Một file không tồn tại ở nhánh cũ không được
gọi là bị xóa bởi nhánh đó; diff trực tiếp giữa các nhánh chỉ cho thấy thiếu
hardening so với nhánh remediation hiện hành.

## 4. Findings

### BR-M1-001 — HIGH — Gold chấm điểm chưa bind nội dung adjudication

- **Affected:** `src/kg_pipeline/acceptance_gates.py:38–57`,
  `src/kg_pipeline/acceptance_quality.py`; chỉ có ở acceptance mới.
- **Expected:** gold cuối phải xuất phát từ hai annotations và kết quả phân xử;
  artifact hashes/identity đúng không thay thế kiểm nội dung.
- **Actual/evidence:** `gold_binding_result.json`: annotations fact count 0,
  adjudication fact count 0, scored gold fact count 1, component status PASS.
- **Confirmed root cause:** caller kiểm article/reviewer IDs và annotation hashes,
  nhưng không đối chiếu các facts/entities/decisions/source groups được chấm với
  kết quả phân xử; pure evaluator tin dữ liệu gold riêng.
- **Reproduction:** chạy `probe_gold_binding.py` trong output review với fixture
  directory mới; không cần API, production run hoặc Neo4j.
- **Minimal fix:** khai báo contract cho adjudicated gold và sinh/kiểm các rows
  cuối từ artifact phân xử đã bind; mismatch hoặc thiếu final rows phải BLOCKED.
- **Regression cần thêm:** đổi gold fact/entity/temporal/span/decision/source
  group trong khi annotations/adjudication giữ nguyên; evaluator phải từ chối.
- **Status/blockers:** chưa sửa code; fixture reproduction VERIFIED trong phạm
  vi component. Final scientific gate vẫn chặn `FINAL_CERTIFICATION_INCOMPLETE`.

### BR-M1-002 — CRITICAL — Pilot quality PASS không cần gold

- **Affected:** `src/kg_pipeline/quality.py:66–146` trên `e19fe25`, `74a1f14`;
  empty `evaluate_quality` trên `05d0eb5`, `e19fe25`.
- **Expected:** thiếu independent gold/coverage/thresholds phải BLOCKED.
- **Actual/evidence:** fixture chỉ có ba Parquet bảng tối thiểu, không có run
  manifest/gold/certificates; `run_quality_gate` vẫn trả PASS trên hai nhánh.
  `evaluate_quality([], [])` cũng PASS ở `05d0eb5`, `e19fe25`.
- **Confirmed root cause:** stage chỉ kiểm offsets tăng, prefix source_id và
  tên mock. Gold được đọc nhưng không dùng. Không đo precision/recall.
- **Reproduction:** probe `quality_without_gold_or_manifests` và `empty_quality`
  trong `<sha>_probes_verified.json`.
- **Minimal fix/regression:** dùng quality evaluator độc lập; test empty/missing
  gold, unmatched FP/FN và incomplete annotation/threshold coverage. Không tái
  dùng các báo cáo PASS này làm pilot/final certification.
- **Status/blockers:** lỗi fixture-confirmed ở nhánh cũ; nhánh Codex giữ empty
  quality BLOCKED nhưng final pipeline quality vẫn cần hoàn thiện BR-M1-001.

### BR-M1-003 — CRITICAL — Thay thế scientific clocks bằng metadata

- **Affected:** `src/kg_pipeline/adjudicate.py` trên `286368e:137–154`,
  `74a1f14:45–90` và họ compliance/cont tương ứng.
- **Expected:** observation proof bind đúng content version; world validity,
  acquisition, ingestion và observation tách biệt.
- **Actual/evidence:** integrated dùng extracted validity hoặc default manifest
  time làm observation và ingestion. Remediation dùng crawl time, thiếu thì
  `now_utc`; không kiểm proof historical content tương ứng.
- **Confirmed root cause:** fallback chains tạo temporal eligibility dù basis
  chưa đủ. Đây là code-path finding, chưa đo số facts production bị ảnh hưởng.
- **Reproduction:** đọc adjudication source ở fixed SHA; đưa claim thiếu observation
  proof vào runner của nhánh cũ trong fixture sẽ đi vào fallback được chỉ rõ.
- **Minimal fix/regression:** quarantine thiếu basis, bind proof/body version;
  test không được thay observation bằng validity/publication/crawl/mtime/now.
- **Status/blockers:** code confirmed, production impact chưa VERIFIED. Nhánh
  mới có guards/components nhưng historical temporal evidence vẫn thiếu.

### BR-M1-004 — CRITICAL — Identity được tạo từ tên, không có as-of decisions

- **Affected:** `src/kg_pipeline/adjudicate.py:93–110` tại `74a1f14`.
- **Expected:** occurrence MentionID và canonical mapping có basis, availability,
  reviewer, version và lịch sử; unresolved phải pending.
- **Actual/evidence:** tạo `ent_<sha256(lowercase name)[:8]>` cho tên chưa có trong
  catalog, công bố `entity_map_version="v1_mock"`; không có mapping-time proof.
- **Confirmed root cause:** synthetic name-based identity nằm trong producer,
  không chỉ test fixture. Chưa chứng minh hash collision trong corpus thật.
- **Reproduction:** đọc lines 95–100; tên mới thiếu mapping vẫn được thêm catalog.
- **Minimal fix/regression:** bỏ đường auto-resolution khỏi production; test
  namesakes, late aliases, competing decisions, collision và missing basis.
- **Status/blockers:** code confirmed; không certify các IDs v3 bằng sidecar mới.
  Current identity implementation vẫn cần approved policy và producer migration.

### BR-M1-005 — HIGH — Evidence hash bind whole body

- **Affected:** `src/kg_pipeline/claims.py`, đặc biệt `74a1f14:41,69–80`, trên
  `05d0eb5`, `286368e`, `e19fe25`, `74a1f14`.
- **Expected:** hash exact evidence slice `[start,end)`, body hash riêng; cả hai
  role mentions phải grounded; co-occurrence không đủ chứng minh relation.
- **Actual/evidence:** fixture có body dài hơn evidence; cả bốn nhánh xuất một
  claim với hash khớp whole body và không khớp span. Older check dùng AND, chỉ
  cần một mention xuất hiện là qua bước grounding.
- **Confirmed root cause:** `evidence_text_hash=text_hash` tính trước vòng claim.
- **Reproduction:** probe `whole_body_evidence_hash`, adapter OfflineMock chỉ fixture.
- **Minimal fix/regression:** kế thừa exact-span/normalization guards ở nhánh mới;
  Unicode/CRLF, one-role-missing và body-versus-span tests; reprocess vào run mới.
- **Status/blockers:** exact-span fixture PASS trên `6000f38` và ba nhánh Codex;
  không sửa historical v3 hoặc tuyên bố các evidence cũ đã đúng.

### BR-M1-006 — HIGH — Revision selection sai hoặc tự chọn sibling

- **Affected:** `src/temporal/snapshot.py` ở compliance, integrated, reconcile,
  cont và remediation; phân biệt đúng fixed SHA.
- **Expected:** validity trước revision; competing effective revisions phải chờ
  adjudication; không chọn bằng timestamp/ID.
- **Actual/evidence:** parent đang valid, child đã biết nhưng effective tháng 7,
  cutoff tháng 6: `05d0eb5`, `286368e`, `6000f38`, `e19fe25` trả empty snapshot.
  `74a1f14` đã sửa trường hợp này. Cả năm vẫn chọn `child2` khi có hai siblings.
- **Confirmed root cause:** older helper resolve supersession trước validity;
  sibling tie-break dùng evidence time và ID.
- **Reproduction:** probes `future_effective_child`, `competing_revisions`.
- **Minimal fix/regression:** dùng validity-first + graph validation từ nhánh
  Codex; missing parent/cycle/sibling/future-effective/retraction fixtures.
- **Status/blockers:** ba nhánh Codex giữ parent và reject siblings trong fixtures.
  Helper FactVersion-only không phải canonical production certification.

### BR-M1-007 — CRITICAL — CSV equality được ghi Stage 4.18 PASS

- **Affected:** `src/08_run_canonical_neo4j_parity.py:98–180` ở `74a1f14`
  và họ continuation.
- **Expected:** materialize database thật, transaction read-back riêng và đối
  chiếu exact nodes/edges/supports với canonical Parquet.
- **Actual/evidence:** tạo `neo4j_edges` cùng lúc viết CSV, so lại với đầu vào,
  ghi overall PASS; report tự nêu `no database read-back`.
- **Confirmed root cause:** parity chỉ là export consistency; không có query
  database để phát hiện missing/extra/duplicate records hoặc import thất bại.
- **Reproduction:** đọc fixed source lines 129–180; không chạy production script.
- **Minimal fix/regression:** real materializer/read-back; tests DB unavailable
  BLOCKED, write succeeds/read fails, missing/extra nodes/edges/support metadata.
- **Status/blockers:** nhánh Codex có driver-double tests; lượt review này không
  chạy Neo4j thật và không cấp Stage 4.18 PASS.

### BR-M1-008 — HIGH — Public M2 single-file loader thiếu certification

- **Affected:** `src/kge/adapter.py` tại `286368e` và `6000f38`.
- **Expected:** public loader bắt buộc run context, producers, mapping/boundary
  lineage và artifact-backed G1/G2.
- **Actual/evidence:** integrated nhận fixture Parquet một triple không manifest
  hay gate. Reconcile single-file API có `verify_manifest=False` và không gọi
  scientific gates; guarded multi-file API không bảo vệ mọi public entrypoint.
- **Confirmed root cause:** standalone path cho phép dùng data ngoài handoff.
- **Reproduction:** probe `standalone_m2` chứng minh integrated bypass; đối chiếu
  reconcile `adapter.py:20–36,156–168` cho flag/path khác nhau.
- **Minimal fix/regression:** giữ public loader hiện hành ở Codex; test standalone,
  false verification flag, fabricated PASS, mismatched run và stale hashes.
- **Status/blockers:** ba nhánh Codex reject standalone fixture. Legacy T01 loader
  vẫn chỉ dùng trong phạm vi LEGACY_ONLY, không đổi thành official handoff.

### BR-M1-009 — GOVERNANCE — Source/window baseline khác giữa hai họ nhánh

- **Affected:** `configs/protocol_v1.yaml`, `data/manifests/sources.lock.json`,
  `decisions/decision_log.jsonl`, `config/snapshot_cutoffs.yaml` ở `74a1f14`
  so với baseline hiện hành.
- **Expected:** exact originals hoặc approved replacement amendment; window theo
  lựa chọn hiện hành 01/03/2025–31/08/2026, extension có quyết định riêng.
- **Actual/evidence:** old branch đổi hai source hashes thành `667aa460...` và
  `50904646...`, có log nhận approval và September extension. Current branch giữ
  `c61d08fc...`/`3f1bc9fd...`; readiness thực tế báo hai originals MISSING, PDF MATCH.
- **Root cause vs hypothesis:** divergence/hashes xác minh được bằng Git diff.
  Review không xác minh được human authorization/replacement evidence cho các
  decisions cũ; không kết luận approval giả, cũng không tự công nhận chúng.
- **Reproduction:** diff `origin/codex/m1-thu-huong-remediation` với
  `origin/feature/remediation-and-parity` trên các paths trên.
- **Minimal fix/regression:** phục hồi exact originals hoặc review amendment với
  bytes/hash/diff/precedence/reprocess; test lock/protocol/approval mismatch.
- **Status/blockers:** production BLOCKED; không thay locked protocol/source lock
  hoặc quyết định semantics trong lượt review.

### BR-M1-010 — HIGH — Runtime contract chưa phù hợp public schema

- **Affected:** `config/schema.yaml`, `src/kg_pipeline/contracts.py`,
  `src/temporal/schema.py`, `src/kg_pipeline/contract_authority.py`.
- **Expected:** names/types/nullability/serializer/PK/FK được khai báo và thống nhất.
- **Actual/evidence:** `current_readiness.json`: 9/17 name mismatches;
  17/17 physical declarations UNDECLARED. Candidate 25 tables là review package,
  không thay runtime schema 1.0.0 hoặc cấp production PASS.
- **Confirmed root cause:** public schema mới chỉ lists fields; producer schemas
  và dataclass/serializers chưa được migrate dưới approved matrix.
- **Reproduction:** `audit_machine_contract`/`readiness` trên current workspace.
- **Minimal fix/regression:** approve exact full matrix, migrate từng producer/
  consumer; Arrow type/nullability/round-trip/extra-column/PKFK tests.
- **Status/blockers:** engine IMPLEMENTED/TESTED; migration chưa EXECUTED/VERIFIED.

### BR-M1-011 — HIGH — Acceptance end-to-end còn chưa triển khai xong

- **Affected:** `src/kg_pipeline/acceptance_runner.py:115–130`,
  `src/kg_pipeline/gates.py:653`, `src/kge/adapter.py:104–134`, runbook.
- **Expected:** producer thật cho từng stage, independent validation, final
  certificates và clean receiving-environment load.
- **Actual/evidence:** runner chỉ dispatch quality component 4.13, còn lại
  `PRODUCTION_PRODUCER_NOT_ACTIVATED`; 4.13 vẫn thiếu stage certification;
  scientific gates luôn giữ `FINAL_CERTIFICATION_INCOMPLETE`.
- **Confirmed root cause:** foundations deliberately chưa activate production;
  đây là delivery gap, không phải lý do bỏ guards hoặc ép gate PASS.
- **Reproduction:** đọc dispatch và tests `test_acceptance_runner.py`,
  `test_component_quality_pass_cannot_open_final_scientific_gate`.
- **Minimal fix/regression:** complete approved contract/producer path, từng stage
  report/validator, final quality/replay/parity/portable certified handoff.
- **Status/blockers:** IMPLEMENTED/TESTED một phần; không có production dataset
  mới EXECUTED/VERIFIED trong lượt này. Gold, budget, approvals còn bắt buộc.

### BR-M1-012 — MEDIUM — M2 code change làm M1 producer binding không còn khớp

- **Affected:** `src/kg_pipeline/run.py:58–70,324–347`,
  `src/kge/adapter.py:104–134`, trên reconcile và các nhánh Codex.
- **Expected:** preserve exact producer context và khai báo compatible consumer;
  hai máy cần kiểm cùng dữ liệu, không bỏ lineage guards.
- **Actual/evidence:** fixture run ban đầu đọc được; chỉ sửa `src/kge/consumer.py`
  khiến `load_run_manifest` reject `Executing code differs...` dù M1 artifact giữ nguyên.
- **Confirmed root cause:** combined package fingerprint gồm M1, M2 và drift;
  consumer dùng current workspace check mặc định. Cùng code/config vẫn có thể
  chạy trên máy khác; không phải mọi transfer đều bị lỗi.
- **Reproduction:** probe `m1_m2_code_binding` tại các fixed SHA.
- **Minimal fix/regression:** giữ immutable producer bundle/environment hoặc
  thêm versioned producer/consumer compatibility contract; test same bundle
  khác máy, consumer-only change, producer drift, missing transitive dependency.
- **Status/blockers:** fixture VERIFIED; pack/fetch/dependency closure và clean
  receiving-environment test chưa triển khai. Không tắt checks để chuyển data.

### BR-M1-013 — MEDIUM — Legacy test failures và lint còn tồn tại

- **Affected:** `tests/kg_pipeline/test_parity.py`, `src/kg_pipeline/parity.py`
  trên compliance/cont; `tests/kg_pipeline/test_locked_mode.py:118` và
  `src/kg_pipeline/run.py` trên reconcile; các files trong Ruff logs.
- **Expected:** regression/contract tests và Ruff đạt trước tích hợp.
- **Actual/evidence:** compliance/cont có ParityError trong test parity;
  reconcile fail vì guard phát ContractError, test đòi ArtifactConflict.
  Lint 1/2/5/7 errors ở các nhánh cũ theo ma trận.
- **Confirmed root cause:** test/runtime không đồng nhất ở fixed branch code;
  reconcile vẫn fail closed, không phải bằng chứng guard fail open.
- **Reproduction:** commands/test targets/JUnit/logs ghi trong
  `verification_results_verified.json`.
- **Minimal fix/regression:** sửa contract/fixture theo dữ liệu đúng, không hạ
  invariant/threshold; Ruff unused imports; quality unused gold cần sửa logic,
  không chỉ xóa biến để lint xanh.
- **Status/blockers:** các nhánh Codex mới đã PASS regression được chạy; không
  sửa nhánh cũ trong review này. Shared environment giới hạn kết luận CI/lock.

## 5. Verification và giới hạn

- Python 3.11.9, shared isolated `.venv-m1`; không cài lại riêng dependency lock
  cho từng nhánh cũ. Do đó bảng không phải kết quả CI/native environment của
  từng branch. Chưa chạy Python 3.10 hoặc remote CI trong lượt review.
- Full current regression: **408 passed, 10 skipped**;
  `outputs/m1_branch_review_20261014/full_current.xml`.
- Current full `ruff check .`: PASS. Không sửa production source để tests xanh.
- Fixtures/probes mới xác minh code behavior; không phải scientific EXECUTED
  hoặc G1/G2 VERIFIED. Các probes báo ModuleNotFound/NotImplemented trên nhánh
  không có component là giới hạn feature, không mặc định gọi là regression.
- Lượt thử đầu thiếu parent của basetemp, gây fixture setup errors; lưu logs
  riêng, tạo parent rồi chạy lại. Chỉ dùng `_verified` logs/JUnit cho ma trận.
- Không truy cập real `data/locked_test/`, rerun acquisition 4.3, gọi Gemini,
  train mới, reprocess corpus, ghi Neo4j, thay artifacts lịch sử hoặc cấp gate PASS.
- Full findings scope là branch review có trọng tâm; không cam kết mọi lỗi có
  thể tồn tại trong mọi dòng code đã được phát hiện.

## 6. Việc nên làm tiếp

1. Giữ acceptance làm nhánh engineering chính; sửa BR-M1-001 trước activate
   quality certification. Không nhập lại các producer cũ có fallback/bypass.
2. Giải quyết exact source authority và review/approve contract/policies;
   production vẫn BLOCKED đến khi đủ bằng chứng.
3. Complete serializers/producers/validators theo từng stage; giữ legacy v3/T01.
4. Thiết kế gói M1→M2 với dependency closure, immutable producer context,
   checksums/version và receiver validation; thử transfer LEGACY_ONLY riêng.
5. Chỉ đánh giá merge code vào main sau fixes, review và CI; nghiệm thu dataset
   cần real artifacts, main gold, physical replay, actual Neo4j read-back và
   certified loader thành công. Engineering merge không đồng nghĩa data PASS.

Trong lượt này chỉ thêm report và cập nhật progress. Không tự commit/push/merge.
