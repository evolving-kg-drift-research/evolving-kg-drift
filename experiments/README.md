# Experiments

Commit **experiment definitions**, không commit arbitrary generated run payloads.

Layout gợi ý khi bắt đầu triển khai:

```text
experiments/
├── vertical_slice/
├── kge_pilot/
├── alignment_null_pilot/
├── dev_ab/
└── locked/
```

Mỗi experiment directory có thể chứa:

- authoring/resolved config nhỏ;
- runner entry point;
- README ghi exact command và purpose.

Các thư mục generated như `runs/`, `cache/` và `artifacts/` bị ignore.

Mọi analysis-relevant run được giữ lại phải bắt đầu từ `MANIFEST_TEMPLATE.yaml` và tạo một immutable manifest mới. Không overwrite manifest/run cũ.
