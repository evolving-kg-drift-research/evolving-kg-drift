# Dữ liệu và artifact contracts

Tài liệu này định nghĩa các engineering conventions để trao đổi dữ liệu giữa module. Scientific choices vẫn nằm trong `configs/protocol_v1.yaml`.

## 1. Canonical data flow

```text
historical source
→ raw immutable record
→ evidence span
→ canonical entity/relation mapping
→ append-only FactVersion store
→ deterministic temporal snapshot
→ KGE / alignment / null / drift
→ QA rankings
→ statistical analysis
```

Canonical Parquet snapshots là scientific source of truth. Neo4j là materialized query layer và phải có edge-set parity với canonical snapshot.

## 2. `FactVersion`

`FactVersion` là đơn vị bất biến biểu diễn một phiên bản của một logical fact.

Implementation trong `src/temporal/schema.py` phải giữ các nhóm field đã đăng ký:

| Nhóm | Field chính | Ý nghĩa |
|---|---|---|
| Identity | `FactVersionID`, `LogicalFactID` | Định danh version và logical fact xuyên revision |
| Triple/value | `subject_id`, `relation_id`, `object_id` | Canonical subject/relation/object |
| World validity | `valid_from`, `valid_to` | Khoảng hiệu lực theo source claim |
| Evidence time | `evidence_observed_at` | Trục as-of khoa học chính |
| Project provenance | `ingested_at_real` | Thời điểm project ingest, không phải historical state |
| Revision | `supersedes_version_id`, `revision_type` | Quan hệ giữa các version |
| Evidence provenance | `source_id`, `source_url`, span/hash | Truy ngược evidence |
| Pipeline provenance | extractor/entity-map version | Phiên bản code/config/mapping |
| Review | `confidence`, `adjudication_status` | Điểm vận hành và trạng thái duyệt |

Không được xóa hoặc đổi nghĩa các field này mà không đi qua protocol/amendment trail tương ứng.

## 3. Snapshot identity và hashing

`snapshot_hash` phải đại diện cho **canonical logical snapshot content**, không phải unstable Parquet container bytes hay filesystem metadata.

Trước khi `build_snapshot()` được dùng cho G1, M1 phải khóa một canonical serialization contract deterministic, tối thiểu gồm:

1. exact column order;
2. exact row sort keys;
3. timestamp/timezone normalization;
4. null representation;
5. text encoding;
6. serialization version identifier;
7. SHA-256 trên canonical bytes.

Cùng logical snapshot, cùng input và cùng serialization version phải sinh cùng hash.

Exact encoding là engineering choice; sau khi đã dùng cho retained/frozen artifacts thì phải version nếu muốn thay đổi, không được đổi âm thầm.

## 4. Artifact naming

Target layout:

```text
data/snapshots/{snapshot_id}/{snapshot_hash}.parquet
outputs/checkpoints/transe/{snapshot_id}/seed={seed}/{config_hash}.pt
outputs/alignment/{transition_id}/fit={anchor_hash}/{alignment_hash}.npz
outputs/null/{transition_id}/{bucket_policy_hash}.parquet
outputs/drift/{transition_id}/{drift_protocol_hash}.parquet
outputs/qa/{query_manifest_hash}.parquet
outputs/rankings/{arm}/{population}/{candidate_universe_hash}.parquet
outputs/analysis/{protocol_hash}/{analysis_run_id}/
reports/{release_tag}/
```

Generated heavy artifacts bị ignore mặc định. Git lưu code/config/manifest; artifact lớn chỉ được commit nếu có quyết định storage rõ ràng.

## 5. Experiment manifest

Mọi analysis-relevant run phải sinh manifest tương thích với:

```text
configs/schemas/experiment_manifest.schema.yaml
```

và bắt đầu từ:

```text
experiments/MANIFEST_TEMPLATE.yaml
```

Manifest phải đủ provenance cho:

- experiment/protocol identity;
- `git_commit` và `dirty_state`;
- data/snapshot/query/mapping/config hashes;
- `seed`;
- environment và hardware;
- checkpoint/artifact hashes;
- Dev/locked `access_state`;
- failure/amendment trail nếu rerun.

Manifest đã nhận diện một retained run là immutable. Rerun phải tạo run/manifest mới, không overwrite run cũ.

## 6. `data/locked_test/`

Locked-test payload bị ignore bởi Git có chủ đích. Git/CODEOWNERS không thể chứng minh một local file chưa từng được mở.

Trước W8 phải có runner/access-control procedure đáp ứng:

- payload không xuất hiện trong ordinary Dev workflow trước freeze;
- sau W7, locked payload được mount/read-only cho locked runner;
- runner ghi access state/timestamp và resolved config trước khi tạo metrics;
- rerun chỉ vì documented engineering failure;
- contaminated/old run được giữ và đánh dấu invalid thay vì xóa.

Xem `data/locked_test/README.md`.

## 7. Dev artifact và locked artifact

Dev outputs dùng để pilot, debug và freeze config. Locked outputs chỉ được tạo từ exact frozen state.

Không được copy một Dev output sang locked namespace rồi coi đó là locked result. Locked result phải được sinh bởi locked runner và có manifest/access trail tương ứng.
