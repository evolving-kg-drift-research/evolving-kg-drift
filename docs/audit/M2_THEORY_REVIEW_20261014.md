# Rà soát tính chính xác của tài liệu lý thuyết M2

Ngày: 14/10/2026. Commit đối chiếu: `cc411c628ea561b5f0a76e185a6c31a79ec13710`.
Phạm vi người dùng yêu cầu: rà soát và chỉ ra chỗ cần sửa; không sửa code,
protocol, configs đã bind hash hoặc artifacts thí nghiệm.

## Kết luận

Tài liệu đúng phần lớn về TransE-L2, margin-ranking loss, SGD per-triple,
multi-seed/repeats, SVD Procrustes, centered cosine của code hiện chạy,
median ba temporal seeds, signed excess, MAD và giới hạn inference.
Các số liệu 30 configurations/60 training executions, 81 alignments,
41.382 noise observations, 20.691 temporal observations, 6.897 drift rows,
3.640 r>0/3.257 r<0 và SED+ max 5,219441 khớp báo cáo đã lưu.

Tuyên bố quan trọng tại §11.4 về median-per-entity **được xác nhận bởi đề
cương PDF đang khóa**, dù file `02_Quy_trinh_KGE_va_do_drift` mà tài liệu
viện dẫn chưa tìm thấy trong workspace. Công thức (27)–(28) yêu cầu lấy một
median qua sáu distances cho mỗi entity, rồi dựng LTO null từ các medians của
entities khác. Code Dev tại `src/drift/artifact_null.py` lại pooling các
distances. Hai phép ước lượng không tương đương.

Lượt M2 trước xác minh arithmetic/lineage theo implementation Dev nhưng đã
bỏ sót đối chiếu estimator này với nguồn PDF. Verification receipts cũ vẫn
chứng minh đúng phạm vi tính toán đã ghi; chúng không chứng nhận scientific
conformance. Đây là thiếu sót cần ghi rõ, không chuyển nhãn các kết quả cũ
thành scientific PASS.

Tài liệu cần bổ sung ba vấn đề còn thiếu: mốc **50 entity-level observations**
đã có trong PDF; khác biệt giữa diagnostics Dev và diagnostics chuẩn hóa của
PDF; và tình trạng chưa hòa giải giữa centered-cosine estimand hiện chạy với
công thức affine-cosine của bản PDF nguồn. Không tự chọn một công thức khi
các nguồn có thẩm quyền chưa được đối chiếu đầy đủ.

## Nguồn và bằng chứng đã kiểm

- Input attachment: `C:/Users/ducan/.codex/attachments/a231a232-34b4-4538-b7e8-3428454a3c99/Pasted text.txt`,
  1.588 lines, SHA-256 `8059a29b893a3d034574454c40bc279c7c65cd5a242aa9b960055c7d41d8b867`.
- HEAD local khớp commit nêu trong tài liệu. Code/configs/reports của M2 đã
  commit; các untracked M1 files đang mở được giữ nguyên.
- `sources/huce_evolving_kg_modular_proposal(8).pdf`: SHA-256
  `d9e6d74b84fabdff880698eb6a5774bed8445897539b3713ba1e0594a446ea6f`,
  khớp `data/manifests/sources.lock.json` và `configs/protocol_v1.yaml`.
  Đã đọc đầy đủ PDF physical pages 6/7/13; page 7 hiển thị printed page 6.
  Render page 7 để kiểm trực quan các công thức (24)–(32).
- Hai source originals `sources/Research_Execution_Plan_v1.0.md` và
  `sources/Research_Execution_Plan_v1.1_Patch.md` có trong lock nhưng thiếu
  trên filesystem. Đây là giới hạn khi kết luận về mọi thay đổi protocol.
- `configs/protocol_v1.yaml` vẫn v1-draft, còn placeholders; YAML chưa biểu
  diễn rõ toàn bộ đơn vị null, diagnostics hoặc centered-cosine semantics.
- Đối chiếu `src/kge/model.py`, `trainer.py`, `src/drift/procrustes.py`,
  `artifact_null.py`, `artifact_drift.py`, fixed-anchor code và approved Dev
  config; audit matrix/fixtures được dùng làm bằng chứng implementation,
  không thay thẩm quyền của protocol/locked sources.
- Đọc `outputs/m2_null/20261014T042450Z_43e91590/lto_statistics.parquet`
  để kiểm reference entity counts; không reestimate null hay drift.
- Bằng chứng số học/fixture: `outputs/m2_theory_review_20261014/evidence.json`.
  Ví dụ tổng hợp chỉ dùng kiểm lý thuyết, không là production evidence.

## Các nội dung chính xác nên giữ

| Nội dung | Kết quả đối chiếu |
|---|---|
| TransE energy `||h+r-t||_2`, positive thấp hơn negative | Khớp `src/kge/model.py:86–95` |
| Negative sampling có rejection known positives, tối đa 100 attempts | Khớp `model.py:134–159`; KG thiếu vẫn có thể có false negatives |
| Epoch loss chia số triples đã duyệt, skipped negatives không góp numerator | Khớp `model.py:212`; mô tả §4.4 đúng |
| SGD per-triple, `batch_size=32` chưa tạo mini-batch updates | Khớp vòng lặp `model.py:115–212` |
| Shuffling và negative sampling có thể làm loss dao động | `rng.shuffle` tại `model.py:124`, sampling trong mỗi epoch |
| Pilot chọn 64 bằng validation/alignment, chưa chứng minh superiority | Khớp pilot config/summary; mean MRR 0,122906 vs 0,110916 |
| Centered Procrustes, `Q=UV^T` theo row-vector convention | Khớp code và PDF (18)–(21) |
| Fit/holdout 101/66, gap là trị tuyệt đối | Khớp fixed-anchor config và `procrustes.py:296` |
| Sáu endpoint cross-seed distances có tương quan | Đúng; không tự tạo sáu independent statistical units |
| `median(median-per-entity)` khác median pooled distances | Đúng; đã tái hiện bằng toy fixture bên dưới |
| Temporal median ba parallel seeds và signed r giữ âm | Khớp `artifact_drift.py:93–95` |
| Ví dụ SED+ 0,3/(1,4826×0,1+0,0001) ≈ 2,022 | Chính xác; giá trị đầy đủ 2,022108385... |
| MAD, hệ số Gaussian-reference scale, SED+ không là p-value | Đúng về lý thuyết; không tự suy ra Gaussian null |
| Loss/SED+/tests không tự chứng minh QA quality, causality hay gate PASS | Đúng và cần giữ |

## Findings và chỗ cần sửa

### M2-THEORY-001 — CRITICAL — Sai khác estimator null được nêu đúng, cần dẫn nguồn gốc trực tiếp

- **Affected:** attachment §11.4 (lines 880–923), §12.1, §16.3, bảng công thức
  §19 và quiz câu 4; `src/drift/artifact_null.py:151–158`.
- **Expected/invariant:** PDF §3.2.4 (27) lấy `n(e,g)=median(d_1,...,d_6)`;
  (28) dựng reference từ `n(e',g)` của entity khác, loại target.
- **Actual:** tài liệu đúng về khác biệt, nhưng viện dẫn tài liệu 02 chưa
  cung cấp path/hash/điều khoản kiểm được. Code pooling six distances per
  entity rồi median/MAD, chưa thực hiện entity-level reduction.
- **Evidence/repro:** fixture A=`[.1,.1,.1,.9,.9,.9]`, B=`[.1,.1,.1,.1,.1,.9]`:
  entity medians `.5,.1` cho center `.3`, MAD `.2`; pooled 12 distances cho
  center `.1`, MAD `0`. Target LTO trong helper hiện trả pooled values.
- **Root cause/hypothesis:** flattening ở `reference = [v ... for v in values[e]]`
  là xác nhận từ code. Chưa có nguồn amendment verified cho phép thay estimator;
  không đoán nội dung hai source MD còn thiếu.
- **Proposed minimal fix:** giữ cảnh báo, thay/bổ sung citation bằng PDF đã
  hash-match và (27)–(29). Gọi kết quả hiện tại là pooled-pairwise Dev
  estimator. Sửa implementation chỉ trong task riêng, sau hòa giải nguồn;
  output mới, giữ historical runs, không âm thầm thay số liệu hiện tại.
- **Regression/status:** toy arithmetic VERIFIED; chưa viết patch hoặc chạy
  remediation. Khi sửa cần regression phân biệt center/MAD hai estimators,
  bảo đảm all-six target exclusion, missing-data handling và lineage mới.
- **Remaining blockers:** source-plan/patch originals và explicit scope của
  remediation. Finding vẫn OPEN đối với scientific use.

### M2-THEORY-002 — HIGH — Tài liệu bỏ sót mốc 50 entity-level observations của nguồn đang khóa

- **Affected:** attachment §12.3–12.4 (lines 979–1021), §16.3;
  `configs/m2_external_dev_v1.yaml:50`, `artifact_null.py:117–158`.
- **Expected:** đoạn ngay sau PDF (31) nêu bucket dưới 50 entity-level
  observations phải mở rộng sang bucket lân cận hoặc conditional kNN;
  không dùng seed-pair rows như independent samples.
- **Actual:** tài liệu chỉ nêu `m_entity` cần chọn/khóa qua pilot và Dev có
  ít nhất 5 observations; chưa nói nguồn đang khóa đã có mốc 50. Config Dev
  đếm pooled pair distances, không có guard minimum reference entities.
- **Evidence:** kiểm inventory artifact thấy **355/6.897 LTO rows** có dưới
  50 reference entities: 17,30,39,49,68,72,24,26,30 theo 9 transitions.
  Đây là count của reference hiện tại, chưa là kết quả áp dụng merge/kNN mới.
- **Root cause/hypothesis:** khác đơn vị support confirmed. Chưa kết luận
  ngưỡng/fallback cuối cùng nếu source patch hợp lệ quy định khác.
- **Proposed fix:** ghi riêng mốc nguồn 50 entity-level observations và
  guard Dev 5 pairwise observations. Nếu muốn đổi mốc nguồn cần căn cứ
  formal registration/amendment; không mô tả nó như tham số chưa hề được đặt.
  Không tự tăng/giảm ngưỡng theo SED+ vừa quan sát.
- **Regression/status:** artifact inventory VERIFIED, không sửa policy.
  Regression remediation phải kiểm support sau target exclusion và khi
  reference chỉ còn một entity, entity-level MAD bằng 0.
- **Blockers:** policy merge/kNN và frequency features theo nguồn được
  reconcile; chỉ biết sparse status không tự chọn fallback mới.

### M2-THEORY-003 — GOVERNANCE — Cần đánh dấu chưa hòa giải centered cosine với công thức PDF

- **Affected:** attachment §9.4, §13.3, §19;
  `src/drift/artifact_drift.py:46–61`, `configs/protocol_v1.yaml:50`,
  `docs/audit/AUDIT_REMEDIATION_MATRIX.md:A19`.
- **Expected:** phân biệt fitting centered Procrustes và lựa chọn cosine
  estimand. Centering khi fit không tự xác định cosine phải dùng vector nào.
- **Actual:** code/Dev dùng `1-cos((x-mu_s)Q,y-mu_t)` và tài liệu mô tả đúng.
  PDF (14) định nghĩa affine `x'=(x-mu_s)Q+mu_t`; (26) viết
  `1-cos(x',y)`. Hai phép đo khác nhau. Audit A19/fixture yêu cầu centered,
  nhưng audit không tự supersede locked source; YAML còn chưa rõ và hai
  source MD originals thiếu.
- **Evidence/repro:** với Q=I, source `(1,0)`, source mean `(0,0)`, target
  `(10,11)`, target mean `(10,10)`: centered cosine displacement=1;
  affine-cosine displacement=`1-220/221`≈0,004525.
- **Root cause:** confirmed source/implementation semantic divergence;
  chưa xác nhận bên nào đã có amendment hợp lệ. Không gọi centered formula
  là lỗi toán học, cũng không tự chọn lại uncentered estimator.
- **Proposed fix:** thêm câu “Công thức ở đây mô tả code Dev hiện chạy;
  scientific registration của centered estimand cần hòa giải với nguồn gốc.”
  Stop mọi quyết định sửa metric cho tới khi authority được giải quyết.
- **Regression/status:** toy difference VERIFIED; existing A19 fixture
  kiểm translation invariance của code, không là bằng chứng source amendment.
- **Blockers:** authoritative original plans/patch và registration trace.

### M2-THEORY-004 — MEDIUM — Diagnostics hiện mô tả đúng Dev nhưng thiếu đối chiếu cách chuẩn hóa trong PDF

- **Affected:** attachment §10.3–10.5 (lines 774–818);
  `src/drift/procrustes.py:184–194,273–296`.
- **Expected:** khi so scientific thresholds, phải dùng đúng statistic và
  thang đo đã đăng ký, không đổi tên để coi hai đại lượng tương đương.
- **Actual:** Dev residual là `sqrt(sum ||error||_2^2 / m)` và orthogonality
  error là Frobenius norm thô. PDF (22)–(23) dùng residual chia
  `||Y_centered||_F`; (24) dùng orthogonality norm chia d. Bảng Dev
  (rank64/RMSE2/gap1/orth1e-4) không chính là bảng Gate C của PDF.
- **Evidence:** source formulas đã đọc/render; code trả `sqrt(total_sq)`
  không chia d. Gate C PDF còn nêu rank fraction≥0,90 và Eorth≤1e-6.
- **Root cause:** thang đo khác nhau confirmed; không kết luận numerical
  alignments hiện tại fail, vì tài liệu đã đúng khi gọi đây là guards Dev.
- **Proposed fix:** giữ các Dev values, bổ sung hai cột “statistic Dev” và
  “statistic PDF nguồn”. Không so residual1,404725 với relative-residual
  threshold hoặc chuyển ngưỡng qua thang khác mà thiếu registration.
- **Regression/status:** code/formula VERIFIED; chưa thay diagnostics.
  Khi reconcile cần fixture phân biệt normalization và guard tương ứng.
- **Blockers:** authority reconciliation trước scientific G3.

### M2-THEORY-005 — MEDIUM — Cụm “quan sát và xác minh” có thể trộn observation với acceptance

- **Affected:** attachment §2.3, line 171;
  `configs/protocol_v1.yaml:12`, `config/protocol.yaml:48–54`.
- **Expected:** `evidence_observed_at` là public availability của phiên bản
  evidence theo basis đã đăng ký; không là lúc dự án xác minh/chấp nhận fact.
- **Actual:** mô tả “khi phiên bản thông tin được quan sát và xác minh” chưa
  phân biệt observation axis và acceptance/adjudication.
- **Evidence/repro:** runtime protocol tách `evidence_observed_at` khỏi
  `accepted_into_kg_at`; câu ví dụ về page date/retrieval trong tài liệu đúng.
- **Root cause:** ambiguity trong wording, không xác nhận dữ liệu bị trộn.
- **Proposed fix:** thay bằng “Khi phiên bản bằng chứng đã công khai theo
  observation basis có thể kiểm chứng”; giải thích acceptance/verification
  và project acquisition bằng fields riêng.
- **Regression/status:** chỉ editorial finding; kiểm lại thuật ngữ ba
  temporal axes sau edit, không chạy lại pipeline.
- **Blockers:** không có cho việc sửa câu chữ.

### M2-THEORY-006 — LOW — 1−cos không phải góc hoặc mathematical metric tổng quát

- **Affected:** attachment §13.2, line 1059.
- **Expected:** `1-cos(theta)` là cosine dissimilarity; góc là
  `arccos(cosine)`. Định nghĩa không bảo đảm triangle inequality.
- **Actual:** gọi là “khoảng cách góc đã biến đổi từ cosine” có thể khiến
  người trình bày nhầm với angular distance hoặc một metric.
- **Evidence/repro:** vector 0°,45°,90°: direct dissimilarity=1 nhưng
  qua 45° tổng=0,585786<1. Range0–2 và bảng hướng trong tài liệu đều đúng.
- **Root cause:** terminology ambiguity, không lỗi numerical formula.
- **Proposed fix:** gọi “cosine dissimilarity sau alignment, bằng
  1−cos(theta), không trực tiếp là góc hoặc phần trăm tri thức thay đổi”.
- **Regression/status:** toy arithmetic VERIFIED; editorial check đủ.
- **Blockers:** không có.

### M2-THEORY-007 — LOW — Bảng verification nên tách tests khỏi kiểm độc lập artifacts

- **Affected:** attachment §16.1, row “Verification”, lines 1326–1336.
- **Expected:** TESTED là fixture/contract tests; VERIFIED cần evidence từ
  kiểm độc lập real artifacts, như quy tắc bốn tiers của AGENTS.md.
- **Actual:** row ghi 505 passed/10 skipped rồi nói artifacts/replay,
  dễ khiến người đọc nghĩ test count tự chứng minh production artifacts.
  Các đoạn sau đã đúng khi bác bỏ việc tests tự cấp scientific certification.
- **Evidence:** drift receipt riêng kiểm20.691 temporal values,6.897 drift
  rows,549 input/57 output hashes; không suy ra các con số đó từ pytest.
- **Root cause:** presentation compression, không nói rằng tài liệu đã
  kết luận G3 PASS.
- **Proposed fix:** tách “Local tests:505/10” và “Independent artifact
  verification:receipt/hash/counts”. Giữ rõ scientific conformance pending.
- **Regression/status:** documentary comparison; không rerun tests vì
  lượt này không sửa code.
- **Blockers:** không có cho bảng, scientific blockers giữ nguyên.

### M2-THEORY-008 — LOW — Bản dán bị mất biểu đồ và escape công thức

- **Affected:** toàn attachment; điển hình lines181/592/1085, các `\\[` /
  `\\(` và escaped underscores, các heading `# 101`, `# 66`.
- **Expected:** tài liệu ôn tập có formulas render đúng, hình/tables đọc
  được và bố cục không mang text fragments từ giao diện khác.
- **Actual:** SVG/chart text bị ghép thành chuỗi số, math delimiters bị
  double-escape, các metric cards trở thành heading rời. Đây là fidelity
  issue của bản dán, không chứng minh tài liệu nguồn có layout lỗi.
- **Evidence:** đọc raw1588lines cho các chuỗi kể trên; chưa có bản gốc
  HTML/PDF/DOCX của tài liệu lý thuyết để kiểm hình thực tế.
- **Root cause:** bản dán mất cấu trúc confirmed; cơ chế export cụ thể
  chưa xác nhận.
- **Proposed fix:** chuẩn hóa math delimiters theo renderer dự kiến, chỉ
  bỏ escape thừa theo ngữ cảnh; thay fragments bằng PNG/SVG hoặc tables
  số liệu nguồn. Không strip tất cả backslashes một cách mù quáng.
- **Regression/status:** cần render bản biên tập và kiểm hình sau khi
  được yêu cầu edit; chưa sửa attachment gốc.
- **Blockers:** định dạng bản final khi có task biên tập.

## Các bổ sung hữu ích trước khi thuyết trình

1. Giải thích entity normalization: code normalize entities sau updates;
   norm constraint giúp tránh lời giải giảm ranking loss chỉ bằng phóng đại
   norm. Relation vectors được normalize lúc initialization, không nên nói
   mọi relation đều được renormalize sau mỗi update.
2. Bổ sung rank bound `rank(X_c^T Y_c)≤min(d,m_fit−1)`. Với 64 chiều,
   64 fit anchors sau centering không thể cho rank64; fit101 chỉ đáp ứng
   điều kiện số lượng, full rank thực tế vẫn cần diagnostics.
3. Giải thích energy lower-is-better, ranking score có thể dùng negative
   energy; filtered evaluation và tie policy (pilot dùng average rank)
   ảnh hưởng MRR/Hits. Không nhầm normalization embeddings với MAD scaling.
4. PDF gọi chỉ số là Standardized Excess Drift. Nếu dùng tên Standardized
   Excess Displacement ở §14.3 cần ghi quy ước của tài liệu, không trình bày
   như canonical expansion đã có trong scientific source.
5. PDF (30)–(31) phân biệt SED score, empirical Q0.95 drift flag và tail
   probability tùy chọn. Run hiện tại chưa tính các inference/flags này;
   quiz r>0/SED+ không nên được thay thành kết luận significance.
6. Nếu pseudo-drift được thảo luận như estimator của protocol, nên ghi
   rõ entity-level noise và LTO center/scale theo PDF (60), cùng population
   masks đăng ký. Đây là planned M4, không là artifact đã chạy.

## Các đoạn nên thay trong tài liệu

### Thay citation và kết luận tại §11.4

Đề cương PDF có hash khớp source lock, §3.2.4 công thức (27)–(29), quy định
lấy median của sáu same-snapshot cross-seed distances cho từng entity rồi
dựng LTO reference từ các entity-level medians khác cùng bucket. Code Dev
hiện pooling sáu distances mỗi reference entity; do đó center/MAD và SED+
không được mặc định tương đương estimator nguồn. Các artifacts đã chạy cần
giữ nhãn pooled-pairwise Dev và được bảo toàn khi thực hiện remediation.

### Bổ sung tại §12.4

Nguồn đang khóa đã nêu mốc 50 entity-level observations cho conditional
null và fallback khi bucket thiếu support. Config Dev hiện chỉ kiểm ít
nhất năm pooled pairwise observations; hai guard khác cả đơn vị và quy mô.
Mốc khoa học/fallback cuối cùng phải được reconcile với các source originals
và amendments, không thay đổi theo SED+ đã quan sát.

### Bổ sung tại §10 và §13

Các formulas và guard đang mô tả chính xác implementation Dev. Bản PDF
nguồn dùng relative Frobenius residual, orthogonality error chia dimension,
và affine-cosine notation khác centered cosine hiện chạy. Các nguồn
runtime/audit không tự supersede scientific sources; cần hòa giải semantic
registration trước khi tuyên bố scientific G3 hoặc sửa metric.

## Trạng thái cuối của lượt review

- **IMPLEMENTED:** báo cáo review và evidence inventory được ghi; không
  implementation patch, không edit attachment hoặc source lock/protocol.
- **TESTED:** toy arithmetic/probe xác nhận các ví dụ estimator/cosine/SED;
  không thêm tests hoặc rerun full suite vì chưa có code change.
- **EXECUTED:** chỉ đọc source PDF/code/config và inventory artifacts đã
  có; không chạy bất kỳ scientific execution stage mới nào.
- **VERIFIED:** commit/source PDF hash, công thức (27)–(28), code flattening,
  diagnostic definitions, các ví dụ số học và counts support được đối chiếu.
- **OPEN:** conformance estimator/support và authority reconciliation;
  không mark RESOLVED hoặc cấp M1/G3 certification.

Lượt review hoàn tất theo scope người dùng yêu cầu. Nếu sửa M2 về sau, cần
một stage/task riêng với source hierarchy được giải quyết, regression trước
patch và output version mới; không overwrite old null/drift/report artifacts.
