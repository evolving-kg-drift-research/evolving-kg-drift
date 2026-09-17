# Tiến độ pipeline

Lần đối chiếu gần nhất: 2026-09-16 (Asia/Saigon)

## Điểm dừng hiện tại

Ticket A đã hoàn tất phần triển khai và báo cáo inventory trong run mới
`llm_rebuild_v2_audit_01`. Gate A đang **BLOCKED**, không phải PASS. Chưa chạy
ticket sau, LLM, pilot, full-corpus inference, network refetch hoặc ghi Neo4j.

## Stage 4.3 - PASS trong phạm vi đã chứng minh

Bằng chứng được đọc và đối chiếu độc lập từ
`data/stage_4_3_runs/stage4_3_final_20260906T144016Z/` sang
`runs/llm_rebuild_v2_audit_01/reports/stage_4_3_reconciliation.json`.

- Final manifest và validation report: PASS/PASS.
- Tất cả hash output trong final manifest đều khớp.
- `discovered_urls.parquet`: 4,692 observation và 3,344 unique URL.
- `archive_candidates.parquet`: 72 dòng.
- `discovery_log.jsonl`: 245,928 record hợp lệ, không rỗng; 0 record lỗi.
- Tuoi Tre historical blocks: 108.

Không chạy lại `src/03b_run_tuoitre_historical_window.py`. Trạng thái trong
`docs/data_pipeline_spec.md` chỉ được đối chiếu từ bằng chứng đã kiểm chứng này.
Điều này không chứng nhận Stage 4.4 hoặc scientific readiness của Ticket A.

## Ticket A - triển khai xong; scientific input readiness BLOCKED

Artifact của run: `runs/llm_rebuild_v2_audit_01/`.

Kết quả inventory thực tế:

- 5,168 raw path / 5,168 giá trị SHA-256 hiện tại khác nhau; 0 lỗi đọc và
  0 filename-hash mismatch.
- 5,167 raw path được nhận diện là HTML và 1 path là text/plain.
- 4,745 body variant, 5,168 source membership và 4,745 exact-body cluster;
  352 cluster có nhiều hơn một membership. Exact clustering giữ toàn bộ
  membership; không suy luận near-duplicate/copy/lineage.
- 20 recovery record nối bằng exact hash và 20 source-version row trỏ tới 18
  blob. Tất cả đều partial: 0 strict retrieval. Thiết kế này cố ý giữ nhiều
  retrieval riêng biệt thay vì gộp chúng.
- 5,150 blob không có direct acquisition evidence; 18 blob có partial evidence
  nhưng thiếu field acquisition bắt buộc. Hash blob hiện tại được ghi là
  computed-now evidence, không phải historical proof.
- Một raw item sinh body rỗng để review. Bốn JSON manifest rỗng có sẵn được ghi
  là evidence-scan review issue không chặn.
- Discovery observation, URL, retrieval record và raw blob là các đơn vị không
  so sánh trực tiếp; không ép số lượng của đơn vị này khớp đơn vị khác.

Bằng chứng gate: `runs/llm_rebuild_v2_audit_01/gates/gate_A.json`.

| Gate check | Kết quả |
| --- | --- |
| Stage 4.3 reconciliation, table/schema readability, raw hash/read audit, giữ retrieval ID, loại legacy decision input | PASS |
| Strict raw provenance | BLOCKED: 0 strict raw path; 5,150 unresolved |
| Source lock | BLOCKED: thiếu cả ba locked original đúng hash |
| Config baseline | BLOCKED: `PROPOSED_UNFROZEN` |
| Near-duplicate/copy/lineage policy | BLOCKED: chưa có semantic policy được duyệt |
| Tổng thể Gate A | **BLOCKED**; lệnh verify thoát đúng với code 2 |

## Kiểm chứng đã chạy

- `python -m ruff check --no-cache src/kg_pipeline tests/kg_pipeline`: PASS.
- `python -m pytest tests/kg_pipeline/test_input_contracts.py tests/kg_pipeline/test_inventory.py tests/kg_pipeline/test_gate_a.py -q`: **7 passed**.
- `git diff --check`: PASS; không báo lỗi whitespace.

## Cần có trước khi Gate A PASS theo khoa học

1. Cung cấp hoặc chính thức thay thế, với thẩm quyền khoa học, các locked
   original đang thiếu mà không sửa `data/manifests/sources.lock.json` để khớp
   một file khác.
2. Khôi phục hoặc quản trị có chủ đích raw acquisition provenance: exact blob
   hash, source/URL/final URL và thời điểm retrieval thật. Không dùng mtime hoặc
   page metadata làm evidence thay thế.
3. Duyệt baseline cho configuration/ontology/time field, bao gồm mâu thuẫn
   10-versus-11 relation và phân biệt `retrieved_at_real` với
   `ingested_at_real`.
4. Duyệt near-duplicate/copy/lineage policy có version nếu cần suy luận vượt ra
   ngoài exact body hash.

Stage tiếp theo cần chỉ đạo rõ từ user sau khi gate liên quan và các quyết định
khoa học thật sự được giải quyết.
