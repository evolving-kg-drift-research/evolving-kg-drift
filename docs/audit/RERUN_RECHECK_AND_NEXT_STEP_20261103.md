# Recheck và bước tiếp theo — 03/11/2026

Nhánh `codex/validation-remediation`; tiếp nối engineering batch 1.
Phạm vi: kiểm tra lại kết quả sửa và xác định công việc tiếp theo; không chạy
training/pipeline trên dữ liệu thật hoặc đổi scientific registration.

## Trạng thái kiểm lại

- Trước follow-up patch: toàn bộ input/patch hashes trong completion manifest
  batch 1 khớp checkout; Ruff PASS; 22 targeted tests PASS.
- Adversarial checks trên **bản sao synthetic fixture runs** phát hiện verifier
  còn nhận metadata không đúng hoặc artifacts không được bind đầy đủ. Không sửa
  fixture originals hoặc research artifacts để tái hiện.
- Thêm 7 regression cases: **7 failed, 6 passed** trước patch; workflow/contracts
  sau patch **19 passed**.
- Full suite sau patch: **681 passed, 10 skipped**, Python3.11.9, 46.13s.
  Ruff và `git diff --check` PASS. Không coi skipped scaffolds là scientific PASS.
- Source readiness của guarded M2 registration vẫn true; registration trả BLOCKED
  với 12 reasons. Schema M1 vẫn 9/17 bảng thiếu/lệch fields.

## Findings và sửa bổ sung

### RECHECK-01 — HIGH — Input identity và consumed artifacts chưa được bind đầy đủ

- **Affected files:** `scripts/verify_kge_validation.py`,
  `tests/test_kge_validation_workflow.py`. Liên quan RERUN-06/10 trong audit trước.
- **Expected:** verifier recompute dataset/query/mapping identities và yêu cầu
  mọi file được sử dụng có physical hash trong manifest. Valid hash syntax không
  thay cho identity equality.
- **Actual trước patch:** đổi query/entity/relation hashes thành 64 số 0 vẫn báo
  `SAVED_VALIDATION_CHECKS_PASS`. Bỏ `epoch_log.json` hoặc checkpoint sidecar khỏi
  manifest vẫn được đọc và chấp nhận.
- **Evidence:** `outputs/recheck_next_step_20261103_probes/results.json`; probes
  sao chép fixture outputs trước sửa, không đọc/chỉnh production data.
- **Root cause confirmed:** chỉ kiểm format và listed artifacts, chưa kiểm tất
  cả declared identities hoặc coverage của các files thực sự tiêu thụ. Không là
  giả thuyết về checkpoint lịch sử bị thay đổi.
- **Reproduction:** chạy các tests
  `test_verifier_checks_declared_input_identity` và
  `test_verifier_requires_all_consumed_artifacts_bound` trên revision trước patch.
- **Minimal fix implemented:** đối chiếu data/snapshot/query/entity/relation/config
  hashes; seed/role/design version; require design/log/epoch checkpoint/sidecar/
  ranks/source-copy bindings. Kiểm code hashes, checkpoint mappings/keys và full
  epoch/design/split provenance. Kiểm population/validity của fixed negative pairs.
- **Regression:** 4 parametrized input-hash cases và 2 unbound-file cases fail→pass;
  existing saved-ranking/loss replay tests vẫn PASS cho seeds 13/37/101.
- **Status:** IMPLEMENTED/TESTED. Chưa production EXECUTED/VERIFIED; không đóng
  toàn bộ RERUN-10 vì các producer/handoff khoa học khác còn thiếu.

### RECHECK-02 — MEDIUM — Thiếu kiểm online loss/sample accounting

- **Affected files:** cùng hai files trên; liên quan RERUN-07.
- **Expected:** online training log có finite values và mẫu số đúng định nghĩa;
  counts cân bằng, không chỉ recompute validation loss/rank.
- **Actual trước patch:** sửa online training loss thành 123456 và bỏ log khỏi
  manifest, hoặc rehash entry log, verifier vẫn báo PASS.
- **Evidence/root cause:** probe `unbound_changed_train_log` và regression
  `test_verifier_checks_online_loss_accounting`. Confirmed verifier chưa kiểm
  `online_train_loss = loss_sum / positives` và các count constraints.
- **Reproduction:** test mới trên source trước patch, với fixture copy duy nhất.
- **Minimal fix implemented:** check finite/nonnegative loss sum, integer sample
  counts, positives đúng train partition, usable/skipped/violations nhất quán,
  loss-definition version và validation observation count; so lại online mean.
- **Regression:** log bị sửa và manifest được rehash vẫn fail; genuine runs PASS.
- **Status:** IMPLEMENTED/TESTED. Đây là kiểm internal accounting + storage binding,
  **không** độc lập replay toàn bộ SGD trajectory; giới hạn này giữ trong verifier.

Không thay ngưỡng scientific/numerical acceptance, split population, optimizer,
seed hoặc loss definition để làm tests pass. Không sửa schema/protocol/ledger.

## Bước tiếp theo được ưu tiên

**Hoàn thiện runner/preflight cho `quality_validation`, kết hợp phần còn lại của
P1/P4 và CORE contract tests P7; chưa chạy full 30 backbones.**

Lý do: engine và verifier đã có fixture evidence, nhưng hiện vẫn là API Dev.
Thiếu entrypoint nhận registered design + canonical input descriptors và trả
readiness trước khi tạo training jobs. M1 migration, empirical pseudo và H2 là
các luồng tiếp theo cho full scientific rerun, không cần biến thành prerequisite
để viết/test preflight cho một diagnostic pilot.

### Phạm vi công việc kỹ thuật kế tiếp

1. Một input plan riêng cho `quality_validation`: canonical snapshot và manifest/
   mapping refs, explicit split artifact, fixed negative pool, candidate/filter
   identities, role/model/seeds/epoch budget và exact executed-code hashes.
2. `check-only` preflight: verify bindings/coverage/as-of handoff của scope được
   duyệt; không train, không chọn latest run hoặc dùng run path cũ ngầm định;
   thiếu đăng ký thì báo BLOCKED với reasons.
3. Bind 3 seed jobs trước execution; nối engine hiện có với manifest và independent
   receipts; không auto-advance sang full backbone/alignment/null/drift/M4.
4. Thêm negative handoff tests và thay CORE invariant scaffolds đã có module bằng
   meaningful fixtures. Không xóa skip để giả scientific gate PASS.
5. Tạo candidate review package; production execution chỉ sau explicit stage
   request và quyết định scientific cần thiết theo AGENTS §2.2/§8.2.

### Candidate nhỏ có thể chuẩn bị để review

| Thành phần | Evidence hiện tại / giới hạn |
|---|---|
| Snapshot | T01 của `data/evolving_kg_downstream_v3_1`, SHA-256 `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e` |
| Existing split | `outputs/m2_pilot/20261014T031822Z_9b722664/split.json`; SHA-256 `f7460e0aec0261b6341d334b95cfd6c7613287a631e59a8e63bcbe143b4ff29d` |
| Feasibility kiểm lại | 101 train / 20 validation, disjoint; union khớp toàn T01 hiện hành |
| Model baseline để review | TransE-L2 d64, seeds13/37/101, lr0.01, margin1, fixed50 epochs là cấu hình lịch sử; chưa tự đăng ký new-run design |
| Logging | Mỗi epoch: train diagnostics, fixed-pair validation loss, MRR/Hits, checkpoint và ranking rows |
| Cần chốt trước train | Scope diagnostic/scientific, split reuse và coverage claims, explicit negative-pool seed/recipe/filter policy, budget/selection rule, test-use history |
| Independent final test | Split trên đã dùng cho validation/model selection; không đổi tên thành independent test hoặc dùng kết quả để certify generalization |

Source lock hiện khớp sau amendment; không cần lặp lại blocker nguồn đã supersede.
Full M1→M4 vẫn cần approved schema, actual gate/handoff evidence, measurement
registration, D-DIAG conflict resolution và scientific designs D07–D09.

## Handoff

Files thay đổi ở follow-up này: verifier, validation workflow tests,
`docs/PROGRESS.md` và report này. Diff: `git diff -- scripts/verify_kge_validation.py
tests/test_kge_validation_workflow.py docs/PROGRESS.md`; hai code files mới vẫn
untracked từ batch trước nên xem thêm nội dung files/`git status --short`.

Tiers: IMPLEMENTED/TESTED follow-up engineering; không new production EXECUTED,
không scientific VERIFIED. Chưa commit/push, chưa train dữ liệu thật.
