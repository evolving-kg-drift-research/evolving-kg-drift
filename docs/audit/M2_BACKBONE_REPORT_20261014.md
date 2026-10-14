# M2 — resolved Dev configuration và backbone stage — 14/10/2026

Nhánh `codex/m2-drift-workflow`; base commit `2860235`. User xác nhận
**"Hãy thực hiện kế hoạch trên."** sau pilot/proposal.

## Bước 3 — cấu hình đã chốt

Active Dev config: `configs/m2_external_dev_v1.yaml`. Hash-bind proposal
`configs/m2_run_proposal.yaml` với SHA-256
`4b959e4f86191bef7545697ea804a0a7e379336a28d3c44681b6a87d61d264b6`.
Giữ nguyên proposal ban đầu; mọi scientific/measurement values bằng proposal
đã duyệt. Model TransE-L2 dimension 64, seeds 13/37/101, 50 epochs,
learning rate 0.01, margin 1, normalized entity vectors, train từ đầu cho từng
snapshot/seed và replay hai lần. Full snapshot training không chia validation.
Các tham số alignment/null/drift đã có giá trị nhưng chưa execute ở stage này.

Serialization detail được sửa trong active config: quote key `'null'` vì
unquoted `null:` của proposal ban đầu được PyYAML đọc thành None key. Guard
chỉ normalize key đó khi so sánh; giữ bytes/hash của proposal và giá trị tham
số nguyên vẹn. Hai null sections cạnh tranh bị từ chối bằng regression.

Runtime `TransEConfig` được lưu đầy đủ trước training, gồm field batch_size 32
sẵn có của backbone. Code trainer hiện huấn luyện per-triple; không thay
optimizer/batching behavior trong lượt này.

## Bước 4 — stage runner và checks

`scripts/run_m2_backbone.py`: chỉ backbone training, không chain alignment,
null, drift hoặc QA. Preflight và pilot manifests phải khớp artifacts thật;
dimension phải khớp independent pilot selection. Bind inputs và 30 jobs trước
execution; copy exact code bytes và resolved config; checkpoint append-only
trong output directory mới; 30 per-seed manifests và aggregate run manifest.

`scripts/verify_m2_backbone.py`: kiểm raw JSON/sidecar bytes riêng, full
entity/relation mappings từ Parquet, config/seed/snapshot/git provenance,
finite dimensions/50-epoch loss history/no validation split, semantic hash,
duplicate/missing jobs và nested per-seed manifests. T01/T02 còn phải khớp
exact checkpoint bytes của equivalent full-snapshot pilot 64 chiều.

Trước execution, targeted tests đạt **55 passed** trên Python 3.11.9, gồm
unapproved-config changes và artifact tampering, wrong mapping/snapshot/config,
missing sidecar, invalid loss/dimension/non-finite vector rejection. Lượt đầu
phát hiện YAML null-key representation và fail trước execution; sửa serializer
binding bằng regression, không thay scientific values hoặc bỏ test.

Full repository regression: **444 passed, 10 skipped** trong 17,72 giây,
Python 3.11.9. Lệnh: `.venv-m1/Scripts/python.exe -m pytest -q -rs -p
no:cacheprovider --basetemp=outputs/m2_backbone_full_regression_20261014`.
10 skips có sẵn ở `tests/test_hard_invariants.py:149–196`: các placeholder
KGE/alignment/null/drift/QA/path/locked-workflow; không dùng các skips để cấp
gate PASS. Stage backbone có tests và independent real-artifact verifier riêng.
Ruff toàn repo PASS. Python 3.10 chưa chạy local.

## Execution/validation

Run: `outputs/m2_backbone/20261014T034042Z_65c464ba/`.
Lệnh execution: `.venv-m1/Scripts/python.exe scripts/run_m2_backbone.py`.
Stage hoàn tất 30 snapshot/seed configurations, 60 independent training
executions trong 160,32 giây, 64 chiều, 50 epochs/configuration. Cả 30 cặp
replay checkpoints byte-identical; embeddings/losses finite, mapping và
serialization/hash checks PASS. Không warm-start hoặc dùng weights pilot.

| Snapshot | Triples | Entities | Final loss seed 13 | Seed 37 | Seed 101 |
|---|---:|---:|---:|---:|---:|
| T01 | 121 | 167 | 0.413035 | 0.416826 | 0.388088 |
| T02 | 247 | 343 | 0.446933 | 0.415828 | 0.428103 |
| T03 | 362 | 503 | 0.413484 | 0.447399 | 0.436178 |
| T04 | 483 | 646 | 0.460287 | 0.436080 | 0.436768 |
| T05 | 604 | 787 | 0.450256 | 0.454663 | 0.459602 |
| T06 | 724 | 936 | 0.464814 | 0.465955 | 0.454492 |
| T07 | 844 | 1057 | 0.471915 | 0.478332 | 0.488443 |
| T08 | 964 | 1176 | 0.498366 | 0.470168 | 0.468138 |
| T09 | 1084 | 1282 | 0.473590 | 0.475009 | 0.475839 |
| T10 | 1205 | 1389 | 0.465831 | 0.477746 | 0.472926 |

Training losses chỉ là diagnostics; không xem chúng là QA quality, drift,
significance hoặc scientific gate certification.

Lệnh validation: `.venv-m1/Scripts/python.exe scripts/verify_m2_backbone.py
--run outputs/m2_backbone/20261014T034042Z_65c464ba`.
Report `independent_verification_20261014T034333Z_cea99585.json`:

- 41/41 input hashes và 176/176 artifact hashes khớp.
- 30/30 per-seed manifests bind đúng checkpoints/config/mapping/git/input
  lineage; đầy đủ 50 epoch losses/config, không validation split.
- 30/30 cặp replay exact bytes, sidecars và checkpoint semantic hash đúng.
- 6/6 primary T01/T02 checkpoints khớp bytes với full-snapshot pilot 64 chiều
  đã được train trước đó trong cùng môi trường/parameters/provenance.
- Entity norm range toàn bộ models: 0.9999999999999993–1.0000000000000004.
- Input Parquet/sidecars/manifests và code bytes không đổi trong execution.

Aggregate manifest SHA-256:
`f4f8771a58cdf0f05ac6ca203c315ab364be6adcde8e9d08200324d729ec8354`.
Đã lưu resolved configuration, runtime model configs, registered jobs,
mappings, source-code copies/hashes, checkpoints/sidecars, 30 seed manifests,
summary và aggregate experiment manifest trước independent verification.

## Engineering finding M2-BB-001 — LOW — YAML null-section key

- **Affected:** `configs/m2_run_proposal.yaml`, `configs/m2_external_dev_v1.yaml`,
  `scripts/run_m2_backbone.py`.
- **Expected:** null-distribution section được nhận dạng thống nhất để bind
  active config với approved proposal; không thay tham số đã duyệt.
- **Actual/evidence:** PyYAML đọc unquoted `null:` thành None key. Reproducing
  approval-binding test fail `Resolved design differs from the approved
  proposal: null` trước bất kỳ training execution nào.
- **Confirmed root cause:** YAML key resolution, không phải khác giá trị M2;
  không có unverified hypothesis.
- **Reproduction:** load proposal bằng `yaml.safe_load`, kiểm None có trong
  top-level keys; chạy `test_design_is_hash_bound_to_approved_proposal` trên
  runner trước patch.
- **Minimal fix:** quote `'null'` trong active config; normalize riêng key None
  của immutable historical proposal trước so sánh, reject ambiguous duplicate
  sections. Không rewrite proposal/hash hoặc đổi thresholds.
- **Regressions:** approval-binding test và
  `test_ambiguous_yaml_null_sections_are_rejected` trong
  `tests/test_m2_backbone_workflow.py`.
- **Status:** IMPLEMENTED + TESTED; production dataset/schema không bị tác
  động. Approved configuration binding và execution được verify trong stage.
- **Remaining blockers:** không còn cho backbone; các stage alignment/null/
  drift chưa thực thi trong lượt này.

## Verification tiers và bàn giao stage

**IMPLEMENTED:** approved Dev config, one-stage runner và verifier riêng.
**TESTED:** targeted 55 passed; full suite 444 passed/10 skipped; Ruff toàn
repo và diff whitespace checks PASS trên Python 3.11.9.
**EXECUTED:** backbone Dev stage trên 10 snapshots thật, 30 configs/60 executions.
**VERIFIED:** independent saved checkpoint/mapping/config/loss/lineage/hash
checks nêu trên; chỉ phạm vi backbone Dev, không scientific G3/M1 certification.

Thay đổi mới trong lượt này: `configs/m2_external_dev_v1.yaml`,
`scripts/run_m2_backbone.py`, `scripts/verify_m2_backbone.py`,
`tests/test_m2_backbone_workflow.py`, báo cáo này. Cập nhật
`docs/M2_EXECUTION_PLAN.md` và `docs/PROGRESS.md`; giữ mọi phần M1 có sẵn.
Diff tracked: `git diff -- docs/PROGRESS.md`; code/docs mới còn untracked,
chưa commit/push. Dữ liệu/generated outputs không được stage.

Bàn giao sang stage alignment: checkpoint paths trong `summary.json`,
hash-addressed experiment manifest, verification report và approved Dev
config. Alignment cần runner/fixtures cho fixed-count stratification 101/66,
degree allocation tie-breaking, đầy đủ 9 transitions và every-pair validity.
Không đổi anchors hoặc thresholds theo drift/QA outcomes.

## Giới hạn và điểm dừng

Phạm vi là M2 Dev trên gói external có thật theo user-authorized M1 exception;
không tự chứng nhận historical identity/temporal semantics hoặc G3.
Python 3.10 local, alignment trên 9 transitions, pooled null/LTO/SED+ và M4
chưa execute/verify. Theo active config `next_stage_only: backbone_training`
và AGENTS.md §8.2, STOP sau báo cáo backbone trước bước alignment.
