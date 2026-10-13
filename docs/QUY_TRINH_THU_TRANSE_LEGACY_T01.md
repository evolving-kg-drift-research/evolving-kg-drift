# Quy trình thử TransE trên dữ liệu legacy v3 — T01

**Cập nhật:** 14/10/2026, Asia/Bangkok.

**Repository:** evolving-kg-drift.

**Nhánh làm việc:** `codex/transe-legacy-exploration`.

**Phạm vi:** thử kỹ thuật và đánh giá link prediction trên một snapshot legacy;
không phải thực nghiệm drift/QA chính thức, không chứng nhận gate production.

Tài liệu này tổng hợp các quyết định, bước thực hiện, kết quả và giới hạn từ
việc chọn nhánh đến kiểm tra cơ chế TransE bằng fixtures. Các báo cáo chi tiết
cũ được giữ nguyên để bảo toàn lịch sử. Tài liệu không thay thế protocol,
source lock hoặc quyết định khoa học đã được phê duyệt.

## 1. Vì sao thử legacy trước khi merge

Repository còn blocker về contract, evidence, mapping và gate. Người dùng có
bộ dữ liệu theo chuẩn cũ và muốn kiểm tra TransE trước khi đưa code vào main.
Vì vậy, công việc được tách thành thử nghiệm legacy có giới hạn, có hash và
lineage riêng. Không sửa dữ liệu cũ để làm cho gate PASS, không tắt kiểm tra
trong loader M2 chính thức.

Ban đầu khuyến nghị dùng `codex/m1-thu-huong-remediation` làm nền hoàn thiện
để merge main. Không merge wholesale các nhánh pipeline cũ có thay đổi source
lock/protocol chưa đối chiếu được thẩm quyền. `main` local khi kiểm tra ở
`d69bb8a`, còn `origin/main` ở `9544e41`; đây là trạng thái lịch sử, không phải
khẳng định remote hiện tại luôn giữ các commit đó.

## 2. Tổ chức nhánh và commit

Đã tạo nhánh `codex/transe-legacy-exploration` từ nền remediation `6000f38`
và push GitHub. Sau khi kiểm thử phần remediation đang mở, đã tạo ba commit:

| Commit | Nội dung |
|---|---|
| `d7f31f9` | Provenance, snapshot certification, parity guards, tests và CI liên quan |
| `2afc456` | Hồ sơ audit, bằng chứng kiểm tra và production blockers |
| `6ef3ff5` | Quy tắc vận hành repository |

Nhánh remediation được fast-forward tới cùng nền; cả hai nhánh đã push.
Trước khi push: 303 tests PASS, 10 skipped; G1 code checks 4 PASS, không phải
scientific G1; Ruff không lỗi lint. Môi trường kiểm tra là Python 3.12.10,
chưa chứng minh tương thích bằng execution trên Python 3.10/3.11.

Các code/báo cáo legacy tạo sau mốc `6ef3ff5` chưa commit ở các lượt trước;
đợt logging 14/10 đóng gói chúng thành hai commit code/tests và tài liệu trên
nhánh legacy. Hash commit tra bằng `git log`; đợt này không push hoặc merge main.
Không coi file đặt trong checkout là đã
được Git theo dõi hoặc đã push. Data, checkpoints và logs không stage tự động.

## 3. Bộ dữ liệu v3

Thư mục input:

```text
data/KG_lan2/evolving_kg_downstream_v3/
```

Đây là bộ v3, không kế thừa chứng nhận từ audit v2. Lượt kiểm tra v3 chỉ đọc,
không chạy producer, acquisition, Neo4j hoặc training.

### 3.1 Kết quả kiểm tra file và graph

- 113 files, 39 Parquet. 38 Parquet có sidecar và cả 38 khớp physical hash,
  semantic hash và row count. File `extracted_claims_partial.parquet` thiếu sidecar.
- 10 canonical snapshots có IDs không rỗng, không trùng triple, không self-loop.
- Canonical triple sets khớp snapshot fact; counts/cutoffs khớp manifest/config.
- CSV node sets và edge multisets kèm temporal metadata khớp Parquet.
- Không thấy future-evidence/validity violation khi đối chiếu timestamps đã
  lưu với cutoff. Chưa xác minh được nguồn gốc và semantics của các timestamps.
- Metadata khai báo 5.271 strict retrievals phủ 5.168 raw hashes; acquisition
  logs/raw bytes chưa được kiểm chứng lại từ gói.
- Gói chỉ có creation facts, không có supersedes; các transitions chỉ thêm
  triples. Điều này không chứng minh correction/retraction hoạt động.

| Snapshot | Fact rows | Canonical triples | Entities | Weak components |
|---|---:|---:|---:|---:|
| T01 | 127 | 121 | 167 | 54 |
| T10 | 1.803 | 1.205 | 1.389 | 313 |

T10 có 1.040/1.389 entities chỉ một láng giềng. Topology counts được đối chiếu
với audit v2 và trùng, nhưng không kết luận hai package giống byte-for-byte.

### 3.2 Các blocker vẫn còn

1. Toàn bộ 1.803 facts ghi `entity_map_version=v1_mock`, thiếu mapping table.
   Tên version không tự chứng minh facts là giả; nó không đủ chứng nhận identity as-of.
2. Thiếu source text, body blobs và acquisition logs được tham chiếu; không
   xác minh độc lập grounding, evidence clocks hay strict acquisition.
3. Thiếu run/stage/gate certificates và một số provenance tables; fields
   khác `config/schema.yaml`. Bundle FROZEN tự khai báo không thay approval evidence.
4. T07–T10 vượt window kết thúc 31/08/2026 của checkout. Không tự sửa cutoff
   hoặc loại snapshot; cần giải quyết thẩm quyền nếu dùng cho nghiên cứu chính thức.
5. Parity là CSV export; report ghi rõ chưa có database read-back.
6. File SHA-256 được cung cấp trỏ ZIP không có trong thư mục; hash ZIP chưa
   được xác minh từ thư mục giải nén.

Chi tiết: [audit v3](../outputs/v3_review_20261013/README.md), kèm `report.json`.
Inventory hash thư mục:
`13440a94fb3e418b0720fa4121734aff42c53e4dab48a8cd203f9dbfcaab89c0`.

## 4. Chốt T01 và mục tiêu thử kỹ thuật

Người dùng chốt T01 sau khi đã được trình bày giới hạn legacy.
Input duy nhất:

```text
data/KG_lan2/evolving_kg_downstream_v3/snapshots/snapshot_T01_canonical.parquet
```

SHA-256:
`42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e`.
Runner từ chối nếu bytes khác hash đã chốt; không glob cả thư mục và không
dùng snapshot fact nhiều support rows thay canonical triples.

| Cấu hình | Giá trị |
|---|---|
| Model / energy | TransE, L2: `||h + r - t||` |
| Dimension | 32 |
| Epochs | 50 |
| Learning rate | 0.01 |
| Margin | 1.0 |
| Seeds | 13, 37, 101 |
| Entity normalization | Bật |
| Trainer | SGD từng triple trong repo, CPU |
| Dữ liệu lượt đầu | Cả 121 triples; không validation/test |

`batch_size=32` tồn tại trong config nhưng implementation hiện không mini-batch.
Mapping integer deterministic từ IDs trong input, không phải chứng nhận
canonical identity theo thời gian.

## 5. Thử huấn luyện đủ T01

Đã chạy hai lần mỗi seed để kiểm tái lập trong cùng môi trường.

| Seed | Loss epoch 1 | Loss epoch 50 | Checkpoint hai lần |
|---|---:|---:|---|
| 13 | 0.966721 | 0.387573 | Byte-identical |
| 37 | 0.997522 | 0.414725 | Byte-identical |
| 101 | 1.013279 | 0.412906 | Byte-identical |

Embeddings có 167 entity vectors và 10 relation vectors, mỗi vector 32 chiều;
loss/vectors hữu hạn. Save/load, mapping, output/input hashes đã kiểm tra.
9 tests input/trainer PASS. Loss giảm chưa chứng minh khả năng dự đoán.

Run: `outputs/legacy_transe/t01_20261013T164822Z_8f5250d7/`.
Chi tiết: [smoke report](audit/legacy_transe_t01_20261013.md).

## 6. Kiểm tra khả năng chia dữ liệu

T01 có 121 entities chỉ xuất hiện trong một triple. Đây là triple incidence,
khác số láng giềng. Có 88 triples không thể giữ riêng để đánh giá mà vẫn giữ
mọi entity trong training. 33 triples có thể giữ riêng từng triple, nhưng
không nhất thiết giữ đồng thời cả 33.

| Diagnostic split | Train | Held-out | Entity OOV trong held-out triples |
|---|---:|---:|---:|
| Công thức hash của trainer, tỷ lệ 20% | 98 | 23 | 20/23 triples |
| Coverage-preserving, thứ tự hash cố định | 101 | 20 | 0/20 triples |

Phương án thứ hai giữ đủ 167 entities và 10 relations trong training, held-out
phủ 7 relations. Có 4 triples mà cùng cặp entity không phân biệt hướng đã có
cạnh khác trong train. Không khẳng định đó là inverse leakage.

Phương án được dựng bằng greedy theo hash cố định, không dùng model scores
và không tuyên bố tối ưu số lượng held-out. 4 tests split audit PASS.
Chi tiết: [split feasibility](audit/legacy_t01_split_feasibility_20261013.md).

## 7. Chốt và chạy đánh giá 101/20

Người dùng đã chốt thiết kế trước khi chạy:

- Giữ nguyên 101 train / 20 held-out, không tuning trên held-out.
- Huấn luyện lại từ đầu với cấu hình và ba seeds ở trên. Không dùng checkpoint
  đã học đủ 121 triples. Integer mappings xây từ training.
- Chấm cả head/tail: 40 ranking queries, không coi là 40 quan sát độc lập.
- Candidate universe: toàn bộ 167 training entities, không type restriction.
- Filter positives khác trong toàn bộ T01 nhưng giữ target. Held-out chỉ dùng
  ở evaluation/filter; negative sampling training chỉ nhận 101 train positives.
- Hạng trung bình khi score bằng nhau. Hits@k kiểm average rank <= k.
- Baseline: tổng tần suất endpoint head+tail trong training; cùng filter/ties.
- Chỉ số: MRR, Hits@1/3/10, riêng từng seed và head/tail.

Design/split được lưu trước training. Split hash:
`c334701a0d2bece4be155af467832eaaa7ee1f416f58e3446f1702b193fd90cd`.

| Model | MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---:|---:|---:|---:|
| Frequency baseline | 0.056464 | 0% | 7.5% | 20% |
| TransE 13 | 0.104897 | 0% | 15% | 30% |
| TransE 37 | 0.084878 | 0% | 10% | 25% |
| TransE 101 | 0.093864 | 0% | 10% | 22.5% |

Mean MRR ba seeds 0.094546 chỉ là thống kê mô tả. Không chọn seed đẹp nhất.
Đã tính lại độc lập 160 rows (baseline + ba seeds) từ saved checkpoints và
frequencies: scores/filter/ranks/metrics khớp. 8 ranking/split tests PASS.

Run: `outputs/legacy_evaluation/20261013T170623Z_e7a3592e/`.
Tên run dùng UTC; ngày địa phương là 14/10/2026.
Chi tiết: [evaluation report](audit/legacy_t01_evaluation_20261014.md).

## 8. Phân tích lỗi sau đánh giá

Giữ nguyên model, data và metrics; phân tích hậu nghiệm không được dùng để
sửa upstream hoặc biến cùng held-out thành kết quả độc lập mới sau tuning.

### 8.1 Lợi thế tập trung ở cặp đã thấy

| Nhóm | Số queries | Baseline MRR | Mean TransE MRR |
|---|---:|---:|---:|
| 4 triples có cặp entity đã thấy | 8 | 0.025926 | 0.257845 |
| 16 triples có cặp entity chưa thấy | 32 | 0.064099 | 0.053722 |

Trên nhóm chưa thấy cặp, cả ba seeds dưới baseline. Không suy ra khả năng
dự đoán cặp mới tốt chỉ từ aggregate MRR cao hơn baseline.

### 8.2 Self-loop và dao động seed

- Self-loop top-1: seed 13 là 36/40; seed 37 là 34/40; seed 101 là 39/40.
- Với TransE, `energy(e,r,e)=||r||`. Đã xác minh từ checkpoint; đây không phải
  bằng chứng evaluator tính sai điểm. Candidate contract hiện cho phép self-loop.
- Chỉ 4/40 queries vào top-10 ở cả ba seeds; 20/40 ngoài top-10 ở cả ba.
- Median khoảng biến thiên rank giữa seeds là 63 hạng.
- Thiếu name/type mapping và source text để kết luận chắc chắn nhầm loại entity,
  entity gần nghĩa hay missing true facts. Không tự bổ sung gold.

Chi tiết: [error report](audit/legacy_t01_error_analysis_20261014.md).

## 9. Bước tiếp theo đã thực hiện: kiểm tra cơ chế bằng fixtures

Đã thêm `tests/scientific/test_transe_mechanics.py`. Fixtures tổng hợp chỉ nằm
trong tests; không đưa synthetic defaults vào production và không đọc held-out
để lựa chọn các fixture values.

### 9.1 Các phép kiểm tra

1. **Numerical gradient:** sai phân trung tâm cho từng tham số entity/relation,
   so với một bước SGD, tắt projection để cô lập gradient. Sáu trường hợp:
   corrupt head/tail thông thường, negative self-loop, positive self-loop.
2. **Sampler rejection:** ép chuỗi random gồm entity gốc, known-positive rồi
   negative hợp lệ; xác nhận hai candidate đầu bị loại trước cập nhật.
3. **Saturated side:** mọi corruption bên đã chọn là positive, thử 100 lần
   rồi skip; weights giữ nguyên, không biến positive thành negative.
4. **Inactive hinge:** loss bằng 0 thì weights không đổi.
5. **Self-loop formula:** energy bằng relation norm ở mọi entity trong fixture.
6. **Projection:** vectors được update có norm 1 khi bật normalization.
7. **Evaluation:** loss khớp công thức độc lập và không sửa weights.
8. **Retry budget:** ép random chọn lại entity gốc 100 lần, xác nhận sampler
   có thể skip dù vẫn có negative hợp lệ; chọn negative hợp lệ trực tiếp thì
   có update. Trường hợp này kiểm cơ chế, không ước lượng xác suất skip thực tế.

Lệnh đã chạy:

```powershell
python -m pytest -q tests/scientific/test_transe_mechanics.py tests/scientific/test_filtered_negative_sampling.py tests/test_legacy_ranking.py -p no:cacheprovider
```

**Kết quả cuối: 20 passed** (15 tests/parameter cases mới, 1 test sampling hiện có,
4 tests ranking). Ruff mục tiêu PASS. Không sửa `src/kge/model.py`, không đổi
negative-sampling rule, không huấn luyện lại trên T01.

### 9.2 Diễn giải và giới hạn

Chưa tìm thấy lỗi gradient, positive filtering hoặc chiều ranking trong phạm
vi kiểm tra. Shared entity indices và negative self-loop không làm sai SGD
trong các fixture đã thử. Không có căn cứ sửa production code ở lượt này.

Sampler hiện thử tối đa 100 lần trên một phía chọn trước rồi skip, không chuyển
sang phía còn lại. Zero loss trong trường hợp saturated chỉ là không có update,
không phải mô hình đã học tốt. Tests xác nhận hành vi này; chưa đo tần suất skip
trên T01 và không đổi quy tắc sampling. Ngay cả khi có negative hợp lệ, chuỗi
draw bị reject hết 100 lần vẫn có thể gây skip; test dùng chuỗi draw ép trước
để chứng minh khả năng này, không kết luận nó gây lỗi prediction trên T01.
Numerical gradient tests tránh điểm
không khả vi tại hinge boundary/zero norm; không chứng minh mọi edge case.

Self-loop ranking cao là hành vi tương thích với công thức và candidate
contract hiện tại. Chưa chứng minh nguyên nhân sâu hơn đến từ data sparsity,
negative sampling, relation norm hay số epochs. Không tự loại self-loop để
nâng Hits@1 sau khi đã xem kết quả.

## 10. Chẩn đoán training 101 triples bằng logging — đã thực hiện

Người dùng yêu cầu thực hiện bước này và bổ sung quy trình từng bước.
Ngày thực hiện theo Asia/Bangkok: 14/10/2026. Mục tiêu là đo sampler/update/norm
trên đúng training population, không chọn cấu hình mới bằng điểm held-out.

### Bước 10.1 — Khóa input và reference

Giữ nguyên T01 đúng SHA-256 đã chốt, 101 training triples trong split đã đánh
giá, dimension 32, 50 epochs, lr 0.01, margin 1.0, seeds 13/37/101.
Reference checkpoints là `seed_13.json`, `seed_37.json`, `seed_101.json` trong
`outputs/legacy_evaluation/20261013T170623Z_e7a3592e/`.

Trước khi chạy, kiểm toàn bộ reference artifact hashes và hash T01, rồi ghi
`design.json`, `train.json`, mappings và bản code vào output mới. Không lấy
held-out positives làm negative filter trong training; chỉ dùng 101 positives.

### Bước 10.2 — Gắn observer vào vòng training hiện có

Thêm `scripts/diagnose_legacy_t01_training.py`. Observer dùng `sys.settrace`
để đọc locals tại các điểm lấy candidate, hoàn tất sampling và kiểm hinge loss.
Không thay RNG, thứ tự shuffle, negative rule hoặc phép tính gradient.
Không sửa `src/kge/model.py` hay `src/kge/trainer.py`.

Mỗi epoch ghi:

- Số triples được xử lý, head/tail trials và candidate draws.
- Số candidate bị loại do bằng entity gốc hoặc tạo known-positive.
- Số valid negatives và số lượt skip vì không tìm được negative.
- Số self-loop negatives; số self-loop negatives có active hinge.
- Số active updates và inactive hinges.
- Loss và norm của từng relation trước/sau epoch.
- Positive/negative IDs, phía corruption, hinge value và update flag từng lượt.

Observer dừng nếu anchors trong source thay đổi hoặc bộ đếm không cân bằng.
Nó trả lại trạng thái tracing sau execution, không lấy thêm số ngẫu nhiên.

### Bước 10.3 — Kiểm observer bằng fixtures

Hai tests mới ở `tests/test_legacy_training_observer.py`:

1. Chạy fixture có/không logging, so toàn bộ checkpoint và chuỗi loss; kiểm
   số sample/epoch, RNG stream và trạng thái tracing được khôi phục.
2. Chạy fixture saturated chỉ một entity, xác nhận đủ 100 draws bị reject,
   một lượt skip và zero updates; không đọc zero loss như bằng chứng đã học tốt.

Lượt test tổng hợp mới nhất:

```powershell
python -m pytest -q tests/test_legacy_training_observer.py tests/test_legacy_ranking.py tests/test_legacy_split_audit.py tests/scientific/test_transe_mechanics.py -p no:cacheprovider
```

**25 passed**. Đây là một lượt test riêng, gồm 2 observer, 4 ranking, 4 split
và 15 mechanics cases; không cộng dồn thành full-suite result. Ruff toàn repo
không lỗi lint, có ba warnings quyền đọc fixture directories cũ. Diff check PASS.

### Bước 10.4 — Chạy replay trên 101 training triples

```powershell
python scripts/diagnose_legacy_t01_training.py
```

Run mới: `outputs/legacy_training_diagnostics/20261013T172626Z_59171a0e/`.
Tên run là UTC; ngày địa phương là 14/10/2026. Tracing có overhead thời gian,
không dùng thời gian replay để so tốc độ với run không logging.

Mỗi checkpoint replay giữ provenance lịch sử của reference để so bytes.
Manifest diagnostics riêng ghi execution mới, current git/dirty state, code
hashes, training/config/mapping hashes và reference checkpoint hash. Như vậy
không nhầm metadata checkpoint tái lập với provenance của lượt quan sát mới.

### Bước 10.5 — Kiểm logging không làm thay kết quả

**Ba checkpoint đều giống hệt reference byte-for-byte**, bao gồm vectors,
training metrics và provenance. Code training được kiểm hash với code snapshot
trong reference run. T01 và toàn bộ reference artifacts giữ nguyên hash.

Không chấm held-out lại; checkpoint không đổi nên giữ kết quả đánh giá đã báo.
Logging không thay data, split, candidate policy hay scientific gates.

### Bước 10.6 — Kết quả sampler và updates

| Seed | Lượt triple | Candidate draws | Valid negatives | Skip | Active updates | Self-loop negatives |
|---|---:|---:|---:|---:|---:|---:|
| 13 | 5.050 | 5.098 | 5.050 | 0 | 4.999 | 23 |
| 37 | 5.050 | 5.103 | 5.050 | 0 | 5.007 | 31 |
| 101 | 5.050 | 5.086 | 5.050 | 0 | 4.990 | 32 |
| Tổng | 15.150 | 15.287 | 15.150 | 0 | 14.996 | 86 |

Tổng 111 draws bị reject do entity gốc và 26 do known-positive; 154 lượt
inactive hinge. Active updates chiếm khoảng 98,98%. Self-loop negatives chiếm
86/15.150 ≈ 0,57%; cả 86 đều có hinge dương và được update.

Trong run này, không có bằng chứng training thiếu updates hoặc bị skip bởi
retry budget. Fixtures trước chỉ chứng minh skip có thể xảy ra ở trường hợp
khác, không phải nó đã xảy ra trên T01.

### Bước 10.7 — Kết quả relation norms

Relation norms khởi tạo xấp xỉ 1.0; cuối training:

| Relation | Seed 13 | Seed 37 | Seed 101 |
|---|---:|---:|---:|
| acquired_by | 1.0110 | 0.9265 | 0.9590 |
| based_on | 0.9598 | 1.0046 | 0.9987 |
| integrated_into | 1.2568 | 1.0162 | 1.1601 |
| invested_in | 1.0455 | 1.0483 | 0.9946 |
| is_CEO_of | 1.1031 | 0.9223 | 0.9329 |
| partners_with | 0.9606 | 0.9798 | 1.0770 |
| released_by | 1.2029 | 1.0845 | 0.9510 |
| succeeded_by | 0.8674 | 1.0287 | 0.9160 |
| version_of | 0.9643 | 0.8967 | 0.8267 |
| works_at | 0.7601 | 1.1700 | 0.9889 |

Cuối training, norm nằm trong khoảng 0.7601–1.2568; không quan sát collapse
về 0. Đây là mô tả số liệu, không đặt thêm threshold scientific.
Đường norm theo epoch nằm trong `seed_*_epochs.json`.

### Bước 10.8 — Xác minh lại logs đã lưu

Đã đọc lại 15.150 sample rows và đối chiếu độc lập:

- Positive thuộc training; negative hợp lệ không thuộc training positives.
- Sample counts, self-loop counts và update flags khớp counters.
- Tổng positive hinge / 101 khớp epoch loss và loss sequence checkpoint.
- Norm cuối khớp tính lại từ relation vectors đã lưu.
- Checkpoint bytes khớp reference; artifact hashes và manifest required fields đạt.

Kết quả ở `independent_verification.json`. Candidate rejection counts được
kiểm bằng accounting từ observer; không lưu toàn bộ rejected candidate IDs để
khẳng định đã replay độc lập mọi rejected draw.

### Bước 10.9 — Diễn giải và điểm dừng

Self-loop negatives được gặp ít trong sampling uniform hiện tại, còn self-loop
đứng đầu phần lớn queries ở đánh giá trước. Đây là quan sát gợi ý để thiết kế
thử nghiệm mới, chưa chứng minh tăng self-loop negatives sẽ cải thiện prediction.
Không đủ căn cứ tự tăng epochs, đổi margin, hard-negative sampling hoặc cấm
self-loop rồi báo điểm mới như evaluation độc lập trên cùng 20 triples.

Tier: IMPLEMENTED observer/tests; TESTED 25 fixtures; EXECUTED replay legacy
trên 101 training triples; VERIFIED logs/integrity/exact checkpoints trong
cùng môi trường. Production gates vẫn BLOCKED. Dừng sau bước chẩn đoán.

### Bước 10.10 — Lưu mốc code và tài liệu

Đóng gói code/tests legacy đã kiểm tra và các báo cáo thành commit riêng trên
`codex/transe-legacy-exploration`. Không stage thư mục `data/`, `outputs/`,
PDF nguồn hoặc `preexisting.patch`. Checkpoints và logs nằm trong thư mục
ignored, cần giữ nguyên run directories để bảo toàn replay reference.
Chưa push các commit legacy mới hoặc merge main trong lượt này.

## 11. Kiểm tra content readiness trước khi tìm được release upstream

Người dùng yêu cầu bước tiếp theo và mở rộng kiểm tra toàn bộ. Lượt này là
kiểm tra read-only trên các repository roots đã biết, không tìm trên toàn
bộ ổ đĩa cá nhân và không thay scientific population hoặc gold labels.

### Bước 11.1 — Mở rộng tìm kiếm artifact upstream

Đã index file paths trong repository hiện tại và checkout phụ:

```text
D:/Users/Documents/HUCE/HK1_2026-2027/2. Machine Learning2/Code/evolving-kg-drift
C:/Users/ducan/orca/workspaces/evolving-kg-drift/main
```

Inventory cuối ghi 296 và 164 file paths tương ứng. Không truy cập
`locked_test`, hidden entries, symlinks/reparse paths, tests, model outputs,
dependency directories hoặc temporary fixture roots. Index names không phải
chứng minh mọi payload đã được kiểm ngữ nghĩa.

Không tìm thấy candidate mapping/mention artifacts, body blobs hoặc acquisition
logs theo tên/đường dẫn trong phạm vi này. Kiểm thêm từng body/evidence path
được khai báo trong mẫu, tương đối với package và hai roots: không file nào
tồn tại. Guide DOCX có hướng dẫn nạp canonical Parquet nhưng không thấy các
từ khóa mapping/entity_map/body_blobs/acquisition/raw hoặc HTTP source pointer
trong phần text đã trích; guide không thay thế source evidence. Chưa có căn cứ
kết luận artifact không tồn tại ở nơi khác ngoài hai roots này.

### Bước 11.2 — Lưu kế hoạch lấy mẫu trước khi đọc nội dung

Thêm `scripts/audit_v3_content_readiness.py`. Trước khi đọc full facts/claims,
chỉ đọc FactVersionID và relation_id, rồi lưu plan:

- Population: toàn bộ 1.803 FactVersion rows v3, không chọn từ lỗi TransE.
- Mẫu chẩn đoán: 3 facts mỗi relation, 10 relations, tổng 30.
- Thứ tự: SHA-256 của JSON chứa salt `v3-content-readiness-diagnostic-v1`,
  relation_id và FactVersionID; lấy ba IDs đầu mỗi relation.
- Mục tiêu: kiểm traceability và availability, không ước lượng fact accuracy
  hoặc xây gold test set. Không đổi decision log, cutoffs hoặc corpus filtering.

Sample plan được ghi exclusive-create trước content review. Plan SHA-256:
`7e3c2902a29445135ffedb25220256d0d3c5467dca71e00a480b24988cfcac91`.
Không đọc training ranks/model scores để chọn hoặc thay mẫu. Năm tests kiểm
row-order independence, không phụ thuộc extra outcome fields và chặn unsafe/
held-out evidence paths đều PASS.

### Bước 11.3 — Kiểm hash và truy nguyên candidate claims

Đối chiếu physical/semantic hashes và counts trước khi đọc facts, final claims,
body metadata, memberships và retrievals. Không dùng partial claims làm input.
Truy candidate claims bằng đúng tổ hợp:

```text
source_id + evidence_span_start + evidence_span_end + evidence_text_hash + relation
```

Kết quả toàn store: 1.497 facts khớp một candidate claim; 306 facts khớp từ
2–6 candidates. Không có fact nào zero candidate theo tổ hợp này.
Đây là đối chiếu metadata, không phải verified supporting-claim lineage.

Trong mẫu 30 facts: 22 khớp một claim; 8 khớp nhiều claims và có cặp mention
khác nhau. Một span có thể chứa nhiều facts đúng cùng relation; việc khớp
nhiều candidates tự nó không chứng minh extraction sai. Thiếu supporting
claim IDs và mapping decisions nên chưa chọn được candidate có thẩm quyền.

### Bước 11.4 — Ghi tên/alias có thể quan sát, không tạo mapping mới

`sample_reviews.json` lưu subject/object IDs cùng candidate mention strings
và claim IDs. Ví dụ metadata có mention `X` và `xAI`; các chuỗi này chỉ là
nhãn quan sát trong extracted claims, không xác nhận identity hay fact đúng.

Không hash lại mention text để tạo canonical IDs, không fuzzy-merge aliases,
không tự suy ra mapping_available_at hoặc nâng `v1_mock` thành certified mapping.
Tất cả 30 rows giữ trạng thái mapping **NOT_VERIFIABLE** vì chưa có registered
mapping artifact có căn cứ as-of.

### Bước 11.5 — Đối chiếu body, span và temporal evidence

Cả 30 facts có body metadata để tham chiếu, nhưng body text tại các vị trí
khai báo không có. Các retrieval links dẫn tới metadata, không tới file evidence
có thể đọc trong phạm vi đã tìm.

| Phép kiểm tra trên mẫu | Kết quả |
|---|---|
| Quan sát candidate mention labels | Có, 30/30 |
| Đối chiếu span hash với body text | 0/30 có đủ payload để kiểm |
| Đọc acquisition/evidence logs được tham chiếu | 0 paths có sẵn trong mẫu |
| Xác minh mapping availability theo cutoff | Chưa đủ artifact |
| Đánh giá đúng/sai của facts từ source content | Chưa thực hiện được |

Không dùng retrieval timestamps làm evidence_observed_at, không dùng valid_from
làm căn cứ evidence time, không tạo fallback timestamps. **0/30 có payload
không phải accuracy=0%**; đúng/sai vẫn chưa được đánh giá.

### Bước 11.6 — Lưu báo cáo và xác minh integrity

Run hoàn chỉnh:
`outputs/v3_content_readiness/20261013T173633Z_fb877e13/`.
UTC trong tên run; ngày địa phương 14/10/2026. Gồm sample plan và hash,
inventory, sample reviews, summary, input hashes, code snapshot,
experiment manifest và independent verification.

Đã kiểm lại output hashes, 30 IDs trong reviews bằng plan đã lưu, sample không
trùng và manifest required fields. Package Parquet giữ nguyên hash. Ruff
không lỗi lint; có warnings quyền đọc các fixture directories cũ.

Run sơ bộ `20261013T173555Z_9d815e6e` cũng được giữ nguyên, nhưng báo cáo hiện
tại tham chiếu run hoàn chỉnh có code/manifest lineage bên trên. Việc chạy
lại chỉ bổ sung lineage/lint fix; không thay cách chọn mẫu hoặc results.

### Bước 11.7 — Finding và phần còn bị chặn

**Finding V3-CONTENT-001 — HIGH**

- **Affected files:** `data/KG_lan2/evolving_kg_downstream_v3/tables/fact_versions.parquet`,
  `extracted_claims.parquet`, `body_variants.parquet`, `retrievals.parquet` trong
  cùng tables directory; mapping/body/evidence artifacts được tham chiếu còn thiếu.
- **Expected:** Fact → supporting claim → span/body → immutable source evidence,
  cùng registered identity/mapping availability và temporal basis kiểm được.
- **Actual:** Các metadata joins tồn tại nhưng thiếu payload/as-of mapping;
  8 sampled facts có nhiều cặp mention candidates, không có explicit support IDs
  để xác định claim liên quan. 30 sampled facts không chấm correctness được.
- **Evidence:** `sample_reviews.json`, `inventory.json`, `summary.json` của run.
- **Root cause vs hypothesis:** Xác nhận thiếu chứng cứ ở locations đã kiểm tra;
  chưa chứng minh dữ liệu sai hoặc artifact đã mất ở mọi nơi. Multiple claims
  trên một span có thể là hợp lệ, nhưng chưa có lineage để disambiguate.
- **Reproduction:** `python scripts/audit_v3_content_readiness.py`; mỗi lần tạo run mới.
- **Proposed minimal fix:** Cung cấp bundle upstream gốc có mapping/mentions,
  supporting-claim decisions, body blobs và acquisition logs đúng hashes; không
  sửa historical facts hoặc tự dựng timestamps để làm cho verifier PASS.
- **Regression tests:** 5 sample/path-guard tests PASS; khi upstream recovery
  có thể thực hiện, cần tests cho missing/tampered body, span/hash mismatch và
  mapping available sau cutoff.
- **Remaining blockers:** Mapping/identity policy, source payloads, supporting
  claim lineage và evidence-time basis chưa được chứng thực.

Tier: IMPLEMENTED audit/report; TESTED 5 fixtures; EXECUTED read-only audit thật;
VERIFIED metadata/integrity trong phạm vi nêu trên. Semantic quality/G2 vẫn
**BLOCKED_NOT_VERIFIED**. Không mở gate và không chỉnh bộ dữ liệu.

### Bước 11.8 — Artifact cần có để tiếp tục

Để hoàn tất phần kiểm nội dung, cần bổ sung từ upstream gốc:

1. `entity_mentions` và `entity_mapping_versions` theo `config/schema.yaml`, gồm
   mention_id, canonical_entity_id, mapping_available_at, version/basis/confidence.
2. Body blobs ở đúng `body_blob_relative_path`, cùng normalization/extractor
   version và immutable clean-text hashes để kiểm span.
3. Acquisition logs và raw bytes đúng evidence paths/hash references.
4. Claim provenance và adjudication decisions nối supporting_claim_ids tới
   FactVersion; căn cứ evidence time/validity và approval/component manifests.

Có thể giữ artifacts gốc ở thư mục riêng và cung cấp đường dẫn; recovery phải
kiểm hash và source authority trước khi dùng. Không crawl lại Stage 4.3 hoặc
thay lock/protocol. Khi artifacts có đủ, tiếp tục review chính 30 sampled IDs
đã lưu; không thay mẫu vì kết quả TransE hoặc vì facts khó kiểm.

## 12. Khôi phục upstream từ GitHub Release và kiểm lại evidence — đã thực hiện

Người dùng yêu cầu thực hiện bước tiếp theo. Lượt này mở rộng từ local files
sang Git history, registered worktrees và GitHub repository artifacts. Đây là
khôi phục artifact đã lưu của dự án qua developer tooling; không crawl hoặc
thu thập lại research data. Không gửi tin nhắn cho người tạo bộ v3.

### Bước 12.1 — Kiểm các nguồn có thể khôi phục

- Fetch remote refs; không thay working tree hoặc merge.
- Kiểm thêm worktree `C:/Users/ducan/orca/workspaces/evolving-kg-drift/dottyback`:
  không có mapping/body/acquisition candidate trong các prefix được phép.
- Nhánh producer `origin/feature/remediation-and-parity` và
  `origin/fix/data-pipeline-compliance-cont` có `entity_map_v1.json`,
  `source_manifest.json`, `snapshot_manifest.json` nhưng đều 0 bytes.
- GitHub Actions artifact listing trả `total_count=0`.
- Tìm được release [data/pre-gate-a-audit-v1](https://github.com/evolving-kg-drift-research/evolving-kg-drift/releases/tag/data/pre-gate-a-audit-v1)
  có archive, dataset manifest, README và SHA256SUMS.

### Bước 12.2 — Đọc metadata trước khi dùng archive

Release được ghi rõ `AUDIT_ONLY`, Gate A BLOCKED, source-hash mismatch chưa
giải quyết, config unfrozen; không phải gói producer run v3 được chứng nhận.
Không dùng approval hoặc source lock bên trong release để thay baseline hiện tại.

Archive `kg-data-pre-gate-a-audit-v1.tar.zst`: 215.571.355 bytes; SHA-256:
`9d72dfce30a63a1048e4e20cc08784a900e3de5d22401f6fe51af96cbedb5184`.
Đã tải và kiểm đúng hash, lưu riêng ở
`outputs/upstream_recovery_release_20261014/`.

### Bước 12.3 — Preflight và khôi phục có chọn lọc

Index 11.431 archive entries trước extraction; kiểm path traversal, absolute
paths, duplicate names, held-out paths và special/link entries. Chỉ file và
directory thông thường được chấp nhận. Không giải nén vào `data/`, `runs/`
hoặc ghi đè artifact hiện có.

Đợt đầu khôi phục 4.790 file entries được chọn, gồm 4.745 body text files,
27 acquisition logs và các evidence files được mẫu tham chiếu. Thêm đợt hai
khôi phục đúng 30 sample raw blobs có đuôi `.bin` từ archive. Member lists
và selection metadata được giữ trong recovery folder.

Payload nằm tại `outputs/upstream_recovery_release_20261014/recovered/`.
Release đầy đủ được giữ nguyên để tái hiện; không cần giải nén toàn bộ khoảng
2,25 GB uncompressed content vào pipeline để kiểm mẫu này.

### Bước 12.4 — Chứng minh payload trùng với references của v3

Không suy ra toàn release bằng v3 từ tên file. Đối chiếu từng payload:

| Phép đối chiếu | Kết quả |
|---|---:|
| Body bytes khớp `body_text_sha256` của v3 | 4.745/4.745 |
| Strict retrieval evidence file hash | 5.271/5.271 |
| Strict retrieval canonical JSON record hash theo locator | 5.271/5.271 |
| Raw hash field trong receipt | 5.271/5.271 |
| Requested/final URL và retrieval time trong receipt | 5.271/5.271 |
| Raw bytes của mẫu khớp content hash | 30/30 |

27 acquisition log files phủ toàn bộ 5.271 retrievals được v3 đánh dấu strict.
Record hash ở đây là SHA-256 canonical JSON, không phải hash raw JSONL line.
Không xác minh bytes toàn bộ 5.168 raw blobs trong lượt này: chỉ 30 sample
raw blobs được khôi phục và hash-check; receipts cho phần còn lại là evidence
metadata đã đối chiếu, không thay thế raw-byte verification.

### Bước 12.5 — Kiểm lại đúng mẫu 30 facts đã lưu

Giữ nguyên sample IDs từ plan ở bước 11.2. Có 29 body variants và 30 raw blobs
liên quan tới 30 facts; không đổi mẫu vì findings mới.
Đọc UTF-8 từ payload bytes đúng hash, kiểm offsets và tính SHA-256 của
`body_text[start:end]`, không thay normalization hoặc tìm vị trí mới để làm
span PASS. Đã kiểm giả thuyết CRLF/universal-newline trên mẫu: không có CRLF
trong các body này và newline conversion không giải thích mismatch.

| Phạm vi | Offsets trong bounds | Hash span khớp | Hash toàn body khớp |
|---|---:|---:|---:|
| Mẫu 30 facts | 30/30 | 1/30 | 30/30 |
| Toàn store 1.803 facts | 1.803/1.803 | 15/1.803 | 1.803/1.803 |

Do đó **1.788 facts** không bind được exact evidence span theo contract hiện
tại. Đây là kiểm integrity/grounding, **không phải tỷ lệ facts đúng hoặc sai**.
Ngay cả 15 span khớp cũng chưa xác nhận entity mapping, relation correctness
hoặc temporal semantics.

### Bước 12.6 — Finding V3-REC-001: evidence hash đang bind toàn body

- **Severity:** HIGH.
- **Affected files:** `data/KG_lan2/evolving_kg_downstream_v3/tables/fact_versions.parquet`,
  `extracted_claims.parquet`; producer candidate `src/kg_pipeline/claims.py`
  trên `origin/feature/remediation-and-parity`.
- **Expected:** Exact code-point span có hash riêng, tách khỏi clean-text/body
  hash; contract hiện tại ở `src/kg_pipeline/evidence.py:EvidenceSpan` và
  `src/kg_pipeline/claims.py` lưu `span.text_sha256`.
- **Actual:** `evidence_text_hash` của toàn bộ 1.803 facts bằng v3 body hash;
  chỉ 15 exact spans khớp; mẫu có 29/30 span mismatches.
- **Evidence:** `summary.json`, `sample_review.json` của recovery review;
  code candidate ghi `text_hash = sha256_text(text)` rồi
  `evidence_text_hash=text_hash`.
- **Root cause vs hypothesis:** Sai binding toàn body trong artifacts đã
  xác nhận; code candidate có đúng cơ chế gây ra nó. Chưa có v3 producer
  code/run manifest để chứng minh chính commit candidate đã tạo v3.
- **Reproduction:** `python scripts/audit_recovered_v3_evidence.py` sau khi
  restore các selected members; so hash body slice với field được lưu.
- **Proposed minimal fix:** Producer/extractor của run mới phải bind exact
  span và body version riêng; kiểm source mentions và relation trong span.
  Không sửa hash/offsets trong historical facts. Phạm vi reprocess và contract
  cần được chốt theo thẩm quyền trước production execution.
- **Regression tests:** Hai tests mới chứng minh whole-body hash không chứng
  nhận subspan và kiểm exact span/out-of-bounds. Current extraction code đã
  có span hashing; không patch lại bằng logic từ producer branch cũ.
- **Remaining blockers:** V3 producer lineage, normalization/extractor
  versions, mapping/identity và upstream stage approval.

### Bước 12.7 — Mapping và temporal semantics còn thiếu

`entity_map_v1.json` trong release cũng 0 bytes. Chưa khôi phục được registered
mapping có mention_id, canonical_entity_id, availability và decision basis;
không tạo mapping từ mention strings hoặc đổi nhãn `v1_mock`.

Acquisition receipts giờ có thể kiểm độc lập, nhưng `retrieved_at_real` là
engineering time; nó không chứng minh public observation time hoặc world
validity của từng fact. Không dùng receipt time thay `evidence_observed_at`.
Supporting-claim/adjudication lineage của producer v3 vẫn thiếu.

Vì vậy không cấp verdict semantic correctness cho mẫu 30 facts trong lượt này.
Source excerpts được lưu để review; các facts có span mismatch chưa có căn cứ
để chứng nhận rằng offset đang trỏ đúng supporting evidence. Không tự lấy đoạn
khác, đổi gold, bỏ fact hoặc sửa corpus theo kết quả TransE.

### Bước 12.8 — Báo cáo, tests và điểm dừng

Thêm `scripts/audit_recovered_v3_evidence.py` và
`tests/test_recovered_evidence_span.py` (2 PASS). Ruff không lỗi lint; warnings
quyền đọc fixture directories cũ vẫn còn. Package v3 giữ nguyên hashes.

Report: `outputs/upstream_recovery_release_20261014/review_20261013T175025Z_5237eafe/`.
Gồm release/v3 comparison summary, receipt checks, recovered body hashes,
sample raw hash checks, nguyên sample plan, source excerpts/span checks,
actual executed code snapshot, experiment manifest và independent verification.
Code snapshot trong run là bản trước khi bỏ hai unused imports; thay đổi lint
này không sửa logic và report không bị ghi đè.

Tier: IMPLEMENTED recovery audit/tests; TESTED 2 fixtures; EXECUTED recovery
và read-only verification trên archived real payloads; VERIFIED exact hashes/
receipts/offset binding trong phạm vi nêu trên. G1/G2, mapping, semantic quality
và production vẫn BLOCKED. Không rerun acquisition/Stage 4.3 hoặc sửa source lock.

**Điểm dừng tiếp theo:** cần producer v3 run/code/config manifests, mapping/
adjudication decisions gốc và quyết định reprocess có thẩm quyền. Có thể review
findings và thiết kế remediation từ source artifacts đã khôi phục; không được
coi lỗi hash là đã RESOLVED chỉ vì body/raw đã lấy lại được.

## 13. Kiểm producer v3 và lập phạm vi remediation — đã thực hiện

### Bước 13.1 — So fingerprints với lịch sử Git

Đối chiếu 13 candidate config hashes của v3 với 32 reachable commits.
Tối đa 6/13 khớp exact Git blob bytes. Bảy files còn lại khớp khi mô phỏng
CRLF của checkout Windows; cả 13 tương thích sáu commits thuộc họ producer.
Không sửa config originals, không dùng newline conversion để cấp source-lock
PASS. Vì nhiều commits có cùng config và thiếu v3 run/code manifest, chưa
xác định được actual producer commit.

### Bước 13.2 — Đối chiếu ID rules và khôi phục mention links cho audit

1.803/1.803 FactVersionID suffixes trỏ tới claim có trong final claims table;
source/relation/span/hash fields khớp claim đó. Subject/object IDs đều khớp
`ent_ + SHA256(strip(lower(mention)))[:8]`; LogicalFactID khớp hash của
`subject|relation|object` lấy 16 hex. Cơ chế này có trong code producer candidate.

Audit tạo mention links cho 1.389 legacy entity IDs, gắn DIAGNOSTIC_ONLY và
availability=null. Không ghi vào mapping production, không tuyên bố aliases
đúng/canonical/as-of. Kết quả mới giúp thu hẹp 8 ambiguous candidate-claim
matches trước đó bằng cú pháp IDs, nhưng vẫn thiếu explicit supporting-claim
decision lineage có thẩm quyền.

### Bước 13.3 — Kiểm remediation boundary của extractor hiện tại

Current extractor đã dùng exact subspan hash và both-role grounding. Thêm
tests gọi trực tiếp extractor bằng ASCII/Unicode fixtures có context trước/sau
span; field output phải là hash đoạn evidence, khác hash toàn body. Claim chỉ
có subject mà thiếu object trong slice phải vào quarantine/review.

Suite extractor boundary/producer diagnostics/recovered span: **7 passed**;
Ruff không lỗi lint. Không có patch production source hoặc historical-data
rewrite. Code producer candidate cũ không được transplant vào nhánh hiện tại.

### Bước 13.4 — Ghi phạm vi remediation có thể review

Hồ sơ [V3_REMEDIATION_SCOPE_20261014.md](audit/V3_REMEDIATION_SCOPE_20261014.md)
lưu dependencies, stage impact set, acceptance checks và finding V3-PROD-001.
Đây là REVIEW REQUIRED, không phải amendment hoặc approved production plan.

Phạm vi đề xuất: Stage 4.9 claims/span → 4.10 temporal normalization → 4.11
as-of adjudication → 4.12 append-only FactVersion → 4.13 quality; sau đó mới
review impacts lên freeze/events/boundaries/snapshots/parity. Chỉ được thực thi
một stage mỗi lần khi đủ inputs/policies/gates và user yêu cầu; không rerun
Stage 4.3 hoặc ghi đè historical artifacts.

### Bước 13.5 — Evidence và điểm dừng

Audit output: `outputs/v3_producer_lineage/20261013T175716Z_b01c9055/`.
Có config comparisons từng commit/file, ID-rule checks, diagnostic mention
links, reference code snapshots, manifest và independent integrity verification.
Code snapshot giữ đúng bản chạy trước lint-only removal of unused import.

IMPLEMENTED/TESTED: diagnostics, tests và scope document. EXECUTED/VERIFIED:
read-only metadata/ID-rule checks; actual producer/mapping/gates chưa VERIFIED.
Chưa chạy production reprocess. Cần producer originals và approved contract,
identity/temporal policies để vượt blocker; nội dung khoa học không được tự
quyết bằng cách suy ra từ hashes.

## 14. Bảng quyết định và dọn repository — đã thực hiện

Người dùng yêu cầu lập bước tiếp theo, dọn file không cần thiết và ghi lại quy
trình. Lượt này chuẩn bị hồ sơ review và thực hiện cleanup engineering; không
áp dụng policy draft hoặc thực thi production reprocess.

### Bước 14.1 — Chuyển remediation scope thành bảng quyết định cụ thể

Tạo [V3_DECISION_TABLE_20261014.md](audit/V3_DECISION_TABLE_20261014.md), gồm
11 IDs: sources, producer lineage, contract, text representation, identity,
observation/acceptance clocks, support/revision, reprocess scope, quality/gold
và window/boundaries. Mỗi mục có hướng đề xuất, lựa chọn khác/hệ quả, hồ sơ
hoặc evidence phải có và trạng thái DECISION/EVIDENCE REQUIRED.

Có mẫu ghi approval theo policy ID/version/path/hash, người có thẩm quyền,
evidence references và affected stages. Không điền approval thay người duyệt.
Với các mục còn thiếu evidence, việc duyệt lựa chọn không tạo ra payload/history
đang thiếu. Không dùng một câu “duyệt toàn pipeline” để bỏ stage prerequisites.

### Bước 14.2 — Kiểm exact hashes của các proposal được tham chiếu

7/8 files khớp manifest proposal tháng 10. `contract_field_matrix.yaml` hiện
có SHA-256 `9cc5e6079fb5f3635cb6bf25593e7b9a3312a12465efe7b3b72c6250371de6c3`,
trong khi manifest cũ khai báo
`716eaf74a1915fff4d39349b6071cd0a03cb7610ed8a3accb73ca151bbd2948c`.
Bản CRLF mô phỏng từ LF hiện tại cho hash manifest, nhưng exact current bytes
không khớp. Không sửa manifest cũ hoặc tự công nhận approval cho schema.

Bảng review ghi rõ mismatch và cả hai hashes. Cần revision/hash binding mới
cho matrix trước approval. Bằng chứng ở
`outputs/repo_cleanup_20261014/policy_hash_review.json`.

### Bước 14.3 — Xác định mục cleanup từ trạng thái thực tế

Rà Git status, tracked files, root directories và references. `diff.txt` là
tracked file 0 bytes, không thấy code/docs/tests tham chiếu. Có 30 directories
tạm/cache cũ: `.pytest-*`, `.tmp-pytest-*`, `tmp-c4c9-*`, `.pytest_cache`,
`.ruff_cache` và root `__pycache__`. Không có tracked files trong các directories.

Giữ scripts/tests active, audit reports, source PDF đúng lock, data v3 và mọi
experiment/recovery outputs. Không coi untracked source original là rác.
Không đọc hoặc cleanup `data/locked_test/`.

### Bước 14.4 — Archive có thể khôi phục, không xóa lịch sử

Chuyển 30 directories và `diff.txt` vào
`backups/repo_cleanup_20261014/`. Dùng native PowerShell `Move-Item -LiteralPath`;
kiểm resolved source là direct child của workspace, resolved target là child
của backup root, không reparse root, không target collision, và diff.txt vẫn
rỗng trước khi move. Không chạy recursive delete hoặc Git clean/reset.

31 mục đều ARCHIVED. Old root paths đã rời workspace root; payload trong backup
giữ lại. Git diff thấy `diff.txt` bị xóa khỏi active tracked layout, nhưng bản
0-byte còn ở backup. `.pytest_cache` mới được tạo lại cho verification, không
ghi đè bản cũ trong backup.

Plan/path map/results: `outputs/repo_cleanup_20261014/plan.json` và `result.json`.
Nếu cần khôi phục mục nào, dùng path map và native `Move-Item`, kiểm root/path
và destination chưa tồn tại trước; không ghi đè cache/run mới.

### Bước 14.5 — Ngăn stage nhầm artifacts và bỏ exclusions đã hết tác dụng

`.gitignore` bổ sung root patterns cho historical pytest/temp directories,
`/data/KG_lan2/` và exact path của audit backup `preexisting.patch`.
Data/patch vẫn ở disk; không đưa chúng vào Git tự động. `backups/` và
`outputs/` đã được ignore từ trước.

Bỏ danh sách 25 Ruff exclusions theo tên cũ trong `pyproject.toml` vì các
directories đã archive; Ruff dựa vào Git ignore. Production source/tests
vẫn được lint. Không đổi dependencies, model configs hoặc scientific parameters.

### Bước 14.6 — Giữ một basetemp chuẩn hoạt động sau cleanup

Lượt full suite đầu bị 173 fixture setup errors do parent `.pytest_cache`
chưa tồn tại cho nested basetemp sau archive; đây không phải production finding.
Tạo lại parent rồi full suite PASS. Sau đó đổi mặc định trong `pytest.ini`
sang `--basetemp=.pytest-tmp`: parent là repo root luôn tồn tại, một temp
directory chuẩn được Git ignore. Chạy lại 5 tests dùng tmp_path theo mặc định
đạt, không cần tạo nested parent thủ công.

Lượt full-suite verification:

```powershell
python -m pytest -q --basetemp=.pytest_cache/repo_cleanup_verified_20261014 --tb=short --junitxml=outputs/repo_cleanup_20261014/fixture_results.xml
```

**345 passed, 10 skipped**, một pytz deprecation warning, Python 3.12.10.
Sau đổi default basetemp, fixture smoke **5 passed**. Không cộng hai lượt thành
số test của một suite và không coi skipped placeholders là scientific PASS.

### Bước 14.7 — Verify cleanup không thay dữ liệu hoặc protected contracts

113 files của package v3 đều giữ nguyên hashes so với inventory ban đầu.
Proposal PDF vẫn khớp source lock. `git diff` không thay source lock,
`configs/protocol_v1.yaml`, `config/schema.yaml`, decision log hoặc `src/`.
Ruff toàn repo `--no-cache` PASS, không còn warnings quyền đọc directories
tạm cũ; diff check PASS. Verify result ở
`outputs/repo_cleanup_20261014/verification.json`.

### Bước 14.8 — Trạng thái sau lượt này

IMPLEMENTED: bảng quyết định, archive cleanup, ignore/lint/pytest configuration.
TESTED: fixture suite và default basetemp checks đạt. VERIFIED: cleanup path
map, active layout và v3/proposal hashes trong phạm vi đã nêu. Không EXECUTED
production stage; Gate A/G1/G2 vẫn BLOCKED. Ở thời điểm cleanup, sửa mới chưa
commit; đợt publish tiếp theo được ghi ở bước 14.9.

Hồ sơ đã sẵn sàng để người có thẩm quyền review từng ID; contract matrix
hash mismatch và evidence gaps vẫn phải giải quyết. Chưa áp dụng schema/
mapping/time decisions hoặc amendment.

### Bước 14.9 — Commit và publish nhánh legacy theo yêu cầu

Người dùng yêu cầu commit/push ngày 14/10. Đóng gói thành commit audit/recovery
`fc46402`, cleanup `80897d2` và commit tài liệu riêng. Hai commit legacy trước
`08c352b` và `d97325e` cũng thuộc phần chưa publish từ mốc remote `6ef3ff5`.
Nhánh đích là `codex/transe-legacy-exploration`, không merge main.

Chọn rõ từng file code/tests/config/docs; không stage `data/`, `outputs/`,
`backups/` hoặc proposal PDF untracked. Kiểm diff và Ruff trước commit; không
coi publish code là giải quyết các scientific blockers. Xác minh push bằng
remote branch SHA so với local HEAD, không chỉ bằng thông báo branch local.

## 15. Artifacts và tái hiện

| Công việc | Code / báo cáo |
|---|---|
| Audit v3 | `outputs/v3_review_20261013/audit_v3.py` và `report.json` |
| Smoke T01 | `scripts/run_legacy_transe_t01.py` |
| Split feasibility | `scripts/audit_legacy_split_t01.py` |
| Đánh giá 101/20 | `scripts/evaluate_legacy_t01.py` |
| Phân tích lỗi | `scripts/analyze_legacy_t01_errors.py` |
| Kiểm tra cơ chế | `tests/scientific/test_transe_mechanics.py` |
| Chẩn đoán training/logging | `scripts/diagnose_legacy_t01_training.py` |
| Kiểm observer | `tests/test_legacy_training_observer.py` |
| Content/mapping readiness | `scripts/audit_v3_content_readiness.py` |
| Sample/path guards | `tests/test_v3_content_readiness.py` |
| Recovery evidence verification | `scripts/audit_recovered_v3_evidence.py` |
| Exact span hash tests | `tests/test_recovered_evidence_span.py` |
| Producer lineage diagnostics | `scripts/audit_v3_producer_lineage.py` |
| Extractor remediation boundary | `tests/kg_pipeline/test_v3_extractor_remediation_boundary.py` |
| Bảng quyết định | `docs/audit/V3_DECISION_TABLE_20261014.md` |
| Cleanup plan/results | `outputs/repo_cleanup_20261014/` |

Training/evaluation runners tạo output run mới, không ghi đè checkpoint cũ.
Audit v3/error analysis dùng output cố định và exclusive-create; muốn tái hiện
phải chọn output mới. Evaluation runner hiện yêu cầu file witness audit ở
`outputs/legacy_split_audit/20261013T165714Z_b4c0f356/report.json` để đối chiếu;
checkout mới chỉ có code sẽ cần artifact này cùng data đúng hash.

Các run lưu code thực tế, resolved scope/config, mapping, git commit/dirty_state,
input/output hashes, manifests và kết quả kiểm lại. Base commit là `6ef3ff5`
với working tree dirty khi chạy; không giả vờ chỉ commit đó đủ tái hiện mọi
file mới. `outputs/` được ignore, cần bảo quản riêng khi bàn giao.

## 16. Trạng thái hiện tại và điều kiện đi tiếp

| Tier | Phạm vi đã đạt |
|---|---|
| IMPLEMENTED | Legacy runners, audit scripts, ranking và mechanics tests, báo cáo |
| TESTED | Các suite mục tiêu đã nêu; không coi tổng các lượt là một full-suite result |
| EXECUTED | Thử legacy T01, logging replay, content readiness và release recovery audit |
| VERIFIED | Hashes, exact replay, ranks/logs, recovered body/raw/receipts, span-binding findings |

Gate A/G1/G2, mapping/provenance certification và M2 production vẫn BLOCKED.
Chưa thực hiện alignment/null/drift/SED+/QA/H1/H2. Chưa merge main.

**Điểm dừng:** body/raw/receipt recovery, producer diagnostics, remediation
scope và bảng quyết định đã lập; repository temporary files đã archive.
Mapping authority/actual producer
lineage còn thiếu và exact-span binding sai ở 1.788 facts. Cần approved
dependencies nêu trong hồ sơ remediation trước semantic certification. Code và phần
bổ sung content/recovery được đóng gói trong đợt publish ở bước 14.9; data/
artifacts vẫn lưu riêng ngoài Git. Nếu thử mô hình tiếp, thiết kế
run mới trước và chốt candidate policy, dữ liệu đánh giá và configuration.
Không retune trên 20 held-out rồi coi điểm mới là độc lập;
không sửa corpus/cutoff/mapping dựa vào outcomes. Các blocker upstream phải
được giải quyết theo protocol, không theo việc cấu hình nào cho điểm tốt hơn.
