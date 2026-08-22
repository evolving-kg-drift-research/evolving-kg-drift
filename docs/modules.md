# Contract của từng module

File này là **engineering map** của repository. Nó không thay thế scientific protocol. Nếu nội dung ở đây khác `configs/protocol_v1.yaml` hoặc authoritative research sources, protocol/source thắng.

## `src/ingestion` — M1 Data/KG

### Mục đích

Thu thập public historical sources và giữ provenance mà không nhầm `ingested_at_real` với historical evidence availability.

### Đầu vào

- Source list/URL.
- Source metadata.
- Ingestion configuration.

### Đầu ra

- Raw/immutable source records.
- Provenance metadata phục vụ `extraction`.

### Trách nhiệm

- Giữ source identity.
- Ghi acquisition metadata.
- Giữ immutable source bytes khi artifact được retain.

### Không được phép

- Dùng `ingested_at_real` làm scientific as-of axis.
- Âm thầm thay authoritative source đã khóa bằng file khác.

### Downstream

`extraction`.

### Gate / deadline

Đóng góp cho W1 source lock và G1 temporal integrity.

---

## `src/extraction` — M1 Data/KG

### Mục đích

Chuyển source evidence thành candidate facts/evidence spans có cấu trúc, đồng thời giữ extractor/config provenance.

### Đầu vào

- Ingested source records.

### Đầu ra

- Extracted evidence.
- Source/evidence offsets hoặc hashes.
- Extraction-quality fields.

### Trách nhiệm

- Version hóa extractor/config.
- Giữ liên kết từ fact candidate về evidence source.
- Tạo thông tin đủ để `temporal` quyết định state theo cutoff.

### Không được phép

- Backfill future correction vào earlier scientific state.
- Che relation/time errors bằng cách chỉ scale data volume.

### Downstream

- `temporal`.
- Extraction-quality controls có thể được `evaluation` sử dụng sau khi được protocol cho phép.

### Gate / deadline

G2 evidence/entity quality.

---

## `src/temporal` — M1 Data/KG

### Mục đích

Quản lý append-only `FactVersion` và tái dựng trạng thái KG một cách deterministic tại một `cutoff`.

### Đầu vào

- Extracted/versioned facts.
- Versioned entity mappings.
- `cutoff`.

### Đầu ra

- Canonical snapshot.
- `snapshot_hash`.
- Snapshot manifest.
- Neo4j materialization có thể được tạo từ canonical snapshot.

### Bất biến bắt buộc

- `evidence_observed_at <= cutoff`.
- Chọn latest observed version theo `LogicalFactID`.
- Áp dụng `valid_from` / `valid_to` đúng as-of state.
- Xử lý `retract` theo protocol.
- `no_future_evidence`.
- `no_future_entity_mapping`.
- Deterministic rebuild.
- Canonical Parquet/Neo4j parity.

### Không được phép

- Dùng future entity mapping.
- Viết lại old snapshot khi late correction xuất hiện.
- Dùng unstable Parquet/container metadata làm logical snapshot identity.

### Artifact sinh ra

Canonical snapshot + manifest/hash.

### Downstream

`kge`, `paths`, `evaluation`.

### Test liên quan

- `test_no_future_evidence`
- `test_no_future_entity_mapping`
- `test_snapshot_reproducible`
- `test_canonical_parquet_neo4j_parity`

### Gate / deadline

G1, cuối W2.

---

## `src/kge` — M2 Drift

### Mục đích

Train/evaluate controlled backbone `TransE-L2` trên frozen snapshots.

### Đầu vào

- Canonical snapshot.
- Entity/relation mappings.
- Resolved KGE config.

### Đầu ra

- Checkpoint.
- Mapping hashes.
- Training diagnostics.
- Experiment manifest.

### Bất biến bắt buộc

- Giữ model/norm/seed contract.
- Mapping parity giữa các seed.
- Finite losses/embeddings.
- Resolved config có provenance/hash.

### Không được phép

- Chọn dimension/config theo H1 sign.
- Chọn theo locked MRR, SED magnitude hoặc path performance.

### Downstream

`drift`, `evaluation`.

### Gate / deadline

KGE component của G3.

---

## `src/drift` — M2 Drift

### Mục đích

Căn chỉnh KGE spaces, xây same-snapshot retraining-noise empirical null và tính raw displacement, signed excess, SED+.

### Đầu vào

- Adjacent-snapshot KGE checkpoints.
- Persistent anchors.
- Same-snapshot seed runs.
- Bucket/null rules đã được freeze đúng hạn.

### Đầu ra

- Alignment artifact + diagnostics.
- Null artifacts.
- Entity-level drift table.
- Query-consumable drift artifacts.

### Bất biến bắt buộc

- Deterministic, disjoint fit/holdout anchors.
- Orthogonality/rank/holdout diagnostics.
- Không dùng forbidden alignment features.
- Deterministic bucket handling.
- Không có NaN/Inf trong drift artifacts.
- Signed raw excess phải được giữ song song với SED+.

### Không được phép

- Chọn anchors từ observed drift, RR hoặc H1 outcome.
- Ép tạo SED khi alignment/null unavailable.
- Merge bucket sau khi đã nhìn H1.

### Downstream

`evaluation`, `statistics`.

### Gate / deadline

G3, cuối W4.

---

## `src/paths` — M3 Auditor/Path

### Mục đích

Cung cấp simple bounded path features cho optional Arm C reranking.

### Đầu vào

- Current canonical/Neo4j graph materialization.
- Query.
- Candidate set.

### Đầu ra

Các path features đã đăng ký, ví dụ:

- `path_exists`
- `path_count`
- optional bounded path score nếu Dev gate cho phép

### Bất biến bắt buộc

- Arm C dùng cùng population/candidate/gold/cutoff với B.
- Khi không có valid path, C phải exact-B fallback.

### Không được phép

- Đổi H3a primary thành path-eligible-only.
- Đưa complex Path Utility/Noisy-OR vào primary analysis.

### Downstream

`evaluation`.

### Gate / deadline

G5 support-module gate, cuối W5.

---

## `src/auditor` — M3 Auditor/Path

### Mục đích

Chạy evidence-constrained semantic audit với structured labels `RETAIN/REPLACE/DECAY`, evidence IDs và abstention/grounding fields.

### Đầu vào

- Registered evidence/QA context.

### Đầu ra

- Structured audit records.
- Audit metrics.

### Bất biến bắt buộc

- Grounding/evidence-ID validation.
- Tuân thủ scope của ICL/optional QLoRA.

### Không được phép

- Tạo Arm D giả khi auditor không rerank.
- Để QLoRA chiếm critical-path time khi go/no-go prerequisites không đạt.

### Downstream

Reporting/evaluation của auditor experiment.

### Gate / deadline

ICL là SUPPORT; QLoRA go/no-go tại W4.

---

## `src/evaluation` — M4 Eval/Stats

### Mục đích

Xây và freeze recurring QA panels; chạy A/B/optional C ranking theo populations và candidate universes đã đăng ký.

### Đầu vào

- Snapshots.
- Query/gold/support metadata.
- KGE checkpoints.
- Optional path features.

### Đầu ra

- Immutable per-query rankings/RR rows.
- H1 panel inputs.
- H2/H3a contrast inputs.
- Candidate/population hashes.

### Bất biến bắt buộc

- Cutoff/gold/support validity.
- Direct-edge shortcut policy.
- Seen-at-T1 primary candidate universe.
- Open-world OOV scoring.
- Complete-support H1 population.
- Exact-B fallback cho C.

### Không được phép

- Tune QA/snapshot survival theo downstream drift hoặc RR.
- Drop hard queries hậu nghiệm mà không có rule đã đăng ký.
- Trộn primary và open-world candidate universes.

### Downstream

`statistics`.

### Gate / deadline

G4 QA/power và G5 support modules.

---

## `src/statistics` — M4 Eval/Stats

### Mục đích

Ước lượng H1/H2/H3a, uncertainty, falsification và pre-specified sensitivities từ immutable evaluation outputs.

### Đầu vào

- Analysis-ready Query×Transition panel.
- Immutable A/B/C outputs.

### Đầu ra

- Estimates.
- Confidence intervals.
- WCB outputs.
- LOTO/sensitivity artifacts.
- Falsification outputs.
- Analysis tables.

### Bất biến bắt buộc

- H1 RR-level two-way fixed effects.
- Transition-cluster WCB procedure sau khi freeze.
- Same-snapshot pseudo-drift falsification.
- Chỉ chạy registered sensitivities.

### Không được phép

- Diễn giải association thành causal effect.
- Thêm unregistered co-primary tests sau result visibility.
- Tạo power giả bằng cách coi seed pairs hoặc transitions là independent units khi protocol không cho phép.

### Downstream

`reports/` và release package.

### Gate / deadline

Statistics freeze tại W7; main analysis tại W9.

## Contract chung cho mọi module

Mọi analysis-relevant artifact phải cung cấp đủ metadata để truy ngược tối thiểu:

- `git_commit` và `dirty_state`;
- resolved `config_hash`;
- immutable input hashes;
- `seed` khi áp dụng;
- output/artifact hash;
- Dev/locked `access_state` khi áp dụng;
- `failure_reason` / `amendment_id` cho rerun hợp lệ.
