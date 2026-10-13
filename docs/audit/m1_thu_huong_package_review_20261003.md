# Review lại gói dữ liệu và nhánh Thu Hương — 2026-10-03

## Kết luận

Gói ZIP có các file dữ liệu để kiểm tra, đọc được và nhất quán về mặt xuất file.
Cả 10 snapshot khớp physical/semantic hashes được công bố, replay bằng hàm
snapshot của nhánh đang review cho cùng nội dung, và CSV xuất Neo4j khớp node
sets/edge multisets cùng temporal metadata. Những kết quả này bổ sung bằng
chứng đáng kể so với lần chỉ review code.

**Chưa đủ để ghi M1 DONE, mở M2 production hoặc chọn nhánh Thu Hương làm
nhánh chính thay thế trực tiếp.** Nguồn thời gian, mapping as-of, independent
human gold, artifact chain/freeze và Neo4j database read-back chưa được chứng
minh. Hai lỗi temporal/quality còn tái hiện được. Các guard C0–C9 trên nhánh
hiện tại cũng chưa được tích hợp vào nhánh Thu Hương.

Không suy luận rằng artifacts upstream không tồn tại trên máy người sản xuất:
chúng **không có trong gói được cung cấp**. Không suy luận dữ liệu là mock chỉ
vì field `entity_map_version` mang nhãn `v1_mock`.

## Phạm vi và bằng chứng

- Nhánh: `origin/fix/data-pipeline-compliance-cont`.
- Commit đã review: `e19fe25d2325a53ebf49ada27cff4692aa1c6638`.
- Nhánh checkout: `reconcile/pipeline-drift-compliance`, commit
  `6000f3834b62e36cf3239cabe5eb14db5352a2a5`.
- Common base: `05d0eb5736930e6da9e87412e86a2902718d4c57`.
- Đã fetch remote; tip nhánh Thu Hương vẫn là `e19fe25`.
- ZIP: `data/evolving_kg_downstream_v2.zip`, 2.062.932 bytes, 38 entries,
  3.590.766 bytes sau giải nén về mặt kích thước khai báo.
- SHA-256 ZIP:
  `de9b273cec9ca13ba6d629017f83a8d00e4471ff8843d00898e5980c7c2b1161`.
- SHA-256 tài liệu hướng dẫn DOCX:
  `666f7afe09c758b0cea89af8706867282528d4e1db0ac2249d606f4afac23161`.
- Bằng chứng máy đọc được:
  [m1_thu_huong_package_review_20261003.json](m1_thu_huong_package_review_20261003.json).
- Review tĩnh nhánh bổ sung sáu findings an toàn về source-lock, historical
  rerun, orchestration, PASS claims, overwrite helper và hosted model tại
  [phụ lục](m1_thu_huong_branch_safety_supplement_20261003.md).

Review đọc trực tiếp ZIP trong bộ nhớ, không giải nén đè lên run, không chạy
production runner, acquisition, training hoặc Neo4j. Chỉ thực thi hai module
domain thuần `src/temporal/schema.py`, `src/temporal/snapshot.py` và hàm
`evaluate_quality` đã đọc trên commit nêu trên. Hash module domain được lưu
trong JSON. ZIP giữ nguyên hash trước/sau review. Không truy cập locked test.

Tái hiện bằng một đường dẫn report mới, vì script từ chối ghi đè report:

```powershell
python scripts/audit_m1_downstream_package.py --zip data/evolving_kg_downstream_v2.zip --ref e19fe25d2325a53ebf49ada27cff4692aa1c6638 --report docs/audit/m1_package_recheck_NEW.json
python -m ruff check --no-cache scripts/audit_m1_downstream_package.py
```

## Kết quả kiểm tra file

| Snapshot | Cutoff UTC | Dòng fact | Entity | Bộ ba duy nhất | Dòng hỗ trợ lặp bộ ba |
|---|---|---:|---:|---:|---:|
| T01 | 2025-06-01 01:05:48 | 127 | 167 | 121 | 6 |
| T02 | 2025-09-16 20:09:42 | 266 | 343 | 247 | 19 |
| T03 | 2025-12-18 07:29:02 | 398 | 503 | 362 | 36 |
| T04 | 2026-02-27 05:54:13 | 537 | 646 | 483 | 54 |
| T05 | 2026-05-26 03:11:12 | 683 | 787 | 604 | 79 |
| T06 | 2026-08-11 04:23:59 | 824 | 936 | 724 | 100 |
| T07 | 2026-09-06 18:04:24 | 1005 | 1057 | 844 | 161 |
| T08 | 2026-09-07 01:55:05 | 1261 | 1176 | 964 | 297 |
| T09 | 2026-09-07 02:03:22 | 1526 | 1282 | 1084 | 442 |
| T10 | 2026-09-07 02:13:25 | 1803 | 1389 | 1205 | 598 |

Tất cả 10 snapshot: hash vật lý/ngữ nghĩa khớp report; replay rows/hash khớp;
counts/cutoff/path khớp giữa các tài liệu; CSV hashes, node sets/counts và edge
multisets chứa temporal metadata khớp Parquet. Không thấy future-evidence hay
validity violation **theo các timestamp đã lưu**, không thấy fact reference
đứt hoặc field snapshot khác fact store. Đây chưa chứng minh timestamp đầu
vào đúng nguồn hoặc không dùng mapping tương lai.

Các bảng khác:

- Fact store: 1.803 FactVersion IDs duy nhất, 1.205 LogicalFact IDs/bộ ba,
  994 source IDs. Tất cả là `creation`, không có supersedes reference.
- Events: 1.205 `assert`; support IDs bao phủ đủ 1.803 facts, không có ID lạ.
- Filter: 4.745 quyết định = 2.196 include + 2.545 exclude + 4 review.
  Mọi source ID trong fact store đều xuất hiện trong tập include.
- Anchors prelock: 1.389 candidates = 44 HIGH + 351 MEDIUM + 994 LOW.
  Đây chưa phải persistent anchor universe đã khóa cho M2.
- Boundary hash khớp nội dung YAML hiện tại.
- Spans/hash evidence có hình dạng hợp lệ; chưa kiểm được offsets/grounding
  vì thiếu exact body text.

**Đính chính lần review trước:** 10 cutoff có timestamp đầy đủ khác nhau.
Ngày 07/09 trùng ở T08–T10 không đồng nghĩa cutoff trùng. Gói hiện đã cung
cấp hai reports và 10 snapshot Parquet; nhận định thiếu toàn bộ output không
còn áp dụng cho gói này. Các lỗi khoa học bên dưới vẫn còn.

## Findings có bằng chứng

Mọi đường dẫn code/line dưới đây thuộc commit `e19fe25`, không phải phiên bản
đang checkout. Lệnh tái hiện chung ở trên tạo toàn bộ các kiểm tra ghi trong JSON.
Không sửa code producer trong lượt review này; regression đề xuất là công việc
tiếp theo, không phải test đã được thêm vào producer.

### M1-PKG-001 — CRITICAL: thiếu temporal/mapping provenance và lệch contract

- **Components:** ZIP `tables/fact_versions.parquet`; `config/schema.yaml`;
  `src/kg_pipeline/adjudicate.py:39–110`, `adjudication.py:78–117`.
- **Expected:** các clock độc lập, evidence-time basis, mapping availability;
  contract có acceptance/adjudication/support provenance; không lấy acquisition
  làm public evidence time hay tự tạo mapping thiếu căn cứ.
- **Actual/evidence:** 1.803/1.803 facts dùng `v1_mock`, `internal://...`,
  confidence 0.9; thiếu mapping artifact và các clock/basis cần xác minh.
  12 tên field được schema khai báo không có, 7 field thực tế không được khai
  báo; cả schema nhánh Thu Hương và schema checkout đều lệch cùng kiểu này.
  Adjudication lấy retrieval hoặc giờ hiện tại làm observed time, tự hash
  mention thành entity ID, clamp thời gian hiệu lực về observed time.
- **Root cause confirmed:** producer có fallback và contract khác YAML.
  **Unverified:** mỗi timestamp/fact cụ thể đã bị sai bao nhiêu; 1.784 facts
  có valid_from bằng observed time chỉ là dấu hiệu, không tự chứng minh lỗi.
- **Repro:** JSON `facts`, `fact_contract_drift`; đọc source tại lines trên.
- **Minimal fix:** quyết định C3 về clock/schema được duyệt, persist căn cứ
  thời gian và mapping decisions đủ as-of, bỏ fallback, rebuild vào run mới.
- **Regression:** contract round-trip, retrieval không thay evidence, late
  alias và mapping unavailable bị chặn bằng runners thật.
- **Blockers:** policy C3/identity chưa duyệt; thiếu upstream để xác minh.

### M1-PKG-002 — HIGH: thiếu chuỗi chứng nhận bàn giao

- **Components:** ZIP root, `reports/snapshots_integrity_report.json`,
  `downstream_transe_config.yaml`; consumer hiện tại `src/kge/adapter.py`.
- **Expected:** producer manifest, COMPLETED/bindings, sidecars, dependency
  hashes, locked config, Gate A và G1/G2 gắn đúng run/artifact.
- **Actual/evidence:** không có run/stage manifests, sidecars, standalone
  snapshot manifest, gate certificates, input/config/code/mapping bindings.
  Report có embedded snapshot hashes nhưng thiếu dependency bindings; config
  downstream chỉ trỏ path/count/cutoff, không trỏ frozen hashes.
- **Root cause confirmed:** export package chưa chứa hợp đồng chứng nhận.
  **Unverified:** artifacts bổ sung có tồn tại ngoài ZIP hay không.
- **Repro:** JSON `missing_expected_evidence_paths`, các danh sách missing
  bindings và sidecars. M2 mặc định kiểm sidecar tại adapter lines 36–40 và
  kiểm producer/gates khi load run; package này chưa đáp ứng.
- **Minimal fix:** export đúng ArtifactRef chain cùng certificate sau khi
  producer inputs được xác minh; không tự tạo certificate từ hashes trong ZIP.
- **Regression:** sửa dependency, parent FAILED, thiếu sidecar/gate đều bị chặn.
- **Blockers:** Gate A/G1/G2, freeze, upstream artifact verification.

### M1-PKG-003 — CRITICAL: revision được xét trước validity

- **Components:** `src/temporal/snapshot.py:19–65`.
- **Expected:** known/accepted → validity → revision → tombstone → mapping as-of.
- **Actual/evidence:** fixture có fact cũ đang hiệu lực và correction đã biết
  nhưng chỉ có hiệu lực sau cutoff; expected `[audit_old]`, actual `[]`.
  Snapshot cũng chỉ lọc observed time, chưa kiểm acceptance/mapping time.
- **Root cause confirmed:** supersession loại fact cũ trước khi lọc validity.
- **Repro:** JSON `producer_future_effective_regression` = FAIL.
- **Minimal fix:** thực hiện thứ tự đặc tả cùng clocks/mapping đã phê duyệt.
- **Regression:** future-effective correction, late correction/retraction,
  acceptance và mapping sau cutoff; gọi runner thật.
- **Blockers:** contract/identity policy. Gói chỉ có creation nên không tự
  cung cấp chứng minh production cho correction/retraction.

### M1-PKG-004 — CRITICAL: quality gate không chứng minh chất lượng

- **Components:** `src/kg_pipeline/quality.py:17–49,56–136`;
  `src/kg_pipeline/adjudication.py:101–130`.
- **Expected:** independent human gold, đủ coverage, ngưỡng đăng ký và evaluator
  được gọi; chưa đánh giá thì BLOCKED.
- **Actual/evidence:** gọi evaluator với một fact và empty gold trả PASS,
  evaluated_count=0. Runner đọc gold nhưng không gọi evaluator; PASS chỉ dựa
  vào span shape, source prefix và vài chuỗi mock. Prefix `bodyvariant_`
  khiến facts được auto-accept/confidence 0.9.
- **Root cause confirmed:** zero-coverage được quy về error_rate=0 và runner
  bỏ qua evaluator. Confidence này chưa phải empirical accuracy.
- **Repro:** JSON `quality_gate_regression`.
- **Minimal fix:** fail-closed evaluator/coverage/gate binding theo C1; gold
  độc lập và threshold được duyệt trước production.
- **Regression:** empty/unmatched gold và skipped evaluator không thể PASS.
- **Blockers:** package không có gold hoặc quality report độc lập.

### M1-PKG-005 — HIGH: CSV parity chưa phải Neo4j read-back

- **Components:** `src/08_run_canonical_neo4j_parity.py:110–139,180–189`;
  ZIP `reports/parity_report.json` và `neo4j_materialization/`.
- **Expected:** import canonical Parquet, query database rồi so sánh tập/thời gian.
- **Actual/evidence:** producer dựng `neo4j_edges` từ cùng Parquet rows vừa
  xuất CSV; không query database. Report tự mô tả Bolt Query Layer và PASS.
  Review này xác minh CSV thực khớp Parquet, chưa kiểm database.
- **Root cause confirmed:** export parity được dùng làm database parity.
- **Repro:** source lines trên; JSON `neo4j_read_back_performed=false`.
- **Minimal fix:** materialize vào DB thử nghiệm riêng, read-back mọi frozen
  snapshot, certificate bind database/result và Parquet hashes.
- **Regression:** counts bằng nhưng node/edge sets hoặc metadata sai phải FAIL.
- **Blockers:** chưa có database/read-back artifact; không chạy lệnh import
  overwrite database trong tài liệu hướng dẫn.

### M1-PKG-006 — HIGH: boundaries chưa đủ điều kiện freeze

- **Components:** `src/06_run_snapshot_boundaries.py:54–98,105–125`;
  ZIP `snapshot_boundaries.yaml`, `tables/kg_events.parquet`.
- **Expected:** scope được duyệt, tie handling outcome-blind, semantic hash
  tái lập và zero overwrite sau lock.
- **Actual/evidence:** T07–T10 sau 2026-08-31; 952 facts có observed date sau
  mốc này. Đặc tả ghi historical operational window kết thúc ngày đó (line
  109), chưa có amendment mở rộng trong gói. T01/T02/T04/T05/T06 chia giữa
  các event cùng timestamp; số event ngoài slice vẫn <= cutoff lần lượt là
  1/6/1/2/1. Chỉ đổi created_at_real cũng đổi boundary hash; YAML được mở `w`.
- **Root cause confirmed:** quantile theo index; operational clock nằm trong
  hash và YAML không immutable. **Unverified:** eligibility của dữ liệu tháng
  9 và phê duyệt tie policy. Không tự loại dữ liệu hoặc đổi cutoff để hợp thức hóa.
- **Repro:** JSON `events_and_boundaries` và source lines trên.
- **Minimal fix:** giải quyết scope bằng quyết định hợp lệ; khóa tie rule;
  tách semantic/physical hash, immutable boundary lock và transition metadata.
- **Regression:** tied timestamps, same frozen inputs khác wall clock,
  resume không overwrite; transition counts khớp trạng thái thực.
- **Blockers:** scope/tie/freeze policy và transition metadata không có trong ZIP.

### M1-PKG-007 — HIGH: support rows chưa tách khỏi canonical training triples

- **Components:** ZIP facts/events/snapshots; `src/kg_pipeline/adjudication.py:99–115`.
- **Expected:** giữ mọi source support, tách SourceClaim/support aggregation;
  canonical graph và counts có semantics được khóa.
- **Actual/evidence:** T10 có 1.803 rows nhưng 1.205 bộ ba; 598 rows cùng
  triple khác source support. Events đã gom còn 1.205. Facts chỉ tạo creation,
  không nối previous FactVersion store hay persist correction/retraction.
- **Root cause confirmed:** mỗi accepted claim tạo riêng FactVersion; export
  giữ tất cả source rows. **Unverified:** consumer khác có deduplicate trước
  training không. Giữ support rows không phải lỗi tự thân; dùng row count làm
  unique edge count hoặc training lặp gây thay đổi trọng số cần được xử lý.
- **Repro:** JSON `snapshot_checks`, `facts`, `events_and_boundaries`.
- **Minimal fix:** canonical triples riêng, support table truy được claim;
  revision append-only qua verified previous store theo policy C6.
- **Regression:** hai nguồn đồng thuận không thành correction/weighted duplicate;
  late correction/retraction xuyên run giữ lịch sử.
- **Blockers:** support/identity/conflict contract và independent source grouping.

### M1-PKG-008 — MEDIUM: ví dụ trong hướng dẫn không chạy với schema gói

- **Components:** DOCX trong `data/`; ZIP snapshots và anchors prelock.
- **Expected:** ví dụ dùng đúng contract và coi anchors prelock là candidates.
- **Actual/evidence:** ví dụ chọn `head_entity_id/relation/tail_entity_id`,
  file thực là `subject_id/relation_id/object_id`; chọn `feasibility_tier`,
  file thực là `feasibility_status`. HIGH candidates chưa có persistent-anchor
  lock hoặc alignment/null chứng nhận.
- **Root cause confirmed:** hướng dẫn và schema khác nhau.
- **Repro:** JSON `guide_triple_columns_missing`, `anchors`.
- **Minimal fix:** cập nhật tài liệu theo contract đã duyệt, chỉ hướng dẫn M2
  đọc verified frozen bundle; không sửa thuật toán M2 trong review này.
- **Regression:** smoke test đoạn ví dụ sau khi consumer contract hoàn tất.
- **Blockers:** final handoff chưa được chứng nhận.

### M1-PKG-009 — GOVERNANCE: source locks đã đổi, approval chưa xác minh

- **Components:** `configs/protocol_v1.yaml`, `data/manifests/sources.lock.json`,
  `decisions/decision_log.jsonl` trên nhánh Thu Hương.
- **Expected:** giữ locked originals và chỉ đổi bằng amendment được duyệt.
- **Actual/evidence:** diff từ common base thay hai SHA-256 execution plan và
  patch ở cả protocol/lock; decision log cũng thay đổi. Không có originals
  hoặc amendment chứng minh phê duyệt trong gói.
- **Root cause confirmed:** Git diff chứa thay đổi locks.
  **Unverified:** ai phê duyệt, lý do, file nguồn có đúng bytes hay không.
- **Repro:** `git diff 05d0eb5 e19fe25 -- configs/protocol_v1.yaml data/manifests/sources.lock.json decisions/decision_log.jsonl`.
- **Minimal fix:** đối chiếu originals với locked hashes và approval trail;
  không tự cập nhật master spec/source-lock theo output để hợp thức hóa.
- **Regression:** W1 kiểm exact bytes và amendment chain.
- **Blockers:** original sources/approved amendment chưa được cung cấp.

### M1-PKG-010 — HIGH: chuỗi giống credential đã được ghi trong Git

- **Components:** `docs/PROGRESS.md:139` trên nhánh Thu Hương.
- **Expected:** execution notes không chứa credentials; secret phải nằm ngoài Git.
- **Actual/evidence:** một chuỗi dạng `sk-...` dài 35 ký tự trong tài liệu;
  giá trị không được chép lại trong report hoặc output audit. Có thêm 11
  control characters không phải tab/newline trong file.
- **Root cause confirmed:** chuỗi được commit trong tài liệu.
  **Unverified:** chuỗi có phải secret thật, còn hiệu lực hay không; không
  thử gọi dịch vụ để kiểm tra.
- **Repro:** quét regex `sk-[A-Za-z0-9_-]{20,}` trên `git show e19fe25:docs/PROGRESS.md`,
  chỉ in đường dẫn/line/length và che toàn bộ giá trị.
- **Minimal fix:** owner xác định secret; nếu là thật thì thu hồi/rotate,
  gỡ khỏi nội dung mới và đánh giá xử lý Git history riêng với cộng tác viên.
- **Regression:** secret scan trong code checks, không log secret.
- **Blockers:** xác nhận owner; không rewrite shared history trong lượt review.

### M1-PKG-011 — HIGH: chưa tích hợp safety guards và coverage cần thiết

- **Components:** nhánh `fix/data-pipeline-compliance-cont`; các paths
  `src/kg_pipeline/contract_authority.py`, `src/kg_pipeline/locked_mode.py`;
  `tests/test_entity_mapping.py`, `tests/test_fact_schema.py`, `tests/test_protocol.py`.
- **Expected:** verified artifact chain, machine contract và locked execution
  guards cùng regression coverage trước khi chọn baseline production.
- **Actual/evidence:** hai module guard đang có trên checkout không có ở tip
  Thu Hương; ba test files nêu trên đều 0 bytes. Hai lỗi PKG-003/004 còn tái
  hiện; data export không thay thế regression coverage.
- **Root cause confirmed:** nhánh chưa tích hợp các remediation sau common
  base. **Unverified:** toàn suite của nhánh Thu Hương; không gọi các test
  khác là không tồn tại hay failing chỉ vì ba file này rỗng.
- **Repro:** `git ls-tree -rl e19fe25 -- tests/test_entity_mapping.py tests/test_fact_schema.py tests/test_protocol.py`;
  đối chiếu tree guard paths và chạy hai reproductions trong script audit.
- **Minimal fix:** tích hợp thay đổi theo contract đã duyệt, giữ guard C0–C9;
  review các path thay đổi ở cả hai nhánh trước merge, không thay checkout
  hiện tại trực tiếp bằng nhánh Thu Hương.
- **Regression:** runner integration, late mapping/revisions, tampering,
  scientific gate refusal, independent frozen rebuild và DB parity.
- **Blockers:** C3/semantic approvals và toàn bộ scientific evidence bên trên.

## Verification tiers và hành động đã làm

| Scope | IMPLEMENTED | TESTED | EXECUTED | VERIFIED |
|---|---|---|---|---|
| Tool đọc ZIP và đối chiếu artifact | Có | Chạy trên gói cung cấp | Không chạy production stage | Hash/rows/CSV trong phạm vi gói đã đối chiếu |
| Hai reproduction temporal/quality | Không patch producer | Đã tái hiện fixture FAIL/false PASS | Không | Chưa xác minh correctness production |
| Gate A/G1/G2, frozen handoff, DB parity | Không | Không chứng nhận bằng fixture | Không thực thi | BLOCKED |

Script audit qua Ruff. `ruff check --no-cache .` của checkout hiện tại trả
exit 0, có cảnh báo Access denied ở các thư mục temporary cũ; không phải kết
quả lint/test của toàn nhánh Thu Hương. Không chạy lại toàn suite producer.

Đã thêm `/data/*.zip` và `/data/*.docx` vào `.gitignore`; cả ZIP và guide được
kiểm tra là ignored. Không đổi bytes của dữ liệu, AGENTS.md, scientific locks
hoặc decision log; không checkout/merge/commit/push trong lượt này.

Ba lineage samples trong JSON nối được fact → filter include → snapshot;
đoạn source → exact text/hash/span/claim vẫn BLOCKED. Chưa đáp ứng kiểm tra
lineage production từ source tới snapshot.

## Đầu vào còn cần để review production đầy đủ

Cần export upstream bundle của đúng run cùng manifests/hash bindings:
immutable raw/body, memberships/retrievals/public URLs, claims/spans/text
versions, mapping decisions/availability, adjudication decisions/clock basis,
originals/approval trail, resolved config/environment/cache, human gold và
quality evaluation, Gate A/G1/G2, frozen boundary/transition metadata,
snapshot support/exclusions và Neo4j read-back. Không thay lịch sử acquisition
bằng refetch và không tự tạo provenance từ mtime.

Trước khi chọn baseline chính, giải quyết findings/semantic approvals,
tích hợp guard C0–C9 theo diff có chọn lọc rồi reprocess vào run mới ở các
stage được cho phép. Mỗi production stage vẫn phải có PASS và yêu cầu tiếp
tục riêng. ZIP này được giữ làm evidence đối chứng, chưa là frozen input M2.
