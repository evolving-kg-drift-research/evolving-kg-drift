# evolving-kg-drift

Codebase nghiên cứu cho đề tài:

**Định lượng độ trôi biểu diễn có hiệu chỉnh nhiễu cho suy luận đa bước trên đồ thị tri thức tiến hóa**  
*(Noise-Calibrated Representation Drift Quantification for Multi-Hop Reasoning on Evolving Knowledge Graphs)*

---

## 1. Tôn chỉ nghiên cứu & Đường găng

Đề tài tập trung vào việc **đo lường độ trôi biểu diễn (representation drift) thực sự vượt qua retraining noise** trên không gian nhúng đồ thị tri thức (KGE) tiến hóa theo thời gian và đánh giá tác động của nó tới năng lực suy luận đa bước (multi-hop QA). Đề tài **không** nhằm mục đích phát minh kiến trúc KGE mới.

### Pipeline 9 chặng nghiên cứu

```text
Temporal evidence
→ versioned facts
→ deterministic snapshots
→ TransE multi-seed
→ centered Procrustes
→ same-snapshot empirical null
→ drift / SED+
→ recurring QA
→ H1/H2 estimation
→ pseudo-drift falsification
```

### Thứ tự ưu tiên bất biến

Đường găng khoa học phải được ưu tiên tuyệt đối theo thứ tự:

```text
temporal integrity → measurement validity → locked experiment
```

- **CORE (Đường găng bắt buộc):** Tính toàn vẹn thời gian (M1), căn chỉnh không gian & ước lượng độ trôi vượt nhiễu (M2), đánh giá suy luận đa bước & kiểm định thống kê (M4).
- **SUPPORT (Mô-đun hỗ trợ):** `paths` (Arm C simple paths) và `auditor` (semantic audit) thuộc nhóm hỗ trợ; nếu không có đường đi hợp lệ, Arm C phải thoái lui chính xác về Arm B (`exact-B fallback`).
- **STRETCH (Mở rộng tùy chọn):** QLoRA, nếu được mở trong auditor workflow, chỉ là nhánh mở rộng và **tuyệt đối không được làm chậm tiến độ phần CORE**.

---

## 2. Bản đồ phân công Module (M1–M4 Ownership Matrix)

Trách nhiệm triển khai và tích hợp được phân định rõ ràng giữa các nhóm tác vụ:

| Nhóm / Module | Thư mục mã nguồn | Cấu hình tham chiếu | Trách nhiệm chính | Cổng nghiệm thu (Gate) |
|---|---|---|---|---|
| **M1 — Data/KG** | `src/ingestion/`<br>`src/extraction/`<br>`src/temporal/` | `configs/data.yaml` | • Thu thập bài viết tin tức và bảo toàn provenance.<br>• Trích xuất `FactVersion` append-only.<br>• Dựng snapshot tất định as-of theo `cutoff`.<br>• Đảm bảo tính tương đương giữa Parquet và Neo4j. | **W1** (Source Lock)<br>**G1** (Temporal Integrity) |
| **M2 — Drift** | `src/kge/`<br>`src/drift/` | `configs/kge.yaml` | • Huấn luyện backbone `TransE-L2` (seeds `13, 37, 101`).<br>• Căn chỉnh Centered Orthogonal Procrustes SVD.<br>• Xây dựng empirical null cùng snapshot theo degree bucket.<br>• Đo lường $\delta_{time}$, signed excess $r$ và $SED^+$. | **G3** (Backbone & Alignment Diagnostics) |
| **M3 — Auditor/Path** | `src/paths/`<br>`src/auditor/` | `configs/protocol_v1.yaml` | • Cung cấp simple bounded path features cho Arm C.<br>• Đảm bảo cơ chế exact-B fallback khi không có path.<br>• Thực thi semantic audit có ràng buộc bằng chứng (`RETAIN/REPLACE/DECAY`). | **G5** (Support Modules Gate) |
| **M4 — Eval/Stats** | `src/evaluation/`<br>`src/statistics/` | `configs/statistics.yaml` | • Xây dựng recurring QA panel và candidate universe (Seen-at-T1).<br>• Thực thi xếp hạng Arm A, B, C và chấm điểm OOV.<br>• Ước lượng Two-Way Fixed Effects cho H1 ($β_d$).<br>• Suy luận bằng Wild Cluster Bootstrap và kiểm định pseudo-drift. | **G4** (QA Panel & Power)<br>**G6** (Protocol Freeze) |

---

## 3. Cấu trúc thư mục (Repository Layout)

```text
evolving-kg-drift/
├── configs/                  # Cấu hình tham số đã freeze (data, kge, statistics, protocol_v1)
│   └── schemas/              # Schema kiểm thực manifest thí nghiệm
├── data/
│   ├── raw/                  # Dữ liệu nguồn thô (JSON/HTML), bất biến kèm SHA-256
│   ├── event_store/          # Kho lưu trữ FactVersion dạng append-only
│   ├── snapshots/            # Snapshots Parquet chuẩn hóa theo mốc thời gian
│   ├── manifests/            # Manifests khóa nguồn và khóa giao thức W7
│   └── locked_test/          # Dữ liệu kiểm thử bị khóa (nghiêm cấm truy cập trước W8)
├── docs/                     # Tài liệu kỹ thuật: kiến trúc, modules, data contracts, gates
├── experiments/              # Định nghĩa thí nghiệm và MANIFEST_TEMPLATE.yaml
├── outputs/                  # Artifacts sinh ra (checkpoints, alignment, null, drift, rankings)
├── reports/                  # Báo cáo tổng hợp kết quả nghiên cứu và release package
├── scripts/                  # Kịch bản tự động kiểm tra cổng (W1, G1, W7, freeze)
├── sources/                  # Tệp tài liệu nguồn căn cứ pháp lý của đề tài
├── src/                      # Mã nguồn chính chia theo 4 nhóm M1–M4
└── tests/                    # Bộ kiểm thử: contracts, fixtures, và hard invariants
```

---

## 4. Thiết lập môi trường phát triển (Developer Onboarding)

### Yêu cầu hệ thống
- **Python:** Phiên bản `3.10` hoặc `3.11`.
- **Git:** 2.30+.
- **Docker:** (Tùy chọn) Để khởi chạy Neo4j phục vụ kiểm thử tính tương đương Parquet/Neo4j.

### Cài đặt môi trường ảo

#### Trên Windows (PowerShell)
```powershell
# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt môi trường ảo
.\.venv\Scripts\Activate.ps1

# Nâng cấp pip và cài đặt dependencies bị khóa
python -m pip install --upgrade pip
pip install -r requirements.lock.txt
```

#### Trên Linux / macOS (Bash)
```bash
# Tạo môi trường ảo
python3 -m venv .venv

# Kích hoạt môi trường ảo
source .venv/bin/activate

# Nâng cấp pip và cài đặt dependencies bị khóa
python -m pip install --upgrade pip
pip install -r requirements.lock.txt
```

### Kiểm tra chất lượng mã nguồn & Gate kiểm soát
Trước khi tạo commit hoặc mở PR, chạy chuỗi lệnh kiểm tra bắt buộc:

```bash
# 1. Kiểm tra format và linting code
python -m ruff check .

# 2. Chạy unit tests và integration tests
python -m pytest -q

# 3. Kiểm tra các cổng khoa học (chế độ CI)
python scripts/verify_w1.py --ci
python scripts/verify_g1.py --ci
python scripts/verify_w7.py --ci
python scripts/check_freeze.py
```

### (Tùy chọn) Khởi chạy Neo4j cục bộ cho Parquet/Neo4j Parity
Để kiểm thử tính tương đương giữa Parquet snapshot và Neo4j materialization:

```bash
docker run -d \
  --name neo4j-evolving-kg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/research_password \
  neo4j:5-community
```

---

## 5. Trạng thái Scaffold & Các chốt chặn kiểm soát (Gates & Freezes)

### Cảnh báo về trạng thái ban đầu
Repository này khởi đầu ở trạng thái **Week-1 scaffold**, không phải bằng chứng rằng các điều kiện toàn vẹn khoa học đã hoàn thành.

Ở thời điểm bootstrap, 14 hard-invariant tests trong `tests/test_hard_invariants.py` được gắn `@pytest.mark.skip` có chủ đích. **CI báo xanh ở giai đoạn này chỉ có nghĩa cấu trúc repo và config contract nhất quán; tuyệt đối không đồng nghĩa với việc G1 temporal integrity đã đạt.**

### Cổng W1 — Authoritative Sources Lock
Repository không coi việc chép một chuỗi hash vào file cấu hình là đủ để xác minh nguồn:
1. Đặt đúng bytes của 3 tệp tài liệu nguồn pháp lý vào thư mục `sources/`:
   - `sources/huce_evolving_kg_modular_proposal(8).pdf`
   - `sources/Research_Execution_Plan_v1.0.md`
   - `sources/Research_Execution_Plan_v1.1_Patch.md`
2. Kiểm tra `data/manifests/sources.lock.json` khớp đường dẫn và SHA-256.
3. Chạy xác thực nghiêm ngặt:
   ```bash
   python scripts/verify_w1.py
   ```
4. Chỉ khi pass mới tạo tag đóng băng tuần 1:
   ```bash
   python scripts/freeze_w1.py
   git push origin v0.1-source-lock
   ```

### Cổng G1 — Temporal Integrity (Cuối W2)
Trước khi coi cổng G1 là đạt, tối thiểu 4 bài test sau trong `tests/test_hard_invariants.py` phải được lập trình hoàn chỉnh và **bỏ decorator `@pytest.mark.skip`**:
- `test_no_future_evidence` (Không rò rỉ bằng chứng tương lai vào snapshot quá khứ)
- `test_no_future_entity_mapping` (Không dùng từ điển mapping tương lai)
- `test_snapshot_reproducible` (Tái dựng snapshot tất định theo SHA-256)
- `test_canonical_parquet_neo4j_parity` (Đồng nhất tập cạnh giữa Parquet và Neo4j)

Chạy kiểm tra G1:
```bash
python scripts/verify_g1.py
```
*(Script sẽ lập tức báo `FAIL` nếu còn bất kỳ test nào trong 4 test trên bị skip).*

### Cổng G6 / W7 — Protocol Freeze & Chính sách Amendment
- Toàn bộ tham số `TO_BE_FROZEN_*` trong `configs/protocol_v1.yaml` phải được chốt trước W7.
- Tạo `data/manifests/w7_freeze.yaml` từ `W7_FREEZE_TEMPLATE.yaml` và chạy:
  ```bash
  python scripts/verify_w7.py
  python scripts/freeze_protocol.py
  git push origin protocol-v1-frozen
  ```
- **Quy tắc sửa đổi sau Freeze:** Tuyệt đối không sửa đổi các file trong `configs/` vì lý do tối ưu kết quả (performance preference). Bất kỳ thay đổi kỹ thuật nào do lỗi hệ thống (bug fix) đều phải có tài liệu sửa đổi theo mẫu `amendments/TEMPLATE.yaml` và lưu vết lần chạy cũ để phục vụ kiểm toán khoa học.

---

## 6. Dữ liệu, Artifacts & Khả năng tái lập (Reproducibility)

1. **Chân lý dữ liệu (Canonical Source of Truth):**
   - Snapshot Parquet lưu trữ dạng chuẩn tắc là chân lý khoa học. Neo4j chỉ là lớp truy vấn đồ thị được hiện thực hóa (materialized layer). Nếu có sự sai lệch giữa Parquet và Neo4j, **Parquet luôn thắng** và Neo4j phải được tái dựng lại.
2. **Experiment Manifests:**
   - Mọi lần chạy tạo ra kết quả phân tích đều phải sinh một experiment manifest theo chuẩn `configs/schemas/experiment_manifest.schema.yaml`, ghi lại đầy đủ: Git commit, trạng thái working tree dirty, hash cấu hình, seed, và hash toàn bộ artifact đầu vào/đầu ra.
3. **Chính sách tệp nhị phân & Git LFS:**
   - Git LFS **không bật mặc định**. Các tệp nhị phân lớn (`*.parquet`, `*.pt`, `*.ckpt`, `*.npz`) không được commit trực tiếp vào Git. Chỉ commit mã nguồn, file cấu hình và manifest chứa mã băm SHA-256.

---

## 7. Lộ trình triển khai tiếp theo: Vertical Slice (10–20 bài báo)

**Cảnh báo:** Không sử dụng `src/temporal/snapshot.py` cho dữ liệu thật khi hàm `build_snapshot()` vẫn còn mang `raise NotImplementedError`.

Nhiệm vụ ưu tiên hàng đầu của nhóm là mở khóa cổng G1 và xây dựng một **Vertical Slice tối thiểu** khép kín toàn bộ pipeline:

```text
10–20 bài viết mẫu (data/raw/)
→ Trích xuất FactVersion (src/extraction/)
→ 3 snapshots nhỏ tất định as-of (src/temporal/)
→ TransE d32 smoke test với 3 seeds (src/kge/)
→ Centered Procrustes alignment & empirical null (src/drift/)
→ 5–10 recurring multi-hop queries mẫu (src/evaluation/)
→ A/B dry-run ranking và xuất bảng Query × Transition (src/statistics/)
```

---

## 8. Hướng dẫn đọc tài liệu (Documentation Hierarchy)

Trước khi bắt tay vào triển khai mã nguồn cho từng module, thành viên dự án cần đọc tài liệu trong thư mục `docs/` theo thứ tự:

1. `docs/architecture.md` — Kiến trúc hệ thống, luồng dữ liệu giữa các module và ranh giới ownership.
2. `docs/modules.md` — Đặc tả chi tiết từng module: mục đích, đầu vào, đầu ra, bất biến bắt buộc và hành vi bị cấm.
3. `docs/data_and_artifacts.md` — Quy ước đặt tên, serialization, hashing và quản lý manifest.
4. `docs/gates_and_freeze.md` — Cơ chế kiểm soát fail-fast gates, lịch trình đóng băng W1 $\to$ W7.
5. `docs/team_handoff.md` — Hướng dẫn bàn giao công việc ban đầu và tiêu chí Definition of Done (DoD).
6. `CONTRIBUTING.md` — Quy tắc tạo nhánh Git, mở PR, quy định ngôn ngữ và quy trình amendment.

> **LƯU Ý:** Các tài liệu hướng dẫn trên giải thích cách thức tổ chức kỹ thuật. Nếu có bất kỳ điểm nào mâu thuẫn với `configs/protocol_v1.yaml` hoặc hồ sơ nghiên cứu trong `contexts/`, **scientific protocol luôn là căn cứ tối cao**.
