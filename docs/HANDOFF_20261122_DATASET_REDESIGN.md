# Bàn giao: phân tích bộ dữ liệu, khung chuẩn mới và các quyết định (2026-11-22)

| | |
|---|---|
| Dành cho | Người tiếp nhận công việc (thành viên nhóm, người hướng dẫn hoặc agent sau), không cần đọc lại hội thoại |
| Phạm vi | Toàn bộ tri thức đã tổng hợp và đã chốt từ ngày 2026-11-17 đến 2026-11-22: kết quả v3.3, danh mục lỗi dữ liệu, tổng hợp tài liệu, so sánh hướng đi, pilot X1, khung chuẩn v1.1 và review |
| Nhánh git | `chore/env-baseline-cleanup`. Các commit của đợt này nằm sau `67673eb` (xem `git log --oneline 67673eb..HEAD`). Kho GitHub là **công khai** |
| Mức xác nhận | Mọi kết quả v3.2/v3.3 đều ở mức EXECUTED (Dev), **chưa chứng nhận**. Khung chuẩn mới chỉ là tài liệu nháp (`DRAFT_PROPOSED`) |

## 0. Đọc gì trước (khoảng 15 phút)

1. File này.
2. [docs/EVOLVING_KG_DATASET_AND_DRIFT_FRAMEWORK_v1.md](EVOLVING_KG_DATASET_AND_DRIFT_FRAMEWORK_v1.md): khung chuẩn v1.1-draft. Đọc phần "Tóm tắt một trang" và mục 1–2.
3. [docs/audit/FRAMEWORK_v1_REVIEW_20261122.md](audit/FRAMEWORK_v1_REVIEW_20261122.md): 28 phát hiện, 2 còn mở.
4. [docs/RESEARCH_REEXECUTION_PLAN_20261117.md](RESEARCH_REEXECUTION_PLAN_20261117.md) §9–§12: nhật ký chạy S1→N1→K1→X1, chứa số liệu gốc.
5. `AGENTS.md`: luật vận hành. Mọi điều trong file này đều nằm dưới AGENTS.md và protocol.

---

## 1. Trạng thái hiện tại

| Hạng mục | Trạng thái | Chi tiết |
|---|---|---|
| Giả thuyết H1 trên v3.3 | **NOT_TESTABLE** theo luật đã đăng ký | Cả quần thể (S6) lẫn nhóm bậc ≥ 3 (N1) đều không cho kết luận E-robust; MDE₈₀ = 0,36–0,57 RR |
| Báo cáo | Đã viết lại theo hướng K1: kết luận phương pháp; kết quả 28/10 bị đánh dấu không dùng | Kế hoạch §11 |
| M1, G1, G2 | **BLOCKED** | 9/17 bảng lệch `config/schema.yaml` |
| Pilot X1 (trích xuất lại bằng Gemini) | Đã đăng ký và duyệt một phần; đã lấy mẫu; **chưa gán nhãn, chưa gọi API** | Chờ O3 (người gán) và API key |
| Khung chuẩn bộ dữ liệu mới | v1.1-draft, đã review | Chưa duyệt; chưa có gì trong khung được áp dụng |
| Môi trường | **Python trong `.venv` bị Windows Application Control chặn** (không nạp được `_ctypes`, nên pandas/pyarrow lỗi) từ 2026-11-22 | Không tìm đường vòng; cần người dùng hoặc quản trị máy gỡ chặn |

---

## 2. Những gì đã CHỐT

### 2.1 Mục trong decision log (`decisions/decision_log.jsonl`, 23 mục)

| decision_id | Nội dung chốt |
|---|---|
| `stage4_3_vnexpress_no_api`, `stage4_3_vnexpress_sitemap_child_unavailable`, `stage4_3_vnexpress_archive_sampling`, `stage4_3_tuoitre_hash_guard_reconciliation` | Luật thu thập Stage 4.3 (không API; lấy mẫu Wayback). Stage 4.3 đã khóa, **không chạy lại** |
| `stage4_3_vnexpress_archive_time_semantics` | Thời gian Wayback là thời điểm bằng chứng của VnExpress |
| `preserve_original_source_baseline_20260920`, `d_source_baseline_amend_20261028` | Mốc nguồn gốc của đề cương |
| `d_cos_affine_estimand_20261028`, `d_diag_g3_thresholds_20261028` | Đại lượng 1 − cos sau căn chỉnh; ngưỡng chẩn đoán G3 |
| `s1_evidence_time_basis_20261118` | Thời điểm bằng chứng = Wayback nếu có, nếu không thì `datePublished` (JSON-LD) có múi giờ. **Không bao giờ dùng thời điểm crawl.** Thiếu thì loại |
| `s1_chrome_teaser_quarantine_20261118` | Loại 52 fact lấy từ khung tin liên quan (Tuổi Trẻ) |
| `s1_tie_safe_boundaries_and_valid_from_20261118` | Ranh giới không cắt nhóm cùng thời điểm; `valid_from` sao chép từ thời điểm bằng chứng được đặt null (1.784 fact) |
| `s2_entity_map_v2_approved_20261118` | **Bảng ánh xạ thực thể v2 được người dùng duyệt nguyên trạng**: chặn 22 mention chung chung, gộp 33 thực thể trong 32 nhóm |
| `s2_quarantine_thresholds_per_cause_20261118` | Tỷ lệ loại ≤ 5% **cho từng nguyên nhân** (3,7% và 3,3%). Tổng 7,1% chỉ công bố, không chặn |
| `s2_bucket_policy_keep_all_buckets_20261118` | Giữ 3 nhóm bậc (< 3, 3–5, ≥ 6); gộp nhóm thưa theo luật |
| `s3_convergence_gate_amendment_option_a_20261118`, `s3_contingency_c_preregistration_20261118` | Các bước trung gian của cổng hội tụ (về sau được thay bằng R1) |
| `s3_r1_fixed_training_budget_20261118` | **Cấu hình huấn luyện R1**: SGD TransE-L2, d = 64, lr = 0,01, margin = 2,0, E = 400 cho mọi snapshot và seed (13, 37, 101). Cổng ràng buộc: chất lượng, ổn định, tái lập. Hội tụ chỉ là chẩn đoán. Kiểm độ vững với E ∈ {300, 400, 500} |
| `s5_s6_drift_measurement_preregistration_20261118` | Đo drift S4–S6 (`configs/s5_drift_v33.yaml`): Procrustes trừ tâm, cross-fit 5 fold; null 6 quan sát; SED⁺; đối chứng âm và dương |
| `n1_h1_degree3_stratum_preregistration_20261118` | N1 (`configs/n1_h1_deg3_v33.yaml`): H1 trên nhóm bậc ≥ 3; luật `testable_large`, `testable_moderate`, `testable_if`; luật E-robust |
| `x1_pilot_registration_approved_20261118` | Pilot X1: O1 (40 bài VnExpress + 10 bài Tuổi Trẻ, parser v2, luật từ khóa), O2 (ngưỡng GO giữ nguyên), trần ngân sách 10 USD. Ghi hash của config X1 và guideline |

### 2.2 Quyết định của người dùng ghi trong kế hoạch (không có mục riêng trong decision log)
- **K1** (kế hoạch §11): dừng đo, viết kết quả như một kết luận về phương pháp, đánh dấu kết quả cũ là không dùng được.
- Bảng D1–D9 (kế hoạch, đầu file): D3 (ngữ nghĩa "đã được đưa tin tới t") và D5 (panel theo cohort). D5 được hiện thực qua N1 (`panel_unit`).

### 2.3 Các con số đã khóa của X1
- Config `configs/x1_reextraction_pilot_v34.yaml`, sha256 `c4f94cf062bb34d77a4a5741bc6cbf67df5ffcc5f980be9630761253f6621a59`.
- Guideline `docs/x1_gold_annotation_guideline_v1.md`, sha256 `dc5f8d218e283874ede2ccc41e1587d4f33f9e31922a6b1de77f93b90621e075`.
- Mô hình `gemini-3.8-flash`; nhiệt độ 0; không cắt bài; trường bắt buộc `evidence_text`.
- Giá tham chiếu: 0,75 USD/1 triệu token vào, 3,75 USD/1 triệu token ra. Trường hợp xấu nhất 0,041 USD mỗi lần gọi; tối đa 190 lần gọi ≈ 7,62 USD; trần cứng 10 USD. **Giá phải kiểm lại ngay trước khi gọi.**
- Luật GO: precision ≥ 0,85 và cận dưới CI ≥ 0,75; recall ≥ 0,60; ≥ 2,5 fact đúng mỗi bài; ≤ 2/50 bài lỗi cuối; câu bằng chứng khớp ≥ 0,95. Nếu F1 giữa hai người gán < 0,70 thì dừng.
- Mẫu đã lấy: `outputs/x1_reextraction_pilot/20261118T054022Z_c4f94cf0/`.
  - Gold 50 bài: VnExpress 40 (tam phân độ dài 14/13/13), Tuổi Trẻ 10 (4/3/3).
  - Dev 10 bài, tách rời gold.
  - File: `gold/G01–G50.txt`, `dev/D01–D10.txt`, `gold_template.csv`, `sample_manifest.json`, `frame_report.json`, `run_manifest.json` (ghi `dirty_state: true`).
- Khung Tuổi Trẻ: parser v2 tách được 1.520/1.529 trang (trung vị 3.119 ký tự). Còn 883 bài sau lọc. Bị loại: 636 vì không có từ khóa, 5 vì thiếu ngày, 4 vì thiếu trường, 1 vì dưới 200 ký tự.
- Luật từ khóa so với bộ lọc v3.1 trên 3.388 thân bài VnExpress: trùng 85% (208 bài v3.1 giữ dù không có từ khóa; 295 bài có từ khóa nhưng bị loại). Vì vậy **phải báo kết quả theo từng nguồn**.

---

## 3. Tri thức đã tổng hợp

### 3.1 Kết quả chính trên v3.3

| Bước | Kết quả |
|---|---|
| S1–S2 | Thời gian bằng chứng: Wayback 880, ngày đăng 871. 10 snapshot cân bằng sự kiện, mỗi snapshot khoảng 110 sự kiện, dài 36–86 ngày. T10: 1.098 triple, 1.286 thực thể |
| S3 (R1) | Cổng chất lượng PASS 10/10 (MRR 0,306–0,440 so với mốc 0,091–0,130). Ổn định giữa seed PASS. 98–100% triple vi phạm margin 2,0 |
| S6 | Ở mức quần thể, drift không khác đối chứng âm (tỷ lệ excess > 0 khoảng 0,50). Đối chứng dương trượt: độ nhạy 0,10–0,15. Thăm dò: nhóm bậc < 3 có độ nhạy 0,01; nhóm bậc ≥ 3 khoảng 0,95 với drift cực mạnh |
| N1 | Nhóm bậc ≥ 3: `testable_large` đạt ở E = 300 và 400, trượt ở E = 500 (FPR 0,170). Hệ số β không E-robust, nên H1 = NOT_TESTABLE. MDE₈₀ = 0,36–0,57. FPR của đối chứng âm tăng theo E (2,7% → 5,8% → 10,3%). Signed excess có β âm (p ≈ 0,05) nhưng **chỉ là thăm dò** |

### 3.2 Danh mục lỗi dữ liệu (L01–L28)

Trạng thái: **Đã sửa** (ở v3.2/v3.3, mức Dev) · **Một phần** · **Mở**.

| Mã | Tầng | Lỗi | Bằng chứng chính | Trạng thái |
|---|---|---|---|---|
| L01 (F12) | Văn bản | Thân bài Tuổi Trẻ thực ra là khung "tin liên quan" | 45–85 ký tự; parser v2 lấy được 1.520/1.529 trang | Một phần (parser v2 chưa vào production) |
| L02 (F10) | Văn bản | Bằng chứng là tiêu đề tin liên quan, lặp trên nhiều URL | 48 tài liệu; 52 fact; 45 sự kiện | Đã loại (S1) |
| L03 | Lọc | Bộ lọc chủ đề không tái lập được từ chính sách | Mã lý do không có trong chính sách; chỉ trùng 85% | Mở |
| L04 | Nguồn | v3.3 gần như chỉ còn dữ liệu VnExpress | Fact của Tuổi Trẻ đến từ khung tin nên bị loại (chưa đếm lại theo nguồn) | Mở |
| L05 (F13) | Trích xuất | Recall thấp | 41% trong 1.621 bài không ra claim nào; trung vị 1 claim/bài; chủ thể nằm ở 3% đầu bài; Nvidia xuất hiện ở 219 bài nhưng chỉ 32 bài có claim | Mở (X1) |
| L06 | Trích xuất | Precision chưa được đo | Một người chấm 40 claim, ước 70–90% | Mở (X1) |
| L07 (F5) | Trích xuất | Vị trí bằng chứng sai | Hash khớp 15/1.803; 828/1.865 claim có cả hai mention nằm trong đoạn bằng chứng | Mở (X1 có `evidence_text`) |
| L08 | Trích xuất | Bộ trích xuất không rõ nguồn gốc | `v1_local`; mọi claim có confidence = 0,9 | Mở |
| L09 (F4) | Thực thể | Một thực thể bị tách thành nhiều node | ≥ 31 nhóm alias. v3.3 đã gộp 33 (đã duyệt); 10 viết tắt chưa gộp | Một phần |
| L10 (F4) | Thực thể | Thực thể chung chung làm hub giả | "ông" có bậc 17. Đã chặn 22 mention; 40 sự kiện bị loại vì chưa giải được đồng tham chiếu | Một phần |
| L11 | Thực thể | Độ chính xác liên kết chưa từng được đo | — | Mở |
| L12 (F1) | Thời gian | Thời điểm crawl bị dùng làm thời điểm bằng chứng | 923/1.803 fact; snapshot T08–T10 dài 0,33/0,01/0,01 ngày | Đã sửa (v3.2) |
| L13 (F2) | Thời gian | Ranh giới cắt ngang nhóm cùng thời điểm | 5/9 ranh giới | Đã sửa |
| L14 (F3) | Thời gian | Không có trục hiệu lực; quan hệ trạng thái không được thực thi | `valid_from` sao chép; Google có nhiều CEO cùng lúc, dù ontology đã khai `is_CEO_of` là quan hệ trạng thái với khóa (relation, object) | Mở |
| L15 (F8, F11) | Cấu trúc | Đồ thị quá thưa | T10: 71% thực thể bậc 1, 18% bậc 2, 11% bậc ≥ 3; nhóm bậc ≥ 6 chỉ có 3–28 anchor | Mở |
| L16 | Cấu trúc | Đồ thị phân mảnh | Thành phần liên thông lớn nhất 447/1.286 (35%) | Mở |
| L17 | Cấu trúc | Tăng trưởng nhỏ; kích thước snapshot chênh khoảng 10 lần | 113 → 1.098 triple; khoảng 110 sự kiện mới mỗi transition | Mở |
| L18 | Câu hỏi | Panel lệch | T09→T10 có 259 dòng, T03→T04 chỉ 1; dùng được 404 dòng / 127 câu / 7 cụm | Mở |
| L19 | Thống kê | Ít cụm | 7 transition dùng được | Mở |
| L20 | Câu hỏi | Nghĩa câu hỏi chưa được người duyệt | Ví dụ "NIC – Apple" | Mở |
| L21 | Quản trị | Lệch schema | 9/17 bảng | Mở (M1 BLOCKED) |
| L22 | Quản trị | Chưa có gì được chứng nhận | v3.2/v3.3 mới ở mức Dev | Mở |
| L23 | Quản trị | Rủi ro chọn theo kết quả | Mọi thiết kế lại đều diễn ra sau N1 | Phải công bố |
| L24 | Cấu trúc | **Đồ thị gần như không đổi quanh thực thể cũ** | Mỗi transition thêm 108–111 triple nhưng 109–148 thực thể mới. Từ T01 đến T10: 985 triple mới, 1.135 thực thể mới (0,9 fact mới cho mỗi thực thể mới, so với khoảng 25 ở LKGE). Ít nhất 58% đầu cạnh mới là thực thể mới. Tối đa 8% anchor có thêm cạnh ở T09→T10 | Mở |
| L25 | Câu hỏi | Câu hỏi dồn vào vài hub | 28/35 câu mẫu đi qua `partners_with`; 5 đáp án (AMD, Anthropic, Intel, Apple, Qualcomm) chiếm 23/35 câu | Mở |
| L26 | Trích xuất | Cạnh sai nghĩa, ngược chiều hoặc thừa | ≥ 4/35 câu mẫu có cạnh sai rõ (đánh giá của Claude, không phải gold): Dario Amodei `works_at` Google; Vũ Quốc Huy `is_CEO_of` NIC; Nomi `integrated_into` GPT-4o; Google Maps `based_on` Gemini. Tim Cook có cả `is_CEO_of` lẫn `works_at` Apple | Mở |
| L27 | Thời gian | Hai căn cứ thời gian lệch nhau có hệ thống | Wayback luôn muộn hơn ngày đăng: trung vị 1,22 ngày, p90 4,16, tối đa 83,5 (n = 479) | Mở (đổi cần amendment) |
| L28 | Thu thập | Độ phủ crawl chưa được kiểm | Mỗi khoảng 110 sự kiện nhưng dài 36–86 ngày; 366 log crawl chưa được đọc | Mở |

Lỗi ở tầng mô hình (không thuộc dữ liệu), ghi trong kế hoạch §1: F6 (chưa hội tụ), F7 (nhiễu seed gần mức ngẫu nhiên ở 50 epoch), F9 (panel cũ chỉ lấy từ T01).

**Bốn nguyên nhân gốc**
1. Bộ trích xuất chưa được đo và gần như chỉ đọc phần đầu bài → L05–L08, phần lớn L15 và L24.
2. Bản chất tin tức và ontology hẹp (10 quan hệ): đuôi dài, chỉ tích lũy → L14–L17.
3. Pipeline được xây trước khi có hợp đồng dữ liệu → L01–L03, L12–L13, L21.
4. Thiết kế phép đo chưa tính tới cách dữ liệu thật thay đổi: đối chứng dương chỉ "thay cạnh" trong khi KG chỉ thêm cạnh; câu hỏi đi qua hub → L24–L26.

### 3.3 Trả lời cho các câu hỏi đã thảo luận

| Câu hỏi | Kết luận đã thống nhất |
|---|---|
| Có nên crawl và gán nhãn một bộ khác không? | **Chưa nên.** Chỗ nghẽn đo được nằm ở khâu trích xuất (L05), không ở số bài. Crawl thêm mà trích xuất như cũ thì vẫn ra khoảng 1 fact/bài. Gán nhãn chỉ để đo chất lượng trên mẫu, không gán cả bộ |
| Có cơ sở nào cho thấy trích xuất lại sẽ tốt hơn? | **Gián tiếp có, trực tiếp chưa.** Ủng hộ: thực thể lớn được nhắc nhiều hơn hẳn số bài có claim; 41% bài không ra claim; 883 bài Tuổi Trẻ chưa từng được tách. Chưa biết: số fact thật có trong mỗi bài, chất lượng của Gemini, và tỷ lệ fact mới nối vào thực thể cũ. Gold của X1 đo được cả ba |
| Bậc ≥ 3 có bắt buộc không? | **Không.** Ngưỡng 3 là mức đối chứng dương bắt đầu có tác dụng trên v3.3 (d = 64). Ngưỡng đúng là k\* lấy từ đường cong phát hiện theo bậc trên chính dữ liệu, chỉ dùng bậc trước transition. Bậc thực ra đại diện cho hai thứ: độ ổn định (nhiễu) và tín hiệu (có thay đổi hay không) |
| Nên đi hướng nào? | So sánh: A1 trích xuất lại (rẻ nhất, giữ trục thời gian, có thể vẫn thưa); A2 thêm nguồn (tốn, đuôi dài); B Wikidata theo lịch sử sửa đổi (trục thời gian tốt nhất nhưng hàng TB dữ liệu); C bộ dày có sẵn như ICEWS (gần như chắc kiểm định được nhưng trục thời gian là giả định). **Khuyến nghị: A1, có C làm phương án dự phòng đăng ký sẵn**, cộng thêm "thang độ dày" lấy mẫu con từ C. Bỏ A2 và B |
| Làm tất cả để so sánh được không? | Được, nhưng chỉ ba nhánh (A1, C, thang độ dày của C), có đăng ký vai trò từng bộ và cam kết báo mọi kết quả. So sánh giữa các bộ khác nhau không tách được nguyên nhân; thang độ dày trong cùng một bộ mới là thí nghiệm có kiểm soát |

### 3.4 Tổng hợp tài liệu (chi tiết ở Phụ lục C và G của khung)

**Cách người ta dựng bộ dữ liệu**
- Các bộ chuẩn được cố ý làm dày: FB15k-237 có bậc trung bình 42,7, YAGO3-10 chỉ giữ thực thể có ≥ 10 quan hệ, WN18RR có bậc 4,5. v3.3 chỉ có 1,7.
- Pujara 2017:
  - NELL165, trích từ văn bản, có bậc 3 và precision 0,35; trên bộ này embedding còn thua mốc cơ bản;
  - chất lượng embedding phụ thuộc vào mật độ triple trên mỗi quan hệ: bỏ trọn một số quan hệ cho Hits@10 lọc tốt hơn bỏ triple ngẫu nhiên tới 60%. Bài không tách riêng ảnh hưởng của mật độ theo thực thể. T10 của v3.3 có trung bình khoảng 110 triple mỗi quan hệ, thấp hơn mốc 220 mà bài gọi là "tương đối cao".
- LKGE 2023: snapshot tiến hóa được dựng sao cho mỗi fact mới chứa ít nhất một thực thể đã có; khoảng 25 fact mới cho mỗi thực thể mới.
- Một văn bản chứa nhiều fact hơn mức một lần trích tìm được: DocRED 12,5 → Re-DocRED ~29,8 triple/văn bản; VLSP 2020 (tin tiếng Việt) khoảng 5,6 quan hệ/bài.
- Bộ chuẩn nào cũng từng có đường tắt (quan hệ nghịch đảo ở FB15k/WN18; quan hệ trùng ở YAGO3-10; quan hệ đoán được bằng tần suất ở FB15k-237) và về sau phải sửa.

**Cốt lõi của việc đánh giá độ trôi** (chủ yếu mượn từ ngành đo thay đổi nghĩa từ, vì KGE chưa có chuẩn riêng)
1. Căn chỉnh: huấn luyện độc lập rồi căn bằng Procrustes trực giao có trừ tâm (Hamilton 2016; Schlechtweg 2019).
2. Đối chứng nhiễu: Dubossarsky 2017 cho thấy trong đối chứng không có thay đổi thật, điểm thay đổi vẫn dương và có ý nghĩa; tần suất giải thích 56% phương sai ngay cả trong đối chứng. Antoniak & Mimno 2018: lấy lại mẫu bootstrap theo tài liệu.
3. Kiểm soát tần suất/bậc: Wendlandt 2018 (từ xuất hiện 100–200 lần vẫn bất ổn); Shoemark 2019 (tần suất tối thiểu 500 mỗi khoảng; ứng viên phải xuất hiện ≥ 500 lần ở ít nhất 75% số khoảng).
4. Đối chứng dương tổng hợp có kèm kịch bản gây nhiễu: Shoemark 2019 dùng 7 kịch bản (3 thay đổi thật, 4 thoáng qua); Kulkarni 2015.
5. Chuẩn vàng: SemEval-2020 Task 1 dùng nhãn người. Với KG, có thể dùng chính thay đổi cấu trúc làm chuẩn vàng.
6. Nhiều thước đo: chồng lấn láng giềng gần nhất (Wendlandt; Gonen 2020); độ tương đồng bậc hai (Hamilton 2016a).
7. Thiên lệch độ phổ biến khi đánh giá: Mohamed 2020.
8. Các bài KGE liên tục (LKGE, BAKE) coi drift là "sự quên" cần hạn chế, không đo nó. Chưa có chuẩn sẵn cho việc đo drift KGE có hiệu chỉnh nhiễu.

### 3.5 Khung chuẩn và review (tóm tắt)

**Khung v1.1-draft gồm:**
- 12 chuẩn mực cốt lõi;
- 20 giai đoạn G0–G19 trong 5 khối (Thiết kế, Từ web đến fact, Snapshot, Đo, Đánh giá), mỗi giai đoạn có cổng ra;
- luật rẽ nhánh, chế độ thực thi và cổng đầu tư;
- sổ 36 rủi ro, bảng kiểm, mốc tài liệu;
- cách áp dụng cho nhánh A và nhánh C, ước lượng thời lượng, ngân sách tính toán (gói tối thiểu khoảng 333–576 lần huấn luyện).

**Những thay đổi then chốt so với cách làm của v3.x:**
- Pilot (G6a) và mô phỏng (G1) chạy **trước** khi dựng dữ liệu.
- Có **cổng cấu trúc đồ thị** (G12) trước khi huấn luyện: kích thước quần thể lõi, số anchor có cạnh mới, số anchor mỗi nhóm bậc, độ liên thông.
- Đối chứng dương bắt buộc có kịch bản **"thêm cạnh"** (PC1).
- Null và δ phải cùng cấu trúc ước lượng (chuẩn mực 11).
- Quan hệ trạng thái phải được thực thi bằng thay thế phiên bản.
- SESOI định nghĩa trên thang chuẩn hóa.
- Câu hỏi có trần theo đáp án; RR được phân tầng theo độ phổ biến.

**Review:** 28 phát hiện (5 cao, 11 trung bình, 11 thấp, 1 quản trị); 26 đã sửa. Hai phát hiện còn mở:
- **RV-16:** SED⁺ chỉ lấy phần dương nên phần lớn quan sát bằng 0, làm mất sức mạnh thống kê. Đổi cần amendment.
- **RV-27:** review do chính tác giả làm, nên chưa độc lập.

### 3.6 Đính chính những điều đã nói ở các lượt trao đổi trước

Các điểm sau được nói trong hội thoại ngày 2026-11-22 nhưng sai hoặc thiếu. Chúng được phát hiện khi đối chiếu với decision log và config. Hãy dùng phiên bản đúng dưới đây.

| Đã nói | Đúng là |
|---|---|
| "Bảng gộp thực thể chưa có người duyệt" (L09, L22) | Đã được duyệt nguyên trạng: `s2_entity_map_v2_approved_20261118`. Cái chưa có là **chứng nhận** M1 |
| "Tỷ lệ loại 7,1% vượt ngưỡng 5%, trượt" | Ngưỡng đã đăng ký là ≤ 5% cho **từng nguyên nhân** (3,7% và 3,3%, đều đạt); tổng 7,1% chỉ công bố (`s2_quarantine_thresholds_per_cause_20261118`) |
| "p_attach ≈ 0,42; 58% đầu cạnh mới là thực thể mới" | Đây là **cận**: p_attach ≤ 0,42 và tỷ lệ thực thể mới ≥ 58% |
| "Cần K ≥ 12 transition" | Protocol cho phép 8–12 snapshot (7–11 transition). Luật đã đăng ký yêu cầu ≥ 5 cụm; mục tiêu đề xuất là ≥ 7 |
| "Bậc trung bình của quần thể ≥ 5" làm cổng | Chỉ số này tự thỏa mãn. Thay bằng kích thước quần thể lõi (A1b) |
| "NELL165 quá thưa" | NELL165 vừa thưa vừa nhiễu |

---

## 4. Việc còn mở và cần người dùng quyết (theo thứ tự ưu tiên)

| # | Việc | Chặn cái gì | Ghi chú |
|---|---|---|---|
| 1 | **O3**: tên và vai trò của 2 người gán nhãn và 1 người phân xử | Gán gold X1 (G6a) | Người gán nhận `gold/G01–G50.txt`, `gold_template.csv` và guideline; không được xem kết quả của mô hình |
| 2 | **API key** có quyền dùng `gemini-3.8-flash`; kiểm lại giá | Gọi Gemini | Viết lớp gọi cho chế độ Dev (dùng lại `request_payload` và `validate_response`), có bộ nhớ đệm bền |
| 3 | Gỡ chặn Python (Windows Application Control) | Mọi bước có dữ liệu và test | Không tìm đường vòng |
| 4 | Thêm chỉ số chẩn đoán vào X1 (fact ngoài ontology; tỷ lệ fact nối vào thực thể cũ) | Nên làm trước khi gán | Là sửa một đăng ký đã duyệt, cần decision log |
| 5 | Hạn nộp hoặc hạn bảo vệ | Chọn giữa làm A1 + C và chỉ làm C | Đã hỏi hai lần, chưa có trả lời |
| 6 | SESOI (thang chuẩn hóa) và MDE mục tiêu | G1 | — |
| 7 | Ngữ nghĩa KG: có thay thế phiên bản cho quan hệ trạng thái không | G2, G10 | — |
| 8 | RV-16: dùng excess có dấu làm biến phơi nhiễu | G15, G18 | Cần amendment |
| 9 | Căn cứ thời gian thống nhất: P hay W | G9 | Cần amendment |
| 10 | Duyệt các ngưỡng [ĐX] của khung | Áp dụng khung | — |
| 11 | Một người review độc lập cho khung (RV-27) | Duyệt khung | — |
| 12 | Mở Pull Request từ `chore/env-baseline-cleanup` vào `main` hay không | — | Các commit đã nằm trên nhánh (mục 6); chưa mở PR |

## 5. Bước tiếp theo đề xuất

1. Khi có O3 và API key: chạy G6a (pilot X1). Thứ tự: gán gold → dùng tập dev để thử prompt → khóa prompt → trích gold → chấm → báo GO hoặc NO-GO.
2. Song song: viết bộ huấn luyện vector hóa, kèm kiểm tương đương trên v3.3. Cần cho G1.
3. G1: mô phỏng khả năng phát hiện → điền các giá trị [MP].
4. Cổng đầu tư (khung, mục 2.3): quyết định giữa nhánh A, nhánh A cộng nguồn mới, hoặc chỉ nhánh C.
5. Mỗi bước chạy một giai đoạn, báo cáo, rồi DỪNG (AGENTS §8.2).

---

## 6. File và artifact (theo AGENTS.md §7.2)

**Tạo trong các phiên 2026-11-18 → 2026-11-22, chưa commit:**

| File | Nội dung | Mức xác nhận |
|---|---|---|
| `configs/x1_reextraction_pilot_v34.yaml` | Đăng ký X1 | Đã duyệt một phần |
| `docs/x1_gold_annotation_guideline_v1.md` | Hướng dẫn gán nhãn | Đã có hash |
| `src/kg_pipeline/tuoitre_parser_v2.py` | Parser Tuổi Trẻ v2 và luật từ khóa | TESTED |
| `scripts/x1_prepare_pilot.py` | Dựng khung lấy mẫu, rút gold/dev, xuất văn bản | EXECUTED (Dev) |
| `tests/test_x1_pilot.py` | 6 test | Pass ngày 2026-11-18 |
| `docs/EVOLVING_KG_DATASET_AND_DRIFT_FRAMEWORK_v1.md` | Khung chuẩn v1.1-draft | Tài liệu nháp, chưa duyệt |
| `docs/audit/FRAMEWORK_v1_REVIEW_20261122.md` | Review khung | — |
| `docs/HANDOFF_20261122_DATASET_REDESIGN.md` | File này | — |

**Sửa:**
- `decisions/decision_log.jsonl`: thêm mục X1.
- `docs/RESEARCH_REEXECUTION_PLAN_20261117.md`: thêm §12.

Hai file `sources/Research_Execution_Plan_v1.0.md` và `v1.1_Patch.md` đã ở trạng thái sửa **từ trước** các phiên này. Thư mục `.serena/` là của công cụ, không thuộc dự án.

**Artifact:** `outputs/x1_reextraction_pilot/20261118T054022Z_c4f94cf0/` (manifest ghi commit `9c98d210…`, `dirty_state: true`).

**Kiểm thử**
- Lần chạy gần nhất (2026-11-18): toàn repo 775 pass, 1 fail cũ (`tests/test_m2_measurement_v2.py::test_current_candidate_reports_remaining_registration_without_execution`, cần outputs M2 cũ), 10 skip; ruff sạch.
- **Ngày 2026-11-22 chưa chạy lại được** vì Python bị chặn.

## 7. Lưu ý về môi trường và công cụ

- **Python bị chặn:** Windows Application Control chặn DLL `_ctypes` của Python 3.11.9 (uv), là Python mà `.venv` dùng. Khi một công cụ bị chặn thì báo người dùng, không tìm cách khác.
- **Đọc PDF:** công cụ đọc web không trích được chữ từ PDF. Bản PDF đã tải về nằm trong thư mục `tool-results` của phiên và đọc được bằng công cụ Read (tham số `pages`).
- **Huấn luyện:** bộ huấn luyện hiện tại là Python thuần chạy CPU. Máy có GPU RTX 2050 4 GB; Python mặc định chưa cài torch.

## 8. Những điều cấm (nhắc lại từ AGENTS.md)

- Không chạy lại `src/03b_run_tuoitre_historical_window.py` (Stage 4.3 đã khóa).
- Không truy cập `data/locked_test/` trước W8.
- Không sửa `configs/protocol_v1.yaml` hay `data/manifests/sources.lock.json` khi chưa có amendment.
- Không thu thập toàn bộ không giới hạn; không dùng API cho dữ liệu nghiên cứu.
- LLM chạy trên máy chủ bên ngoài không được làm người quyết định khoa học khi chưa có đăng ký.
- Mù kết quả: drift, RR, MRR, QA, H1 không được ảnh hưởng tới bất kỳ lựa chọn nào ở thượng nguồn.
- Không commit khi người dùng chưa yêu cầu.
- **Kho GitHub là công khai.** Không đẩy văn bản bài báo gốc (`outputs/` và `data/evolving_kg_downstream_v3_3/` đang bị `.gitignore`, giữ nguyên như vậy), khóa API, hay tên người gán nhãn khi họ chưa đồng ý.
- Không bỏ qua cổng chất lượng của git (không `--no-verify`, không đổi đường dẫn hook).
