# G2-QUALITY-01 — Gold, coverage và chứng nhận chất lượng

Version: 1. Status: **PROPOSED / NOT APPROVED; NUMERIC THRESHOLDS ABSENT**.
Findings: M1-002/018; M1-RV-003/004. Authority: Stage 4.13.

## Procedure đề xuất cần duyệt

- Gold tạo độc lập từ exact source texts/evidence, người annotate không dùng
  predictions đang đánh giá làm đáp án. Lưu annotation IDs, guideline version,
  reviewer provenance và adjudication bất đồng.
- Khóa sampling rule/IDs trước scoring; phân tầng theo source, relation và
  thời gian trong scope. Lưu cả pending/conflict/copy cases, không chỉ accepted.
- Annotation unit là candidate claim với mention/entity links, relation,
  subject/object/value, validity/evidence-time basis, spans và expected decision.
- Entity linking: đúng canonical ID trên gold mentions đủ điều kiện; relation:
  precision/recall từ matched predictions và gold, report FP/FN đầy đủ; temporal:
  field-specific agreement theo basis đã duyệt; span: exact text/offset/hash
  checks. Mỗi metric có numerator/denominator và exclusions có reason.
- Báo riêng conflict/pending behavior và source-copy errors. Duplicate gold
  IDs/prediction keys, missing evaluation units, NaN scores phải fail closed.
- Không gộp metric thành confidence 0.9. G2 report bind gold hash, policy hash,
  input hashes, evaluator code và run. Structural diagnostics không cấp G2.
- Zero-tolerance temporal/mapping/provenance invariant violation: FAIL.
  Không có gold/evaluated rows/approved threshold/coverage requirement: BLOCKED.

## Ngưỡng và các đầu vào còn thiếu

Không đề xuất numeric thresholds ở đây vì không có pilot/gold độc lập.
Sau pilot, lập threshold annex gồm values, selection basis, denominators,
coverage minimum và hash; reviewer phê duyệt/khóa trước scale main corpus.
Không điều chỉnh ngưỡng vì test hoặc downstream result xấu. Chấp thuận hồ sơ
procedure này chưa đủ mở gate khi annex chưa tồn tại.

Stage 4.13 dùng pilot quality evidence, không yêu cầu final snapshot G1 trước
pilot. Final G2 dùng frozen procedure và artifacts được bàn giao; không tái
sử dụng pilot PASS như chứng nhận toàn main corpus.

## Tests và ảnh hưởng

Empty/unmatched gold, zero coverage, missing strata, false match, FP/FN,
duplicate prediction/gold, invalid threshold, stale gold/input hashes,
evaluator-not-run và handcrafted PASS certificate đều phải bị chặn.
Thay evaluator/guideline/gold invalidate reports, không tự đổi raw/facts;
nếu phát hiện extraction/identity errors thì định phạm vi reprocess bằng finding.
