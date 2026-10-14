# Báo cáo M2 input preflight và pilot — 14/10/2026

Nhánh: `codex/m2-drift-workflow`; base `2860235`.
Phạm vi: người dùng cho phép bỏ điều kiện nghiệm thu M1 để chạy M2 Dev trên
gói hiện có, sau đó xác nhận pilot chọn dimension qua validation/alignment.
Thiết kế và trình tự: `docs/M2_EXECUTION_PLAN.md`, `configs/m2_pilot.yaml`.

## Bước 1 — input preflight đã thực hiện

Run: `outputs/m2_preflight/20261014T031739Z_71f4e280/`.
Lệnh: `.venv-m1/Scripts/python.exe scripts/inspect_m2_inputs.py`.

10/10 canonical snapshots đạt kiểm physical SHA-256, semantic sidecar hash,
snapshot config/manifest count và ID, unique nonempty triples, timezone và
cutoff ordering. T01: 121 triples, 167 entities; T10: 1.205 triples,
1.389 entities; cả 10 snapshot có 10 relations. Tất cả 9 transitions giữ
toàn bộ entities/edges trước đó và chỉ thêm cạnh; persistent counts lần lượt
167, 343, 503, 646, 787, 936, 1.057, 1.176, 1.282. Không chọn/lọc snapshot
theo outcomes. Cutoffs của gói được giữ nguyên.

Inventory gói bổ sung: body_variants 4.745 rows, extracted_claims 1.865,
fact_versions 1.803, kg_events 1.205. Hash/schema/row counts được ghi trong
report; không lấy các bảng này để tự dựng một snapshot khác cho KGE.

Canonical export thực tế có 10 columns gồm triples và provenance; loader
kiểm ba ID columns, giữ semantic hash của toàn bộ rows và ghi source columns.
Regression xác nhận export có provenance không bị từ chối chỉ vì nhiều hơn
ba columns. Không suy luận temporal validity từ hash/count consistency.

Artifacts: `report.json`, `mappings.json`, `experiment_manifest.json`.
Input hashes được kiểm lại sau đọc. Kết quả: **PACKAGE_TECHNICAL_CHECKS_PASS**,
`scientific_certification=false`. M1 criteria được loại khỏi phạm vi Dev này
theo chỉ đạo; không sửa M1 status hoặc adapter production.

## Engineering verification trước pilot

Python 3.11.9, NumPy 2.2.6, PyArrow 23.0.0. Baseline KGE/drift/adapter:
23 passed. Workflow + toàn scientific suite: 83 passed; schema-export regression
thêm sau đó: workflow 17 passed. Ruff mục tiêu PASS.

Lượt test ban đầu có 20 passed/3 setup errors do quyền thư mục temp cũ, không
phải model assertion failure; chạy lại với test directory mới ở outputs đạt
23/23. Không xóa thư mục test cũ, không đổi thresholds hoặc bỏ tests.

## Bước 2 — pilot

Được người dùng cho phép sau khi chọn phương án validation/alignment.
Run: `outputs/m2_pilot/20261014T031822Z_9b722664/`.
Lệnh: `.venv-m1/Scripts/python.exe scripts/run_m2_pilot.py --preflight
outputs/m2_preflight/20261014T031739Z_71f4e280`.

Trước training đã ghi design, input hashes, split, anchor IDs/hashes, mappings
và exact source-code copies. Coverage-preserving split salt mới tạo **101 train /
20 validation triples**, 40 head/tail queries, 167 candidate entities,
10 relations trong train. Không đọc lại kết quả legacy để chọn split. Có cùng
số rows với legacy nhưng không phải việc tái sử dụng legacy held-out results;
split/hash mới đã được lưu trước training.

18 checkpoint configurations: 2 dimensions × 3 seeds × (validation-train,
full T01, full T02). Mỗi configuration chạy lại từ đầu hai lần, tổng 36
training executions. Tất cả embeddings/losses finite, round-trip/hash/mapping
checks đạt và 18/18 cặp checkpoint **byte-identical** trong môi trường này.

| Dimension | MRR seed 13 | MRR seed 37 | MRR seed 101 | Mean MRR | Alignment |
|---|---:|---:|---:|---:|---|
| 32 | 0.092789 | 0.086340 | 0.153618 | 0.110916 | 9/9 operational + full-rank |
| 64 | 0.120254 | 0.100356 | 0.148108 | 0.122906 | 9/9 operational + full-rank |

Mỗi dimension có sáu same-snapshot cross-seed và ba cross-time parallel-seed
alignments. Fit/holdout **101/66** với exact-degree stratification đã lưu trước
model outcomes. Minimum rank lần lượt 32 và 64. Max holdout RMSE:
1.338309 / 1.303041; max absolute fit-holdout gap: 0.375913 / 0.512759;
max orthogonality error: 1.2241e-14 / 2.0902e-14. Đạt giới hạn operational
hiện có không có nghĩa là representations đã ổn định về semantic quality.

Quy tắc selection trước chạy đề xuất **64 chiều**. Chênh mean MRR ~0.01199
chỉ là Dev pilot trên tập nhỏ và biased về repeated entities; không có kiểm
định cho superiority, không suy ra QA/H1 hoặc mọi transition sau đều khả dụng.
Hits@1 của cả ba models 64 chiều bằng 0; không che hạn chế này bằng aggregate MRR.

## Independent artifact verification

`scripts/verify_m2_pilot.py` kiểm lại saved artifacts: toàn bộ 40 input hashes,
101 artifact hashes, exact checkpoint replay và input/config/mapping/git
provenance. Ranking được tính lại trực tiếp từ serialized vectors, không gọi
ranking function của runner. Procrustes được đối chiếu bằng NumPy SVD riêng
với means, Q, singular values, numerical rank, orthogonality và residuals.

Kết quả: **240/240 ranking rows**, **18/18 alignments** và selection 64 chiều
khớp. Verification reports append-only trong pilot directory; không ghi đè
report đầu khi verifier được bổ sung provenance/duplicate guards.

Workflow + scientific/KGE/Procrustes/null regressions cuối: **86 passed**,
Python 3.11.9; Ruff toàn repo PASS. Regression verifier từ chối saved rank hoặc
Q bị đổi. Không thay code scientific hiện hữu để đạt PASS.

Full repository regression sau tất cả code changes: **427 passed, 10 skipped**
trong 19,09 giây. Lệnh: `.venv-m1/Scripts/python.exe -m pytest -q -p
no:cacheprovider --basetemp=outputs/m2_full_regression_20261014`. Không biến
10 skipped thành scientific PASS; independent validation ở trên chỉ cho pilot.
Ruff toàn repo và `git diff --check` PASS. Report verifier cuối:
`independent_verification_20261014T032428Z_ea8b68ae.json`.

## Bước 3 — proposal cụ thể, chưa activate

`configs/m2_run_proposal.yaml` có status **REVIEW_REQUIRED**:

- TransE-L2 64 chiều; seeds 13/37/101; 50 epochs; learning rate 0.01; margin 1.
- Fixed fit/holdout 101/66 để giữ mức pilot, sampled by pretransition degree;
  cần test allocation ở các transitions có nhiều hơn 167 persistent entities.
- Candidate null proposal: degree bins `<3`, `3–5`, `>=6`; six endpoint pairs;
  LTO bỏ tất cả target observations; adjacent merge như engineering hiện có;
  min reference observations 5, epsilon 1e-4. Những giá trị null là **đề xuất
  dựa trên defaults code hiện có**, không phải giá trị đã calibrated/frozen.
- Shared anchor universe/stratification cho temporal và same-snapshot null;
  validate từng pair, manifest đầy đủ và unavailable không NaN/Inf cần hoàn
  thiện/test trước measurement. Không tính null/drift trong lượt pilot.

Lý do cần user chốt M2 proposal trước execution tiếp theo: `AGENTS.md` mục
2.2 quy định **"If information is insufficient for an issue affecting scientific
semantics, data population, or temporal behavior: STOP and request user
clarification."** Protocol hiện vẫn để placeholders cho dimension, anchor
counts, bucket merge và epsilon. Chỉ đạo bỏ tiêu chí M1 đã được áp dụng cho
pilot; không tự coi đó là lựa chọn các tham số M2 chưa được chốt.

Mọi lần thực thi tiếp theo chỉ một stage; bước kế tiếp sau user chốt proposal
là backbone training T01–T10. Không tự tiến vào measurement hoặc M4.

## Verification tiers và diff

| Phạm vi | IMPLEMENTED | TESTED | EXECUTED | VERIFIED |
|---|---|---|---|---|
| Input inspection | Có | Fixtures PASS | Đã đọc dữ liệu thật của gói | Hash/schema/count/cutoff ordering; không temporal certification |
| Pilot M2 Dev | Có | Targeted 86; full suite 427 passed/10 skipped | 36 training executions trên T01/T02 thật | Saved checkpoint/ranking/alignment arithmetic và lineage trong phạm vi pilot |
| Full M2 measurement | Kế hoạch/proposal; chưa complete runner | Chưa full-stage tests | Chưa | Chưa; G3 chưa chứng nhận |

Tier EXECUTED ở đây ghi rõ **Dev pilot trên dữ liệu thật**, không gọi đó là
production-stage completion hoặc scientific gate PASS.

Files mới: `scripts/inspect_m2_inputs.py`, `scripts/run_m2_pilot.py`,
`scripts/verify_m2_pilot.py`, `tests/test_m2_pilot_workflow.py`,
`configs/m2_pilot.yaml`, `configs/m2_run_proposal.yaml`,
`docs/M2_EXECUTION_PLAN.md`, báo cáo này. `docs/PROGRESS.md` chỉ thêm trạng thái
M2, giữ nguyên phần M1 đang sửa trước lượt này. Review diff: `git diff` cho
tracked progress; các files mới còn untracked, chưa commit/push.

## Phạm vi chưa xác minh

Chưa Python 3.10 local, full T01–T10 training, null/LTO/SED+, M2→M4 handoff,
G3 scientific gate hoặc historical temporal/identity certification.
Không rerun acquisition, không mở locked_test, không sửa protocol/source lock.
