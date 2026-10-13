# Phụ lục review an toàn nhánh Thu Hương — 2026-10-03

Ref đã đọc tĩnh: `origin/fix/data-pipeline-compliance-cont` tại
`e19fe25d2325a53ebf49ada27cff4692aa1c6638`. Không chạy script trên nhánh đó.
Phụ lục này bổ sung findings sau báo cáo package review; nó không sửa hoặc
thay đổi nội dung ZIP, source-lock, protocol hay lịch sử acquisition.

## M1-BRANCH-001 — CRITICAL: công cụ tự tạo source lock và hash hiện không khớp

- **Affected files:** `fix_source_lock.py:21–31`,
  `data/manifests/sources.lock.json`, hai execution-plan files trong `sources/`.
- **Expected/invariant:** W1 xác minh đúng bytes của locked originals; missing
  originals phải BLOCKED, không tạo placeholder hay đổi lock theo file đang có.
- **Actual/evidence:** script tạo nội dung placeholder nếu file thiếu, tính
  hash từ file cục bộ và ghi đè `sources.lock.json`. Đối chiếu bytes trong Git
  tại tip: proposal khớp lock; execution plan và patch không khớp. Lock lần lượt
  ghi `667aa4601afdb888dd079670336a45611531fa34d8d8b283a1773d06d4ff7949` và
  `509046466a6f81b9dc2119ab8fdd56d50fbb1019a0e83e5c46000a126bfcd3fe`, trong
  khi bytes tại tip cho ra `12e492387dc562e623fba098ae3956c65411f4420fdb3c368848b72521f24bc5`
  và `faae34f40f6380fe6222374f682335bedbe69ba5779b9d00b6222875080e1611`.
- **Root cause:** hành vi ghi placeholder/hash-lock được xác nhận trong code;
  hai checksum không khớp được xác nhận trên Git blobs. Chưa có bằng chứng
  script từng được chạy hoặc nội dung nào được phê duyệt.
- **Read-only repro:** `git show e19fe25:fix_source_lock.py`; tính SHA-256 cho
  ba blobs trong `sources.lock.json` và đối chiếu. Không chạy helper.
- **Minimal fix:** không tích hợp helper; phục hồi/nhận đúng originals và
  approval trail rồi xử lý W1 theo gate hiện hành. Không “sửa” lock để khớp
  file thiếu căn cứ.
- **Regression:** W1 exact bytes/role/hash; thiếu file, placeholder và hash
  mismatch phải nonzero/BLOCKED; decision log không tự sinh approval.
- **Blockers:** originals và approval chưa được chứng minh.

## M1-BRANCH-002 — CRITICAL: thêm đường chạy lại Stage 4.3 đã khóa

- **Affected file:** `src/03b_run_tuoitre_historical_window.py:180–182,304,362–414`.
- **Expected/invariant:** Stage 4.3 108 historical blocks chỉ được đối chiếu
  read-only; không rerun crawler hoặc unconstrained historical acquisition.
- **Actual/evidence:** script tạo 108 sitemap tháng 03/2025–08/2026; mặc định
  không bật `--dry-run` và chạy crawler từng sitemap với `--limit 0`. Dry-run
  chỉ là opt-in. Nó ghi thêm run log và gọi `src/03_discover_historical_tuoitre.py`.
- **Root cause:** hành vi fetch được xác nhận bằng source; chưa gọi script.
- **Read-only repro:** `git show e19fe25:src/03b_run_tuoitre_historical_window.py`;
  lần theo `main → run_one_sitemap → subprocess.run`. Không chạy kể cả dry-run.
- **Minimal fix:** không tích hợp đường crawler. Giữ Stage 4.3 bằng read-only
  reconciliation artifacts đã có; không tạo provenance hồi tố.
- **Regression:** static policy check phải từ chối production acquisition
  entrypoint/108-block rerun trong remediation branch.
- **Blockers:** không được rerun; thiếu chính artifacts/provenance không cho
  phép dựng lại bằng refetch.

## M1-BRANCH-003 — HIGH: một script gộp inventory, Gate A và tests

- **Affected file:** `run_all.py:25–35`.
- **Expected/invariant:** fail-closed, một stage mỗi lần; Stage report và yêu
  cầu tiếp tục trước stage/gate kế tiếp.
- **Actual/evidence:** khi file được thực thi hoặc import, nó lần lượt
  init-run, inventory `--verify-inputs`, gọi Gate A rồi pytest trong một tiến
  trình. Mỗi return code bị bỏ qua nên bước sau vẫn được gọi khi bước trước lỗi;
  không có `if __name__ == "__main__"` guard.
- **Root cause:** lời gọi tuần tự và return codes không được kiểm tra xác nhận
  trong source; script chưa được chạy.
- **Read-only repro:** `git show e19fe25:run_all.py`, xem lines 25–35.
- **Minimal fix:** không port orchestrator này. CLI phải nhận đúng một stage;
  mỗi lệnh dừng với code khác 0 khi gate trước đó BLOCKED/FAIL.
- **Regression:** static/CLI check chứng minh Gate A/inventory/tests không
  tự chạy tiếp qua một wrapper nhiều-stage.
- **Blockers:** Gate A còn BLOCKED; không có stage authorization liền mạch.

## M1-BRANCH-004 — HIGH: trạng thái tài liệu báo PASS vượt quá bằng chứng

- **Affected files:** `docs/PROGRESS.md:3–6,175–180` và các producer/report
  Stage 4.18 trên nhánh Thu Hương.
- **Expected:** mutable progress phải phản ánh run/artifact thực; Stage 4.18
  yêu cầu Neo4j materialization và database read-back set equality; Gate A
  phải dựa trên input lock thật.
- **Actual/evidence:** PROGRESS tuyên bố Gate A và Stage 4.18 PASS. Package
  chứa Parquet/CSV exports và report claims, nhưng không có database read-back;
  code Stage 4.18 dựng list cạnh từ cùng Parquet rows vừa ghi CSV. Hai source
  lock hashes cũng không khớp hai source blobs. File có 11 control characters
  ngoài tab/newline; finding M1-PKG-010 ghi riêng chuỗi credential-like mà
  không tiết lộ giá trị.
- **Root cause:** report chứa claims và file bytes bất thường được xác nhận;
  các claims chưa được support bởi artifact read-back/gate evidence trong ZIP.
- **Read-only repro:** `git show e19fe25:docs/PROGRESS.md` (scanner chỉ xuất
  line/count, không xuất credential); đối chiếu code Stage 4.18 và package
  hashes trong `m1_thu_huong_package_review_20261003.json`.
- **Minimal fix:** không kế thừa PASS. Viết trạng thái mới như BLOCKED với
  links tới evidence; xác minh/thu hồi credential với owner nếu chuỗi đó là
  secret thật.
- **Regression:** checker đối chiếu mỗi Stage PASS với Stage Report, hashes,
  Gate certificate và DB read-back; secret scan/redaction và UTF-8 control
  character check.
- **Blockers:** thiếu certificate/run lineage, DB read-back và secret ownership
  confirmation.

## M1-BRANCH-005 — HIGH: helper sao chép artifact từ backup, có thể ghi đè run

- **Affected file:** `copy_stage_4_4.py:4–18`.
- **Expected/invariant:** raw/stage artifacts append-only; provenance phải nối
  tới đúng nguồn đã khóa; không tái dùng output legacy chỉ vì nó đang nằm ở
  một thư mục backup.
- **Actual/evidence:** script hard-code một đường dẫn backup trên ổ D:, copy
  mọi item vào `data/stage_4_4_runs`, dùng `copytree(..., dirs_exist_ok=True)`
  và `copy2`. Nó không xác minh run identity, content hashes, manifests hay
  lineage và có thể ghi đè file đích trùng tên.
- **Root cause:** hành vi overwrite-capable xác nhận trong source; chưa chạy
  và chưa kiểm tra đường dẫn backup có tồn tại.
- **Read-only repro:** `git show e19fe25:copy_stage_4_4.py`, đọc source/đích và
  flags `dirs_exist_ok=True`/`copy2`. Không thực thi.
- **Minimal fix:** không tích hợp helper. Khôi phục qua verified immutable
  artifact chain; conflict phải dừng, artifact mới dùng run path mới.
- **Regression:** destination trùng tên/hash khác phải báo conflict và giữ
  nguyên destination; provenance/run identity bắt buộc.
- **Blockers:** origin backup chưa được chứng minh là canonical/authorized.

## M1-BRANCH-006 — HIGH: Stage 4.14 mở đường gọi hosted model

- **Affected files:** `src/04_run_production_pipeline.py` và
  `src/kg_pipeline/llm_adapter.py` trên nhánh Thu Hương.
- **Expected/invariant:** không gửi research data qua hosted API; locked mode
  chỉ dùng local adapter đã pin/version/fingerprint và replay cache.
- **Actual/evidence:** CLI Stage 4.14 cung cấp `--llm-mode hosted` và truyền
  thẳng mode đó vào `get_llm_adapter`; module adapter có nhánh chọn hosted
  implementation. Không gọi lệnh hoặc network trong review.
- **Root cause:** explicit mode path có trong code; không chứng minh rằng
  mode này đã được chạy.
- **Read-only repro:** `git show e19fe25:src/04_run_production_pipeline.py`
  và `git show e19fe25:src/kg_pipeline/llm_adapter.py`; lần theo CLI đến factory.
- **Minimal fix:** không port hosted branch; chỉ cho scientific locked path
  local adapter đã pin. Hosted data processing phải bị từ chối trước run/cache.
- **Regression:** locked CLI reject hosted/remote adapter trước mọi file, API
  hoặc cache operation; mock cũng không được dùng làm production PASS.
- **Blockers:** exact dependency lock, adapter fingerprint/cache và replay
  evidence còn thiếu trên gói.

## Quyết định tích hợp

Không cherry-pick toàn bộ nhánh Thu Hương và không chạy `run_all.py`,
`fix_source_lock.py`, `copy_stage_4_4.py`, historical crawler, production
runner, hosted adapter hoặc database import. Tip có các script/schema/output
hữu ích để tham khảo, nhưng source-lock mismatch, auto-rerun Stage 4.3,
auto-advance, overwrite helper, hosted path và PASS chưa có artifact nền khiến
toàn bộ branch chưa an toàn làm baseline M1 chính. Port theo từng diff chỉ sau
khi C3/policy cần thiết được duyệt và producer code có regression/artifact
lineage khớp guard của nhánh mới.
