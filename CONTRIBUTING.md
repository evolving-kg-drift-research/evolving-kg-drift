# Hướng dẫn đóng góp

## 1. Làm việc theo contract đã đăng ký

Trước khi implement một module, đọc:

1. `docs/architecture.md`
2. section tương ứng trong `docs/modules.md`
3. `configs/protocol_v1.yaml`
4. tests/contracts hiện có của module

Không tự điền `TO_BE_FROZEN_*` theo sở thích cá nhân hoặc theo downstream performance.

Nếu docs và `configs/protocol_v1.yaml` mâu thuẫn, **protocol thắng**.

## 2. Ngôn ngữ tài liệu

- Nội dung giải thích trong `README.md`, `CONTRIBUTING.md` và `docs/*.md` viết bằng **Tiếng Việt**.
- Tên file, module, class, function, biến, config key, path và command giữ nguyên **English**.
- Thuật ngữ học thuật quan trọng nên ghi Tiếng Việt và English ở lần xuất hiện đầu tiên khi điều đó làm rõ nghĩa, ví dụ: *độ trôi biểu diễn (representation drift)*.
- Không dịch tên model, metric, framework hoặc identifier như `TransE`, `PyKEEN`, `Neo4j`, `SHA-256`, `RR`, `MRR`, `Hits@K`, `QLoRA`, `ICL`, `Git`, `CI`, `CODEOWNERS`.
- Không đổi terminology hoặc key trong `configs/protocol_v1.yaml` chỉ vì lý do dịch thuật.

Nguyên tắc hierarchy:

```text
configs/protocol_v1.yaml
        ↓
docs tiếng Việt giải thích
        ↓
code + docstring
```

## 3. Branches

Dùng branch ngắn hạn theo work package, ví dụ:

```text
data/<task>
drift/<task>
path-auditor/<task>
eval/<task>
chore/<task>
docs/<task>
```

Mỗi PR nên tập trung vào một thay đổi logic. Rebase/update từ `main` thường xuyên, tránh branch lớn tồn tại quá lâu.

## 4. Ownership và review

`CODEOWNERS` dùng để route review đến owner chính. Thay đổi ở interface tích hợp nên request thêm upstream/downstream owner liên quan.

Thay đổi `configs/protocol_v1.yaml` là thay đổi nhạy cảm cấp nhóm.

`CODEOWNERS` không thay thế amendment mechanism và không tự động có nghĩa mọi owner được liệt kê đều phải approve.

## 5. Trước khi mở PR

Chạy:

```bash
python -m ruff check .
python -m pytest -q
python scripts/verify_w1.py --ci
python scripts/verify_g1.py --ci
python scripts/verify_w7.py --ci
python scripts/check_freeze.py
```

Ở giai đoạn scaffold, CI có thể pass trong khi một số future-gate tests vẫn `skip` có chủ đích. Gate verification trở nên strict khi đến milestone tương ứng hoặc khi chạy không có `--ci`.

## 6. Experiments

Experiment definitions nằm trong `experiments/` và **phải được commit**. Generated run caches hoặc local artifacts không được đưa vào Git.

Bắt đầu từ:

```text
experiments/MANIFEST_TEMPLATE.yaml
```

Mọi retained analysis run phải có immutable manifest truy ngược được về code/config/input/output hashes.

## 7. Dependencies

Không sửa `requirements.lock.txt` tùy tiện. Dependency change nên nằm trong PR riêng và lock phải được regenerate có chủ đích.

Không thêm library mới nếu standard library hoặc stack hiện tại đã đủ.

## 8. Generated data và binary artifacts

Không commit trực tiếp các file generated thông thường như:

```text
*.parquet
*.pt
*.npz
checkpoints
```

Commit manifest/hash và storage reference. Chỉ xem xét Git LFS sau pilot khi kích thước thực tế cho thấy cần thiết.

## 9. Correction sau freeze

Sau `protocol-v1-frozen`, không sửa frozen paths vì performance preference.

Nếu có engineering/data/integrity failure hợp lệ:

1. tái hiện failure;
2. thêm hoặc cập nhật regression test;
3. tạo amendment từ `amendments/TEMPLATE.yaml`;
4. thực hiện correction nhỏ nhất cần thiết;
5. sinh protocol/run/output version mới;
6. giữ previous/contaminated run để audit.
