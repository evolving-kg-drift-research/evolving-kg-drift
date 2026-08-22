# Gate và quy trình đóng băng

Research plan dùng fail-fast gates. File này ánh xạ các gate khoa học sang repository checks; nó không thay đổi deadline hoặc scientific criteria trong protocol.

| Milestone | Deadline | Điều kiện chính | Lệnh hiện tại |
|---|---:|---|---|
| W1 source/contracts | Cuối W1 | Verify authoritative source bytes, Day-1 contracts, tests scaffold | `python scripts/verify_w1.py` |
| W1 tag | Cuối W1 | Chỉ tag khi strict W1 verification pass và working tree clean | `python scripts/freeze_w1.py` |
| G1 temporal integrity | Cuối W2 | 4 temporal hard invariants phải chạy và pass, không `skip` | `python scripts/verify_g1.py` |
| G2 evidence/entity | Cuối W3 | Evidence/entity audit + QA feasibility hash | module-specific checks sẽ bổ sung |
| G3 alignment/null | Cuối W4 | KGE/alignment/null diagnostics trong operating range đã khóa từ pilot | module-specific checks sẽ bổ sung |
| G4 QA/power | Cuối W5 | QA/population/power viability | module-specific checks sẽ bổ sung |
| G5 support modules | Cuối W5 | Quyết định giữ/cắt path và optional auditor branches | module-specific checks sẽ bổ sung |
| G6 protocol lock | Cuối W7 | Không còn placeholder; W7 freeze manifest đầy đủ; dry-run; full tests | `python scripts/verify_w7.py` |
| W7 tag | Cuối W7 | Tạo immutable protocol freeze tag sau G6 | `python scripts/freeze_protocol.py` |
| Locked run | W8 | Exact frozen state, access log, không outcome tuning | locked runner phải implement trước W8 |

## 1. W1 — Source/contracts

Không tạo `v0.1-source-lock` khi bootstrap repository.

`freeze_w1.py` chỉ được chạy sau khi:

- authoritative source bytes có thật;
- `verify_w1.py` pass;
- test scaffold hợp lệ;
- working tree clean.

## 2. G1 — Temporal integrity

Base repository có skipped tests để scaffold. CI xanh lúc bootstrap **không tương đương G1**.

Trước khi G1 được coi là pass, các test sau phải được implement và pass:

- `test_no_future_evidence`
- `test_no_future_entity_mapping`
- `test_snapshot_reproducible`
- `test_canonical_parquet_neo4j_parity`

`verify_g1.py` fail nếu một trong bốn test còn `skip`.

## 3. G2–G5

Các gate này chưa cần một generic script ngay ở base. Khi module implementation xuất hiện, owner phải thêm machine-checkable checks cho phần có thể tự động hóa.

Không biến mọi pilot criterion thành một hard-coded constant trước khi có pilot evidence. Procedure được khóa trước; realized value được freeze đúng deadline.

## 4. W7 / G6 — Protocol freeze

Trước `protocol-v1-frozen`:

1. resolve mọi `TO_BE_FROZEN_*` theo đúng deadline;
2. tạo `data/manifests/w7_freeze.yaml` từ `data/manifests/W7_FREEZE_TEMPLATE.yaml`;
3. ghi frozen data/query/snapshot/candidate/pseudo hashes;
4. ghi WCB seed/draws và locked access state;
5. hoàn tất Dev dry-run bằng cùng runner/artifact schema dự kiến dùng W8;
6. chạy `python scripts/verify_w7.py`;
7. commit để working tree clean;
8. chạy `python scripts/freeze_protocol.py` và push tag.

## 5. Thay đổi sau W7

Frozen scientific/config path chỉ được sửa vì documented engineering/data/integrity failure; không được sửa vì một giá trị khác cho performance tốt hơn.

PR chạm frozen paths phải có `amendments/*.yaml` khớp với thay đổi và chứa:

- failure reason hợp lệ;
- reproduction evidence;
- regression test;
- new versioned outputs/protocol state;
- retention của previous/contaminated run.

`scripts/check_freeze.py` enforce phần policy có thể kiểm tra từ Git sau khi freeze tag tồn tại.

Review-count policy là team governance riêng.

## 6. W8 — Locked run

Locked runner phải:

- kiểm tra exact config/input hashes trước khi chạy;
- ghi resolved config + access log trước metrics;
- sinh raw ranking/panel artifacts trước statistical tables/figures;
- cấm tuning sau result visibility;
- rerun chỉ theo amendment khi engineering failure được chứng minh.
