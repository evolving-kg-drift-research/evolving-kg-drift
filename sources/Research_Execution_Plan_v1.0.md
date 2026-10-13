# Research Execution Plan v1.0

BỘ MÔN KHOA HỌC MÁY TÍNH – KHOA CÔNG NGHỆ THÔNG TIN

KẾ HOẠCH THỰC THI 10 TUẦN

MVR/TDR, phân công, gates, rủi ro, GPU và scope cuts

ĐỊNH LƯỢNG ĐỘ TRÔI BIỂU DIỄN CÓ HIỆU CHỈNH NHIỄU CHO SUY LUẬN ĐA BƯỚC TRÊN ĐỒ THỊ TRI THỨC TIẾN HÓA

Loại tài liệu

Tài liệu mô tả ngữ cảnh nghiên cứu

Tác giả thực hiện

[NHÓM SINH VIÊN THỰC HIỆN]

Người hướng dẫn

ThS. Nguyễn Đình Quý

Đơn vị

Bộ môn Khoa học máy tính – Khoa Công nghệ thông tin

Ngày thực hiện

Tháng 8 năm 2026

1. MVR, TDR và thứ tự ưu tiên

Lớp

Thiết kế

MVR — Minimum Defensible Research

Temporal evidence reconstruction; versioned facts; 8–10 meaningful snapshots; TransE-L2 d32/64; 3 seeds; Procrustes; same-snapshot null; raw/excess/SED; recurring QA; A/B; H1/H2; pseudo-drift; reproducibility.

TDR — Recommended

Toàn bộ MVR + relation-aware structural drift, extraction-quality controls, simple path nếu gate đạt, evidence-constrained ICL, selected extra-seed sensitivity.

STRETCH

QLoRA 3–4B pilot; snapshot 11–12 nếu algorithm chọn; expanded human evaluation; max-path sensitivity; covariance sensitivity đã đăng ký.

REMOVED

Nhiều KGE, GraphRAG, complex Path Utility, Noisy-OR, auditor ranking arm, path-eligible primary, mandatory 5 seeds all snapshots, nhiều co-primary tests.

MVR vẫn là Advanced Machine LearningGiá trị ML nằm ở representation geometry, multi-seed stochastic control, cross-time alignment, empirical null, query-level exposure construction, controlled Frozen/Updated evaluation và panel falsification. Đây không chỉ là data engineering dù temporal integrity là điều kiện đầu tiên.

2. RACI

Work package

M1 Data/KG

M2 Drift

M3 Auditor/Path

M4 Eval/Stats

Temporal corpus, versioning, snapshots

A/R

C

I

C

TransE, alignment, null, drift

C

A/R

I

C

QA benchmark, populations, candidate universes

C

C

R/C

A/R

Path retrieval/reranking

C

C

A/R

C

ICL/optional QLoRA auditor

I

C

A/R

R/C

H1/H2/H3a runner, WCB, falsification

I

C

C

A/R

Protocol freeze và reproducibility audit

R

R

R

A

Final report và defense

R

R

R

A

3. Lộ trình 10 tuần

Tuần 1 — Khóa contracts

Trường

Nội dung

Scientific objective

Khóa contracts

Engineering tasks

Verify source hashes; temporal/fact schema; H1 complete-support; H2 populations/candidate universes; H3a full population; anchor eligibility; median aggregator; repo/tests.

Deliverable

Source lock; schema; protocol draft; tests skeleton.

Decision/Gate

Hard invariants có hiệu lực.

GPU use

CPU; GPU chỉ environment smoke.

Fallback

Nếu source mismatch: dừng downstream và lập amendment.

Tuần 2 — Vertical slice

Trường

Nội dung

Scientific objective

Vertical slice

Engineering tasks

30–50 bài; 3 tiny snapshots; d32/d64 smoke; extraction pilot; pseudo algorithm; snapshot metrics; null merge procedure; MDE simulation ban đầu.

Deliverable

End-to-end slice và telemetry.

Decision/Gate

G1 temporal integrity.

GPU use

T4 smoke KGE; không QLoRA.

Fallback

Giảm ontology/relations nếu extraction hoặc mapping yếu.

Tuần 3 — Hai real transitions

Trường

Nội dung

Scientific objective

Hai real transitions

Engineering tasks

Stage-A ingest; entity-resolution audit; 3-seed KGE; anchor/holdout pilot; freeze candidate QA feasibility panel/hash.

Deliverable

Mapping audit; checkpoints; QA candidate hash.

Decision/Gate

G2 evidence/entity; freeze anchor counts.

GPU use

T4 ưu tiên KGE seeds.

Fallback

Conservative IDs; targeted annotation.

Tuần 4 — Measurement viability

Trường

Nội dung

Scientific objective

Measurement viability

Engineering tasks

Alignment/null diagnostics; exact snapshot selection; freeze S/boundaries/null/SED; ICL baseline; QLoRA go/no-go.

Deliverable

Measurement viability report; snapshot hashes.

Decision/Gate

G3 alignment/null; QLoRA cancellation rule.

GPU use

T4 KGE/null; QLoRA pilot chỉ sau six prerequisites.

Fallback

d64→d32; merge buckets; Relative Landmark fallback; cancel QLoRA.

Tuần 5 — Khóa benchmark

Trường

Nội dung

Scientific objective

Khóa benchmark

Engineering tasks

Final QA populations; complete-support attrition; H2/H3a memberships/universe hashes; controls/transforms; path cap/go-no-go; corpus scale decision.

Deliverable

QA/panel v0.9; frozen configs.

Decision/Gate

G4 QA/power; G5 support modules.

GPU use

Inference/path dev; optional auditor.

Fallback

Targeted collection hoặc hạ claim; cắt path trước controls.

Tuần 6 — Dev A/B/C

Trường

Nội dung

Scientific objective

Dev A/B/C

Engineering tasks

A/B Dev; H1 dry-run; H2 contrasts; C−B full population nếu path sống; reproduction check.

Deliverable

Dev tables; analysis-ready panel; reproducibility report.

Decision/Gate

Không outcome-tune.

GPU use

T4 batch KGE/inference theo queue.

Fallback

Nếu C fail, TDR quay về A/B; nếu H1 panel yếu, tăng query có mục tiêu.

Tuần 7 — Protocol freeze

Trường

Nội dung

Scientific objective

Protocol freeze

Engineering tasks

Hoàn tất protocol_v1.yaml; freeze data/query/snapshot/pseudo hashes; WCB seed/draws; dry-run locked pipeline.

Deliverable

Signed protocol; immutable manifests.

Decision/Gate

G6 protocol lock.

GPU use

Không exploratory training.

Fallback

Mọi thay đổi cần amendment; contamination làm invalid run.

Tuần 8 — Locked experiment

Trường

Nội dung

Scientific objective

Locked experiment

Engineering tasks

Chạy H1/H2/pseudo và optional C/audit; không tuning sau result visibility; rerun chỉ khi engineering failure được ghi.

Deliverable

Immutable raw outputs/logs.

Decision/Gate

Locked access audit.

GPU use

T4 dedicated locked queue.

Fallback

Khắc phục bug rồi rerun toàn affected block với version mới.

Tuần 9 — Main analysis

Trường

Nội dung

Scientific objective

Main analysis

Engineering tasks

H1/H2/optional H3a; pseudo; LOTO; registered sensitivity; negative-result analysis; figures/tables.

Deliverable

Main results và failure taxonomy.

Decision/Gate

Không thêm model/metric.

GPU use

CPU bootstrap; T4 chỉ inference rerun hợp lệ.

Fallback

Nếu power yếu, báo descriptive/inconclusive và MDE.

Tuần 10 — Tái lập và bảo vệ

Trường

Nội dung

Scientific objective

Tái lập và bảo vệ

Engineering tasks

Fresh reproduction; report; figures; slides; demo; packaging source/data manifests/checkpoints.

Deliverable

Release candidate và defense pack.

Decision/Gate

Release checklist.

GPU use

GPU chỉ reproduction cần thiết.

Fallback

Cắt demo aesthetics trước robustness/reproduction.

4. Kế hoạch 72 giờ đầu

Ngày

Owner

Công việc

Artifact

Tiêu chí thành công

Day 1

M4(A), M1/M2/M3(R)

verify_source_hashes; tạo temporal/H1/H2/H3a/anchor contracts; khóa candidate-universe rules và missing-support codes.

sources.lock; protocol skeleton; schemas; tests list.

Hashes khớp; không còn ambiguity về primary estimands/populations.

Day 2

M1(A/R), M2/M4(C)

Ingest 10–20 bài mẫu; tạo append-only versions; 3 cutoff fixtures; canonical Parquet và Neo4j materialization.

tiny event store; 3 snapshots; manifests.

Zero future evidence/mapping; rebuild hash giống; Parquet/Neo4j parity.

Day 3

M2(A/R), M4(R), M3(C)

TransE d32 smoke 3 seed trên hai transitions; anchor split; Procrustes/null; 5–10 recurring QA rows; A/B runner dry-run.

checkpoints; diagnostics; drift table; panel slice.

Finite embeddings; alignment artifact; same-snapshot null; RR rows sinh được end-to-end.

5. Sáu gate fail-fast

Gate

Metric

Loại

Deadline

Quyết định

G1 — Temporal integrity

Future-leak count=0; deterministic rebuild/hash; mapping validity; canonical/Neo4j parity.

HARD

End W2

Pass: tiếp tục Stage A. Fail: dừng downstream, sửa as-of/schema và rebuild.

G2 — Evidence/entity quality

Extraction and mapping metrics/procedure đã khóa; relation-specific error audit; QA feasibility.

Pilot-calibrated

End W3

Fail: giảm ontology, conservative IDs, targeted adjudication.

G3 — KGE/alignment/null

3 seeds finite; mapping parity; rank/fit/holdout/null diagnostics trong operating range khóa từ pilot.

Hard + pilot

End W4

Fail: d64→d32; merge null buckets; Relative Landmark fallback; hạ measurement claim.

G4 — QA/power

Recurring panels, complete-support attrition và MDE đủ để estimand còn có ý nghĩa.

Pilot-calibrated

End W5

Fail: targeted queries/data; giảm S; hạ H1 thành descriptive/inconclusive.

G5 — Support modules

Path coverage/gain hoặc auditor prerequisites đạt Dev rules.

Pilot-calibrated

End W5

Fail: cắt path; giữ ICL; hủy QLoRA.

G6 — Protocol lock

All configs/hashes/seeds/draws frozen; no locked access; dry-run tái lập.

HARD

End W7

Fail: chưa mở locked test; sửa protocol rồi ký version mới.

6. GPU/compute queue

Job

Thiết bị

Ưu tiên

Cửa sổ

Ghi chú

Extraction/local inference

CPU/GPU tùy model

Cao khi data pilot

W1–W5

Batch; cache outputs; không tranh locked KGE.

TransE seeds

T4

CORE cao nhất

W2–W6, W8

Snapshot×3 seeds; selected extra seeds chỉ sensitivity.

Procrustes/null/statistics

CPU

CORE

W3–W10

Không đáng kể VRAM; bootstrap CPU parallel.

Path extraction

CPU/Neo4j

SUPPORT

W4–W6

Bounded 1–3 hop; cache theo snapshot/query hash.

ICL inference

T4

SUPPORT

W4–W8

Không chạy đồng thời KGE locked jobs.

QLoRA pilot

T4

STRETCH

Một slot sau W4 gate

Hủy nếu core chưa pass; không để chiếm nửa dự án.

7. Top bottlenecks và can thiệp

Xếp hạng

Rủi ro

Cảnh báo sớm

Can thiệp muộn nhất

Fallback

1

Temporal leakage/evidence semantics

Fact/mapping sau cutoff xuất hiện; correction backfill.

W2

Dừng downstream; sửa as-of; rebuild.

2

Entity resolution

Merge/split sai ở entity bậc cao; overlap giả.

W3

Conservative IDs; manual core mapping.

3

Extraction quality

Core relation/evidence-time error cao.

W3

Giảm ontology; adjudicate support facts.

4

Recurring QA/complete support

Attrition cao; panel sống kém.

W5

Targeted annotation/collection; hạ query types.

5

Meaningful temporal evolution

Transitions gần như không đổi hoặc batch artifacts.

W4

Event-balanced merge; giảm S; đổi window/domain.

6

Alignment/null identifiability

Rank thiếu, holdout fail, zero MAD rộng.

W4

d32; fixed bucket merge; Relative Landmark fallback.

7

Statistical power

Within variation thấp; MDE/interval quá lớn.

W5

Tăng queries có mục tiêu; downgrade claim.

8

Schedule/integration

Không có vertical slice cuối W2.

W2

Cắt QLoRA/path/extra snapshots; pair owners.

8. Scope-cut order

Tình huống

Cắt/đổi theo thứ tự

Trễ 3 ngày

Hủy max-path sensitivity và extra covariance; giữ core controls/falsification.

Trễ 1 tuần

Hủy QLoRA; giảm human evaluation; path chỉ path_exists/count hoặc cắt hoàn toàn.

Trễ 2 tuần

MVR-only: A/B, H1/H2, pseudo-drift; 8–10 snapshots; ICL/path không trên critical path.

Dataset quality yếu

Giảm relation ontology, conservative entity IDs, targeted evidence; không scale dữ liệu bẩn.

Procrustes fail

Dùng Relative Landmark Drift; báo measurement limitation; không thay anchor theo outcome.

Power yếu

Tăng recurring queries có mục tiêu hoặc giảm claim thành controlled descriptive case study; không thêm bootstrap để giả power.

QLoRA fail

Dừng; evidence-constrained ICL là auditor; báo negative result hoặc not attempted.

9. Deliverables

Mã nguồn, configs, manifests và hướng dẫn tái lập.

Temporal KG dataset; append-only fact store; snapshot Parquet + SHA-256; Neo4j materialization.

Recurring multi-hop QA benchmark với support IDs, cutoff, hop, OOV và population metadata.

TransE checkpoints, Procrustes artifacts, same-snapshot null, raw displacement/excess/SED tables.

Frozen/Updated results; H1/H2 analysis; pseudo-drift falsification; optional H3a/ICL results.

Figures, tables, failure taxonomy, technical report, slides, demo và release package.