# Báo cáo toàn bộ quy trình M2 — huấn luyện, alignment, nhiễu và drift

Ngày: 14/10/2026. Phạm vi: external-package Dev, scientific_certification=false.


## 1. Mục tiêu, phạm vi và kết quả chính


Mục tiêu của M2 là đo sự thay đổi representation qua thời gian và hiệu chỉnh theo nhiễu do retraining. Backbone giữ TransE-L2; dự án không đề xuất một kiến trúc KGE mới.


Người dùng yêu cầu sử dụng toàn bộ dữ liệu đã upload, bỏ điều kiện nghiệm thu M1 cho lần thực hiện M2 này, tạo nhánh mới và làm từng bước. Nhánh làm việc là codex/m2-drift-workflow, base commit 2860235; công việc M1 đang mở được giữ nguyên.


Đã hoàn tất preflight → pilot → chốt cấu hình → backbone → alignment → empirical null/LTO → longitudinal drift → Dev handoff. 30 checkpoint configurations, 81 alignments, 41.382 noise observations, 20.691 temporal observations và 6.897 entity×transition drift rows đã được lưu và kiểm độc lập.


Báo cáo này bổ sung trực quan hóa và log dễ tra cứu từ artifacts đã lưu; không chạy lại training hoặc thay đổi bất kỳ tham số, snapshot, anchor, bucket, null reference hay metric nào. M3 hiện mới có khung module; M4/QA/statistical inference chưa được thực hiện.


| Phần | Trạng thái |
| --- | --- |
| M2 | EXECUTED / VERIFIED trong Dev scope |
| M3 paths / auditor | Khung module; chưa triển khai thực thi |
| M4 QA / thống kê | Chưa thực hiện; bước kế tiếp là readiness |
| Nghiệm thu khoa học M1 / G3 | Chưa chứng nhận |


## 2. Kiểm tra đầu vào và tiến trình snapshots


Nguồn KGE là canonical Parquet của data/KG_lan2/evolving_kg_downstream_v3. Preflight kiểm bytes/hashes, schema ID columns, mappings, counts và cutoff ordering. Giữ toàn bộ provenance columns của canonical export; không dựng private snapshots.


10 snapshots có cùng 10 relations; T01 có 121 triples/167 entities, T10 có 1.205 triples/1.389 entities. Trong gói này các transitions chỉ thêm cạnh/thực thể và giữ toàn bộ population trước đó; đây là giới hạn phạm vi khi diễn giải các thay đổi KG.


Cutoffs do gói bên ngoài cung cấp được giữ nguyên. Các khoảng cách thời gian không đều, đặc biệt T07–T10 tập trung trong tháng 9/2026. Đồ thị theo thứ tự transition chưa phải tốc độ drift mỗi ngày. Historical observation/identity validity của M1 vẫn chưa được chứng nhận.


| Snapshot | Cutoff (UTC) | Triples | Entities | Relations |
| --- | --- | --- | --- | --- |
| T01 | 2025-06-01T01:05:48+00:00 | 121 | 167 | 10 |
| T02 | 2025-09-16T20:09:42+00:00 | 247 | 343 | 10 |
| T03 | 2025-12-18T07:29:02+00:00 | 362 | 503 | 10 |
| T04 | 2026-02-27T05:54:13+00:00 | 483 | 646 | 10 |
| T05 | 2026-05-26T03:11:12+00:00 | 604 | 787 | 10 |
| T06 | 2026-08-11T04:23:59+00:00 | 724 | 936 | 10 |
| T07 | 2026-09-06T18:04:24+00:00 | 844 | 1057 | 10 |
| T08 | 2026-09-07T01:55:05+00:00 | 964 | 1176 | 10 |
| T09 | 2026-09-07T02:03:22+00:00 | 1084 | 1282 | 10 |
| T10 | 2026-09-07T02:13:25+00:00 | 1205 | 1389 | 10 |


![Quy mô dữ liệu T01–T10](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/01_snapshot_growth.png>)

10 relations ở mọi snapshot. Trục x là thứ tự snapshot; các cutoff không cách đều theo thời gian.


## 3. Pilot và quyết định 64 chiều


Pilot thử dimensions 32 và 64, seeds 13/37/101. T01 chia coverage-preserving thành 101 train và 20 validation triples; mỗi seed/dimension có 40 head/tail ranking queries với 167 candidate entities. Có 18 configurations, mỗi configuration chạy từ đầu hai lần (36 training executions).


Mean validation MRR: 32 chiều = 0,110916; 64 chiều = 0,122906. Cả hai dimensions đạt 9/9 pilot alignment checks; quy tắc chọn đã đăng ký trước outcomes đề xuất 64 chiều và người dùng duyệt cấu hình. Chênh lệch khoảng 0,01199 chỉ là kết quả pilot Dev, chưa có kiểm định superiority.


Hits@1 của cả ba seeds 64 chiều bằng 0. Validation thiên về entities có nhiều cạnh do split giữ coverage; kết quả không đại diện cho toàn corpus hoặc QA multi-hop. Dimension không được chọn bằng SED+, RR của QA hay dấu H1.


Independent pilot verifier đo lại 240 ranking rows và 18 SVD alignments từ serialized vectors, kiểm input/output provenance, exact replays và selection.


![Pilot: chất lượng link prediction trên T01](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/02_pilot_validation.png>)

101 train / 20 validation triples; 40 head/tail queries/seed/dimension. Đây là validation link prediction, chưa phải QA multi-hop. Hits@1 của cả 3 seeds 64 chiều bằng 0.


## 4. Backbone và log huấn luyện


Cấu hình đã duyệt: TransE-L2, dimension 64, epochs 50, learning rate 0,01, margin 1, entity normalization và seeds 13/37/101. Mỗi snapshot/seed train từ đầu độc lập trên toàn snapshot. Field batch_size=32 có trong cấu hình, nhưng implementation cập nhật per-triple; báo cáo không gọi đây là mini-batch training.


30 configurations × 2 repeats = 60 training executions, mất 160,32 giây theo stage log. 30/30 replay checkpoint pairs byte-identical trong môi trường đã dùng; full mapping/config/snapshot/seed/git lineage và finite losses/embeddings được kiểm độc lập.


Loss epoch 50 nằm trong [0.388088, 0.498366]. Median giảm loss so với epoch 1 là 53.84%, range [50.16%, 60.67%]. Các giá trị này chỉ mô tả training diagnostics.


Đã xuất 1.500 epoch log rows cho 30 mô hình × 50 epoch từ repeat 1; repeat 2 đã chứng minh exact byte replay. Full-snapshot training không có validation loss. Không có intermediate embeddings/checkpoints theo từng epoch trong run này, nên không thể vẽ quỹ đạo embedding hoặc drift theo epoch từ log hiện có.


Loss là margin-ranking objective với negative sampling. Đường loss giảm và có dao động; không tuyên bố đã hội tụ tối ưu, khái quát tốt hay có QA quality chỉ từ biểu đồ loss. Phần Log huấn luyện trong báo cáo HTML cho phép chọn snapshot/seed, đọc epoch và tải log đang chọn.


| Snapshot | Triples | Entities | Loss seed 13 | Loss seed 37 | Loss seed 101 |
| --- | --- | --- | --- | --- | --- |
| T01 | 121 | 167 | 0.413035 | 0.416826 | 0.388088 |
| T02 | 247 | 343 | 0.446933 | 0.415828 | 0.428103 |
| T03 | 362 | 503 | 0.413484 | 0.447399 | 0.436178 |
| T04 | 483 | 646 | 0.460287 | 0.436080 | 0.436768 |
| T05 | 604 | 787 | 0.450256 | 0.454663 | 0.459602 |
| T06 | 724 | 936 | 0.464814 | 0.465955 | 0.454492 |
| T07 | 844 | 1057 | 0.471915 | 0.478332 | 0.488443 |
| T08 | 964 | 1176 | 0.498366 | 0.470168 | 0.468138 |
| T09 | 1084 | 1282 | 0.473590 | 0.475009 | 0.475839 |
| T10 | 1205 | 1389 | 0.465831 | 0.477746 | 0.472926 |


![Loss huấn luyện: 30 mô hình × 50 epoch](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/03_training_losses.png>)

Đường loss thô từ checkpoints, không làm trơn; full-snapshot training không có validation loss. Loss dao động do negative sampling; đồ thị chưa xác nhận hội tụ tối ưu hoặc chất lượng QA.


![Chẩn đoán loss cuối và mức giảm loss](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/04_training_summary.png>)

Phần trăm giảm = 100×(loss epoch 1 − loss epoch 50)/loss epoch 1. Mỗi mô hình train từ đầu; quy mô và samples khác nhau giữa snapshots nên loss không phải thước đo so sánh độ chính xác QA.


## 5. Centered Procrustes alignment


Anchors là persistent canonical entities, phân tầng theo exact degree ở snapshot trước. Split cố định, deterministic và disjoint: 101 fit / 66 holdout; cùng split dùng cho mọi comparison trong một transition. Không chọn anchors theo drift, fact-change labels hoặc QA outcomes.


81 comparisons = 9 transitions × (3 cross-time same-seed + 6 same-snapshot cross-seed tại hai endpoints). Mỗi comparison chạy SVD hai lần, tổng 162 SVD executions; 81/81 exact replays và 81/81 available theo các guard Dev đã duyệt.


Tất cả numerical rank bằng 64. Max holdout RMSE = 1.404725; max holdout−fit gap = 0.580387; max orthogonality error = 2.198345e-14.


Guard đã duyệt trước measurement: rank tối thiểu 64, holdout RMSE tối đa 2, gap tối đa 1, orthogonality error tối đa 1e−4. Đạt numerical diagnostics trong Dev scope không tương đương semantic stability hoặc G3 scientific certification.


![Alignment: 81 comparisons và các guard Dev đã duyệt](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/05_alignment_diagnostics.png>)

27 cross-time + 54 same-snapshot comparisons; 101 fit / 66 holdout anchors. Max/Min tổng hợp theo transition, không phải CI. Numerical diagnostics đạt guard không xác nhận semantic quality hoặc cấp G3.


## 6. Empirical null và Leave-Target-Out


Mỗi persistent entity có 6 noise observations: seed pairs (13,37), (13,101), (37,101) ở mỗi endpoint. Noise dùng saved centered Q/fit means; không re-align. Có 41.382 observations; các seed-pair observations có tương quan và không được tính là 6 statistical units độc lập.


Buckets dùng degree ở snapshot trước: low <3, medium 3–5, high ≥6. Sparse merging pooled theo adjacency, tie về trái; trong run thật không có merge. LTO bỏ toàn bộ 6 observations của target, rồi tính median/MAD/robust scale từ reference entities còn lại. Không target-specific remerge.


Guard reference: ít nhất 5 observations và MAD≥1e−12; scale=1,4826×MAD. Empty/degenerate references phải unavailable có reason. 6.897/6.897 references available theo rules đã duyệt, nhưng numerical availability chưa chứng minh adequate inferential support.


T01→T02 high bucket chỉ có 2 target entities: mỗi LTO còn 1 reference entity và 6 correlated observations. Bảng/biểu đồ support giữ rõ hạn chế này; không đổi threshold/buckets sau khi nhìn outcomes.


![Degree buckets và support của null LTO](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/09_degree_support.png>)

Degree lấy từ snapshot trước. T01→T02 high bucket có 2 targets; mỗi LTO chỉ còn 1 reference entity/6 correlated pair observations. Giữ nguyên buckets và các guard đã duyệt.


## 7. Longitudinal drift: displacement, signed excess và SED+


Mỗi seed: δ_seed = 1 − cos((x_previous − μ_source)Q, y_next − μ_target). Dùng đúng ba cross-time parallel seeds 13/37/101; δ_time là median ba values của từng entity. Undefined centered cosine hoặc unavailable alignment làm stage dừng, không sinh defaults.


Signed excess r = δ_time − LTO_null_median, giữ cả giá trị âm. SED+ = max(0,r)/(1,4826×LTO_MAD + 0,0001), chỉ khi null available. Epsilon không được dùng để cứu ZERO_MAD/thiếu reference.


Có 20.691 temporal observations và 6.897 entity×transition drift rows, đều available theo Dev config. 3.640 rows có r>0 (52.78%); 3.257 rows âm được giữ và có SED+=0. SED+ lớn nhất 5.219441.


Giá trị SED+ lớn nhất thuộc high bucket của T01→T02, nơi mỗi LTO chỉ có một reference entity. Đây là điểm cần đọc cùng support counts; extreme SED+ trong bucket nhỏ chưa đủ cơ sở cho kết luận drift có ý nghĩa thống kê.


Independent NumPy verifier đo lại toàn bộ temporal/calibrated values, kiểm 549 input hashes, 57 artifact hashes, 9 transition manifests, JSON/Parquet equality, replays và Dev handoff. 9/9 transition JSON repeats và 2/2 Parquet serialization repeats exact bytes.


Một r>0 hay SED+ cao chỉ là chỉ số mô tả representation movement trên noise reference. Chưa có p-value, kiểm định H1, ước lượng tác động QA hoặc kết luận nhân quả. Population và upstream measurement parameters không thay đổi theo các đồ thị mới.


| Transition | n | Median δ_time | Median r | Median SED+ | P95 SED+ | r>0 | Min LTO entities |
| --- | --- | --- | --- | --- | --- | --- | --- |
| T01→T02 | 167 | 0.358799 | -0.030598 | 0.000000 | 3.227369 | 75 | 1 |
| T02→T03 | 343 | 0.833742 | 0.012604 | 0.046436 | 0.939583 | 178 | 6 |
| T03→T04 | 503 | 0.892596 | 0.019016 | 0.089150 | 1.072816 | 266 | 11 |
| T04→T05 | 646 | 0.927986 | 0.017416 | 0.096690 | 1.009759 | 351 | 14 |
| T05→T06 | 787 | 0.924675 | 0.005515 | 0.032297 | 0.992718 | 407 | 17 |
| T06→T07 | 936 | 0.938494 | 0.005733 | 0.036846 | 1.107518 | 489 | 21 |
| T07→T08 | 1057 | 0.942547 | 0.010263 | 0.065713 | 1.066213 | 566 | 23 |
| T08→T09 | 1176 | 0.948712 | 0.017000 | 0.110744 | 1.095157 | 655 | 25 |
| T09→T10 | 1282 | 0.942291 | 0.001978 | 0.013052 | 1.091118 | 653 | 29 |


![Chuyển dịch qua thời gian so với nhiễu retraining](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/06_temporal_vs_noise.png>)

Mỗi điểm là một entity×transition. Vùng màu là IQR (25–75%), không phải khoảng tin cậy. Điểm trên đường chéo có r>0; điều này chưa phải kiểm định ý nghĩa thống kê.


![Phân bố signed excess và SED+](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/07_drift_distributions.png>)

Median/IQR, whiskers 1.5×IQR và mọi outlier được hiển thị. r giữ dấu âm; SED+ cắt phần âm về 0 và chuẩn hóa bằng 1.4826×LTO_MAD + 1e−4. Tất cả 6.897 rows được giữ.


![Tỷ lệ excess dương và phần đuôi SED+](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/08_drift_summary.png>)

Phân vị và tỷ lệ mô tả trên toàn population; không có p-value hoặc kiểm định H1. Median thấp vẫn có thể đi cùng một phần đuôi SED+ cao.


![Độ biến thiên displacement giữa ba seeds](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/figures/10_seed_variability.png>)

Range đo chênh lệch của ba parallel seed values; không phải sai số chuẩn. δ_time production vẫn là median theo từng entity, không phải median của ba đường tổng hợp trong hình.


## 8. Kiểm chứng, tái lập và artifact lineage


Các stage độc lập theo thứ tự inspect → plan → implement → test → execute → validate → report → dừng. Mỗi lần advance có yêu cầu người dùng. Artifacts mới append-only; old runs và historical source data được giữ nguyên.


Bản M2 cuối được full suite kiểm: 505 passed, 10 existing skipped; Ruff và diff checks PASS, Python 3.11.9. 10 skip là placeholder tests có sẵn, không dùng để nghiệm thu gate. Python 3.10 chưa được chạy local.


IMPLEMENTED: code/guards/manifests đã viết. TESTED: fixtures/contract/scientific regression. EXECUTED: stage chạy trên real artifact-backed data. VERIFIED: verifier độc lập kiểm lại arithmetic/population/lineage. Các tier này áp dụng đúng scope Dev, không xác minh bổ sung M1 temporal semantics.


Báo cáo mới kiểm lại source manifest/receipt fingerprints và các source hash catalogs trước khi trích log/vẽ. Report manifest bind source hashes, exact report/plot/log hashes và archived report code/template. Không có hosted scientific decision-maker hoặc truy cập locked_test.


| Stage | Run | Independent receipt | Manifest SHA-256 |
| --- | --- | --- | --- |
| preflight | outputs/m2_preflight/20261014T031739Z_71f4e280 | Preflight technical inventory | 8be78a857f9bf561c4326dc397644dcabcddce7e34793ab89880aa16d326f6fe |
| pilot | outputs/m2_pilot/20261014T031822Z_9b722664 | PILOT_ARTIFACT_VERIFICATION_PASS | 4796d73ffddfb070fb6eefc174a13deeeca1b1682d1a790c72256fb5447f29d1 |
| backbone | outputs/m2_backbone/20261014T034042Z_65c464ba | BACKBONE_ARTIFACT_VERIFICATION_PASS | f4f8771a58cdf0f05ac6ca203c315ab364be6adcde8e9d08200324d729ec8354 |
| alignment | outputs/m2_alignment/20261014T040001Z_96d9ccbc | ALIGNMENT_ARTIFACT_VERIFICATION_PASS | 920b78c4ec057ff95f3e6cd812394cf3cae43e275f286779bfeee583ca6403ea |
| null | outputs/m2_null/20261014T042450Z_43e91590 | NULL_ARTIFACT_VERIFICATION_PASS | 7bdd6de62fc0f506661957e15909a9ecc43bdcfe935227425d22635436976b89 |
| drift | outputs/m2_drift/20261014T044648Z_ae9f0401 | DRIFT_ARTIFACT_VERIFICATION_PASS | e35ff8ee51a9ee1126325d5e995f8d62e30adb4d488325d963e83d187826eeda |


## 9. Những phần còn thiếu và bước tiếp theo


M2 Dev đã hoàn tất đến entity-level drift và handoff. M1 G1/G2/official handoff và scientific G3 chưa được chứng nhận; scientific protocol vẫn còn các giá trị chờ freeze. Numerical PASS của run này không chuyển trạng thái các gate đó.


M3 bounded paths và semantic auditor mới có khung module, chưa triển khai/chạy. Đây là support track; không dùng việc chờ M3 để chặn CORE. M4 chưa có recurring QA panel đã chốt trong gói đang dùng; chưa chạy Arms A/B/C, RR/MRR QA, H1/H2, WCB hoặc pseudo-drift falsification.


Bước kế tiếp là M4 readiness: kiểm query/gold/support evidence theo cutoff, recurring population, Seen-at-T1/candidate universes và complete-support joins với drift. Khi panel/rules đầy đủ mới thực hiện đánh giá theo stage authorization. Trước kết luận khoa học chính thức cần hoàn tất nghiệm thu M1/G3.


Các biểu đồ hiện có phản ánh loss theo epoch và movement giữa snapshots. Chưa có log gradient, intermediate embedding trajectories hoặc validation mỗi epoch của full-snapshot backbone; báo cáo giữ rõ phạm vi log thật, không dựng dữ liệu giả.


## Log và các file bàn giao


- [Báo cáo và bảng tra cứu tương tác](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/report.html>)

- [1.500 log epoch huấn luyện](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/training_epoch_log.jsonl>)

- [6.897 log drift có ba seed values](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/entity_drift_log.jsonl>)

- [Thống kê và dữ liệu nguồn cho biểu đồ](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/analysis_summary.json>)

- [Report lineage và hashes](<D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift/outputs/m2_report/20261014T061101Z_a624c271/experiment_manifest.json>)