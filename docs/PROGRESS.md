# Tiến độ pipeline

## M1 C3 — 2026-09-28: machine contract và các clock

Đã thêm audit đọc `config/schema.yaml`, chặn đường production khi PyArrow hoặc
dataclass không tương thích; run lưu version/hash schema. Đã bỏ fallback 2020,
việc dùng retrieval thay ingestion và suy diễn UTC cho thời gian thiếu timezone.
Adjudication dừng khi chưa có artifact thời gian Stage 4.10 được duyệt.

Audit thực tế: **BLOCKED, 9/17 bảng lệch contract**. Code/fixture tests: toàn bộ
194 passed, 10 skipped; bộ C3 cuối cùng 9 passed; Ruff đạt. Đây không phải
scientific PASS. Cần quyết định schema migration, nguồn clock và đánh giá
reprocess trước khi triển khai phần còn lại của C3. Xem [báo cáo C3](audit/m1_c3_contract_time.md).

Đối chiếu đọc lại tại `922e319` ngày 2026-09-28 xác nhận audit còn BLOCKED ở 9/17
bảng (schema version `1.0.0`, SHA-256
`48ad42f86088ae0e9ca8b8cbb158017bf8ec14e0d450fdeff523bf59e6902840`). Hồ sơ
quyết định C3 đã được lập để xin duyệt tên/kiểu contract, căn cứ clock và phạm
vi reprocess; đây chưa phải quyết định được duyệt và chưa được ghi vào decision
log. Xem [hồ sơ quyết định C3](audit/m1_c3_decision_package.md). C3 tiếp tục
BLOCKED; không mở production adjudication hoặc snapshot.


## M1 C4–C9 — 2026-09-28: code remediation, production vẫn BLOCKED

Đã triển khai guard và fixture coverage cho mapping as-of, text/extraction
provenance, cache replay bất biến, SourceClaim/conflict handling, parent
FactVersion lineage, snapshot dependency hashes, M2 handoff, exact-set parity,
và scientific locked mode. **C4–C9 chỉ hoàn tất một phần ở mức code**; từng
checkpoint chưa đạt production certification. Ma trận M1-001–M1-020 đã được
cập nhật riêng [tại đây](audit/m1_c4_c9_finding_matrix.md), với bốn trạng thái
IMPLEMENTED, TESTED, EXECUTED và VERIFIED.

Regression cuối: **230 passed, 10 skipped**; Ruff và `git diff --check` đạt.
Đây là kiểm tra code/fixture, không phải scientific PASS. Schema machine audit
vẫn **BLOCKED: 9/17 bảng**; Gate A, G1/G2, production stages và M2 vẫn BLOCKED.
Không chạy production runner, không materialize Neo4j, không rerun hoặc sửa
Stage 4.3/raw/source-lock, không ghi decision log và chưa commit.

Sau lần regression trên, đã harden thêm C9: cấu hình local adapter nằm tại
`config/llm_adapter.yaml` và được đưa vào run fingerprint; locked extraction
từ chối thiếu adapter local/pins/decoding fields, ontology thiếu hoặc adapter
mock. Locked init đối chiếu direct dependencies với exact pins trong lock và
hiện chặn `openai>=1.0.0` vì không có exact pin tương ứng trong lock.
Extraction runner không tự chọn ontology mẫu hay mock; helper cũng cần adapter,
ontology và cache directory tường minh. Kiểm thử tập trung mới nhất:
**25 passed, 4 deselected**; Ruff và `git diff --check` đạt. Chưa chạy lại toàn
regression sau patch C9: pytest bị môi trường Windows từ chối truy cập thư mục
temporary (`WinError 5`), nên số 230/10 ở trên chỉ thuộc revision ngay trước
patch này. Xem [báo cáo C9](audit/m1_c9_locked_ci.md).

- C4: [mapping theo cutoff](audit/m1_c4_mapping.md) — còn thiếu stable mention ID và identity policy.
- C5: [text và extraction provenance](audit/m1_c5_text_extraction.md) — normalization mới chưa được phê duyệt.
- C6: [claims và revisions](audit/m1_c6_claims_revisions.md) — conflict/SourceClaim persistence chưa có contract.
- C7: [snapshot và bàn giao M2](audit/m1_c7_snapshots_m2.md) — acceptance clock, boundaries và G1/G2 còn thiếu.
- C8: [Neo4j parity](audit/m1_c8_neo4j_parity.md) — chưa có materialization/read-back thật.
- C9: [locked mode và CI](audit/m1_c9_locked_ci.md) — CI chưa thể cấp chứng nhận artifact-backed.


## M1 C2 — 2026-09-28: chuỗi artifact và bàn giao M2

Đã triển khai ArtifactRef và xác minh đệ quy run/stage lineage cho canonical
Parquet. Các runner bind input/output và Gate A; M2 yêu cầu snapshot manifest,
producer hoàn tất, Gate A hợp lệ và đúng snapshot được yêu cầu. Kiểm thử toàn bộ:
187 passed, 10 skipped; bổ sung ca vòng stage: bộ test chuỗi 11 passed. Đây là
kết quả code/fixture, không phải production hay G1/G2 PASS. Gate A vẫn BLOCKED.
Chi tiết và phần dependency chưa khóa: [báo cáo C2](audit/m1_c2_artifact_chain.md).


## M1 C1 — 2026-09-28: chặn scientific PASS sai

Đã triển khai và kiểm thử guard G1/G2: yêu cầu run rõ ràng, bỏ synthetic fallback,
chọn run theo mtime và miễn kiểm chứng G1 bằng tag. Kiểm tra cấu trúc/fixture được
tách khỏi chứng nhận khoa học. Chẩn đoán quality không PASS khi không có bản ghi
được đánh giá hoặc thiếu coverage của gold.

Regression: 174 passed, 10 skipped; bộ guard cuối cùng: 16 passed; Ruff và diff
check đạt. Đây chỉ là bằng chứng kỹ thuật. G1/G2 vẫn BLOCKED do chưa có evaluator
khoa học đầy đủ; Gate A và production không được mở. C2–C9 chưa hoàn thành.
Chi tiết: [báo cáo C1](audit/m1_c1_gate_guards.md).

## Checkpoint khắc phục 0 — 2026-09-20

Nhánh sửa: `fix/data-pipeline-compliance`, từ `origin/feature/data_try` tại `4c24da2`.
Đã lập ma trận 24 bước (`data_pipeline_compliance.md`) và ADR 0007 theo lựa chọn
của người dùng: giữ ba original với hash baseline, không placeholder hoặc đổi hash.
Source lock/protocol và artifact lịch sử không thay đổi. Chưa sửa runtime Ticket A.

Trạng thái checkpoint: **VALIDATION INCOMPLETE**, không phải PASS. Các lệnh kiểm
JSONL, historical-prefix và `git diff --check` chưa chạy được do bộ kiểm tra quyền
công cụ tạm thời không khả dụng. Tìm file ở checkout hiện tại chỉ thấy
`sources/README.md` trong `sources/` và `.gitkeep` trong `data/raw/`; chưa có bằng
chứng local để kiểm lại dữ liệu production. Xem `checkpoint_0_report.md`.

Các kết quả PASS/test/count bên dưới là báo cáo lịch sử ngày 2026-09-16, không
phải kết quả chạy lại trong checkpoint này. Không rerun acquisition hoặc tự mở
stage downstream để khắc phục thiếu dữ liệu.

## Checkpoint R1 — Baseline and Execution Guards — 2026-09-20

Các guard về baseline và fingerprint đã được triển khai đầy đủ cho R1.

- Source lock kiểm tra đúng ba role gốc, không cho qua bằng placeholder.
- Fingerprint bao gồm cấu trúc, code, file nguồn, ontology, protocol và corpus scope.
- Trạng thái cấu hình được kiểm tra sự đồng thuận (`APPROVED`) ở config_baseline, được lưu vào `config_approval` trong manifest thay vì cứng ngắc là FROZEN. Cập nhật này ngăn run chạy tiếp nếu có thay đổi ngoài lề.
- Các bài kiểm tra validation (hợp lệ schema của cấu hình, resumption rollback khi approval thay đổi) đã được bổ sung.
- Không giả mạo bất kỳ nguồn hoặc quyết định phê duyệt nào. Do thiếu tài liệu và gói data production, pipeline hiện tại vẫn đang **BLOCKED** ở input readiness.
- **Retest hoàn tất**: Toàn bộ hệ thống (gồm validate config_approval, shell commands) đã vượt qua regression tests. R1 đã hoàn thành phần code, Gate A từ chối chính xác khi config bị unfrozen.

## Checkpoint R2 — Acquisition Trust and Identity — 2026-09-20

Tiếp nối R1, hệ thống đã triển khai các cấu trúc định danh và trust:
- Bổ sung định nghĩa PK/FK ở `contracts.py` và check bắt buộc trong Gate A (`A-011`). 
- Chỉnh sửa `_recovery_row` để đánh giá strict timestamp tại thời điểm scan. Bằng chứng sai định dạng ngày tháng hay thiếu timezone giờ sẽ hạ xuống mức không strict (giữ lại làm ledger) thay vì làm nổ cả quá trình inventory.
- Viết test coverage (`test_inventory.py`) cho nhiều luồng (dup event, multiple publishers cho cùng 1 byte, strict vs partial timestamps).
- Việc test đã hoàn tất thành công. Xem chi tiết tại `checkpoint_r2_progress.md`.

## Checkpoint R3 — Storage and Reproducibility — 2026-09-20

Hệ thống lưu trữ và toàn vẹn dữ liệu được cải thiện ở R3:
- Cài đặt `exclusive_artifact_lock` dùng `os.mkdir` (atomic OS-level) để đảm bảo đồng bộ khóa đa tiến trình trên cả Windows và Linux. Khóa bao phủ trọn vẹn quy trình check-verify-publish.
- Xử lý Crash recovery: Nếu một table parquet và sidecar bị can thiệp nhưng nội dung khóa học (`semantic_sha256`) lệch với `input_lock` đang chạy, `ArtifactConflict` sẽ ném ra, chặn không cho tái sử dụng (hoặc ghi đè). Đã có test coverage `test_tampered_table_and_manifest_rejected_during_write`.
- Đã loại bỏ các `run_id` bị lọt vào `semantic_sha256` bằng cách chỉ lưu đường dẫn tương đối (relative to run_dir). Đảm bảo tính cross-run reproducibility độc lập.
- Chi tiết xem tại `checkpoint_r3_progress.md`.

## Checkpoint R4 — Gates and Integration — 2026-09-20

Việc định danh và đánh giá Gate A được củng cố ở R4:
- `latest_gate_a_report` đã chuyển sang sắp xếp báo cáo dựa trên metadata thực `evaluated_at_real` chứa trong file thay vì dùng UUID lexicographical sort.
- Ngăn chặn stale PASS: `evaluate_gate_a` gọi `load_run_manifest` và tự động fail nếu cấu hình (config fingerprints) bị trôi lệch sau khi init run. Đã thêm test `test_input_mutation_invalidates_gate` để chứng minh báo cáo PASS giả bị bác bỏ nếu input thực tế không khớp.
- Khôi phục `.gitignore` strict cho thư mục `data/locked_test/*`, bảo vệ tính vô hình của tệp held-out. Thêm bài test `test_locked_test_payload_ignored` dùng `git check-ignore` xác thực điều này.
- `cli.py` đã đảm bảo trả mã exit hợp lệ (`0` khi `PASS`, `2` khi bị block/fail hoặc crash).
- Xem chi tiết tại `checkpoint_r4_progress.md`. 
Lưu ý: Môi trường hiện tại là Python 3.12, cần xác thực lại trên CI với Python 3.11.

## Báo cáo lịch sử — giữ nguyên

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
- `python -m pytest -q`: **63 passed, 14 skipped**. (Python 3.12).
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
