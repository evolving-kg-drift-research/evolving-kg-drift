# M1 acceptance rebuild — báo cáo triển khai engineering

Ngày: 14/10/2026. Nhánh: `codex/m1-acceptance-rebuild`.
Base commit: `684dc6b288f0463bbe0aa393347feceec5294868`.
Commit tài liệu/contract package: `92a3ecb`; engineering foundations: `a715a21`.
Các commit mới hiện lưu local; chưa push nhánh này.

**Trạng thái: engineering foundations IMPLEMENTED/TESTED; M1 production và
handoff vẫn BLOCKED. Kế hoạch end-to-end chưa hoàn tất.**

## 1. Công việc đã thực hiện

- Tạo nhánh đúng base, giữ tài liệu handoff và proposal PDF đang untracked.
- Lưu kế hoạch và runbook; giữ scientific protocol/source lock/public schema
  hiện hành, historical v3 và T01 artifacts.
- Tạo review package revision mới: 25 typed tables (17 public + 8 auxiliary),
  matrix/source hashes, explicit serializer mapping. Runtime không activate draft.
- Implement `PublicContract`: exact columns/types/nullability, PK/FK, UTC,
  finite confidence, SHA-256 domains và lossless serializer/Parquet round-trip.
- Siết schema auditor: UNDECLARED physical declarations không trả PASS. Đây là
  enforcement contract, không tạo quyết định schema migration.
- Artifact reader giới hạn workspace/paths, chặn locked_test/links/traversal,
  kiểm hash trước đọc; approval binding qua đúng decision ledger.
- Gemini REST capture/replay có inventory/approval/run/Gate A guards, budget
  reservations, attempts/usage/model version, strict response validation;
  replay không gọi mạng. Chỉ fixture transport chạy trong lượt này.
- Independent document-level quality metrics có FP/FN, denominators, strata,
  two-annotator/adjudication bindings và threshold/procedure approvals.
- Temporal helpers có occurrence identity, observation basis, acceptance lúc
  đủ supports/mappings, future-effective revision/retract behavior và atomic
  event-quantile boundaries. Đây là components, không phải producer certified.
- Registry/preflight cho từng stage, phase và prerequisites; không auto-advance.
  Quality stage có component dispatch; production backends còn chưa activate.
- Scientific gate có đường recompute component evidence, nhưng luôn giữ
  `FINAL_CERTIFICATION_INCOMPLETE` tới khi toàn bộ certification path hoàn thiện.
- Môi trường Python 3.11 riêng, dependency lock 52 packages từ requirements.in,
  pin OpenAI legacy client, Requests/Gemini REST, Neo4j driver và Tomli. Sửa
  Python 3.10 imports, CI matrix 3.10/3.11; soupsieve 2.8 để hỗ trợ 3.10.

## 2. Bằng chứng trên artifacts thật

### Raw recovery mở rộng

Chỉ phục hồi raw members mà v3 membership table tham chiếu, vào namespace mới.
Không chạy acquisition, extraction hoặc sửa artifacts lịch sử.

- Archive SHA-256: `9d72dfce30a63a1048e4e20cc08784a900e3de5d22401f6fe51af96cbedb5184`.
- V3 memberships SHA-256: `36f8307a8362761ae72245cbd6a6d130484745f9dbd5c91e41870c2ab1778f72`.
- **5.168/5.168 referenced raw blobs khớp hash**, 1.662.329.089 bytes.
- Selection SHA-256: `c21cfd4d810ca19e367b613fada48c9abd2e3a55dcfe7f24a4acefb782e144c6`.
- Results semantic SHA-256: `3a1a7bb440dc500ef86400188f95c6924639ad0347e02027533d7aee6263019e`.
- Output: `outputs/m1_acceptance_raw_recovery_20261014/`.

Scope là **HASH_RECOVERY_AUDIT_ONLY**. Kết quả này không chứng minh observation
times, canonical identity, semantic correctness hoặc Stage 4.4 PASS.

### Source authority

Đối chiếu 35 reachable commits và exact paths theo source lock. Proposal có
Git blob đúng hash và file local đúng bytes. Hai execution-plan/patch originals
không có exact matching Git blob. Không đổi lock theo candidate bytes.
Report: `outputs/m1_acceptance_rebuild_baseline/source_search.json`.

### Bảo toàn

Đối chiếu với original v3 inventory: **113 files không đổi hashes**.
Git diff xác nhận không đổi `config/schema.yaml`, `configs/protocol_v1.yaml`,
`data/manifests/sources.lock.json` hoặc `decisions/decision_log.jsonl`.

## 3. Verification

| Check | Kết quả/phạm vi |
|---|---|
| Baseline trước patch | 345 passed, 10 skipped trên Python 3.12 sau sandbox permission correction |
| Contract tests | 35 passed ở lượt mục tiêu |
| Gemini fixtures | 15 passed, không gọi provider |
| Foundations suite | 61 passed trên Python 3.11 |
| Full regression cuối | **408 passed, 10 skipped trên Python 3.11.9** |
| Dependency consistency | `pip check` và direct runtime/build lock checks PASS |
| Python 3.10 compatibility | Package Requires-Python metadata compatible; CI matrix đã thêm; chưa chạy Python 3.10 thật |
| Ruff | Toàn repo PASS, không sửa format bằng lint |
| Raw audit | EXECUTED + VERIFIED checksum scope; không scientific certification |

Các skipped tests có từ scaffold và không được dùng làm scientific PASS.
Sandbox ban đầu chặn fixture/cache Windows; các lượt verified chạy trong
basetemp riêng với quyền phù hợp. Logs/JUnit tại
`outputs/m1_acceptance_rebuild_baseline/`.
`verification_manifest.json` và `code_snapshot/` lưu provenance/hash code thực
tế của lượt kiểm tra; null mapping/query/seed/RAM được ghi rõ là không áp dụng
hoặc chưa đo, không tạo dữ liệu giả.

## 4. Phần chưa thực hiện và blockers

1. Khôi phục exact source originals hoặc approved replacement amendment.
2. Review source-event/eligibility của fields mới và approve full candidate
   schema/policies bằng exact hashes. Package hiện vẫn REVIEW_REQUIRED.
3. Activate serializers/runtime schema và migrate tất cả producer/consumer
   paths dưới contract đã duyệt; hiện 9/17 name mismatches vẫn tồn tại ở runtime.
4. Hoàn thiện production stage backends, split actual 4.11/4.12 publication,
   main replay orchestration và full artifact producer manifests.
5. Tạo 50-article pilot đủ eligibility, independent annotations, guideline,
   sampling/matching rules, review và threshold/coverage annex.
6. Dự toán/chốt budget và model capability/config registration trước Gemini
   calls; legacy extraction runner hiện vẫn local-only, chưa route sang Gemini.
7. Complete physical bit-identical rebuild certificate, final independent G2/
   QA feasibility, frozen boundaries và producer lineage checks.
8. Production snapshots, actual Neo4j materialization/read-back, Stage 4.18
   PASS và certified M2 load trên real rebuilt package.

Các phần trên chưa được đánh dấu RESOLVED/EXECUTED/VERIFIED. Không có datasets
mới được chứng nhận, API billing, production stage hoặc training mới trong lượt này.

## 5. Finding M1-ACC-001 — GOVERNANCE

- **Affected:** sources theo source lock; candidate package; M1 producers/gates.
- **Expected:** Handoff dựa exact authority, approved typed contracts và
  độc lập kiểm định real artifacts; không cấp PASS từ fixture hoặc report text.
- **Actual:** Raw bytes đã recover đầy đủ trong phạm vi v3; source originals,
  schema activation, gold/budget và final certifier còn thiếu.
- **Evidence:** source-search/raw-audit/readiness reports, full JUnit và runtime audit.
- **Root cause:** Thiếu authority/approval/evidence và production implementation
  đã ghi; không suy diễn raw hash PASS thành temporal/quality PASS.
- **Reproduce:** `kg_pipeline rebuild-readiness`; đọc exact artifact refs ở mục 2.
- **Minimal fix:** Giải quyết authority/full contract review trước activation;
  tiếp tục staged engineering theo runbook, không patch data v3 in-place.
- **Regression:** Contract/Gemini/temporal/quality/preflight tests và guard chặn
  component PASS mở final scientific gate.
- **Remaining blockers:** Mục 4. M1 → M2 production vẫn BLOCKED.
