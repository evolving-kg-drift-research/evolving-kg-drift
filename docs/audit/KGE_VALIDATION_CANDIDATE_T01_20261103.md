# Candidate pilot T01 và read-only preflight — 03/11/2026

## Vai trò trong đề tài

Đây là bước chuẩn bị diagnostic experiment trong M2 trước training: cố định
input/split/sampling/configuration, kiểm provenance/coverage rồi mới đo curves.
Mục đích là giúp phân biệt tối ưu training objective với chất lượng held-out
ranking. Không là alignment/null/drift stage, không thay scientific backbone
và không dùng validation outcomes để chọn anchors/buckets/H1 population.

User yêu cầu thực hiện bước chuẩn bị candidate; không tự diễn giải yêu cầu này
thành approval cho một scientific design mới hoặc yêu cầu chạy stage training.

## Package cụ thể đã tạo

`outputs/kge_validation_candidate/20261103_t01_v1/`:

- `prepare.py`: exact preparation recipe, tạo package mới bằng exclusive writes.
- `package/candidate.yaml`: status CANDIDATE, approval null, scientific certification false.
- `package/split.json`: versioned descriptor, giữ nguyên memberships của pilot cũ.
- `package/negative_pairs.json`: 20 fixed validation pairs, chưa train.
- `package/negative_pool_provenance.json`: generator/version/hash, proposed seed13,
  sampling/filter rule và explicit NOT_SCIENTIFICALLY_REGISTERED status.
- `package/design_provenance.json`: original split/design/model-config refs/hashes,
  design hash và lịch sử sử dụng validation.
- `preflight.json`, exact code copies và schema-conformant `experiment_manifest.json`.

Không sửa bất kỳ canonical/old-run artifact nào. Script prepare từ chối chạy
lại vào cùng package đã tồn tại; muốn rebuild phải dùng version/directory mới.

| Thành phần | Candidate để review |
|---|---|
| Source | Canonical T01 trong `data/evolving_kg_downstream_v3_1` |
| Physical SHA-256 | `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e` |
| Cutoff | `2025-06-01T01:05:48+00:00`, giữ nguyên canonical manifest |
| Split | 101 train / 20 validation; giữ exact memberships từ pilot14/10 |
| Coverage | Toàn bộ167 entities và10 relations có trong training |
| Model | TransE-L2 d64, lr0.01, margin1, normalize entities true |
| Budget | Fixed50 epochs; không early stop hoặc chọn best bằng test |
| Model seeds | 13,37,101, train từ đầu riêng từng seed |
| Training sampler | Filter theo training positives; per-triple SGD như pilot cũ |
| Validation ranking | Head/tail, toàn167 training entities, filter all known T01 positives, exact-average ties |
| Validation loss | Một negative cố định/held-out triple; proposed pool seed13, cùng pool cho cả3 model seeds/epochs |
| Pool choice | Seed nhỏ nhất trong ba model seeds có sẵn; chọn trước mọi loss/rank computation, không dựa outcomes |

Model parameters được lấy từ saved backbone model config; không retune từ kết
quả drift/M4. Fixed-pool seed là **đề xuất mới** để review, chưa được đăng ký hoặc
đưa vào decision log. Pool này chỉ phục vụ đánh giá, không tham gia gradient.

## Checks đã thực hiện

1. Reuse canonical snapshot inspector và verify explicit Parquet/sidecar/YAML
   manifest hashes/counts/cutoff. Không diễn giải structural checks thành G1/G2.
2. Exact train/validation memberships bằng original split, disjoint và union bằng
  121 canonical triples. Đủ entity/relation coverage; không drop hard queries.
3. Replay20 fixed pairs bằng generator rồi replay độc lập từ `random.Random(13)`;
   mỗi negative đổi đúng head hoặc tail, cùng relation, khác original và không
   thuộc known T01 positives; không có sampling-exhaustion fallback.
4. Read-only CLI preflight và preflight với model initialization bị trap bằng
   mock: **0 models initialized/trained**.
5. Independent review rehash **57 input refs /13 artifact refs**;42 protected
   inputs từ prior completion manifest không đổi. Ruff PASS.

CLI đã chạy:

```powershell
.venv-m1/Scripts/python.exe scripts/run_kge_validation.py --config outputs/kge_validation_candidate/20261103_t01_v1/package/candidate.yaml --check-only
```

Kết quả đúng thiết kế: exit2, `ready=false`, `executed=false`; chỉ còn blockers:

- `CANDIDATE_NOT_ACTIVE`
- `EXPLICIT_DEV_APPROVAL_MISSING`

Đây là **technical inputs validated**, không gọi toàn bộ preflight READY/PASS cho
execution. Logs/evidence bổ sung:
`outputs/kge_validation_candidate_20261103_check_only.log` và
`outputs/kge_validation_candidate_20261103_independent_review.json`.

## Giới hạn và điều kiện chuyển bước

Split này đã dùng làm validation/model selection trước đây. Chạy lại sẽ cung cấp
learning curves/ranking diagnostics có kiểm soát, **không** tạo independent final
test hoặc chứng minh generalization toàn KG/multi-hop QA.

Để chuyển sang training stage, cần review candidate, chốt pool seed/recipe,
filter/budget và scope Dev; sau explicit user approval tạo **approved config mới**
và hash-bound approval artifact mới, giữ candidate package nguyên vẹn. Thay input
ref/status/approval không được rewrite candidate; approved-config design identity
phải được tính lại theo chính descriptors của config mới. Không backfill approval.

Theo AGENTS §8.2: "Never run Stage N+1 automatically." Stage hiện tại dừng sau
preparation/preflight report. M1 schema, measurement registration, threshold
conflict, pseudo/H2 và W8 requirements của full scientific rerun vẫn giữ nguyên.

Tiers: PREPARED package; TESTED runner ở lượt trước (688/10 baseline, không chạy
lại full suite vì lượt này không đổi source code); EXECUTED/VERIFIED chỉ read-only
preparation/structural/hash/replay checks trên package; **không production training
hoặc scientific gate certification**. Không commit/push.

Files repo chỉnh trong lượt này chỉ report này và `docs/PROGRESS.md`; code thực
hiện prep nằm trong output package. Diff: `git diff -- docs/PROGRESS.md` và report
untracked. Các thay đổi code từ lượt trước được giữ nguyên.
