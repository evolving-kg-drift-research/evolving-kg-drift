# ADR 0002: Ticket A dùng immutable run artifact và content-addressed body text

Trạng thái: Accepted; quyết định kỹ thuật

## Quyết định

Work mới được cô lập dưới `runs/<run_id>/`. Raw bytes chỉ được đọc bằng repository-relative path và hash; không copy đè, xóa hoặc thay thế. Table là canonical Parquet part có ordered-row semantic manifest và physical file hash. Normalized body text được lưu theo SHA-256 riêng trong CAS path mới.

Retry chỉ được dùng lại artifact khi semantic hash khớp. Payload khác tại cùng output path là conflict và cần run mới. Operational timestamp đi vào append-only JSONL và bị loại khỏi semantic table hash.

## Mô hình recovery

Ghi data vào temporary file, rename sang final immutable path, rồi commit sidecar manifest. Nếu crash giữa các bước này, retry kiểm tra row Parquet hiện có theo semantic hash dự kiến trước khi ghi manifest còn thiếu.

## Hệ quả

Canonical scientific storage vẫn là Parquet. Neo4j không được dùng trong Ticket A và vẫn là materialization/query layer ở stage sau. Quyết định này không freeze parsing semantics, ontology, temporal behavior hoặc input readiness.
