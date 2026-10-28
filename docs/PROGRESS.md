# Tiến độ pipeline

## M4 Evaluation & Statistics (Stage 8 & Stage 9) EXECUTED/VERIFIED - 2026-10-28

Đã hoàn thành Stage 8 (Recurring QA Panel Evaluation) và Stage 9 (Two-Way Fixed Effects Estimation):
- QA Panel: 147 queries bền vững (121 1-hop + 26 2-hop) từ snapshot T01, theo dõi qua 9 transitions (1.323 quan sát).
- Đánh giá Arm A (Frozen T01) vs Arm B (Updated Tt) trên 2 candidate universes: Seen-at-T1 và Open-World.
- Kết nối đo lường trôi dạt SED+ từ M2 Parquet theo cơ chế median support entities.
- Mô hình Two-Way Fixed Effects H1: beta_d = -0.003665 (SE = 0.007168, t = -0.5113), WCB p-value = 0.574 (999 draws).
- Falsification test với D_pseudo: beta_pseudo = -0.012246 (SE = 0.014866, t = -0.8238), WCB p-value = 0.438 (PASS: không có hiệu ứng giả từ nhiễu).
- Contrast H2: Delta MRR Seen-at-T1 = -0.1384 vs Open-World = -0.1654 (OOV gap = -0.0270).
Artifacts: `outputs/m4_eval/20261028T065503Z_740d4fcc/` và `outputs/m4_stats/20261028T065503Z_740d4fcc/`.

## M2 Data 3.1 - Stage Null v2 & Stage Drift v2 EXECUTED/VERIFIED - 2026-10-28

- Phê duyệt AMEND-2026-001 (D-SOURCE), chốt D-COS = Affine, thu thập Pilot căn chỉnh 81 comparisons.
- Chốt ngưỡng G3 (D-DIAG): rank_fraction=0.90, orth_err=1e-6, max_holdout_residual=1.50, max_gap=0.65.
- Stage Null v2: 6.897 entity observations qua 9 transitions, 100% available sau LTO >= 50.
- Stage Drift v2: 6.897 entity observations, 100% available, median positive drift rate = 47.6%, Max SED+ = 7.32.
Artifacts: `outputs/m2_null_v2/20261027T190109Z_e6d40655/` và `outputs/m2_drift_v2/20261027T190838Z_ea66c2af/`.


## M2 data 3.1 - pilot plan PREPARED, raw collector IMPLEMENTED/TESTED - 2026-10-21

Candidate/inventory đủ30 checkpoint,81 comparisons (27 cross-time/54 same-snapshot),
9 transitions và9 saved anchor plans fit101/holdout66. Run:
`outputs/m2_alignment_pilot_plan/20261021T072021Z_e4934444/`.
Rehash176 backbone +269 alignment artifacts; canonical3.1 khớp frozen inputs.
Không chọn jobs theo outcomes/old availability, không train/refit/collection thật.

Đã tách raw geometry khỏi gate settings; giữ spectrum/norms/signed+absolute gap,
rank null nếu tolerance thiếu. Gate wrapper tiếp tục dùng explicit policy.
20 cases mới; targeted158 passed, full **639 passed, 10 skipped**; Ruff/diff PASS.
Sources: PDF khớp; hai MD originals vẫn thiếu. Kiểm18/26 encoding/newline variants
không khớp baseline; package MDs là CRLF variants của Git, không là locked originals.
Chưa resolve được originals trong các tệp đã lưu; không thay lock/protocol/ADR0007.

[Hồ sơ pilot và giới hạn](audit/M2_ALIGNMENT_PILOT_PREPARATION_20261021.md).
IMPLEMENTED/TESTED engineering; EXECUTED/VERIFIED chỉ inventory/source/hash scope.
**Pilot thật chưa chạy, chưa scientific registration/G3.** Cần originals/amendment,
anchor-frequency design và pilot decision rule; không cần residual/gap acceptance
values để thu raw statistics. M1-PASS vẫn là tiền đề. Kết thúc preparation stage.

## M2 data 3.1 - measurement v2 integration IMPLEMENTED/TESTED - 2026-10-21

Đã thêm geometry/diagnostics v2, nối saved checkpoints/alignments vào entity-null
v2 và calibration; runner tách stage null/drift, có input hash/sidecar/canonical
checks và independent NumPy verifier. Config candidate mới để null các trường
chưa đăng ký; không thay defaults/runner v1 hoặc scientific protocol.

45 cases mới; targeted **138 passed**, full **619 passed, 10 skipped**; Ruff/diff
PASS. File-backed fixture đã chạy hai stage riêng. Lỗi physical-vs-content hash
trong implementation đầu được regression test phát hiện và sửa; giữ hai loại
hash riêng. Invalid alignment không tạo SED+, không drop population; raw temporal
được giữ khi chỉ null alignment lỗi.

Preflight thực `outputs/m2_measurement_v2_readiness/20261021T064255Z_677b20b7/`
trả BLOCKED/exit2 đúng thiết kế:15 reasons về sources/registration/plan. Không
chạy measurement/pilot thật, không G3. M1-PASS vẫn là tiền đề người dùng.
IMPLEMENTED/TESTED phần integration; EXECUTED/VERIFIED chỉ readiness/hash scope.
[Báo cáo stage và giới hạn](audit/M2_MEASUREMENT_V2_INTEGRATION_20261021.md).
Kết thúc stage; cần hoàn tất scientific registration trước activation.

## M2 data 3.1 - candidate config và checkpoint reuse VERIFIED trong phạm vi kỹ thuật - 2026-10-21

Đã review phần chuẩn bị và thêm cấu hình ứng viên v2 (chưa active), reuse
inspector cùng20 regression cases. M1-PASS là tiền đề theo chỉ đạo người dùng.
Run `outputs/m2_reuse_readiness/20261021T060328Z_96561ac8/` xác minh10 canonical
snapshots khớp frozen training inputs,30/30 checkpoint configurations với
60 saved checkpoint files/sidecars,30 per-seed manifests và176 artifact hashes.
18 archived/current producer source files và runtime khớp;43 protected inputs
giữ nguyên. Không có training mới; không chứng nhận Q/raw-distance reuse.

Targeted37 passed; full suite **574 passed, 10 skipped**; Ruff/diff PASS.
IMPLEMENTED/TESTED công cụ/config; EXECUTED/VERIFIED chỉ technical reuse trên
real artifacts, không scientific measurement/G3. Candidate đề xuất affine cosine,
entity-level median/LTO, support50 và normalized diagnostics; các choices chưa
đăng ký vẫn ghi rõ, không freeze Dev defaults. Hai original source MD còn thiếu;
Git blobs tìm được không đúng baseline hash nên không restore substitutes.

[Báo cáo kết quả, bằng chứng và blockers](audit/M2_V3_1_CONFIG_AND_REUSE_20261021.md).
Scientific runner chưa kích hoạt: còn source readiness, conditioning/merge và
operating range cần registration. Giữ protocol/source lock/decision log, data
và lịch sử runs; branch chưa đổi, chưa commit/push. Kết thúc stage inspection.

## M2 data 3.1 - entity-level null v2 IMPLEMENTED/TESTED - 2026-10-21

Theo yêu cầu tiếp tục, đã thực hiện phần A/B có định nghĩa rõ: thêm reducer
median-six/entity rồi entity-level LTO, count contract/schema v2, calibration
ba seed IDs, verifier NumPy độc lập và strict v2 Parquet guards. Giữ provenance
sáu distances, kiểm missing/duplicate pairs và conflicting checkpoint/alignment
hashes. V1 vẫn phục vụ historical Dev; chưa đổi default scientific runner.

Targeted93 passed; full regression **554 passed, 10 skipped** trên Python3.11.9.
Ruff toàn repo/diff PASS. Tests kiểm support49/50 chỉ là fixtures, không freeze
ngưỡng. Chưa đổi cosine, merge policy, diagnostics, protocol/source lock hay
historical artifacts. M1-PASS tiếp tục là tiền đề người dùng, không đánh giá lại.

Chi tiết files/tests/diff/remaining scope:
[implementation report](audit/M2_ENTITY_NULL_V2_IMPLEMENTATION_20261021.md).
IMPLEMENTED/TESTED phần engine/schema/verifier; chưa EXECUTED/VERIFIED production,
chưa G3. Cần chốt scientific choices trong hồ sơ giai đoạn1 trước runner activation
và rerun null/drift data3.1. Branch chưa đổi, chưa commit/push.

## M2 data 3.1 - hồ sơ hòa giải đặc tả - 2026-10-21

Người dùng thống nhất ba nhóm A (đúng đặc tả), B (kiểm chứng), C (độ bền vững)
và chỉ đạo lấy M1 đã PASS với data3.1 làm tiền đề M2. Đã lập
[hồ sơ giai đoạn1](M2_SPEC_RECONCILIATION_V3_1.md): đối chiếu PDF/protocol/code,
dự thảo ba count fields, danh sách consumers/verifiers phải sửa và impact/reuse plan.
Giữ toàn bộ các báo cáo/gate lịch sử; không nghiệm thu lại M1 trong scope này.

Run `outputs/m2_spec_reconciliation/20261021T050958Z_b8d8b9c9/` kiểm lại source
hashes, 10 canonical snapshot hashes/mapping records và sáu numerical fixture probes.
PDF khớp lock; hai MD trong package khác hash của baseline repository, hai originals
ở root chưa có. Entity-level estimator là hướng đã thống nhất; cosine, support/
conditioning/merge và diagnostics cần quyết định cụ thể, không tự freeze giá trị Dev.
Đề cương đã nêu Q0.95 và m3/m5 pilot; phải ánh xạ từng yêu cầu thay vì gọi toàn bộ
seed/quantile checks là tùy chọn mới hoặc tự thêm cả nhóm C vào G3.

IMPLEMENTED hồ sơ/bằng chứng; TESTED/VERIFIED chỉ phạm vi sources, metadata và
fixtures theo completion manifest. Chưa sửa production code, chưa rerun M2 stage,
chưa xác nhận hòa giải hoàn tất hoặc cấp G3; không ghi decision/amendment giả.
Nhánh vẫn `codex/m2-drift-workflow`; chưa commit/push. Dừng ở hồ sơ giai đoạn1
theo AGENTS.md mục2.2/8.2, chờ giải quyết các lựa chọn khoa học trong hồ sơ.

## M1 — review data theo tiêu chí v2 và kiểm tra certified handoff — 2026-10-14

User yêu cầu đối chiếu bộ tiêu chí Downloads v2 với data hiện tại, chỉ pass M2
nếu đủ điều kiện. Checkout thực tế `codex/m2-drift-workflow@abeb425`, dirty;
giữ nguyên work M2 và lịch sử v3. Không checkout/reprocess/acquisition/API/DB
write/train hoặc mở locked_test.

Read-only audit toàn phạm vi v3, bốn-file package và audit/gates bundle:
128 metadata files/43 Parquet được kiểm kê; 5.168/5.168 referenced raw và
4.745/4.745 body hashes khớp; 5.271 strict receipts khớp hashes/raw/URLs/clock;
38/38 sidecars v3 có sẵn đạt. 10 canonical snapshots unique và khớp legacy
fact-clock graph sets; đây là structural checks, không scientific certification.

FAIL thực tế: 1.788/1.803 fact span hashes và 1.849/1.865 claim span hashes
không khớp exact slices; field contract drift còn 9/17 và physical declarations
17/17 thiếu. Boundary indices chia timestamp groups ở T01/T02/T04/T05/T06,
interval event counts T01–T07 lệch cutoff counts. Window hiện hành kết thúc
31/08 nhưng T07–T10 và 952 facts observed trong tháng 9. Identity chưa được
chứng nhận: tất cả facts ghi v1_mock/AUTO_ACCEPTED. Bundle có thêm source/
config/freeze/window approvals khác active ledger; chưa đủ original bytes/
hash/amendment/run bindings để giải quyết authority.

Hai reports bundle trùng bytes reports v3; parity vẫn DB_READ_BACK_PERFORMED=false,
chỉ CSV. Gói bốn file cũng là copy v3, không phải rebuild đã sửa lỗi. Gold/
approved threshold annex/mapping decisions/accepted clock/producer manifest/
real DB read-back/receiver evidence còn thiếu. G1/G2 thực gọi BLOCKED với
evaluated_count=0; public M2 certified loader từ chối vì thiếu
runs/production_v3/run_manifest.yaml.

**Không nghiệm thu M1 hoặc bàn giao scientific M2.** M2 Dev runs riêng không
thay đổi gates M1. [Review đủ 16 tiêu chí và 9 findings](audit/M1_CRITERIA_V2_DATA_REVIEW_20261014.md)
ghi rõ FAIL/BLOCKED, phần kiểm được và dependency G1↔Stage 4.18 cần làm rõ.
Evidence: outputs/m1_criteria_v2_review_20261014/; rehash 128 inputs/protected
locks không đổi. Chỉ thêm audit/docs, không remediation production. Bước ưu
tiên: authority/approval reconciliation và historical eligibility trước pilot/
new run. Ruff toàn repo và git diff --check PASS; không thay production code.

## M2 — rà soát tài liệu lý thuyết và scientific conformance — 2026-10-14

User yêu cầu rà soát tính chính xác của tài liệu lý thuyết dựa trên commit
`cc411c628ea561b5f0a76e185a6c31a79ec13710`; không yêu cầu sửa code.
Đã đối chiếu raw attachment, code/config và PDF nguồn có hash khớp lock.
PDF §3.2.4 (27)–(28) yêu cầu median-six per entity rồi entity-level LTO
reference; Dev helper hiện pooling pairwise observations. Sai khác này
CONFIRMED đối với nguồn PDF đang có, còn hai original source MD thiếu.

PDF còn nêu sparse support dưới50 entity-level observations; Dev guard là
5 pairwise observations. Inventory hiện có355 LTO rows dưới50 reference
entities. Đã ghi thêm divergence diagnostic normalization và unresolved
centered-vs-affine cosine registration; không tự quyết scientific semantics.
Toy checks/evidence và [review chi tiết](audit/M2_THEORY_REVIEW_20261014.md)
ghi8 findings, phần đúng và wording cần sửa. Không patch/rerun/overwrite
outputs, không đổi source lock/protocol, không mở locked_test.

Numerical/lineage verification của các Dev runs trước giữ đúng phạm vi;
không chứng nhận source conformance hoặc G3. Lượt trước đã bỏ sót đối chiếu
null estimator với nguồn scientific PDF. Scientific use tiếp tục chưa đủ
điều kiện; source reconciliation và remediation cần được xử lý trước
scientific downstream inference, trong task/stage được yêu cầu riêng.

## M2 — báo cáo toàn bộ quy trình và trực quan hóa — 2026-10-14

Theo yêu cầu người dùng, đã viết lại báo cáo xuyên suốt preflight/pilot/
backbone/alignment/null/LTO/drift và Dev handoff từ artifacts đã lưu.
Run báo cáo `outputs/m2_report/20261014T061101Z_a624c271/`: HTML tự chứa,
Markdown, 10 biểu đồ PNG/SVG, 1.500 epoch loss log rows và 6.897 drift log
rows có đầy đủ ba seed values. Giao diện chọn snapshot/seed, lọc transition/
bucket/entity, phân trang và tải log. Không train lại hoặc đổi phép đo.

Independent report verifier kiểm 716 source hashes/32 artifact hashes,
đối chiếu mọi exported log/HTML data/quantiles/support với checkpoint/Parquet
PASS; 10 hình đã kiểm bố cục. Browser filters/downloads/navigation PASS,
không console errors. Ruff/diff PASS. Full scientific regression 505 passed/
10 skipped là kết quả của stage M2 trước, không chạy lại để viết báo cáo.
[Báo cáo toàn bộ M2](audit/M2_FULL_WORKFLOW_REPORT_20261014.md).

M2 Dev đã EXECUTED/VERIFIED; M3 chỉ scaffold, M4 chưa thực hiện. Report giữ
M1/G3 uncertified, low-support T01 high bucket và giới hạn log (chỉ loss theo
epoch, embeddings cuối training; không có embedding trajectories theo epoch).
Giữ mọi historical reports/runs; các bản report draft trước được bảo toàn,
run cuối ở trên là bản bàn giao, không auto-advance scientific stage.

## M2 — longitudinal drift và Dev handoff — 2026-10-14

User yêu cầu bước tiếp theo sau null/LTO verified; stage config
`configs/m2_drift_v1.yaml` bind approved config/null manifest/receipt hashes.
Saved cross-time Q/fit means cho 3 parallel seeds 13/37/101; median delta_time,
signed r giữ âm và SED+ theo đúng LTO MAD/epsilon đã duyệt. Không re-align,
retrain hoặc chọn lại population/anchors/buckets.

Run `outputs/m2_drift/20261014T044648Z_ae9f0401/` hoàn tất 20.691 temporal
observations và 6.897 entity×transition drift rows; 6.897/6.897 available,
3.640 r>0 (mô tả, không significance/H1). 9/9 JSON replays exact bytes,
2/2 deterministic Parquet files. Independent verifier recompute toàn bộ
temporal/calibrated rows, kiểm 549 input/57 artifact hashes, 9 manifests và
Dev handoff PASS. Full suite 505 passed/10 existing skipped; Ruff/diff PASS.
[Báo cáo drift](audit/M2_DRIFT_REPORT_20261014.md).

IMPLEMENTED/TESTED + EXECUTED/VERIFIED phạm vi M2 drift Dev trên artifacts
thật; không scientific M1/G3 certification. M1 G1/G2/official handoff vẫn
BLOCKED/uncertified. T01 high-bucket LTO chỉ 1 reference entity/6 correlated
observations, giữ nguyên support counts và limitation. Dừng sau Stage Report;
chưa M4/QA/MRR/H1. Next stage M4 readiness cần user yêu cầu tiếp.
Không đổi upstream artifacts/locks/protocol, không đọc locked_test.

## M2 — empirical null 6 cặp và Leave-Target-Out — 2026-10-14

User yêu cầu bước tiếp theo sau alignment; stage config `configs/m2_null_v1.yaml`
bind approved config/alignment manifest/independent receipt hashes. Saved Q và
fit means dùng cho 6 endpoint seed pairs, pretransition-degree bins 3/6,
pooled adjacent merge và LTO bỏ toàn bộ 6 target observations; không re-align.

Run `outputs/m2_null/20261014T042450Z_43e91590/` hoàn tất 41.382 noise rows
và 6.897 entity×transition LTO stats, 6.897/6.897 available theo approved
guards, 9/9 null JSON replays exact bytes, 2 Parquet serializations deterministic.
Không có sparse merge thực tế. T01 high bucket chỉ 1 reference entity mỗi LTO
(6 correlated pair observations); lưu support counts, không tự đổi thresholds.

Independent verifier recompute 41.382 noise/6.897 LTO values, kiểm 491 input/
55 artifact hashes và 9 manifests PASS. Targeted 23 passed; full suite 479
passed/10 skipped, Ruff/diff PASS, Python 3.11.9.
[Báo cáo null/LTO](audit/M2_NULL_REPORT_20261014.md).

IMPLEMENTED/TESTED + EXECUTED/VERIFIED trong phạm vi null Dev trên artifacts
thật; không scientific G3/M1 certification. Dừng sau stage; chưa delta_time/
signed excess/SED+ hoặc M4. Không sửa upstream artifacts/locks/protocol,
không retrain backbone, không đọc locked_test.

## M2 — fixed-anchor alignment cho 9 transitions — 2026-10-14

User yêu cầu thực hiện alignment; stage config `configs/m2_alignment_v1.yaml`
bind approved config/backbone hashes, không đổi inputs cũ. Đã lưu outcome-blind
anchor plans trước SVD: persistent IDs, exact pretransition-degree quotas,
fixed 101 fit/66 holdout, cùng split cho cả 9 comparisons của mỗi transition.

Run `outputs/m2_alignment/20261014T040001Z_96d9ccbc/` hoàn tất 81 comparisons
× 2 repeats = 162 SVD executions. 81/81 available, 9/9 transitions đạt approved
diagnostics; mọi numerical rank 64, max holdout RMSE 1.404725, max gap 0.580387,
max orthogonality 2.198345e-14. 81/81 replays byte-identical.

Independent verifier reconstruct 9 anchor plans và recompute 81 SVD results,
kiểm 219 input/269 artifact hashes và 81 manifests PASS. Full suite 462
passed/10 skipped, targeted 23 passed, Ruff/diff PASS, Python 3.11.9.
[Báo cáo alignment](audit/M2_ALIGNMENT_REPORT_20261014.md).

IMPLEMENTED/TESTED + EXECUTED/VERIFIED trong phạm vi alignment Dev trên
checkpoints thật; không scientific G3/M1 certification. Dừng sau stage;
chưa empirical null/LTO/SED+ hoặc M4, không retrain backbone, không sửa locks/
protocol/historical data hoặc mở locked_test.

## Review toàn bộ Docs và hướng M1 — 2026-10-14

Đọc/kiểm kê 94 Docs files lúc đầu, bổ sung ba Docs M2 mới thành 97 files
(không tính report mới của lượt này);
báo cáo [M1 direction review](audit/M1_DIRECTION_REVIEW_20261014.md) có 12
findings và dependency/artifact roadmap. Giữ hướng rebuild chọn lọc, ưu tiên
historical-proof eligibility trước pilot costs. Metadata v3: 5.271 retrieval
clocks đều tháng 9 sau window; 1.930 archive rows trong window nối 1.840 raw
hashes/1.770 bodies, chưa chứng nhận content-version proof/eligibility.
Candidate contract không cho pending/reject có acceptance null; còn thiếu
domains/per-stage contracts/ontology semantics và gold/coverage integration.
47 targeted tests PASS; probes chỉ fixture/component scope. Không thay source,
schema/protocol/lock/decision log hoặc historical data; không production M1,
Gemini/Neo4j/training/certification. Checkout chung chuyển sang M2 workflow cùng
HEAD trong khi review, work M2 giữ nguyên. Dev M2 không chứng nhận M1; final
G1/G2 và official handoff vẫn BLOCKED. Không commit/push/merge trong lượt này.

## M2 — chốt cấu hình và backbone toàn bộ snapshots — 2026-10-14

User xác nhận thực hiện kế hoạch sau pilot; đã lưu approved Dev configuration
`configs/m2_external_dev_v1.yaml` hash-bind proposal, giữ protocol/source lock.
Stage backbone trên `codex/m2-drift-workflow` hoàn tất T01–T10, TransE-L2
64 chiều/50 epochs/lr 0.01, seeds 13/37/101: 30 configurations × 2 repeats =
60 training executions, 30/30 exact checkpoint byte replays.

Run `outputs/m2_backbone/20261014T034042Z_65c464ba/`: independent verifier
đạt 41 input/176 artifact hashes, 30 seed manifests, full mapping/config/git/
snapshot/loss provenance; 6 T01/T02 checkpoints còn khớp exact bytes với pilot.
Targeted tests 55 passed; full suite 444 passed/10 skipped, Ruff/diff PASS,
Python 3.11.9. [Báo cáo backbone](audit/M2_BACKBONE_REPORT_20261014.md).

IMPLEMENTED/TESTED + EXECUTED/VERIFIED trong phạm vi backbone **Dev trên data
thật**; không production scientific certification/G3/M1 PASS. Dừng sau Stage
Report theo kế hoạch; chưa execute fixed-count alignment 9 transitions,
null/LTO/SED+ hoặc M4. Không sửa scientific protocol, input artifacts, gate
status lịch sử; không đọc locked_test, không rerun acquisition.

## M2 Dev pilot trên dữ liệu được user chỉ định — 2026-10-14

Đã tạo `codex/m2-drift-workflow` từ `2860235`, giữ thay đổi M1 đang mở.
User yêu cầu bỏ tiêu chí nghiệm thu M1 cho công việc M2 này và xác nhận pilot
chọn dimension qua validation/alignment. Đã lưu
[kế hoạch từng bước](M2_EXECUTION_PLAN.md) và
[báo cáo pilot](audit/M2_PILOT_REPORT_20261014.md).

Input preflight 10 snapshots/9 transitions đạt technical hash/count/structure
checks. Pilot T01/T02: dimensions 32/64, seeds 13/37/101, 101 train/20 validation,
18 configurations replay hai lần = 36 training executions. 18/18 checkpoint
replays byte-identical; 240 rankings và 18 alignments được tính lại độc lập.
Mean validation MRR 0.110916/0.122906; cả hai đạt 9/9 alignment checks, đề xuất
64 chiều theo rule đã lưu trước training. Targeted suite 86 passed; full suite
427 passed/10 skipped trên Python 3.11.9; Ruff/diff PASS.

Đây là IMPLEMENTED/TESTED và EXECUTED/VERIFIED trong phạm vi **Dev pilot trên
artifacts thật**, không chứng nhận M1/G3 hoặc full M2 measurement. Proposal
`configs/m2_run_proposal.yaml` còn REVIEW_REQUIRED, không activate defaults
null/epsilon hoặc đổi scientific protocol. Dừng sau pilot; chưa train T03–T10,
chưa pooled null/LTO/SED+, chưa chạy M4, không sửa data/source lock/protocol.

## Review toàn bộ các nhánh M1 sau đồng bộ remote — 2026-10-14

Fetch/prune và remote-tip verification thành công; remote không có commit mới.
Pull fast-forward-only từ legacy vào acceptance trả Already up to date, giữ
HEAD `2860235` và ba commit local chưa push. Review 8 remote M1 branches và
acceptance local bằng fixed code snapshots; full current regression **408
passed, 10 skipped**, Ruff toàn repo PASS. Findings/report:
[M1 all-branch review](audit/M1_ALL_BRANCH_REVIEW_20261014.md).
Phát hiện mới BR-M1-001: quality component chưa bind nội dung gold được chấm
với nội dung adjudication; fixture mismatch vẫn component PASS, final gates
vẫn BLOCKED. Các nhánh pipeline cũ còn clock/mapping/evidence/quality/parity
defects; không merge wholesale. Không production execution/certification,
không sửa source code, protocol/source lock hoặc historical artifacts.

## M1 acceptance rebuild foundations — 2026-10-14

Đã tạo `codex/m1-acceptance-rebuild` từ `684dc6b`, lưu
[kế hoạch](M1_REMEDIATION_PLAN.md) và [runbook](M1_ACCEPTANCE_RUNBOOK.md).
Engineering mới: typed public-contract engine/candidate package 25 tables,
exact artifact/decision guards, Gemini capture/replay/budget fixtures,
independent quality metrics, temporal/boundary helpers và one-stage preflight.
Public schema/locks/protocol chưa thay; production backends và final
certification vẫn chưa activate. Component PASS không mở scientific gate.

Bounded recovery audit đạt **5.168/5.168 referenced raw hashes**, 1,662 GB;
35-commit source search không tìm exact execution-plan/patch originals.
V3 113 files unchanged. Full suite **408 passed, 10 skipped** trong isolated
Python 3.11; Ruff/dependency checks PASS. Python 3.10 package metadata compatible
và CI matrix đã thêm, local 3.10 chưa chạy. Không gửi Gemini requests hoặc chạy
production/Neo4j thật. Gate A/G1/G2 và M2 handoff vẫn BLOCKED.
Chi tiết và phần engineering chưa hoàn tất:
[implementation report](audit/M1_ACCEPTANCE_IMPLEMENTATION_20261014.md).

## Đóng gói audit/recovery và cleanup theo yêu cầu commit/push — 2026-10-14

Nhánh đích: `codex/transe-legacy-exploration`. Commit audit/recovery:
`fc46402`; commit cleanup: `80897d2`. Hai commit legacy trước đó `08c352b`
và `d97325e` cùng tài liệu cập nhật được đưa vào đợt publish này. Dữ liệu,
checkpoints, recovery archives, backups và proposal PDF không được stage.
Validation trước commit: Ruff/diff PASS; fixture suite đã đạt 345 passed,
10 skipped và 5 default-temp checks. Decision table vẫn REVIEW REQUIRED,
production gates vẫn BLOCKED. Trạng thái GitHub được xác minh từ remote tip
sau push, không suy ra từ local commits.

## Bảng quyết định và repository cleanup — 2026-10-14

Đã lập [11 mục quyết định](audit/V3_DECISION_TABLE_20261014.md), status REVIEW
REQUIRED, không tự apply scientific choices. Proposal hash check 7/8 exact;
contract matrix lệch manifest (CRLF hypothesis matches), giữ cả hashes để review.
Archive 30 temp/cache directories và diff.txt rỗng vào backups riêng; không
xóa data/experiment outputs. Ignore rules/lint exclusions/default pytest temp
đã dọn; v3 113 files và locked proposal hash giữ nguyên. Full suite 345 passed,
10 skipped; default tmp fixture smoke 5 passed. Ruff/diff PASS. Quy trình đầy
đủ ở [mục 14](QUY_TRINH_THU_TRANSE_LEGACY_T01.md#14-bảng-quyết-định-và-dọn-repository--đã-thực-hiện).
Gates còn BLOCKED; phần cleanup được đóng gói trong đợt commit/push ở trên.

## Producer diagnostics và phạm vi remediation v3 — 2026-10-14

Đối chiếu 32 commits/13 config inputs: 6 exact blob hashes, cả 13 tương thích
với CRLF/LF hypotheses ở sáu producer-family commits; chưa verified actual
v3 commit. Toàn bộ 1.803 facts khớp claim-ID suffix, metadata và legacy
lowercase-mention hash IDs. Tạo diagnostic mention links cho 1.389 IDs,
không registered mapping/availability. 7 tests extractor boundary/producer/
span PASS, Ruff không lỗi lint; current extractor đã bind exact span/both
roles nên không patch production. Phạm vi stage/dependency review tại
[V3 remediation scope](audit/V3_REMEDIATION_SCOPE_20261014.md), trạng thái
REVIEW REQUIRED; chưa reprocess, không thay lock/protocol/gates.

## Khôi phục release upstream và kiểm evidence v3 — 2026-10-14

Đã lấy audit-only release `data/pre-gate-a-audit-v1`, archive SHA-256 khớp;
restore có chọn lọc vào outputs riêng. 4.745 body hashes khớp v3, 5.271 strict
receipt references khớp file/record/raw hash/URL/retrieval time, 30 sample raw
blobs khớp bytes. Mapping manifest vẫn rỗng, chưa phải producer run v3.
Finding V3-REC-001: toàn bộ 1.803 evidence hashes bind body, chỉ 15 exact spans
khớp (mẫu 1/30); không sửa historical facts/hashes. 2 regression tests PASS,
Ruff không lỗi lint. Gates/semantic quality tiếp tục BLOCKED. Chi tiết từng
bước ở [mục 12 của quy trình](QUY_TRINH_THU_TRANSE_LEGACY_T01.md#12-khôi-phục-upstream-từ-github-release-và-kiểm-lại-evidence--đã-thực-hiện).

## Content/mapping readiness v3 — 2026-10-14

Read-only inventory toàn bộ hai repository roots đã biết (loại locked_test,
hidden/reparse paths và model outputs) không tìm thêm mapping/body/acquisition
artifacts. Plan 30 facts (3/relation) được lưu trước content review, không dùng
outcomes. 22 sample facts khớp một claim; 8 khớp nhiều cặp mention. Cả 30 thiếu
body/evidence payload nên chưa đánh giá correctness hoặc as-of mapping.
Metadata/integrity kiểm độc lập đạt, 5 tests PASS, package giữ nguyên; G2 và
semantic quality tiếp tục BLOCKED_NOT_VERIFIED. Quy trình, finding và bundle
cần bổ sung tại [mục 11](QUY_TRINH_THU_TRANSE_LEGACY_T01.md#11-kiểm-tra-chất-lượng-nội-dung-và-mapping-v3--đã-thực-hiện-phần-khả-dụng).

## Replay training 101 triples với logging — 2026-10-14

Đã quan sát training hiện có qua read-only tracing, không thay RNG/calculations.
Ba checkpoint bytes khớp reference 101/20. Trên 15.150 lượt triple, 0 skip,
14.996 active updates, 86 self-loop negatives (tất cả active); cuối training
relation norms 0.7601–1.2568. Kiểm lại 15.150 saved samples/losses/norms và hashes
đạt. 25 tests observer/ranking/split/mechanics PASS; Ruff không lỗi lint.
Không chấm lại held-out/tuning, không sửa production code hoặc mở gates.
Quy trình từng bước, số liệu và diễn giải tại
[mục 10 của quy trình T01](QUY_TRINH_THU_TRANSE_LEGACY_T01.md#10-chẩn-đoán-training-101-triples-bằng-logging--đã-thực-hiện).

## Tổng hợp quy trình và kiểm tra cơ chế TransE — 2026-10-14

Đã tổng hợp toàn bộ tiến trình legacy trong
[quy trình T01](QUY_TRINH_THU_TRANSE_LEGACY_T01.md). Thêm fixture checks cho
numerical gradients (head/tail, shared indices, self-loops), sampler rejection,
saturated-side skip, inactive hinge, projection và evaluation không sửa weights.
Suite cơ chế/sampling/ranking cuối: **20 passed**, Ruff mục tiêu PASS. Có thêm
retry-budget fixtures xác nhận skip có thể xảy ra dù tồn tại negative hợp lệ;
chưa đo xác suất trên dữ liệu thật và không sửa sampling semantics. Chưa thấy
lỗi triển khai trong phạm vi này; không đổi production code/candidate policy,
không training lại T01. Self-loop behavior đúng công thức nhưng nguyên nhân
chất lượng prediction chưa được chứng minh. Gates tiếp tục BLOCKED.

## Phân tích lỗi legacy T01 — 2026-10-14

Phân tích saved ranks: lợi thế aggregate so với baseline tập trung ở 4
seen-pair triples; cả ba seeds dưới baseline trên 16 unseen-pair triples.
Self-loop top-1 lần lượt 36/34/39 trong 40 queries, đã đối chiếu score trực
tiếp từ checkpoint. Chưa sửa candidate policy, không tuning/training lại,
không thay input/gates. Chi tiết:
[T01 error analysis](audit/legacy_t01_error_analysis_20261014.md).

## Đánh giá legacy T01 101/20 được user chốt — 2026-10-14

Đã lưu design/split hash trước khi train lại từ đầu trên 101 triples. Chấm
20 held-out theo head/tail, 167 candidates, filtered ranking và average ties.
MRR seeds 13/37/101 lần lượt 0.104897/0.084878/0.093864, baseline tần suất
0.056464; Hits@1 đều 0. Kiểm lại độc lập 160 ranking rows từ saved artifacts
đạt; 8 tests PASS, Ruff không lỗi lint. Chỉ là kết quả legacy, không tuning
hoặc mở scientific gates. Chi tiết:
[T01 evaluation](audit/legacy_t01_evaluation_20261014.md). Dừng sau báo cáo.

## Kiểm tra khả năng chia T01 legacy — 2026-10-13

Audit chỉ đọc cho thấy hash split 20% tạo 98 train/23 held-out, nhưng 20/23
held-out có entity không xuất hiện trong train. Coverage-preserving witness
theo hash cố định tạo 101 train/20 held-out, giữ đủ 167 entities/10 relations
trong train; held-out chỉ phủ 7 relations và có 4 cặp entity đã có cạnh khác
trong train. Chưa khóa split, chưa training mới/MRR. 4 tests PASS; báo cáo:
[T01 split feasibility](audit/legacy_t01_split_feasibility_20261013.md).
Production gates và các blocker v3 giữ nguyên.

## Thử TransE legacy T01 theo phạm vi user chốt — 2026-10-13

Đã chạy độc lập T01 canonical của bộ v3: 121 triples/167 entities/10 relations,
TransE-L2 dimension 32, 50 epochs, seeds 13/37/101. Mỗi seed chạy hai lần,
checkpoint byte-identical trong cùng môi trường; embeddings/loss hữu hạn,
mapping/serialization/hash đã kiểm tra. Đây là thử legacy được user chốt,
không phải M2 production hoặc scientific gate PASS. Không đổi loader guards,
protocol, source lock hoặc dữ liệu. Gate A/G1/G2 và M2 production vẫn BLOCKED.
9 tests mục tiêu PASS; chưa xác thực Python 3.10/3.11. Báo cáo và giới hạn:
[legacy T01](audit/legacy_transe_t01_20261013.md). Dừng tại T01, không tự mở rộng.

## Kiểm tra trước commit remediation — 2026-10-13

Kiểm tra working tree trên Python 3.12.10: `python -m pytest -q
--basetemp=.pytest_cache/commit_verified_20261013 --tb=short` đạt **303 passed,
10 skipped**, một cảnh báo deprecation pytz. Lượt sandbox ban đầu bị lỗi quyền
thư mục tạm; lượt chạy lại với quyền phù hợp hoàn tất thành công.
`python scripts/verify_g1.py --ci --code-checks` đạt **4 passed**; chỉ là
CODE_CONFORMANCE_PASS, không chứng nhận scientific G1. `python -m ruff check .`
không có lỗi lint, nhưng báo ba warning quyền đọc thư mục; chưa kiểm tra lại
trên Python 3.10/3.11 trong lượt này.

Phạm vi: đóng gói code/tests, CI và hồ sơ audit đang mở trên nhánh remediation.
Không đưa dữ liệu nguồn hoặc bản sao `preexisting.patch` vào commit. Mức xác
nhận là **IMPLEMENTED + TESTED** (fixtures/code); không chạy production,
Neo4j thật hoặc huấn luyện trên dữ liệu thật. Gate A/G1/G2 và M2 production
tiếp tục **BLOCKED** theo hồ sơ hiện hành. Không thay protocol/source lock.

## Đánh giá lại nhánh Hương và hướng M1 → M2 — 2026-10-04

Đã fetch tất cả remote; tip Hương vẫn `e19fe25`, không có commit mới so với
review 03/10. ZIP `data/evolving_kg_downstream_v2.zip` được người dùng xác nhận,
hash không đổi. Kiểm lại 10 snapshots: export/replay/hash nhất quán; temporal
future-effective fixture và zero-gold quality PASS trên producer Hương vẫn lỗi.
Schema checkout vẫn BLOCKED 9/17, hai source Markdown gốc thiếu, raw chỉ có
`.gitkeep`, không có local `runs/` hoặc approved baseline file.

Audit cấu trúc bổ sung: T01 có 121 triples/167 entities/24 chuỗi 2-hop có hướng;
T10 có 1.205 triples/1.389 entities/313 weak components, 1.040 entities chỉ có
một láng giềng. Chín transitions chỉ thêm triples; chưa chứng minh QA/anchor
feasibility hay correction/retraction production. Khuyến nghị giữ nhánh
remediation làm nền, khôi phục upstream và sửa M1 có chọn lọc trước M2 production.
Chưa merge nhánh Hương vì xung đột locked source baseline chưa giải quyết.

Focused checkout regressions: **43 passed**; G1 code checks: **4 passed**,
không cấp scientific PASS. Ruff `src tests scripts` PASS; whole-repo Ruff FAIL
15 lỗi từ pytest fixture directories cũ; diff check báo whitespace sẵn có
trong AGENTS.md. Không chạy production/Neo4j/training hay sửa locked inputs.
Gate A/G1/G2 và M2 handoff tiếp tục BLOCKED. Kết luận, structured findings,
bằng chứng và lộ trình từng stage ở [báo cáo 04/10](audit/m1_final_direction_20261004.md).

## Nhánh khắc phục sau review Thu Hương — 2026-10-03

Đã tạo `codex/m1-thu-huong-remediation` từ `6000f38`, giữ các thay đổi đang mở.
Sửa `src/temporal/snapshot.py` để cả hai snapshot paths lọc validity trước
revision; kiểm tra revision graph và dừng khi thiếu parent, sai LogicalFactID,
cycle hoặc hai revision hiệu lực cạnh tranh. Future-effective correction không
còn loại fact cũ trước cutoff. Regression snapshot/provenance: **35 passed**;
Ruff đạt. Bước này **IMPLEMENTED + TESTED** ở fixture tier; chưa chạy production.

Chi tiết finding, bằng chứng regression và blocker: [báo cáo snapshot](audit/m1_snapshot_revision_guard_20261003.md).

Kế hoạch tích hợp chọn lọc C3–C9 và stage production, blocker/chứng cứ cần có,
và tiêu chí nghiệm thu ở [đây](audit/m1_thu_huong_remediation_plan_20261003.md).
C3 và policy identity/conflict/normalization chưa duyệt; Gate A/G1/G2, các
production stages và M2 vẫn **BLOCKED**.
Review tĩnh bổ sung phát hiện source-lock hash mismatch, helper có thể ghi
placeholder/ghi lại lock, đường rerun 108-block Stage 4.3, wrapper tự chạy
nhiều bước, copy helper có thể ghi đè và hosted model mode trên nhánh Thu
Hương. Xem [phụ lục](audit/m1_thu_huong_branch_safety_supplement_20261003.md).

### Đối chiếu input readiness read-only — 2026-10-03

Đã khôi phục đúng proposal PDF từ blob ở commit `6779bf4` vì SHA-256 khớp
source-lock; `inspect_source_lock` hiện báo proposal `MATCH`. Hai Markdown gốc
vẫn `MISSING`; bản trong Git history lệch hash nên không dùng. Raw chỉ có
`.gitkeep`, không có `runs/` hoặc artifact Stage 4.3. ZIP downstream không đổi,
không có upstream provenance/gate evidence. Xem [báo cáo input readiness](audit/m1_input_readiness_recovery_20261003.md).
W1 `--ci` chỉ đạt scaffold/contracts; strict W1 verifier vẫn FAIL vì hai
Markdown gốc thiếu. Không nhầm scaffold PASS với source-lock PASS.
Checkout phụ cũng chỉ có hai `inventory` pilot runs, config
`PROPOSED_UNFROZEN`, source lock và recorded Gate A đều `BLOCKED`.
Không mở `data/locked_test/`,
không rerun Stage 4.3, không sửa source-lock hay raw; Gate A vẫn **BLOCKED**.

## Review gói dữ liệu Thu Hương — 2026-10-03

Đã đối chiếu read-only `data/evolving_kg_downstream_v2.zip` với nhánh
`fix/data-pipeline-compliance-cont` tại `e19fe25`. Cả 10 snapshot khớp hash,
replay rows/semantic hash bằng hàm producer và CSV node/edge sets cùng metadata.
10 cutoff có timestamp khác nhau; T07–T10 vượt historical window hiện tại.
Đây là xác minh tính nhất quán file export, chưa là Neo4j database parity hay
scientific PASS. Temporal future-effective regression vẫn FAIL; evaluator
quality trả PASS khi evaluated_count=0. Package thiếu upstream provenance,
mapping as-of, gold, freeze/gate certificates và verified handoff manifests.

Gate A/G1/G2, production và M2 tiếp tục **BLOCKED**. Không chạy production
stage, không sửa raw/source-lock, không merge nhánh Thu Hương. ZIP/guide đã
được ignore. Xem [review chi tiết và bằng chứng](audit/m1_thu_huong_package_review_20261003.md).

## C4 — mapping theo cutoff, runner fixtures — 2026-10-03

Thêm regression fixtures gọi trực tiếp `run_adjudication` và `run_snapshot`:
mapping alias chỉ có sau `evidence_observed_at` không tạo FactVersion; snapshot
trước ngày supersession giữ mapping cũ và snapshot sau ngày đó dùng mapping mới.
Bộ test tập trung đạt **48 passed**, Ruff đạt. Đây là **IMPLEMENTED + TESTED**
ở fixture tier; Gate A/schema/artifact I/O được cô lập trong test, không phải
`EXECUTED` hay `VERIFIED` production.

C4 vẫn **PARTIAL/BLOCKED**: schema audit còn 9/17 bảng lệch; runtime chưa nối
stable `MentionID` và `MappingDecisionID` xuyên Claim → FactVersion → snapshot;
identity policy và mapping-catalog fingerprint/binding chưa được chứng minh.
Không chạy production. Xem [báo cáo C4](audit/m1_c4_runner_regression_20261003.md).

## C5 — text/evidence provenance và locked extraction cache — 2026-10-03

Extraction giờ từ chối body variant thiếu `normalization_version`, và chỉ dùng
identity normalization hiện tại; NFC chưa được bật khi chưa có quyết định được
duyệt. Helper extraction yêu cầu version tường minh và text đúng với version.
Locked replay bind hash input, parser, dependency lock, model/tokenizer,
normalization, prompt/schema/decoding, endpoint, runtime và nền tảng; replay
thiếu cache hoặc fingerprint thì dừng. Stage Manifest kiểm physical và
semantic hash cho `extractor_manifest.json`, nơi body variant nối clean-text
hash/version với claim span.

Focused tests: **52 passed**, một cảnh báo deprecation pytz hiện hữu; Ruff đạt.
Đây là **IMPLEMENTED + TESTED** trên fixtures, không phải extraction
EXECUTED/VERIFIED production. C5 còn **BLOCKED** cho production: schema hiện
không có `body_variants.normalization_version`, C3 còn 9/17 bảng lệch, chưa có
duyệt NFC, và local runtime fingerprint chưa được attest độc lập. Xem [báo cáo
C5](audit/m1_c5_text_provenance_20261003.md).

## C6 — source claims và append-only revisions — 2026-10-03

`run_adjudication` ghi `source_claims-v1` JSON theo provenance path và
đăng ký artifact đó trong output manifests để stage chain kiểm tra hash. Nếu
run con khai báo parent nhưng FactVersion store đã xác minh không có, runner
giờ dừng thay vì khởi động lịch sử rỗng. Support xuyên run không tạo version
mới; conflict, correction và retraction tiếp tục pending khi chưa có policy.
Focused adjudication/provenance/artifact-chain suite: **25 passed**; toàn bộ
`tests/kg_pipeline/`: **176 passed**, một cảnh báo deprecation pytz hiện hữu.
Ruff đạt, dù lượt toàn repo có warning quyền đọc thư mục pytest cũ. Đây là
**IMPLEMENTED + TESTED** fixtures;
chưa có production `EXECUTED` hoặc độc lập `VERIFIED`.

C6 còn **PARTIAL/BLOCKED**: chưa có contract schema cho SourceClaim/support
aggregation, chưa xác định nhóm nguồn độc lập, conflict/revision policy chưa
được duyệt, Stage 4.10 và Gate A vẫn chặn production. Xem [báo cáo C6]
(audit/m1_c6_claim_revision_20261003.md).

## C7 — snapshot certification và bàn giao M2 — 2026-10-03

Snapshot manifest `v2` bind semantic hash của exclusions; per-snapshot YAML
manifest được đăng ký làm output của snapshot producer stage. M2 kiểm tra
ArtifactRef chain, hash config/code/mapping/boundary, support/exclusion lineage
tới fact và claim provenance, Gate A hiện hành, cùng G1/G2 certificate đã lưu
và gắn đúng run/hash. Public single-snapshot loader cũng bắt buộc run context
và chuyển qua verified-run loader, đóng đường đọc Parquet trực tiếp bỏ qua
stage/gates. Bộ `tests/kg_pipeline/`, temporal snapshot và M2 adapter đạt
**204 passed**; Ruff mục tiêu đạt. Đây chỉ là **IMPLEMENTED + TESTED** trên
fixture, không phải production execution hay certification.

C7 còn **PARTIAL/BLOCKED**: `accepted_into_kg_at` chưa có trong contract có
thẩm quyền, schema audit vẫn lệch 9/17 bảng, boundary/identity policy chưa được
duyệt, Gate A/G1/G2 và production artifacts vẫn thiếu. Không có production
snapshot hoặc M2 handoff nào được chạy/xác minh. Xem [báo cáo C7]
(audit/m1_c7_snapshot_certification_20261003.md).

## C8 — Neo4j materialization và read-back parity — 2026-10-03

Thêm adapter chỉ materialize sau khi M2 verified-run loader chấp nhận snapshot;
đọc cạnh/support/fact trực tiếp từ canonical Parquet, giữ temporal support theo
FactVersion, ghi Neo4j bằng thao tác append-only và so sánh read-back toàn bộ
node/edge sets cùng thời gian. Parity key bắt cả lệch metadata khi counts bằng
nhau. Bộ `tests/kg_pipeline/`, temporal snapshot và M2 adapter đạt **210
passed**; Ruff mục tiêu đạt. Các test dùng driver double.

C8 **PARTIAL/BLOCKED**: không có Neo4j driver hoặc Docker daemon trong môi
trường; Gate A/G1/G2 và artifact runner production vẫn blocked. Stage 4.10
thiếu approved temporal evidence và runtime contract thiếu
`accepted_into_kg_at`, nên không thể chạy vertical slice qua snapshot runner mà
không bypass policy. Chưa có Neo4j database read-back hoặc hai production-runner
semantic hashes. Xem [báo cáo C8](audit/m1_c8_neo4j_readback_20261003.md).

## C9 — locked mode và phạm vi CI — 2026-10-03

Locked initialization kiểm tra exact pin cho dependency runtime và build;
config run chỉ lấy protocol có thẩm quyền từ `configs/protocol_v1.yaml`, không
dùng `config/protocol.yaml` làm fallback. CI mặc định chỉ chạy code checks và
G1 code conformance, không gọi verifier để cấp scientific PASS; regression
khóa ranh giới này. C9-focused tests đạt **82 passed**; full suite đạt **278
passed, 10 skipped**. Mười skip là các placeholder M2/M3/M4 và locked-test
workflow trong `tests/test_hard_invariants.py`. Ruff và diff check đạt.

C9 **IMPLEMENTED + TESTED** ở fixture/code tier; chưa có locked production
`EXECUTED` hoặc `VERIFIED`. Baseline config chưa được duyệt, `openai>=1.0.0`
chưa có exact pin trong lock, Gate A/G1/G2 và production artifacts vẫn
BLOCKED; C8 cũng chưa có Neo4j read-back thật. Xem [báo cáo C9](audit/m1_c9_locked_ci_20261003.md).
Chưa commit.

Audit machine schema chạy lại read-only sau C9: vẫn **BLOCKED 9/17** với
schema version `1.0.0`, hash
`48ad42f86088ae0e9ca8b8cbb158017bf8ec14e0d450fdeff523bf59e6902840`.
Chi tiết field mismatch được lưu tại
[JSON audit](audit/m1_c3_contract_diff_20261003.json); chưa đổi schema vì các
clock/version/reprocess choices cần approval.

## M1 C3 — 2026-09-28: machine contract và các clock

Đã thêm audit đọc `config/schema.yaml`, chặn đường production khi PyArrow hoặc
dataclass không tương thích; run lưu version/hash schema. Đã bỏ fallback 2020,
việc dùng retrieval thay ingestion và suy diễn UTC cho thời gian thiếu timezone.
Adjudication dừng khi chưa có artifact thời gian Stage 4.10 được duyệt.

Audit thực tế: **BLOCKED, 9/17 bảng lệch contract**. Code/fixture tests: toàn bộ
194 passed, 10 skipped; bộ C3 cuối cùng 9 passed; Ruff đạt. Đây không phải
scientific PASS. Cần quyết định schema migration, nguồn clock và đánh giá
reprocess trước khi triển khai phần còn lại của C3. Xem [báo cáo C3](audit/m1_c3_contract_time.md).

Đối chiếu đọc lại tại `922e319` ngày 2026-09-28 xác nhận audit còn BLOCKED ở 9/17
bảng (schema version `1.0.0`, SHA-256
`48ad42f86088ae0e9ca8b8cbb158017bf8ec14e0d450fdeff523bf59e6902840`). Hồ sơ
quyết định C3 đã được lập để xin duyệt tên/kiểu contract, căn cứ clock và phạm
vi reprocess; đây chưa phải quyết định được duyệt và chưa được ghi vào decision
log. Xem [hồ sơ quyết định C3](audit/m1_c3_decision_package.md). C3 tiếp tục
BLOCKED; không mở production adjudication hoặc snapshot.


## M1 C4–C9 — 2026-09-28: code remediation, production vẫn BLOCKED

Đã triển khai guard và fixture coverage cho mapping as-of, text/extraction
provenance, cache replay bất biến, SourceClaim/conflict handling, parent
FactVersion lineage, snapshot dependency hashes, M2 handoff, exact-set parity,
và scientific locked mode. **C4–C9 chỉ hoàn tất một phần ở mức code**; từng
checkpoint chưa đạt production certification. Ma trận M1-001–M1-020 đã được
cập nhật riêng [tại đây](audit/m1_c4_c9_finding_matrix.md), với bốn trạng thái
IMPLEMENTED, TESTED, EXECUTED và VERIFIED.

Regression cuối: **230 passed, 10 skipped**; Ruff và `git diff --check` đạt.
Đây là kiểm tra code/fixture, không phải scientific PASS. Schema machine audit
vẫn **BLOCKED: 9/17 bảng**; Gate A, G1/G2, production stages và M2 vẫn BLOCKED.
Không chạy production runner, không materialize Neo4j, không rerun hoặc sửa
Stage 4.3/raw/source-lock, không ghi decision log và chưa commit.

Sau lần regression trên, đã harden thêm C9: cấu hình local adapter nằm tại
`config/llm_adapter.yaml` và được đưa vào run fingerprint; locked extraction
từ chối thiếu adapter local/pins/decoding fields, ontology thiếu hoặc adapter
mock. Locked init đối chiếu direct dependencies với exact pins trong lock và
hiện chặn `openai>=1.0.0` vì không có exact pin tương ứng trong lock.
Extraction runner không tự chọn ontology mẫu hay mock; helper cũng cần adapter,
ontology và cache directory tường minh. Kiểm thử tập trung mới nhất:
**25 passed, 4 deselected**; Ruff và `git diff --check` đạt. Chưa chạy lại toàn
regression sau patch C9: pytest bị môi trường Windows từ chối truy cập thư mục
temporary (`WinError 5`), nên số 230/10 ở trên chỉ thuộc revision ngay trước
patch này. Xem [báo cáo C9](audit/m1_c9_locked_ci.md).

- C4: [mapping theo cutoff](audit/m1_c4_mapping.md) — còn thiếu stable mention ID và identity policy.
- C5: [text và extraction provenance](audit/m1_c5_text_extraction.md) — normalization mới chưa được phê duyệt.
- C6: [claims và revisions](audit/m1_c6_claims_revisions.md), cập nhật fixture
  ngày 2026-10-03 tại [đây](audit/m1_c6_claim_revision_20261003.md) — source
  paths đã được persist/bind; policy support/conflict và production vẫn BLOCKED.
- C7: [snapshot và bàn giao M2](audit/m1_c7_snapshots_m2.md) — acceptance clock, boundaries và G1/G2 còn thiếu.
- C8: [Neo4j parity](audit/m1_c8_neo4j_parity.md) — chưa có materialization/read-back thật.
- C9: [locked mode và CI](audit/m1_c9_locked_ci.md) — CI chưa thể cấp chứng nhận artifact-backed.


## M1 C2 — 2026-09-28: chuỗi artifact và bàn giao M2

Đã triển khai ArtifactRef và xác minh đệ quy run/stage lineage cho canonical
Parquet. Các runner bind input/output và Gate A; M2 yêu cầu snapshot manifest,
producer hoàn tất, Gate A hợp lệ và đúng snapshot được yêu cầu. Kiểm thử toàn bộ:
187 passed, 10 skipped; bổ sung ca vòng stage: bộ test chuỗi 11 passed. Đây là
kết quả code/fixture, không phải production hay G1/G2 PASS. Gate A vẫn BLOCKED.
Chi tiết và phần dependency chưa khóa: [báo cáo C2](audit/m1_c2_artifact_chain.md).


## M1 C1 — 2026-09-28: chặn scientific PASS sai

Đã triển khai và kiểm thử guard G1/G2: yêu cầu run rõ ràng, bỏ synthetic fallback,
chọn run theo mtime và miễn kiểm chứng G1 bằng tag. Kiểm tra cấu trúc/fixture được
tách khỏi chứng nhận khoa học. Chẩn đoán quality không PASS khi không có bản ghi
được đánh giá hoặc thiếu coverage của gold.

Regression: 174 passed, 10 skipped; bộ guard cuối cùng: 16 passed; Ruff và diff
check đạt. Đây chỉ là bằng chứng kỹ thuật. G1/G2 vẫn BLOCKED do chưa có evaluator
khoa học đầy đủ; Gate A và production không được mở. C2–C9 chưa hoàn thành.
Chi tiết: [báo cáo C1](audit/m1_c1_gate_guards.md).

## Checkpoint khắc phục 0 — 2026-09-20

Nhánh sửa: `fix/data-pipeline-compliance`, từ `origin/feature/data_try` tại `4c24da2`.
Đã lập ma trận 24 bước (`data_pipeline_compliance.md`) và ADR 0007 theo lựa chọn
của người dùng: giữ ba original với hash baseline, không placeholder hoặc đổi hash.
Source lock/protocol và artifact lịch sử không thay đổi. Chưa sửa runtime Ticket A.

Trạng thái checkpoint: **VALIDATION INCOMPLETE**, không phải PASS. Các lệnh kiểm
JSONL, historical-prefix và `git diff --check` chưa chạy được do bộ kiểm tra quyền
công cụ tạm thời không khả dụng. Tìm file ở checkout hiện tại chỉ thấy
`sources/README.md` trong `sources/` và `.gitkeep` trong `data/raw/`; chưa có bằng
chứng local để kiểm lại dữ liệu production. Xem `checkpoint_0_report.md`.

Các kết quả PASS/test/count bên dưới là báo cáo lịch sử ngày 2026-09-16, không
phải kết quả chạy lại trong checkpoint này. Không rerun acquisition hoặc tự mở
stage downstream để khắc phục thiếu dữ liệu.

## Checkpoint R1 — Baseline and Execution Guards — 2026-09-20

Các guard về baseline và fingerprint đã được triển khai đầy đủ cho R1.

- Source lock kiểm tra đúng ba role gốc, không cho qua bằng placeholder.
- Fingerprint bao gồm cấu trúc, code, file nguồn, ontology, protocol và corpus scope.
- Trạng thái cấu hình được kiểm tra sự đồng thuận (`APPROVED`) ở config_baseline, được lưu vào `config_approval` trong manifest thay vì cứng ngắc là FROZEN. Cập nhật này ngăn run chạy tiếp nếu có thay đổi ngoài lề.
- Các bài kiểm tra validation (hợp lệ schema của cấu hình, resumption rollback khi approval thay đổi) đã được bổ sung.
- Không giả mạo bất kỳ nguồn hoặc quyết định phê duyệt nào. Do thiếu tài liệu và gói data production, pipeline hiện tại vẫn đang **BLOCKED** ở input readiness.
- **Retest hoàn tất**: Toàn bộ hệ thống (gồm validate config_approval, shell commands) đã vượt qua regression tests. R1 đã hoàn thành phần code, Gate A từ chối chính xác khi config bị unfrozen.

## Checkpoint R2 — Acquisition Trust and Identity — 2026-09-20

Tiếp nối R1, hệ thống đã triển khai các cấu trúc định danh và trust:
- Bổ sung định nghĩa PK/FK ở `contracts.py` và check bắt buộc trong Gate A (`A-011`). 
- Chỉnh sửa `_recovery_row` để đánh giá strict timestamp tại thời điểm scan. Bằng chứng sai định dạng ngày tháng hay thiếu timezone giờ sẽ hạ xuống mức không strict (giữ lại làm ledger) thay vì làm nổ cả quá trình inventory.
- Viết test coverage (`test_inventory.py`) cho nhiều luồng (dup event, multiple publishers cho cùng 1 byte, strict vs partial timestamps).
- Việc test đã hoàn tất thành công. Xem chi tiết tại `checkpoint_r2_progress.md`.

## Checkpoint R3 — Storage and Reproducibility — 2026-09-20

Hệ thống lưu trữ và toàn vẹn dữ liệu được cải thiện ở R3:
- Cài đặt `exclusive_artifact_lock` dùng `os.mkdir` (atomic OS-level) để đảm bảo đồng bộ khóa đa tiến trình trên cả Windows và Linux. Khóa bao phủ trọn vẹn quy trình check-verify-publish.
- Xử lý Crash recovery: Nếu một table parquet và sidecar bị can thiệp nhưng nội dung khóa học (`semantic_sha256`) lệch với `input_lock` đang chạy, `ArtifactConflict` sẽ ném ra, chặn không cho tái sử dụng (hoặc ghi đè). Đã có test coverage `test_tampered_table_and_manifest_rejected_during_write`.
- Đã loại bỏ các `run_id` bị lọt vào `semantic_sha256` bằng cách chỉ lưu đường dẫn tương đối (relative to run_dir). Đảm bảo tính cross-run reproducibility độc lập.
- Chi tiết xem tại `checkpoint_r3_progress.md`.

## Checkpoint R4 — Gates and Integration — 2026-09-20

Việc định danh và đánh giá Gate A được củng cố ở R4:
- `latest_gate_a_report` đã chuyển sang sắp xếp báo cáo dựa trên metadata thực `evaluated_at_real` chứa trong file thay vì dùng UUID lexicographical sort.
- Ngăn chặn stale PASS: `evaluate_gate_a` gọi `load_run_manifest` và tự động fail nếu cấu hình (config fingerprints) bị trôi lệch sau khi init run. Đã thêm test `test_input_mutation_invalidates_gate` để chứng minh báo cáo PASS giả bị bác bỏ nếu input thực tế không khớp.
- Khôi phục `.gitignore` strict cho thư mục `data/locked_test/*`, bảo vệ tính vô hình của tệp held-out. Thêm bài test `test_locked_test_payload_ignored` dùng `git check-ignore` xác thực điều này.
- `cli.py` đã đảm bảo trả mã exit hợp lệ (`0` khi `PASS`, `2` khi bị block/fail hoặc crash).
- Xem chi tiết tại `checkpoint_r4_progress.md`. 
Lưu ý: Môi trường hiện tại là Python 3.12, cần xác thực lại trên CI với Python 3.11.

## Báo cáo lịch sử — giữ nguyên

Lần đối chiếu gần nhất: 2026-09-16 (Asia/Saigon)

## Điểm dừng hiện tại

Ticket A đã hoàn tất phần triển khai và báo cáo inventory trong run mới
`llm_rebuild_v2_audit_01`. Gate A đang **BLOCKED**, không phải PASS. Chưa chạy
ticket sau, LLM, pilot, full-corpus inference, network refetch hoặc ghi Neo4j.

## Stage 4.3 - PASS trong phạm vi đã chứng minh

Bằng chứng được đọc và đối chiếu độc lập từ
`data/stage_4_3_runs/stage4_3_final_20260906T144016Z/` sang
`runs/llm_rebuild_v2_audit_01/reports/stage_4_3_reconciliation.json`.

- Final manifest và validation report: PASS/PASS.
- Tất cả hash output trong final manifest đều khớp.
- `discovered_urls.parquet`: 4,692 observation và 3,344 unique URL.
- `archive_candidates.parquet`: 72 dòng.
- `discovery_log.jsonl`: 245,928 record hợp lệ, không rỗng; 0 record lỗi.
- Tuoi Tre historical blocks: 108.

Không chạy lại `src/03b_run_tuoitre_historical_window.py`. Trạng thái trong
`docs/data_pipeline_spec.md` chỉ được đối chiếu từ bằng chứng đã kiểm chứng này.
Điều này không chứng nhận Stage 4.4 hoặc scientific readiness của Ticket A.

## Ticket A - triển khai xong; scientific input readiness BLOCKED

Artifact của run: `runs/llm_rebuild_v2_audit_01/`.

Kết quả inventory thực tế:

- 5,168 raw path / 5,168 giá trị SHA-256 hiện tại khác nhau; 0 lỗi đọc và
  0 filename-hash mismatch.
- 5,167 raw path được nhận diện là HTML và 1 path là text/plain.
- 4,745 body variant, 5,168 source membership và 4,745 exact-body cluster;
  352 cluster có nhiều hơn một membership. Exact clustering giữ toàn bộ
  membership; không suy luận near-duplicate/copy/lineage.
- 20 recovery record nối bằng exact hash và 20 source-version row trỏ tới 18
  blob. Tất cả đều partial: 0 strict retrieval. Thiết kế này cố ý giữ nhiều
  retrieval riêng biệt thay vì gộp chúng.
- 5,150 blob không có direct acquisition evidence; 18 blob có partial evidence
  nhưng thiếu field acquisition bắt buộc. Hash blob hiện tại được ghi là
  computed-now evidence, không phải historical proof.
- Một raw item sinh body rỗng để review. Bốn JSON manifest rỗng có sẵn được ghi
  là evidence-scan review issue không chặn.
- Discovery observation, URL, retrieval record và raw blob là các đơn vị không
  so sánh trực tiếp; không ép số lượng của đơn vị này khớp đơn vị khác.

Bằng chứng gate: `runs/llm_rebuild_v2_audit_01/gates/gate_A.json`.

| Gate check | Kết quả |
| --- | --- |
| Stage 4.3 reconciliation, table/schema readability, raw hash/read audit, giữ retrieval ID, loại legacy decision input | PASS |
| Strict raw provenance | BLOCKED: 0 strict raw path; 5,150 unresolved |
| Source lock | BLOCKED: thiếu cả ba locked original đúng hash |
| Config baseline | BLOCKED: `PROPOSED_UNFROZEN` |
| Near-duplicate/copy/lineage policy | BLOCKED: chưa có semantic policy được duyệt |
| Tổng thể Gate A | **BLOCKED**; lệnh verify thoát đúng với code 2 |

## Kiểm chứng đã chạy

- `python -m ruff check --no-cache src/kg_pipeline tests/kg_pipeline`: PASS.
- `python -m pytest -q`: **63 passed, 14 skipped**. (Python 3.12).
- `git diff --check`: PASS; không báo lỗi whitespace.

## Cần có trước khi Gate A PASS theo khoa học

1. Cung cấp hoặc chính thức thay thế, với thẩm quyền khoa học, các locked
   original đang thiếu mà không sửa `data/manifests/sources.lock.json` để khớp
   một file khác.
2. Khôi phục hoặc quản trị có chủ đích raw acquisition provenance: exact blob
   hash, source/URL/final URL và thời điểm retrieval thật. Không dùng mtime hoặc
   page metadata làm evidence thay thế.
3. Duyệt baseline cho configuration/ontology/time field, bao gồm mâu thuẫn
   10-versus-11 relation và phân biệt `retrieved_at_real` với
   `ingested_at_real`.
4. Duyệt near-duplicate/copy/lineage policy có version nếu cần suy luận vượt ra
   ngoài exact body hash.

Stage tiếp theo cần chỉ đạo rõ từ user sau khi gate liên quan và các quyết định
khoa học thật sự được giải quyết.
