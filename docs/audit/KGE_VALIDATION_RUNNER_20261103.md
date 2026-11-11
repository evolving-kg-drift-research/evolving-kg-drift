# Quality-validation runner/preflight — 03/11/2026

Nhánh `codex/validation-remediation`. IMPLEMENTED/TESTED engineering, không
production execution. Tiếp nối [recheck](RERUN_RECHECK_AND_NEXT_STEP_20261103.md).

## Modified files

- `scripts/run_kge_validation.py`: runner Dev, read-only preflight mặc định.
- `src/kge/validation.py`: tách pure input validation dùng chung cho preflight và
  engine, thêm kiểm explicit model parameters; không đổi gradient/loss/seed rules.
- `tests/test_kge_validation_runner.py`: canonical-Parquet fixtures và workflow guards.
- `docs/PROGRESS.md` và báo cáo này.

## Contract đã triển khai

Config YAML version `quality_validation_runner_v1`, `scientific_certification=false`;
fields bắt buộc: `status`, `package_root`, `snapshot`, `snapshot_files`, `split`,
`negative_pairs`, `model`, `seeds`, `training_filter_scope`, `approval`.

- Snapshot spec gồm `snapshot_id`, `parquet_path`, timezone-aware `cutoff`, `edges`,
  `entities`; reuse canonical inspector hiện có. Cả Parquet, JSON sidecar và YAML
  manifest phải có explicit path/SHA-256 bindings trước khi inspector đọc.
- Split JSON có `version`, `train`, `validation`; enforce disjoint/exhaustive,
  unique/coverage. Negative pairs là artifact có hash, cung cấp trước execution;
  runner không tự sinh random pool hoặc chọn split theo kết quả model.
- Model phải có đủ dimension/norm/epochs/batch_size/lr/margin/entity-normalization;
  seeds chính xác 13/37/101. Không có defaults thay cho cấu hình đã review.
- Pure validator không khởi tạo weights, gọi RNG, train hoặc ghi output.
- `CANDIDATE` luôn BLOCKED cho execution. `APPROVED_DEV_STAGE` còn cần explicit
  approval artifact: `actor=user`, `scope=quality_validation_dev`, instruction và
  `design_sha256` khớp `design_identity(config)`. Design hash loại riêng approval
  ref/status để tránh circular hash; mọi execution semantics còn lại được bind.
- Không tạo approval record thật hoặc active config trong task này. Actor/instruction
  trong tests chỉ là fixture. Approval artifact phải xuất phát từ quyết định thật.

## CLI

Các ví dụ dưới đây yêu cầu thay đường dẫn bằng config đã được chuẩn bị/review;
chưa có real-pilot config hoặc negative pool mới được tạo trong lượt này.

```powershell
.venv-m1/Scripts/python.exe scripts/run_kge_validation.py --config path/to/config.yaml --check-only
```

Không có `--execute` cũng chỉ preflight. Candidate report có `executed=false`,
scope Dev, readiness/blockers và 3 prospective job configs; không tạo thư mục run.
Malformed/tampered input fail thay vì sử dụng fallback. CLI trả2 khi chưa ready.

Execution riêng, sau explicit stage request và approved design:

```powershell
.venv-m1/Scripts/python.exe scripts/run_kge_validation.py --config path/to/approved.yaml --execute --output outputs/new-validation-run
```

- Output phải là thư mục mới bên dưới `outputs/`; không overwrite run cũ.
- Persist resolved config, readiness, đủ 3 registered jobs, exact input/code copies
  trước training. Rehash trước và sau compute; changed inputs/code không finalize run.
- Mỗi seed gọi engine hiện có rồi verifier độc lập. Parent manifest bind child
  manifests/receipts, output hashes và actual commit/dirty/environment.
- Chỉ một quality-validation stage; không gọi backbone/alignment/null/drift/M4.
  Incomplete output không có final manifest, không được nhận làm completed run.
- Khóa đường dẫn `locked_test` trước đọc config/hash/payload và trước output writes.
- Đây chỉ là kiểm bytes/structure của canonical package cho scope Dev; không thay
  thế certified M1 adapter hoặc temporal/mapping gate evidence.

## Tests/evidence

Tests feature được viết trước implementation (6 setup errors do module chưa có).
Sau implementation/refactor đã sửa missing local bindings được tests phát hiện,
không đổi thresholds hoặc bỏ assertions để pass.

Final **688 passed, 10 skipped**, Python3.11.9, 45.36s; Ruff/diff PASS.
Full log: `outputs/validation_runner_20261103_full.log`.

7 runner cases kiểm:

1. Check-only không gọi training và không tạo outputs.
2. Locked config bị reject trước bất kỳ hash read nào.
3. Approved fixture stage thực hiện đủ 13/37/101, lưu jobs + independent receipts;
   lặp cùng output directory bị reject.
4. Missing approval, wrong hash, changed epoch budget sau approval và locked split
   đều fail trước output allocation.

Các loss/ranking/checkpoint regression trước tiếp tục PASS. Chỉ synthetic fixtures
được train; không dùng canonical research data để chạy thử model.

## Verification tiers và việc còn lại

- IMPLEMENTED/TESTED: runner/preflight/file-backed fixtures và independent receipts.
- EXECUTED production: NO. Scientific VERIFIED: NO. Python3.10 chưa chạy local.
- 10 skipped scaffolds còn nguyên, không dùng để cấp gate PASS.
- Không đổi schema M1, protocol, sources lock, decision log hoặc diagnostics values.

Bước tiếp theo là chuẩn bị **candidate pilot package** để review: snapshot T01
data3.1, versioned explicit memberships (existing101/20 chỉ là validation đã từng
được dùng), fixed negative-pool artifact/recipe, training filter scope và epoch
budget/selection policy. Sau khi chốt mới tạo approval binding thật và chạy
check-only trên package đó; không tự chạy 30 backbone jobs hoặc independent test.
M1 schema/measurement registration/pseudo/H2 blockers của full scientific rerun
không được coi là đã giải quyết bởi runner Dev này.

Diff: `git diff -- src/kge/validation.py docs/PROGRESS.md`; runner/test/report mới
chưa stage, xem `git status --short`. Không commit/push.
