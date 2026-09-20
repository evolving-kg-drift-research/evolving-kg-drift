# Đối chiếu cấu hình - Ticket A

## Bổ sung checkpoint 0 — 2026-09-20

ADR 0007 giữ baseline nguồn gốc theo quyết định trực tiếp của người dùng và supersede quyền placeholder/đổi hash trong ADR 0006. Không thay source lock hoặc protocol hashes. Thiếu original đúng bytes vẫn BLOCKED.

Phần bảng và mô tả bên dưới là đối chiếu lịch sử, không phải kiểm chứng lại hash/reader của HEAD hiện tại. Một số script legacy được nhắc tới không có trong nhánh này. Hiện `run.py::_bundle_payload` đã hard-code `FROZEN` theo ADR 0005, trái với mô tả `PROPOSED_UNFROZEN` lịch sử bên dưới; đó không phải bằng chứng scientific freeze. Runtime validation sẽ được sửa ở checkpoint tiếp theo. Baseline kỹ thuật Ticket A không thay pilot/ontology/pipeline freeze theo master spec. Xem `data_pipeline_compliance.md` và `checkpoint_0_report.md`.

## Đối chiếu lịch sử (giữ nguyên)

Trạng thái: **PROPOSED_UNFROZEN**. Tài liệu này chỉ map các file cấu hình thực tế trong repository; nó không merge cấu hình và không chọn scientific baseline.

| File | SHA-256 | Version / vai trò quan sát được | Reader hiện tại quan sát được | Time field / hành vi chính | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `config/protocol.yaml` | `8de31ee8fa6b68671195d0bb99c2801ce966cf40ef716f150670ff6e4bf9ce99` | `protocol_version: 0.1.0`; common contract kiểu legacy | `src/00_validate_protocol.py`, `src/invariants.py`; Ticket A chỉ fingerprint | Định nghĩa `retrieved_at_real` là project-time provenance và tách riêng `evidence_observed_at` / `accepted_into_kg_at`. | Chỉ là candidate; chưa có evidence cho thấy nó thay thế draft. |
| `config/ontology.yaml` | `9d3345a3f12e2c4641179710abf3904b1175a3181ea2d63987b022195b7c1262` | `ontology_version: 1.1`; 10 relation trong config | Ticket A chỉ fingerprint; chưa có semantic consumer mới | Domain/range và tính đối xứng của `partners_with`; chưa có cách xử lý được duyệt cho mâu thuẫn lịch sử 10/11 relation. | Không thêm/xóa/đổi relation. |
| `config/schema.yaml` | `6eb1a66ffdf19ff7b720e41d61eaab5aa25526fca569c022ccc93465ae71a6f2` | Danh sách field lưu trữ hiện có | Ticket A chỉ fingerprint; chưa có semantic consumer mới | Raw source version dùng `retrieved_at_real`; claims/facts tách riêng evidence/acceptance/valid fields. | Chỉ là candidate field mapping. |
| `configs/protocol_v1.yaml` | `61d1eb47ec9fbfb06fff418c785722fecb16090ef886039cd1359ff5cc465c73` | Scientific protocol `v1-draft` | `tests/test_config_consistency.py`, `scripts/verify_w1.py`, `scripts/verify_w7.py`; Ticket A chỉ fingerprint | Dùng `ingested_at_real`; còn các giá trị `TO_BE_FROZEN_*` chưa resolve. | Không thể freeze nguyên trạng. |
| `configs/data.yaml` | `9f85c14535c2f5a54487167d719a62c274edeb60efbcd0e3e395578d1d4a610d` | Config data/fact-version | `tests/test_config_consistency.py`, `scripts/verify_w1.py`; Ticket A chỉ fingerprint | Dùng `ingested_at_real`; khớp cách đặt tên field của draft protocol. | Không chứng minh tương đương với `retrieved_at_real`. |
| `data/manifests/sources.lock.json` | `a6e32c14f28aa60e7977ec25b1ee60e71bf1226273d4f94de4edb58cf9a796b7` | Immutable source-artifact lock | `kg_pipeline.run.inspect_source_lock` và input check trong run manifest | Khóa ba source artifact gốc đang thiếu. | BLOCKED; không đổi. |

## Các phân biệt bắt buộc

- `retrieved_at_real`: một collection/retrieval event có tên, chỉ hợp lệ khi acquisition record chứng minh event đó.
- `ingested_at_real`: một project ingestion event có tên. Không được âm thầm đổi tên thành retrieval.
- `evidence_observed_at`: thời điểm evidence content state có thể được biết công khai; không phải crawler time.
- `accepted_into_kg_at`: thời điểm acceptance có hiệu lực theo adjudication rule đã freeze; không phải job time.
- `valid_from` / `valid_to`: world validity; không field nào được backfill từ các field ở trên.

Vì vậy Ticket A ghi một field là unknown nếu allowed acquisition evidence không mang đúng field đó. Ticket A không thay thế bằng file mtime, HTML publication tag, inventory time hoặc thứ tự thư mục.

## Quyết định mapping

Run ghi `inputs/proposed_config_bundle.yaml`, gồm hash của source file và các open decision. File này cố ý có `status: PROPOSED_UNFROZEN`:

1. Chưa có evidence được duyệt để chọn một protocol directory làm canonical.
2. Hai real-time field có nhãn/vai trò khác nhau và chưa có alias rule được duyệt.
3. Các locked source artifact gốc đang không có sẵn.
4. Mâu thuẫn số lượng relation trong ontology chưa được adjudicate.

Không downstream scientific output nào được tuyên bố bundle này đã frozen. Lựa chọn parser/storage của Ticket A là kỹ thuật và có thể đảo ngược; mọi lựa chọn về ontology, identity, time, source-scope hoặc acceptance semantics đều cần scientific decision riêng và đánh giá tác động reprocessing có version.
