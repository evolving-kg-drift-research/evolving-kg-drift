# Yêu cầu nghiệm thu và bàn giao M1 → M2

Ngày cập nhật: 14/10/2026.

**M1 chỉ đạt yêu cầu bàn giao chính thức khi dữ liệu được xác minh trên artifacts
thật, các gate liên quan đạt PASS và Stage 4.18 đạt PASS.** Có file Parquet,
unit tests xanh hoặc chạy được TransE chưa đủ để chứng nhận data-ready.

Tài liệu này tổng hợp yêu cầu hiện hành, không phê duyệt scientific policies,
không thay đổi protocol và không cấp phép chạy production stages. Tham số,
population và semantics vẫn theo [protocol](../configs/protocol_v1.yaml) cùng
[source lock](../data/manifests/sources.lock.json). Quy trình M1 theo
[đặc tả pipeline](data_pipeline_spec.md), ranh giới module theo
[kiến trúc](architecture.md) và [modules](modules.md).

## 1. Phạm vi bàn giao

M1 chịu trách nhiệm biến nguồn và bằng chứng thành canonical temporal snapshots
có provenance, mapping và thời gian kiểm chứng được. M2 nhận snapshots đã được
chứng nhận để huấn luyện TransE-L2, sau đó alignment và đo drift.

Canonical Parquet là nguồn dữ liệu chuẩn. Neo4j là lớp materialization/query.
M2 đọc Parquet trực tiếp và không tự dựng snapshot riêng, tự diễn giải lại tin
tức hoặc tự sửa entity identity để dùng cho training.

Gói nhận trực tiếp của M2 gồm **snapshots + entity/relation mappings + manifests
và hashes**. Hồ sơ provenance và nghiệm thu phải đi kèm hoặc được tham chiếu
tới kho immutable có thể truy cập, kiểm tra và đối chiếu hash.

## 2. Điều kiện nghiệm thu M1

| Mã | Yêu cầu | Bằng chứng cần kiểm tra |
|---|---|---|
| H01 | Nguồn, config và schema hợp lệ | Source lock được xác minh; baseline/config được duyệt; bảng đúng schema, types, PK/FK và nullability; Gate A PASS gắn đúng run/inputs. |
| H02 | Facts có evidence đầy đủ | Truy được fact → supporting claim → source/body → exact evidence span; offsets hợp lệ, hash đoạn khớp đúng text representation/version; thiếu grounding phải quarantine hoặc block. |
| H03 | Canonical identity và mapping hợp lệ | Có canonical registry, mapping decisions, basis, version, lịch sử và `mapping_available_at`; aliases/conflicts xử lý theo policy được duyệt. Hash tên thực thể không tự chứng minh canonical identity. |
| H04 | Temporal integrity — G1 | Không future evidence/mapping; snapshot dùng đúng cutoff, validity và revision/retraction rules; acceptance clock có contract/basis được duyệt; kiểm chứng trên real artifacts. |
| H05 | Evidence/entity quality — G2 | Gold/reference độc lập; procedure và thresholds được duyệt/khóa theo lịch pilot; báo cáo chất lượng có artifacts, sample/population và kết quả từng tiêu chí. |
| H06 | Snapshots được khóa đúng phạm vi | Snapshot IDs, cutoffs, window và boundary policy được khóa; lựa chọn outcome-blind; mappings và required temporal metadata có đầy đủ. |
| H07 | Tái tạo xác định | Cùng inputs, config, mappings và component versions tạo output hash giống nhau; có báo cáo rebuild đối chiếu hashes, không ghi đè run cũ. |
| H08 | Parquet–Neo4j parity thật | Đọc lại database thực tế; tập node/edge bằng canonical Parquet; row/entity/relation counts khớp; snapshot hashes được ghi và downstream config tham chiếu frozen hashes. |
| H09 | Hồ sơ kết thúc Stage 4.18 | Required inputs/outputs, schema, invariants, referential integrity, provenance và stage-specific checks đạt; Stage 4.18 report PASS với evidence references. |

### 2.1. Những kiểm tra thời gian bắt buộc

- `evidence_observed_at <= snapshot_cutoff`.
- `mapping_available_at <= snapshot_cutoff`.
- Giữ riêng world validity (`valid_from`, `valid_to`), evidence observation
  (`evidence_observed_at`) và project acquisition (`retrieved_at_real`,
  `ingested_at_real`); không dùng trục này thay trục kia.
- Kiểm tra future-effective changes, late corrections, retractions/tombstones
  và revision chains theo contract đã duyệt.
- Raw, retrievals và FactVersion store append-only; snapshots và artifacts
  lịch sử không bị ghi đè. Run mới có version và supersession lineage.

### 2.2. Những kiểm tra chất lượng bắt buộc

Theo Stage 4.13, đo tối thiểu entity-linking accuracy, relation precision/recall,
temporal-field accuracy, evidence-span validity, conflict/pending behavior và
source-copying cases. G2 còn cần hồ sơ QA feasibility/hash theo gate hiện hành.

Không tự đặt ngưỡng số để nghiệm thu. Threshold phụ thuộc dữ liệu phải được
xác lập và khóa từ pilot theo procedure được duyệt. Vi phạm invariant thuộc
zero-tolerance phải FAIL. Diagnostic sample không tự trở thành gold; loss/MRR
của TransE không thay thế kiểm định chất lượng M1.

## 3. Những gì cần bàn giao

| Thành phần | Nội dung tối thiểu | Bên nhận sử dụng |
|---|---|---|
| Canonical snapshots dạng Parquet | Snapshot ID/cutoff, triples theo schema, metadata thời gian bắt buộc; toàn bộ snapshots thuộc phạm vi đã khóa. | M2 dùng trực tiếp làm input; M3/M4 dùng graph theo cùng snapshot. |
| Entity/relation mappings | Canonical IDs, ontology/relation version, mapping history và decisions có basis/availability; hash mappings. Mapping sang chỉ số training phải xác định và được ghi nhận. | M2 bảo đảm ánh xạ IDs nhất quán giữa seeds và truy vết qua snapshots. |
| Snapshot manifests và hashes | Hash file/graph theo contract, counts, cutoff, builder version, references/hashes của fact store, mapping, config và các dependencies bắt buộc. | Kiểm tra input không đổi và dependency lineage. |
| Run/stage manifests | Run ID/parent lineage, producer commit, dirty state và patch khi applicable, resolved config/hash, component versions, input/output ArtifactRefs/hashes. | Truy đúng producer, tái tạo và audit. |
| FactVersion store | Lịch sử append-only, support/revision links, temporal fields và adjudication provenance theo schema đã duyệt. | Kiểm chứng triple từ đâu đến và vì sao được chọn ở cutoff. |
| Claims, evidence và nguồn | Claims/support links, exact spans/hashes, body/raw artifacts, source IDs/URLs và acquisition receipts/logs. Có thể tham chiếu kho immutable đã xác minh thay vì sao chép toàn bộ. | Truy vết nội dung và bằng chứng thời gian. |
| Hồ sơ quality/gates | Gate A/G1/G2 gắn đúng run và inputs; independent gold/procedure/threshold references, quality results và QA feasibility evidence. | Xác nhận điều kiện scientific handoff. |
| Determinism và parity reports | Rebuild hash comparison; actual Neo4j read-back, node/edge set equality và counts; snapshot identity của mỗi kiểm tra. | Kiểm chứng H07/H08. |
| Exclusions/quarantine và limitations | Records có lý do loại/pending, conservation accounting, unresolved findings và ảnh hưởng phạm vi. | Không silently drop dữ liệu hoặc che blockers. |
| Hướng dẫn tái tạo và báo cáo bàn giao | Phiên bản môi trường/dependencies, cách đọc input và chạy checks, phạm vi, artifact inventory/hashes, Stage 4.18 PASS report. | Bên nhận kiểm tra độc lập mà không cần hidden local state. |

Các yêu cầu manifest phải theo schema tương ứng, gồm
[experiment manifest schema](../configs/schemas/experiment_manifest.schema.yaml)
cho artifacts thuộc contract đó. Không điền synthetic hashes, timestamps hoặc
producer commit suy đoán vào trường provenance đang thiếu.

Data và outputs đang được ignore trong Git cần được bảo quản và bàn giao riêng;
push code lên GitHub không đồng nghĩa đã bàn giao những artifacts này.

## 4. Checklist bên nhận xác nhận

- [ ] Có inventory của gói bàn giao, run ID, versions và phạm vi snapshot/cutoff.
- [ ] Có đủ artifacts hoặc references truy cập được; hashes/schema/counts khớp.
- [ ] Truy được dependency lineage và nguồn bằng chứng; không có placeholder
  chưa giải quyết trong contract/config cần thiết cho bước được mở.
- [ ] Gate A/G1/G2 có kiểm định artifact-backed hợp lệ cho đúng run/inputs.
- [ ] Evidence spans và entity mapping-as-of đã được xác minh.
- [ ] Independent quality evaluation đạt tiêu chí được duyệt.
- [ ] Deterministic rebuild và actual Parquet–Neo4j parity đạt.
- [ ] Stage 4.18 report PASS; không còn blocker ngăn bàn giao chính thức.
- [ ] M2 certified loader đọc được canonical snapshots và xác minh dependencies.
- [ ] Owner M1 và bên nhận M2 review interface, phạm vi và limitations.

[M2 adapter](../src/kge/adapter.py) hiện yêu cầu run, canonical manifests và
artifact-backed G1/G2 PASS certificates; canonical validation còn kiểm Gate A
và producer lineage. Không dùng loader diagnostic hoặc legacy runner để thay
cho certified handoff.

M1 được nghiệm thu là điều kiện dữ liệu cho M2. Trước training chính thức vẫn
phải hoàn tất các lựa chọn/config M2 cần khóa theo protocol, gồm TransE-L2,
seeds 13/37/101 và dimension theo đúng lịch freeze; dimension 32 của thử legacy
không tự trở thành dimension production.

## 5. Mức xác nhận phải ghi trong báo cáo

| Mức | Ý nghĩa |
|---|---|
| IMPLEMENTED | Code/schema/guard đã được viết. |
| TESTED | Unit/fixture/contract tests đã chạy và đạt trong môi trường ghi nhận. |
| EXECUTED | Stage đã chạy trên dữ liệu thật có artifacts/provenance. |
| VERIFIED | Kiểm định độc lập trên real artifacts/manifests/invariants đã đạt trong phạm vi ghi rõ. |

Unit tests, CI xanh hoặc exit code 0 không tự chứng nhận scientific gate PASS.
Mỗi kết luận cần ghi phạm vi, thời điểm, inputs và mức xác nhận đã đạt.

## 6. Trạng thái bộ v3 tại ngày 14/10/2026

**M1 → M2 production: BLOCKED.** Kết quả thử TransE T01 đã lưu vẫn là legacy,
không phải chứng nhận bộ v3 đủ điều kiện cho nghiên cứu chính thức.

| Blocker | Bằng chứng/trạng thái hiện có |
|---|---|
| Evidence-span binding | 1.803 fact hashes bind whole body; chỉ 15 exact spans khớp, 1.788 không khớp. Đây là lỗi binding, không phải tỷ lệ fact đúng/sai. |
| Canonical mapping-as-of | Chưa có registered canonical mapping/availability; diagnostic mention links không thay mapping production. |
| Producer và temporal basis | Chưa xác minh actual v3 producer run/commit, approved production binding và đầy đủ basis observation/acceptance. |
| Schema/source/config authority | C3 còn BLOCKED với 9/17 bảng lệch public contract; authority và approved baseline còn blockers. |
| Window/boundaries | T07–T10 vượt window kết thúc 31/08/2026 hiện hành; chưa có amendment cho việc mở rộng này. |
| Quality/G2 | Chưa có independent gold, approved thresholds và kiểm định chất lượng đủ để chứng nhận. |
| Neo4j parity | CSV export comparison chưa phải actual database read-back/set equality của Stage 4.18. |
| Công cụ scientific nghiệm thu | `evaluate_scientific_gate` hiện fail-closed với `SCIENTIFIC_EVALUATOR_UNAVAILABLE`; G1/G2 không thể được mở chỉ bằng tự viết JSON PASS. |

Recovery đã xác minh 4.745 body hashes, 5.271 strict receipt references và 30
sample raw blobs. Kết quả này phục hồi một phần evidence; chưa chứng nhận toàn
bộ raw corpus, temporal semantics, canonical identity hay quality gates.

Hồ sơ chi tiết: [PROGRESS](PROGRESS.md),
[quy trình legacy T01](QUY_TRINH_THU_TRANSE_LEGACY_T01.md),
[phạm vi remediation v3](audit/V3_REMEDIATION_SCOPE_20261014.md) và
[bảng quyết định](audit/V3_DECISION_TABLE_20261014.md). Hai hồ sơ đề xuất sau
vẫn REVIEW REQUIRED; nội dung tài liệu này không biến chúng thành approval.

## 7. Trình tự tiến tới bàn giao

1. Giải quyết evidence/dependencies và duyệt các contract, identity, temporal,
   support, quality, window policies cần thiết theo bảng quyết định.
2. Hoàn thiện công cụ kiểm định production bằng real artifacts, giữ nguyên
   fail-closed guards trong khi chưa đủ bằng chứng.
3. Nếu cần reprocess, tạo run/version mới; xác định stage sớm nhất bị ảnh hưởng.
   Không sửa đè v3 hoặc historical facts/hashes/timestamps.
4. Thực hiện từng stage theo thứ tự inspect → plan → implement → test → execute
   → validate → Stage Report → STOP. Chỉ mở stage tiếp khi stage trước PASS và
   có yêu cầu rõ ràng; không rerun Stage 4.3 historical acquisition đã khóa.
5. Sau Stage 4.18 PASS và các gate cần thiết được chứng nhận, đóng gói inventory,
   artifacts, manifests và reports; bên nhận kiểm tra checklist mục 4.
6. Mở training TransE-L2 chính thức theo config M2 đã khóa và user request.

Không dùng drift/MRR/QA outcomes để chọn lại corpus, cutoffs, mappings hoặc
upstream policies nhằm cải thiện kết quả downstream.
