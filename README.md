# evolving-kg-drift

Codebase nghiên cứu cho đề tài:

**Định lượng độ trôi biểu diễn có hiệu chỉnh nhiễu cho suy luận đa bước trên đồ thị tri thức tiến hóa**

## Đường găng nghiên cứu

```text
Temporal evidence
→ versioned facts
→ deterministic snapshots
→ TransE multi-seed
→ centered Procrustes
→ same-snapshot empirical null
→ drift
→ recurring QA
→ H1/H2
→ pseudo-drift falsification
```

Đường găng cần được ưu tiên theo thứ tự:

```text
temporal integrity → measurement validity → locked experiment
```

`paths` và `auditor` là mô-đun SUPPORT. QLoRA, nếu được mở, chỉ thuộc STRETCH và không được chặn tiến độ phần CORE.

## Tài liệu trong repository

Trước khi nhận một module, đọc theo thứ tự:

- `docs/architecture.md` — kiến trúc code/data-flow và ranh giới ownership.
- `docs/modules.md` — mục đích, đầu vào, đầu ra, bất biến và hành vi bị cấm của từng module.
- `docs/data_and_artifacts.md` — contract dữ liệu canonical, hashing và experiment manifest.
- `docs/gates_and_freeze.md` — cách repository kiểm tra W1, G1 và W7/G6.
- `docs/team_handoff.md` — gói công việc đầu tiên cho M1–M4 và tiêu chí tích hợp.
- `CONTRIBUTING.md` — quy tắc branch, PR, experiment, dependency và amendment.

Các tài liệu trên chỉ **giải thích cách triển khai**. Chúng không thay thế `configs/protocol_v1.yaml`.

## Trạng thái scaffold ban đầu

Repository này bắt đầu ở trạng thái **Week-1 scaffold**, không phải bằng chứng rằng các điều kiện toàn vẹn khoa học đã pass.

Ở thời điểm bootstrap, phần lớn hard-invariant tests được `skip` có chủ đích. CI xanh ở giai đoạn này chỉ có nghĩa cấu trúc repo và config contract nhất quán; **không có nghĩa G1 temporal integrity đã đạt**.

Đến cuối W2/G1, tối thiểu các test sau phải được implement và không còn `skip`:

- `test_no_future_evidence`
- `test_no_future_entity_mapping`
- `test_snapshot_reproducible`
- `test_canonical_parquet_neo4j_parity`

Trước khi coi G1 là pass, chạy:

```bash
python scripts/verify_g1.py
```

`verify_g1.py` sẽ fail nếu một trong bốn test trên vẫn bị `skip`.

## Bắt đầu nhanh

### Windows / PowerShell

Sửa các biến ở đầu `bootstrap_repo.ps1`:

- `ORG_NAME`
- `REPO_NAME`
- `VISIBILITY`
- `M1_OWNER`
- `M2_OWNER`
- `M3_OWNER`
- `M4_OWNER`

Sau đó chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\bootstrap_repo.ps1
```

Repository GitHub được tạo theo dạng:

```text
ORG_NAME/evolving-kg-drift
```

## Authoritative sources và W1 source lock

Repository không coi việc chép một chuỗi hash vào config là đủ để xác minh source.

Trước khi tạo `v0.1-source-lock`:

1. Đặt đúng bytes của authoritative source artifacts vào `sources/`.
2. Kiểm tra `data/manifests/sources.lock.json` chứa đúng path và SHA-256.
3. Chạy:

```bash
python scripts/verify_w1.py
```

`verify_w1.py` tính hash trực tiếp từ file thật và đối chiếu với cả manifest lẫn `configs/protocol_v1.yaml`.

Chỉ sau khi pass mới tạo tag:

```bash
python scripts/freeze_w1.py
git push origin v0.1-source-lock
```

`sources.lock.json` không dùng một trường `status` có thể sửa tay; trạng thái source lock được biểu diễn bằng Git tag.

## W7 protocol freeze và amendment

W7/G6 sử dụng hai lệnh chính:

```text
scripts/verify_w7.py
scripts/freeze_protocol.py
```

Chỉ tạo `data/manifests/w7_freeze.yaml` từ template khi trạng thái W7 đã hoàn chỉnh. `freeze_protocol.py` sẽ không tạo tag `protocol-v1-frozen` nếu strict W7 verification chưa pass hoặc working tree chưa clean.

Sau khi tag `protocol-v1-frozen` tồn tại, `scripts/check_freeze.py` kiểm soát các thay đổi tracked dưới:

```text
configs/
data/manifests/
```

Payload của locked test không được commit và không thể được Git chứng minh là "chưa từng mở". W8 phải dùng runner/read-only/access-log riêng; xem `data/locked_test/README.md`.

Thay đổi nhạy cảm sau freeze phải có amendment hợp lệ, tối thiểu gồm:

- lý do failure/error được phép, không phải `performance_preference`;
- repo paths bị ảnh hưởng;
- test tái hiện failure;
- regression/new tests;
- protocol/output version mới;
- cam kết giữ lại previous/contaminated run để audit.

Số lượng GitHub approvals là quy tắc quản trị của nhóm, không phải requirement khoa học tự thân.

## Experiment definitions và manifests

Experiment definitions trong `experiments/` được commit. Các thư mục generated như `runs/`, `cache/` và `artifacts/` bị ignore.

Mọi run được giữ lại cho phân tích phải bắt đầu từ `experiments/MANIFEST_TEMPLATE.yaml` và tuân theo contract trong:

```text
configs/schemas/experiment_manifest.schema.yaml
```

Mục tiêu là mọi kết quả có thể truy ngược về code, config, seed, immutable inputs và artifact hashes.

## Config consistency

`tests/test_config_consistency.py` kiểm tra các contract field bị lặp giữa:

```text
configs/protocol_v1.yaml
configs/kge.yaml
configs/statistics.yaml
configs/data.yaml
```

## Git LFS

Git LFS **không bật mặc định**. Checkpoint, Parquet, NPZ và generated artifacts thông thường không được commit trực tiếp vào Git. Sau pilot mới quyết định có cần LFS hay external storage dựa trên kích thước thực tế.

## Bước triển khai tiếp theo

Không dùng `src/temporal/snapshot.py` cho dữ liệu thí nghiệm thật khi nó còn `NotImplementedError`.

Ưu tiên đầu tiên là implement đúng temporal semantics đã đăng ký, sau đó dựng vertical slice nhỏ:

```text
10–20 articles
→ FactVersion
→ 3 tiny snapshots
→ TransE smoke
→ alignment/null
→ 5–10 recurring QA rows
→ A/B dry-run
```
