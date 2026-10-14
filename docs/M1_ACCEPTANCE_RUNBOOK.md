# Runbook triển khai và kiểm tra M1 acceptance rebuild

Ngày: 14/10/2026. [Kế hoạch](M1_REMEDIATION_PLAN.md).

## 1. Phạm vi thực thi hiện tại

Nhánh `codex/m1-acceptance-rebuild` đã có engineering foundations và package
contract 1.1 để review. Schema production 1.0, source lock và protocol giữ
nguyên. Những điều kiện thiếu tiếp tục BLOCKED, không có production certificate.

Các lệnh dưới chạy từ root repo trong PowerShell. `.venv-m1` là môi trường
Python 3.11 riêng; dependency lock được giải lại từ `requirements.in`.

## 2. Kiểm tra readiness và contract

```powershell
$env:PYTHONPATH = 'src'
.\.venv-m1\Scripts\python.exe -m kg_pipeline rebuild-readiness
.\.venv-m1\Scripts\python.exe -m kg_pipeline audit-schema
```

Exit 2 khi còn BLOCKED là kết quả mong đợi của guard. `rebuild-readiness` chỉ
đọc: source identity, runtime schema, candidate package hashes và prerequisites
của 16 stages. Nó không tạo run hay nâng trạng thái gate.

Candidate nằm trong `docs/audit/m1_acceptance_design_v2/`. Manifest mới bind
matrix revision 2, 17 public tables và 8 auxiliary tables. Review cả field
matrix lẫn candidate schema; `source_event` của các fields mới còn cần xác định
cụ thể trước approval. Không copy candidate đè lên `config/schema.yaml`.

## 3. Kiểm thử

```powershell
.\.venv-m1\Scripts\python.exe -m pip check
.\.venv-m1\Scripts\python.exe -m ruff check . --no-cache
.\.venv-m1\Scripts\python.exe -m pytest -q --basetemp=outputs/m1_acceptance_tests/fresh_tmp
```

Dùng namespace tạm mới; pytest có thể dọn basetemp của nó, nên không trỏ vào
data, runs, recovery archives hoặc thư mục có artifacts cần bảo toàn.
Fixtures/API transport doubles không chứng nhận scientific gate hay Neo4j thật.
CI có matrix Python 3.10/3.11; local Python 3.10 chưa được thực thi trong lượt này.

## 4. Gemini registration và ngân sách

`gemini_capture.capture_or_replay` chỉ hoạt động trong frozen run, Gate A PASS,
article inventory đúng hash và approval decision đúng dependencies. Nó yêu cầu
config chứa model/API/phase/payload policy, relations, prompt template,
max_input_chars, max_output_tokens, temperature, budget_usd và
attempt_cost_ceiling_usd. Ngân sách là decimal strings, không có default.

Decision ledger cần action `approve_hosted_extraction` và exact bindings:

```json
{
  "config_sha256": "<hash của exact config>",
  "inventory_sha256": "<hash của exact approved inventory>",
  "phase": "pilot",
  "scope": "candidate_extraction_only"
}
```

Đây là mô tả interface, không phải approval đã tồn tại. Chỉ ghi quyết định thật
sau khi người có thẩm quyền review exact payload/config/chi phí. API key lấy
từ `GEMINI_API_KEY`; không đưa key vào tài liệu hoặc artifacts.

Capture là tuần tự với pre-attempt reservations. Mọi started attempt giữ nguyên
approved upper-bound cost, gồm timeout/429/5xx. Cách này có thể dừng sớm hơn
chi phí thực nhưng không tạo giả billing amount. Capture lỗi/interrupted cần
review; không tự bỏ reservations rồi gọi lại. Replay thiếu/hỏng cache sẽ dừng
và tuyệt đối không gọi mạng.

Output gồm requests, attempt results, provider modelVersion/usage, validated
response và immutable cache envelope. Candidate JSON không chứng nhận relation
grounding, temporal basis, canonical mapping hoặc acceptance.

API transport dùng REST `generateContent`; không bật hosted tools/search.
References: [Google API](https://ai.google.dev/api/generate-content),
[structured output](https://ai.google.dev/gemini-api/docs/structured-output).

## 5. Gold và thresholds

Gold được annotate từ bài nguồn và facts thuộc ontology, gồm facts extractor
bỏ sót. Mỗi bài có hai annotation refs độc lập và adjudication ref đúng hashes,
IDs người annotate, guideline và sampling-plan bindings.

Evaluator `acceptance_quality` trả metrics theo numerator/denominator, FP/FN,
coverage và limitations. Metrics gồm entity accuracy, relation precision/recall,
temporal-field agreement, span, decision và copy-origin agreement. Component
report có scope `independent_quality_metrics_only`, không phải G2 certificate.

Threshold annex cần đủ metric criteria, minimum denominator, selection basis
và strata minima; missing/zero coverage/NaN phải BLOCKED. Main gold tách khỏi
development/pilot. Không dùng kết quả T01 legacy làm gold hoặc chọn thresholds.

Artifact evaluator còn kiểm exact procedure/threshold approvals, raw annotations,
adjudication binding và evaluator code hash. Final G1/G2 vẫn fail-closed tới khi
physical rebuild, QA feasibility và migrated producer lineage được hoàn thiện.

## 6. Runner một stage

```powershell
.\.venv-m1\Scripts\python.exe -m kg_pipeline run-stage --run RUN_ID --stage 4.9 --phase pilot --inputs runs/RUN_ID/inputs/stage_4_9.json --inputs-sha256 EXACT_SHA256
```

Không có lệnh `--stage all`. Stage 4.3 acquisition bị khóa. Input manifest phải
bind run/stage/phase, exact artifact refs, execution approval và previous stage
report có outputs đã xác minh. Stage 4.14 nhận pilot 4.13 PASS rồi mới vào main.

Hiện registry/preflight đủ tất cả stages; production producers chưa được
activate/migrate. Stage 4.13 có component-quality dispatch; các stage khác báo
`PRODUCTION_PRODUCER_NOT_ACTIVATED` khi đủ prerequisites nhưng producer chưa
sẵn sàng. Không coi registry là pipeline đã thực thi hay có đủ mọi backend.

## 7. Recovery audit và bàn giao

`scripts/audit_m1_reused_raw.py` chỉ phục hồi/hash đúng raw blobs mà v3 membership
tham chiếu, từ archive đã khóa hash vào output namespace mới. Audit 14/10 đạt
5.168/5.168 hashes, 1.662.329.089 bytes. Đây là HASH_RECOVERY_AUDIT_ONLY,
không phải Stage 4.4/G1 PASS. Body/receipt checks cũ giữ phạm vi đã báo.

Mỗi production stage phải có báo cáo input/output hashes, schema/invariant/FK/
determinism/resume/gate checks và STOP. Handoff theo
[M1 requirements](M1_HANDOFF_REQUIREMENTS.md); gói dữ liệu lớn được bảo quản
ngoài Git cùng inventory/checksums, không suy từ code commit/push.
