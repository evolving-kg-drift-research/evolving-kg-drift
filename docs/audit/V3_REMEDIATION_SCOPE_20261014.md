# Phạm vi remediation v3 sau kiểm producer và evidence

Ngày: 14/10/2026. **REVIEW REQUIRED — chưa là amendment, chưa được phép reprocess production.**
Phạm vi này bảo toàn protocol, raw/body bytes, v3 và các kết quả legacy đã lưu.
Không bổ sung approval vào decision log hoặc đổi source lock.

## 1. Bằng chứng hiện có

- Recovery release `data/pre-gate-a-audit-v1` là AUDIT_ONLY; body/raw/receipt
  hashes đã đối chiếu với v3 theo mục 12 của quy trình.
- 1.803 facts bind whole-body hash; 1.788 exact subspans không khớp.
- FactVersionID suffix khớp claim_id; source/relation/span/hash fields khớp
  claim tương ứng trên **1.803/1.803** rows.
- Subject/object IDs khớp `ent_ + SHA256(strip(lower(mention)))[:8]`; LogicalFactID
  khớp SHA256 của `subject_id|relation|object_id` lấy 16 hex trên toàn store.
- Chẩn đoán 32 reachable Git commits: tối đa 6/13 exact Git-blob config hashes;
  khi chỉ mô phỏng line endings LF/CRLF, 13/13 hashes tương thích với sáu commits
  thuộc họ producer `6779bf4` → `e19fe25` → `74a1f14`.
- Không có v3 code/run manifest để xác nhận đúng commit; tương thích line endings
  không phục hồi originals có thẩm quyền hoặc phê duyệt baseline.

Audit mới: `outputs/v3_producer_lineage/20261013T175716Z_b01c9055/`.
Đọc `summary.json`, `config_comparisons.json`, `fact_claim_rule_diagnostics.json`
và reference code snapshots để tái kiểm. Mention links của 1.389 legacy entity
IDs được lưu với nhãn DIAGNOSTIC_ONLY, không phải mapping table production.

## 2. Phạm vi engineering đã xử lý

Current `src/kg_pipeline/claims.py` tính hash exact span qua `EvidenceSpan`,
kiểm cả subject và object mention trong slice, và quarantine candidate không
được grounded. Không transplant logic whole-body hash từ producer cũ.

Thêm regression gọi trực tiếp extractor hiện tại trên ASCII/Unicode fixtures:
span đúng dù model response mang body hash; field output phải là subspan hash;
claim chỉ có một role trong span bị quarantine. Suite cùng producer-diagnostic
và recovered-span checks: **7 passed**. Ruff toàn repo không lỗi lint, có warning
quyền đọc fixture directories cũ. Không sửa production source vì behavior cần
thiết đã có và tests xác nhận.

Đây chỉ là IMPLEMENTED/TESTED guard behavior. V3 lịch sử không được sửa hash,
offset, mention, ID hoặc timestamp để làm cho các tests này PASS.

## 3. Các dependency phải giải quyết trước real-data execution

| Dependency | Cần xác nhận bằng chứng | Trạng thái |
|---|---|---|
| Producer lineage | Original run manifest, exact commit/dirty patch, code/config/model/cache hashes của v3 | Thiếu |
| Contract migration | Public schema version/fields/types và body/span/provenance contracts được duyệt | C3 còn BLOCKED |
| Normalization/extraction | Explicit clean-text representation, normalization/parser/extractor versions, reproducible local cache | Thiếu approved production binding |
| Canonical identity | MentionID, MappingDecisionID, canonical IDs, mapping basis/availability và alias/conflict policy | Thiếu |
| Temporal basis | Stage 4.10 evidence_observed_at/acceptance clocks có evidence; không thay bằng retrieval/validity | Thiếu |
| Source/config authority | Original locked sources và approved resolved baseline | Chưa verified |

Nếu producer gốc không thể cung cấp, phải ghi nhận lineage không thể khôi phục
và chốt việc bắt đầu một run mới từ verified upstream artifacts. Không tự ghi
commit candidate thành actual producer. Mọi run mới vẫn cần dependencies trên.

## 4. Reprocess impact set đề xuất

Chỉ sau khi các dependencies được duyệt/verified, thực hiện một stage mỗi lần:

1. **Stage 4.9 — claims/span:** read exact versioned body text; bind body hash và
   subspan hash riêng; giữ candidate raw responses và cache lineage. Candidate
   thiếu grounding phải có review/quarantine record, không tự tìm span thay thế.
2. **Stage 4.10 — temporal normalization:** dùng registered evidence basis,
   giữ validity/observation/acquisition axes riêng. Thiếu basis tiếp tục blocked.
3. **Stage 4.11 — as-of adjudication:** dùng registered mapping decisions tại
   đúng cutoff; nối supporting_claim_ids, acceptance/decision provenance.
   Hashing surface names không thay canonical identity resolution.
4. **Stage 4.12 — FactVersion store:** append-only lineage mới trong run/version
   mới, giữ version cũ và supersession evidence. Không ghi đè 1.803 rows hiện tại.
5. **Stage 4.13 — quality gate:** independent gold/procedure theo protocol đã
   đăng ký. Diagnostic sample 30 facts không tự trở thành gold/accuracy estimate.
6. **Stages 4.14–4.18:** chỉ mở khi stage trước đạt gate và user yêu cầu tiếp;
   rebind freeze/events/boundaries/snapshot/support/exclusions/manifests khi
   inputs thay đổi; Neo4j cần real database read-back.

Impact set trên là phạm vi dependencies cần review, không phải cho phép chạy
liền nhiều stages. Raw acquisition Stage 4.3 không thuộc rerun scope. Raw/body
đã match hash có thể được đánh giá để reuse, không tự chứng nhận toàn corpus.

Không mở training/drift/QA production với artifacts đã invalidated. Legacy
TransE results cũ được giữ làm kết quả của dataset cũ, không đổi label thành
scientific certification sau khi sửa extractor.

## 5. Tiêu chí review từng stage

- Input ArtifactRefs/hash/approved policies có đủ trước execution.
- Mỗi claim có exact offsets, body representation/version và span hash match.
- Both-role grounding và explicit relation audit; substring match một mình
  không chứng minh quan hệ đúng hoặc canonical mapping đúng.
- Mapping-as-of, evidence/acceptance basis kiểm được, không future catalog.
- Missing evidence/conflicts có structured review/quarantine hoặc fatal blocker.
- Old run không đổi bytes; new run có supersession/invalidation lineage.
- Contract tests, temporal invariants và required checks đạt; không skip rồi
  gọi gate PASS. Stage report phân biệt IMPLEMENTED/TESTED/EXECUTED/VERIFIED.

Không đề xuất threshold mới, scientific estimand mới hoặc bỏ khó queries/facts
để đạt điểm tốt. Không dùng MRR/self-loop findings quyết định corpus/mapping.

## 6. Finding V3-PROD-001

- **Severity:** HIGH.
- **Affected files:** v3 `inputs/proposed_config_bundle.yaml`, `tables/fact_versions.parquet`,
  `tables/extracted_claims.parquet`; producer candidates trong `src/kg_pipeline/`.
- **Expected:** Exact producer lineage và registered mapping/basis, không suy ra authority từ ID syntax/config tương thích.
- **Actual:** ID algorithms tương thích toàn store, nhưng mapping chỉ là hash surface form và actual producer commit chưa verified.
- **Evidence:** Audit output ở mục 1; code candidate `adjudicate.py`/`adjudication.py` và config comparisons.
- **Root cause vs hypothesis:** ID rules/hash mechanism xác nhận bằng artifact values; actual v3 execution commit vẫn unverified.
- **Reproduction:** `python scripts/audit_v3_producer_lineage.py`; chạy mới không ghi đè report cũ.
- **Proposed minimal fix:** Lấy original producer manifests/mapping decisions hoặc chốt new-run reconstruction dưới approved contracts, theo stages mục 4.
- **Regression tests:** 2 producer diagnostics + 3 actual-extractor boundary cases + 2 recovered-span tests PASS.
- **Remaining blockers:** Producer authority, identity/temporal policies, C3/schema và Gate A/G1/G2.

## 7. Status và việc cần quyết định

**Đã thực hiện:** producer/ID-rule diagnostics, mention links chỉ để audit,
regression extractor hiện tại, phạm vi reprocess có reviewable dependencies.
**Chưa thực hiện:** production re-extraction, mapping adjudication hoặc sửa artifacts.
Producer/gates không được đánh dấu VERIFIED/RESOLVED.

Để tiến tới execution cần owner có thẩm quyền xác nhận contract/identity/time
policies và cung cấp producer manifests; nếu thiếu originals, cần quyết định
new-run lineage rõ ràng. Đọc hồ sơ C3 hiện có cùng phạm vi này, không sửa source
lock để khớp file candidate. Chưa ghi decision log hoặc amendment có hiệu lực.
