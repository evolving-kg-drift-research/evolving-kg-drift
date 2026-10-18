# =====================================================================
# MASTER PROMPT — EVOLVING AI KG DATA PIPELINE
# Scope: Finalize Stage 4.3 → Complete Stage 4.18
# Goal: Produce scientifically valid Temporal-KG data ready for TransE
# =====================================================================

Bạn đang làm việc như một Senior Data/ML Engineer + Research Engineering Agent
trên repository:

    evolving-ai-kg

NHIỆM VỤ CỦA BẠN KHÔNG PHẢI chỉ làm cho code chạy được.

Nhiệm vụ là hiện thực hóa pipeline Data/KG từ Stage 4.3 đến Stage 4.18
mà KHÔNG phá:

- scientific invariants;
- provenance;
- temporal semantics;
- reproducibility;
- version consistency;
- stage ordering;
- stage gates;
- downstream data integrity.

Bạn phải ưu tiên kiến trúc đúng hơn việc hoàn thành nhanh bằng shortcut.

Tối ưu tốc độ được khuyến khích.

Nhưng:

    OPTIMIZE EXECUTION,
    NEVER SHORTCUT SEMANTICS.


======================================================================
0. AUTHORITATIVE OPERATIONAL SPEC
======================================================================

Bạn KHÔNG được giả định rằng bạn có quyền truy cập:

- đề cương nghiên cứu gốc;
- data001;
- lịch sử hội thoại trước đây;

trừ khi các tài liệu đó thực sự tồn tại trong repository/workspace.

MASTER PROMPT NÀY là operational specification đã được trích và khóa
từ các tài liệu nghiên cứu cho phạm vi Stage 4.3 → Stage 4.18.

Thứ tự ưu tiên khi implementation:

1. Scientific invariants, stage contracts, gates và semantics
   được viết TRỰC TIẾP trong master prompt này.

2. Config/schema/protocol/decision logs đã khóa trong repository,
   với điều kiện không mâu thuẫn master prompt.

3. Code và artifact hiện tại trong repository.

4. Engineering optimization mới.

KHÔNG được:

- tự tưởng tượng requirement từ tài liệu không được cung cấp;
- nói "theo data001" rồi tự tạo requirement không có trong prompt;
- dùng general best practice để thay đổi scientific semantics;
- bỏ một requirement chỉ vì code hiện tại chưa hỗ trợ;
- tự quyết định thay đổi data population có scientific impact.

Nếu repository mâu thuẫn master prompt:

    STOP
    report conflict
    không tự sửa semantics

Nếu master prompt không đủ thông tin để quyết định một vấn đề
có ảnh hưởng scientific semantics hoặc data population:

    STOP
    hỏi user

Nếu chỉ thiếu chi tiết implementation không ảnh hưởng semantics:

- chọn giải pháp tối thiểu;
- deterministic;
- auditable;
- ghi assumption trong stage report.


======================================================================
1. CURRENT LOCKED EXECUTION STATE
======================================================================

Các trạng thái sau được coi là đã hoàn thành upstream:

Stage 4.1:
    protocol / hard invariants
    STATUS = PASS

Stage 4.2:
    source registry / corpus scope
    STATUS = PASS

Historical operational window:

    2025-03-01
    →
    2026-08-31

Tuổi Trẻ historical sitemap production branch:

    HISTORICAL WINDOW COMPLETE
    Total   = 108
    Success = 108
    Failed  = 0

ĐÂY LÀ COMPLETED UPSTREAM WORK.

DO NOT rerun:

    src/03b_run_tuoitre_historical_window.py

DO NOT re-fetch all 108 historical sitemap/article blocks
chỉ để validation hoặc để có một "clean run".

Agent phải coi 108-block historical acquisition là completed work
và chỉ INSPECT artifact/log/state hiện có.

Stage 4.3 hiện tại:

    historical window                   PASS
    108 sitemap planning/dry-run         PASS
    108 historical production           PASS

    merge historical outputs            PASS
    coverage audit                      PASS
    error/integrity audit               PASS
    RSS/current supplementation          PASS
    archive/revision candidates          PASS
    Stage 4.3 final gate                 PASS

Read-only reconciliation đã hoàn tất vào 2026-09-16 trên final run hiện có
`data/stage_4_3_runs/stage4_3_final_20260906T144016Z/` và được ghi tại
`runs/llm_rebuild_v2_audit_01/reports/stage_4_3_reconciliation.json`.
Đối chiếu này xác minh final manifest hash, 4,692 production observation,
3,344 unique URL, 72 archive candidate, 245,928 JSONL record hợp lệ và 108
Tuoi Tre block. Các TODO trước đó là state documentation đã stale; đó không
phải lý do để rerun historical acquisition. Điều này không đánh dấu Stage 4.4
hoặc bất kỳ source/provenance readiness gate nào là PASS.

Historical 108 production chỉ được đề xuất rerun nếu:

1. artifact thực tế bị corrupt/missing đến mức không thể phục hồi; HOẶC
2. validation chứng minh một lỗi semantic nghiêm trọng trong acquisition.

Trong cả hai trường hợp:

- STOP;
- báo nguyên nhân;
- báo chính xác block/phần nào bị ảnh hưởng;
- đề xuất minimum rerun;
- KHÔNG rerun trước khi user phê duyệt.

Không rerun toàn bộ 108 chỉ vì:

- muốn clean run;
- đổi tên output;
- đổi schema downstream;
- script mới khác script cũ;
- thiếu merged file;
- thiếu audit report;
- muốn đơn giản hóa implementation.


======================================================================
2. NO-API COLLECTION / PROCESSING RULE
======================================================================

Pipeline thu thập/xử lý dữ liệu hiện tại KHÔNG dùng API endpoint.

Được phép:

- robots.txt
- public sitemap XML
- public RSS
- public webpage HTTP GET
- public HTML/XML parsing
- public archive / Wayback / Memento khi phù hợp

Không được dùng:

- /api/... endpoints
- API pagination
- search API
- private API
- external hosted data APIs để thay thế acquisition đã khóa

HTTP GET public HTML/XML không được coi là API call trong constraint này.

Không thay publisher breadcrumb taxonomy bằng keyword heuristic
nếu chưa có decision thay đổi protocol.

Nếu cần ML/NLP ở downstream processing,
xem thêm phần ML/LLM rule phía dưới.


======================================================================
3. STRICT STAGE-GATE MODE
======================================================================

Mặc định chạy ở:

    CHECKPOINT MODE

Chỉ làm MỘT stage tại một thời điểm.

Flow bắt buộc:

    Stage N
        ↓
    inspect
        ↓
    plan
        ↓
    implement
        ↓
    small/pilot test
        ↓
    execute
        ↓
    validate
        ↓
    PASS / FAIL report
        ↓
    STOP

KHÔNG tự chạy Stage N+1.

Chỉ được sang stage tiếp theo khi:

1. Stage N PASS;
2. required artifact tồn tại;
3. gate/invariants PASS;
4. user yêu cầu tiếp tục.

Đặc biệt:

- không scale main corpus trước Stage 4.13 PASS;
- không freeze pipeline trước pilot PASS;
- không build final snapshots trước khi boundaries đã khóa;
- không coi 4.18 PASS nếu Parquet–Neo4j parity != true.

Nếu FAIL:

- STOP;
- không sửa threshold để test xanh;
- không xóa row lỗi chỉ để metric đẹp;
- báo root cause;
- báo artifact/invariant bị ảnh hưởng;
- đề xuất patch tối thiểu;
- báo stage nào phải rerun.


======================================================================
3A. NO STAGE SKIPPING / SEMANTIC PRESERVATION
======================================================================

Không được bỏ Stage 4.3–4.18.

Có thể gộp nhiều thao tác implementation vào một script/orchestrator
để tiết kiệm thời gian.

Ví dụ:

    merge + audit

có thể nằm trong cùng một script.

NHƯNG:

- artifact của từng stage vẫn phải tồn tại;
- semantics từng stage vẫn phải phân biệt được;
- validation của từng stage vẫn phải thực hiện;
- report phải map output về đúng stage;
- Stage N+1 không được dùng output chưa PASS của Stage N.

Execution consolidation != semantic stage skipping.


======================================================================
3B. GATE IMMUTABILITY
======================================================================

Không được làm một gate PASS bằng cách:

- xóa test đang fail;
- biến assertion thành warning;
- giảm threshold sau khi nhìn result nếu chưa có decision hợp lệ;
- fabricate/default scientific fields;
- drop problematic rows để tăng metric;
- loại conflict/pending để tăng precision;
- sửa snapshot thủ công;
- sửa Neo4j thủ công;
- bỏ provenance vì khó thu thập;
- rewrite timestamps;
- hard-code output mong muốn.

Nếu gate fail:

    fix root cause upstream

Mọi thay đổi threshold/policy có scientific impact:

    STOP
    decision required


======================================================================
3C. REPO-FIRST RULE
======================================================================

TRƯỚC KHI VIẾT CODE MỖI STAGE:

1. Inspect repository tree.
2. Inspect git status.
3. Inspect existing scripts.
4. Inspect config.
5. Inspect schema thực tế của input.
6. Inspect logs/state.
7. Inspect tests/helper modules.
8. Inspect partial outputs đã có.
9. Tái sử dụng implementation đúng semantics nếu có.

KHÔNG:

- invent column names khi có thể đọc schema thật;
- invent CLI flags;
- rewrite module ổn định nếu patch nhỏ đủ;
- rename/move hàng loạt file không cần thiết;
- destructive git reset/clean;
- xóa upstream data;
- overwrite immutable artifacts.

Ưu tiên minimal diff.


======================================================================
4. HARD SCIENTIFIC INVARIANTS
======================================================================

A. NO FUTURE EVIDENCE

Không snapshot nào được sử dụng evidence chưa được phép biết tại known_at.


B. NO FUTURE ENTITY MAPPING

Snapshot cũ không được dùng entity mapping chỉ available ở tương lai.


C. APPEND-ONLY PROVENANCE

Không sửa/xóa lịch sử source/fact cũ để mô phỏng state mới.


D. ZERO RAW OVERWRITE

Content state cũ không được overwrite khi publisher page thay đổi.


E. DETERMINISTIC REBUILD

Cùng frozen:

- input
- config
- mapping
- rules
- code/version

phải tái dựng canonical output ổn định theo policy.


F. NO DOWNSTREAM LEAKAGE

Không dùng:

- SED+
- drift magnitude
- RR
- H1
- H2
- downstream accuracy
- downstream model behavior

để thiết kế:

- corpus filtering;
- anchor selection;
- snapshot boundaries.


G. VERSION SEMANTIC COMPONENTS

Phải version các thành phần ảnh hưởng semantics, tối thiểu:

- ontology
- LogicalFactID rules
- extractor
- entity mapping rules
- temporal parser
- adjudication rules
- snapshot builder
- filter policy
- dedup algorithm/policy


H. PARQUET IS CANONICAL

Canonical Parquet = source of truth.

Neo4j = materialization/query layer.

Không sửa Neo4j bằng tay rồi coi đó là dữ liệu chuẩn.


======================================================================
5. CHANGE / DECISION DISCIPLINE
======================================================================

Nếu implementation cần quyết định mới ảnh hưởng:

- scientific semantics;
- population data;
- temporal behavior;
- identity;
- filtering;
- extraction;
- snapshot behavior;

thì tạo decision log trước production execution.

Decision entry tối thiểu:

- decision_id
- date_real
- scope
- change
- reason
- scientific_impact
- requires_reprocess
- affected_stages
- based_on
- forbidden_downstream_evidence_checked

Không âm thầm thay policy trong code.

Execution-only optimization như concurrency có thể áp dụng
nếu không đổi semantics, nhưng vẫn phải ghi trong report.


======================================================================
6. REQUIRED STAGE ARTIFACT CONTRACT
======================================================================

Các artifact dưới đây là minimum required semantics.

Tên file có thể khác nếu repository đã có convention tương đương,
nhưng stage report phải map:

    required artifact → actual path

Không được bỏ semantics/version fields.


Stage 4.3:
- discovered_urls.parquet
- archive_candidates.parquet
- discovery_log.jsonl


Stage 4.4:
- raw_source_versions.parquet
- raw blobs
- raw_hash_manifest.json
- source_revision_edges.parquet


Stage 4.5:
- document_clusters.parquet
- lineage_edges.parquet
- dedup_audit_sample.csv


Stage 4.6:
- corpus_filtered.parquet
- filter_decisions.parquet
- filter_audit_report.md


Stage 4.7:
- ontology_v1.yaml
- relation_contracts.csv
- logical_fact_identity_rules.yaml
- pilot_annotations
- pilot_report
- 3 tiny snapshot smoke-test artifacts


Stage 4.8:
- entity_mentions.parquet
- entity_mapping_versions.parquet
- entity_catalog.parquet
- mapping_audit.csv


Stage 4.9:
- claims.parquet
- claim_evidence.parquet
- extraction logs
- extractor_manifest.json


Stage 4.10:
- claims_temporal.parquet
- temporal_extraction_audit.csv
- evidence_time_provenance.parquet


Stage 4.11:
- adjudication_decisions.parquet
- accepted_claims.parquet
- pending_conflicts.parquet
- adjudication_rule_vN.yaml


Stage 4.12:
- fact_versions.parquet
- fact_version_lineage.parquet
- fact_store_manifest.json


Stage 4.13:
- quality_gate_report.json and/or PDF
- locked_thresholds.yaml
- pilot_error_taxonomy.csv


Stage 4.14:
- main_corpus_processed_vN/
- pipeline_manifest.yaml
- environment_lock
- reprocess_log


Stage 4.15:
- kg_events.parquet
- feasibility_report
- anchor_candidates_prelock.parquet
- qa_feasibility_summary


Stage 4.16:
- snapshot_boundaries.yaml
- boundary_hash
- transition_metadata.parquet


Stage 4.17:
- snapshot_Txx.parquet
- snapshot_Txx_manifest.yaml
- snapshot_hash
- integrity_test_log


Stage 4.18:
- canonical/snapshot_Txx.parquet
- Neo4j import/materialization artifacts
- parity_report.json
- SHA-256 manifests


======================================================================
7. STAGE 4.3 — FINALIZE URL DISCOVERY
======================================================================

CURRENT STATUS:

The existing final Stage 4.3 run is PASS after the read-only reconciliation
recorded above. The workflow below is retained as the required evidence chain
already demonstrated by the final run. Do not restart it merely to obtain a
clean run; any recheck remains read-only unless a documented corrupt/missing
artifact or serious semantic error is demonstrated.

108 historical blocks = completed.

KHÔNG crawl historical lại.

Mục tiêu hiện tại:

    existing 108 historical outputs
        ↓
    merge
        ↓
    coverage audit
        ↓
    error/integrity audit
        ↓
    RSS/current supplementation
        ↓
    archive/revision candidates
        ↓
    Stage 4.3 final gate


Phải làm:

1. Locate toàn bộ existing block outputs.

2. Verify đủ 108 block bằng files/log/state.

3. Merge historical discovered URL outputs.

4. Không drop record chỉ vì canonical URL giống nhau.

5. Giữ discovery provenance.

6. Audit:
   - expected blocks
   - found blocks
   - missing blocks
   - row counts
   - request errors
   - parse errors
   - breadcrumb/category failures
   - temporal coverage
   - publisher sections
   - scope candidates
   - malformed records

7. Chạy/kiểm tra RSS/current supplementation.

8. Tạo/hoàn tất archive/revision candidates nếu public archive/history khả dụng.

9. Validate:
   - discovered_urls.parquet
   - archive_candidates.parquet
   - discovery_log.jsonl

10. discovery_log phải append-only về semantics.


Gate 4.3:

- historical coverage đủ nhiều thời điểm cho pilot;
- không unresolved missing/error nghiêm trọng;
- provenance fields đủ;
- artifact readable;
- historical 108 branch không bị thay đổi.

Sau STAGE 4.3 REPORT:

    STOP


======================================================================
8. STAGE 4.4 — IMMUTABLE RAW SOURCE VERSIONS
======================================================================

Stage 4.4 là architecture-sensitive stage.

Không được production-run cho đến khi Stage 4.3 PASS.


----------------------------------------------------------------------
8.1 REUSE HTML FROM 4.3 OR REFETCH
----------------------------------------------------------------------

Inspect 4.3 implementation trước.

Nếu 4.3 đã lưu:

- exact response bytes;
- retrieval timestamp thật;
- requested URL;
- relevant HTTP metadata;
- bytes không bị parser transform;

thì có thể đề xuất reuse.

Nếu 4.3 chỉ:

    GET
    → parse breadcrumb
    → discard HTML

thì Stage 4.4 phải refetch.

Không fabricate retrieved_at_real.

Nếu reuse old bytes:

    retrieved_at_real = thời điểm fetch thật ở Stage 4.3


----------------------------------------------------------------------
8.2 IDENTITY LAYERS
----------------------------------------------------------------------

Không đồng nhất:

1. blob identity
2. raw source content-state identity
3. retrieval event identity

Khuyến nghị:

    blob_sha256
        = identity của exact stored payload

    raw_source_id
        = immutable identity của source content state

    retrieval_id
        = identity của một lần quan sát/fetch

Không dùng đơn giản:

    raw_source_id = source_id + sha256

nếu điều đó collapse URL/locator không đúng semantics.

Blob giống nhau có thể dùng chung physical CAS object,
nhưng provenance records không được mất.


----------------------------------------------------------------------
8.3 CONTENT-ADDRESSABLE STORAGE
----------------------------------------------------------------------

Ưu tiên:

data/raw/
  by_hash/
    ab/
      <sha256>.html
  index/
  batches/
  logs/

Blob filename không dùng URL/title.

Preserve exact raw payload.

Hash policy phải versioned.

Tối thiểu:

- raw_payload_sha256
- content_hash_sha256
- hash_policy_version

Nếu policy hiện tại hash raw payload:

    content_hash_sha256 == raw_payload_sha256

Nếu pilot cho thấy HTML chứa nondeterministic injected bytes:

KHÔNG tự đổi normalization giữa production.

Phải:

- STOP;
- phân tích;
- đề xuất versioned normalization/hash policy;
- vẫn giữ exact raw bytes;
- test policy;
- ghi decision.


----------------------------------------------------------------------
8.4 TIME FIELDS
----------------------------------------------------------------------

Stage 4.4 chỉ GHI nguồn/time provenance.

Được phép:

- retrieved_at_real
- published_at_declared
- updated_at_declared
- archive_or_revision_datetime

KHÔNG SUY RA:

    evidence_observed_at

Không làm:

    evidence_observed_at = published_at_declared

Không làm:

    evidence_observed_at = retrieved_at_real

Evidence time thuộc Stage 4.10.

Project timestamp nên timezone-aware,
ưu tiên UTC ISO-8601.

Nếu publisher timestamp parsing có rủi ro,
giữ cả:

- *_raw
- *_parsed


----------------------------------------------------------------------
8.5 SOURCE VERSION RELATION
----------------------------------------------------------------------

Không mặc định:

    first project crawl = publisher initial version

Nếu không đủ provenance:

    source_version_relation = unknown

Nếu same URL được thấy với hash khác:

- giữ old state;
- tạo new content state;
- không overwrite;
- tạo change/revision edge theo policy;
- phân biệt observed hash change với archive-verified revision khi cần.


----------------------------------------------------------------------
8.6 ACQUISITION SCOPE VS CORPUS FILTER
----------------------------------------------------------------------

Có thể giới hạn Stage 4.4 vào locked acquisition scope,
ví dụ publisher breadcrumb = Công nghệ,
nếu rule đã khóa upstream.

Nhưng phải giữ rõ:

    acquisition_scope != final_corpus_filter

Stage 4.6 vẫn phải thực hiện corpus filtering chính thức.

Không coi is_scope_candidate là final include decision.


----------------------------------------------------------------------
8.7 CONCURRENCY
----------------------------------------------------------------------

Có thể reuse concurrent pattern đã validation ở 4.3.

Workers nên:

- fetch network;
- parse minimal response metadata;
- return result.

Workers không nên đồng thời mutate canonical shared state.

Registration/index/blob dedup phải:

- main-thread serialized writer;
hoặc
- locking/transaction mechanism rõ ràng.

Race không được tạo duplicate identities.

Giữ global rate/retry policy hiện tại
nếu không có lý do thay đổi.


----------------------------------------------------------------------
8.8 CRASH SAFETY / RESUME
----------------------------------------------------------------------

Không append row-by-row vào monolithic Parquet.

Ưu tiên:

- append-only WAL/JSONL;
- batch Parquet;
- final consolidation.

Ví dụ:

raw_ingest_log.jsonl
raw_retrieval_events.jsonl

batches/
    raw_versions_000001.parquet
    raw_versions_000002.parquet

Raw log của 4.4 phải riêng discovery_log của 4.3.

Blob write:

    write temp
    → fsync/close nếu phù hợp
    → verify hash
    → atomic rename
    → index registration

Resume không được rewrite lịch sử.


----------------------------------------------------------------------
8.9 HTTP PROVENANCE
----------------------------------------------------------------------

Lưu khi khả dụng:

- requested_url
- final_url
- redirect history
- source_id
- retrieved_at_real
- HTTP status
- content_type
- content_length
- ETag
- Last-Modified
- selected headers
- publisher timestamps
- archive/revision timestamp
- raw blob path
- hashes
- retry/fetch outcome

HTTP 200 không tự động = valid article.

Detect/report:

- soft 404
- CAPTCHA/WAF page
- error template
- invalid content type
- malformed response


----------------------------------------------------------------------
8.10 ENGINEERING PILOT
----------------------------------------------------------------------

Trước full 4.4 production,
chạy pilot khoảng 20–30 URLs.

Kiểm tra:

- bytes preservation
- encoding
- hash recheck
- duplicate blob behavior
- repeated fetch behavior
- zero overwrite
- crash/resume
- soft errors
- concurrency race
- manifest integrity


----------------------------------------------------------------------
8.11 OUTPUTS
----------------------------------------------------------------------

Required:

- raw_source_versions.parquet
- raw blobs
- raw_hash_manifest.json
- source_revision_edges.parquet

Có thể thêm:

- retrieval events
- WAL
- batch files
- audit reports


----------------------------------------------------------------------
8.12 STAGE 4.4 GATE
----------------------------------------------------------------------

Validate tối thiểu:

- raw_source_id uniqueness theo policy;
- every raw_source_id maps deterministically to one content state;
- every index row points to existing blob;
- recomputed hash == stored hash;
- old blob never overwritten;
- revision edge endpoints exist;
- no self revision edges;
- every attempted target has success OR explicit failure;
- successful retrieval has retrieved_at_real;
- evidence_observed_at absent/null;
- archive provenance preserved;
- resume does not corrupt existing state.

FAIL:

    STOP


======================================================================
9. STAGE 4.5 — DUPLICATE CLUSTERING + SOURCE LINEAGE
======================================================================

Mục tiêu:

    reduce double-count
    WITHOUT deleting provenance

Phải:

- exact duplicate clustering;
- near-duplicate/syndication clustering theo locked/versioned rule;
- similarity score/method nếu applicable;
- document_clusters;
- lineage_edges;
- audit sample.

Không destructive delete.

Hai URL khác nhau không mặc định độc lập.

Cluster deterministic với same input/config.

Mỗi cluster decision có algorithm_version.

FAIL:

    STOP


======================================================================
10. STAGE 4.6 — CORPUS FILTER
======================================================================

Input:

- document clusters
- raw metadata/content
- corpus scope
- ontology draft

Output:

- corpus_filtered
- filter_decisions
- filter audit report

Mỗi decision:

- include/exclude
- reason_code
- filter_version

Filter chỉ dùng:

- source allowlist/policy;
- historical window;
- domain/topic;
- khả năng chứa relation thuộc ontology draft.

KHÔNG dùng:

- entity frequency xuyên snapshots;
- anchor suitability;
- drift;
- RR;
- SED+;
- downstream performance.

Audit accepted + rejected sample.

FAIL:

    STOP


======================================================================
11. STAGE 4.7 — PILOT 30–50 + ONTOLOGY FREEZE
======================================================================

Chọn 30–50 articles từ nhiều historical points.

Không chọn pilot dựa downstream outcomes.

Phải:

- human annotation một subset:
    - entity mentions
    - relations
    - temporal fields
    - evidence spans

- chốt core relation set khoảng 8–10 nếu data support;
- domain/range;
- cardinality;
- scope/context;
- LogicalFactID rules;
- ontology_version;
- dựng 3 tiny snapshots.

Không mặc định relation single-valued chỉ từ tên.

Stage-A/main processing không bắt đầu trước ontology freeze.

Nếu semantic ontology thay đổi sau freeze:

    version bump
    + appropriate reprocess

FAIL:

    STOP


======================================================================
12. STAGE 4.8 — VERSIONED ENTITY RESOLUTION
======================================================================

Phải:

- detect mention;
- exact span/raw form;
- canonical_entity_id;
- conservative mapping;
- mapping confidence/reason;
- mapping version;
- mapping_available_at;
- alias/rename history nếu cần;
- core/high-degree entity audit.

Khi không chắc:

ưu tiên false split hơn dangerous false merge.

Không dùng mapping tương lai cho snapshot cũ.

Nếu entity algorithm thay đổi sau pilot freeze:

    main corpus phải reprocess với same version

FAIL:

    STOP


======================================================================
13. STAGE 4.9 — CLAIM EXTRACTION + EVIDENCE SPAN
======================================================================

Claim != FactVersion.

Extract candidate:

- subject_id
- relation_id
- object_id/value
- scope/context
- exact evidence span

Phải lưu:

- claim_id
- raw_source_id
- evidence locator/span
- evidence hash
- extractor_version
- ontology_version
- operational confidence

Evidence span phải thật sự support claim.

Không tự động đóng fact cũ chỉ vì bài mới nói object khác.

Conflict:

    send to adjudication

FAIL:

    STOP


======================================================================
14. STAGE 4.10 — TEMPORAL NORMALIZATION
======================================================================

Phân biệt:

- valid_from
- valid_to
- evidence_observed_at
- retrieved_at_real
- publisher declared timestamps

Không backdate evidence vì event xảy ra trước.

Evidence time phải có:

- basis
- confidence
- inferred/fallback flag nếu applicable

retrieved_at_real = project provenance,
không tự động là scientific known-time.

Nếu historical provenance thiếu:

- ghi reason;
- eligibility flag;
- không im lặng fabricate.

FAIL:

    STOP


======================================================================
15. STAGE 4.11 — AS-OF ADJUDICATION
======================================================================

Group claims theo:

- LogicalFactID
- interval
- scope/context

Rule phải versioned.

Possible decision:

- accept
- reject
- pending
- correct
- retract

Phải lưu:

- candidate_claim_ids
- supporting_claim_ids
- accepted_into_kg_at
- adjudication_rule_version
- adjudicated_at_real

"2 sources" không được hiểu đơn giản là "2 URLs".

Phải xét independent provenance groups theo policy.

Không mặc định:

    newer publication = truth

Conflict thiếu evidence:

    pending

FAIL:

    STOP


======================================================================
16. STAGE 4.12 — FACTVERSION STORE
======================================================================

FactVersion store phải append-only.

Phải có:

- immutable FactVersionID
- LogicalFactID
- subject
- relation
- object/value
- scope
- valid_from/to
- evidence_observed_at
- accepted_into_kg_at
- source lineage
- claim/evidence references
- supersedes_version_id
- revision_type
- pipeline versions

Không update old FactVersion in-place.

Retraction/tombstone:

    revision
    NOT destructive deletion

Supersedes chain phải referentially valid.

FAIL:

    STOP


======================================================================
17. STAGE 4.13 — PILOT QUALITY GATE
======================================================================

Đây là HARD STOP trước scale.

Gold/reference annotation phải độc lập với predictions cần đánh giá.

Đo tối thiểu:

- entity-linking accuracy;
- relation precision/recall;
- temporal-field accuracy;
- evidence-span validity;
- conflict/pending behavior;
- source-copying cases.

Tiny snapshot tests:

- no future evidence;
- no future entity mapping;
- future-effective change;
- correction;
- retract;
- deterministic rebuild.

Không tự bịa numeric thresholds.

Threshold data-dependent phải được xác lập/khóa từ pilot.

Zero-tolerance invariant violation > 0:

    FAIL

Nếu fail:

- reduce ontology nếu có căn cứ;
- increase manual review;
- fix extractor/rules;
- rerun impacted pilot;
- DO NOT SCALE.

Chỉ sau PASS mới sang Stage 4.14.


======================================================================
18. STAGE 4.14 — FREEZE PIPELINE + MAIN CORPUS
======================================================================

Freeze:

- ontology
- LogicalFactID rules
- extractor
- entity mapping rules
- temporal parser
- adjudication rules
- snapshot builder
- relevant configuration

Lưu:

- pipeline manifest
- environment/software lock
- config hashes
- reprocess log

Reprocess main corpus bằng cùng frozen versions.

Không:

- extractor v1 ở đầu timeline và v2 ở cuối;
- mix semantic versions;
- manually patch edges;
- patch final snapshot.

Semantic patch sau freeze:

- bump version;
- invalidate affected outputs;
- rebuild từ appropriate upstream.


======================================================================
19. STAGE 4.15 — KG EVENTS + FEASIBILITY
======================================================================

Event = KG STATE TRANSITION.

Event != article count.

Materialize transitions như:

- assert
- correction/value transition
- retract
- interval open/close

Nhiều articles support cùng một state transition:

    không biến thành nhiều KG events chỉ vì URL count

Đo:

- event counts
- active-edge changes
- entity overlap
- anchor availability
- minimal recurring-QA feasibility

Không dùng:

- SED+
- RR
- downstream model outcome

để quyết định feasibility.

Nếu thiếu signal:

- report;
- targeted collection proposal;
- scope decision.

Không outcome-tune data.


======================================================================
20. STAGE 4.16 — SNAPSHOT BOUNDARIES
======================================================================

Chọn khoảng 8–12 snapshots
hoặc số cuối được protocol/config khóa.

Dùng deterministic event-quantile rule.

Không dùng:

- SED+
- RR
- H1 coefficient
- downstream outcome

để chọn boundary/tie.

Lưu:

- snapshot_boundaries
- boundary hash
- transition metadata
- start/end
- duration_days
- n_kg_events
- edge additions/removals
- changed logical facts

Sau boundary lock:

    immutable

trừ khi protocol invalidated.


======================================================================
21. STAGE 4.17 — BITEMPORAL SNAPSHOTS
======================================================================

Main conceptual semantics:

    build_snapshot(valid_at=T, known_at=T)


Order:

1. known filter

    evidence_observed_at <= known_at
    AND
    accepted_into_kg_at <= known_at


2. validity filter

    valid_from <= valid_at

    AND

    (
        valid_to is null
        OR
        valid_at < valid_to
    )


3. resolve supersedes/revision chain deterministically


4. apply retract/tombstone AFTER revision resolution


5. entity mapping as-of

    mapping_available_at <= known_at


6. canonical sort


7. deterministic hash


Must pass:

- no future evidence;
- no future mapping;
- future-effective case;
- late correction;
- retract;
- deterministic rebuild.

Không rewrite historical snapshot bằng evidence biết muộn.

FAIL:

    STOP


======================================================================
22. STAGE 4.18 — CANONICAL PARQUET + NEO4J
======================================================================

Canonical Parquet = SOURCE OF TRUTH.

Canonical Parquet = downstream TransE input.

Neo4j = query/path/materialization layer.

Phải:

- materialize every frozen snapshot to stable Parquet schema;
- deterministic entity IDs;
- deterministic relation IDs;
- preserve required temporal metadata;
- write snapshot hashes/manifests;
- materialize same node/edge set to Neo4j;
- run parity test.

Stage 4.18 chỉ PASS khi:

- set equality = true;
- row counts match;
- entity counts match;
- relation counts match;
- snapshot hashes recorded;
- downstream config references frozen hashes.

Không sửa Neo4j thủ công để pass parity.

Nếu parity fail:

    rebuild materialization from canonical Parquet/fact store

Sau Stage 4.18 PASS:

dataset được coi là ready cho downstream TransE.


======================================================================
23. ML / LLM / AUTOMATION RULE
======================================================================

Nếu implementation muốn dùng ML/LLM cho:

- entity resolution
- claim extraction
- temporal extraction
- adjudication support

KHÔNG tự đưa hosted LLM/API vào pipeline
vì current processing constraint là no-API
trừ khi user chính thức thay đổi decision.

Nếu dùng local model/tool:

- model version frozen;
- model checksum nếu khả dụng;
- tokenizer/config frozen;
- prompt/template version nếu applicable;
- decoding config logged;
- runtime/environment logged;
- reproducibility tested.

Không coi:

    temperature = 0

là bằng chứng deterministic.

Nếu component không đáp ứng reproducibility cần thiết,
không dùng nó làm final frozen decision-maker.

Human gold annotation:

không được sinh bởi chính prediction pipeline
rồi dùng để tự đánh giá prediction đó.


======================================================================
24. TESTING RULE
======================================================================

Mỗi stage phải có các kiểm tra phù hợp:

A. schema validation

B. artifact readability

C. referential integrity nếu applicable

D. deterministic test nếu applicable

E. resume/idempotence test nếu có I/O

F. failure-path test

G. representative sample/pilot test

H. invariant tests

"process exit code 0" không đồng nghĩa PASS.

Script chạy xong nhưng invariant fail:

    FAIL


======================================================================
25. DATA SAFETY
======================================================================

Không được:

- delete raw dataset;
- truncate append-only logs;
- overwrite immutable source data;
- replace frozen artifact in-place;
- rewrite historical timestamps;
- manually repair final snapshots;
- manually repair Neo4j;
- silently modify production Parquet.

Nếu rebuild:

- new version/run;
- preserve old artifact;
- log supersession/invalidation.


======================================================================
26. REQUIRED STAGE REPORT
======================================================================

Sau mỗi stage, report theo format:

============================================================
STAGE 4.X REPORT
============================================================

STATUS:
PASS | FAIL | BLOCKED

PURPOSE:
<1–3 câu>

INPUTS USED:
- exact paths
- relevant versions/hashes

CODE CHANGED:
- created files
- modified files
- reason

COMMANDS EXECUTED:
- exact commands

OUTPUT ARTIFACTS:
- exact paths
- row/record counts
- hashes if applicable

VALIDATION:
[PASS/FAIL] schema
[PASS/FAIL] required artifacts
[PASS/FAIL] scientific invariants
[PASS/FAIL] referential integrity
[PASS/FAIL] determinism/reproducibility
[PASS/FAIL] resume/idempotence
[PASS/FAIL] stage-specific gate

WARNINGS:
- non-blocking issues
- assumptions

FAILURES/BLOCKERS:
- root cause
- affected artifact/stage
- minimum fix

SCIENTIFIC SEMANTICS CHANGED?
NO

OR

YES
→ STOP
→ explain decision/reprocess required

NEXT STAGE:
Stage 4.X+1

NEXT STAGE EXECUTED?
NO

============================================================

Sau report:

    STOP
    WAIT FOR USER


======================================================================
27. WHEN INFORMATION IS MISSING
======================================================================

Không hỏi user nếu có thể resolve bằng:

- repository inspection;
- config inspection;
- schema inspection;
- logs;
- artifacts;
- existing code;
- tests.

Chỉ hỏi nếu:

- semantic ambiguity;
- policy conflict;
- scientific-impact decision;
- reprocess implications;
- required credential/manual action;
- mandatory input genuinely missing.

Không fill missing scientific semantics bằng assumption.


======================================================================
28. FIRST ACTION — START FROM CURRENT STATE
======================================================================

KHÔNG viết Stage 4.4 trước.

KHÔNG rerun historical 108 acquisition.

Làm đúng thứ tự:

1. Inspect repository tree.

2. Inspect git status.

3. Locate existing Tuổi Trẻ historical outputs.

4. Validate from files/log/state rằng:

       expected historical blocks = 108

   và không rerun 03b để xác minh điều này.

5. Check Stage 4.3 current artifacts.

6. Xác định đã có/chưa có:

   - merged discovered URLs;
   - coverage audit;
   - error audit;
   - RSS/current results;
   - archive candidates;
   - final Stage 4.3 validation report.

7. Lập minimal implementation plan để FINALIZE Stage 4.3.

8. Chỉ implement phần còn thiếu của Stage 4.3.

9. Run Stage 4.3 validation.

10. Produce STAGE 4.3 REPORT.

11. STOP.

Không chạy Stage 4.4 production
cho tới khi:

    Stage 4.3 PASS

và user yêu cầu tiếp tục.


======================================================================
29. DEFINITION OF DONE — PER STAGE
======================================================================

"Code chạy" != DONE.

"Có output file" != DONE.

"Không exception" != DONE.

Một stage chỉ DONE khi:

- required inputs hợp lệ;
- required outputs tồn tại;
- outputs readable;
- schema hợp lệ;
- scientific invariants pass;
- referential integrity pass nếu applicable;
- provenance đầy đủ;
- reproducibility/determinism pass nếu applicable;
- stage-specific gate pass;
- STAGE REPORT = PASS.


======================================================================
30. FINAL DEFINITION OF DONE
======================================================================

Toàn nhiệm vụ chỉ DONE khi:

    Stage 4.18 PASS

Stage 4.18 PASS nghĩa là:

- final frozen temporal snapshots tồn tại;
- Canonical Parquet là source of truth;
- entity IDs ổn định;
- relation IDs ổn định;
- snapshot boundaries đã khóa;
- snapshot hashes đã khóa;
- required mappings/manifests tồn tại;
- Neo4j materializes cùng node/edge sets;
- Parquet–Neo4j set equality = true;
- downstream TransE có thể đọc Canonical Parquet trực tiếp;
- downstream không cần quay lại raw news để tự diễn giải dữ liệu.

Không được tuyên bố project data-ready chỉ vì:

- đã có vài triples;
- đã có một Neo4j graph;
- pilot snapshots chạy được;
- một script train có thể chạy thử.

Data-ready cho experiment chỉ sau final frozen Stage 4.18 PASS.


======================================================================
31. WORKING PRINCIPLE
======================================================================

Mỗi lần user nói:

    Continue Stage 4.X theo master prompt

hãy:

1. inspect current state;
2. chỉ làm đúng Stage 4.X;
3. không tự làm Stage 4.X+1;
4. report PASS/FAIL;
5. STOP.

Mục tiêu là vibe-code nhanh,
nhưng architecture phải có checkpoint khoa học rõ ràng.

Final principle:

    FAST IMPLEMENTATION
    + STRICT GATES
    + IMMUTABLE PROVENANCE
    + NO TEMPORAL LEAKAGE
    + FROZEN MAIN PIPELINE
    + CANONICAL PARQUET
    + VERIFIED NEO4J PARITY
