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

## 11. Artifacts và tái hiện

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

Training/evaluation runners tạo output run mới, không ghi đè checkpoint cũ.
Audit v3/error analysis dùng output cố định và exclusive-create; muốn tái hiện
phải chọn output mới. Evaluation runner hiện yêu cầu file witness audit ở
`outputs/legacy_split_audit/20261013T165714Z_b4c0f356/report.json` để đối chiếu;
checkout mới chỉ có code sẽ cần artifact này cùng data đúng hash.

Các run lưu code thực tế, resolved scope/config, mapping, git commit/dirty_state,
input/output hashes, manifests và kết quả kiểm lại. Base commit là `6ef3ff5`
với working tree dirty khi chạy; không giả vờ chỉ commit đó đủ tái hiện mọi
file mới. `outputs/` được ignore, cần bảo quản riêng khi bàn giao.

## 12. Trạng thái hiện tại và điều kiện đi tiếp

| Tier | Phạm vi đã đạt |
|---|---|
| IMPLEMENTED | Legacy runners, audit scripts, ranking và mechanics tests, báo cáo |
| TESTED | Các suite mục tiêu đã nêu; không coi tổng các lượt là một full-suite result |
| EXECUTED | Thử legacy T01, đánh giá 101/20, phân tích artifacts, logging replay 101 train |
| VERIFIED | Hashes, exact replay smoke/logging, saved ranking metrics, fixture mechanics |

Gate A/G1/G2, mapping/provenance certification và M2 production vẫn BLOCKED.
Chưa thực hiện alignment/null/drift/SED+/QA/H1/H2. Chưa merge main.

**Điểm dừng:** hoàn tất tài liệu, fixture diagnostics và logging replay. Nếu tiếp tục, thiết
kế một thử nghiệm mới và chốt trước candidate policy, dữ liệu đánh giá và
configuration. Không retune trên 20 held-out rồi coi điểm mới là độc lập;
không sửa corpus/cutoff/mapping dựa vào outcomes. Các blocker upstream phải
được giải quyết theo protocol, không theo việc cấu hình nào cho điểm tốt hơn.
