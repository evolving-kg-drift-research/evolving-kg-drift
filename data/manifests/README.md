# Manifests

Thư mục này lưu **small, reviewable provenance records**, không lưu generated experiment payloads.

Các record hiện tại/dự kiến:

- `sources.lock.json` — authoritative source paths + SHA-256 cho W1.
- `w7_freeze.yaml` — tạo tại W7 từ `W7_FREEZE_TEMPLATE.yaml`; ghi frozen protocol và input hashes cần thiết để mở locked run.

Run-specific provenance nằm cùng experiment run manifest và phải tuân theo:

```text
configs/schemas/experiment_manifest.schema.yaml
```
