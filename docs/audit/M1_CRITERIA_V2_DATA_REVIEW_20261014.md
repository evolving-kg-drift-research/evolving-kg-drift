# Review data M1 theo tiêu chí v2 — 14/10/2026

**Kết luận: M1 chưa được nghiệm thu; không bàn giao scientific cho M2.**
Có lỗi thực tế (`FAIL`) và điều kiện chưa có bằng chứng (`BLOCKED`).
G1/G2 hiện trả BLOCKED, certified M2 loader từ chối gói `production_v3`.
Việc M2 Dev đã chạy riêng không thay đổi kết luận nghiệm thu M1.

## 1. Phạm vi và căn cứ

- Checkout thực tế: `codex/m2-drift-workflow` tại
  `abeb425385f8b19bb05db30c84c4bb05371e8640`, dirty state true.
  Không checkout/reset nhánh acceptance, không thay dữ liệu hay code production.
- Tài liệu đối chiếu: `D:/Users/Downloads/Tieu_chi_nghiem_thu_M1_Data_Temporal_KG_v2 (1).md`,
  SHA-256 `0414650cbed7b73871867d51c3b6ad6f913504dd4b5f372f155861ef0ce7f560`.
  Tên file v2, version bên trong là 1.1. Đọc toàn bộ tài liệu; đây là checklist
  tham khảo, không tự tạo approval/amendment/certificate.
- Requirements có hiệu lực: AGENTS, `configs/protocol_v1.yaml`,
  `data/manifests/sources.lock.json`, `docs/data_pipeline_spec.md`,
  `config/schema.yaml`, `config/corpus_scope.yaml`, `docs/M1_HANDOFF_REQUIREMENTS.md`;
  đọc PROGRESS, các audit M1 gần nhất và hồ sơ mới trong bundle.
- Data thực tế: toàn bộ file của `data/KG_lan2/evolving_kg_downstream_v3/`,
  `data/transe_fact_check_package/`, `data/m1_audit_and_gates_bundle/`;
  body/raw/receipts được tham chiếu và đã khôi phục dưới `outputs/`.
  Tổng cộng 128 file metadata/package được kiểm kê hash, 43 Parquet gồm
  39 Parquet v3 và 4 bản sao. Kiểm toàn bộ body/raw tham chiếu, không chỉ sample.
- Không đọc `data/locked_test/`, không chạy lại acquisition 4.3, không gọi LLM,
  không reprocess corpus, không ghi Neo4j, không train M2.
  Không tự xác nhận một kho dữ liệu khác chưa được cung cấp URI.

Evidence mới, bất biến theo lần review:
`outputs/m1_criteria_v2_review_20261014/`.
Các script ở đây phục vụ kiểm toán read-only, không phải producers/certificates.

## 2. Những phần kiểm tra kỹ thuật đã đạt

| Kiểm tra thực tế | Kết quả | Giới hạn |
|---|---|---|
| Raw bytes theo inventory/memberships | **5.168/5.168 khớp SHA-256** | Không tự chứng minh public availability hoặc source independence. |
| Body text blobs | **4.745/4.745 khớp hash** | Không tự chứng minh parser/semantics đã được duyệt. |
| Strict retrieval receipts | **5.271/5.271** khớp file hash, canonical record hash, raw hash, URLs, retrieval clock | Chứng minh acquisition linkage; không biến acquisition clock thành evidence clock. |
| Sidecars v3 có sẵn | **38/38** khớp physical hash, semantic hash và row count | `extracted_claims_partial.parquet` thiếu sidecar; bốn file copy cũng không có sidecar tại chỗ. |
| Canonical triples | **10/10** snapshots có triples duy nhất, counts/hash khớp manifest cũ | Manifest cũ không đủ contract chứng nhận hiện hành. |
| Legacy snapshot set reconstruction | **10/10** khớp tập triples khi dùng clocks ghi sẵn trong fact store | Không phải certified replay: chưa chứng minh clocks/mapping/acceptance hoặc byte-identical rebuild. |
| Các liên kết hiện có | Không thấy dangling ở các joins raw/body/retrieval/source-version/event→fact đã kiểm; PK đã khai báo của bảng có mặt không trùng | Không bù được bảng/khóa chưa tồn tại; extracted_claims thiếu `body_variant_id` theo runtime FK. |
| Bảo toàn đầu vào | Rehash **128/128** file package không thay đổi; bốn protected config/lock không đổi | Không sửa dữ liệu cũ để làm PASS. |

Đặc biệt: gói `transe_fact_check_package` là **bản sao đúng bytes** của bốn bảng
v3; hai reports trong `m1_audit_and_gates_bundle` cũng **trùng bytes** reports v3.
Chúng không phải một run đã rebuild hoặc đã sửa các lỗi M1.

## 3. Đối chiếu đủ 16 nhóm tiêu chí

Không có nhóm nào đủ toàn bộ điều kiện để nhận scientific PASS. Một nhóm ghi
FAIL nếu có kiểm tra cụ thể đã phát hiện vi phạm; BLOCKED dùng cho bằng chứng
còn thiếu. Không đánh đồng thiếu evidence với một fact chắc chắn sai.

| Mã | Trạng thái nghiệm thu | Bằng chứng / phần thiếu hiện tại |
|---|---|---|
| M1-01 Nguồn có thẩm quyền | **BLOCKED** | Proposal đúng hash; hai original Markdown thiếu. Approval/source replacement trong bundle chưa đối chiếu amendment/bytes/hash với authority đang có. |
| M1-02 Truy ngược nguồn | **BLOCKED** | Raw/body/strict receipts kiểm được; 1.803 facts dùng URL `internal://`; thiếu certified ClaimProvenance và lineage producer v3. |
| M1-03 Dẫn chứng chính xác | **FAIL** | **1.849/1.865 claims**, **1.788/1.803 facts** không khớp exact span hash. Các hashes hiện khớp whole body. |
| M1-04 Định danh đúng/as-of | **BLOCKED** | 1.803/1.803 facts ghi `entity_map_version=v1_mock`; không có registry/mapping decisions/basis/availability được chứng nhận. |
| M1-05 Thời gian có căn cứ | **FAIL + BLOCKED** | 952 facts observed trong tháng 9; T07–T10 ngoài window trong config hiện hành. Bundle khai có extension nhưng chưa đủ amendment binding. Clock proof/acceptance policy chưa hoàn tất. |
| M1-06 Lịch sử dữ kiện | **BLOCKED** | 1.803 rows đều creation/AUTO_ACCEPTED, không supersedes. Thiếu adjudication/support/conflict/revision lineage có rule/evidence. Chỉ có creation không tự chứng minh dữ kiện sai hoặc bắt buộc phải có correction thật. |
| M1-07 Thống nhất schema | **FAIL + BLOCKED** | Bảng fact_versions/document_clusters không đúng public fields; runtime 9/17 name mismatches, 17/17 physical contracts chưa khai báo. Candidate 1.1 chưa được áp dụng/phê duyệt. |
| M1-08 Snapshot as-of đúng | **BLOCKED** | Unique triples và legacy set reconstruction đạt; thiếu accepted clocks, mapping-as-of, certified support/exclusions và manifest dependencies. |
| M1-09 Parquet–Neo4j | **BLOCKED** | Report ghi `DB_READ_BACK_PERFORMED=false`; chỉ export CSV, không có actual DB node/edge/support read-back. |
| M1-10 Gold/G2 quality | **BLOCKED** | Không có gold độc lập, matching/coverage annex và ngưỡng số approved cho run này; policy vẫn PROPOSED. Confidence 0.9/AUTO_ACCEPTED không thay thế quality evaluation. |
| M1-11 Tái tạo/kiểm toán | **BLOCKED** | Hash file kiểm được; không có producer run_manifest hiện hành, frozen config/code/component chain và certified full rebuild. |
| M1-12 M2 nhận an toàn | **BLOCKED** | Public certified loader đã gọi với run lấy từ report; bị chặn vì thiếu `runs/production_v3/run_manifest.yaml`. G1/G2 BLOCKED, evaluated_count=0. |
| M1-13 Stage 4.18 PASS | **BLOCKED** | PASS cũ không hợp lệ để nghiệm thu khi không read-back DB thật; thiếu stage manifest/receiver evidence. |
| M1-14 Downstream feasibility | **FAIL + BLOCKED** | Boundary indices cắt timestamp groups; có overlap/path counts nhưng chưa có QA semantics/support/guideline/approved feasibility thresholds. |
| M1-15 Conservation | **FAIL + BLOCKED** | Event interval counts lệch actual cutoff counts tại T01–T07; chưa có claim dispositions cho toàn bộ 1.865 claims và full cross-stage reconciliation. |
| M1-16 Artifact inventory/receiver | **BLOCKED** | Local inventory mới phục vụ review, không thay handoff manifest; thiếu accessible receiver URIs, certified producer refs và kiểm tra từ thiết bị nhận. |

Các missing public table names được ghi trong `data_public_contract_checks.json`.
Một tên bảng thiếu **không đồng nghĩa vai trò dữ liệu hoàn toàn không tồn tại**:
v3 có `extracted_claims`, `source_versions`, các snapshot files dưới tên legacy.
Nhưng không có approved serializer/contract chứng minh những file ấy đáp ứng
đầy đủ `claims`, `raw_source_versions`, `snapshot_edges/support/exclusions`.
Không tự đổi tên hoặc suy đoán aliases để qua audit.

## 4. Findings có thể tái kiểm

### ACC-V2-001 — Authority và approval bundle chưa đủ mở production

- **Severity:** GOVERNANCE / HIGH.
- **Files:** `data/manifests/sources.lock.json`, `configs/protocol_v1.yaml`,
  `config/corpus_scope.yaml`, `decisions/decision_log.jsonl`,
  `data/m1_audit_and_gates_bundle/decisions/decision_log.jsonl`.
- **Expected:** exact source bytes/hash hoặc approved amendment; window/config
  và quyết định có binding tới run được xét.
- **Actual/evidence:** hai locked Markdown MISSING, proposal MATCH.
  Bundle có thêm bốn decisions về source replacement, config approval, freeze
  và September extension; không có trong active ledger; chỉ `TEMPLATE.yaml`
  trong amendments, không có active `config_baseline.json` hoặc run manifest.
  `approved_by=user` trong file được giao không tự xác thực authorization.
- **Root cause confirmed:** thiếu source originals/binding artifacts; bundle
  và authority hiện hành khác nhau. Không kết luận các quyết định là giả.
- **Reproduce:** đọc `source_authority_check.json` và
  `input_stability_and_approval_checks.json` trong evidence directory.
- **Minimal fix:** restore originals; hoặc review/approve amendment đúng bytes,
  hash, scope, precedence và reprocess impact. Xác minh extension riêng trước
  đổi window. Giữ nguyên các ledger/artifacts lịch sử.
- **Regression proposed:** source replacement không được chấp thuận bằng
  approval string, stale baseline hash hoặc bundled decision không bind run.
- **Remaining blockers:** owner/approval, original bytes, approved baseline.
- **Tier:** audit EXECUTED/VERIFIED sự thiếu/bất nhất; remediation NOT IMPLEMENTED.

### ACC-V2-002 — Whole-body hash đang được dùng làm evidence-span hash

- **Severity:** CRITICAL.
- **Files:** `data/KG_lan2/evolving_kg_downstream_v3/tables/extracted_claims.parquet`,
  `tables/fact_versions.parquet`, `tables/body_variants.parquet`.
- **Expected:** hash exact `[start,end)` trên đúng body representation.
- **Actual/evidence:** offsets hợp lệ ở 1.865 claims/1.803 facts; tất cả hashes
  khớp whole body. Chỉ 16 claims/15 facts khớp exact slice; các slice này cũng
  chưa được đánh giá relation semantics/grounding bằng gold.
- **Root cause confirmed:** payload chứa body hash thay vì span hash; không
  suy đoán code producer đã tạo lỗi vì producer lineage chưa được khôi phục.
- **Reproduce:** `audit_data.py` tạo `span_checks.json` từ toàn bộ referenced texts.
- **Minimal fix:** run mới từ stage sớm nhất bị ảnh hưởng sau contract/approval;
  tái tạo candidates/spans và human evidence validation. Không sửa sidecar/hash
  tại chỗ để nâng chứng nhận dữ liệu v3.
- **Regression proposed:** whole body khác proper slice phải FAIL; Unicode,
  offsets, representation/version, subject/object grounding và relation support.
- **Remaining blockers:** body/ontology policy, producer, approved extractor/review.
- **Tier:** defect EXECUTED/VERIFIED toàn bộ span hashes; semantic accuracy NOT VERIFIED.

### ACC-V2-003 — Identity/acceptance/temporal provenance chưa được chứng nhận

- **Severity:** HIGH.
- **Files:** `tables/fact_versions.parquet`, `tables/extracted_claims.parquet`,
  `config/schema.yaml`, `docs/audit/m1_acceptance_design_v2/identity.md`, `temporal.md`.
- **Expected:** canonical identity decisions có basis/availability; riêng validity,
  evidence, acquisition, adjudication và accepted clocks; human review v1.
- **Actual/evidence:** 1.803 v1_mock/AUTO_ACCEPTED/internal URLs; thiếu accepted clock,
  mapping decision history, scientific time basis và adjudication provenance.
  1.784 facts có observed_at=valid_from; sự bằng nhau không chứng minh clock
  substitution, nhưng không có proof độc lập để xác nhận cách gán.
- **Root cause confirmed:** thiếu required provenance/clock fields/artifacts.
  Timestamp substitution và tỷ lệ entity errors vẫn là hypotheses chưa chứng minh.
- **Reproduce:** `review_summary.json`, public field diff, source/receipt tables.
- **Minimal fix:** verified body→source/claim links, occurrence registry/mappings,
  temporal evidence and reviewed decisions trong run mới theo policies approved.
- **Regression proposed:** same-name collision, future alias, late support/mapping,
  no timezone/basis, pending không vào graph, support-only update.
- **Remaining blockers:** authority, identity/temporal/acceptance approvals.
- **Tier:** missing metadata EXECUTED/VERIFIED; identity/scientific clocks BLOCKED.

### ACC-V2-004 — Data và active public/runtime contracts không thống nhất

- **Severity:** HIGH.
- **Files:** `config/schema.yaml`, `src/kg_pipeline/contracts.py`,
  `tables/fact_versions.parquet`, `tables/document_clusters.parquet`,
  `docs/audit/m1_acceptance_design_v2/manifest.json`.
- **Expected:** full typed fields/PK/FK/nullability và explicit serializer mappings.
- **Actual/evidence:** 9/17 runtime name mismatches, 17/17 physical declarations
  UNDECLARED. Fact store thiếu public IDs, accepted/reviewer/ontology/rule fields,
  scope, literal values và supporting claim lists. Runtime claim FK dùng
  `body_variant_id`, file legacy dùng `source_id`. Candidate package 8/8 hashes
  MATCH nhưng REVIEW_REQUIRED, runtime_apply_allowed=false.
- **Root cause confirmed:** các hợp đồng/tables khác phiên bản, migration chưa activated.
- **Reproduce:** `machine_contract_audit.json`, `data_public_contract_checks.json`,
  `runtime_PK_FK_checks.json`; không bỏ cột/đổi aliases để làm PASS.
- **Minimal fix:** duyệt field-level matrix revision rồi serializer/migration run
  mới; bảo toàn literals và legacy files; conditional requiredness cho pending/reject.
- **Regression proposed:** exact column/type/nullability, PK/FK, entity/literal XOR,
  serializer round-trip và public compatibility.
- **Remaining blockers:** contract owner/approval, missing production producers.
- **Tier:** contract audit EXECUTED/VERIFIED; migration BLOCKED.

### ACC-V2-005 — Boundary index chia đôi timestamp groups; counts không theo cutoff

- **Severity:** HIGH.
- **Files:** `snapshot_boundaries.yaml`, `config/snapshot_boundaries.yaml`,
  `tables/kg_events.parquet`, `tables/transition_metadata.parquet` của v3.
- **Expected:** atomic timestamp groups, counts đúng events thuộc interval cutoff;
  không điều chỉnh cutoffs dựa vào downstream scores.
- **Actual/evidence:** T01/T02/T04/T05/T06 index splits equal timestamp groups.
  T01 khai 120 events nhưng cutoff bao gồm **121**; T02 cumulative index241
  nhưng thực tế **247**, interval khai121/thực126. Counts interval T01–T07 lệch.
  Các canonical snapshot sets vẫn khớp legacy fact clocks; đây là lỗi boundary
  allocation/accounting, không phải chứng minh thiếu triples tại cùng cutoff.
- **Root cause confirmed:** boundary partition dùng row indices bên trong groups
  có cùng effective_at; groups có 293 timestamp values xuất hiện nhiều lần.
- **Reproduce:** `additional_checks.py` tạo `atomic_boundary_and_count_checks.json`;
  so sorted events `[end-1]`/`[end]` và recount effective_at<=cutoff.
- **Minimal fix:** đăng ký tie/feasibility rule và rebuild events/boundaries trong
  run mới, chỉ sau khi clocks/supports được xác minh; không epsilon/patch v3.
- **Regression proposed:** nhiều events cùng timestamp tại quantile; index/counts
  phải bind cùng atomic groups và snapshot interval semantics.
- **Remaining blockers:** approved boundary/window policy, verified KG state events.
- **Tier:** accounting defect EXECUTED/VERIFIED; scientific boundary construction BLOCKED.

### ACC-V2-006 — Chưa có gold/thresholds/main evaluation đủ điều kiện

- **Severity:** HIGH.
- **Files:** `docs/audit/m1_acceptance_design_v2/quality.md`,
  `src/kg_pipeline/acceptance_quality.py`, `src/kg_pipeline/acceptance_gates.py`,
  `data/m1_audit_and_gates_bundle/decisions/decision_log.jsonl`.
- **Expected:** independent source-document gold, hai annotators và adjudication,
  thresholds/coverage locked trước main scoring, FP/FN/denominators/strata.
- **Actual/evidence:** quality policy ghi NUMERIC THRESHOLDS ABSENT/NOT APPROVED.
  Bundle freeze dẫn pilot30/43.3% include/invariant checks, không cung cấp gold
  hay quality report: include ratio không là relation precision/recall.
  Current approved design yêu cầu pilot50. G2 thực gọi BLOCKED/evaluated_count0.
  Existing audit còn ghi gold-content/adjudication binding và relation coverage
  gaps; chưa có remediation evidence đóng các findings ấy.
- **Root cause confirmed:** thiếu approved scoring inputs và độc lập gold tại run xét.
- **Reproduce:** policy text, bundle inventory, `certified_handoff_checks.json`.
- **Minimal fix:** whole-article pilot annotations rồi approved threshold annex;
  main gold độc lập và evaluator kiểm đúng adjudication content/coverage.
- **Regression proposed:** empty/unsupported gold, modified adjudication, missing
  per-relation denominator, unrecognized annex keys, stale hash/run.
- **Remaining blockers:** annotators/owner/guideline, pilot/main artifacts và approvals.
- **Tier:** required-input absence EXECUTED/VERIFIED; quality scoring BLOCKED.

### ACC-V2-007 — PASS report không chứng minh Stage 4.18/Neo4j parity

- **Severity:** HIGH.
- **Files:** `reports/parity_report.json` của v3 và bundle,
  `data/m1_audit_and_gates_bundle/docs/PROGRESS.md`.
- **Expected:** materialize real DB, separate read-back, exact node/edge/support
  parity, run/database identity và valid Stage 4.18 chain.
- **Actual/evidence:** status PASS đồng thời DB_READ_BACK_PERFORMED=false,
  materialization_layer=Neo4j CSV Export (no database read-back).
  T10 parity ghi1803 rows, canonical snapshot chỉ1205 unique triples;
  chưa có contract phân biệt support rows và canonical database edges.
- **Root cause confirmed:** parity proof chỉ là exported CSV; không kết luận DB
  thực sai vì chưa có DB read-back để kiểm tra.
- **Reproduce:** `new_audit_bundle_checks.json`; reports có hash trùng v3.
- **Minimal fix:** canonical validation trước materialization, real read-back và
  final G1/Stage4.18 reports mới, không đổi chữ PASS trong historical file.
- **Regression proposed:** duplicate support rows, missing/extra edge/node, sai
  run/database/support metadata, write succeeds/read-back fails.
- **Remaining blockers:** certified inputs, active producer and Neo4j target/access.
- **Tier:** report limitations EXECUTED/VERIFIED; parity/Stage4.18 BLOCKED.

### ACC-V2-008 — Chưa có certified portable handoff

- **Severity:** HIGH.
- **Files:** `src/kge/adapter.py`, `src/kg_pipeline/gates.py`,
  v3 snapshot manifests, `data/transe_fact_check_package/`.
- **Expected:** reachable artifact inventory, supported manifests, exact run/gates,
  receiver validation và certified loader thành công.
- **Actual/evidence:** run ID `production_v3` lấy từ parity report, nhưng public
  loader ném FileNotFoundError: `runs/production_v3/run_manifest.yaml` chưa có.
  G1/G2 gọi thực đều BLOCKED/evaluated_count0. Bốn tables chỉ copy v3, thiếu
  snapshots/maps/gold/support/gates. Chưa thử từ thiết bị nhận/kho URI khác.
- **Root cause confirmed:** package không có certified producer/dependency chain;
  loader từ chối đúng điều kiện, không phải lỗi cần bypass.
- **Reproduce:** `.venv-m1/Scripts/python.exe -X utf8 outputs/m1_criteria_v2_review_20261014/audit_data.py`
  trong fresh output namespace; xem `certified_handoff_checks.json`.
- **Minimal fix:** tạo handoff ở cuối certified new run, giữ component/run hashes
  và immutable URI inventory, kiểm clean receiver environment. Không tạo fake
  run_manifest/sidecar, gọi private loader hoặc đổi guard để thông qua.
- **Regression proposed:** thiếu/stale manifest/certificate, mutated artifact,
  wrong run, independent receive/download/checksum/load.
- **Remaining blockers:** toàn bộ gates/Stage4.18/portable certification path.
- **Tier:** official-loader refusal EXECUTED/VERIFIED; official handoff BLOCKED.

### ACC-V2-009 — Conservation mới chỉ kiểm được một phần

- **Severity:** MEDIUM.
- **Files:** `tables/filter_decisions.parquet`, `extracted_claims.parquet`,
  `fact_versions.parquet`, `transition_metadata.parquet` và required ledgers.
- **Expected:** defined units, disjoint exhaustive statuses, ID/reason/ref links;
  multiple outputs/support multiplicity không bị coi như missing rows.
- **Actual/evidence:** 4.745 body filters đối soát đầy đủ (2196include/2545exclude/
  4review). 1.865claims và 1.803facts chênh62 rows, nhưng không có adjudication
  disposition ledger để giải thích theo ID; không kết luận62claims bị mất.
  T01–T07 event counts có violation xác minh ở ACC-V2-005.
- **Root cause confirmed:** full cross-stage accounting artifacts còn thiếu.
- **Reproduce:** `link_and_conservation_checks.json`, table counts, boundary report.
- **Minimal fix:** per-stage disposition/reconciliation trong run mới, conservation
  theo đúng unit, explicit many-to-one links và pending/exclusions reason codes.
- **Regression proposed:** unexplained discard, duplicate dispositions, pending
  entering graph, facts/supports/unique edges counted as separate units.
- **Remaining blockers:** schema/adjudication/source-support producers.
- **Tier:** body filter accounting EXECUTED/VERIFIED; full accounting BLOCKED.

## 5. Review chính bộ tiêu chí mới

16 nhóm bao phủ đúng các mặt cần nghiệm thu; không cần thêm ngưỡng số tùy ý.
Cần làm rõ ba điểm trước khi dùng làm quy trình execution:

1. **Sửa vòng phụ thuộc G1 ↔ Stage4.18:** §2.4.1 yêu cầu G1 PASS làm đầu vào
   Stage4.18, trong khi §2.2 G1 yêu cầu real parity. §7 bước6 cũng đòi finalG1
   trước bước7 realDB. Nên tách pre-materialization canonical/temporal checks
   khỏi finalG1: GateA/required quality → canonical validation → materialize/
   read-back → finalG1 + Stage4.18 closeout → M2 receiver. Không bỏ parity,
   không coi prechecks là finalG1. Không tự thay quy định cấp cao khi chưa duyệt.
2. **Tách provenance evidence của approval:** thêm owner/role, version/hash/scope,
   amendment reference và dependency invalidation cho từng quyết định. Xử lý
   cụ thể bundled source/window approvals trước run; không chỉ nhìn approved_by.
3. **Vận hành gold/coverage:** final gold phải bind nội dung labels/adjudication,
   đánh giá recall từ toàn bài, đủ relation/source/time strata và denominators;
   cung cấp approved numerical annex cùng independent main sample. Policy file
   candidate vẫn nói candidate-claim unit, nên chưa tương thích hoàn toàn với
   lựa chọn whole-article gold trong plan.

Không bổ sung downstream score làm tiêu chí chọn/sửa M1. Overlap/path counts
trên graph legacy chỉ là chẩn đoán: T01 có167entities/121triples và24 directed
two-hop node sequences; T10 có1389entities/1205triples và1783 sequences.
Persistent ID counts qua9transitions: 167,343,503,646,787,936,1057,1176,1282.
Những ID chưa verified và chuỗi hai cạnh không tự là QA gold/semantic questions.

## 6. Điều kiện để được chuyển chính thức sang M2

1. Khôi phục source authority và đối soát bundled decisions/window/config.
2. Hoàn thiện/phê duyệt schema, identity/evidence/time/support và quality procedure.
3. Chứng nhận historical upstream eligibility/GateA; chọn pilot theo registered
   procedure, xử lý stage sớm nhất bị ảnh hưởng trong **run mới**.
4. Independent pilot gold/quality, threshold annex, freeze/main processing và
   independent final quality; từng production stage phải report rồi STOP.
5. Rebuild graph events/atomic boundaries/snapshots; đủ support/exclusions,
   conservation và deterministic proof theo frozen versions.
6. Actual Neo4j read-back, finalG1/G2 và Stage4.18 PASS đúng run.
7. Portable handoff inventory/receiver checks và certified M2 loader PASS.

Đây là thứ tự remediation, không cấp phép tự chạy liên tiếp production stages.
Next bounded work nên là authority/approval reconciliation + historical
eligibility ledger, trước sửa data và scale extraction. Không cần bỏ toàn bộ
raw/body đã khôi phục, không tự crawl lại từ đầu.

## 7. Mức kiểm chứng và thay đổi trong lượt này

- **EXECUTED:** read-only audit trên real files; explicit G1/G2 evaluations và
  official M2 loader check. Các gate không tạo run vì producer manifest thiếu.
- **VERIFIED:** hashes toàn referenced raw/body, strict receipts, existing sidecars,
  legacy graph sets, boundary accounting và loader refusal trong phạm vi đã nêu.
- **Chưa VERIFIED:** relation/entity semantic quality, scientific clocks, complete
  reproducible pipeline, live Neo4j parity, scientific gates hoặc receiving device.
- **IMPLEMENTED:** chỉ thêm audit scripts/evidence/report; không remediation code
  production. Không chạy lại full pytest vì không đổi production code; fixture
  tests cũ không được dùng làm chứng nhận dữ liệu lần này.
- Files có thể review: report này và mục mới trong `docs/PROGRESS.md`; evidence
  dưới outputs được ignore. Các work M2/untracked có trước được bảo toàn.
- Không commit/push/merge, không sửa protocol/source lock/decision ledger hoặc
  file tiêu chí Downloads. Findings vẫn OPEN theo đúng phạm vi.
