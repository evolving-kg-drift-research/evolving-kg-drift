# ADR 0001: Đối chiếu trạng thái Stage 4.3 từ final evidence

Trạng thái: Accepted; chỉ đối chiếu factual state

## Bối cảnh

`docs/data_pipeline_spec.md` vẫn liệt kê phần finalize Stage 4.3 là TODO, trong khi final run tại `data/stage_4_3_runs/stage4_3_final_20260906T144016Z/` có manifest PASS, validation report PASS, artifact hash, 4,692 production observation, 3,344 unique URL và 108 historical block đã kiểm tra.

## Quyết định

Chỉ đối chiếu trạng thái sau khi read-only verifier kiểm tra final report/manifest hash, khả năng đọc và count của Parquet, validity/count của JSONL và block count. Cập nhật state text đã stale để trỏ tới evidence đó. Không chạy lại `src/03b_run_tuoitre_historical_window.py`, không đổi artifact Stage 4.3 và không suy luận Stage 4.4 PASS.

## Hệ quả

Stage 4.3 có thể được ghi là PASS trong phạm vi đã chứng minh. Raw provenance, source lock, configuration freeze và Gate A vẫn được đánh giá độc lập và có thể blocked.
