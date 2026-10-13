# Phân tích lỗi T01 legacy — 2026-10-14

## Kết luận

MRR tổng cao hơn baseline nhưng lợi thế tập trung ở 4 held-out triples có cặp
entity đã có cạnh khác trong training. Trên 16 triples còn lại, cả ba seed
đều thấp hơn baseline. Đồng thời self-loop đứng đầu phần lớn lượt dự đoán.
Kết quả hiện tại chưa hỗ trợ kết luận mô hình dự đoán tốt các cặp chưa thấy.

Đây là phân tích hậu nghiệm, chỉ mô tả artifacts hiện có; không thay metrics
chính, không bỏ query, không huấn luyện lại hoặc điều chỉnh dữ liệu upstream.

## Evidence và cách tái hiện

Run đã chấm: `outputs/legacy_evaluation/20261013T170623Z_e7a3592e/`.
Phân tích: `outputs/legacy_error_analysis_20261014/report.json`.
Lệnh: `python scripts/analyze_legacy_t01_errors.py`.
Script kiểm hashes toàn bộ inventory trước/sau, đọc split/ranks, tính nhóm
head/tail/relation/seen-pair và lưu top-3 cho từng query/seed. Thư mục output
dùng exclusive creation; để tái hiện cần đổi output path mới, không xóa/ghi đè
báo cáo cũ. Không đọc model outcome để thay đổi upstream.

## Tách nhóm cặp entity

Seen-pair ở đây chỉ có nghĩa cùng cặp entity không phân biệt hướng đã xuất hiện
qua một triple khác trong 101 training triples; không khẳng định inverse leakage.

| Nhóm | Queries | Baseline MRR | Seed 13 | Seed 37 | Seed 101 |
|---|---:|---:|---:|---:|---:|
| 4 triples seen-pair | 8 | 0.025926 | 0.288273 | 0.205400 | 0.279861 |
| 16 triples unseen-pair | 32 | 0.064099 | 0.059053 | 0.054747 | 0.047365 |

Mean MRR ba seed: seen-pair 0.257845; unseen-pair 0.053722. Không tính significance
hoặc coi các query/seed là independent observations. Giữ nguyên điểm tổng đã báo.

## Head/tail và độ ổn định

| Hướng | Baseline MRR | Seed 13 | Seed 37 | Seed 101 |
|---|---:|---:|---:|---:|
| Head (20 queries) | 0.032700 | 0.114613 | 0.069542 | 0.101104 |
| Tail (20 queries) | 0.080229 | 0.095182 | 0.100214 | 0.086624 |

- Chỉ 4/40 queries nằm top-10 ở cả ba seed; 20/40 ngoài top-10 ở cả ba.
- 15/40 queries tốt hơn baseline ở cả ba seed.
- Median của khoảng max-rank minus min-rank giữa seeds là 63 hạng.
- 31/40 queries có cùng top-1 ở cả ba seed; sự đồng thuận này không đồng nghĩa
  đúng vì top-1 tập trung ở self-loop. Không có top-score ties ở cả 120 lượt.

## Self-loop

| Seed | Top-1 là entity còn lại trong query | Tỷ lệ |
|---|---:|---:|
| 13 | 36/40 | 90% |
| 37 | 34/40 | 85% |
| 101 | 39/40 | 97.5% |

Ví dụ query head `(? , integrated_into, ent_60965168)`, gold là
`ent_6b0f56dd`: cả ba seed đứng đầu bằng `ent_60965168`, tạo self-loop.
Gold ranks tương ứng 26/85/41.

Theo TransE-L2, energy của `(e,r,e)` bằng `||r||` vì hai entity vectors triệt
tiêu. Kiểm tra độc lập từ checkpoint xác nhận self-loop score bằng âm norm
relation (sai số < 1e-12) và tái đếm đúng 36/34/39 top-1 self-loops.
Candidate universe đã duyệt là toàn bộ 167 entities, không cấm self-loop;
filtered ranking chỉ bỏ positive khác đã biết, nên những candidate này còn
được chấm đúng thiết kế. Chưa có bằng chứng evaluator đảo chiều điểm hay lỗi tie.

Đây là cơ chế scoring đã xác minh, nhưng chưa đủ để kết luận nguyên nhân
training sâu hơn (ít dữ liệu, relation norms, negative sampling, số epochs).
Không tự sửa evaluator để loại self-loop và tăng Hits@1 hậu nghiệm.

## Theo relation (chỉ mô tả, sample nhỏ)

| Relation | Queries | Baseline MRR | Mean MRR ba seeds |
|---|---:|---:|---:|
| integrated_into | 4 | 0.010596 | 0.025289 |
| invested_in | 2 | 0.266667 | 0.014833 |
| partners_with | 8 | 0.065806 | 0.095612 |
| released_by | 10 | 0.086429 | 0.064897 |
| succeeded_by | 2 | 0.010582 | 0.102059 |
| version_of | 6 | 0.010582 | 0.170845 |
| works_at | 8 | 0.025933 | 0.125997 |

`invested_in` chỉ có một held-out triple, không suy rộng thành kết luận toàn
relation. Không có canonical name/type mapping hoặc source text đủ để phân
loại một cách tin cậy các lỗi thành nhầm người/tổ chức, gần nghĩa, hoặc fact
đúng còn thiếu. Giữ entity IDs, không suy đoán tên hoặc tự bổ sung gold.

## Structured findings

### LTE-001 — MEDIUM — Lợi thế tập trung ở seen-pair subset
- **Affected:** saved `split.json`, `seed_*_ranks.json`, `baseline_ranks.json` trong run trên.
- **Expected:** Diễn giải kết quả trong đúng population, không suy rộng từ aggregate.
- **Actual:** Unseen-pair MRR cả ba seeds dưới baseline; aggregate vẫn trên baseline.
- **Evidence:** Bảng nhóm và `report.json:groups.*.seen_pair/unseen_pair`.
- **Root cause vs hypothesis:** Khác biệt theo nhóm đã xác nhận; vì sao mô hình tận dụng cặp cũ tốt hơn chưa được chứng minh nhân quả.
- **Reproduction:** Chạy script phân tích, nhóm bằng unordered entity pair membership trong train.
- **Minimal action:** Công bố phân rã, giữ aggregate gốc; nếu thử split khác phải đăng ký thử nghiệm mới.
- **Regression tests:** Không thêm unit test; đối chiếu counts 8+32=40 và group metrics từ rank rows.
- **Blockers:** Sample nhỏ, chưa có independent evaluation population mới.

### LTE-002 — MEDIUM — Self-loop chiếm phần lớn top-1
- **Affected:** `src/kge/model.py:score_triple`, `scripts/evaluate_legacy_t01.py:rank_query`, saved checkpoints/ranks.
- **Expected:** Giữ đúng candidate/filter contract và phân biệt hành vi mô hình với lỗi evaluator.
- **Actual:** Self-loop top-1 36/34/39 trên 40 queries.
- **Evidence:** Saved top scores và phép tính độc lập `score(e,r,e)=-||r||`.
- **Root cause vs hypothesis:** Cancellation và ranking đã xác minh; tác động của optimizer/config/dataset vẫn là giả thuyết.
- **Reproduction:** Từ checkpoint, lấy entity còn lại làm candidate và so điểm với toàn candidate scores.
- **Minimal action:** Ghi nhận failure mode; chỉ thử constraint/training khác trong run mới được chốt, không sửa kết quả cũ.
- **Regression tests:** Ranking tests trước đã kiểm direction/filter/ties; lượt này kiểm trực tiếp 120 self-loop scores và top counts.
- **Blockers:** Chưa có policy loại self-loop/type constraints được chốt cho một thử nghiệm mới.

### LTE-003 — GOVERNANCE — Không đủ evidence để giải thích ngữ nghĩa
- **Affected:** legacy entity IDs và upstream mapping/provenance v3.
- **Expected:** Kết luận nhầm entity hoặc missing true fact phải có canonical mapping/source evidence.
- **Actual:** Chỉ phân tích structural errors; không đủ căn cứ giải thích gần nghĩa/type/missing gold.
- **Evidence:** Audit v3 đã ghi mapping `v1_mock` và thiếu upstream payloads; lượt này không mở rộng acquisition.
- **Root cause vs hypothesis:** Evidence thiếu; không kết luận dữ liệu giả hoặc dự đoán ngoài gold chắc chắn sai trong thực tế.
- **Reproduction:** Đối chiếu package inventory và audit v3.
- **Minimal action:** Khôi phục evidence theo quy trình upstream được duyệt, tách khỏi việc xem model outcomes.
- **Regression tests:** Không thêm; cần provenance/mapping tests khi thực hiện remediation.
- **Blockers:** Mapping và source text chưa được chứng thực.

## Verification và điểm dừng

IMPLEMENTED: script/report mới. TESTED: targeted Ruff PASS, không huấn luyện
hoặc chạy lại test suite. EXECUTED: phân tích read-only trên artifacts thật.
VERIFIED: artifact hashes trước/sau, group counts và self-loop scores/top-counts;
không chứng nhận scientific gates. Không sửa dữ liệu, split, weights hoặc metrics.
Code/báo cáo chưa commit/push trong lượt này.

Bước tiếp theo hợp lý là kiểm tra cơ chế training/negative sampling bằng fixtures
được thiết kế trước, và làm rõ candidate constraints cho một thử nghiệm mới.
Không tuning tiếp trên 20 held-out hoặc chạy drift để quyết định upstream.
