# Temporal fixtures

Các synthetic fixtures này mã hóa ba leakage case bắt buộc mà temporal snapshot implementation phải xử lý trước G1:

1. **Normal publication:** evidence chỉ được xuất hiện khi `evidence_observed_at <= cutoff`.
2. **Late correction:** correction tạo version mới và không viết lại earlier scientific state.
3. **Historical ingestion:** source được ingest năm 2026 vẫn có thể eligible trong historical snapshot theo verified `evidence_observed_at`; `ingested_at_real` chỉ dùng cho provenance.

Fixtures không phải research data thật và an toàn để commit.
