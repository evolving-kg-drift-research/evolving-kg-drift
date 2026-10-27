# Kiểm tra tiếp nhận dữ liệu M1 V3.1 — 2026-10-21

## Kết luận và phạm vi

Gói được kiểm tra: `data/evolving_kg_downstream_v3_1/` và ZIP cùng tên.
**Toàn vẹn đóng gói đã được kiểm chứng; chưa đủ điều kiện tiếp nhận scientific M2.**
Đây là kết quả kiểm tra trực tiếp gói mới, không phải việc áp lại trạng thái
BLOCKED từ báo cáo cũ. Không có quyết định thay đổi scientific semantics.

`RELEASE_V3_1.md` và `reports/v3_1_package_validation_report.json` chỉ tuyên bố
PASS cho canonical TransE input package / Stage 4.18 handoff; báo cáo ghi rõ
`full_m1_acceptance: NOT_CERTIFIED_BY_THIS_PACKAGE`. Phạm vi này không đồng
nghĩa toàn bộ M1, G1/G2 hoặc certified loader của repository đã PASS.

Checkout: `codex/m2-drift-workflow`, commit
`abeb425385f8b19bb05db30c84c4bb05371e8640`, dirty trước khi kiểm tra.
Nguồn đối chiếu gồm AGENTS.md, docs/PROGRESS.md, các audit matrices hiện hành,
docs/data_pipeline_spec.md, docs/modules.md, config/schema.yaml,
configs/protocol_v1.yaml, data/manifests/sources.lock.json và code loader thực tế.

## Những phần đã kiểm chứng

| Kiểm tra | Kết quả trực tiếp |
|---|---|
| Release inventory | 4.871/4.871 đường dẫn, kích thước và SHA-256 khớp; không thiếu/thừa file ngoài manifest tự loại trừ chính nó |
| ZIP so với thư mục giải nén | 4.872/4.872 file khớp bytes |
| Parquet sidecars | 39/39 khớp physical hash và row count; chấp nhận đúng hai tên field hash được sidecar khai báo |
| Body CAS | 4.745/4.745 body khớp SHA-256 nội dung UTF-8 |
| Canonical snapshots | 10/10 khớp hash và số lượng trong downstream config; không triple trùng |
| Timestamp tại cutoff | Không có `evidence_observed_at > cutoff`, `valid_from > cutoff` hoặc `valid_to <= cutoff` trong canonical rows |
| Quan hệ giữa snapshots | Các tập triples tăng đơn điệu; mỗi snapshot có 10 relations |
| Báo cáo Neo4j mới | Có `DB_READ_BACK_PERFORMED=true`; 10 canonical edge-set digests tính lại khớp cả canonical/Neo4j digests trong report |

Kiểm tra timestamp ở trên chỉ đối chiếu các giá trị đã ghi; không xác minh
nguồn gốc clock, future mapping hoặc toàn bộ temporal integrity. Không đọc
lại database Neo4j trong lượt này; node-set equality và lần database read-back
ngày 18/10 vẫn là bằng chứng do producer báo cáo, chưa được receiver tái thực hiện.

| Snapshot | Edges | Entities | Representative facts có span-hash mismatch |
|---|---:|---:|---:|
| T01 | 121 | 167 | 121 |
| T02 | 247 | 343 | 247 |
| T03 | 362 | 503 | 362 |
| T04 | 483 | 646 | 483 |
| T05 | 604 | 787 | 604 |
| T06 | 724 | 936 | 724 |
| T07 | 844 | 1.057 | 829 |
| T08 | 964 | 1.176 | 949 |
| T09 | 1.084 | 1.282 | 1.069 |
| T10 | 1.205 | 1.389 | 1.190 |

Không cộng cột cuối thành số fact độc lập: snapshots lặp lại facts qua thời gian.

## Findings

### M1-V31-001 — Xung đột source authority chưa được hòa giải

- **Severity:** GOVERNANCE, chặn tiếp nhận scientific.
- **Affected Components/Files:** `configs/protocol_v1.yaml`,
  `data/manifests/sources.lock.json`; các bản tương ứng và hai execution-plan
  Markdown dưới `data/evolving_kg_downstream_v3_1/`; `decisions/decision_log.jsonl`;
  `data/m1_audit_and_gates_bundle/decisions/decision_log.jsonl`.
- **Expected Behavior / Invariant:** Theo AGENTS.md §2.1–2.2, phải xác định
  authoritative source baseline; không tự thay protocol/source lock để khớp gói mới.
- **Actual Behavior:** Hai execution-plan source hashes của package khác active
  protocol/lock. Active ledger giữ quyết định preserve-original; bundle riêng có
  quyết định bổ sung `resolve_source_lock_with_course_execution_plan_20260922`.
  Không có amendment hoàn chỉnh trong `amendments/` hiện tại, chỉ có template.
- **Evidence:**

  | Role | Active protocol/lock | Package protocol/lock và bytes nguồn |
  |---|---|---|
  | execution_plan | `c61d08fc6a5a63658e2b99c1245867b9221a3f84c04fa9d872bad8fbbb638b94` | `667aa4601afdb888dd079670336a45611531fa34d8d8b283a1773d06d4ff7949` |
  | patch | `3f1bc9fd9d3dca2bb47eadc59c0ec6266a12794612761ce6b7ffb204fccb31a5` | `509046466a6f81b9dc2119ab8fdd56d50fbb1019a0e83e5c46000a126bfcd3fe` |

- **Root Cause vs. Hypothesis:** Đã xác nhận khác baseline/ledger. Chưa xác minh
  thẩm quyền và hiệu lực của quyết định trong bundle; không suy đoán quyết định giả.
- **Reproduction Steps:** Đọc `sources` trong hai bản protocol và SHA-256 của hai
  Markdown trong package; đối chiếu hai ledger nêu trên.
- **Proposed Minimal Fix:** Chủ sở hữu M1 cung cấp quyết định/phê duyệt có binding
  old/new hashes và run; hòa giải qua quy trình sửa baseline được chấp thuận,
  giữ nguyên lịch sử. Không tự copy đè active lock/protocol.
- **Regression Tests:** Chưa thêm test trong lượt audit. Khi có quyết định hợp lệ,
  kiểm tra source-lock bytes, protocol bindings và run lineage trên cùng baseline.
- **Remaining Blockers:** Quyết định authority và đánh giá ảnh hưởng downstream.

### M1-V31-002 — Evidence hash đang băm toàn body thay vì exact span

- **Severity:** HIGH.
- **Affected Components/Files:**
  `data/evolving_kg_downstream_v3_1/tables/fact_versions.parquet`,
  `data/evolving_kg_downstream_v3_1/tables/extracted_claims.parquet`,
  `data/evolving_kg_downstream_v3_1/tables/body_variants.parquet`,
  `data/evolving_kg_downstream_v3_1/body_blobs/sha256/`,
  `data/evolving_kg_downstream_v3_1/snapshots/snapshot_T*_canonical.parquet`.
- **Expected Behavior / Invariant:** `evidence_text_hash` phải bằng SHA-256 của
  exact Unicode code-point slice `[evidence_span_start:evidence_span_end]`.
- **Actual Behavior:** 1.788/1.803 facts và 1.849/1.865 claims không khớp slice.
  Toàn bộ 1.803 facts và 1.865 claims lại khớp hash toàn body. Có body và các
  chỉ số span đều trong giới hạn; đây không phải thiếu file khi giải nén.
- **Evidence:** Source `bodyvariant_003a18ca5c414b5a8e062407d2c995cb`, span
  `[236:329]`, body dài 4.798 code points. Stored hash
  `04c600356000fb39bf451deae65e2a3a9c604acfac79859e3b171e022900d30a`;
  exact-slice hash
  `e4300a004bbd94cd76d83036e7f0f090b4ac006251bb9988e5113b79953c0124`.
  Join representative `fact_version_id` của T10 về fact store cho thấy
  1.190/1.205 canonical rows cũng nối tới facts bị lỗi này.
- **Root Cause vs. Hypothesis:** Đã xác nhận representation của hash là whole-body
  ở records hiện có. Chưa truy nguyên code producer đã tạo records; không quy kết
  một hàm cụ thể trong checkout hiện tại.
- **Reproduction Steps:** Đọc Parquet bằng PyArrow; join `source_id` với
  `body_variants.body_variant_id`; đọc bytes tại
  `body_blobs/sha256/<hash[:2]>/<hash>.txt`, decode UTF-8, tính
  `hashlib.sha256(text[start:end].encode('utf-8')).hexdigest()` rồi đối chiếu
  `evidence_text_hash`. Không normalize hoặc strip text.
- **Proposed Minimal Fix:** M1 sửa producer exact-span hashing và tạo run/version
  mới với lineage/supersession, rebuild các artifacts phụ thuộc; bảo toàn package
  V3.1. Không sửa trực tiếp hash trong historical Parquet để che lỗi.
- **Regression Tests:** Chưa thêm test vì audit không sửa code. Yêu cầu hồi quy
  Unicode/code-point slicing và kiểm chứng toàn bộ claims/facts mới trên body CAS.
- **Remaining Blockers:** Producer remediation và artifact-backed revalidation.

### M1-V31-003 — Gói chưa đáp ứng certified M2 handoff của repository

- **Severity:** HIGH.
- **Affected Components/Files:** `src/kge/adapter.py`,
  `src/kg_pipeline/canonical_validation.py`, `src/kg_pipeline/run.py`,
  `data/evolving_kg_downstream_v3_1/snapshots/snapshot_Txx_manifest.yaml`,
  `data/evolving_kg_downstream_v3_1/tables/fact_versions.parquet`;
  thiếu `runs/production_v3/run_manifest.yaml`.
- **Expected Behavior / Invariant:** Certified loader cần producer run/stage
  manifests, snapshot-manifest-v2 dependency bindings, mapping-as-of evidence và
  artifact-backed G1/G2 PASS. Physical sidecars không thay thế scientific certificate.
- **Actual Behavior:** Package có historical per-snapshot manifests nhưng không
  có producer run manifest/certified layout. 1.803/1.803 facts ghi
  `entity_map_version=v1_mock`, `adjudication_status=AUTO_ACCEPTED`; package không
  có bảng entity mapping versions để receiver chứng minh INV-02.
- **Evidence:** Gọi public loader trả
  `FileNotFoundError: Run has not been initialized: .../runs/production_v3/run_manifest.yaml`.
  Gọi internal canonical loader với manifest verification trả
  `ValueError: Missing snapshot manifest: .../evolving_kg_downstream_v3_1/snapshots`.
- **Root Cause vs. Hypothesis:** Đã xác nhận thiếu contract/certification artifacts.
  Nhãn `v1_mock` chưa tự chứng minh identity thực tế sai; mapping đúng/sai và thời
  điểm mapping có sẵn chưa thể xác minh bằng các files được bàn giao.
- **Reproduction Steps:** Trong Python có `src` trên `sys.path`, gọi
  `kge.adapter.load_snapshots_from_run(Path.cwd(), 'production_v3', ['T01'])`;
  hoặc `_load_snapshot_from_parquet(package / 'snapshots/snapshot_T01_canonical.parquet', 'T01')`
  từ `kg_pipeline.canonical_validation` với mặc định verification bật.
- **Proposed Minimal Fix:** Sau khi hòa giải authority, M1 bàn giao producer
  manifest/stage lineage, mapping decisions/as-of, support/exclusion dependencies
  và chứng nhận G1/G2 thực. Migration contract nếu cần phải có version, giữ lại
  historical package; không tắt guards hoặc tự tạo certificate.
- **Regression Tests:** Chưa thêm test; chỉ thực gọi hai loader, ghi nhận fail-closed.
  Receiver retest public loader trên package hợp lệ và negative cases thiếu bindings.
- **Remaining Blockers:** M1-V31-001, M1-V31-002 và chứng nhận temporal/entity quality.

### M1-V31-004 — Machine contract vẫn BLOCKED tại checkout nhận dữ liệu

- **Severity:** HIGH.
- **Affected Components/Files:** `config/schema.yaml`,
  `src/kg_pipeline/contract_authority.py`, `src/kg_pipeline/contracts.py`,
  `data/evolving_kg_downstream_v3_1/tables/fact_versions.parquet`,
  `data/evolving_kg_downstream_v3_1/tables/document_clusters.parquet`.
- **Expected Behavior / Invariant:** Runtime schemas/domain implementation và
  data phải tuân thủ authoritative machine contract, gồm types/nullability.
- **Actual Behavior:** Audit runtime hiện tại vẫn có 9/17 bảng lệch field contract;
  17/17 chưa khai báo physical types/nullability. Đây là tình trạng có sẵn của
  checkout, không quy kết là lỗi mới do upload V3.1. Trong 6 bảng package có cùng
  tên với top-level YAML contracts, `fact_versions` và `document_clusters` lệch fields.
- **Evidence:** `audit_machine_contract(Path.cwd())` trả `status=BLOCKED`,
  `physical_contract_status=BLOCKED`. Fact Parquet thiếu các fields contract như
  `accepted_into_kg_at`, `adjudicated_at_real`, `adjudication_rule_version`,
  `ontology_version`, `retrieved_at_real`, `supporting_claim_ids`; có các field
  legacy như `fact_version_id` thay `FactVersionID`.
- **Root Cause vs. Hypothesis:** Đã xác nhận sai khác khai báo và trạng thái audit.
  Chưa xác định schema migration nào được phê duyệt cho baseline mới.
- **Reproduction Steps:** Chạy read-only
  `from kg_pipeline.contract_authority import audit_machine_contract; audit_machine_contract(Path.cwd())`;
  so `pq.read_schema(path).names` với `config/schema.yaml`, bỏ field envelope
  `schema_version` khi so fields.
- **Proposed Minimal Fix:** Hòa giải baseline trước; migrate contract/runtime và
  versioned artifacts trong task được chấp thuận, thêm physical declarations;
  không sửa schema nhằm bỏ qua dữ liệu hoặc acceptance clocks còn thiếu.
- **Regression Tests:** Chưa thêm test; đã chạy machine-contract diagnostic thật.
  Bổ sung contract regression khi có migration được phê duyệt.
- **Remaining Blockers:** Authority/schema migration và artifact-backed execution.

## Giới hạn tái lập và bằng chứng định danh

- 5.168 raw references, tổng 1.662.329.089 bytes, được producer ghi là external
  và không nhúng trong ZIP. Không file nào hiện có tại repository-relative paths
  được khai báo. Đây là giới hạn của bản bàn giao hiện tại, không phải lỗi ZIP:
  chưa thể độc lập xác minh lại raw acquisition/content provenance tại máy nhận.
- `inputs/config_baseline_scope_note.json` tự ghi nhận năm candidate config hash
  mismatches và chỉ chứng nhận packaging/parity, không re-anchor Ticket A.
- Không thử lại full G1/G2 hoặc đánh giá gold quality; không chạy production stage,
  acquisition, training, drift hoặc database access. Không mở `data/locked_test/`.
- Không sửa input data, protocol/source lock, decision ledger, historical outputs
  hoặc docs/PROGRESS.md. Chỉ thêm báo cáo audit này; không commit/push.

| Artifact | SHA-256 |
|---|---|
| ZIP V3.1 | `a6acd988e81c9ab99bdd76e7a1f450f6f9360a7a5404cc53d33c4af8ba04915d` |
| release_manifest.json | `3106f3f13982d55d0ab035466f5e326ebf5df7bf743931e04287e74da70426d5` |
| Active protocol | `61d1eb47ec9fbfb06fff418c785722fecb16090ef886039cd1359ff5cc465c73` |
| Active source lock | `a6e32c14f28aa60e7977ec25b1ee60e71bf1226273d4f94de4edb58cf9a796b7` |

## Mức kiểm chứng và điểm dừng

- **IMPLEMENTED:** Không patch production code hoặc remediation data.
- **TESTED:** Read-only loader probes và machine-contract diagnostic; Ruff toàn
  repo PASS với `--force-exclude --extend-exclude data/locked_test`;
  `git diff --check` PASS. Không chạy pytest vì không thay code.
- **EXECUTED:** Chỉ intake audit trên artifacts thật; không production pipeline stage.
- **VERIFIED:** Packaging/hash/snapshot-count/body-CAS checks và các defect được
  tái hiện ở trên. Không có scientific gate PASS hoặc M1 recertification.

Dừng việc tiếp nhận scientific tại source-authority conflict theo AGENTS.md §2.2.
Cần M1 giải quyết authority, exact-span provenance và certified handoff trước
khi đăng ký bộ này làm scientific input cho M2. Không tự chuyển sang huấn luyện.
