# M2 — alignment stage — 14/10/2026

Nhánh `codex/m2-drift-workflow`; base `2860235`. Người dùng yêu cầu
**"Hãy làm bước này."** sau mô tả alignment cho cả 9 transitions.
Stage config `configs/m2_alignment_v1.yaml` bind approved Dev config SHA-256
`7d43c3f4260ee47bf12ce374b85cff21a5ac933a6d976b311d23ceb724766765`
và backbone manifest `f4f8771a58cdf0f05ac6ca203c315ab364be6adcde8e9d08200324d729ec8354`.
Không sửa các configs/input artifacts của stage backbone đã hoàn tất.

## Thiết kế trước execution

- Input: 30 verified primary checkpoints của backbone run
  `outputs/m2_backbone/20261014T034042Z_65c464ba/`, seeds 13/37/101, 64 chiều.
- 9 adjacent transitions, mỗi transition có 3 parallel-seed cross-time và
  6 within-snapshot cross-seed comparisons (3 tại mỗi endpoint): **81 comparisons**.
- Một bộ 101 fit / 66 holdout anchors cho tất cả 9 comparisons của transition;
  universe = persistent IDs, stratification chỉ bằng degree snapshot trước.
  Degree của endpoint sau không tham gia selection/conditioning.
- Allocation implementation version `fixed_degree_joint_sample_then_split_v1`:
  proportional largest-remainder quotas cho joint sample 167 từ toàn persistent
  pool; tiếp tục largest-remainder quotas cho 101 fit từ sample, 66 holdout là
  phần còn lại. Quota ties ưu tiên degree nhỏ; ID order theo
  SHA-256(salt:transition:degree:degree_value:entity_id), tie theo ID.
  Chi tiết engineering này được ghi trước outcomes, không đổi counts/thresholds
  đã duyệt và không nhìn embeddings, fact-change labels, drift hoặc QA.
- Ghi cả 9 plans/IDs/hashes/degree allocations và 81 jobs trước SVD đầu tiên.
- Fit-only centering; Q = U Vᵀ; diagnostics theo core implementation.
  Gọi validity với rank tối thiểu **64**, max gap **1.0**, max holdout RMSE
  **2.0**, max orthogonality **1e-4** theo approved config, không dùng default
  half-rank criterion cho stage này.
- Missing/duplicate anchors, inconsistent dimensions/identity hoặc non-finite
  vectors/outputs phải fatal. Invalid diagnostics lưu unavailable/reason;
  không tạo SED+/null hoặc nâng threshold để tạo PASS.
- Chạy hai lần mỗi comparison, so exact JSON bytes; artifacts append-only,
  81 per-alignment manifests và aggregate manifest nối checkpoint/input/code/
  config/anchor hashes. Dừng sau Stage Report, không auto-execute null/drift.

## Engineering verification trước execution

Targeted workflow + Procrustes/centered cosine/unavailable regressions:
**23 passed**, Python 3.11.9; Ruff toàn repo PASS. Fixtures bao phủ fixed counts,
integer largest remainder/ties/zero strata, insufficient/duplicate/missing degree,
order invariance, fractional independent allocation, missing seeds/holdout,
known rotation+translation, rank deficiency, excessive holdout gap, fit-only
means và rejection của saved Q/mean/rank/availability/identity tampering.

Independent verifier reconstruct anchors bằng Fraction arithmetic và tính
SVD/means/rank/objective/residuals/orthogonality bằng NumPy riêng, không gọi
core aligner hoặc anchor allocator. Check cả availability/reason theo config
đã chốt, checkpoint hashes và per-alignment manifests.

## Execution và independent validation

Run: `outputs/m2_alignment/20261014T040001Z_96d9ccbc/`.
Execution command: `.venv-m1/Scripts/python.exe scripts/run_m2_alignment.py`.
Đã chạy **81 comparisons × 2 repeats = 162 SVD executions** trong 25,64 giây.
Cả 9 transitions có đúng 101 fit / 66 holdout anchors, không overlap; pool sizes
lần lượt 167, 343, 503, 646, 787, 936, 1.057, 1.176, 1.282. Tất cả 81 results
available theo thresholds đã chốt; 81/81 repeat pairs **exact JSON bytes**.

| Transition | Min rank / 64 | Max holdout RMSE | Max absolute gap | Available |
|---|---:|---:|---:|---|
| T01→T02 | 64 | 1.296854 | 0.509983 | 9/9 |
| T02→T03 | 64 | 1.380451 | 0.574474 | 9/9 |
| T03→T04 | 64 | 1.379977 | 0.559299 | 9/9 |
| T04→T05 | 64 | 1.398636 | 0.580387 | 9/9 |
| T05→T06 | 64 | 1.382857 | 0.563518 | 9/9 |
| T06→T07 | 64 | 1.404725 | 0.571767 | 9/9 |
| T07→T08 | 64 | 1.398808 | 0.556214 | 9/9 |
| T08→T09 | 64 | 1.400225 | 0.560565 | 9/9 |
| T09→T10 | 64 | 1.397523 | 0.570237 | 9/9 |

Global max orthogonality error **2.198345e-14** (<1e-4). Rank 64 ở mọi
comparison, holdout RMSE tối đa 1.404725 (<2.0), gap tối đa 0.580387 (<1.0).
Không đổi diagnostic thresholds sau khi nhìn kết quả. Operational PASS không
chứng minh displacement vượt retraining noise; câu hỏi này cần null stage.

Independent validation command: `.venv-m1/Scripts/python.exe
scripts/verify_m2_alignment.py --run outputs/m2_alignment/20261014T040001Z_96d9ccbc`.
Report: `independent_verification_20261014T040130Z_31179f1c.json`.

- Reconstruct cả **9/9 anchor plans** bằng fractional arithmetic từ persistent
  IDs và degree của snapshot trước; exact ID roles/quotas/hashes khớp.
- Recompute **81/81 SVD results** bằng NumPy riêng: fit-only means, Q,
  singular values/rank, optimum objective, orthogonality, fit/holdout RMSE/gap,
  availability/reason và diagnostic hash khớp.
- Kiểm **219/219 input hashes**, **269/269 artifact hashes**, archived code
  fingerprints và **81/81 per-alignment manifests** với source/target seed,
  checkpoint/config/mapping/anchor/backbone lineage khớp.
- 81/81 alignment replays byte-identical; input package, backbone artifacts,
  approved configs và executable code không đổi trong stage.

Aggregate manifest SHA-256:
`920b78c4ec057ff95f3e6cd812394cf3cae43e275f286779bfeee583ca6403ea`.
Artifacts: resolved stage/approved config, backbone verification receipt,
input/code hashes+copies, 9 anchor plans, 81 jobs, Q/means/diagnostics/reason
cho mỗi result và repeat, 81 manifests, summary, aggregate manifest.

## Final verification và bàn giao

Full repository regression: **462 passed, 10 skipped**, Python 3.11.9,
20,63 giây. Lệnh `.venv-m1/Scripts/python.exe -m pytest -q -rs -p
no:cacheprovider --basetemp=outputs/m2_alignment_full_regression_20261014`.
10 skips có sẵn tại `tests/test_hard_invariants.py:149–196`; không dùng chúng
để cấp scientific PASS. Targeted suite 23 passed; Ruff toàn repo và
`git diff --check` PASS. Python 3.10 local chưa được tested.

**IMPLEMENTED:** fixed-count allocation helper, stage config, runner và verifier.
**TESTED:** fixture/contract checks và regressions nêu trên.
**EXECUTED:** alignment Dev stage trên real canonical-backed checkpoints,
81 comparisons/162 SVD executions.
**VERIFIED:** independent anchor/SVD/availability/artifact-lineage checks;
chỉ phạm vi alignment Dev, không full scientific G3/M1 certification.

Files mới: `src/drift/fixed_anchors.py`, `scripts/run_m2_alignment.py`,
`scripts/verify_m2_alignment.py`, `tests/test_m2_alignment_workflow.py`,
`configs/m2_alignment_v1.yaml`, báo cáo này. Cập nhật
`docs/M2_EXECUTION_PLAN.md` và `docs/PROGRESS.md`; giữ nguyên M1 edits/reports
đang mở. Diff tracked: `git diff -- docs/PROGRESS.md`; files mới còn untracked,
chưa commit/push, không stage dữ liệu/generated artifacts.

Bàn giao empirical-null stage: dùng 6 saved **same_snapshot_cross_seed**
alignments/transition có available=true, đúng shared anchor-plan hash và
pretransition-degree strata. Persisted Q/means đủ để tính centered noise
observations cho persistent entities. Phải bind endpoint/pair IDs rõ ràng,
kiểm 6 observations/entity, rồi LTO loại tất cả observations của target theo
approved null rules. Stage này chưa tính bất kỳ observation/null/drift metric.

## Phạm vi và điểm dừng

M2 Dev trên external-package snapshots theo ngoại lệ M1 người dùng đã cho phép;
không certification temporal identity/M1/G3. Chưa Python 3.10 local, pooled
null/LTO/SED+, QA/H1 hoặc M4. STOP sau báo cáo alignment theo AGENTS.md §8.2
và stage config; không retrain backbone, không đọc locked_test hoặc sửa locks.
