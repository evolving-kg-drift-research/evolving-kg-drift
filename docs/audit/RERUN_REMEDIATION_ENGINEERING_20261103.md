# Rerun remediation — engineering batch 1 — 03/11/2026

Nhánh: `codex/validation-remediation`, base `eadf22abc436dcbe2f12ae850ed9a5e4382dc714`.
Theo [kế hoạch](../PRE_RERUN_REMEDIATION_PLAN_20261103.md) và
[audit](PRE_RERUN_CODEBASE_REVIEW_20261103.md). Chưa commit/push.

## Kết quả và phạm vi

Đã triển khai guards P0, checkpoint integrity P2, sửa split/RNG/loss ở P3 và một
validation engine Dev có file-backed logs/checkpoints + independent verifier
cho P4. P1 có shared manifest/binding contract và chặn các entrypoints bỏ qua
registration. P6 mới có complete-support helper đã test; chưa có producer M4 mới.

Không thay model TransE-L2, seeds 13/37/101, protocol, sources lock, scientific
thresholds, schema M1 hoặc decision log. Không train trên dữ liệu thật, không
acquisition, không mở `data/locked_test/`, không kết nối Neo4j.

## Files đã chỉnh sửa/bổ sung

| Nhóm | Files |
|---|---|
| Checkpoint/training | `src/kge/checkpoint.py`, `src/kge/model.py`, `src/kge/trainer.py` |
| Canonical splits và epoch validation mới | `src/kge/splits.py`, `src/kge/validation.py` |
| Independent validation verifier mới | `scripts/verify_kge_validation.py` |
| Shared manifest/input contract | `src/kg_pipeline/experiment_manifest.py`, `scripts/inspect_m2_inputs.py` |
| Complete support | `src/evaluation/support.py` |
| Retired unsafe entrypoints | `scripts/import_to_neo4j.py`, `scripts/run_m4_evaluation_and_stats.py`, `scripts/run_m2_null_v2_all_transitions.py`, `scripts/run_m2_drift_v2_all_transitions.py` |
| Reproductions/integration mới | `tests/test_rerun_hardening.py`, `tests/test_kge_validation_workflow.py`, `tests/test_remediation_contracts.py` |
| Consumers/tests cập nhật | `tests/test_kge_training.py`, `tests/test_legacy_training_observer.py`, `tests/scientific/test_transe_mechanics.py` |
| Trạng thái/bàn giao | `docs/PROGRESS.md`, báo cáo này |

Plan và audit untracked đã có trước lượt coding này được giữ nguyên. Thay các
entrypoints cũ bằng lỗi rõ ràng là deliberate compatibility break đã nêu trong
kế hoạch: không tiếp tục global DB delete, Gaussian pseudo, implicit stage advance
hoặc silently dùng run tháng 10. Historical outputs/code copies vẫn được giữ.

## Chi tiết thay đổi

### Checkpoint

- `verify_sidecar=True` yêu cầu sidecar tồn tại, format/name/hash khớp. Filenames
  có spaces được hỗ trợ. Semantic hash và vector dimension được kiểm khi load.
- Save kiểm finite/dimension/semantic hash và dùng exclusive artifact lock;
  immutable save từ chối checkpoint/sidecar đã tồn tại, kể cả orphan sidecar.
- Giữ nguyên v1 provenance serialization và phép hash/rounding để đọc lịch sử.
  Không thêm default fields làm đổi semantic hash v1.

### Split, RNG, loss

- Coverage-preserving split keyed bằng canonical triples, kế thừa thứ tự hash và
  greedy procedure của pilot; lưu memberships/version/split hash trong metrics.
- Yêu cầu validation nhưng không tạo được nonempty disjoint/exhaustive partition
  hoặc coverage không đủ thì fail. Invalid ratio/nonpositive epoch budget fail.
- Dev config identity chứa split, requested ratio, evaluation version và declared
  snapshot positive-filter policy. Full-snapshot helper giữ model config hash cũ.
- Validation RNG riêng, reset để cùng negative draws mỗi epoch; thay đổi mức tiêu
  thụ random của validation không đổi weights training. Không bật early stopping.
- Lưu positives/usable/skipped/margin-violations/loss-sum; giữ nguyên định nghĩa
  online training loss chia số positives. Zero usable không còn báo successful 0.
  Validation ghi usable/skipped counts và fail nếu zero usable.
- Dimension helper không còn lấy training loss thay final validation loss.
- Generic helper giữ snapshot-positive filtering đã có và ghi rõ policy. Engine
  mới yêu cầu explicit `training_filter_scope`; không tự đăng ký scope scientific.

### Validation engine Dev và verifier

`kge.validation.train_validation_run` yêu cầu explicit split, fixed negative pairs,
positive filter và training-filter scope; không có default production split/budget.
Chỉ ghi `scientific_certification=false`, role `quality_validation`.

- Validate partitions/pairs/filter/seed và git identity trước tạo run directory.
- Lưu design trước train; mỗi epoch ghi online train loss, validation loss trên
  fixed pairs, MRR/Hits@1/3/10, raw head/tail ranks, sample diagnostics và checkpoint.
- Candidate universe, filter, split, negative pairs, model config và fixed-budget
  policy nằm trong design hash. Checkpoint snapshot identity là **train partition**,
  không giả thành full-snapshot backbone.
- Outputs exclusive-create; checkpoint mọi monitored epoch, không overwrite best
  weights. Không đọc/chấm independent final test và không chọn epoch theo test.
- Sao lưu exact producer source bytes và hashes; manifest có actual git/dirty,
  model seed, data/split/config/mapping/query identities và output hashes.
- Verifier dùng NumPy tính lại khoảng cách/loss và sorted-rank positions từ vectors,
  không gọi evaluator producer; kiểm split/design/epoch/checkpoint lineage và
  manifest hashes. Có test sửa validation loss rồi rehash manifest vẫn bị phát hiện.
- Verifier chỉ xác minh fixed validation losses/ranks/lineage; không độc lập replay
  online gradient trajectory hoặc certify temporal validity/upstream data.

Engine này là API Development, **chưa phải production CLI đã registered**. Chưa
tích hợp curves mới vào HTML report cũ, chưa có selection/final-test orchestration.
Không dùng checkpoint Dev này thay scientific backbone trước approved design.

### Manifest/support và entrypoints

- Contract validator/bound-file helper dùng schema hiện hành; strict mode reject
  commit alias, malformed hashes, path escape và locked-test path. Historical
  fixture runners giữ basic validation mode; không tuyên bố tất cả old producers
  đã chuyển sang strict scientific contracts.
- Complete-support helper deduplicate supports, require available + finite data;
  missing/partial support trả null/eligibility=false + reason, không điền 0.
  Chưa nối vào production M4 runner mới vì scientific design chưa registered.
- Hai v2 wrappers cũ dừng trước đọc inputs/tạo outputs và chỉ hướng đến guarded
  `run_m2_measurement_v2.py` với registered config/input plan. Không rewrite code
  copies trong old runs và không đổi thresholds để làm readiness PASS.
- Combined M4 và legacy Neo4j import bị vô hiệu hóa trước side effects; code tạo
  Gaussian pseudo và query global-delete đã bị loại khỏi active entrypoints.

## Kiểm thử và bằng chứng

Reproduce first: 8 hardening tests fail trên code cũ; 2 wrapper tests tái hiện
đường đọc implicit old runs; 3 validation workflow tests ban đầu thiếu feature.
Sau sửa, các assertions về lỗi/lineage/independent ranking đều đạt.

- Full suite final: **674 passed, 10 skipped**, Python **3.11.9**, 39.23 giây.
- Targeted sau checkpoint/validation changes: 14 passed. File-backed workflow
  chạy cả seeds **13/37/101**, mỗi seed hai runs, checkpoint bytes identical.
- Ruff toàn repo: PASS. `git diff --check`: PASS (Git thông báo normalize CRLF
  trên một số scripts; không là lint/whitespace failure).
- G1 code conformance: **4 passed**, output explicit không certify scientific G1.
- Đối chiếu riêng **42 protected input hashes**: không đổi.
- **176 backbone artifact hashes**: không đổi. Strict-load **60/60 historical
  checkpoint files** thành công, chỉ xác nhận integrity/v1 compatibility.

Logs: `outputs/remediation_20261103_final_full.log` và
`outputs/remediation_20261103_verification/` (preservation, Ruff, G1 code và manifest).

Lệnh chính:

```powershell
.venv-m1/Scripts/python.exe -m pytest -q -rs -p no:cacheprovider --basetemp=outputs/remediation_20261103_final_full
.venv-m1/Scripts/python.exe -m ruff check . --no-cache
.venv-m1/Scripts/python.exe scripts/verify_g1.py --ci --code-checks
```

Không chạy lại bằng cùng basetemp để tránh xóa test evidence cũ; dùng thư mục mới.
Atomic checkpoint test chuyển temp vào `tmp_path` của workspace. Các tests từng
đòi successful zero loss khi sampling exhausted được đổi sang fatal error +
unchanged weights/trace restoration; không đổi threshold hoặc gradient để pass.

Red wrapper tests chặn `inspect_package` bằng mock; bản code cũ đã tạo hai empty
output directories trước khi mock abort, không đọc canonical data hoặc chạy stage.
Giữ lại: `outputs/m2_null_v2/20261103T144042Z_d5e9b4e1/` và
`outputs/m2_drift_v2/20261103T144042Z_6d33b8e8/`. Chúng không là completed runs và
không có manifests/metrics. Tests sau đó bind output root vào tmp_path.

## Trạng thái 14 findings

| Finding | IMPLEMENTED/TESTED trong batch này | EXECUTED/VERIFIED và remaining blockers |
|---|---|---|
| RERUN-01 | Guard retired combined runner; Gaussian replacement removed | Chưa empirical pseudo estimator/producer; cần D07 |
| RERUN-02 | Complete-support helper + partial/missing/nonfinite tests | Chưa production M4 integration/panel eligibility verification |
| RERUN-03 | Retired runner không còn sinh misleading H2 summary | Secondary population và frozen query/candidate design chưa implement/register |
| RERUN-04 | Independent validation stream + observer isolation tests | Chưa real-data validation run |
| RERUN-05 | Coverage/partition validation fail-closed | Cần approved memberships/population trước real train |
| RERUN-06 | Dev split/design hash, explicit new-engine role/inputs | Chưa registered scientific training design |
| RERUN-07 | Sample accounting + fatal zero usable; denominator preserved | Old logs không có skip counts; không suy ngược old train efficacy |
| RERUN-08 | Strict physical/semantic/dimension checks + lock/tests | Historical v1 integrity/compatibility kiểm riêng 60 files; không certify training quality |
| RERUN-09 | Retired implicit v2 wrappers, bound-file helper | New registered backbone/measurement configurations/preflight còn thiếu |
| RERUN-10 | Strict shared validator + valid new Dev manifests | Chưa thay mọi historical producer; không backfill old provenance |
| RERUN-11 | Combined Stage 8→9 path bị chặn | Hai production runners/receipts riêng cần hoàn thiện sau scientific design |
| RERUN-12 | Không đổi schema/semantics | 9/17 field mismatches và physical declarations còn BLOCKED |
| RERUN-13 | Không tự chọn threshold hoặc sửa protocol/ledger | Registration, D-DIAG conflict, WCB/controls và design decisions còn pending |
| RERUN-14 | Legacy DB entrypoint dừng trước connection; regression PASS | Không real DB operation/parity verification |

Không finding nào được gán RESOLVED toàn bộ phạm vi khoa học. 10 hard-invariant
scaffolds vẫn skipped, không dùng full-suite PASS làm scientific gate PASS.
Python 3.10 chưa chạy local. Independent final-test validity, new M4 stages,
readiness integration và HTML report integration chưa được xác minh.

## Bước còn cần trước real rerun

Theo AGENTS §2.2, không tự quyết scientific population, temporal/schema meanings
hoặc ngưỡng đang mâu thuẫn. Cần chốt các mục D01–D09 áp dụng trong kế hoạch trước
activation. P5 schema/registration và phần scientific P6 chưa thể được coi là đã
hoàn tất từ batch guards này. CORE invariant/CI integration P7 còn cần hoàn thiện.

Diff reference: `git diff -- src/kge scripts tests docs/PROGRESS.md` và
`git status --short` để thấy các file mới chưa stage. Source/config/test/report
hashes của batch được bind trong completion manifest; không commit/push.

**Tiers:** IMPLEMENTED/TESTED engineering như trên; EXECUTED **không có production**;
VERIFIED chỉ fixture numerical replay và preserved historical integrity. Không
auto-advance scientific stage.
