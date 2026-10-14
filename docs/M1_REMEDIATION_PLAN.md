# Kế hoạch sửa M1 và nghiệm thu dữ liệu bàn giao M2

Ngày: 14/10/2026. Nhánh: `codex/m1-acceptance-rebuild`.
Base: `684dc6b288f0463bbe0aa393347feceec5294868` từ `codex/transe-legacy-exploration`.

## 1. Mục tiêu và các lựa chọn đã chốt trong chat

Tạo bộ dữ liệu mới có schema thống nhất, evidence và thời gian kiểm chứng được,
canonical mapping theo cutoff, snapshots tái tạo được, G1/G2 có kiểm định thật,
Stage 4.18 PASS và certified M2 loader đọc được gói bàn giao.

| Nội dung | Lựa chọn |
|---|---|
| Git | Nhánh thông thường từ base trên, dùng checkout hiện tại, giữ thay đổi đang có |
| Inputs | Tái dùng upstream đã xác minh, giữ v3 và T01 legacy bất biến |
| Sources | Khôi phục originals đúng bytes/hash trước; không có thì amendment riêng |
| Contracts | Hoàn thiện drafts hiện có; full matrix và bảng phụ trợ phải được duyệt đúng hash trước activation |
| Window | 01/03/2025–31/08/2026; thay đổi cần approval/amendment |
| Pilot | 50 bài, outcome-blind, phủ nguồn và historical points |
| Gold | Hai người độc lập, có phân xử và giữ nhãn gốc |
| Extractor | Gemini `gemini-3.8-flash`, chỉ đề xuất candidates |
| API payload | Clean text công khai trong inventory được duyệt, ontology và prompt |
| Ngân sách | Dự toán và duyệt trần riêng cho pilot/main trước requests |
| Kết thúc | Nghiệm thu M1 và load M2; không tự mở training/drift/QA chính thức |

Yêu cầu implement kế hoạch cho phép phát triển code và đăng ký lựa chọn đã
chốt; không tạo ra originals, gold, thresholds, ngân sách hoặc authority đang
thiếu. Các đầu vào đó phải tồn tại trước production tương ứng; thiếu thì BLOCKED.

## 2. Authority, schema và lineage

- Inventory exact sources/config/artifacts; giữ lock hiện tại. Nếu originals
  không còn, lập amendment với replacement bytes/hash, precedence và impact.
- Producer v3 chưa xác minh thì ghi UNVERIFIED; run mới dùng verified input
  lineage, không gán candidate commit thành actual producer.
- Tạo policy package revision mới, giữ bản cũ và ghi matrix hash mismatch.
- Public contract 1.1.0 giữ field names, typed Arrow/nullability/PK/FK/domain,
  serializer mapping tường minh; hoàn thiện cả 17 bảng và auxiliary tables.
- Bổ sung acceptance/adjudication clocks, scope/literals, ontology/support,
  body/mention/mapping/temporal provenance; timestamp UTC ISO-8601 có timezone.
- Lists sort/dedup theo contract; literal facts giữ trong store, KGE nhận
  entity-object triples và exclusions rõ ràng.
- Không activation từ tên phiên bản hoặc draft. Schema audit phải phát hiện
  undeclared physical contract; migration tạo artifacts/run mới.
- Pilot baseline và main freeze riêng; dependencies theo stage, không để
  boundary cuối là prerequisite của pilot.

## 3. Identity, evidence và thời gian

- Mention ID theo occurrence/body/hash/version/offsets; registry/mapping
  append-only với basis, availability, reviewer và supersession.
- Không merge tên bằng lowercase/fuzzy. Collision, conflicting decisions,
  missing proof phải pending/BLOCKED; không chọn lexical winner.
- Dùng `clean-text-identity-v1`; body hash và exact `[start,end)` span hash
  riêng. Kiểm roles và relation support; đổi normalization phải version/rebuild.
- Tách validity/observation/acquisition/ingestion/adjudication clocks.
  Observation cần proof gắn content version; không thay bằng publication/mtime.
- Acceptance là min t đủ supports và identity theo rule đã duyệt; reviewer
  execution time lưu riêng. Không invent missing clocks hoặc validity.
- Source independence dựa origin/copy evidence; support thêm không tạo graph
  change giả. Human review là phương án v1; auto-accept chỉ theo rule đăng ký.
- Correction/retraction cần evidence, LogicalFactID và chain hợp lệ.

## 4. Gemini capture và locked replay

Ngoại lệ hosted LLM chỉ cho extraction candidates. Research acquisition vẫn
theo cơ chế nguồn công khai hiện hành. Gemini không quyết định scientific
clocks, identity, acceptance hoặc gate. Registration phải bind exact config,
inventory và phạm vi trước capture; không tự mở hosted tools/search/grounding.

- Adapter Gemini riêng, JSON schema và local validation. Không fallback model.
- Khóa prompt/schema/model/parameters/API/client/input hashes; actual model
  version ghi khi có, không bịa fingerprint trọng số hosted.
- API key từ environment/secret, không đưa vào artifacts/logs.
- Chỉ gửi payload đã duyệt; không gửi gold/logs/secrets/downstream outcomes.
- Whole article, không silently truncate; over-limit review/quarantine,
  chunking cần rule/version riêng.
- Sequential capture; tối đa 3 attempts cho lỗi tạm thời, mọi attempt ghi
  usage/budget; lỗi malformed/blocked/truncated không trở thành empty claims.
- Capture lưu immutable request/response/attempts. Locked replay chỉ đọc cache
  đúng hash, không mạng. Không hứa gọi lại hosted model cho cùng bytes.
- Thiếu/hỏng cache, changed config/model hoặc vượt budget thì dừng.

## 5. Runner, gates và lộ trình execution

Entrypoint nhận đúng một stage, run, pilot/main và input manifest; không có
auto-run cả pipeline. Tách adjudication 4.11 khỏi publication 4.12. Certified
M2 API giữ guard. Structural checks, pilot quality và final G1/G2 riêng.
Gate tính lại từ artifacts, không tin JSON tự ghi PASS. Materializer kiểm
canonical inputs trước; G1 kiểm actual parity sau, tránh circular dependency.

| Chặng | Output và điều kiện qua chặng |
|---|---|
| 0 | Branch/base/inventory/baseline tests và tài liệu; bảo toàn lịch sử |
| 1 | Source restoration, exact policy approvals, full matrix, Gemini registration; thiếu authority chặn production |
| 2 | Contracts/serializers/runner/cache/validators; tests PASS, schema không mismatch/undeclared |
| 4.3 | Chỉ reconciliation discovery/coverage/108 blocks; không rerun acquisition |
| 4.4 | Verify mọi selected raw/body/receipt references, hashes/URLs/clocks/PK/FK/coverage; không suy từ 30 samples |
| 4.5 | Deterministic dedup/copy/source lineage; không mất provenance hoặc đếm URL như independence |
| 4.6 | Filter source/window/language/topic với include/exclude reasons, conservation và audit hai nhóm |
| Gate A | Source/config/input lock/lineage đúng run; audit-only release không cấp certificate |
| 4.7 | 50 bài deterministic stratified, hai annotators, ontology/domain/range/cardinality/LogicalFactID, 3 tiny snapshots |
| 4.8 | Mention/registry/mapping history và availability proofs; unresolved giữ ledger |
| 4.9 | Budget-approved Gemini capture, replay, claims/evidence/logs/manifest; exact grounding, lỗi quarantine |
| 4.10 | Temporal claims/proof/audit; scientific times có basis, không clock substitution |
| 4.11 | Every claim có decision/support/reviewer/acceptance; conflict thiếu evidence pending |
| 4.12 | Append-only facts/support/revisions, complete PK/FK/parents, không support-only duplicate graph |
| 4.13 | Independent pilot gold, đầy đủ metrics/FP/FN/denominators/coverage, approved threshold annex; FAIL không scale |
| 4.14 | Freeze components/environment/config; main corpus cùng versions, budget main approved, checkpoints nội bộ |
| Main quality | Mẫu mới khóa trước scoring; independent gold và thresholds frozen, không dùng pilot PASS thay main |
| 4.15 | Graph-change events/overlap/anchors/recurring-QA feasibility/hash; thiếu signal báo scope/targeted collection proposal |
| 4.16 | Atomic timestamp groups, event quantiles, target 10/range 8–12, earlier timestamp tie-break; không đủ thì BLOCKED |
| 4.17 | Known/accepted → validity → revision → tombstone → mapping-as-of; support/exclusions/manifests/determinism |
| 4.18 | Canonical Parquet, isolated Neo4j materialization và read-back; exact nodes/edges/counts/support equality |
| Handoff | Final G1/G2 đúng run/input hashes, Stage 4.18 PASS, inventory và certified M2 loader trên môi trường nhận |

Mỗi production stage: inspect → plan → implement → test → execute → validate
→ Stage Report → STOP. Chỉ mở stage kế khi prerequisites/PASS và explicit
request có đủ. Không mặc định bắt đầu 4.9; stage upstream chỉ được reuse khi
artifacts/contracts/producer/validation đủ điều kiện.

## 6. Verification và failure handling

- Targeted reproductions/regressions, Ruff toàn repo, full regression khi đóng
  gói. Python 3.10/3.11 compatibility và exact locks phải được kiểm chứng;
  CI code-only không cấp scientific PASS.
- Contracts: types/nullability/PK/FK/round-trip/literals. Evidence: whole-body
  vs span hash, Unicode/CRLF/roles/relation. Mapping: late aliases/collisions.
- Temporal/revisions: missing timezone/basis, future-effective/late support,
  correction/retract, missing parent/cycle/competing siblings, support-only.
- Gemini: rate/transport/budget/errors/truncation/model/cache drift; replay
  network forbidden. Resume không ghi đè outputs hoặc mất attempted requests.
- Gates: empty/stale/unmatched gold, missing strata/thresholds, wrong run,
  handcrafted PASS, required skip. Neo4j thật: extra/missing/duplicate metadata.
- Gold annotate từ bài nguồn, gồm facts extractor bỏ sót để đo recall;
  giữ nhãn độc lập và phân xử. Khóa sampling/guidelines/matching trước scoring.
- Pilot 50 bài không tự đủ coverage. Threshold annex cần values/basis/minimum
  denominators/strata/zero-denominator/PASS-FAIL-BLOCKED rules, được khóa trước
  main evaluation. Không giảm threshold theo downstream outcomes.
- Missing prerequisites → BLOCKED; observed violation → FAIL. Outputs incomplete
  không downstream-consumable. New input/config/model → new run/invalidation.
- Fresh report clocks riêng semantic data. Replay giữ engineering event times
  đã ghi như input. Không có historical evidence đủ thì báo không khả thi,
  không fabricate timestamps/facts hoặc tự mở window.

## 7. Deliverables và definition of done

Code/contracts/runners/Gemini replay/identity/time/support/gates/parity;
policy revisions/gold guidelines/threshold annex/runbook/Stage Reports;
immutable sources/claims/mappings/facts/events/boundaries/snapshots/support/
exclusions/manifests; independent quality/determinism/read-back certificates;
artifact inventory/hash/environment lock và certified M2 load.

Commits theo nhóm reviewable: docs/baseline → contracts → provenance/temporal
→ extractor → quality/gates → snapshots/parity → handoff. Không merge main.
Data lớn có storage/inventory riêng, không coi code push là artifact handoff.

DoD theo [M1 handoff requirements](M1_HANDOFF_REQUIREMENTS.md). Báo đúng
IMPLEMENTED/TESTED/EXECUTED/VERIFIED; không còn blocker mới được nghiệm thu.
Theo dõi execution tại [PROGRESS](PROGRESS.md).
