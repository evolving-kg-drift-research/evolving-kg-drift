# Khung chuẩn: xây dựng bộ dữ liệu KG tiến hóa và đo độ trôi biểu diễn

| | |
|---|---|
| Phiên bản | v1.1-draft (2026-11-22). Đã sửa theo review cùng ngày; xem "Lịch sử sửa đổi" ở cuối tài liệu |
| Trạng thái | `DRAFT_PROPOSED`: đề xuất, **chưa có hiệu lực** |
| Thứ bậc tài liệu (AGENTS.md §2.1) | Dưới `configs/protocol_v1.yaml` và `data/manifests/sources.lock.json`. Khi mâu thuẫn, protocol và các config đã đăng ký thắng cho tới khi có amendment. |
| Điều kiện hiệu lực | Mỗi mục chỉ có hiệu lực sau khi người dùng duyệt và ghi vào `decisions/decision_log.jsonl`. Mục gắn [AM] cần thêm amendment. |
| Công bố (INV-06) | Viết **sau** khi đã biết N1 (H1 = NOT_TESTABLE trên v3.3). Mọi tiêu chí chỉ dựa trên cấu trúc dữ liệu, chất lượng trích xuất và độ nhạy của phép đo. Không tiêu chí nào dùng độ lớn drift, RR, MRR hay hệ số H1 của bất kỳ bộ dữ liệu nào. |
| Phạm vi | Dựng một bộ dữ liệu KG tiến hóa mới (gọi tạm là **v4**) và quy trình đo độ trôi trên bộ đó. Dùng được cho bộ tự trích từ tin tức (nhánh A) và bộ dày có sẵn (nhánh C), xem Phụ lục D. |
| Tài liệu đi kèm | Review: [docs/audit/FRAMEWORK_v1_REVIEW_20261122.md](audit/FRAMEWORK_v1_REVIEW_20261122.md) · Bàn giao: [docs/HANDOFF_20261122_DATASET_REDESIGN.md](HANDOFF_20261122_DATASET_REDESIGN.md) |

## Tóm tắt một trang

Một bộ dữ liệu KG tiến hóa chỉ dùng được để đo độ trôi khi đạt đồng thời bảy điều:

1. **Đủ dày.** Các thực thể được đo phải có đủ cạnh để vị trí embedding ổn định giữa các seed. v3.3 có bậc trung bình 1,7. Các bộ chuẩn có bậc 4,5–43. NELL165 là một bộ trích từ văn bản, vừa thưa (bậc 3) vừa nhiễu (precision 0,35); trên bộ này embedding còn thua cả mốc cơ bản.
2. **Thật sự thay đổi.** Mỗi transition phải có đủ thực thể cũ được thêm cạnh. Ở v3.3, tối đa 8% anchor có cạnh mới ở T09→T10.
3. **Đúng thời gian.** Thời điểm bằng chứng là ngày công bố có thể kiểm chứng, không bao giờ là ngày crawl. Không dùng bằng chứng hay ánh xạ thực thể từ tương lai.
4. **Đúng nội dung.** Precision và recall của trích xuất được con người đo trên gold. Thực thể được gộp đúng. Quan hệ đúng chiều, đúng loại, không có đường tắt.
5. **Đo được.** Phép đo đạt đối chứng âm (không báo nhầm) và đối chứng dương (thấy thay đổi biết trước, giống cách dữ liệu thật thay đổi), xét theo từng nhóm bậc.
6. **Đủ sức mạnh thống kê.** MDE₈₀ đạt mục tiêu. Có đủ transition và câu hỏi, phân bố cân bằng, đáp án không dồn vào vài thực thể lớn.
7. **Tái lập và mù kết quả.** Mọi ngưỡng được đăng ký trước. Mọi artifact có manifest và hash. Không quyết định nào dựa trên kết quả drift hay QA.

Thứ tự làm việc (mục 2): thiết kế → **pilot trên kho bài đã có** → **mô phỏng** → **cổng đầu tư** → dựng dữ liệu → **cổng cấu trúc đồ thị** → huấn luyện và đo → **hiệu chuẩn** → mới đến thống kê.

---

## 0. Cách đọc

**Nhãn nguồn gốc của mỗi ngưỡng**

| Nhãn | Nghĩa |
|---|---|
| **[ĐK]** | Đã đăng ký hoặc đã duyệt trong repo (có ghi tên file). Giữ nguyên. |
| **[ĐX]** | Đề xuất mới, chờ người dùng duyệt. |
| **[MP]** | Giá trị phải lấy từ mô phỏng ở G1, trước khi dựng dữ liệu. |
| **[TL]** | Mốc tham chiếu từ tài liệu. Chỉ để so sánh, không phải ngưỡng. |
| **[AM]** | Đụng tới `protocol_v1.yaml`, `sources.lock.json` hoặc một quyết định đã ghi, nên cần amendment hoặc quyết định mới trước khi áp dụng. |

**Khi một mục có cả [ĐK] và [ĐX]**, giá trị [ĐK] có hiệu lực cho tới khi được thay bằng một quyết định mới. Ví dụ ở NC1: ngưỡng hiện hành là ≤ 0,10 [ĐK], còn ≤ 0,05 chỉ là mục tiêu [ĐX].

**Mức ưu tiên** (Phụ lục B): **BB** bắt buộc · **N** nên làm · **TC** tùy chọn.

**Bảng mã**

| Mã | Nghĩa |
|---|---|
| G0–G19 (G6a, G6b) | Các giai đoạn của khung |
| F1–F13, L01–L28 | Lỗi đã gặp ở v3.1–v3.3 (trong kế hoạch và file bàn giao) |
| R01–R36 | Rủi ro (Phụ lục A) |
| A1, A1b, A2–A8 | Chỉ số của cổng cấu trúc đồ thị (G12) |
| NC, PC, DC | Đối chứng âm, đối chứng dương, kịch bản gây nhiễu (G16) |
| RV-01–RV-28 | Phát hiện của review |
| S1–S6, N1, X1, R1 | Các bước và đăng ký đã chạy ở v3.2–v3.3 |

**Khuôn của mỗi giai đoạn G0–G19:** Mục tiêu → Các bước → Cổng ra → Lưu ý → Sự cố thường gặp → Sản phẩm.

**Mã lỗi.** Mã Fxx và Lxx trỏ tới lỗi đã gặp ở v3.1–v3.3, ghi trong `docs/RESEARCH_REEXECUTION_PLAN_20261117.md` §1, §6–§12 và tổng hợp trong file bàn giao. Mã Rxx thuộc sổ rủi ro ở Phụ lục A.

**Mức xác nhận** (AGENTS.md §5.1): IMPLEMENTED → TESTED → EXECUTED → VERIFIED. Test fixture pass, exit code 0 hay CI xanh **không bao giờ** đồng nghĩa với cổng khoa học PASS.

---

## 1. Mười hai chuẩn mực cốt lõi

1. **Thiết kế ngược từ khả năng đo.** Trước khi thu thập, chứng minh bằng mô phỏng rằng bộ dữ liệu dự kiến đủ để phát hiện hiệu ứng nhỏ nhất đáng quan tâm. v3.3 chỉ phát hiện được hiệu ứng rất lớn (MDE₈₀ = 0,36–0,57 RR trong khi RR trung bình là 0,09). Nếu biết điều này từ trước thì đã tránh được cả một vòng làm lại.
2. **Đăng ký trước, đo sau.** Ngưỡng, quần thể, thước đo chính và quy tắc rẽ nhánh phải được khóa (hash và decision log) trước khi chạm vào dữ liệu kết quả.
3. **Mù kết quả (INV-06).** Drift, RR, MRR, kết quả QA và hệ số H1 không bao giờ được dùng để chọn nguồn, bài, thực thể, anchor, mốc thời gian, bucket hay ngưỡng.
4. **Ba trục thời gian không thay thế cho nhau.** Đó là hiệu lực thế giới (`valid_from`, `valid_to`), quan sát bằng chứng (`evidence_observed_at`) và thu thập (`retrieved_at_real`, `ingested_at_real`). Thời điểm crawl không bao giờ được dùng làm thời điểm bằng chứng.
5. **Không có bằng chứng và ánh xạ tương lai (INV-01, INV-02).** Mọi fact và mọi quy tắc gộp thực thể trong snapshot T phải có sẵn tại cutoff của T.
6. **Chỉ thêm, không sửa (INV-03).** Dữ liệu thô, bản ghi tải về và kho FactVersion chỉ được thêm vào. Dựng lại thì tạo phiên bản mới, giữ nguyên bản cũ và ghi quan hệ thay thế.
7. **Tái lập từng byte (INV-04).** Cùng đầu vào, cấu hình và phiên bản thành phần phải cho cùng SHA-256. Mỗi artifact có manifest ghi `git_commit`, `dirty_state`, `config_hash`, hash đầu vào, seed và hash đầu ra.
8. **Thiếu thì loại, không đoán (fail-closed).** Thiếu ngày, thiếu trường hay không giải được thực thể thì loại kèm mã lý do, và mã đó phải nằm trong danh sách của chính sách. Không bao giờ điền giá trị mặc định.
9. **Chất lượng do con người đo.** Precision và recall của trích xuất, độ chính xác liên kết thực thể và nghĩa của câu hỏi đều được đo trên mẫu do người gán độc lập. LLM không được làm người quyết định khoa học.
10. **Mỗi phép đo có đối chứng âm và đối chứng dương** [TL: Dubossarsky 2017; Shoemark 2019]. Đối chứng âm là tình huống chắc chắn không có thay đổi thật. Đối chứng dương là thay đổi biết trước, giống cách dữ liệu thật thay đổi.
11. **So sánh cùng loại với cùng loại.** Độ trôi và null phải được tính bằng cùng một cấu trúc ước lượng: cùng số cặp, cùng cách gộp, cùng quan hệ seed (cùng seed hay khác seed). Nếu không, null có thể hẹp hơn độ trôi ngay cả khi không có drift (giả thuyết rút ra từ N1, R24).
12. **Kết quả null chỉ hợp lệ khi phép đo đã được chứng minh là đủ nhạy.** Nếu đối chứng dương không đạt thì báo NOT_TESTABLE. Không hạ ngưỡng, không đổi thước đo sau khi thấy kết quả.

---

## 2. Bản đồ giai đoạn

| Khối | Giai đoạn | Cổng ra chính | Stage tương ứng (AGENTS §1.2) |
|---|---|---|---|
| A. Thiết kế | G0 Câu hỏi, đại lượng, mục tiêu đo | Estimand, SESOI, MDE mục tiêu, ngữ nghĩa KG được ghi | (mới) |
| | G1 Mô phỏng khả năng phát hiện | Có vùng khả thi; tính được k\*, M, K, Q | (mới) |
| | G2 Ontology và quan hệ | 0 cặp nghịch đảo hoặc trùng nghĩa; có luật kiểu, luật trạng thái | 2 (một phần) |
| | G3 Chọn và khóa nguồn | Sản lượng dự kiến nằm trong vùng khả thi; nguồn đã khóa | 1 |
| B. Từ web đến fact | G4 Thu thập thô | Độ phủ theo tháng ≥ 90% | 1 |
| | G5 Tách văn bản, lọc phạm vi | 0 bài lấy nhầm khung; lọc tái lập được | 1 |
| | G6 Gold và pilot trích xuất: **G6a** pilot trên kho bài đã có (chạy sớm, xem luồng); **G6b** gold mới khi ontology hoặc nguồn đổi | GO theo luật X1 | (mới) |
| | G7 Trích xuất toàn bộ | Lỗi cuối ≤ 1%; bằng chứng khớp ≥ 95%; 0 vi phạm kiểu | 2 |
| | G8 Thực thể | 0 thực thể chung chung; độ chính xác liên kết ≥ 0,90 | 2 |
| | G9 Thời gian bằng chứng | 0 fact dùng thời điểm crawl | 2 |
| | G10 Kho FactVersion | Khớp schema 17/17; parity Parquet–Neo4j | 2 |
| C. Snapshot | G11 Snapshot tuần tự | Đúng as-of; đủ transition; cân bằng | 3 |
| | G12 Cổng cấu trúc đồ thị | A1b, A3, A5, A7, A8 đạt; A1, A2, A6 có báo cáo | (mới) |
| D. Đo | G13 Huấn luyện KGE | Chất lượng, hội tụ, tái lập | 4 |
| | G14 Căn chỉnh và null | Chẩn đoán căn chỉnh đạt; đủ quan sát null | 5, 6 |
| | G15 Đo độ trôi | Một thước đo chính và nhóm thước đo độ vững được đăng ký | 7 |
| | G16 Hiệu chuẩn phép đo | Đối chứng âm/dương đạt; hợp lệ về cấu trúc | 7 (mở rộng) |
| E. Đánh giá | G17 Bộ câu hỏi đa bước | Không đáp án nào > 5%; duyệt nghĩa đạt | 8 |
| | G18 Thống kê | Luật E-robust; falsification | 9 |
| | G19 Đóng băng, báo cáo | Freeze sạch; có datasheet | W7 |

**Luồng:** G0 → **G6a** (pilot trên kho bài đã có, theo X1) → G1 → **cổng đầu tư** (mục 2.3) → (G2 song song G3) → G4 → G5 → **G6b** (chỉ khi ontology hoặc nguồn đổi) → G7 → G8 → G9 → G10 → G11 → G12 → G13 → G14 → G15 → G16 → G17 → G18 → G19.

G6a chạy sớm vì G1, G2 và G3 cần số liệu của nó: số fact/bài, p_attach và số fact nằm ngoài ontology. Nếu ontology hoặc nguồn thay đổi sau G6a, gold cũ không đo được phần mới, nên phải gán gold mới (G6b) trước khi trích toàn bộ.

Cổng nào trượt thì đi theo nhánh đã đăng ký ở mục 2.1. Không bao giờ chỉnh cho qua.

### 2.1 Quy tắc rẽ nhánh (đăng ký cùng lúc với G0)

| Cổng trượt | Nhánh bắt buộc |
|---|---|
| G1: không có vùng khả thi với nguồn dự kiến | Đổi thiết kế **trước khi thu thập**: thêm nguồn, đổi ontology, hoặc dùng bộ dày (nhánh C) để kiểm định phương pháp. |
| G6: NO-GO | Báo cáo đủ số liệu. Muốn đổi prompt hoặc mô hình thì phải đăng ký mới và gán gold mới [ĐK X1]. |
| G12: cấu trúc không đạt | H1 = NOT_TESTABLE trên bộ này. Đi tiếp theo nhánh đã ghi: quay lại G3 để thêm nguồn, hoặc chuyển phần kiểm định sang nhánh C. |
| G16: đối chứng dương không đạt | H1 = NOT_TESTABLE. Pipeline vẫn chạy và báo cáo mô tả [ĐK `configs/s5_drift_v33.yaml`]. |
| G18: kết luận không E-robust | H1 = NOT_TESTABLE [ĐK `configs/n1_h1_deg3_v33.yaml`]. |
| Cổng đầu tư (mục 2.3): nhánh A không thể vào vùng khả thi | Chỉ làm nhánh C. v3.3 giữ vai trò nghiên cứu tình huống |

### 2.2 Chế độ thực thi (AGENTS.md §8.2)
- Mỗi lần chỉ chạy **một** giai đoạn, theo trình tự: xem xét → lập kế hoạch → làm → kiểm thử → chạy → kiểm chứng → báo cáo giai đoạn → **DỪNG**. Không tự sang giai đoạn sau.
- Chỉ sang giai đoạn sau khi: giai đoạn trước PASS, đủ artifact, mọi bất biến vẫn giữ, **và** người dùng yêu cầu rõ.
- Phải có người dùng duyệt rõ trước khi:
  - thu thập dữ liệu mới (G4);
  - xử lý lại toàn kho (G7 trên toàn bộ bài);
  - gọi API có tính phí;
  - sửa protocol hoặc `sources.lock.json`.

### 2.3 Cổng đầu tư (sau G1 và G6a)
Dựng v4 (nhánh A) tốn nhiều tuần. Trước khi bắt đầu G2–G10, so sản lượng tốt nhất có thể đạt của nhánh A với vùng khả thi của G1. Sản lượng ước tính = fact/bài × số bài × p_attach, lấy từ G6a.

| Kết quả | Quyết định |
|---|---|
| Sản lượng ước tính từ kho bài đã có nằm trong vùng khả thi | Làm nhánh A (có thể song song nhánh C) |
| Chỉ vào được vùng khả thi khi thêm nguồn | Làm G3 cho nguồn mới, rồi nhánh A |
| Không vào được, kể cả khi trích xuất lại đầy đủ và thêm các nguồn khả dĩ | Chỉ làm nhánh C để kiểm định phương pháp. Nhánh A dừng ở mức nghiên cứu tình huống (v3.3) |

---

## Khối A. Thiết kế trước khi có dữ liệu

### G0. Câu hỏi, đại lượng cần ước lượng và mục tiêu đo

**Mục tiêu.** Chốt chính xác cái cần đo và độ nhạy cần có, trước mọi bước khác.

**Các bước**

1. **Viết giả thuyết dạng toán.** H1: `RR_{q,t} = β·D_{q,t} + α_q + γ_t + ε`.
   - Đơn vị quan sát: câu hỏi × transition. Cụm: transition.
   - D là trung vị SED⁺ của các thực thể hỗ trợ khác nhau, chỉ tính khi đủ hỗ trợ [ĐK protocol: `query_aggregator_primary`, `missing_support_primary`, `fixed_effects`].
2. **Định nghĩa "độ trôi thật".** Đó là thay đổi biểu diễn của một thực thể giữa hai snapshot, **vượt mức nhiễu huấn luyện lại**, sinh ra bởi thay đổi cấu trúc. Phân biệt hai loại:
   - *trực tiếp*: cạnh của chính thực thể thay đổi;
   - *gián tiếp*: cạnh của hàng xóm thay đổi, hoặc toàn đồ thị lớn lên. Loại này có thể xảy ra ngay cả khi lân cận của thực thể không đổi.
3. **Chọn hiệu ứng nhỏ nhất đáng quan tâm (SESOI)** trên **thang chuẩn hóa**, rồi đặt mục tiêu MDE₈₀ ≤ SESOI. **[ĐX: người dùng chọn con số]**
   - Thang đề xuất: chênh lệch RR giữa phân vị 75 và phân vị 25 của D, ví dụ 0,02 RR. Hoặc: thay đổi RR cho mỗi độ lệch chuẩn của D.
   - Lý do: β "trên mỗi đơn vị SED⁺" thay đổi ý nghĩa theo phân phối của D. Ở N1, độ lệch chuẩn của D chỉ 0,03–0,11, nên β = 0,05 trên mỗi đơn vị chỉ còn khoảng 0,005 RR trên mỗi độ lệch chuẩn (RV-02).
   - Vẫn báo cáo thêm thang gốc để đối chiếu với N1.
4. **Chốt ngữ nghĩa KG.**
   - (a) **Tích lũy, "đã được đưa tin tới t".** Fact không bao giờ bị bỏ và drift chỉ đến từ việc thêm cạnh. Đây là ngữ nghĩa thực tế của v3.x. Nó là mục D3 trong bảng quyết định của kế hoạch, và được thể hiện một phần ở [ĐK `s1_tie_safe_boundaries_and_valid_from_20261118`]. Decision log chưa có mục riêng cho tuyên bố ngữ nghĩa này.
   - (b) **"Đúng tại t".** Cần sự kiện kết thúc hoặc thay thế, chỉ ghi khi bài báo nói rõ (từ nhiệm, bán lại, ngừng sản phẩm). Ontology 1.1 đã khai `is_CEO_of` là quan hệ trạng thái với khóa logic (relation, object), tức một tổ chức chỉ có một CEO tại một thời điểm. Nhưng pipeline v3.x không thực thi khóa này nên Google có nhiều CEO cùng lúc (F3).
   - **[ĐX]** Giữ (a) làm trục chính. Áp dụng thay thế phiên bản theo khóa logic cho các quan hệ trạng thái đã khai trong ontology, chỉ khi bằng chứng rõ. Đây là quyết định của người dùng.
5. **Đăng ký quy tắc rẽ nhánh** (mục 2.1) và ghi các mục trên vào decision log trước khi bắt đầu G1.

**Cổng ra.** Estimand, quần thể, SESOI, MDE mục tiêu, ngữ nghĩa KG và quy tắc rẽ nhánh đều có trong decision log.

**Lưu ý**
- Không lấy phương sai của RR hay của drift từ v3.3 để đặt MDE, vì như vậy là dùng kết quả để thiết kế. Hãy dùng một dải giả định có biên trên và biên dưới trong mô phỏng.
- Chỉ có **một** giả thuyết chính. Mọi phân tích khác ghi rõ là thăm dò.
- H2 (Seen-at-T1, OOV) và H3a (đường đi, fallback exact-B) giữ nguyên theo protocol. Khung này không đổi chúng.

**Sự cố thường gặp:** SESOI chọn sau khi thấy kết quả; định nghĩa drift mơ hồ dẫn tới đổi thước đo giữa chừng (R30).

**Sản phẩm:** file cấu hình thiết kế (`configs/<tên>_design.yaml`) và các mục decision log.

### G1. Mô phỏng khả năng phát hiện, trước khi có dữ liệu

**Mục tiêu.** Quy MDE mục tiêu thành yêu cầu cụ thể cho dữ liệu: số thực thể, bậc, tỷ lệ cạnh mới bám vào thực thể cũ, số transition và số câu hỏi.

**Các bước**

1. **Dựng bộ sinh đồ thị tổng hợp có tham số:**
   - số thực thể N và số quan hệ R;
   - phân bố bậc đuôi dài (dạng luật lũy thừa), lấy số mũ từ dải trong tài liệu hoặc từ pilot G6, không lấy từ kết quả drift;
   - số fact mới mỗi transition;
   - **p_attach**: xác suất một đầu của fact mới là thực thể đã có. v3.3 tối đa 0,42 tính theo đầu cạnh. Đây là cận trên, vì một thực thể mới có thể nằm ở nhiều cạnh mới. LKGE bằng 1,0 vì cách dựng [TL];
   - số transition K.
2. **Chạy đúng mã M2 đã đăng ký** (TransE-L2, cùng d, lr, margin, E, 3 seed) trên đồ thị tổng hợp.
3. **Bơm drift theo các kịch bản của G16**, bắt buộc có kịch bản "thêm k cạnh". Đo độ nhạy và FPR **theo từng nhóm bậc** để có đường cong phát hiện. Từ đó lấy **k\***: bậc nhỏ nhất mà PC1 ở mức +100% bậc đạt độ nhạy ≥ 0,50 và FPR ≤ 0,10, ở mọi E (theo chuẩn của G16).
4. **Ước lượng MDE₈₀.**
   - Cài hiệu ứng **chỉ trên kết quả tổng hợp**: RR_sim lấy từ mô hình huấn luyện trên đồ thị tổng hợp, cộng thêm β·D_sim.
   - Ước lượng bằng TWFE và WCB, rồi tính MDE₈₀ theo số câu Q và số transition K.
   - Không dùng RR hay phương sai RR của dữ liệu thật (INV-06; RV-12).
5. **Quét lưới tham số** để tìm **vùng khả thi**: các tổ hợp (N, bậc trung bình, p_attach, K, M, Q) đạt mục tiêu. K và M phải cùng nằm trong lưới vì chúng đánh đổi nhau (G11).
6. **Ghi các giá trị dẫn xuất:**
   - k\*;
   - M: số anchor tối thiểu có thay đổi mỗi transition;
   - M₀: kích thước tối thiểu của snapshot đầu;
   - K tối thiểu và Q tối thiểu.

**Cổng ra.** Vùng khả thi khác rỗng và chứa được sản lượng ước tính của nguồn dự kiến (G3). Nếu không, đi theo nhánh ở mục 2.1.

**Lưu ý**
- **Đồ thị tổng hợp phải có đuôi dài như tin tức thật.** Đồ thị đều cho kết quả quá lạc quan.
- **Kịch bản drift trong mô phỏng phải giống cách dữ liệu thật thay đổi** (thêm cạnh), không chỉ "thay toàn bộ lân cận".
- **Chi phí tính toán.** Bộ huấn luyện hiện tại (`src/kge/model.py`) viết bằng Python thuần, chạy CPU. Mô phỏng nhiều cấu hình cần bản vector hóa. Mọi bản mới phải chứng minh cho kết quả tương đương bản cũ trên v3.3 trước khi dùng. Ngân sách tính toán xem Phụ lục H.
- **k\* phụ thuộc vào d, E và cách điều chuẩn.** Đổi các tham số này thì phải chạy lại G1.

**Sự cố thường gặp:** chỉ chạy một cấu hình; dùng tham số "mong muốn" thay cho tham số mà nguồn thực sự đạt được.

**Sản phẩm:** báo cáo mô phỏng, bảng vùng khả thi, đường cong phát hiện theo bậc.

### G2. Ontology và cách xây dựng quan hệ

**Mục tiêu.** Có một tập quan hệ đủ dày, không có đường tắt, có luật kiểu và luật thời gian rõ ràng.

**Các bước**

1. **Thu thập quan hệ ứng viên từ pilot G6a.** Người gán ghi cả fact nằm ngoài ontology. Đây là chỉ số chẩn đoán, dùng để biết có nên mở rộng ontology hay không. Nếu ontology đổi, gold của G6a không đo được quan hệ mới, nên phải gán gold mới (G6b) trước G7.
2. **Mỗi quan hệ phải có hồ sơ:**

   | Thuộc tính | Ví dụ |
   |---|---|
   | Định nghĩa, ví dụ đúng và ví dụ sai | `invested_in`: không tính tài trợ nghiên cứu |
   | Kiểu chủ thể → khách thể | Person → Organization |
   | Chiều chuẩn | luôn lưu `X released_by Y`, không lưu chiều ngược |
   | Tính chất | đối xứng (`partners_with`); trạng thái/hàm (`is_CEO_of`); sự kiện (`acquired_by`); một-nhiều |
   | Luật loại trừ | đã có `is_CEO_of` thì không thêm `works_at` cho cùng cặp |
   | Ngữ nghĩa thời gian | sự kiện hay trạng thái; điều kiện kết thúc |

3. **Không lưu cặp nghịch đảo** (ví dụ cả `acquires` lẫn `acquired_by`), và không để hai quan hệ trùng nghĩa.
   - [TL] FB15k và WN18 bị lộ đáp án vì phần lớn bộ test là nghịch đảo của bộ train. Tài liệu thứ cấp ghi khoảng 81% (Toutanova & Chen 2015). Đây là lý do có FB15k-237 và WN18RR.
   - [TL] YAGO3-10 bị phê bình vì có nhiều quan hệ trùng nhau.
4. **Quan hệ đối xứng** được lưu một lần theo thứ tự chuẩn (ví dụ theo id). Khi xếp hạng, lọc cả hai chiều. Trong câu hỏi đa bước, cấm đi tới rồi quay lui qua cùng một cạnh đối xứng.
5. **Quan hệ trạng thái** (khóa logic chỉ gồm relation và object, như `is_CEO_of`): fact mới cho cùng khóa là **phiên bản thay thế**, không phải fact song song. Pipeline phải thực thi điều này. v3.x không thực thi, dẫn tới F3.
6. **Kiểu thực thể.** Bộ trích xuất phải trả kiểu cho mỗi mention, hoặc có bước gán kiểu riêng. Một thực thể mang hai kiểu mâu thuẫn ở các bài khác nhau thì đưa vào hàng chờ duyệt.
7. **Tiêu chí giữ một quan hệ** [ĐX]: có ≥ 50 triple ở snapshot cuối và xuất hiện ở ≥ 80% số snapshot. Quan hệ quá hiếm thì gộp hoặc bỏ.
8. **Đánh phiên bản và hash ontology** (`ontology_version`). Mọi thay đổi tạo phiên bản mới [AM].

**Cổng ra.** 0 cặp nghịch đảo; 0 quan hệ trùng nghĩa; kiểm kiểu tự động chạy được; mỗi quan hệ có hồ sơ và ví dụ trong guideline.

**Lưu ý: đánh đổi về mật độ**
- Thêm quan hệ thì tăng số cạnh nhưng giảm số triple trên mỗi quan hệ. Nên ưu tiên quan hệ nối các thực thể đã phổ biến, vì đó là cách nâng bậc của quần thể lõi.
- [TL] Pujara 2017 bớt một nửa triple của FB15k theo hai cách: bỏ triple ngẫu nhiên (`sparse`) hoặc bỏ trọn một số quan hệ (`stable`). Bỏ trọn quan hệ cho Hits@10 lọc tốt hơn bỏ ngẫu nhiên tới 60%. Bài rút ra rằng chất lượng embedding phụ thuộc vào **mật độ triple trên mỗi quan hệ**. Bài **không tách riêng** ảnh hưởng của mật độ trên mỗi thực thể, nên không thể suy ra rằng mật độ theo thực thể quan trọng hơn mật độ theo quan hệ.
- Với dự án: T10 của v3.3 có 1.098 triple trên 10 quan hệ, trung bình khoảng 110 triple mỗi quan hệ. Con số này thấp hơn mốc 220 mà Pujara gọi là "tương đối cao" (một nửa FB15k). Vì vậy mật độ theo quan hệ cũng cần được theo dõi bên cạnh bậc thực thể (chỉ số A8 ở G12).

**Sự cố thường gặp:** đường tắt qua quan hệ đối xứng (L25: 80% câu mẫu đi qua `partners_with`); sai chiều (`Nomi integrated_into GPT-4o`); sai loại (`Google Maps based_on Gemini`); quan hệ trạng thái bị lưu song song (F3).

**Sản phẩm:** `config/ontology.yaml` phiên bản mới, bảng hồ sơ quan hệ, test kiểu.

### G3. Chọn và khóa nguồn

**Mục tiêu.** Có các nguồn công khai, đủ sản lượng, có ngày đăng tin cậy, và được khóa trước khi thu thập.

**Các bước**

1. **Tiêu chí chọn nguồn:**
   - công khai, thu thập được bằng sitemap, RSS, HTML hoặc Wayback theo AGENTS §9, không dùng API;
   - ≥ 95% trang có ngày đăng do nhà xuất bản khai kèm múi giờ (JSON-LD `datePublished`) [ĐX];
   - đúng phạm vi chủ đề;
   - cấu trúc HTML ổn định, hoặc chia được theo từng phiên bản giao diện.
2. **Ước lượng sản lượng** = bài/tháng × fact/bài (từ G6) × p_attach (từ G6), rồi đối chiếu với vùng khả thi của G1.
3. **Khóa nguồn** trong `sources.lock.json` qua amendment [AM]: tên nguồn, khoảng thời gian, mẫu URL, phiên bản parser.

**Cổng ra.** Sản lượng dự kiến nằm trong vùng khả thi; nguồn đã được khóa.

**Lưu ý**
- Việc chọn nguồn không được dựa vào bất kỳ kết quả drift nào.
- Đường tải nào mơ hồ với luật "không API" thì hỏi trước và ghi quyết định. Ví dụ: máy chủ CDX của Wayback, đường dẫn `/api/` của kho Dataverse.
- Thêm nguồn khác thể loại sẽ làm thay đổi quần thể, nên kết quả phải báo theo từng nguồn.
- Bản quyền: chỉ lưu văn bản đầy đủ cho mục đích nghiên cứu. Khi phát hành, chỉ phát hành triple, URL, hash và đoạn bằng chứng ngắn.

**Sự cố thường gặp:** nguồn đổi giao diện giữa kỳ; bị chặn crawl; thiếu ngày đăng; cùng một tin xuất hiện ở nhiều nguồn (gộp ở tầng fact, giữ bằng chứng sớm nhất).

**Sản phẩm:** amendment, `sources.lock.json` mới, bảng sản lượng dự kiến.

---

## Khối B. Từ trang web đến fact

### G4. Thu thập thô và độ phủ

**Các bước**
1. Lập danh sách URL từ sitemap, RSS hoặc Wayback theo khoảng thời gian đã khóa.
2. Tải HTML, lưu blob theo SHA-256 và ghi `raw_inventory` kèm `retrieved_at_real`. Chỉ thêm, không sửa.
3. Đo độ phủ theo tháng và theo nguồn: số URL tải được chia cho số URL trong sitemap. Ghi phần thiếu vào `missing_coverage_ledger`.
4. Phát hiện trang lỗi giả (soft 404), chuyển hướng, trang cần JavaScript, paywall.
5. Lưu log crawl và hash toàn bộ blob vào manifest.

**Cổng ra.** Độ phủ ≥ 90% mỗi tháng, mỗi nguồn [ĐX]; 100% blob khớp hash; có log crawl.

**Lưu ý**
- `retrieved_at_real` chỉ thuộc trục thu thập (chuẩn mực 4).
- Không chạy lại Stage 4.3 (`src/03b_run_tuoitre_historical_window.py`) [ĐK AGENTS §8.2].
- Không thu thập toàn bộ một cách không giới hạn.

**Sự cố thường gặp**
- Tốc độ sự kiện chênh nhiều giữa các tháng mà không rõ do nhịp tin tức hay do crawl sót. Ví dụ L28: 110 sự kiện trải trên 36–86 ngày.
- Dữ liệu thô không có hash gốc từ người gửi.

**Sản phẩm:** blob, `raw_inventory`, báo cáo độ phủ theo tháng.

### G5. Tách văn bản và lọc phạm vi

**Các bước**
1. **Mỗi nguồn một parser có phiên bản.** Chỉ lấy tiêu đề, sapo và đoạn văn của vùng nội dung. Bỏ khung ảnh, tin liên quan, tác giả, khu tương tác. Mẫu: [src/kg_pipeline/tuoitre_parser_v2.py](../src/kg_pipeline/tuoitre_parser_v2.py).
2. **Test parser trên trang thật** cho từng phiên bản giao diện. Thiếu trường bắt buộc thì loại kèm mã lý do.
3. **Lọc phạm vi bằng một luật duy nhất** trong file chính sách, áp dụng giống nhau cho mọi nguồn. Mọi mã lý do phải có trong chính sách.
4. **Loại trùng văn bản** (cùng nội dung ở nhiều URL): giữ một bản theo quy tắc xác định và ghi lý do.
5. **Ghi cả `datePublished` và `dateModified`** nếu trang có, để dùng ở G9.

**Cổng ra**
- Kiểm tay 30 bài mỗi nguồn: không bài nào lấy nhầm khung [ĐX].
- 100% mã lý do nằm trong chính sách; chạy lại cho cùng kết quả.
- Có báo cáo phân bố độ dài theo nguồn.

**Sự cố thường gặp:** selector bắt nhầm khung tin liên quan (F12, F10); mã lọc không có trong chính sách (L03); hai nguồn được lọc theo hai cách khác nhau (quy tắc từ khóa và bộ lọc v3.1 chỉ trùng 85%).

**Sản phẩm:** bảng thân bài, bảng quyết định lọc, báo cáo parser.

### G6. Gold và pilot trích xuất (G6a chạy sớm, G6b khi cần)

**Mục tiêu.** Đo chất lượng trích xuất bằng con người trước khi chạy toàn bộ, đồng thời đo các chỉ số chẩn đoán cần cho G1, G2 và G3.

**Hai lượt**
- **G6a** chạy ngay sau G0, trên kho bài đã có, dùng chính đăng ký X1.
- **G6b** là một lần gán gold mới, đăng ký mới, chỉ khi ontology hoặc nguồn thay đổi sau G6a.

Cả hai lượt theo cùng các bước dưới đây.

**Các bước** (theo mẫu X1 đã đăng ký: `configs/x1_reextraction_pilot_v34.yaml`)
1. **Lấy mẫu** phân tầng theo nguồn × tam phân độ dài. Thứ tự lấy theo khóa SHA-256, không dùng RNG. Tách riêng tập gold và tập dev. Khóa danh sách kèm hash trước mọi lệnh gọi mô hình và trước khi bắt đầu gán.
2. **Gán nhãn.** Hai người gán độc lập theo guideline và không thấy kết quả của mô hình. F1 giữa hai người trước phân xử phải ≥ 0,70; nếu thấp hơn thì guideline có lỗi và phải dừng [ĐK].
3. **Phân xử** bởi người thứ ba. Giữ nhãn gốc. Khóa hash của gold.
4. **Chỉnh prompt chỉ trên tập dev**, tối đa 2 lần, dựa trên kiểm tra cơ học. Sau đó đóng băng prompt và trích gold đúng một lần [ĐK].
5. **Chấm điểm:** so khớp một-một theo khóa chuẩn của thực thể; `partners_with` tính đối xứng; mention chung chung tính là sai.
6. **Chỉ số chẩn đoán bổ sung** [ĐX, cần sửa đăng ký X1]:
   - số fact nằm ngoài ontology trên mỗi bài;
   - tỷ lệ fact gold có ít nhất một thực thể đã có trong snapshot trước ngày đăng bài (ước lượng p_attach). Lưu ý: ở pilot, snapshot dùng để so là v3.3 (trích xuất cũ, thưa hơn), nên con số thường là cận dưới của p_attach ở v4;
   - lỗi chiều và lỗi loại quan hệ, đếm riêng.

**Cổng ra: GO khi đạt đủ cả năm điều kiện** [ĐK X1]
- precision ≥ 0,85, cận dưới CI95 ≥ 0,75;
- recall ≥ 0,60;
- ≥ 2,5 fact khẳng định đúng trên mỗi bài;
- ≤ 2/50 bài bị lỗi cuối;
- câu bằng chứng tìm thấy nguyên văn ≥ 0,95.

**Lưu ý**
- Gold không bao giờ được dùng để chỉnh prompt. Nếu NO-GO thì phải đăng ký mới và gán gold mới.
- Báo cáo theo từng nguồn, vì khung lọc của hai nguồn khác nhau.
- Mốc tham chiếu [TL]:
  - NELL đạt độ chính xác 0,75–0,85 với các trích xuất tự tin và 0,35–0,45 trên toàn bộ (Mitchell 2015, theo Pujara 2017).
  - Một văn bản thường chứa nhiều fact hơn mức một lần trích tìm được: DocRED 12,5 triple/văn bản, gán lại thành Re-DocRED còn ~29,8.

**Sự cố thường gặp:** F1 giữa người gán thấp; mô hình trả JSON sai; cùng prompt cho kết quả khác nhau giữa hai lần chạy (đo Jaccard, chỉ để chẩn đoán); chi phí vượt trần (R33).

**Sản phẩm:** manifest mẫu, gold đã khóa, báo cáo điểm kèm CI, báo cáo chi phí.

### G7. Trích xuất toàn bộ

**Các cách xây dựng quan hệ từ văn bản**

| Cách | Mô tả | Ưu | Nhược | Ví dụ |
|---|---|---|---|---|
| LLM theo schema | Prompt có định nghĩa quan hệ, đầu ra JSON | Nhanh, không cần dữ liệu huấn luyện | Hộp đen; phiên bản có thể đổi; tốn chi phí; có thể bịa | X1 (Gemini) |
| Mô hình RE có giám sát | Huấn luyện trên dữ liệu đã gán nhãn | Ổn định, tái lập được | Cần nhiều nhãn; tiếng Việt ít dữ liệu | VLSP 2020: 1.056 bài, 4 loại quan hệ |
| Từ điển và mẫu câu | Danh mục thực thể cộng mẫu động từ | Minh bạch, tái lập, nhanh | Bỏ sót cách diễn đạt mới; tốn công làm từ điển | ICEWS (bộ mã CAMEO, từ điển chủ thể) |
| Máy đề xuất, người duyệt | Mô hình đề xuất, người xác nhận | Chất lượng cao | Tốn công người | DocRED |

Cách nào cũng phải qua G6 trước khi chạy toàn bộ.

**Các bước**
1. **Đóng băng bộ trích xuất:** mã mô hình, phiên bản API, hash prompt, nhiệt độ 0, schema JSON (có trường `evidence_text` và kiểu thực thể).
2. **Bộ nhớ đệm bền.** Khóa đệm là hash của (văn bản, prompt, cấu hình). Phản hồi đã lưu là nguồn sự thật, không gọi lại mô hình.
3. **Đọc toàn bài.** Bài vượt giới hạn thì loại kèm mã lý do, không cắt và không chia khúc [ĐK X1].
4. **Tính lại vị trí bằng chứng** bằng tìm chuỗi nguyên văn. Không tìm thấy thì gắn cờ `SPAN_UNVERIFIED`.
5. **Kiểm tra từng claim:** mention có thật trong văn bản; kiểu và chiều đúng theo ontology; cờ dự kiến hoặc phủ định.
6. **Ghi trạng thái từng bài** (thành công, lỗi tạm, lỗi cuối) và chi phí thực tế.

**Cổng ra**
- Lỗi cuối ≤ 1% số bài [ĐX].
- Bằng chứng khớp nguyên văn ≥ 95% [ĐK X1].
- Chi phí không vượt trần đã duyệt.
- Tỷ lệ claim vi phạm kiểu, tính **trước khi lọc**, ≤ 5% và có báo cáo [ĐX]. Claim vi phạm bị loại kèm lý do. Không đếm sau khi lọc, vì khi đó con số luôn bằng 0 (RV-13).

G7 là xử lý toàn kho, nên cần người dùng duyệt rõ trước khi chạy (mục 2.2).

**Lưu ý.** Mô hình chạy trên máy chủ của nhà cung cấp có thể đổi hành vi mà vẫn giữ nguyên tên (R10). Vì vậy:
- ghi metadata của mọi phản hồi;
- mỗi lần chạy lại là một phiên bản mới;
- không trộn kết quả của hai phiên bản mô hình trong cùng một bộ.

**Sự cố thường gặp:** mô hình bị ngừng giữa chừng; bị giới hạn tốc độ gọi; thực thể bịa, không có trong bài; tin đồn bị ghi thành fact khẳng định (R11).

**Sản phẩm:** bảng claim, bộ nhớ đệm, manifest, báo cáo chi phí.

### G8. Chuẩn hóa và liên kết thực thể

**Các bước**
1. **Khóa chuẩn xác định**, chỉ dựa trên chính chuỗi mention: NFC, chữ thường, bỏ tiền tố và hậu tố pháp lý theo luật. Mẫu: [src/kg_pipeline/entity_map_v2.py](../src/kg_pipeline/entity_map_v2.py).
2. **Danh sách chặn** cho mention chung chung và đại từ, có phiên bản.
3. **Gộp alias theo luật.** Những liên kết cần hai mention (viết tắt ↔ tên đầy đủ) phải có `mapping_available_at` ≤ cutoff (INV-02).
4. **Người duyệt bảng gộp** trước khi dùng. Nhãn hiển thị bỏ kính ngữ: "ông Trương Gia Bình" → "Trương Gia Bình".
5. **Tùy chọn: gắn vào danh mục có id ổn định**, như từ điển chủ thể của ICEWS [TL]. Dùng danh mục bên ngoài là quyết định thu thập dữ liệu, nên cần duyệt.
6. **Giải đồng tham chiếu đơn giản trong bài**, nếu được duyệt. Ví dụ "ông" → tên người đã được nêu trước đó trong cùng bài. Nếu không được duyệt thì loại và ghi lý do.

**Cổng ra**
- Kiểm 100 thực thể lấy ngẫu nhiên: thực thể chung chung ≤ 1% [ĐX]. Không dùng con số đếm sau khi chặn làm cổng, vì nó luôn bằng 0 (RV-13).
- Độ chính xác liên kết ≥ 0,90 trên ≥ 100 mention gán tay [ĐX].
- Tỷ lệ sự kiện bị loại: **mỗi nguyên nhân ≤ 5%**; tổng chỉ công bố, không chặn [ĐK `s2_quarantine_thresholds_per_cause_20261118`]. v3.3: 3,7% + 3,3% = 7,1%.
- Bảng gộp đã được duyệt và có hash. Ở v3.3, người dùng đã duyệt bảng gộp theo khuyến nghị, không sửa [ĐK `s2_entity_map_v2_approved_20261118`].

**Sự cố thường gặp**
- Gộp nhầm (Alpha 7 IV/V, Nguyễn Mạnh Cường/Tường).
- Tách nhầm (AWS có 4 biến thể).
- Ánh xạ dùng thông tin tương lai (R14).
- Hub giả ("ông" có bậc 17).
- Đặc thù tiếng Việt: tên có dấu và không dấu; tên tiếng Việt và tiếng Anh của cùng một tổ chức; viết tắt nằm trong ngoặc, ví dụ "Bộ Công an (A05)".

**Sản phẩm:** `entity_map` phiên bản mới, báo cáo gộp, mẫu duyệt.

### G9. Gán thời gian bằng chứng

**Các bước**
1. **Đăng ký trước một quy tắc chọn căn cứ thời gian, thống nhất cho mọi nguồn.** Hai phương án:

   | Phương án | Ưu | Nhược |
   |---|---|---|
   | **P**: ngày đăng do nhà xuất bản khai, có múi giờ | Sớm, đúng lúc công chúng thấy bài | Do nguồn tự khai, cần kiểm chéo |
   | **W**: lần lưu Wayback đầu tiên | Bên thứ ba kiểm chứng được | Luôn muộn hơn P: trung vị 1,22 ngày, p90 4,16, tối đa 83,5 ngày (n = 479) |

   v3.2 dùng W khi có, P khi không có W [ĐK `s1_evidence_time_basis_20261118`, giữ quyết định `stage4_3_vnexpress_archive_time_semantics`]. Muốn đổi cần [AM].
2. **Ghi căn cứ, độ tin cậy và cờ** cho từng FactVersion. Sự kiện lấy bằng chứng sớm nhất.
3. **Kiểm bài bị sửa sau khi đăng (R02).**
   - Vấn đề: nếu `dateModified` > `datePublished`, văn bản tải về có thể chứa nội dung được thêm sau ngày đăng. Fact từ phần đó sẽ bị gán ngày sớm hơn thực tế, tức vi phạm INV-01 một cách ngầm.
   - Cách xử lý [ĐX]: so với văn bản của bản lưu Wayback sớm nhất nếu có. Nếu không có, fact không tìm thấy trong bản sớm thì dùng `dateModified` làm thời điểm bằng chứng, hoặc loại kèm lý do.
4. **Kiểm chéo độc lập:** mã bài trong URL tăng dần theo thời gian; dấu thời gian trong URL (Tuổi Trẻ). Chỉ dùng để kiểm, không dùng làm bằng chứng.
5. **`valid_from` chỉ điền khi văn bản nêu rõ ngày.** Không bao giờ sao chép thời điểm bằng chứng sang.

**Cổng ra**
- 0 fact dùng thời điểm crawl; 100% có múi giờ.
- Trung vị |Δ| của kiểm chéo ≤ 15 ngày [ĐK S1].
- Tỷ lệ fact đổi snapshot nếu dùng căn cứ còn lại ≤ 2% [ĐX].
- Có báo cáo số fact có `dateModified` > `datePublished`.

**Sự cố thường gặp:** thời điểm crawl bị dùng thay thời điểm bằng chứng (F1); độ trễ của Wayback (L27); thiếu múi giờ; khung tin liên quan không có ngày riêng (F10).

**Sản phẩm:** sổ thời gian bằng chứng, báo cáo căn cứ thời gian, báo cáo kiểm chéo.

### G10. Kho FactVersion và sự kiện

**Các bước**
1. **Khóa LogicalFactID theo ontology:**
   - quan hệ sự kiện: subject + relation + object;
   - quan hệ trạng thái: relation + object;
   - quan hệ đối xứng: theo thứ tự chuẩn.
2. **Mỗi bằng chứng sinh một FactVersion**, chỉ thêm vào. Các loại phiên bản: tạo mới, ủng hộ, thay thế, rút lại.
3. **Sự kiện KG** là một thay đổi của trạng thái logic, tính tại thời điểm bằng chứng sớm nhất.
4. **Kiểm schema** theo `config/schema.yaml`. Parquet là nguồn sự thật; Neo4j chỉ là lớp truy vấn, phải kiểm parity (INV-05).

**Cổng ra**
- 17/17 bảng khớp schema (hiện có 9/17 lệch nên M1 đang BLOCKED).
- Dựng hai lần trùng từng byte.
- Parity Parquet–Neo4j đạt.
- `python scripts/verify_g1.py --ci --code-checks` PASS.

**Sự cố thường gặp:** lệch schema (L21); sự kiện bị trùng sau khi gộp thực thể; quan hệ trạng thái bị lưu song song (R15).

**Sản phẩm:** bảng FactVersion, bảng sự kiện, bảng loại trừ, manifest.

---

## Khối C. Snapshot và cổng dữ liệu

### G11. Dựng snapshot tuần tự: khoảng thời gian và khoảng cách

**Mục tiêu.** Có một dãy snapshot đúng as-of, đủ số transition, đủ thay đổi ở mỗi transition và cân bằng giữa các transition.

**1. Kiểu snapshot**

| Kiểu | Nội dung snapshot T | Ưu | Nhược | Dùng khi |
|---|---|---|---|---|
| Tích lũy (as-of) | Mọi fact có bằng chứng ≤ cutoff, bỏ fact đã bị thay thế nếu dùng thay thế cho quan hệ trạng thái | Khớp định nghĩa as-of; nhiễu giảm dần khi đồ thị lớn lên | Thay đổi tương đối nhỏ dần ở các mốc sau | **Trục chính** [ĐK protocol] |
| Cửa sổ trượt | Chỉ fact có bằng chứng trong [T − w, T] | Thay đổi lớn hơn; hợp với dữ liệu sự kiện thoáng qua (Phụ lục D) | Thực thể biến mất; drift lẫn với "quên" | Phân tích độ vững; dữ liệu sự kiện |

**2. Cách đặt mốc**

| Cách | Mô tả | Ưu | Nhược |
|---|---|---|---|
| Cân bằng sự kiện | Mỗi khoảng có cùng số sự kiện. v3.x dùng `OUTCOME_BLIND_EVENT_BALANCED_V1`: khoảng 110 sự kiện mỗi khoảng, dài 36–86 ngày | Số thay đổi đều nhau | Độ dài theo lịch không đều; khó giải thích theo thời gian |
| Lịch cố định | Mỗi 30, 45 hoặc 60 ngày | Dễ giải thích | Số sự kiện không đều; có thể có khoảng rỗng |
| Lai | Lịch cố định, gộp khoảng quá ít sự kiện theo luật đăng ký trước | Cân bằng hai mục tiêu | Thêm một quy tắc cần đăng ký |

Cách nào cũng phải:
- chỉ dùng số sự kiện và dấu thời gian (mù kết quả);
- không cắt ngang nhóm sự kiện cùng dấu thời gian [ĐK S1];
- mỗi khoảng dài ≥ 14 ngày [ĐK S1].

Đổi thuật toán đặt mốc so với protocol là [AM].

**3. Kích thước và khoảng cách** (giá trị cụ thể lấy từ G1)

| Tham số | Chuẩn | Lý do |
|---|---|---|
| Số snapshot | 8–12 [ĐK protocol `allowed_range`], tức 7–11 transition. Muốn nhiều hơn cần [AM] | — |
| Số transition dùng được cho H1 | ≥ 5 cụm [ĐK N1 `testable_if`]; mục tiêu ≥ 7 [ĐX] | WCB kém tin cậy khi ít cụm hoặc cụm lệch kích thước [TL: MacKinnon & Webb 2017] |
| Snapshot đầu | ≥ M₀ triple [MP] | T01 của v3.3 chỉ có 113 triple, trong đó 29 triple để đánh giá |
| Thay đổi mỗi transition | ≥ M anchor có ít nhất 1 cạnh mới [MP] | Không có thay đổi thì không có drift (L24) |
| Cân bằng | Không transition nào vượt 2 × trung vị về số sự kiện hoặc số câu hỏi [ĐX] | v3.3: T09→T10 có 259 dòng câu hỏi, T03→T04 chỉ có 1 |
| Độ dài khoảng so với độ trễ bằng chứng | ≥ 5 × p90 độ trễ giữa hai căn cứ thời gian [ĐX] | Giảm số fact rơi sai snapshot (L27) |

**Đánh đổi giữa K và M.** Tổng số sự kiện của bộ dữ liệu là cố định. Chia càng nhiều mốc (K lớn) thì mỗi transition càng ít thay đổi (M nhỏ). K lớn giúp suy luận theo cụm; M lớn giúp phép đo có tín hiệu. Chọn K bằng lưới mô phỏng G1, không chọn theo cảm tính.

**4. So sánh ở khoảng cách nào**

| Kiểu so sánh | Ý nghĩa | Vai trò |
|---|---|---|
| Liên tiếp (T_k → T_{k+1}) | Drift trong một bước | **Chính**, khớp với TWFE theo transition |
| Mốc cố định (T_1 → T_k) | Drift tích lũy | Phụ: thấy xu hướng dài |
| Cả chuỗi | Tìm điểm thay đổi (mean-shift kèm kiểm định hoán vị) hoặc độ dốc | Phụ. [TL Shoemark 2019]: phân tích cả chuỗi tốt hơn chỉ so đầu với cuối, và chọn mốc tham chiếu nào cũng ảnh hưởng tới kết quả. Kiểm định hoán vị theo Kulkarni 2015 |

**Cổng ra.** Mỗi snapshot là hàm thuần của cutoff; các snapshot lồng nhau (trục tích lũy); INV-01 và INV-02 PASS; các tham số ở bảng 3 đạt.

**Sự cố thường gặp:** ranh giới cắt ngang nhóm cùng thời điểm (F2); snapshot cuối chỉ dài 0,01 ngày vì bị dồn về ngày crawl (F1); khoảng rỗng do crawl sót.

**Sản phẩm:** snapshot canonical, manifest của từng snapshot, `snapshot_boundaries.yaml`.

### G12. Cổng cấu trúc đồ thị, trước khi huấn luyện

**Mục tiêu.** Dừng sớm nếu dữ liệu không thể cho một phép đo đủ nhạy. Mọi chỉ số ở đây chỉ dùng cấu trúc đồ thị, không dùng embedding hay kết quả, nên được phép theo INV-06.

**Quần thể lõi** = các thực thể có bậc **tại snapshot trước transition** ≥ k\*.

| Mã | Chỉ số (mỗi snapshot / transition) | Chuẩn | Mốc so sánh |
|---|---|---|---|
| A1 | Bậc trung bình 2T/E của **toàn đồ thị** | Báo cáo bắt buộc. Không dùng làm cổng: nếu tính trên quần thể đã lọc theo bậc thì kết quả luôn ≥ k\* (RV-01) | v3.3: 1,7. [TL] NELL165: 3; WN18RR: 4,5; FB15k-237: 42,7. Các mốc này nói về chất lượng link prediction, không trực tiếp về độ nhạy với drift |
| A1b | Kích thước quần thể lõi: số thực thể có bậc trước transition ≥ k\*, mỗi transition | ≥ N_core [MP] | v3.3 với k\* = 3: 14–129 thực thể mỗi transition |
| A2 | Tỷ lệ fact mới có ít nhất một đầu là thực thể đã có | Chẩn đoán, báo cáo bắt buộc | [TL] LKGE: 1,0 vì cách dựng. v3.3: ít nhất 58% đầu cạnh mới là thực thể mới (chưa đếm theo từng fact) |
| A3 | Số anchor trong quần thể lõi có ≥ 1 cạnh mới ở mỗi transition | ≥ M [MP] | v3.3: tối đa 8% anchor ở T09→T10 |
| A4 | Ngưỡng bậc k\*, chỉ tính bằng bậc **trước** transition | Từ đường cong của G1 [MP] | v3.3 dùng 3 |
| A5 | Số anchor mỗi nhóm bậc | ≥ 51, để còn ≥ 50 tham chiếu sau khi loại thực thể đích [ĐX; ĐK S5 support = 50] | v3.3: nhóm ≥ 6 chỉ có 3–28 |
| A6 | Số triple trên mỗi tham số thực thể, T / (d·E) | Báo cáo bắt buộc [ĐX] | v3.3 ≈ 0,013; FB15k-237 với d = 200 ≈ 0,11 |
| A7 | Thành phần liên thông lớn nhất | ≥ 50% số thực thể [ĐX]. Lý do: trong TransE, các cụm rời nhau ít ràng buộc với nhau, nên căn chỉnh toàn cục dễ đặt sai cụm nhỏ và sinh drift giả; câu hỏi đa bước cũng cần liên thông | v3.3 ở T10: 35% |
| A8 | Mỗi quan hệ | ≥ 50 triple ở snapshot cuối [ĐX]; 0 cặp nghịch đảo | — |

**Báo cáo thêm (không phải cổng):** phân bố bậc; hệ số Gini của bậc; phân bố Jaccard lân cận giữa hai snapshot; số thực thể mới mỗi transition; tỷ lệ cạnh mới đổ vào 10 thực thể lớn nhất (liên quan L25).

**Cổng ra.** A1b, A3, A5, A7, A8 đạt; A1, A2, A6 có báo cáo. Nếu trượt, đi theo nhánh ở mục 2.1.

**Lưu ý.** Chọn quần thể theo bậc **tương lai** nghĩa là chọn theo chính biến phơi nhiễu (những thực thể sắp có thêm cạnh), nên bị cấm. Chỉ dùng bậc tại snapshot trước transition [ĐK protocol `anchor_policy: persistent_canonical_pretransition_stratified`].

---

## Khối D. Đo độ trôi

### G13. Huấn luyện KGE

**Các bước**
1. **Một cấu hình cho mọi snapshot:** TransE-L2 với cùng d, lr, margin, số epoch E [ĐK protocol]. Seed 13, 37, 101 [ĐK protocol]. Cấu hình hiện tại của v3.3: SGD, d = 64, lr = 0,01, margin = 2,0, E = 400; kiểm độ vững với E ∈ {300, 400, 500}. Không chỉnh tham số riêng cho từng snapshot, vì như vậy sẽ lẫn vào drift.
2. **Đánh giá có cấu trúc.** Validation lấy theo fold, chỉ trên triple có cả hai đầu bậc ≥ 2, lặp lại nhiều fold (F8).
3. **Cổng chất lượng:** cận dưới CI95 của MRR lọc phải lớn hơn mốc "đuôi phổ biến theo quan hệ" ở mọi snapshot [ĐK R1].
4. **Cổng hội tụ** (chẩn đoán): loss và nhiễu giữa seed không còn giảm đáng kể.
5. **Tái lập:** dựng lại checkpoint phải cho cùng hash.

**Cổng ra.** Chất lượng PASS ở mọi snapshot; tái lập PASS; độ ổn định giữa seed (1 − cos trên holdout) thấp hơn mốc ngẫu nhiên ở mọi nhóm bậc có đủ anchor [ĐK R1].

**Lưu ý**
- **Tỷ lệ tham số so với dữ liệu (A6).** d lớn trên đồ thị thưa làm thực thể ít bị ràng buộc, nên nhiễu seed lớn. d đang để `TO_BE_FROZEN_W2` trong protocol. Chọn d chỉ dựa trên chất lượng link prediction và độ ổn định, không dựa trên drift.
- **Chuyển sang GPU** có thể làm mất tính tái lập từng bit (R32). Cần một chính sách tái lập trước khi dùng: hoặc cờ tất định, hoặc so sánh có dung sai được đăng ký [AM nếu nới INV-04].
- **Margin.** Ở v3.3, 98–100% triple vi phạm margin 2,0 với thực thể đã chuẩn hóa. Cần xem lại lựa chọn margin trước khi đóng băng.

**Sự cố thường gặp:** chưa hội tụ (F6); nhiễu seed gần mức ngẫu nhiên (F7); snapshot đầu quá nhỏ (R19).

**Sản phẩm:** 3 × K checkpoint, báo cáo chất lượng, manifest.

### G14. Căn chỉnh và null

**Các bước**
1. **Anchor:** thực thể có mặt ở cả hai snapshot, phân tầng theo bậc trước transition. Không được dùng nhãn thay đổi, drift, RR, MRR, kết quả QA hay hệ số H1 [ĐK protocol `forbidden_features`].
2. **Căn chỉnh** bằng Procrustes trực giao có trừ tâm [TL: Schönemann 1966; Hamilton 2016; Schlechtweg 2019 chuẩn hóa độ dài và trừ tâm trước khi căn]. Dùng **cross-fit 5 fold**: mỗi thực thể được đo khi nó không nằm trong tập fit của chính mình [ĐK S5].
3. **Chẩn đoán căn chỉnh** [ĐK S5]:
   - sai số trực giao ≤ 1e-6;
   - hạng số ≥ 0,90 × min(d, n_fit − 1);
   - chênh lệch (holdout − fit) ≤ 0,65.

   Fold nào trượt thì các thực thể của fold đó được đánh dấu "không khả dụng" kèm lý do.
4. **Null cùng snapshot, khác seed** [ĐK S5]:
   - 3 cặp seed ở snapshot trước và 3 cặp ở snapshot sau, tổng 6 quan sát cho mỗi thực thể, lấy trung vị;
   - tính theo từng nhóm bậc, loại chính thực thể đích khỏi tập tham chiếu;
   - cần ≥ 50 tham chiếu (N1 dùng 30); nhóm thưa được gộp theo luật đã đăng ký.
5. **Null bổ sung, chỉ dùng chẩn đoán** [ĐX]: *nhiễu do lấy mẫu dữ liệu*. Huấn luyện trên hai mẫu bootstrap theo bài báo của cùng một snapshot. [TL: Antoniak & Mimno 2018: kho nhỏ thì láng giềng thay đổi mạnh giữa các mẫu bootstrap.] Null chính của protocol giữ nguyên.
6. **Kiểm cấu trúc ước lượng** (chuẩn mực 11, R24). Có hai điểm lệch cần kiểm:
   - δ là trung vị của 3 khoảng cách, còn null là trung vị của 6 quan sát;
   - δ so **cùng seed** ở hai snapshot, còn null so **khác seed**. Cần kiểm xem cùng seed có dùng chung khởi tạo cho thực thể cũ hay không.

   Nếu lệch, dùng một phiên bản null cùng cấu trúc (ví dụ phân phối trung vị của 3 khoảng cách cùng loại) làm phân tích độ vững. Thay null chính là [AM].

**Cổng ra.** Chẩn đoán căn chỉnh PASS; mọi nhóm bậc của quần thể đủ tham chiếu; số anchor fit ≥ max(51, 2d) [ĐX].

**Sự cố thường gặp**
- Hạng suy biến.
- Nhóm bậc cao quá ít anchor nên bị gộp với nhóm nhiễu hơn. Kết quả là excess âm và SED⁺ ≈ 0 với các thực thể bậc cao tự nhiên (kế hoạch §9.4.3; R23).
- Dùng phần dư căn chỉnh để loại anchor. Làm vậy là dùng drift để chọn anchor, nên bị cấm trừ khi đã đăng ký và thực hiện mù.

**Sản phẩm:** embedding đã căn, bảng chẩn đoán, bảng null theo nhóm bậc.

### G15. Các cách đo độ trôi

**Đăng ký một thước đo chính và một nhóm thước đo độ vững trước khi đo.** Không được chọn thước đo "chạy được" sau khi thấy H1.

| Tầng | Thước đo | Cách tính | Cần căn chỉnh | Vai trò | Ưu tiên | Nguồn |
|---|---|---|---|---|---|---|
| 0. Thay đổi cấu trúc (sự thật nền) | Δbậc; số cạnh mới; Jaccard lân cận 1 bước; thay đổi lân cận 2 bước | Đếm trực tiếp trên snapshot | Không | Biến kiểm tính hợp lệ (G16); biến phơi nhiễu phụ | BB | — |
| 1. Hình học | δ_time | Trung vị theo 3 seed của 1 − cos giữa vector đã căn ở T và vector ở T+1, cùng seed | Có | Thành phần của thước đo chính | BB | [ĐK protocol `raw_metric`] |
| | Khoảng cách L2 sau căn chỉnh | Độ dài của hiệu giữa vector đã căn ở T và vector ở T+1 | Có | Độ vững (TransE dựa trên L2) | TC | [ĐX] |
| 2. Hiệu chỉnh nhiễu | Signed excess r | δ_time − trung vị null của nhóm | Có | Báo cáo bắt buộc | BB | [ĐK protocol `report_signed_raw_excess`] |
| | **SED⁺** | max(0, r) / (1,4826 · MAD(null) + ε), ε = 1e-4; coi là phát hiện khi SED⁺ ≥ 2 | Có | **Thước đo chính** | BB | [ĐK protocol, S5] |
| | Bách phân vị thực nghiệm | Vị trí của δ trong phân phối null cùng nhóm | Có | Độ vững, không giả định hình dạng phân phối | N | [ĐX] |
| 3. Không cần căn chỉnh | Chồng lấn k láng giềng gần nhất | 1 − (số láng giềng chung trong top-k ở T và T+1)/k, so với cùng chỉ số giữa hai seed của cùng snapshot | Không | Độ vững chính (tránh lỗi căn chỉnh) | N | [TL] Wendlandt 2018 (k = 10); Gonen 2020 (danh sách dài thì ổn định hơn) |
| | Tương đồng bậc hai | 1 − cos giữa hai vector độ tương đồng tới hợp các láng giềng ở hai thời điểm, k = 25 | Không | Độ vững | TC | [TL] Hamilton và cộng sự 2016a, theo Shoemark 2019 |
| 4. Chức năng | Trôi thứ hạng | Thay đổi thứ hạng của các fact cũ của thực thể giữa mô hình T và T+1 | Không | **Chỉ mô tả.** Không dùng làm biến phơi nhiễu H1, vì cùng cơ chế xếp hạng với RR | TC | [ĐX] |
| | Chồng lấn dự đoán | Chồng lấn top-k đuôi dự đoán cho (e, r, ?) giữa hai thời điểm, so với giữa hai seed | Không | Chỉ mô tả, cùng lý do trên | TC | [TL] Méroué 2026 (preprint) |
| 5. Quần thể | Tỷ lệ excess > 0; tỷ lệ SED⁺ ≥ 2; khác biệt phân phối của δ so với null | Như S6 | — | Báo cáo mức quần thể | BB | [ĐK S5] |

**Chuẩn chung cho mọi thước đo**
- Mỗi thước đo có null riêng (cùng snapshot, khác seed) và kết quả đối chứng dương riêng (G16).
- Báo cáo theo từng nhóm bậc, không chỉ số gộp.
- Gộp lên mức câu hỏi bằng trung vị trên các thực thể hỗ trợ khác nhau, và chỉ khi đủ hỗ trợ [ĐK protocol].
- Thước đo độ vững chỉ được dùng để **xác nhận chiều** của kết quả chính, không được thay kết quả chính.

**Lưu ý**
- [TL] Dubossarsky 2017: trong đối chứng không có thay đổi thật, **mọi** điểm thay đổi vẫn dương và có ý nghĩa thống kê. Tần suất giải thích 56% phương sai trong đối chứng, so với 67% ở dữ liệu thật. Vì vậy mức thay đổi thô không bao giờ là bằng chứng; chỉ phần vượt đối chứng mới được tính.
- Tần suất, tương ứng với bậc trong KG, là biến gây nhiễu chính của mọi thước đo dựa trên embedding. [TL] Wendlandt 2018: từ xuất hiện 100–200 lần vẫn thường bất ổn. [TL] Shoemark 2019: huấn luyện embedding với tần suất tối thiểu 500 trong mỗi khoảng, và chỉ xét ứng viên thay đổi xuất hiện ≥ 500 lần ở ít nhất 75% số khoảng. Các con số này **chỉ để so sánh định tính**: số lần xuất hiện của một từ và bậc của một thực thể không cùng thang, nên không chuyển thẳng thành ngưỡng bậc (RV-17).
- **Rủi ro còn mở (RV-16).** SED⁺ chỉ giữ phần dương, nên phần lớn quan sát bằng 0 và biến phơi nhiễu D có phương sai rất nhỏ (N1: độ lệch chuẩn 0,03–0,11). Điều này làm mất sức mạnh thống kê. Phương án là dùng excess chuẩn hóa có dấu làm biến phơi nhiễu chính hoặc phụ, nhưng protocol đã chốt `standardization: positive_part_median_MAD`, nên muốn đổi cần [AM]. Người dùng quyết định.

### G16. Hiệu chuẩn phép đo

**Mục tiêu.** Chứng minh thước đo:
- phát hiện được thay đổi biết trước;
- không báo nhầm khi không có thay đổi;
- tăng theo mức thay đổi cấu trúc.

**1. Đối chứng âm (không có thay đổi thật)**

| Mã | Cách dựng | Kỳ vọng | Ưu tiên | Nguồn |
|---|---|---|---|---|
| NC1 | Drift giả cùng snapshot: các cặp seed ở snapshot trước đóng vai "thời gian", các cặp seed ở snapshot sau làm tham chiếu | Tỷ lệ excess > 0 nằm trong [0,40; 0,60]; tỷ lệ phát hiện gộp ≤ 0,10 [ĐK S5]. Mục tiêu chặt hơn: ≤ 0,05 [ĐX] | BB | [ĐK protocol `falsification: same_snapshot_pseudo_drift`] |
| NC2 | Hai mẫu bootstrap theo bài báo trong cùng snapshot | Như NC1 | N | [ĐX; TL Antoniak & Mimno] |

Đối chứng "trộn thời gian" của Dubossarsky không áp dụng trực tiếp cho KG tích lũy: trộn dấu thời gian thì đồ thị vẫn lớn lên giữa các snapshot, nên vẫn có thay đổi thật. Xem review, phát hiện RV-03.

**2. Đối chứng dương (thay đổi biết trước).** Bơm vào bản sao của snapshot sau, rồi huấn luyện lại 3 seed với cùng cấu hình.

| Mã | Kịch bản | Cường độ | Vì sao cần | Ưu tiên |
|---|---|---|---|---|
| PC1 | **Thêm k cạnh mới** cho thực thể đích, nối tới thực thể đã có, đúng kiểu ontology. Đầu kia và quan hệ của cạnh mới lấy theo **phân phối thực nghiệm của các fact mới thật** trong transition đó (chỉ dùng cấu trúc, mù kết quả). Báo thêm kết quả khi chọn đầu kia ngẫu nhiên đều (RV-11) | +25%, +50%, +100% bậc, tối thiểu +1 [ĐX] | Giống cách KG tích lũy thật sự thay đổi | **BB** |
| PC2 | Viết lại: thay đầu kia của một phần cạnh | 0,25 / 0,5 / 1,0 [ĐK N1] | Kịch bản đã dùng ở S5/N1; giữ để so sánh | BB |
| PC3 | Thay đổi gián tiếp: thêm cạnh cho hàng xóm, không đụng thực thể đích | như PC1 | Đo mức lan truyền; tách drift trực tiếp với gián tiếp | N |
| PC4 | Đổi quan hệ trên cạnh có sẵn (đổi vai trò) | 25% / 50% số cạnh | Thay đổi nghĩa mà không đổi lân cận | TC |

**Quy tắc chung khi bơm**
- Chọn thực thể bơm theo thứ tự SHA-256 trong từng nhóm bậc (mù kết quả).
- Tỷ lệ bơm 10–25% mỗi nhóm (S5 dùng 0,10; N1 dùng 0,25 với tối thiểu 3). Báo cáo độ nhạy theo tỷ lệ bơm, vì thực thể bơm cũng nằm trong tập anchor và có thể làm lệch căn chỉnh.
- Bơm ở **mọi** transition dùng được. S5 chỉ bơm ở 2 transition, quá ít.
- FPR tính trên các thực thể không được bơm và không chạm vào cạnh bị đổi.

**3. Kịch bản gây nhiễu (không được báo là drift)** [ĐX]. [TL: Shoemark 2019 dùng 4 kịch bản thay đổi thoáng qua bên cạnh 3 kịch bản thay đổi thật.]

| Mã | Kịch bản | Kỳ vọng | Ưu tiên |
|---|---|---|---|
| DC1 | Thêm bản sao của fact đã có | Không làm tăng tỷ lệ phát hiện | N |
| DC2 | Đổi thứ tự triple trong dữ liệu đầu vào | Tỷ lệ phát hiện ≤ FPR nền (tác động tương đương nhiễu seed) | TC |
| DC3 | Đồ thị lớn lên ở nơi khác, cách thực thể đích ≥ 3 bước | Tỷ lệ phát hiện ≤ FPR nền | N |

**4. Tính hợp lệ cấu trúc** [ĐX]
- Tương quan hạng giữa thước đo và mức thay đổi lân cận (tầng 0) phải lớn hơn tương quan tương ứng trong đối chứng NC1.
- Phải có quan hệ liều–đáp: cường độ bơm càng cao thì tỷ lệ phát hiện càng cao, và tăng đơn điệu.

**5. Luật quyết định**
- `testable_large`: độ nhạy ở cường độ 1,0 ≥ 0,80 và FPR ≤ 0,10, ở mọi E [ĐK N1].
- `testable_moderate`: độ nhạy ở cường độ 0,5 ≥ 0,50 và FPR ≤ 0,10, ở mọi E [ĐK N1].
- H1 được coi là kiểm định được khi đạt `testable_large` ở mọi E, **và** có ≥ 100 quan sát mang thông tin, **và** có ≥ 5 cụm [ĐK N1 `testable_if`].
- Bổ sung [ĐX]: PC1 đạt độ nhạy ≥ 0,50 ở mức +100% bậc trong quần thể lõi; DC1 và DC3 không vượt FPR nền.
- Nếu muốn dùng kết quả đối chứng dương trên dữ liệu thật để thu hẹp quần thể theo nhóm bậc, luật đó phải được đăng ký **trước khi** chạy đối chứng dương trên dữ liệu đó. N1 đăng ký quần thể bậc ≥ 3 sau khi đã thấy kết quả S6 theo nhóm bậc, và đã công bố điều này; không nên lặp lại cách đó (RV-20).

**Sự cố thường gặp:** kịch bản bơm cực đoan, không giống thực tế (thay 100% lân cận; R25); FPR tăng theo E (N1: 4,3% → 9,0% → 17,0%); chỉ bơm ở 2 transition; δ và null khác cấu trúc ước lượng (R24).

**Sản phẩm:** bảng độ nhạy và FPR theo nhóm bậc × cường độ × E × kịch bản; đường cong liều–đáp.

---

## Khối E. Đánh giá và công bố

### G17. Bộ câu hỏi đa bước

**Các bước**
1. **Sinh đường đi** từ snapshot as-of và đặt câu tiếng Việt theo mẫu của chuỗi quan hệ.
2. **Lọc đường tắt:**
   - câu trả lời được chỉ bằng một quan hệ trực tiếp;
   - đường đi tới rồi quay lui qua cạnh đối xứng;
   - đường đi qua thực thể chung chung;
   - đường dùng cặp nghịch đảo.
3. **Đặt trần:** mỗi head ≤ 3 câu [ĐK N1]; mỗi đáp án chiếm ≤ 5% số câu [ĐX].
4. **Panel theo cohort:** câu vào panel ở snapshot đầu tiên mà nó khả thi, rồi được theo dõi ở mọi transition sau đó [ĐK N1 `panel_unit`; ý tưởng từ mục D5 của kế hoạch]. Quần thể H2 Seen-at-T1 giữ theo protocol. Muốn đổi định nghĩa này cần [AM].
5. **Xếp hạng lọc** (loại mọi đáp án đúng khác). Quy tắc OOV đã đóng băng: ứng viên chưa thấy nhận điểm −∞; đáp án OOV có RR = 0 [ĐK protocol].
6. **Duyệt nghĩa bằng tay** ≥ 50 câu; tỷ lệ sai nghĩa ≤ 10% [ĐX].
7. **Báo cáo thêm RR phân tầng theo độ phổ biến của đáp án** [TL: Mohamed 2020: MRR và Hits nghiêng về các thực thể phổ biến].

**Cổng ra.** Đủ Q câu mỗi transition [MP]; không transition nào vượt 2 × trung vị [ĐX]; khâu duyệt nghĩa đạt.

**Sự cố thường gặp:** câu hỏi dồn vào vài hub (L25: 5 đáp án chiếm 66% số câu); panel lệch (L18); cạnh sai nghĩa làm đáp án sai (L26); quan hệ một-nhiều nhưng không lọc các đáp án đúng khác.

**Sản phẩm:** panel đã đóng băng (có hash), mẫu duyệt, báo cáo phân bố.

### G18. Phân tích thống kê

**Các bước**
1. **Mô hình chính:** TWFE với hiệu ứng cố định theo câu hỏi và theo transition [ĐK protocol].
2. **Suy luận:** wild cluster bootstrap theo transition, trọng số Webb, 9.999 lần [ĐK N1]. Báo cáo kèm MDE₈₀.
3. **Falsification:** thay D bằng drift giả cùng snapshot [ĐK protocol].
4. **Độ vững đã đăng ký.** Gồm đủ danh sách `statistics.sensitivity` của protocol (RV-07):
   - bỏ lần lượt từng transition (`LOTO`);
   - `delta_RR_stable_subset`;
   - `mean_max_query_drift`;
   - signed excess (`signed_raw_excess`);
   - một biến kiểm soát đăng ký trước (`one_pre_specified_covariance`, xem bước 5).

   Thêm các mục của N1: tách theo số bước, bỏ trần head, E ∈ {300, 400, 500}, kiểm soát log bậc.
5. **Mô hình phụ: kiểm soát độ bất ổn nền của thực thể** [ĐX; dùng để điền `one_pre_specified_covariance` và `controls: TO_BE_FROZEN_W5`].
   - Mô hình chính giữ **không có biến kiểm soát**, vì wild bootstrap hạn chế chỉ hợp lệ khi đó [ĐK N1 `model_primary`; RV-06].
   - Mô hình phụ thêm biến kiểm soát là nhiễu cùng snapshot, khác seed của các thực thể hỗ trợ tại T, bằng cách chiếu Frisch–Waugh như `model_control` của N1.
   - Biến này được đo trước transition nên không bị transition tác động. Lý do: ở N1, signed excess có β âm (p ≈ 0,05). Điều này có thể chỉ phản ánh rằng thực thể vốn bất ổn thì vừa có δ lớn vừa có RR thấp, chứ không phải do drift.
6. **Luật E-robust:** chỉ kết luận khi dấu của hệ số và lớp ý nghĩa (p < 0,05 hay không) giống nhau ở cả ba mức E [ĐK N1].

**Cổng ra.** Kết luận đúng theo luật đã đăng ký; mọi phân tích khác được dán nhãn thăm dò.

**Sự cố thường gặp:** biến phơi nhiễu gần như hằng (N1: độ lệch chuẩn 0,03–0,11; R28); ít cụm hoặc cụm lệch; nhiều phép so sánh; nhân quả ngược (R29).

**Sản phẩm:** báo cáo H1/H2, bảng độ vững, manifest.

### G19. Đóng băng, báo cáo và lưu trữ

**Các bước**
1. **Freeze (W7):** cây làm việc sạch, manifest không còn placeholder, gắn tag [ĐK `docs/gates_and_freeze.md`].
2. **Không truy cập `data/locked_test/` trước W8** [ĐK AGENTS §8.2].
3. **Viết datasheet cho bộ dữ liệu:** nguồn, khoảng thời gian, quy trình, giới hạn, phân bố, giấy phép nội dung (chỉ phát hành triple, URL, hash và đoạn bằng chứng ngắn), những cách dùng không nên. Ghi rõ về thông tin cá nhân: thực thể Person chỉ là người của công chúng xuất hiện trong tin, không lưu thuộc tính nhạy cảm [TL: Gebru và cộng sự, *Datasheets for Datasets*].
4. **Báo cáo mọi kết quả**, kể cả NOT_TESTABLE. Kết quả cũ bị thay thế phải ghi rõ là "superseded".
5. **Cập nhật** `docs/PROGRESS.md`, decision log và amendment.

**Cổng ra.** `python scripts/verify_w7.py --ci` PASS trên cây sạch; có datasheet.

---

## Phụ lục A. Sổ rủi ro (các vấn đề có thể gặp)

| Mã | Vấn đề | Giai đoạn | Dấu hiệu phát hiện | Phòng ngừa | Đã gặp ở dự án |
|---|---|---|---|---|---|
| R01 | Thời điểm crawl bị dùng làm thời điểm bằng chứng | G9 | Snapshot cuối dài < 1 ngày; nhiều fact cùng ngày crawl | Cấm theo luật; kiểm "0 fact có căn cứ là crawl" | F1 |
| R02 | Bài bị sửa sau khi đăng nên fact bị ghi ngày quá sớm | G9 | `dateModified` > `datePublished` | So với bản Wayback sớm nhất; dùng `dateModified` hoặc loại | Chưa kiểm |
| R03 | Độ trễ Wayback đẩy fact sang snapshot sau | G9, G11 | Lệch giữa hai căn cứ thời gian | Một căn cứ thống nhất; khoảng ≥ 5 × p90 độ trễ | L27 |
| R04 | Ranh giới cắt ngang nhóm cùng thời điểm | G11 | Kiểm tie | Luật tie-safe | F2 (đã sửa) |
| R05 | Parser bắt nhầm khung trang | G5 | Thân bài rất ngắn, lặp ở nhiều URL | Parser theo nguồn và kiểm tay | F12, F10 |
| R06 | Lọc phạm vi không tái lập được | G5 | Mã lý do không có trong chính sách | Một luật duy nhất trong file chính sách | L03 |
| R07 | Crawl sót theo tháng | G4 | Tốc độ sự kiện chênh lớn | Đo độ phủ theo tháng | L28 (chưa rõ nguyên nhân) |
| R08 | Trích xuất sót | G6, G7 | Nhiều bài 0 fact; số fact không tăng theo độ dài | Đo recall trên gold; đọc toàn bài | F13 |
| R09 | Sai chiều, sai loại quan hệ | G7 | Kiểm kiểu; duyệt mẫu | Kiểm kiểu tự động; gold đếm riêng lỗi này | L26 |
| R10 | Mô hình LLM đổi hành vi mà vẫn giữ tên | G7 | Jaccard giữa các lần chạy lặp giảm | Ghi metadata; bộ đệm là nguồn sự thật | Chưa gặp |
| R11 | Tin đồn bị ghi thành fact khẳng định | G7 | Duyệt mẫu | Cờ dự kiến/phủ định; kiểm trên gold | L26 (nghi ngờ) |
| R12 | Thực thể chung chung thành hub giả | G8 | Từ chung có bậc cao bất thường | Danh sách chặn | F4 |
| R13 | Gộp nhầm hoặc tách nhầm thực thể | G8 | Mẫu duyệt | Luật gộp và người duyệt | F4 |
| R14 | Ánh xạ dùng thông tin tương lai | G8 | Id thực thể đổi giữa các snapshot | `mapping_available_at` | Đề xuất đã bị hoãn ở S2 |
| R15 | Quan hệ trạng thái bị lưu song song | G10 | Nhiều CEO cùng lúc | Khóa logic theo ontology | F3 |
| R16 | Đồ thị quá thưa | G12 | A1 thấp | Thiết kế ngược (G1) | F8, L15 |
| R17 | Tăng trưởng chủ yếu là thực thể mới | G12 | A2, A3 thấp | Đọc toàn bài; dùng quần thể lõi | L24 |
| R18 | Đồ thị phân mảnh | G12 | A7 thấp | Ưu tiên quan hệ nối với hub | L16 |
| R19 | Snapshot đầu quá nhỏ | G11, G13 | MRR có CI rộng ở T01 | Ngưỡng M₀ | L17 |
| R20 | Đường tắt qua quan hệ đối xứng hoặc nghịch đảo | G2, G17 | Câu đi tới rồi quay lui | Lọc đường tắt | L25 |
| R21 | Embedding chưa hội tụ | G13 | Loss hoặc nhiễu vẫn còn giảm | Cổng hội tụ | F6 |
| R22 | Nhiễu seed gần mức ngẫu nhiên | G13 | 1 − cos trên holdout ≈ mốc ngẫu nhiên | Cổng ổn định | F7 |
| R23 | Nhóm bậc cao quá ít anchor, bị gộp, làm SED⁺ lệch | G14 | Có gộp nhóm | A5 | F11 |
| R24 | δ và null khác cấu trúc ước lượng | G14 | FPR tăng theo E | Chuẩn mực 11 | N1 (giả thuyết) |
| R25 | Đối chứng dương không giống thay đổi thật | G16 | Chỉ có kịch bản viết lại cạnh | PC1 bắt buộc | S5, N1 |
| R26 | Câu hỏi dồn vào hub | G17 | Một đáp án chiếm > 5% | Trần đáp án; RR phân tầng | L25 |
| R27 | Panel lệch, ít cụm | G17, G18 | Một transition chiếm đa số câu | Cân bằng | L18, L19 |
| R28 | Biến phơi nhiễu gần như hằng | G18 | Độ lệch chuẩn rất nhỏ | Thiết kế ngược | N1 |
| R29 | Nhiễu riêng của thực thể gây tương quan giả | G18 | Signed excess "có ý nghĩa" | Biến kiểm soát độ bất ổn nền | N1 |
| R30 | Chọn sau khi xem kết quả (nhiều lối rẽ) | Mọi giai đoạn | Đổi thước đo hoặc ngưỡng sau khi có kết quả | Đăng ký trước; dán nhãn thăm dò | L23 |
| R31 | Lệch schema | G10 | Kiểm hợp đồng dữ liệu | Kiểm schema tự động | L21 |
| R32 | GPU không tái lập từng bit | G13 | Hash checkpoint khác nhau | Chính sách tái lập | Chưa gặp |
| R33 | Chi phí API vượt trần | G6, G7 | Sổ chi phí | Trần cứng; dự trữ chi phí trường hợp xấu nhất | Chưa gặp |
| R34 | Nguồn đổi giao diện hoặc chặn crawl | G4, G5 | Lỗi parser tăng | Parser theo phiên bản giao diện | Chưa gặp |
| R35 | Đụng tới tập kiểm tra khóa quá sớm | Mọi giai đoạn | Có truy cập `data/locked_test/` | Cấm tới W8 | Chưa gặp |
| R36 | Công cụ môi trường bị chặn (ví dụ chính sách Windows chặn thư viện của Python) | Mọi giai đoạn | ImportError khi nạp DLL | Báo người dùng; không tìm đường vòng | Gặp ngày 2026-11-22 |

## Phụ lục B. Bảng kiểm tổng hợp

| Giai đoạn | Mục kiểm | Ngưỡng | Nhãn | Ưu tiên |
|---|---|---|---|---|
| G0 | Estimand, SESOI, MDE, ngữ nghĩa KG, luật rẽ nhánh có trong decision log | có | [ĐX] | BB |
| G6a | Pilot trên kho bài đã có, chạy trước G1 | GO/NO-GO theo X1 | [ĐK X1] | BB |
| G1 | Vùng khả thi khác rỗng; có k\*, M, M₀, K, Q, N_core | có | [MP] | BB |
| G1 + G6a | Cổng đầu tư (mục 2.3) | có quyết định ghi lại | [ĐX] | BB |
| G2 | Cặp nghịch đảo / trùng nghĩa | 0 | [ĐX] | BB |
| G2 | Số triple mỗi quan hệ ở snapshot cuối | ≥ 50 | [ĐX] | N |
| G3 | Trang có `datePublished` kèm múi giờ | ≥ 95% | [ĐX] | BB |
| G4 | Độ phủ theo tháng, theo nguồn | ≥ 90% | [ĐX] | BB |
| G5 | Bài lấy nhầm khung (kiểm 30 bài mỗi nguồn) | 0 | [ĐX] | BB |
| G6 | F1 giữa người gán | ≥ 0,70 | [ĐK X1] | BB |
| G6 | Precision; cận dưới CI95; recall; fact đúng/bài; câu bằng chứng khớp | ≥ 0,85; ≥ 0,75; ≥ 0,60; ≥ 2,5; ≥ 0,95 | [ĐK X1] | BB |
| G7 | Tỷ lệ bài lỗi cuối | ≤ 1% | [ĐX] | N |
| G7 | Tỷ lệ claim vi phạm kiểu, tính trước khi lọc | ≤ 5%, có báo cáo | [ĐX] | BB |
| G8 | Thực thể chung chung trong 100 thực thể lấy ngẫu nhiên | ≤ 1% | [ĐX] | BB |
| G8 | Độ chính xác liên kết thực thể (≥ 100 mention) | ≥ 0,90 | [ĐX] | BB |
| G8 | Tỷ lệ sự kiện bị loại, theo từng nguyên nhân | ≤ 5% mỗi nguyên nhân; tổng chỉ công bố | [ĐK `s2_quarantine_thresholds_per_cause_20261118`] | BB |
| G9 | Fact có căn cứ là thời điểm crawl | 0 | [ĐK S1] | BB |
| G9 | Trung vị \|Δ\| kiểm chéo | ≤ 15 ngày | [ĐK S1] | BB |
| G9 | Tỷ lệ fact đổi snapshot nếu dùng căn cứ còn lại | ≤ 2% | [ĐX] | N |
| G10 | Bảng khớp schema | 17/17 | [ĐK] | BB |
| G11 | Số snapshot | 8–12 | [ĐK protocol] | BB |
| G11 | Độ dài khoảng; không cắt tie | ≥ 14 ngày; 0 | [ĐK S1] | BB |
| G11 | Cân bằng giữa các transition | ≤ 2 × trung vị | [ĐX] | N |
| G12 | A1b, A3, A5, A7, A8 đạt; A1, A2, A6 có báo cáo | xem G12 | [ĐX]/[MP] | BB |
| G13 | Cổng chất lượng, tái lập, ổn định | PASS | [ĐK R1] | BB |
| G14 | Chẩn đoán căn chỉnh | sai số trực giao ≤ 1e-6; hạng ≥ 0,90; chênh lệch ≤ 0,65 | [ĐK S5] | BB |
| G14 | Số tham chiếu null mỗi nhóm | ≥ 50 | [ĐK S5] | BB |
| G16 | NC1: excess > 0; tỷ lệ phát hiện | [0,40; 0,60]; ≤ 0,10 | [ĐK S5] | BB |
| G16 | `testable_large` ở mọi E; ≥ 100 quan sát; ≥ 5 cụm | đạt | [ĐK N1] | BB |
| G16 | PC1 ở +100% bậc | độ nhạy ≥ 0,50 | [ĐX] | BB |
| G17 | Trần mỗi head; trần mỗi đáp án | ≤ 3; ≤ 5% | [ĐK N1]; [ĐX] | BB |
| G17 | Tỷ lệ sai nghĩa (≥ 50 câu) | ≤ 10% | [ĐX] | BB |
| G18 | Luật E-robust; falsification | theo đăng ký | [ĐK N1] | BB |
| G19 | `verify_w7.py --ci` trên cây sạch; datasheet | PASS; có | [ĐK] | BB |

## Phụ lục C. Mốc tham chiếu từ tài liệu

Bậc trung bình tính bằng 2 × số triple / số thực thể. Các bộ được đánh dấu "(thứ cấp)" lấy số liệu qua bảng tổng hợp của bài khác. Các bài khác nhau có thể báo số thực thể khác nhau.

| Bộ | Cách dựng | Thực thể | Quan hệ | Triple | Bậc TB |
|---|---|---|---|---|---|
| FB15k-237 | Cụm thực thể phổ biến của Freebase; bỏ quan hệ nghịch đảo | 14.541 | 237 | 310.116 | 42,7 |
| WN18RR | WordNet, bỏ quan hệ nghịch đảo (thứ cấp) | 40.943 | 11 | 93.003 | 4,5 |
| YAGO3-10 | Thực thể có ≥ 10 quan hệ khác nhau (thứ cấp) | 123.182 | 37 | ~1,09 triệu | ~18 |
| CoDEx-S / CoDEx-M | Wikidata | 2.034 / 17.050 | 42 / 51 | 36.543 / 206.205 | 35,9 / 24,2 |
| NELL165 | Trích từ văn bản web; precision 0,35 (Pujara 2017) | — | 221 | ~1 triệu | 3 |
| ICEWS14 | Tin tức, mã hóa tự động bằng từ điển chủ thể và bộ CAMEO (thứ cấp) | ~6.900–7.100 | 230 | ~90.700 trong 1 năm (số triple lấy từ trí nhớ, chưa kiểm) | ~25 (suy ra từ số triple trên) |
| LKGE ENTITY | FB15k-237 chia thành 5 snapshot; mỗi fact mới chứa ≥ 1 thực thể đã có; tách 3:1:1 | 2.909 → 14.541 | 237 | thêm 46–74 nghìn mỗi snapshot | 42,7 (snapshot cuối) |
| VLSP 2020 RelEx | Tin tiếng Việt, 4 loại quan hệ | — | 4 | ~5.900 quan hệ trên 1.056 bài (~5,6/bài) | — |
| DocRED / Re-DocRED | Wikipedia, 96 loại quan hệ | — | 96 | 12,5 → ~29,8 triple/văn bản | — |
| **v3.3 (T10)** | Tin tức, trích bằng LLM, 10 quan hệ | 1.286 | 10 | 1.098 | **1,7** |

**Bài học rút ra**
1. Các bộ chuẩn được cố ý làm dày bằng cách giữ những thực thể phổ biến (Pujara 2017; YAGO3-10).
2. KG trích từ văn bản vừa thưa vừa nhiễu. Trên NELL165, embedding còn thua cả mốc cơ bản là xếp theo độ tin cậy của bộ trích xuất.
3. Các bộ chuẩn về KG tiến hóa bắt fact mới phải nối vào thực thể đã có (LKGE).
4. Gán nhãn lại thường tìm được nhiều fact hơn hẳn (Re-DocRED gấp khoảng 2,4 lần DocRED).
5. Bộ chuẩn nào cũng từng có đường tắt (quan hệ nghịch đảo, quan hệ trùng, quan hệ đoán được bằng tần suất) và về sau phải sửa.

## Phụ lục D. Áp dụng cho hai nhánh dữ liệu

| Giai đoạn | Nhánh A: tin tức tiếng Việt (v4) | Nhánh C: bộ dày có sẵn (ví dụ ICEWS14) |
|---|---|---|
| G3–G5 | Như phần chính | Thay bằng: tải bộ dữ liệu, kiểm hash, ghi nguồn. Cách tải phải hợp luật "không API" [AM] |
| G6–G8 | Bắt buộc | Bỏ qua, vì dữ liệu đã được mã hóa sẵn bằng từ điển. Phải ghi giới hạn về chất lượng của mã hóa tự động |
| G9 | Ngày đăng hoặc Wayback | **Giả định** thời điểm sự kiện = thời điểm có bằng chứng. Ghi rõ đây là giả định, yếu hơn nhánh A |
| G11 | Tích lũy, cân bằng sự kiện hoặc theo lịch | Dữ liệu là **sự kiện thoáng qua** (gặp gỡ, tuyên bố) lặp lại nhiều ngày. Snapshot tích lũy sẽ bão hòa nhanh: cặp thực thể nào cũng đã gặp từ sớm, nên các mốc sau hầu như không còn cạnh mới. Phải kiểm A3; nhiều khả năng cần **cửa sổ trượt** gom theo khoảng (ví dụ 30 ngày) |
| G12–G18 | Như phần chính | Như phần chính. Đây là nơi kiểm định phương pháp khi đã có đủ độ nhạy |
| Vai trò | Trường hợp thực tế, trục thời gian sạch | Kiểm định phương pháp và làm thang độ dày |

**Thang độ dày** [ĐX]. Lấy mẫu con của nhánh C ở nhiều mức bậc trung bình, từ khoảng 1,7 (như v3.3) lên tới mức đầy đủ, giữ nguyên mọi yếu tố khác. Sau đó đo độ nhạy theo độ dày. Đây là thí nghiệm có kiểm soát duy nhất trả lời được câu "đồ thị cần dày tới đâu" [TL: cách làm thưa hóa "sparse/stable" của Pujara 2017].

## Phụ lục E. Ước lượng thời lượng (một người, ước lượng thô)

| Giai đoạn | Thời lượng | Phụ thuộc |
|---|---|---|
| G0–G1 | 1–2 tuần | Cần bộ huấn luyện nhanh |
| G2–G3 | 3–5 ngày | Amendment |
| G4–G5 | 0 ngày (dùng dữ liệu thô có sẵn) đến 2 tuần (nguồn mới) | — |
| G6 | 1–2 tuần | Người gán nhãn (O3) |
| G7 | 2–4 ngày | API key, ngân sách |
| G8–G10 | 1–1,5 tuần | Người duyệt bảng gộp; sửa schema |
| G11–G12 | 2–3 ngày | — |
| G13–G16 | 1–2 tuần nếu có bộ huấn luyện vector hóa. Với bộ Python thuần hiện tại có thể lâu hơn nhiều (chưa đo) | Phụ lục H |
| G17–G18 | 1 tuần | Duyệt nghĩa câu hỏi |
| G19 | 2–3 ngày | — |
| **Tổng** | **khoảng 8–12 tuần**, với điều kiện đã có bộ huấn luyện nhanh | Chưa tính thời gian chờ duyệt, chờ người gán nhãn và thời gian huấn luyện thực tế (Phụ lục H) |

## Phụ lục F. Những gì cần quyết định hoặc amendment trước khi áp dụng

1. SESOI và MDE mục tiêu (G0).
2. Ngữ nghĩa KG: giữ tích lũy, hay thêm thay thế phiên bản cho quan hệ trạng thái (G0, G2, G10).
3. Ontology mới nếu mở rộng: phiên bản `ontology_version` mới (G2).
4. Nguồn mới: amendment `sources.lock.json` (G3).
5. Căn cứ thời gian thống nhất P hay W: đổi quyết định `stage4_3_vnexpress_archive_time_semantics` (G9).
6. Sửa đăng ký X1 để thêm chỉ số chẩn đoán (G6, bước 6).
7. Các ngưỡng [ĐX] ở G2–G9, G11, G12, G16, G17.
8. Null bổ sung NC2; các kịch bản PC1, PC3, PC4, DC1–DC3. Tất cả đều tốn thêm tính toán.
9. Biến kiểm soát độ bất ổn nền (G18, bước 5), điền vào protocol `controls: TO_BE_FROZEN_W5`.
10. Giá trị d và chính sách tái lập khi dùng GPU (G13).
11. Hai mục đang chờ từ X1: O3 (người gán nhãn) và API key.
12. Có dùng excess chuẩn hóa có dấu thay cho SED⁺ phần dương làm biến phơi nhiễu hay không (RV-16) [AM].
13. Một người review độc lập cho khung này (RV-27).

## Phụ lục G. Tài liệu tham khảo

Đã đọc trực tiếp bản PDF, chỉ các trang về cách dựng dữ liệu, số liệu và phương pháp, của bốn bài: Pujara 2017 (trang 1–4), Cui 2023 / LKGE (trang 5–6), Dubossarsky 2017 (trang 3–6), Shoemark 2019 (trang 2–4). Phần còn lại của bốn bài này và toàn bộ các bài khác mới đọc phần tóm tắt hoặc thông tin thứ cấp (kết quả tìm kiếm, bảng tổng hợp của bài khác). Các số liệu từ nguồn thứ cấp cần được kiểm lại trước khi trích dẫn chính thức.

- Pujara, Augustine, Getoor (2017). Sparsity and Noise: Where Knowledge Graph Embeddings Fall Short. EMNLP. https://aclanthology.org/D17-1184/
- Cui và cộng sự (2023). Lifelong Embedding Learning and Transfer for Growing Knowledge Graphs. AAAI. https://arxiv.org/abs/2211.15845
- Dubossarsky, Weinshall, Grossman (2017). Outta Control: Laws of Semantic Change and Inherent Biases in Word Representation Models. EMNLP. https://aclanthology.org/D17-1118/
- Shoemark và cộng sự (2019). Room to Glo: A Systematic Comparison of Semantic Change Detection Approaches with Word Embeddings. EMNLP-IJCNLP. https://aclanthology.org/D19-1007/
- Hamilton, Leskovec, Jurafsky (2016). Diachronic Word Embeddings Reveal Statistical Laws of Semantic Change. ACL. https://aclanthology.org/P16-1141/
- Kulkarni và cộng sự (2015). Statistically Significant Detection of Linguistic Change. WWW. https://arxiv.org/abs/1411.3315
- Antoniak, Mimno (2018). Evaluating the Stability of Embedding-based Word Similarities. TACL. https://aclanthology.org/Q18-1008/
- Wendlandt, Kummerfeld, Mihalcea (2018). Factors Influencing the Surprising Instability of Word Embeddings. NAACL. https://aclanthology.org/N18-1190/
- Gonen và cộng sự (2020). Simple, Interpretable and Stable Method for Detecting Words with Usage Change across Corpora. ACL. https://aclanthology.org/2020.acl-main.51
- Schlechtweg và cộng sự (2019). A Wind of Change. ACL. https://arxiv.org/abs/1906.02979
- Schlechtweg và cộng sự (2020). SemEval-2020 Task 1: Unsupervised Lexical Semantic Change Detection. https://arxiv.org/abs/2007.11464
- Safavi, Koutra (2020). CoDEx: A Comprehensive Knowledge Graph Completion Benchmark. EMNLP. https://arxiv.org/abs/2009.07810
- Tan và cộng sự (2022). Revisiting DocRED – Addressing the False Negative Problem in Relation Extraction. EMNLP. https://aclanthology.org/2022.emnlp-main.580
- Mai và cộng sự (2020). Overview of VLSP RelEx shared task. https://aclanthology.org/2020.vlsp-1.17
- Mohamed và cộng sự (2020). Popularity Agnostic Evaluation of Knowledge Graph Embeddings. UAI. https://auai.org/uai2020/proceedings/440_main_paper.pdf (tên bài và tác giả lấy từ trí nhớ, cần kiểm lại)
- Schumacher và cộng sự (2021). The Effects of Randomness on the Stability of Node Embeddings. https://arxiv.org/abs/2005.10039
- Méroué, Gandon, Monnin (2026, preprint). Link Prediction or Perdition: the Seeds of Instability in Knowledge Graph Embeddings. https://arxiv.org/abs/2606.03365
- Ali và cộng sự (2021). Bringing Light Into the Dark: A Large-scale Evaluation of Knowledge Graph Embedding Models Under a Unified Framework. https://arxiv.org/abs/2006.13365 (năm và nơi đăng cần kiểm lại)
- Các bài đã có trong `reports/report_latex_final/references.bib`: Bordes 2013 (TransE); Schönemann 1966 (Procrustes); Cameron, Gelbach, Miller 2008; Webb 2014; MacKinnon, Webb 2017 (wild cluster bootstrap); Dettmers 2018 (WN18RR, ConvE).
- Gebru và cộng sự. Datasheets for Datasets. Communications of the ACM (2021).

## Phụ lục H. Ngân sách tính toán và gói tối thiểu

**Công thức đếm số lần huấn luyện**
- Huấn luyện gốc = số seed × số mức E × số snapshot.
- Đối chứng dương = số seed × số mức E × số transition được bơm × số biến thể cần huấn luyện lại riêng.
- NC2 (bootstrap) = số seed × số mức E × số snapshot × 2 mẫu.

**Ví dụ** với 10 snapshot, 9 transition, 3 seed, 3 mức E (huấn luyện gốc = 90 lần):

| Gói | Thành phần | Số lần huấn luyện |
|---|---|---|
| Tối thiểu, có gộp kịch bản | Gốc, cộng PC1 và PC2 bơm vào các tập đích rời nhau trong **cùng** một lần huấn luyện lại, ở 3 mức cường độ | 90 + 3 × 3 × 9 × 3 = **333** |
| Tối thiểu, không gộp | Gốc, cộng PC1 và PC2 huấn luyện riêng, mỗi cái 3 mức cường độ | 90 + 3 × 3 × 9 × 6 = **576** |
| Đầy đủ | Thêm NC2 (180 lần), PC3, PC4 và DC1–DC3 | **khoảng 750 trở lên**, tùy cách gộp |

**Cách tiết kiệm**
1. **Gộp kịch bản** vào các tập thực thể đích rời nhau trong cùng một lần huấn luyện lại. Điều kiện: các tập đích cách nhau ≥ 2 bước, để hạn chế nhiễu chéo. Phải báo cáo rủi ro nhiễu chéo.
2. **Dùng bộ huấn luyện vector hóa hoặc GPU**, nhưng chỉ sau khi:
   - qua kiểm tương đương trên v3.3: MRR khớp trong dung sai đã đăng ký, kết luận của các cổng R1 không đổi;
   - có chính sách tái lập (R32).
3. **Đo thời gian một lần huấn luyện trên snapshot lớn nhất** trước khi cam kết lịch.
4. **Gói tối thiểu là điều kiện cần cho kết luận về H1.** Các mục N và TC chỉ làm khi còn ngân sách.

**Gói tối thiểu gồm:** G0, G6a, G1, cổng đầu tư, G12, huấn luyện gốc, NC1 (không cần huấn luyện thêm vì dùng lại các cặp seed), PC1 + PC2, G17, G18.

## Lịch sử sửa đổi

| Phiên bản | Ngày | Thay đổi |
|---|---|---|
| v1.0-draft | 2026-11-22 | Bản đầu |
| v1.1-draft | 2026-11-22 | Sửa theo [review](audit/FRAMEWORK_v1_REVIEW_20261122.md): RV-01, RV-02, RV-04 đến RV-15, RV-17 đến RV-26, RV-28. RV-03 đã xử lý ngay ở v1.0. Còn mở: RV-16 (cần amendment) và RV-27 (cần người review độc lập) |
| v1.1-draft (hiệu chỉnh trích dẫn) | 2026-11-22 | Sửa 4 chỗ trích dẫn tài liệu trước khi đưa lên kho công khai (BS-1 đến BS-4, mục 6 của review): diễn giải Pujara 2017, ngưỡng tần suất của Shoemark 2019, mức độ đã đọc ở Phụ lục G, số triple ICEWS14 |
