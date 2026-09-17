# Runbook Ticket A

Runbook này chỉ bao phủ phần inventory/gate đã triển khai. Nó không cho phép
LLM inference, pilot/full-corpus work, network collection hoặc Neo4j
materialization.

## Môi trường

Chạy PowerShell từ repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Build backend đã được pin trong `pyproject.toml` và `requirements.lock.txt`.
Kích hoạt `.venv` nếu dùng `python` trực tiếp; nếu không, giữ executable của
virtual environment như các lệnh bên dưới.

## Lệnh Ticket A

```powershell
.\.venv\Scripts\python.exe -m kg_pipeline --help
.\.venv\Scripts\python.exe -m kg_pipeline init-run --run llm_rebuild_v2_audit_01 --mode inventory
.\.venv\Scripts\python.exe -m kg_pipeline inventory --run llm_rebuild_v2_audit_01 --verify-inputs
.\.venv\Scripts\python.exe -m kg_pipeline verify --run llm_rebuild_v2_audit_01 --gate A
.\.venv\Scripts\python.exe -m kg_pipeline status --run llm_rebuild_v2_audit_01
.\.venv\Scripts\python.exe -m pytest tests/kg_pipeline/test_input_contracts.py tests/kg_pipeline/test_inventory.py tests/kg_pipeline/test_gate_a.py
```

`verify` chỉ exit 0 khi Gate A là PASS. `BLOCKED`, `FAIL` và `NOT_RUN` được
thiết kế để trả nonzero. Retry có thể dùng lại immutable output tương đương về
semantic; nếu semantic input/output thay đổi tại một run path đã tồn tại thì đó
là conflict, cần dùng run ID mới thay vì overwrite artifact.

## Ranh giới an toàn

- Raw roots là read-only input. Không xóa, rewrite hoặc patch thủ công raw blob,
  input lock, Parquet table hoặc gate report.
- Stage 4.3 reconciliation là read-only. Không chạy lại
  `src/03b_run_tuoitre_historical_window.py` nếu chưa có quyền rõ ràng từ user.
- Proposed config bundle chưa frozen. Gate A có thể vẫn blocked dù phần triển
  khai/báo cáo Ticket A đã hoàn tất.
