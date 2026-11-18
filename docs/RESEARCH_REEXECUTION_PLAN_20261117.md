# Kế hoạch thực hiện lại nghiên cứu trên data v3.1 — bản 2 (2026-11-17)

Trạng thái: **ĐỀ XUẤT**, chưa phải protocol. Giá trị đánh dấu *(đăng ký)* phải được chốt
bằng decision/amendment **trước** khi chạy stage tương ứng (INV-06). Bản 2 thay bản 1
cùng ngày, bổ sung phân tích định danh entity, span bằng chứng, độ hội tụ huấn luyện,
noise floor và quy mô bộ câu hỏi.

## Tóm tắt

1. Gói v3.1 **toàn vẹn** (hash, parity Neo4j có so khớp tập cạnh/node) nhưng **trục thời
   gian sai cho ~51% fact**: thời điểm crawl bị dùng làm thời điểm quan sát bằng chứng.
   T07–T10 là dữ liệu dồn cuối, không phải tiến hóa theo thời gian.
2. Embedding của run cũ **chưa hội tụ** (50 epoch): MRR ngang baseline tầm thường, nhiễu
   giữa seed ≈ 88–94% nhiễu của vector ngẫu nhiên → drift cũ chủ yếu là nhiễu.
3. Định danh entity = hash chuỗi viết thường → alias bị tách, đại từ "ông" thành hub.
4. Bộ câu hỏi cũ = fact đã train; chỉ T01 thì không đủ câu đa bước → cần panel cohort.
5. Kết quả M2/M4 ngày 28/10 và báo cáo LaTeX **không dùng được làm kết luận**; cần chạy
   lại sau khi sửa dữ liệu. Thứ tự: thời gian → định danh → huấn luyện → đo → QA → thống kê.

## 0. Đã xác thực

| Hạng mục | Kết quả |
|---|---|
| ZIP v3.1 | SHA-256 `a6acd988…915d` khớp `.sha256.txt` |
| Giải nén `data/evolving_kg_downstream_v3_1/` | 4.871/4.871 file khớp `release_manifest.json` |
| `inspect_package` | `PACKAGE_TECHNICAL_CHECKS_PASS` (10 snapshot, 9 transition) |
| Parity Neo4j (`reports/exact_neo4j_readback_parity.json`) | Read-back thật, `EDGE_SET_EQUALITY` và `NODE_SET_EQUALITY` = true (chưa tự chạy lại) |
| W1 strict | **PASS** sau khi sửa `.gitattributes` (`sources/*.md -text`) và khôi phục byte CRLF |
| Môi trường | `.venv` Python 3.11.9; ruff sạch; pytest 651 pass / 1 fail (cần outputs cũ) / 10 skip |

Ghi chú: tài liệu `v3.1 có gì.docx` ghi "đạt chuẩn nghiệm thu khoa học"; chính
`v3_1_package_validation_report.json` ghi phạm vi là gói đầu vào TransE + Stage 4.18 và
"does not claim a full M1 re-certification". Kế hoạch theo phạm vi của báo cáo validation.

## 1. Phát hiện

| ID | Mức | Bằng chứng | Hệ quả |
|---|---|---|---|
| **F1** | CRITICAL | 923/1.803 fact version không có bằng chứng Wayback; `evidence_observed_at == retrieved_at_real` (crawl 06–07/09/2026). Event chỉ có bằng chứng crawl: T07 75%, T08 98%, T09 94%, T10 97% (T01–T06: 0%). T08/T09/T10 dài 0,33/0,01/0,01 ngày. | "Drift" qua T07–T10 là thứ tự crawler; T01–T06 thiếu fact đáng lẽ thuộc về chúng. |
| F1a | — | Mã bài VnExpress trong URL so với ngày Wayback: Spearman 0,999, sai số trung vị ~9 ngày (462 bài). Ước lượng ngày đăng 484 bài "trễ": 04/2025 → 08/2026; 48% trước 18/12/2025; 15% trước cutoff T01. | Xác nhận F1 có hệ thống; mã bài dùng được để **kiểm chéo**, không phải bằng chứng. |
| F1b | — | 52 fact Tuổi Trẻ quan sát 17:29–17:53 ngày 06/09/2026; URL chứa timestamp đăng (`…-20260220140751211.htm`), 1.400/1.529 URL có dạng này. | Có nguồn thời điểm đăng do nhà xuất bản công bố. |
| **F2** | HIGH | 5/9 ranh giới (sau T01, T02, T04, T05, T06) cắt nhóm cùng `effective_at`. | Snapshot không là hàm as-of thuần của cutoff. |
| **F3** | HIGH | `valid_from == evidence_observed_at` 1.784/1.803; `valid_to` rỗng; `revision_type` toàn `creation`; `confidence` = 0,9 cho mọi fact. CEO của Google: Page, Eric Schmidt, Sundar Pichai, "ông". | KG là tích lũy "đã được đưa tin tới t", không phải "đúng tại t". Trục hiệu lực thế giới không tồn tại thực chất. |
| **F4** | HIGH | `entity_id = "ent_" + sha256(lower(mention))[:8]` cho 1.389/1.389 entity (`v1_mock`, `AUTO_ACCEPTED`). ≥ 31 nhóm alias (63 entity) chỉ với chuẩn hóa nhẹ: FPT / tập đoàn FPT, AWS ×4 biến thể, Grok 3 / Grok-3… Entity chung chung ≥ 6: "ông" (bậc 17, top-10), "công ty" (9), "AI" (6); 103 entity bắt đầu bằng chữ thường ("laptop mới", "thế hệ TV năm nay"). | Alias làm đồ thị thưa giả tạo; hub rác tạo đường đa bước vô nghĩa (35/1.842 đường 2-hop ở T10 đi qua entity chung chung). |
| **F5** | MEDIUM | Span hash khớp 15/1.803 fact; chỉ 828/1.865 claim có cả hai mention nằm trong span, 1.859/1.865 có trong body. | Offset span sai; bằng chứng truy vết yếu (ảnh hưởng G2, không chặn TransE). |
| **F6** | HIGH | Probe T10, d=64, lr 0,01: ep50 loss 0,48, val filtered MRR 0,18 ≈ baseline "tail phổ biến theo relation" 0,16; ep100–500 MRR 0,25–0,29, loss < 0,05 từ ep200. lr 0,05 hội tụ từ ep50. | Embedding cũ chưa hội tụ. |
| **F7** | HIGH | Khoảng cách 1−cos giữa seed 13/37 sau Procrustes, entity bậc 1: T01 0,43 → 0,26 (ep50 → ep300); T05 0,71 → 0,54; bậc ≥ 6 ở T05: 0,34 → 0,10. Mốc ngẫu nhiên: T01 0,49, T05 0,76. | Ở ep50 nhiễu ≈ ngẫu nhiên → giải thích tỷ lệ drift dương 47,6% ≈ 50% của run cũ. Mốc ngẫu nhiên phụ thuộc số entity/số chiều → phải đo trên holdout. |
| **F8** | HIGH | 90% entity bậc ≤ 2. Triple có thể giữ lại làm validation (cả hai đầu bậc ≥ 2): 27% (T01), 25% (T05), 34% (T10). Chia ngẫu nhiên 10% ở T05 chỉ còn 15 triple xếp hạng được. | Validation phải lấy mẫu có cấu trúc + lặp nhiều fold. |
| **F9** | HIGH | Panel cũ = 121 triple train T01 + 26 đường 2-hop; ranking không lọc. Với mốc thời gian ước lượng (F1a/F1b) và lọc đường tắt/entity chung chung: T01 chỉ có 18 câu 2-hop, 1 câu 3-hop; T05 358/154; T10 1.707/1.935. | Panel chỉ từ T01 không đủ power; cần panel cohort. |

Hệ quả cho kết quả cũ: H1 (β_d = −0,0037, p = 0,574) và pseudo-drift được ước lượng
trên trục thời gian sai (F1) và embedding chưa hội tụ (F6–F7). Không dùng làm kết luận;
báo cáo LaTeX cần ghi rõ là đã bị thay thế.

## 2. Quyết định cần chốt (trước khi chạy)

| ID | Câu hỏi | Khuyến nghị | Lý do |
|---|---|---|---|
| D1 | Nguồn thời điểm đăng | **Đã giải quyết khả thi, không cần tải lại:** raw HTML trong `evolving-kg-drift.zip` của người xử lý data (5.426 blob). 482/484 bài VnExpress có JSON-LD `datePublished`; 2 bài còn lại → quarantine hoặc xem xét tay. Tuổi Trẻ: timestamp trong URL, kiểm chéo bằng HTML. Mã bài VnExpress chỉ dùng kiểm chéo. | Thời điểm công khai thật, xác định, kiểm chứng được. Kiểm chéo: |Δ| so với ước lượng từ mã bài trung vị 7,6 ngày, tối đa 35 ngày; khoảng 17/03/2025 → 30/08/2026; 0 bài đăng sau ngày crawl. |
| D2 | Quy tắc ranh giới | Event-balanced, dời ranh giới tới cuối nhóm cùng timestamp | Giữ `OUTCOME_BLIND_EVENT_BALANCED_V1`, sửa F2 |
| D3 | Ngữ nghĩa KG | Khai báo rõ: KG tích lũy "đã được đưa tin tới t"; không suy diễn `valid_to` | Trung thực với dữ liệu (F3); không bịa trục hiệu lực |
| D4 | Entity map v2 | (i) Danh sách chặn entity chung chung → quarantine; (ii) quy tắc alias xác định (bỏ tiền tố "tập đoàn/công ty/ngân hàng…", tách viết tắt trong ngoặc, chuẩn hóa dấu gạch/khoảng trắng); (iii) danh sách gộp được người duyệt; version `entity_map_v2` | Sửa F4 trước khi train; phải chốt trước để mù kết quả |
| D5 | Quần thể QA | Panel cohort: câu vào panel ở snapshot đầu tiên nó khả thi, theo dõi mọi transition sau; TWFE unbalanced với query FE. Cần amendment cho định nghĩa Seen-at-T1 của H2. | F9 |
| D6 | Chế độ huấn luyện | Số epoch cố định chung, chọn sao cho snapshot lớn nhất hội tụ với biên an toàn; mọi run phải qua cổng hội tụ. Lưới: d ∈ {32, 64}, lr ∈ {0,01; 0,05}, margin, uniform vs Bernoulli. | F6; cùng cấu hình cho mọi snapshot để drift không lẫn thay đổi cấu hình |
| D7 | Ngưỡng G3 | Chạy lại pilot căn chỉnh trên embedding đã hội tụ rồi đăng ký lại ngưỡng (D-DIAG 28/10 lấy từ pilot chưa hội tụ) bằng amendment | Ngưỡng phải phản ánh mô hình thật được dùng |
| D8 | Kết quả null | Đăng ký MDE trước; null là kết quả hợp lệ nếu qua đối chứng dương (S6) | Tránh tune sau khi thấy kết quả |
| D9 | Kết quả 28/10 | Đánh dấu superseded trong PROGRESS và báo cáo | F1, F6, F7 |

## 3. Kế hoạch theo stage

Nguyên tắc: một stage một lần; mỗi run có manifest (`git_commit`, `dirty_state`,
`config_hash`, hash input/output, seed); dừng nếu cổng không qua; không dùng drift, RR/MRR
của QA hay H1 để chọn tham số upstream.

### S1 — Sửa trục thời gian, dựng snapshot v3.2 (M1)
- **Làm:** gán `evidence_observed_at` cho fact crawl trực tiếp = thời điểm đăng từ D1;
  giữ `archive_datetime` cho bản Wayback; event `effective_at` = bằng chứng sớm nhất.
  Fact không xác định được → `snapshot_exclusions.parquet`, không điền mặc định. Cắt
  snapshot theo D2 thành version mới; v3.1 giữ nguyên.
- **Vì sao:** INV-01 và tách 3 trục thời gian là bất biến cứng; mọi phép đo sau dựa trên
  thứ tự thời gian.
- **Xác thực:**
  - 0 fact có `evidence_observed_at == retrieved_at_real` mà không có bằng chứng ngày đăng.
  - Kiểm chéo: ngày đăng khôi phục so với ước lượng từ mã bài, |Δ| trung vị ≤ 15 ngày
    *(đăng ký)*; mọi ngày đăng ≤ `archive_datetime` nếu có cả hai.
  - Tuổi Trẻ: timestamp URL so với meta HTML (khi có raw) khớp ≤ 1 ngày.
  - 0 ranh giới cắt nhóm timestamp; mỗi snapshot kéo dài ≥ 14 ngày *(đăng ký)*.
    Theo ước lượng: 35–65 ngày.
  - `verify_g1.py --ci --code-checks`, `tests/test_hard_invariants.py`; dựng lại 2 lần
    cho cùng hash (INV-04). Tỷ lệ quarantine được báo cáo; > 5% *(đăng ký)* → dừng.

### S2 — Entity map v2 và độ đủ của dữ liệu
- **Làm:** áp D4; báo cáo trước/sau: số entity, bậc, thành phần liên thông, số anchor bền
  vững theo bucket bậc, số câu hỏi khả thi theo hop, MDE cho H1.
- **Vì sao:** alias tách một thực thể thành nhiều node bậc thấp → tăng nhiễu (F7) và mất
  đường đa bước; entity chung chung tạo đường giả. Sửa trước khi train để không chọn quy
  tắc theo kết quả.
- **Xác thực:** người duyệt mẫu ≥ 50 cặp gộp và toàn bộ danh sách chặn; 0 entity chung
  chung còn trong snapshot; ánh xạ v1 → v2 lưu dạng bảng có hash; MDE ghi vào decision log.

### S3 — Huấn luyện TransE-L2 có kiểm định
- **Làm:**
  1. Chọn siêu tham số một lần trên snapshot lớn nhất sau sửa: validation = K = 5 fold
     lấy mẫu **chỉ trong triple giữ lại được** (cả hai đầu còn trong train), hash-disjoint.
     Thước đo: filtered MRR và Hits@10, kèm khoảng tin cậy bootstrap.
  2. Huấn luyện chính: cùng cấu hình và cùng số epoch cho 10 snapshot × 3 seed
     (13, 37, 101), train toàn bộ snapshot.
- **Vì sao:**
  - TransE-L2 do protocol chốt; tịnh tiến cho phép ghép đường `h + r1 + r2`.
  - Cấu hình chung: nếu khác nhau, chênh lệch embedding chứa thay đổi cấu hình.
  - Số epoch cố định nhưng **bắt buộc kiểm hội tụ từng run**: snapshot nhỏ có ít cập nhật
    mỗi epoch; nếu chưa hội tụ đều thì mức nhiễu khác nhau theo kích thước, lẫn vào drift.
  - Chỉ dùng tiêu chí protocol cho phép: `validation_quality`, `stability`,
    `alignment_feasibility`.
- **Theo dõi mỗi epoch, mỗi seed:** margin loss trung bình; tỷ lệ cặp còn vi phạm margin;
  validation filtered MRR/Hits@10 mỗi 10 epoch; norm entity/relation; NaN/Inf. Lưu đường
  cong vào artifact và vẽ hình.
- **Xác thực:**
  - Hội tụ: thay đổi tương đối loss < 1% trong 20 epoch cuối *(đăng ký)*, cho **mọi**
    snapshot × seed; không NaN.
  - Chất lượng: cận dưới CI của validation MRR > baseline "tail phổ biến theo relation"
    (probe hiện tại: 0,16) và >> ngẫu nhiên (~0,006).
  - Ổn định: noise floor theo bucket bậc < mốc vector ngẫu nhiên của cùng cấu hình, đo
    trên anchor holdout.
  - Xác định: cùng seed → checkpoint trùng hash.
- **Tham khảo từ probe (dữ liệu chưa sửa, không phải giá trị đăng ký):** lr 0,01 cần
  ~200 epoch; lr 0,05 ~50 epoch; MRR bão hòa ~0,27–0,29. Mỗi epoch T10 mất ~0,06 s →
  toàn bộ 30 run × vài trăm epoch chỉ vài phút; tìm siêu tham số đầy đủ là khả thi.

### S4 — Căn chỉnh Procrustes trực giao có trừ tâm
- **Làm:** anchor = entity có mặt ở cả hai snapshot, phân tầng theo bậc trước transition,
  chia fit/holdout hash-disjoint; giải Procrustes trực giao sau khi trừ tâm.
- **Vì sao:** khoảng cách TransE không đổi khi quay mọi vector bằng cùng một ma trận trực
  giao và tịnh tiến entity → mỗi lần train cho một hệ tọa độ tùy ý; Procrustes trực giao +
  trừ tâm khử đúng phần tùy ý đó. Entity đã chuẩn hóa L2 nên không cần co giãn. Anchor
  chọn theo cấu trúc, không theo drift (protocol cấm).
- **Lưu ý từ F7:** khi số anchor fit không lớn hơn nhiều so với số chiều (T01: ~167 entity,
  d = 64), Procrustes khớp luôn cả nhiễu → mọi chẩn đoán đo trên holdout; tỷ lệ anchor/số
  chiều là một tiêu chí khi chọn d ∈ {32, 64}.
- **Xác thực:** lỗi trực giao, residual holdout, chênh lệch fit–holdout, hạng số trong
  ngưỡng G3 đăng ký lại (D7); căn chỉnh hỏng → `unavailable_with_reason`, không ép SED⁺.

### S5 — Null cùng snapshot (nhiễu huấn luyện)
- **Làm:** mỗi snapshot, khoảng cách giữa 3 cặp seed sau căn chỉnh cho từng entity; điều
  kiện theo bucket bậc; leave-target-out.
- **Vì sao:** khoảng cách T → T+1 = drift thật + nhiễu tối ưu hóa; cùng snapshot khác seed
  chỉ có nhiễu. Điều kiện theo bậc vì nhiễu giảm mạnh theo bậc (F7). LTO tránh entity tự so
  với chính nó.
- **Xác thực:** đủ quan sát tham chiếu mỗi bucket; MAD > 0; báo cáo phân phối null theo
  bucket và tỷ lệ so với mốc ngẫu nhiên.

### S6 — Đo drift và kiểm chứng phép đo
- **Làm:** δ_time = trung vị 3 seed của (1 − cos) sau căn chỉnh; r = δ_time − trung vị
  null; SED⁺ = max(0, r) / (1,4826·MAD + ε).
- **Vì sao:** trung vị/MAD bền với ngoại lai khi chỉ có 3 seed; lấy phần dương vì câu hỏi
  là "drift vượt nhiễu"; vẫn báo cáo r có dấu.
- **Xác thực (đăng ký trước):**
  - Đối chứng âm: pseudo-drift cùng snapshot → tỷ lệ r > 0 ≈ 50%, SED⁺ trung vị ≈ 0.
  - Đối chứng dương: bản sao snapshot, đổi đích một phần cạnh của tập entity chọn theo
    seed cố định → estimator phải phát hiện; báo cáo độ nhạy theo bucket bậc. Không phát
    hiện được → kết quả null trên dữ liệu thật không diễn giải được.
  - Hiệu lực cấu trúc: entity có cạnh mới trong transition có δ lớn hơn entity không đổi
    cùng bucket bậc (giả thuyết ghi trước).

### S7 — Bộ câu hỏi đa bước ẩn mắt xích
- **Định nghĩa cấu trúc:** `(head, [r1..rk], tập đáp án as-of)`, k ∈ {1, 2, 3}. Mắt xích
  không xuất hiện trong truy vấn; điểm = −‖h + Σrᵢ − c‖; thực thể bắc cầu nằm trong
  `support_entities` để đo drift.
- **Lọc (đăng ký trước):** bỏ câu có đường tắt (đáp án nối trực tiếp với head); bỏ câu qua
  entity chung chung; bỏ chu trình; giới hạn số câu mỗi head *(đăng ký)*; phân tầng theo
  kiểu đường quan hệ và bucket bậc.
- **Ranking có lọc:** loại các đáp án đúng khác (as-of) khỏi ứng viên — bắt buộc vì nhiều
  (h, r) có nhiều đáp án và KG tích lũy (F3).
- **Panel cohort (D5):** câu vào panel ở snapshot đầu tiên khả thi. Quy mô ước lượng: tổng
  câu 2-hop/3-hop tăng từ 18/1 (T01) lên 358/154 (T05) và 1.707/1.935 (T10).
- **1-hop là thứ cấp:** là fact đã train → RR gần trần. H1 chính dựa trên 2–3 hop.
- **Tối đa 3 hop:** protocol giới hạn 1–3 hop; sai số tịnh tiến cộng dồn theo số bước.
- **Câu chữ tiếng Việt:** sinh từ template cho người đọc và nhánh ICL tùy chọn; kiểm tay
  ≥ 30 câu (không lộ mắt xích, đúng nghĩa quan hệ, nêu rõ tập đáp án). Câu chữ không ảnh
  hưởng điểm TransE.
- **Xác thực:** đủ câu theo MDE; kiểm trần/sàn RR ở Arm A; hash panel freeze trước Arm B.

### S8 — Đánh giá Arm A (frozen T01) / Arm B (updated Tt)
Seen-at-T1 và open-world tách biệt; ứng viên chưa thấy → −∞; gold OOV → RR = 0. Xác thực:
cân bằng panel, không trộn universe, đủ 3 seed.

### S9 — Thống kê
TWFE (query FE + transition FE), WCB theo cluster transition, pseudo-drift falsification,
LOTO. Chỉ có 9 cluster → p-value WCB rời rạc; báo cáo kèm khoảng tin cậy và MDE.

## 4. Nhận xét về đề nghị của người dùng

1. **Xác thực từng bước** — đồng ý; nhưng thứ tự quan trọng hơn độ kỹ. Probe cho thấy
   chất lượng embedding sửa được dễ (thêm epoch), còn trục thời gian và định danh thì
   không — phải sửa trước.
2. **"Embedding tốt"** — định nghĩa trước bằng validation link prediction + ổn định giữa
   seed. Entity bậc 1 sẽ vẫn nhiễu cao kể cả khi hội tụ; báo cáo theo bậc thay vì ép.
3. **Câu hỏi ẩn mắt xích nhiều bước** — chất lượng nằm ở cấu trúc (lọc đường tắt, entity
   chung chung, ranking có lọc), không ở câu chữ; dừng ở 3 hop.
4. **Kết quả có thể là null** — hợp lệ nếu phép đo qua đối chứng dương.

## 5. Cần từ người dùng
- ~~Raw HTML~~ — **đã có** trong `evolving-kg-drift.zip` (root dự án, 1,43 GB, SHA-256
  `0daf5b1f…9622`; chưa có hash gốc từ bên gửi để đối chiếu). Mới giải nén vào thư mục tạm,
  chưa đưa vào `data/raw/` của repo; cần bạn đồng ý trước khi đặt vào repo.
- Chốt D1–D9 (D1 chỉ còn cần xác nhận phương án dùng JSON-LD `datePublished`).

## 5a. Kết quả kiểm tra gói của người xử lý data (2026-11-17)
- Zip là bản sao toàn bộ thư mục dự án (gồm `.venv`, `.git`, ~40 thư mục `runs/pilot_*`);
  chỉ `data/raw/stage_4_4/blobs`, `data/stage_4_4_runs`, `runs/production_v3` là cần.
- 484 bài VnExpress "trễ" (898 fact): 484/484 có raw blob; 482 trích được `datePublished`
  bằng JSON-LD; 2 không khớp mẫu nào.
- Kiểm chéo độc lập với ước lượng từ mã bài (calibrate trên 462 bài có Wayback): n = 482,
  |Δ| trung vị 7,6 ngày, p90 23,9 ngày, tối đa 35 ngày. Phân bố ngày đăng: 16,6% trước
  cutoff T01 cũ, 49,4% trước 18/12/2025, 98,3% trước 11/08/2026, 100% trước 06/09/2026.
- Hệ quả: xác nhận F1; mốc cuối 30/08/2026 khớp window dữ liệu 31/08 đã ghi trong audit;
  T07–T10 cũ thực chất là dữ liệu trải từ 03/2025 đến 08/2026 bị dồn về ngày crawl.
- Raw blob: **5.168/5.168 khớp SHA-256 trong `raw_blob_reference_manifest.json`** (0 sai,
  0 thiếu) — nên raw trong zip chính là bản gói v3.1 đã tham chiếu.
- Chưa làm: chưa kiểm `data/stage_4_4_runs` (log crawl) xem có ghi `lastmod`/`pubDate` để
  đối chiếu thêm; chưa đưa raw vào `data/raw/` của repo; chưa kiểm 2 bài không có
  `datePublished` và 44 fact Tuổi Trẻ bằng HTML.

## Phụ lục — các probe đã chạy (Dev, không đăng ký)
Trên dữ liệu v3.1 chưa sửa; chỉ dùng thước đo protocol cho phép (link prediction, ổn
định giữa seed); không dùng drift/QA/H1. Không tạo artifact trong `outputs/`.
- Huấn luyện T10 bằng `kge.model.TransEModel` (d = 64, margin 1, seed 13), held-out 83
  triple (fold 1/5 của triple giữ lại được), filtered MRR ở ep 10/50/100/200/500/1000.
- Noise floor T01/T05: seed 13 so với 37, ep 50 và 300, Procrustes trực giao có trừ tâm
  trên toàn bộ entity, 1 − cos theo bậc; mốc = hai ma trận Gauss ngẫu nhiên cùng kích thước.
- Mốc thời gian ước lượng (F1a/F1b) chỉ dùng để định cỡ S1/S7, không phải dữ liệu.

## 6. S1 — Kết quả thực hiện (2026-11-18) — EXECUTED (Dev), chưa certified

**Phạm vi:** dựng lại thời gian bằng chứng và 10 snapshot canonical thành gói v3.2 *candidate*
(`data/evolving_kg_downstream_v3_2/`, gitignored). v3.1 và `data/raw` không bị sửa. Không chạy
`run_snapshot` production (M1 vẫn BLOCKED); đây là tái dựng kỹ thuật từ bảng v3.1.

### Quy tắc thời gian áp dụng (mỗi fact version ghi basis / confidence / flags)
1. Có bản chụp Wayback → `evidence_observed_at = archive_datetime` nhỏ nhất (giữ nguyên quyết
   định `stage4_3_vnexpress_archive_time_semantics`); basis `wayback_archive_datetime`, confidence `high`.
2. Không có Wayback → ngày đăng do nhà xuất bản khai trong HTML (JSON-LD `datePublished`);
   basis `publisher_declared_published_at`, confidence `medium`. Không có múi giờ → bị từ chối.
3. Thân bài là tiêu đề tin liên quan (cờ producer `SHORT_BODY_LT_200_CHARS`) mà không có Wayback →
   **quarantine** (`CHROME_TEASER_EVIDENCE_TIME_UNKNOWN`).
4. Thời điểm crawl (`retrieved_at_real`) không bao giờ là thời điểm bằng chứng; không điền giá
   trị mặc định. Event = bằng chứng sớm nhất; snapshot = mọi event có thời điểm ≤ cutoff.
5. Ranh giới: event-balanced như v3.1 (`round(k·N/10)`) nhưng dời tới cuối nhóm cùng timestamp
   (`OUTCOME_BLIND_EVENT_BALANCED_V1_TIE_SAFE`); chỉ dùng số event và timestamp (mù kết quả).
6. `valid_from` v3.1 là bản sao thời điểm crawl ở 1.784/1.803 fact → đặt null; 19 giá trị độc
   lập (ngày thật trong văn bản) giữ nguyên.

### F10 (phát hiện mới trong S1) — HIGH: bằng chứng là "khung tin liên quan"
48 tài liệu Tuổi Trẻ có thân bài 37–91 ký tự là tiêu đề tin liên quan ở khung trang, lặp lại trên
nhiều URL khác nhau (23 tài liệu gắn ≥ 2 URL với ngày đăng khác nhau). Ngày đăng của trang chứa
không cho biết lúc tiêu đề đó xuất hiện; trạng thái khung phản ánh lúc crawl. Ảnh hưởng: 52/1.803
fact, 45/1.205 event chỉ có loại bằng chứng này (3,7%, dưới ngưỡng 5%).

### Số liệu
| | v3.1 | v3.2 candidate |
|---|---|---|
| fact version / event có thời gian hợp lệ | 1.803 / 1.205 | 1.751 / 1.160 |
| basis | crawl-time 923 (51%) | Wayback 880, publisher 871 |
| độ dài snapshot (ngày) | T08–T10: 0,33 / 0,01 / 0,01 | 36,7 – 76,4 (min ≥ 14 ✔) |
| cutoff T01 → T10 | 2025-06-01 → 2026-09-07 | 2025-04-27 → 2026-08-15 |
| triple T01 / T05 / T10 | 121 / 604 / 1.205 | 117 / 580 / 1.160 |
| ranh giới cắt nhóm timestamp | 5/9 | 0/9 |

Độ lệch giữa hai cơ sở thời gian (Wayback − ngày đăng, n = 479): trung vị 1,22 ngày, p90 4,16 ngày,
tối đa 83,5 ngày, 0 trường hợp âm → việc trộn hai cơ sở gây lệch nhỏ so với độ dài snapshot.
Kiểm chéo bằng mã bài VnExpress (n = 466): |Δ| trung vị 7,96 ngày, p90 24,3, tối đa 34,7.

### Xác thực (mỗi mục đã chạy)
| Kiểm | Kết quả |
|---|---|
| Unit test logic thuần (`tests/test_evidence_time.py`) | 13 pass |
| Toàn repo: ruff / pytest | sạch / 664 pass, 1 fail (cũ, cần outputs M2), 10 skip |
| INV-01 mọi dòng canonical `observed ≤ cutoff` | PASS |
| Snapshot = đúng tập event as-of (dựng lại độc lập từ v3.1) | PASS, lồng nhau, không xóa cạnh |
| Phân tích lại ngày đăng bằng regex (mẫu 80 tài liệu) | 0 lệch |
| Nạp bằng bộ nạp M2 (`inspect_package`) | PACKAGE_TECHNICAL_CHECKS_PASS |
| Giả mạo cố ý 1 thời điểm | verifier FAIL (3 tín hiệu) |
| Dựng lại 2 lần | 14 Parquet + YAML + báo cáo trùng từng byte |

### Giới hạn / chưa làm
- Chưa phải certification: entity map còn `v1_mock`, schema M1 BLOCKED, chưa decision/amendment cho
  quy tắc basis (spec §8.4 cấm gán thẳng ngày đăng ở Stage 4.4; ở Stage 4.10 được phép nếu ghi
  basis/confidence/cờ — mình theo hướng này nhưng chưa có phê duyệt ghi vào decision log).
- Ngày đăng của trang có thể bị nhà xuất bản sửa; chưa có cách kiểm độc lập ngoài mã bài.
- 2 fact có `valid_from` (ngày thuần, nửa đêm UTC) sau thời điểm quan sát ~6 giờ: lệch múi giờ,
  giữ nguyên và ghi cờ trong báo cáo.
- Chưa kiểm 366 file log crawl (`stage_4_4_runs`); 16 tài liệu có nhiều ngày đăng giữ ngày sớm nhất
  (đều có nội dung đầy đủ hoặc đã loại nếu là khung tin liên quan — chưa tách riêng để xác nhận).
- Parquet ghi bởi pyarrow 23.0.0 (khóa trong lock); hash vật lý phụ thuộc phiên bản đó.

### Quyết định cần người dùng duyệt trước S2
- Q1: Chấp nhận Wayback > ngày đăng làm basis thời gian (và ghi decision log)?
- Q2: Chấp nhận quarantine khung tin liên quan (F10), hay muốn xử lý khác?
- Q3: Chấp nhận chính sách ranh giới tie-safe (D2) và `valid_from` = null cho bản sao crawl?

## 7. S2 — Entity map v2 và độ đủ của dữ liệu (2026-11-18) — EXECUTED (Dev), chưa certified

**Phạm vi:** Q1–Q3 đã được duyệt và ghi vào `decisions/decision_log.jsonl` (3 dòng, 2026-11-18).
S2 tạo `entity_map_v2` (ánh xạ id v1 → v2 hoặc BLOCK) và gói **v3.3 candidate** =
v3.2 + mapping. v3.1/v3.2 không đổi. Mapping ở trạng thái `PROPOSED_UNREVIEWED`.

### Nguyên tắc thiết kế (INV-02)
Mọi quy tắc chỉ phụ thuộc **chính chuỗi mention đó** (không phụ thuộc mention khác, không dùng thông
tin xuất hiện sau). Nhờ vậy id v2 là hàm thuần của khóa chuẩn, ổn định ở mọi snapshot và không cần
`mapping_available_at`. Liên kết cần hai mention đi cùng nhau (ví dụ AWS ↔ Amazon Web Services)
**không áp dụng**, chỉ đề xuất kèm thời điểm khả tri.

### Quy tắc áp dụng
1. Khóa chuẩn: NFC, chữ thường, gạch/gạch dưới → khoảng trắng, bỏ nháy, bỏ ngoặc cuối **không chứa chữ số**
   (giữ "(A05)", "(M3407GA)"); bỏ tiền tố {tập đoàn, công ty, hãng, ông, bà} nếu từ kế tiếp viết hoa/chữ
   số (ngoại lệ "Bà Rịa"); bỏ hậu tố pháp lý {Corporation, Inc, Ltd, LLC, PLC, Group, Co}.
2. Chặn (quarantine) mention chung chung: danh sách đại từ/danh từ lớp (ông, công ty, AI, chatbot, …) và mô tả
   toàn chữ thường ≥ 2 từ ("laptop mới", "người này").
3. id v2 = `ent2_` + sha256("entity_map_v2|"+khóa)[:8].
4. Sự kiện chứa entity bị chặn → quarantine `GENERIC_ENTITY_BLOCKED`; trùng bộ ba sau gộp → gộp sự kiện
   (thời điểm sớm nhất); khuyên tự nối sau gộp → quarantine (thực tế: 0).

### Kết quả
| | v3.2 | v3.3 candidate |
|---|---|---|
| entity (v1 → v2) | 1.389 | 1.334 (22 bị chặn, 33 gộp, 32 nhóm) |
| triple T01 / T05 / T10 | 117 / 580 / 1.160 | 113 / 549 / 1.098 |
| entity ở T10 | 1.343 | 1.286 |
| thành phần lớn nhất T10 | 522 | 447 |
| đường 2-hop / 3-hop ở T10 | 1.589 / 1.851 | 1.467 / 1.611 |
| tỷ lệ bậc ≤ 2 | 0,88–0,91 | 0,89–0,91 |

Chặn entity chung chung **giảm liên thông giả** (hub "ông" bậc 17, "công ty" bậc 9 từng nối các cụm
không liên quan). Gộp alias chỉ giảm 3% số entity: **không khắc phục được độ thưa**.

Chặn (22): Hãng, học viện, mẫu robot mới, Tính năng, đèn giao thông, AI, chatbot, công ty, máy tính lượng
tử ion, Sản phẩm, Mô hình, người này, tính năng chỉnh sửa video, tính năng giám sát trẻ, trợ lý ảo, chuông cửa,
hai công ty công nghệ quốc phòng, kho dữ liệu dùng chung, laptop mới, nền tảng điều khiển robot bằng ý nghĩ,
ông, loạt trợ năng mới. Chi tiết 32 nhóm gộp: `data/entity_map_v2/mapping_report.json`.

### Đề xuất chờ duyệt, KHÔNG áp dụng (`data/entity_map_v2/review_proposals.csv`)
| Loại | Số | Nhận xét |
|---|---|---|
| acronym_alias (AWS, KAIST, PTIT, USTC, EPFL, CXMT, UTS, NIC, Vinasa) | 10 | Liên kết thật nhưng cần thiết kế as-of: 2/10 có viết tắt xuất hiện *trước* khi liên kết khả tri → entity đổi id giữa các snapshot |
| corporate_suffix (Samsung Electronics/Samsung, LG Electronics/LG, Loongson Technology/Loongson, Walden International/Walden) | 4 | Mơ hồ công ty mẹ/con |
| code_in_parenthesis (Bộ Công an (A05), Vivobook S14 (M3407GA), Zenbook 14 (UM3406GA)) | 3 | Giữ tách (đơn vị con / mã model) |
| near_duplicate_key | 12 | **Không an toàn tự động**: gộp nhầm Alpha 7 IV/V, ZenBook 14 2025/2026, Nguyễn Mạnh Cường/Tường; chỉ đúng với "Helion Enegy", "AI Overview(s)", Berkeley |
| lowercase_start_not_blocked | 88 | Phần lớn là thương hiệu (xAI, iPhone, iOS, macOS, o1) |

### Xác thực (mỗi mục đã chạy)
| Kiểm | Kết quả |
|---|---|
| Unit test quy tắc (`tests/test_entity_map_v2.py`) | 38 pass, gồm ca không được gộp: Bà Rịa, Ngân hàng Nhà nước, Bộ Công an (A05) |
| Toàn repo: ruff / pytest | sạch / 702 pass, 1 fail (cũ), 10 skip |
| Verifier độc lập cho v3.3 (dựng lại bộ ba đã ánh xạ từ v3.1, kiểm bảng mapping theo quy tắc) | PASS |
| Giả mạo bảng mapping | verifier FAIL gọn, 4 tín hiệu (lần đầu sập traceback → đã sửa dùng `.get`) |
| Dựng v3.3 hai lần | 14 Parquet + YAML trùng từng byte |
| Tương thích ngược: dựng lại v3.2 bằng code mới | 14 Parquet trùng từng byte với bản cũ (YAML chỉ khác nhãn `run_id`, `entity_map_version`) |
| Nạp bằng bộ nạp M2, snapshot lồng nhau, 0 khuyên tự nối, INV-01 | PASS |

### Gate trượt — cần quyết định
**Gate quarantine ≤ 5% (ngưỡng ứng viên, chưa đăng ký) = FAIL ở v3.3: 85/1.205 sự kiện (7,1%)** =
45 thiếu thời gian bằng chứng (3,7%) + 40 chứa entity chung chung (3,3%); 22 sự kiện *gộp* không tính
là loại. Mình đã sửa phép đo (lần đầu đếm cả sự kiện gộp: 8,9%) nhưng **không đổi ngưỡng**.
v3.2 vẫn PASS (3,7%).

### F11 (mới) — HIGH: số anchor theo bucket bậc quá mỏng
Anchor bền vững (bucket bậc trước transition `<3 / 3–5 / ≥6`), v3.3:
T01→T02 151 (137/11/3); T03→T04 424 (384/30/10); T05→T06 691 (625/47/19); T09→T10 1.157 (1.028/101/28).
Bucket ≥ 6 không bao giờ vượt 28 anchor, bucket 3–5 chỉ vượt 50 từ T05→T06; 89–91% anchor có bậc < 3.
Hệ quả: null theo bucket (cần ≥ 50 quan sát tham chiếu sau LTO) không dựng được cho entity bậc cao;
chính sách gộp bucket thưa phải đăng ký trước, và kết luận về entity bậc cao sẽ rất yếu.
Panel QA khả thi (cohort theo snapshot, v3.3): 2-hop 4.183 và 3-hop 3.065 quan sát (query×transition);
với trần mỗi head = 3: 3.611 / 2.528. MDE **chưa tính** (cần phương sai kết quả, không được lấy từ kết quả cũ).

### Giới hạn
- Mapping chưa được người duyệt (danh sách chặn 22 và 32 nhóm gộp); tầng 3 chưa áp dụng.
- Quy tắc dựa vào chuỗi: không giải tham chiếu ngữ cảnh ("ông" là ai) — 40 sự kiện bị loại thay vì cứu.
- Chưa chạy `run_snapshot` production; M1/G1/G2 vẫn BLOCKED, entity chưa được chứng nhận.
- Danh sách chặn gồm vài mô tả mơ hồ ("trợ lý ảo", "đèn giao thông", "máy tính lượng tử ion") — người duyệt quyết định.

### Quyết định cần duyệt trước S3
- Q4: Duyệt (hoặc sửa) danh sách chặn 22 và 32 nhóm gộp ở trên?
- Q5: Gate quarantine: chấp nhận 7,1% (mỗi nguyên nhân đều theo quy tắc, mù kết quả) và đăng ký ngưỡng tổng/riêng, hay muốn giảm?
- Q6: Với F11, hướng nào: (a) giữ cả ba bucket và đăng ký chính sách gộp bucket; (b) giới hạn quần thể chính ở entity bậc ≥ 3; (c) bổ sung dữ liệu.

## 8. S3 — Huấn luyện backbone có kiểm định (2026-11-18) — DỪNG GIỮA CHỪNG: cổng hội tụ đăng ký bị lỗi thiết kế

**Đã làm:** Q4–Q6 ghi vào decision log (3 dòng). v3.3 dựng lại với gate quarantine theo từng nguyên nhân
(3,7% / 3,3%, đều ≤ 5%) — PASS. Đăng ký `configs/s3_backbone_v33.yaml` **trước khi chạy** (lưới, quy tắc chọn, cổng).
Code: `src/kge/validation.py` (folds không làm mồ côi entity, filtered MRR hai chiều, baseline tần suất,
bootstrap, plateau, Procrustes holdout) + 8 test; `scripts/s3_backbone.py` (`search`, `train`).
Toàn repo: ruff sạch; pytest 710 pass, 1 fail cũ, 10 skip (số liệu cuối phiên, xem dưới).

**Giai đoạn `search` (240 lần huấn luyện, 5 fold × 2 seed × 2 snapshot dev T05/T10 × 12 cấu hình):**
- Chọn theo quy tắc đăng ký: **d = 64, lr = 0,01, margin = 2,0**, MRR validation lọc 0,3495 (T05 0,394; T10 0,305).
  Ba cấu hình kế tiếp: (64; 0,05; 2,0) 0,348; (32; 0,05; 2,0) 0,343; (32; 0,01; 2,0) 0,338. margin 0,5 kém rõ (≤ 0,22).
- MRR bão hòa: 0,3015 (E=100) → 0,341 (200) → 0,3495 (300) → 0,3466 (400).
- **Quy tắc chọn số epoch KHÔNG thỏa ở mốc nào** (0/9 lần chạy qua cổng hội tụ, kể cả 400 epoch) → `train` bị từ chối
  đúng thiết kế. Artifact: `outputs/s3_backbone_v33/20261117T183704Z_a6a27177/search/`.

**Chẩn đoán (đã kiểm trên đường cong loss, 9 lần chạy T01/T05/T10 × 3 seed, 400 epoch):**
| Tiêu chí con | margin 2,0 (đã chọn) | margin 1,0 (xem thử, không áp dụng) |
|---|---|---|
| giảm loss ≥ 75% so với epoch đầu | 0/9 (loss chỉ còn 31–34% epoch đầu) | 9/9 |
| plateau (|Δ| hai khối 10 epoch ≤ max(1%, 0,002)) | 7/9 ở E=400 (T01 seed 13/101 trượt: 3,1% và 1,8%) | 6/9 ở E=400; không mốc nào đủ 9/9 |

Nguyên nhân gốc (lỗi của mình, không phải của dữ liệu): (1) entity chuẩn hóa độ dài 1 nên khoảng cách ≤ 2;
margin 2,0 không thể thỏa → sàn loss tự nhiên ≈ 0,65, trong khi ngưỡng 75% mình đặt từ thử nghiệm margin 1,0
(loss về 0,02). (2) Dung sai tuyệt đối 0,002 nhỏ hơn nhiễu SGD của trung bình loss mỗi epoch khi loss chỉ 0,01–0,02,
nhất là snapshot nhỏ (T01 có 113 triple). Hai khiếm khuyết cùng nằm trong gate mình đăng ký; không đổi ngưỡng để qua.

### Lựa chọn cần bạn duyệt (khuyến nghị: A)
- **A (khuyến nghị): sửa cổng, giữ nguyên kết quả chọn cấu hình.** Thay hai tiêu chí con bằng: (i) plateau có xét nhiễu:
  hiệu hai khối 20 epoch cuối ≤ 2 sai số chuẩn của hiệu; (ii) loss khối cuối ≤ 0,5 × loss epoch đầu (kiểm tra có học);
  điều kiện MRR validation ≥ 0,98 × tốt nhất giữ nguyên. Lý do: lỗi nằm ở gate chứ không ở lựa chọn; xóa margin 2,0
  chỉ vì nó làm gate trượt mới là chọn theo gate. Sửa **sau khi đã thấy kết quả**, nên ghi decision log và nói rõ là hậu nghiệm;
  mình sẽ chạy lại phần chọn epoch rồi báo cáo kết quả kể cả khi vẫn không đạt.
- **B:** loại margin > 1,0 (lý do cấu trúc), chọn lại (32; 0,05; 1,0; MRR 0,328, thấp hơn ~0,02), nhưng plateau vẫn cần sửa như A.
- **C:** dừng S3, xem lại thiết kế (ví dụ chuẩn hóa hoặc tối ưu hóa khác).

### Chưa làm
Giai đoạn `train` (10 snapshot × 3 seed), cổng chất lượng so baseline tần suất, nhiễu giữa seed, tái lập checkpoint.
Lưu ý trước: T01 chỉ có ~29 triple giữ lại cho validation nên khoảng tin cậy chất lượng sẽ rất rộng.

### 8.1 Phương án A đã chạy (2026-11-18) — gate v2 cũng KHÔNG đạt → kích hoạt điều kiện T1 của phương án C

Người dùng duyệt A và yêu cầu ghi chú C nếu có vấn đề. Đã ghi `decisions/decision_log.jsonl`
(`s3_convergence_gate_amendment_option_a_20261118`, nêu rõ **sửa hậu nghiệm**) cùng điều kiện kích hoạt C (T1–T4).
Gate v2 = plateau có xét nhiễu (hai khối 20 epoch, ≤ 2 SE) + kiểm tra có học (loss ≤ 0,5 × epoch đầu).
Chạy lại toàn bộ `search` (`outputs/s3_backbone_v33/20261117T185407Z_11ed1e11/search/`):

| E | MRR | MRR ≥ 0,98×tốt nhất | số lần qua gate v2 |
|---|---|---|---|
| 100 / 150 | 0,3015 / 0,3327 | không | 0/9 |
| 200 | 0,3410 | không | 1/9 |
| 300 | 0,3495 | có | 3/9 (T05, T10 còn giảm: 2,3–5,2 SE) |
| 400 | 0,3466 | có | **8/9** (chỉ T05 seed 37 trượt: 3,1 SE) |

- Tái lập: điểm MRR và đường cong loss **giống hệt** lần chạy trước (huấn luyện xác định).
- Lần này gate hoạt động đúng ý: "learned" đạt 9/9; chỉ "plateau" trượt vì loss còn giảm ~1% mỗi 20 epoch.
  Vậy cấu hình đã chọn (lr = 0,01) hội tụ chậm hơn ngân sách đăng ký (Emax = 400), không còn là lỗi thước đo.
- Quan sát: (64; 0,05; 2,0) hòa với cấu hình được chọn (MRR 0,348 vs 0,3495) và đạt đỉnh sớm (epoch 100);
  quy tắc hòa của mình ("lr nhỏ hơn") đã chọn đúng cấu hình hội tụ chậm. Đây là khiếm khuyết thứ ba trong thiết kế đăng ký.
- **T1 kích hoạt** (gate v2 không đạt ở mọi mốc ≤ 400). S3 dừng; `train` chưa chạy. T2–T4 chưa đánh giá.

### 8.2 Phương án C — đề xuất có thứ tự (chưa chạy, cần duyệt)
Giữ nguyên: dữ liệu v3.3, entity map v2, các cổng chất lượng/ổn định/tái lập, nguyên tắc không dùng kết quả hạ nguồn.
1. **C1 (rẻ nhất, vài phút):** thêm "hội tụ trong ngân sách" vào quy tắc chọn: trong nhóm cấu hình hòa (≤ 0,005 MRR)
   chọn cấu hình đạt gate v2 ở E nhỏ nhất, thay vì lr nhỏ nhất. Thực tế = đánh giá (64; 0,05; 2,0). Đây là lần sửa hậu nghiệm thứ hai.
2. **C2:** nếu C1 vẫn không đạt, đổi quy tắc chọn epoch sang **độ ổn định giữa seed theo epoch** (khoảng cách Procrustes holdout):
   dừng khi mức nhiễu không còn giảm — gắn với mục đích đo drift hơn là hình dạng loss.
3. **C3:** nếu vẫn không đạt, tối ưu hóa mini-batch/Adam (lớp mô hình mới, không sửa `src/kge/model.py`), margin/chuẩn hóa, Bernoulli negatives;
   đăng ký lại lưới và cổng **trước** khi chạy.
Rủi ro cần minh bạch: mỗi lần sửa hậu nghiệm làm tăng bậc tự do của người phân tích. Kế hoạch: đăng ký trọn bộ C1–C3 và quy tắc dừng trước khi chạy,
và báo cáo mọi biến thể đã thử (gate v1, gate v2, xem thử margin ≤ 1,0).

### 8.3 Phương án C đã chạy theo đăng ký trước (2026-11-18) — C1, C2, C3 đều KHÔNG chọn được → S3 DỪNG (quy tắc dừng)

Đăng ký trước khi chạy: `configs/s3_backbone_v33.yaml` mục `contingency_c` (hash `a5db1837…`) và decision
`s3_contingency_c_preregistration_20261118`. Nhóm hòa (≤ 0,005): (64; 0,01; 2,0) và (64; 0,05; 2,0).

| Bước | Kết quả | Chi tiết |
|---|---|---|
| C1 (gate v2, chọn E nhỏ nhất trong nhóm hòa) | không chọn | lr 0,05: MRR đỉnh ở E=100 (0,348) rồi **giảm** (0,314 ở 400); gate v2 đạt 9/9 ở E=200 nhưng khi đó MRR < 0,98 × đỉnh. lr 0,01: như §8.1 |
| C2 (ổn định giữa seed, dung sai 0,01) | không chọn | lr 0,01: nhiễu vẫn giảm đều tới 500 (T10 0,484 → 0,458 → 0,447). lr 0,05: nhiễu dao động ±0,02 (T10 0,396 → 0,403 → 0,382) |
| C3 (mini-batch Adam, 16 cấu hình, 320 lần tìm kiếm) | không chọn | MRR tốt nhất **0,330** (< SGD 0,3495); nhiễu giữa seed **cao hơn** (T05 0,52–0,67); nhóm hòa 4 cấu hình margin 2,0 |

Artifact: `outputs/s3_backbone_v33/20261117T191103Z_dea923f8/` (C1), `…20261117T191159Z_5de85915/` (C2),
`…20261117T192353Z_d6cb1436/` (C3). Bước `train` không chạy ở bất kỳ nhánh nào.

**Cài đặt C3 qua Codex CLI** (theo đề nghị người dùng): Codex chỉ tạo `src/kge/minibatch.py` và `tests/test_kge_minibatch.py`
(đã đối chiếu `git status`), nhưng không chạy được test trong sandbox. Mình soát lại: đạo hàm, lọc negative, Bernoulli,
tính tất định đúng; phát hiện **lỗi do spec của mình**: Adam dense dịch chuyển cả hàng không có trong batch nhưng chỉ
chuẩn hóa hàng trong batch → entity rời mặt cầu đơn vị. Đã sửa (chiếu toàn bộ entity) và thêm test nhiều batch; đã chứng minh test
này fail trên code cũ. Nhánh SGD gốc cho kết quả giống hệt trước khi tích hợp.

### 8.4 Phân tích tổng hợp sau S3 (để người dùng quyết định)
1. **Nhiễu giữa seed cao bất kể bộ tối ưu**: T05/T10 ≈ 0,44–0,67 (mốc ngẫu nhiên ≈ 0,75); T01 thấp hơn (0,17–0,52)
   một phần vì Procrustes với ít anchor so với 64 chiều "khớp" luôn nhiễu (F7). Nguyên nhân chủ yếu là dữ liệu: 89–91% entity
   bậc ≤ 2 chỉ bị một hai triple ràng buộc (F3/F11). Đổi bộ tối ưu không sửa được điều này (C3 còn tệ hơn).
2. **"Hội tụ" theo ngưỡng không phải câu hỏi đúng**: cả bốn ngưỡng mình đặt (75%, 0,002, 0,01 và sàn của gate v2) đều không được
   hiệu chỉnh theo nhiễu của chính phép đo. Thiết kế nghiên cứu đã có cơ chế đúng cho nhiễu tối ưu hóa: **null cùng snapshot**
   (S5) đo đúng nhiễu đó ở cùng cấu hình/epoch, và **đối chứng dương** (S6) kiểm xem drift có còn phát hiện được không.
3. **Đề xuất R1 (khuyến nghị):** khai báo **ngân sách huấn luyện cố định** thay cho cổng hội tụ: cấu hình được chọn ban đầu
   theo quy tắc đăng ký (SGD gốc, d=64, lr=0,01, margin=2,0), E = 400 (mốc lớn nhất đã đăng ký; MRR 0,3466 = 99% đỉnh; gate v2
   8/9; nhiễu còn giảm ≤ 0,026/100 epoch), hội tụ chỉ báo cáo; **phân tích độ nhạy E ∈ {300, 400, 500}** ở S5–S9 (kết luận không
   được phụ thuộc E). Đây là lần sửa hậu nghiệm thứ ba — phải ghi rõ, kèm danh sách mọi biến thể đã thử.
   - R2 (không khuyến nghị): hiệu chỉnh dung sai bằng bootstrap rồi chạy lại C2 — tiếp tục tinh chỉnh cổng sau khi thấy kết quả.
   - R3: dừng M2, xem lại phạm vi nghiên cứu (dữ liệu quá thưa) hoặc bổ sung dữ liệu trước khi đo drift.

## 9. R1 train, S4–S6 (2026-11-18) — EXECUTED (Dev), chưa certified. Kết quả: phép đo KHÔNG phát hiện được drift ở mức cá nhân; H1 = NOT_TESTABLE theo quy tắc đã đăng ký

Decision log: `s3_r1_fixed_training_budget_20261118`, `s5_s6_drift_measurement_preregistration_20261118`.
Đăng ký trước khi đo: `configs/s5_drift_v33.yaml` (hash `489a0d99…`); không có số drift/null nào được tính trên v3.3 trước đó.

### 9.1 Train (R1: SGD, d=64, lr=0,01, margin=2,0, E=400, 10 snapshot × 3 seed) — cổng ràng buộc PASS
| Cổng | Kết quả |
|---|---|
| Chất lượng: cận dưới CI95 của MRR lọc > baseline tần suất | PASS 10/10. MRR 0,306–0,440 so với baseline 0,091–0,130 (random 0,004–0,037). T01 chỉ 29 triple giữ lại: CI [0,174; 0,448] |
| Ổn định giữa seed (median 1−cos holdout, mốc ngẫu nhiên ≈ 1,0) | PASS mọi bucket đủ ≥ 10 anchor: bậc < 3: 0,21–0,55; bậc 3–5: 0,17–0,33; bậc ≥ 6: 0,12–0,15 (chỉ đủ anchor ở T07, T09) |
| Tái lập checkpoint | PASS (artifact_hash trùng) |
| Hội tụ (chẩn đoán, không chặn) | 24/30 lần qua gate v2 |
Cảnh báo: **98–100% triple luôn vi phạm margin** (margin 2,0 không thể thỏa với entity chuẩn hóa) — mô hình vẫn xếp hạng tốt nên không chặn.

### 9.2 S4 căn chỉnh chéo — 243 kiểm tra fold, 4 trượt (hạng số, chỉ ở E=500: 151 entity không khả dụng); chênh lệch fit–holdout trung vị 0,085 (ngưỡng 0,65). Embedding dựng lại khớp checkpoint S3 (sai khác 0,0).

### 9.3 S5–S6 phép đo (9 transition, 6.040 quan sát entity×transition; E = 300 / 400 / 500)
| | E=300 | E=400 | E=500 |
|---|---|---|---|
| Drift: tỷ lệ excess > 0 | 0,503 | 0,509 | 0,509 |
| Drift: tỷ lệ SED⁺ ≥ 2 | 0,8% | 1,1% | 1,5% |
| **Đối chứng âm** (drift giả = 0): excess > 0 / SED⁺ ≥ 2 | 0,517 / 1,0% | 0,518 / 1,1% | 0,517 / 1,4% |
→ Ở mức quần thể, **drift không khác đối chứng âm** (đạt kỳ vọng đăng ký: 0,40–0,60 và ≤ 10%) ở cả ba E.

**Đối chứng dương (drift bơm có chủ đích: viết lại cạnh của 10% entity mỗi bucket), quy tắc đăng ký "độ nhạy ≥ 0,50 và FPR ≤ 0,10 ở strength 1,0":
KHÔNG ĐẠT ở cả E = 300 / 400 / 500** (độ nhạy gộp 0,10–0,15 ở strength 1,0; FPR 0,1–1,3%).
Theo bucket (thăm dò, KHÔNG đăng ký, n nhỏ, gộp 2 transition, E=400):
| Nhóm | n bơm | độ nhạy @0,5 | độ nhạy @1,0 | FPR |
|---|---|---|---|---|
| bậc < 3 | 166 | 0,04 | **0,01** | ~0 |
| bậc ≥ 3 | 21 | 0,48 | 0,95 | 5–6% (E=500: 10–14%) |
Giá trị trung bình của drift bơm vào có thấy được (excess +0,31…+0,39 so với ~0 ở nhóm sạch; SED⁺ trung vị 1,1–1,3 so với 0,2),
nhưng với entity bậc < 3 (90% quần thể) nhiễu giữa seed lấn át tín hiệu từng entity.

### 9.4 Ý nghĩa cho nghiên cứu
1. **H1 theo định nghĩa đăng ký (SED⁺ per query) = NOT_TESTABLE trên dữ liệu này**: biến phơi nhiễu gần như toàn 0 (≈ 99% entity SED⁺ < 2) và hai
   phân phối drift/đối chứng âm trùng nhau; một kết quả null của H1 sẽ không mang thông tin. Kết luận này vững theo E (không đổi ở 300/400/500).
2. **Nhóm bậc ≥ 3 có tín hiệu phát hiện được trong thăm dò** (độ nhạy ~0,95 với drift cực đoan 100% cạnh), nhưng chỉ 21 entity bơm, FPR sát ngưỡng khi E=500,
   và quần thể nhóm này nhỏ (14–129 entity mỗi transition). Đây là giả thuyết, chưa phải kết quả: cần đăng ký tiêu chí phát hiện riêng rồi tăng cỡ mẫu bơm.
3. **Khiếm khuyết thiết kế phát hiện (đã đăng ký, không sửa):** bucket ≥ 6 có 3–28 entity mỗi transition (< 51) nên bị gộp vào bucket kề; entity bậc cao có nhiễu thấp
   (δ trung vị 0,116) bị so với null của nhóm nhiễu hơn (0,227) → excess âm (chỉ 18,8% > 0) → SED⁺ luôn ≈ 0 với entity bậc cao *tự nhiên*, dù bơm vẫn phát hiện được.
   Đây chính là rủi ro đã nêu ở decision Q6.
4. Drift bơm là cực đoan (thay toàn bộ lân cận); drift thật có thể yếu hơn → độ nhạy thật thấp hơn các con số trên.

### 9.5 Giới hạn
Đối chứng dương chỉ gồm 2 transition (T05→T06, T09→T10) và 1 cách bơm; null và δ dùng cùng seed nên chưa độc lập hoàn toàn; hội tụ chưa đạt (nhiễu còn giảm ≤ 0,026/100 epoch);
phân tích theo bucket là thăm dò; MDE chưa tính. Chưa chạy S7 (bộ QA), S8 (Arm A/B), S9 (TWFE) — kết quả S6 là điều kiện để quyết định có nên chạy tiếp.
Artifact: `outputs/s5_drift_v33/20261117T195720Z_d5692c54/` (bảng entity-level theo E, báo cáo, manifest), `outputs/s3_backbone_v33/*_r1/train/` (30 checkpoint).

### 9.6 Lựa chọn tiếp theo (cần người dùng quyết định)
- **N1 (khuyến nghị): đăng ký phân tích nhóm bậc ≥ 3 làm quần thể chính cho H1**, kèm tiêu chí phát hiện riêng và cỡ mẫu bơm lớn hơn (nhiều transition, nhiều strength thấp hơn), rồi mới chạy S7–S9 trên nhóm này; báo cáo rõ phạm vi (≈ 10% entity).
- **N2:** chạy S7–S9 trên toàn bộ như thiết kế gốc nhưng gắn nhãn H1 = NOT_TESTABLE, chỉ báo cáo mô tả (kết quả chủ yếu là kết luận phương pháp: nhiễu lấn át drift).
- **N3:** dừng đo drift, bổ sung dữ liệu (cần thêm nhiều triple trên cùng entity để nâng bậc) trước khi tiếp tục.

## 10. N1 — H1 trên nhóm bậc ≥ 3 (2026-11-18) — EXECUTED (Dev), chưa certified. Kết quả: **H1 = NOT_TESTABLE theo quy tắc đã đăng ký**

Đăng ký trước: `configs/n1_h1_deg3_v33.yaml` (hash `bf754250…`) + decision `n1_h1_degree3_stratum_preregistration_20261118`.
Tiết lộ trước khi đăng ký: kết quả S6 (quần thể), số entity bậc ≥ 3 mỗi transition và 330 + 217 quan sát đủ hỗ trợ; `support_minimum` hạ 50 → 30 **sau khi thấy số đếm**
(giữ được 7 transition: T03→T04 … T09→T10). Không có số drift/RR/H1 nào của N1 được tính trước đăng ký.
Phân công: Codex viết `src/evaluation/n1_panel.py` và 2 file test (đã soát logic, chạy test, 36 pass gồm hiệu chuẩn mô phỏng của bộ ước lượng); phần còn lại do mình viết.

### 10.1 Drift nhóm bậc ≥ 3 và đối chứng dương (626 entity×transition; 582 khả dụng)
| | E=300 | E=400 | E=500 |
|---|---|---|---|
| drift: excess>0 / SED⁺≥2 | 0,522 / 2,7% | 0,545 / 6,2% | 0,540 / 11,0% |
| đối chứng âm (pseudo): excess>0 / SED⁺≥2 | 0,505 / 2,7% | 0,502 / 5,8% | 0,500 / 10,3% |
| độ nhạy @0,25 / @0,5 / @1,0 (n = 149 mỗi mức) | 0,15 / 0,36 / **0,81** | 0,25 / 0,52 / **0,99** | 0,37 / 0,57 / **0,99** |
| dương tính giả @1,0 | 0,043 | 0,090 | **0,170** |
| `testable_large` (độ nhạy@1,0 ≥ 0,80 và FPR ≤ 0,10) | **đạt** | **đạt** | **KHÔNG** |
| `testable_moderate` (độ nhạy@0,5 ≥ 0,50 và FPR ≤ 0,10) | không | đạt | không |
→ So với S6 (quần thể, độ nhạy 0,10–0,15), nhóm bậc ≥ 3 **phát hiện được drift mạnh** (thay toàn bộ lân cận) ở E=300–400, nhưng chỉ drift vừa (50% cạnh) ở E=400.
Dương tính giả **tăng theo E** (cả ở đối chứng âm: 2,7% → 5,8% → 10,3%, so với ≈ 2,3% danh nghĩa): mức hiệu chuẩn của SED⁺ ≥ 2 trôi khi huấn luyện lâu hơn.
Nguyên nhân khả dĩ (giả thuyết, chưa kiểm): δ_time là trung vị 3 seed còn null là trung vị 6 quan sát → δ phân tán hơn null ngay cả khi drift = 0; null mỗi bucket chỉ 30–128 entity.

### 10.2 Bộ câu hỏi (S7) và kết quả (S8)
590 dòng (query×transition), 259 query khác nhau; 502 dòng / 225 query sau trần 3 mỗi head; 2-hop 329, 3-hop 261.
Phân bố rất lệch: T09→T10 có 259 dòng, T03→T04 chỉ 1, T04→T05 9. Quan sát có thông tin cho hồi quy (query xuất hiện ≥ 2 lần): **404 dòng, 127 query, 7 cụm**.
RR_B trung bình 0,088–0,098 (thấp). Mẫu 35 câu tiếng Việt (`h1/questions_review_sample.csv`): 0 lỗi mẫu câu; **cần người duyệt tay** về nghĩa quan hệ — xem câu đầu: bộ đáp án "Apple" cho
"Đối tác chiến lược của … NIC" nghe không hợp lý, tức dữ liệu/quan hệ nguồn có thể sai ngữ nghĩa (độ chính xác trích xuất chưa được chứng nhận).

### 10.3 H1 (S9): RR_B ~ β·(trung vị SED⁺ của support) + FE query + FE transition; bootstrap cụm Webb 9999 lần
| E | β | SE | p (WCB) | MDE₈₀ | falsification (pseudo): β / p |
|---|---|---|---|---|---|
| 300 | +0,025 | 0,167 | 0,858 | 0,47 | +0,489 / 0,067 |
| 400 | −0,242 | 0,129 | 0,132 | 0,36 | +0,196 / 0,372 |
| 500 | −0,329 | 0,205 | 0,062 | 0,57 | −0,089 / 0,483 |
- **Không có kết luận E-robust**: dấu và lớp (p<0,05) không nhất quán ở ba mức E (quy tắc đăng ký) → H1_status = **NOT_TESTABLE** (cũng do đối chứng dương trượt ở E=500).
- Hệ số thiên về âm (drift cao → RR thấp) ở E=400/500 nhưng khoảng tin cậy rộng, chứa 0 và cả các giá trị rất âm. Độ lệch chuẩn của biến phơi nhiễu chỉ 0,03–0,11;
  MDE₈₀ = 0,36–0,57 RR cho mỗi đơn vị SED⁺ (RR trung bình 0,09): **dữ liệu chỉ phát hiện được hiệu ứng rất lớn**; một kết quả null không loại trừ hiệu ứng nhỏ-vừa.
- Falsification (pseudo drift): E=300 β = +0,49 với p = 0,067 (sát ngưỡng) → ở E này biến phơi nhiễu giả cũng "gần có ý nghĩa", cảnh báo về hiệu chuẩn.
- Phân tích phụ (KHÔNG đăng ký là kết luận, 24 mô hình, nhiều so sánh): biến phơi nhiễu **signed excess** có β âm ở cả 3 E với p_WCB = 0,049 / 0,050 / 0,016. Không báo cáo là phát hiện:
  (i) p sát 0,05 trong nhiều thử nghiệm; (ii) falsification chỉ được chạy cho biến phơi nhiễu chính, chưa cho signed excess; (iii) signed excess có thể phản ánh **nhiễu biểu diễn riêng của entity**
  (entity kém ổn định có cả δ lớn lẫn RR thấp) thay vì drift thật. Đây chỉ là giả thuyết cho nghiên cứu sau.
- Biến kiểm soát (log bậc hậu transition) không đổi kết luận; hop 2/3, không trần head và leave-one-transition-out: xem `h1/n1_h1_report.json`.

### 10.4 Ý nghĩa tổng hợp và giới hạn
1. Chuỗi bằng chứng nhất quán: **trên KG này (≈ 120 sự kiện mỗi snapshot, 89–91% entity bậc ≤ 2) phép đo drift chỉ có độ nhạy với thay đổi lớn ở nhóm bậc ≥ 3 và gần như mù ở nhóm bậc < 3**; H1 không thể kiểm định.
2. Kết quả cũ (β_d = −0,0037, p = 0,574, báo cáo LaTeX ngày 28/10) **nên bị thay thế/đánh dấu không dùng được**: trục thời gian sai, embedding chưa huấn luyện kỹ, nhóm bậc thấp chiếm ưu thế.
3. Kết luận có thể bảo vệ: (a) quy trình sửa dữ liệu và chuỗi kiểm định đã xây; (b) **bằng chứng định lượng rằng nhiễu huấn luyện lấn át drift biểu diễn** trên KG thưa cỡ này; (c) MDE và điều kiện dữ liệu cần để kiểm định H1.
4. Giới hạn: một cách bơm drift (viết lại cạnh), 7 transition, panel lệch về T09→T10, phân bố null mỗi nhóm nhỏ, hội tụ chưa đạt, entity chưa được chứng nhận, độ chính xác trích xuất chưa kiểm (ví dụ câu mẫu "NIC–Apple"), H2/Arm A/OOV và H3a chưa chạy.
Artifact: `outputs/n1_h1_v33/20261117T201007Z_19ea4bcf/` (bảng entity-level theo E, embedding, báo cáo drift, `h1/` gồm panel, ước lượng, câu hỏi mẫu, manifest).

## 11. K1 — Viết kết quả thành kết luận phương pháp, cập nhật báo cáo LaTeX (2026-11-18)

Người dùng chọn K1: dừng đo, viết kết quả như kết luận phương pháp, đánh dấu kết quả cũ không dùng được.
- **Bảng và hình sinh tự động từ artifact:** `scripts/make_report_assets.py` (Codex viết theo spec, mình chạy và soát hình/bảng) đọc 5 tệp JSON kết quả và sinh
  8 bảng `reports/report_latex_final/generated/*.tex` + 4 hình `figures/fig_*.png`; nguồn và SHA-256 ở `generated/SOURCES.txt`. Không có số nào trong bảng được chép tay.
- **Viết lại:** tóm tắt (`main.tex`), chương 4 (kết quả), chương 5 (thảo luận: vì sao H1 không kiểm định được, lý do thiết kế từng bước, mối đe dọa tính hợp lệ,
  điều được và không được khẳng định), chương 6 (kết luận). **Sửa** chương 1 (đóng góp C2/C3, mô tả mô hình — bản cũ ghi sai "Adam, 50 epoch, margin 1,0",
  snapshot, ghi chú RQ3 chưa trả lời), chương 2 (gỡ 3 hình kết quả cũ, sửa câu khẳng định quá mức về kiểm định giả), chương 3 (M2/M4, giai đoạn 4/6/8/9).
- **Kết quả cũ:** hình cũ chuyển vào `figures/superseded_20261028/` (kèm README); PDF cũ đổi tên `main_SUPERSEDED_20261028.pdf`.
- **Kiểm tra:** máy không có trình biên dịch LaTeX nên **PDF mới chưa được biên dịch**. Đã chạy kiểm tra tĩnh (môi trường, ngoặc, tệp `\input`/hình,
  `\ref`/nhãn, khóa trích dẫn): không lỗi. matplotlib 3.10.9 được cài vào `.venv` chỉ để vẽ hình (không thuộc `requirements.lock.txt`).
