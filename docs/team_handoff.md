# Bàn giao công việc ban đầu cho nhóm

File này dùng làm assignment sheet đầu tiên sau khi repository được tạo. Phân chia theo RACI M1–M4 nhưng mục tiêu chung đầu tiên vẫn là **end-to-end vertical slice**, không phải bốn module tách rời.

## Mục tiêu tích hợp đầu tiên

```text
10–20 sample articles
→ append-only FactVersion
→ 3 tiny snapshots
→ TransE d32 smoke / 3 seeds
→ anchor split + Procrustes + same-snapshot null
→ 5–10 recurring QA rows
→ A/B dry-run
```

Không owner nào nên tối ưu riêng module của mình khi integration path trên đang hỏng.

## M1 — Data/KG

### Phạm vi sở hữu

```text
src/ingestion/
src/extraction/
src/temporal/
configs/data.yaml
```

### Công việc đầu tiên

1. Khóa canonical snapshot serialization/hash convention phục vụ G1.
2. Implement `FactVersion` validation và `build_snapshot()` semantics.
3. Chuyển 3 temporal fixtures thành executable tests.
4. Implement/enable 4 G1 hard invariants.
5. Sinh tiny snapshot + manifest artifacts cho vertical slice.

### Tiêu chí nghiệm thu

Khi G1 work hoàn thành:

```bash
python scripts/verify_g1.py
```

phải pass và không còn skip trong 4 test cốt lõi.

### Điểm bàn giao

Bàn canonical snapshot/mapping contracts cho M2 và M4 sớm; không chờ full Stage-A ingestion.

---

## M2 — Drift

### Phạm vi sở hữu

```text
src/kge/
src/drift/
configs/kge.yaml
```

### Công việc đầu tiên

1. Định nghĩa KGE runner I/O contract trên snapshot/mapping artifacts của M1.
2. Implement TransE smoke runner cho seeds `13/37/101`.
3. Thêm deterministic anchor split interface và alignment diagnostics scaffold.
4. Định nghĩa same-snapshot null artifact contract.
5. Định nghĩa output schema cho raw displacement / signed excess / SED+.

### Tiêu chí nghiệm thu

Tiny two-transition smoke run sinh được:

- finite checkpoints;
- alignment artifact + diagnostics;
- same-snapshot null artifact;
- manifest/hash trail.

### Điểm bàn giao

M4 review shape của query-level drift inputs trước khi interface được coi là stable.

---

## M3 — Auditor/Path

### Phạm vi sở hữu

```text
src/paths/
src/auditor/
```

### Công việc đầu tiên

1. Định nghĩa path feature interface: `path_exists`, `path_count`, optional registered score.
2. Viết contract/test plan cho exact-B fallback khi không có path.
3. Định nghĩa structured evidence-constrained auditor output schema.
4. Không mở QLoRA trước khi W4 go/no-go prerequisites thực sự tồn tại.
5. Dùng spare capacity hỗ trợ M1/M4 ở fixtures, QA support IDs hoặc integration tests.

### Tiêu chí nghiệm thu

Path/auditor interfaces có thể test độc lập và không đưa SUPPORT/STRETCH vào critical path.

---

## M4 — Eval/Stats

### Phạm vi sở hữu

```text
src/evaluation/
src/statistics/
configs/statistics.yaml
experiment/evaluation contracts
```

### Công việc đầu tiên

1. Định nghĩa recurring QA row/query schema với cutoff, gold, support IDs, hop/OOV/population fields.
2. Định nghĩa candidate-universe và Frozen OOV scoring interfaces cho H2.
3. Implement experiment-manifest validation từ schema/template đã commit.
4. Scaffold A/B runner và H1 Query×Transition panel assembly.
5. Phụ trách gate/reproducibility plumbing (`verify_w7`, freeze manifest evolution) với consultation từ M1–M3.

### Tiêu chí nghiệm thu

5–10 tiny QA rows đi qua A/B dry-run và sinh immutable RR rows + run manifest.

## Review tại các integration point

| Interface | Primary owner | Cần consultation/review |
|---|---|---|
| `FactVersion → snapshot` | M1 | M2, M4 |
| `snapshot/mappings → KGE` | M2 | M1 |
| `drift artifact → H1 exposure` | M2 | M4 |
| `QA/candidate universe → A/B` | M4 | M1, M2 |
| `path features → C` | M3 | M4 |
| `protocol/G6 freeze` | M4 accountable | cả 4 |

## Definition of done cho một task

Task chưa được coi là xong chỉ vì "code compiles". Một task merge-ready thông thường cần:

- implementation hoặc scaffold đúng issue;
- tests liên quan;
- không thay đổi scientific contract âm thầm;
- cập nhật docs khi interface thay đổi;
- manifest/provenance handling cho retained artifact;
- `ruff`, `pytest` và gate check liên quan pass;
- PR nhỏ, rõ ràng và có thể review bởi owner khác.
