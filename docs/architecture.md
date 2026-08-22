# Kiến trúc nghiên cứu và codebase

Tài liệu này mô tả **software architecture** của repository và cách các module phụ thuộc lẫn nhau. Scientific source of truth vẫn là `configs/protocol_v1.yaml` cùng authoritative source artifacts được khóa trong `data/manifests/sources.lock.json`.

## 1. Luồng nghiên cứu chính

```text
sources
  ↓
ingestion
  ↓
extraction
  ↓
temporal ───────────────→ evaluation (QA construction)
  ↓
kge
  ↓
drift ──────────────────→ evaluation
                              ↓
                           statistics

temporal ─→ paths ─────────→ evaluation

evidence / QA ─────────────→ auditor
```

Đường găng nghiên cứu là:

```text
temporal integrity → measurement validity → locked experiment
```

`paths` và `auditor` thuộc SUPPORT. QLoRA, nếu được mở trong auditor workflow, thuộc STRETCH và không được chặn đường găng CORE.

## 2. Source of truth

| Nội dung | Source of truth |
|---|---|
| Estimand, population, candidate universe, freeze deadline | `configs/protocol_v1.yaml` + authoritative sources |
| Canonical graph snapshot | canonical Parquet snapshot |
| Graph query/path materialization | Neo4j, phải parity với canonical snapshot |
| Source provenance | `data/manifests/sources.lock.json` |
| Run provenance | experiment manifest |
| Correction sau freeze | `amendments/*.yaml` |
| Generated outputs | immutable artifact + hash; không sửa tay |

Neo4j không phải scientific data source thứ hai. Nếu Neo4j khác canonical Parquet, canonical Parquet thắng và materialization phải được rebuild.

## 3. Ownership theo M1–M4

- **M1 — Data/KG:** `ingestion`, `extraction`, `temporal`, data config.
- **M2 — Drift:** `kge`, `drift`, alignment/null implementation.
- **M3 — Auditor/Path:** `paths`, `auditor`.
- **M4 — Eval/Stats:** `evaluation`, `statistics`, experiment/evaluation contracts.

Ownership là trách nhiệm implement/review chính, không có nghĩa module làm việc độc lập. Interface giữa hai module phải được upstream và downstream owner liên quan review.

## 4. Quy tắc dependency

1. Downstream module đọc immutable artifacts/manifests, không phụ thuộc vào hidden in-memory state từ local run của người khác.
2. Module không được tự suy ra một scientific choice đã thuộc protocol hoặc freeze schedule.
3. Downstream outcomes không được dùng để chọn snapshot boundaries, anchors, null rules, QA feasibility IDs hoặc các lựa chọn pre-registered khác.
4. SUPPORT module phải degrade an toàn: no-path phải trả exact B ranking; auditor là thí nghiệm riêng nếu không thực sự rerank.
5. Mọi output dùng cho phân tích phải truy ngược được về `git_commit`, resolved config, seed và input hashes qua experiment manifest.
6. Khi interface thay đổi, phải cập nhật tests và docs liên quan trong cùng PR.

## 5. Ranh giới dữ liệu giữa các module

### `ingestion → extraction`

Bàn giao raw source record và provenance; không bàn giao trạng thái KG đã diễn giải.

### `extraction → temporal`

Bàn giao evidence/fact candidates có source span/hash, extractor version và thời gian liên quan.

### `temporal → kge`

Bàn giao canonical snapshot + mapping + snapshot manifest/hash. KGE không được dựng snapshot riêng.

### `kge → drift`

Bàn giao checkpoint, mapping hashes, seed và resolved config hash.

### `drift → evaluation/statistics`

Bàn giao alignment/null/drift artifacts đã có diagnostics và hash; không bàn giao một dataframe local không có provenance.

### `evaluation → statistics`

Bàn giao immutable RR/ranking rows và Query×Transition panel theo population/candidate universe đã khóa.

## 6. Nguyên tắc thiết kế

- **Canonical first:** Parquet snapshot là chuẩn khoa học; Neo4j chỉ materialize để query/path.
- **Hash-addressable:** artifact quan trọng phải có hash và manifest.
- **Outcome blind upstream:** lựa chọn upstream không nhìn downstream outcome bị cấm.
- **Fail-fast:** gate fail thì dừng hoặc hạ scope theo protocol, không cứu kết quả bằng tuning hậu nghiệm.
- **Version instead of overwrite:** rerun hợp lệ tạo version mới; run cũ được giữ để audit.

Xem `docs/modules.md` để biết contract từng module và `docs/data_and_artifacts.md` để biết contract artifact.
