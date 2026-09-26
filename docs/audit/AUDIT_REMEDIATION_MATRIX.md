# Bảng Ma trận Khắc phục Audit (Audit Remediation Matrix)

**Phiên bản:** 1.0.0  
**Ngày khởi tạo:** 2026-09-26  
**Nhánh cơ sở:** `fix/data-pipeline-compliance`  
**Nhánh tích hợp dài hạn:** `reconcile/pipeline-drift-compliance`  
**Nguyên tắc chỉ đạo:** Không merge wholesale `feature/integrated-kge-drift`. Giữ nguyên storage/gate/provenance hardening của `fix/data-pipeline-compliance`. Transplant có chọn lọc M2 và sửa từng invariant bằng regression test trước khi merge.

---

## 1. Trạng thái Tổng quan theo Nhóm Vấn đề

| Nhóm | Số lượng | Critical | High | Trạng thái hiện tại |
|---|---:|---:|---:|---|
| **0. Baseline & Authority** (A01, A30) | 2 | 0 | 2 | A01, A30 RESOLVED |
| **1A. Provenance Identity** (A05, A06) | 2 | 1 | 1 | A05, A06 RESOLVED |
| **1B. Temporal Axes** (A07, A08) | 2 | 1 | 1 | A07, A08 RESOLVED |
| **1C. Entity Mapping** (A09) | 1 | 1 | 0 | A09 RESOLVED |
| **1D. Revision Semantics** (A10, A11) | 2 | 0 | 2 | A10, A11 RESOLVED |
| **1E. Snapshot Edge Separation** (A12) | 1 | 1 | 0 | A12 RESOLVED |
| **1F. Exclusion Quarantine** (A13, A14) | 2 | 1 | 1 | A13, A14 RESOLVED |
| **1G. Config & Gates** (A02, A03, A04) | 3 | 2 | 1 | RESOLVED |
| **1H. Snapshot Manifest** (A15, A16) | 2 | 0 | 2 | RESOLVED |
| **1I. Fingerprint & Lineage** (A27, A28, A46) | 2 | 1 | 1 | RESOLVED |
| **2A. Centered Procrustes** (A19) | 1 | 1 | 0 | RESOLVED |
| **2B. Multi-Seed Drift** (A20) | 1 | 1 | 0 | RESOLVED |
| **2C. 6-Pair Transition Null** (A21) | 1 | 1 | 0 | RESOLVED |
| **2D. Leave-Target-Out** (A22) | 1 | 1 | 0 | RESOLVED |
| **2E. Adjacent Merge** (A23) | 1 | 0 | 1 | RESOLVED |
| **2F. Filtered Negative Sampling** (A17) | 1 | 0 | 1 | RESOLVED |
| **2G. Alignment Diagnostics** (A24, A25) | 2 | 0 | 2 | A24, A25 RESOLVED |
| **3. Artifact Unification** (A26) | 1 | 0 | 1 | A26 RESOLVED |
| **4. Fixture & Governance** (A29, A31–A34) | 5 | 0 | 5 | A29, A31 RESOLVED, A32 FROZEN, A33-A34 Governance |
| **Tổng cộng** | **34** | **11** | **23** | **31 RESOLVED, 1 FROZEN, 2 GOVERNANCE** |

---

## 2. Chi tiết 34 Mục Khắc phục (A01 – A34)

| ID | Mức độ | Tiêu đề tóm tắt | Tệp ảnh hưởng | Yêu cầu khoa học / Test kiểm chứng | Trạng thái |
|---|---|---|---|---|---|
| **A01** | HIGH | Phân kỳ nhánh giữa compliance và integrated | `src/` | Tạo nhánh `reconcile/pipeline-drift-compliance` từ `fix/data-pipeline-compliance`, transplant M2 chọn lọc. | `RESOLVED` |
| **A02** | CRITICAL | Config bundle thiếu runtime configs | `src/kg_pipeline/run.py`, `extract.py` | `proposed_config_bundle.yaml` phải chứa resolved ontology, entity catalog, adapter. | `RESOLVED` |
| **A03** | HIGH | Trộn lẫn quyền Ticket-A và extraction | `src/kg_pipeline/run.py`, `cli.py` | Tách biệt stage-level permissions: InventoryRun cấm LLM, ExtractionRun theo config. | `RESOLVED` |
| **A04** | CRITICAL | Downstream không bắt buộc Gate A PASS | `src/kg_pipeline/cli.py`, `extract.py` | Extraction/adjudication/snapshot phải từ chối chạy nếu Gate A != PASS trên production. | `RESOLVED` |
| **A05** | CRITICAL | `source_id` bị dùng làm `body_variant_id` | `src/kg_pipeline/extract.py`, `claims.py` | Tách `ClaimCandidate` khỏi `ClaimProvenance` (nối qua membership tới source_version/retrieval). | `RESOLVED` |
| **A06** | HIGH | `body_to_sources` không được nạp dữ liệu | `src/kg_pipeline/adjudicate.py` | Điền ánh xạ từ `memberships` và `retrievals` để bảo toàn luồng trust. | `RESOLVED` |
| **A07** | CRITICAL | Fallback `valid_from` $\to$ `evidence_observed_at` | `src/kg_pipeline/adjudicate.py` | Tách hoàn toàn trục quan sát và trục hiệu lực. Thiếu quan sát $\to$ `EVIDENCE_TIME_UNAVAILABLE`. | `RESOLVED` |
| **A08** | HIGH | `ingested_at_real` lấy từ manifest time | `src/kg_pipeline/adjudicate.py` | Phải phản ánh đúng mốc thời gian thu thập thực tế từ log retrieval. | `RESOLVED` |
| **A09** | CRITICAL | Thiếu versioned temporal entity mapping | `src/temporal/snapshot.py`, `adjudicate.py` | Entity resolution phải theo mốc `mapping_available_at <= cutoff`. | `RESOLVED` |
| **A10** | HIGH | `LogicalFactID` không hỗ trợ state replacement | `src/kg_pipeline/adjudication.py` | Khóa logic phải cấu hình theo từng quan hệ trong `ontology.yaml` (state vs event). | `RESOLVED` |
| **A11** | HIGH | Thiếu chuỗi revision/supersession thực | `src/kg_pipeline/adjudication.py` | Hỗ trợ 4 loại revision (`creation`, `state_change`, `correction`, `retraction`) và `supersedes_version_id`. | `RESOLVED` |
| **A12** | CRITICAL | Đồ thị snapshot nhân bản edge theo FactVersion | `src/kg_pipeline/snapshot_runner.py` | Tách `snapshot_edges` (unique triples) khỏi `snapshot_edge_support` (provenance join). | `RESOLVED` |
| **A13** | CRITICAL | Snapshot runner tạo span $[0, 1)$ và hash giả | `src/kg_pipeline/snapshot_runner.py` | Fail closed: loại bỏ mọi hành vi tạo dữ liệu giả, đưa vào kiểm dịch. | `RESOLVED` |
| **A14** | HIGH | FactVersion lỗi bị drop âm thầm | `src/kg_pipeline/snapshot_runner.py` | Xuất `snapshot_exclusions.parquet` có lý do cấu trúc cho mọi bản ghi bị loại. | `RESOLVED` |
| **A15** | HIGH | Ngữ nghĩa snapshot hash bị phân mảnh | `src/temporal/snapshot.py`, `storage.py` | Định nghĩa rõ: `graph_semantic_hash`, `support_semantic_hash`, `artifact_physical_sha256`, `manifest_hash`. | `RESOLVED` |
| **A16** | HIGH | KGE adapter không verify `SnapshotManifest` | `src/kge/adapter.py` | Adapter phải xác thực tính toàn vẹn và chữ ký của manifest trước khi huấn luyện. | `RESOLVED` |
| **A17** | HIGH | Negative sampling TransE không lọc triples dương | `src/kge/model.py`, `trainer.py` | Rejection sampling không trùng triple dương tại cutoff; entity thay thế $\neq$ entity gốc. | `RESOLVED` |
| **A18** | MEDIUM | Thiếu validation split / early stopping | `src/kge/trainer.py` | Bổ sung dev loss tracking và dev dimension selection. | `RESOLVED` |
| **A19** | CRITICAL | Drift cosine dùng translated thay centered vector | `src/drift/procrustes.py`, `metrics.py` | Đo estimand: $1 - \cos((x - \mu_s)Q, y - \mu_t)$ không cộng lại $\mu_t$. | `RESOLVED` |
| **A20** | CRITICAL | Temporal drift dùng seed 13 thay median 3 seeds | `src/drift/pipeline.py`, `metrics.py` | Đo 3 cặp seed $(13\to 13, 37\to 37, 101\to 101)$, lấy median 3 làm độ dịch chuyển. | `RESOLVED` |
| **A21** | CRITICAL | Null chỉ lấy 3 cặp endpoint thay 6 cặp transition | `src/drift/pipeline.py`, `null.py` | Transition null gộp 6 cặp: 3 cặp tại $S_t$ + 3 cặp tại $S_{t+1}$. | `RESOLVED` |
| **A22** | CRITICAL | Null không loại trừ chính entity đích (Leave-Target-Out) | `src/drift/null.py`, `metrics.py` | Khi tính median/MAD cho entity $e$, loại trừ các quan sát của $e$ khỏi bucket tham chiếu. | `RESOLVED` |
| **A23** | HIGH | Merge bucket thưa chọn sai bucket đông nhất | `src/drift/null.py` | Nghiêm ngặt chỉ merge với bucket lân cận (adjacent) theo bậc phân tầng. | `RESOLVED` |
| **A24** | HIGH | Chẩn đoán căn chỉnh không chặn xuất SED+ | `src/drift/metrics.py`, `procrustes.py` | Trả về `ALIGNMENT_UNAVAILABLE`, SED+ = None nếu rank suy biến hoặc holdout gap vượt ngưỡng. | `RESOLVED` |
| **A25** | HIGH | Tham số drift bị hard-code trong code | `src/drift/metrics.py`, `null.py` | Đọc toàn bộ tham số từ cấu hình protocol đã đóng băng. | `RESOLVED` |
| **A26** | HIGH | KGE checkpoint dùng plain json thay immutable writer | `src/kge/checkpoint.py` | Đồng nhất hạ tầng lưu trữ bất biến có sidecar SHA-256 tương tự M1. | `RESOLVED` |
| **A27** | CRITICAL | Run fingerprint bỏ qua `src/kge` và `src/drift` | `src/kg_pipeline/run.py` | `package_fingerprint` phải bao phủ toàn bộ mã nguồn pipeline. | `RESOLVED` |
| **A28** | HIGH | Checkpoint thiếu git commit thật | `scripts/run_vertical_slice.py` | Ghi nhận commit hash và trạng thái dirty vào mọi checkpoint. | `RESOLVED` |
| **A29** | HIGH | Cutoff 2021–2023 xung đột phạm vi corpus 2025–2026 | `config/snapshot_cutoffs.yaml` | Tách biệt cấu hình fixture kiểm thử khỏi cấu hình corpus khóa. | `RESOLVED` |
| **A30** | HIGH | Cạnh tranh nguồn sự thật giữa `config/` và `configs/` | `configs/protocol_v1.yaml` | `configs/protocol_v1.yaml` là thẩm quyền duy nhất; `config/` là dẫn xuất thực thi. | `RESOLVED` |
| **A31** | HIGH | Lệch schema giữa schema.yaml, PyArrow và dataclass | `config/schema.yaml`, `contracts.py` | Chuẩn hóa đồng nhất định nghĩa trường trên toàn bộ các lớp biểu diễn. | `RESOLVED` |
| **A32** | HIGH | Evaluation và Statistics chưa hoàn thiện | `src/evaluation/`, `src/statistics/` | Đóng băng cho tới khi hoàn tất nghiệm thu khoa học M1/M2. | `FROZEN` |
| **A33** | HIGH | Thiếu bằng chứng CI trên các nhánh tính năng | `.github/workflows/ci.yml` | Đảm bảo CI chạy và pass 100% trên PR tích hợp. | `READY_FOR_PR` |
| **A34** | HIGH | Chưa bật bảo vệ nhánh | GitHub Settings | Bật branch protection trước khi chạy thực nghiệm khóa. | `GOVERNANCE` |
| **A32** | HIGH | Evaluation và Statistics chưa hoàn thiện | `src/evaluation/`, `src/statistics/` | Đóng băng cho tới khi hoàn tất nghiệm thu khoa học M1/M2. | `FROZEN` |
| **A33** | HIGH | Thiếu bằng chứng CI trên các nhánh tính năng | `.github/workflows/ci.yml` | Đảm bảo CI chạy và pass 100% trên PR tích hợp. | `OPEN` |
| **A34** | HIGH | Chưa bật bảo vệ nhánh | GitHub Settings | Bật branch protection trước khi chạy thực nghiệm khóa. | `OPEN` |

---

## 3. Quy trình Kiểm thử Bắt buộc (Conformance Loop)

Mỗi mục Axx khi được sửa đổi phải tuân thủ nghiêm ngặt 8 bước:
1. **Viết test tái hiện bug trước:** Viết trong `tests/scientific/` hoặc `tests/kg_pipeline/`; xác nhận test fail trên code chưa sửa.
2. **Sửa code tối thiểu:** Chỉ sửa đúng điểm vi phạm invariant khoa học.
3. **Targeted unit test:** Kiểm tra test mới pass.
4. **Upstream/downstream contract test:** Kiểm tra các module liên quan không bị ảnh hưởng.
5. **Full test suite & Ruff:** Đảm bảo toàn bộ test của repo và kiểm tra tĩnh đều xanh.
6. **Deterministic check:** Xác thực băm hash tái lập.
7. **Cập nhật ma trận:** Điền commit, test file và chuyển trạng thái sang `RESOLVED`.
8. **Commit có thông điệp chuẩn hóa:** `fix(Axx): <nội dung ngắn gọn>`.
