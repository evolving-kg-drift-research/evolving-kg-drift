# M1: review nhánh Hương, dữ liệu ZIP và quyết định hướng đi — 2026-10-04

## Kết luận điều hành

**Khuyến nghị: sửa M1 có chọn lọc trước khi mở M2 production.** Giữ nhánh
`codex/m1-thu-huong-remediation` làm nền tích hợp. Giữ nguyên gói của Hương làm
artifact tham chiếu để đối chiếu/replay, chưa dùng làm bộ dữ liệu thí nghiệm khóa.
Không cần bỏ toàn bộ công sức hoặc crawl lại từ đầu. Cần khôi phục upstream,
giải quyết thẩm quyền/schema/clock, rồi chỉ tái xử lý những stage bị ảnh hưởng
trong run mới. Đây là đề xuất, không phải amendment hoặc quyết định khoa học đã duyệt.

M2 có thể tiếp tục phát triển/test bằng fixtures; chưa huấn luyện production,
chưa lấy drift/SED+/QA outcomes để quyết định cách sửa M1.

## Remote và trạng thái tích hợp

Đã chạy `git fetch --all` thành công ngày 04/10. Không có remote tip mới so với
refs đã có trước lượt này. Nhánh Hương được nhận diện qua tác giả hai commit:
`6779bf4` và `e19fe25`; tip đầy đủ là
`e19fe25d2325a53ebf49ada27cff4692aa1c6638`.

| Remote branch | Tip | Quan hệ với HEAD 6000f38 / hướng xử lý |
|---|---|---|
| main | 9544e41 | Đã là ancestor; không có commit thiếu |
| feature/data_try | 4c24da2 | Đã là ancestor; không có commit thiếu |
| fix/data-pipeline-compliance | 05d0eb5 | Đã là ancestor; không có commit thiếu |
| reconcile/pipeline-drift-compliance | 6000f38 | Cùng HEAD |
| feature/integrated-kge-drift | 286368e | Lịch sử phân kỳ 17/2; có code M2 cũ, không lấy cả nhánh thay nền |
| fix/data-pipeline-compliance-cont | e19fe25 | Lịch sử phân kỳ 11/2; review chọn lọc, chưa merge |

**Fetch đã hoàn tất; merge/pull vào checkout chưa thực hiện.** Checkout có các
sửa đổi C4–C9 và snapshot chưa commit từ trước; không stash/reset/ghi đè chúng.
Nhánh Hương đồng thời thay `configs/protocol_v1.yaml`, `sources.lock.json` và
decision log. AGENTS.md §2.2 và §8.2 không cho tự quyết định xung đột khoa học
hoặc sửa locked sources khi chưa có amendment được duyệt.

Decision log của nhánh Hương có mục tự ghi `approved_by: user` ngày 22/09,
trong khi baseline checkout giữ original hashes theo quyết định ngày 20/09.
Không coi chuỗi đó là xác nhận thẩm quyền trong phiên này; cần đối chiếu approval
gốc. Chưa kết luận quyết định của Hương là giả hoặc không từng được duyệt.

Đối chiếu nhánh integrated: `src/drift/pipeline.py` vẫn mô tả/tính primary drift
bằng seed 13; checkout đã có sửa ba seed. Đây là bằng chứng không nên thay toàn
bộ M2 bằng bản từ nhánh integrated. Chưa thực hiện audit đầy đủ M2 trong lượt này.

## Dữ liệu đã đọc và xác minh

Người dùng xác nhận ZIP là `data/evolving_kg_downstream_v2.zip`, không phải file
khác ở root. SHA-256:
`de9b273cec9ca13ba6d629017f83a8d00e4471ff8843d00898e5980c7c2b1161`.
File 2.062.932 bytes, 38 entries; giống byte-for-byte bản review 03/10.
Đọc trong bộ nhớ; không giải nén đè, không thay đổi ZIP.

Bằng chứng mới:

- [Replay và contract review](m1_package_recheck_20261004.json).
- [Topology, source lock, schema và remote refs](m1_graph_readiness_20261004.json).
- Finding gốc đầy đủ: [review 03/10](m1_thu_huong_package_review_20261003.md)
  và [phụ lục an toàn nhánh](m1_thu_huong_branch_safety_supplement_20261003.md).

Cả 10 snapshot khớp physical/semantic hash, pure producer replay, CSV node sets
và edge multisets kèm temporal metadata. Không thấy future-evidence/validity
violation khi so với timestamp đã lưu. **Chưa xác minh được căn cứ của các
timestamp đó, mapping availability hoặc Neo4j database read-back.**

| Chỉ tiêu | T01 | T06 | T10 |
|---|---:|---:|---:|
| Dòng fact | 127 | 824 | 1.803 |
| Bộ ba duy nhất | 121 | 724 | 1.205 |
| Entity | 167 | 936 | 1.389 |
| Thành phần liên thông yếu | 54 | 263 | 313 |
| Entity trong thành phần lớn nhất | 19 | 277 | 562 |
| Entity chỉ có một láng giềng | 126 | 750 | 1.040 |
| Chuỗi node 2-hop có hướng, đơn | 24 | 710 | 1.783 |

Đếm 2-hop trên ba node khác nhau, gộp nhãn relation; đây là mô tả cấu trúc,
không phải số câu QA hợp lệ, không bao gồm quy tắc inverse relation chưa được
đăng ký. Không chọn query IDs, anchors, buckets hoặc cutoffs trong lượt audit.

Các điểm tích cực: file đọc được, export nhất quán, 994 source IDs trong fact
store đều thuộc tập include; 167 entity T01 còn xuất hiện tại mọi snapshot sau.
Persistent intersection theo từng transition tăng từ 167 đến 1.282, nên không
phải thiếu hoàn toàn ứng viên anchor. Tuy nhiên số lượng không chứng minh
canonical identity, chất lượng anchor, numerical rank hoặc holdout alignment.

Các giới hạn quan trọng:

- 598/1.803 dòng T10 lặp bộ ba; cần bảo toàn support provenance và tách riêng
  canonical graph/training triples theo contract. Không mặc định xóa 598 facts.
- T10 có 1.040/1.389 entity bậc láng giềng 1 (~74,9%); đồ thị phân mảnh. Đây là
  rủi ro về tính nhận dạng/căn chỉnh và chất lượng multi-hop, chưa phải bằng
  chứng mô hình chắc chắn thất bại hoặc không đủ statistical power.
- Cả 9 transition có 0 removed triples, 0 disappeared entities; store có 1.803
  `creation`, 0 supersedes. Graph tăng trưởng vẫn có thể tạo representation
  drift; gói này chưa kiểm chứng cơ chế correction/retraction trong thực tế.
- H2 Seen-at-T1 bị giới hạn bởi 167 entity tại T01; 24 chuỗi 2-hop T01 cho thấy
  cần kiểm tra feasibility recurring QA sớm. Không thay T01 theo QA scores.
- T07–T10 ngoài operational window kết thúc 31/08/2026; 952 facts có observed
  date sau mốc đó. T08–T10 chỉ cách nhau 18 phút 20 giây. Không tự loại tháng 9
  hay gộp snapshot; phải giải thích nguồn clock, scope và tie rule trước freeze.

## Findings xác nhận lại

### M1-RV-001 — GOVERNANCE: xung đột source baseline khi tích hợp

- **Files:** `configs/protocol_v1.yaml`, `data/manifests/sources.lock.json`,
  `decisions/decision_log.jsonl` trên nhánh Hương; `sources/` trên checkout.
- **Expected:** giữ baseline đã có thẩm quyền, thay đổi qua approval/amendment.
- **Actual/evidence:** hai hash Markdown bị thay trên remote; local thiếu hai
  originals, chỉ proposal MATCH; JSON `source_lock.status=BLOCKED`.
- **Root cause:** xác nhận có hai baseline khác nhau; chưa xác minh thẩm quyền
  approval mới, không suy đoán về người tạo.
- **Repro:** `git diff HEAD...origin/fix/data-pipeline-compliance-cont -- configs/protocol_v1.yaml data/manifests/sources.lock.json decisions/decision_log.jsonl`;
  chạy diagnostic script bên dưới.
- **Minimal fix:** lấy originals đúng hash hoặc xác nhận amendment hợp lệ và
  ảnh hưởng invalidation; chưa được tự đổi hash để qua gate.
- **Regression:** source-byte mismatch/missing và stale config approvals phải BLOCKED.
- **Blockers/status:** approval evidence, original files; không sửa/RESOLVED.

### M1-RV-002 — CRITICAL: clocks, mapping và schema chưa chứng minh M1

- **Files:** `src/kg_pipeline/adjudicate.py`, `config/schema.yaml`, ZIP
  `tables/fact_versions.parquet`; runtime `src/kg_pipeline/contracts.py`.
- **Expected:** clocks tách biệt, identity as-of, schema và lineage đầy đủ.
- **Actual/evidence:** producer fallback retrieval/now thành observed time,
  hash mention tự sinh entity; 1.803 facts dùng `v1_mock`, `internal://`,
  confidence 0.9; thiếu clock/basis/mapping artifacts. Local schema vẫn 9/17
  bảng BLOCKED. Nhãn `v1_mock` không tự chứng minh nội dung là dữ liệu giả.
- **Root cause:** xác nhận producer/contract thiếu ràng buộc; chưa biết chính
  xác bao nhiêu timestamp/entity sai nếu không có upstream.
- **Repro:** JSON `facts`, `fact_contract_drift`, `machine_contract`; đọc
  `git show e19fe25:src/kg_pipeline/adjudicate.py`.
- **Minimal fix:** duyệt C3, mapping/clock basis, bổ sung lineage rồi rebuild
  stage bị ảnh hưởng vào run mới; không thêm timestamp giả vào ZIP.
- **Regression:** exact schema round-trip, late mapping, missing clock,
  no retrieval-as-evidence; existing guard tests không thay production evidence.
- **Blockers/status:** upstream, C3 và identity policy; production BLOCKED.

### M1-RV-003 — CRITICAL: revision/quality lỗi trên producer Hương

- **Files:** `src/temporal/snapshot.py`, `src/kg_pipeline/quality.py` tại e19fe25.
- **Expected:** validity trước revision; gold rỗng không PASS.
- **Actual/evidence:** future-effective fixture expected `[audit_old]`, actual
  `[]`; evaluator empty gold trả PASS với evaluated_count=0; runner không gọi
  evaluator. JSON `producer_future_effective_regression`, `quality_gate_regression`.
- **Root cause:** thứ tự filter sai; zero coverage bị quy thành zero error.
- **Repro:** package diagnostic script bên dưới, đã chạy lại 04/10.
- **Minimal fix:** giữ guard/snapshot remediation hiện tại, tích hợp có chọn
  lọc; G2 phải có gold độc lập và coverage theo rule được duyệt.
- **Regression:** `tests/temporal/test_snapshot.py`, `tests/kg_pipeline/test_quality.py`,
  `tests/kg_pipeline/test_scientific_gate_guards.py` đã chạy trên checkout.
- **Blockers/status:** checkout có IMPLEMENTED/TESTED guards; branch Hương chưa
  được sửa; chưa EXECUTED/VERIFIED production, không RESOLVED toàn bộ finding.

### M1-RV-004 — HIGH: export chưa phải certified M2 handoff

- **Files:** ZIP manifests/reports, `src/08_run_canonical_neo4j_parity.py`,
  consumer `src/kge/adapter.py`.
- **Expected:** Parquet + support/exclusions + mapping/config/code hashes +
  run/stage chain + Gate A/G1/G2; Stage 4.18 có database read-back.
- **Actual/evidence:** ZIP thiếu certificates/upstream bindings/sidecars;
  producer xây `neo4j_edges` từ cùng Parquet thay vì đọc database.
- **Root cause:** xác nhận export kiểm tra nội bộ bị mô tả thành database parity;
  chưa biết upstream đầy đủ có tồn tại trên máy producer hay không.
- **Repro:** package JSON missing-evidence fields; `git show e19fe25:src/08_run_canonical_neo4j_parity.py`.
- **Minimal fix:** export đủ chain sau khi inputs hợp lệ; materialize/read-back
  DB riêng từ canonical Parquet; không tự sinh certificate từ ZIP.
- **Regression:** `tests/kg_pipeline/test_m2_snapshot_certification.py` đã chạy;
  DB integration và hai rebuild độc lập còn phải thực hiện sau gates.
- **Blockers/status:** chưa có certified snapshot; M2 production BLOCKED.

### M1-RV-005 — MEDIUM: feasibility của corpus còn chưa được chứng minh

- **Files:** ZIP `snapshots/*.parquet`, `snapshot_boundaries.yaml`,
  `tables/kg_events.parquet`; `configs/kge.yaml`, `configs/protocol_v1.yaml`.
- **Expected:** feasibility outcome-blind trước freeze; không suy luận power từ counts.
- **Actual/evidence:** topology/counts như bảng; append-only additions, scope
  lệch window và ties giữa event slices đã xác nhận trong package JSON.
- **Root cause vs hypothesis:** cấu trúc/counts là quan sát xác nhận; ảnh hưởng
  đến chất lượng KGE/rank/QA/power là rủi ro chưa đo, không gọi là lỗi tất định.
- **Repro:** graph diagnostic script bên dưới.
- **Minimal fix:** sau sửa provenance, audit identity/connectivity/QA feasibility
  bằng protocol đã đăng ký; chỉ chọn dimension 32/64 theo validation/stability/
  alignment được phép. Không tune corpus/cutoff theo drift, RR, H1.
- **Regression:** kiểm corpus diagnostics tái lập; tie handling, support
  aggregation, boundary hash/immutability cần test theo policy đã duyệt.
- **Blockers/status:** chưa có QA gold, frozen boundaries hay G3; không kết
  luận phải tăng data, đổi dimension hoặc đổi số snapshot ngay bây giờ.

## Lộ trình M1 được đề xuất

Các dòng dưới là thứ tự công việc, không phải lệnh tự chạy nhiều stage.
Mỗi stage phải inspect → implement/test → execute → validate → report → STOP.

| Chặng | Việc cụ thể | Điều kiện ra |
|---|---|---|
| Khôi phục bằng chứng | Nhận source originals/approval, raw bytes và Stage 4.3 manifests/reports 108 blocks, retrievals/memberships/body texts, các run upstream của Hương | Hash/lineage kiểm được; giữ Stage 4.3 khóa, không rerun discovery |
| C3 và chính sách | Duyệt field/type/nullability, clock placement/basis, acceptance semantics, canonical identity, support/conflict policy, corpus window/ties | Contract version rõ, không thiếu nguồn clock; schema 17/17 tương thích |
| 4.4–4.6 | Inventory raw/provenance, duplicate/source lineage, corpus filtering | Raw/membership/retrieval audit; Gate A đúng run PASS; exact duplicates giữ mọi source support |
| 4.7–4.9 | Pilot 30–50 theo spec, ontology freeze, versioned identity as-of, extraction span/hash/local cache | Mention → MappingDecision → Claim → exact source text truy ngược được; không full corpus trước pilot gate |
| 4.10–4.12 | Temporal basis, as-of adjudication, append-only FactVersion | Clocks không thay thế nhau; pending/quarantine có reason; parent/revision/support đầy đủ |
| 4.13 | Independent human gold và đánh giá coverage/quality | G2 thực chất, không PASS với zero evaluated; thresholds giữ nguyên đăng ký |
| 4.14 | Freeze code/config/dependencies/local model và main-corpus run | Đúng versions đã qua pilot; immutable cache/manifests; phạm vi được duyệt |
| 4.15–4.16 | KG events + feasibility; boundaries outcome-blind với timestamp ties | Source support khác graph change; scope hợp lệ; deterministic semantic hash, immutable boundary lock |
| 4.17 | Canonical as-of snapshots, mappings, support/exclusions | G1 artifact-backed; đúng known → validity → revision → tombstone → mapping; rebuild/hash hợp lệ |
| 4.18 | Materialize Neo4j từ canonical Parquet và query read-back | Node/edge/temporal equality thật, certificate gắn đúng artifacts; M1 handoff hoàn chỉnh |

**Nút cần quyết định rõ nhất:** nếu `accepted_into_kg_at` được hiểu là thời gian
duyệt thật ở hiện tại thì không được backdate để đi vào snapshot lịch sử.
Phải làm rõ scientific acceptance axis và engineering adjudication clock theo
nguồn có thẩm quyền trước khi triển khai; thêm cột cho đủ schema chưa giải quyết
được bài toán historical replay. Xem hồ sơ [C3](m1_c3_decision_package.md).

Thành phần nên tận dụng từ Hương: cấu trúc export/package, thống kê corpus,
format KG-event/boundary reports, các parser/helper đã được chứng minh qua
review và có thể nối với runner chuẩn. Stage 4.15–4.18 chỉ được đưa vào producer
sau khi đáp ứng guards/contract; không cherry-pick cả hai commit lớn để mở gate.

Nếu upstream khôi phục và chứng minh được, tái sử dụng artifacts phù hợp và
rebuild từ stage đầu tiên bị ảnh hưởng. Nếu chỉ có ZIP, không thể dựng ngược
evidence provenance đáng tin từ hash/IDs; giữ nó cho kiểm tra cấu trúc, báo rõ
blocker và lập phương án recovery/phạm vi thu thập giới hạn để xin duyệt riêng.

## Điều kiện chuyển M2 và bước M2 đầu tiên

Chỉ mở M2 production sau khi loader verified-run chấp nhận canonical M1 run,
W1/Gate A/G1/G2 và yêu cầu Stage 4.18 có bằng chứng đúng artifact; resolved
config/mappings/manifests được khóa. Không tắt verify hoặc đọc ZIP trực tiếp
để vượt gate.

Sau đó, bước M2 đầu tiên là pilot backbone TransE-L2 theo seeds 13/37/101,
dimension chọn trong không gian 32/64 theo quy tắc W2. Kiểm tra persistent
canonical anchors, split fit/holdout, centered Procrustes rank/holdout,
same-snapshot null sáu cặp của hai endpoint với leave-target-out và bucket
policy đã khóa. Khi alignment không hợp lệ phải giữ unavailable; không ép SED+.
Chỉ sau G3 mới mở rộng thí nghiệm theo các stage đã được yêu cầu.

## Kiểm chứng trong lượt này và giới hạn

- Package kiểm lại trên ZIP thật: 10/10 export/replay/hash nhất quán; hai fixture
  regression trên producer Hương vẫn tái hiện lỗi. Không phải scientific PASS.
- Checkout: **43 passed**, một pytz deprecation warning; code G1 **4 passed**,
  verifier ghi rõ CODE_CONFORMANCE_PASS, không cấp G1 khoa học.
- Python thực tế 3.12; chưa xác nhận lại 3.10/3.11 trong lượt này.
- `ruff check src tests scripts`: PASS. `ruff check .`: **FAIL 15 F821** trong
  các thư mục pytest cũ có `example.py` chứa `changed`; không sửa/xóa dữ liệu
  kiểm thử cũ trong lượt review. Không được báo whole-repo Ruff PASS.
- `git diff --check`: FAIL do ba trailing-whitespace lines trong AGENTS.md
  đã có từ trước. Không sửa instructions của người dùng để làm xanh check.
- Lần gọi test đầu dùng sai tên file đã không thu thập test; đã sửa đường dẫn
  và chạy thành công suite nêu trên. Code G1 lần sandbox bị PermissionError ở
  XML temporary output; chạy lại ngoài sandbox thành công, không bỏ check.
- Không chạy acquisition, production stage, extraction/model training hoặc
  Neo4j write; không mở locked_test; không thay protocol/source-lock/decision log.

Tier: audit đọc real artifacts đã chạy và xác minh phạm vi export/topology;
guard code ở mức TESTED. **M1 production EXECUTED/VERIFIED, G1/G2 scientific
certification và M2 handoff vẫn chưa đạt.** Không mark finding RESOLVED.

## Tái hiện và thay đổi của lượt này

Chọn report path mới để giữ các kết quả cũ bất biến:

```powershell
python scripts/audit_m1_downstream_package.py --zip data/evolving_kg_downstream_v2.zip --ref e19fe25d2325a53ebf49ada27cff4692aa1c6638 --report docs/audit/m1_package_recheck_NEW.json
python scripts/audit_m1_graph_readiness.py --zip data/evolving_kg_downstream_v2.zip --report docs/audit/m1_graph_readiness_NEW.json
python -m pytest -q tests/temporal/test_snapshot.py tests/kg_pipeline/test_quality.py tests/kg_pipeline/test_m2_snapshot_certification.py tests/kg_pipeline/test_scientific_gate_guards.py tests/scientific/test_centered_cosine_estimand.py --basetemp .pytest-review-NEW
python scripts/verify_g1.py --ci --code-checks
python -m ruff check src tests scripts
```

Thêm script diagnostic `scripts/audit_m1_graph_readiness.py`, hai JSON bằng
chứng và báo cáo này; bổ sung trạng thái `docs/PROGRESS.md`. Không sửa production
code hoặc tests. Các test nêu trên là existing regression đã chạy, không phải
test mới. Diff của progress: `git diff -- docs/PROGRESS.md`; các file mới còn
untracked. Chưa commit/push; mọi sửa đổi sẵn có của người dùng được giữ nguyên.
