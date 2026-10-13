# TransE legacy T01 — 2026-10-13

User chốt T01 cho lần thử kỹ thuật trên bộ v3, sau khi đã được thông báo
các blocker mapping/provenance và phạm vi không chứng nhận khoa học.

## Phạm vi và cấu hình

- Branch: `codex/transe-legacy-exploration`; base commit `6ef3ff5`.
- Input: `data/KG_lan2/evolving_kg_downstream_v3/snapshots/snapshot_T01_canonical.parquet`.
- Input SHA-256: `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e`.
- 121 triples, 167 entities, 10 relations; IDs giữ nguyên, integer mapping sort deterministic trong T01.
- TransE-L2 của repo, dimension 32, 50 epochs, learning rate 0.01, margin 1.0,
  entity normalization bật, seeds 13/37/101; SGD từng triple, negative sampling
  lọc known-positive. `batch_size=32` là field mặc định nhưng trainer hiện không
  dùng mini-batch. Chạy CPU Python 3.12.10.
- Dùng toàn bộ T01 làm training. Không validation/test split, không MRR/Hits,
  không alignment/null/drift/QA, không chọn hyperparameter theo loss.
- Mỗi seed chạy hai lần với cùng inputs/config; lặp lại phục vụ kiểm tái lập.
- Runner độc lập có input hash allowlist theo ủy quyền legacy; không sửa hoặc
  tắt gate trong loader M2 chính thức. Không tự dựng snapshot mới.

## Kết quả

| Seed | Loss epoch 1 | Loss epoch 50 | Training lần 1 (giây) | Full checkpoint replay |
|---|---:|---:|---:|---|
| 13 | 0.966721 | 0.387573 | 0.190 | Byte-identical |
| 37 | 0.997522 | 0.414725 | 0.217 | Byte-identical |
| 101 | 1.013279 | 0.412906 | 0.211 | Byte-identical |

Loss là mean margin-ranking loss trên shuffled training triples/negatives của
từng epoch; final thấp hơn initial không chứng minh generalization hoặc đảm
bảo loss giảm đơn điệu. Thời gian trên chỉ tính training call, không tính I/O.

Embeddings có đúng 167 entity vectors và 10 relation vectors, mỗi vector 32
chiều; tất cả giá trị/loss hữu hạn. Mapping giống nhau giữa seeds. Checkpoint
save/load khớp, sidecar/hash khớp. Đối chiếu độc lập file đã lưu xác nhận các
hashes, exact repeat, dimensions, mapping và hash input giữ nguyên.

## Artifacts và tái hiện

Run: `outputs/legacy_transe/t01_20261013T164822Z_8f5250d7/`.
Thư mục chứa sáu checkpoints và sidecars, manifests từng seed, config đã resolve,
mapping, scope, environment, bản code đã chạy, code hashes, summary,
artifact inventory và independent verification. Các output được Git ignore.

Lệnh: `python scripts/run_legacy_transe_t01.py`. Mỗi lần gọi tạo run ID mới và
không ghi đè run trước; file input phải khớp hash đã chốt. Không tự chạy lại
hoặc mở rộng sang snapshot khác trong lượt này.

Working tree có thay đổi chưa commit khi chạy nên manifest ghi dirty_state=true.
Code dùng thực tế được lưu trong `code/` cùng hashes; provenance không chỉ dựa
vào base commit. `query_hash=null` vì không có QA; RAM không đo, ghi null và
chú thích thay vì tạo giá trị mặc định giả.

## Verification tiers và giới hạn

- **IMPLEMENTED:** `scripts/run_legacy_transe_t01.py`, cùng tests và báo cáo này.
- **TESTED:** 9 tests (5 input guards/mapping + 4 existing trainer tests) PASS;
  Ruff toàn repo không có lỗi lint, có ba warning quyền đọc thư mục cũ;
  diff check PASS. Một pytz deprecation warning; chưa kiểm tra Python 3.10/3.11.
- **EXECUTED:** Lần thử legacy trên T01 thật hoàn tất; không phải production M2 stage.
- **VERIFIED:** Kết quả kỹ thuật và integrity của artifacts trong run trên.
  Tái lập chỉ được chứng minh trong cùng môi trường, không phải cross-platform.

Mapping version `v1_mock`, thiếu upstream evidence và các blocker audit v3
vẫn nguyên. Kết quả không chứng nhận identity, temporal semantics, chất lượng
KG hoặc mô hình. Gate A/G1/G2 và M2 production vẫn BLOCKED. Dừng sau báo cáo;
không tự chạy T02 hoặc đánh giá dự đoán.

Không commit/push code hoặc output trong lượt này. Diff review:
`git diff -- docs/PROGRESS.md`; runner, test và báo cáo là file mới chưa stage.
