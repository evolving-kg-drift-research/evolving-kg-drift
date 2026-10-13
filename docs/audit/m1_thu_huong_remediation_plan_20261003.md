# Kế hoạch tích hợp và hoàn thiện M1 sau review nhánh Thu Hương

Ngày lập: 2026-10-03
Nhánh làm việc: `codex/m1-thu-huong-remediation`
Điểm xuất phát: `6000f3834b62e36cf3239cabe5eb14db5352a2a5`
Nhánh đối chiếu: `origin/fix/data-pipeline-compliance-cont` tại
`e19fe25d2325a53ebf49ada27cff4692aa1c6638`.

## Đích đến

Giữ một nhánh tích hợp các guard M1 đã có, chọn lọc phần code có ích trên
nhánh Thu Hương, sửa lỗi mà review đã tái hiện, và hoàn thiện C3–C9 mà không
đưa ra quyết định khoa học thay người có thẩm quyền. M1 chỉ hoàn thành khi
các stage production được xác minh bằng artifact thật, Gate A/G1/G2 đạt và
Stage 4.18 chứng minh Neo4j read-back parity. Code/fixture xanh chỉ đóng phần
kỹ thuật.

## Thứ tự triển khai

### R0 — Tạo điểm làm việc có thể truy vết

- Đã tạo nhánh mới từ `6000f38`; các thay đổi đang mở được giữ nguyên.
- Giữ ZIP và guide bất biến, bỏ qua bằng `.gitignore`.
- Giữ nguyên `AGENTS.md` đang được người dùng sửa; không đưa thay đổi ấy vào
  patch M1.
- Khóa lại common base, tip nhánh Thu Hương và inventory/diff trước mọi merge.
- Không commit cho tới khi người dùng cho phép lại hoặc M1 hoàn thành, theo
  chỉ dẫn commit trước đó.

### R1 — Sửa lỗi đã tái hiện trên code tương thích snapshot

- Sửa `build_snapshot` để lọc validity trước khi chọn revision, đúng thứ tự
  Stage 4.17. Fact cũ còn hiệu lực phải tồn tại tới khi correction được biết
  **và** có hiệu lực.
- Cả hai snapshot paths kiểm tra duplicate FactVersionID, parent bị thiếu/chưa
  được biết, parent sai LogicalFactID và revision cycle. Hai correction cùng
  cạnh tranh hiệu lực cho một parent giờ trả blocker cần adjudication, không
  tự chọn bằng evidence-time rồi lexical ID.
- Giữ `build_snapshot_edges_and_support` làm đường snapshot production; nó
  bắt buộc clock acceptance và mapping artifact. Hàm tương thích cũ không
  chứng nhận snapshot production vì không nhận đủ các clocks/mappings đó.
- Bằng chứng đóng bước cần regression future-effective correction/retraction,
  late correction, accepted-after-cutoff và so sánh runner với hàm tương thích.
- **Trạng thái:** IMPLEMENTED + TESTED: 35 test hẹp đã qua, Ruff đạt.
  EXECUTED/VERIFIED trên production: chưa.

### R2 — Chọn lọc thay đổi từ nhánh Thu Hương

- Đối chiếu từng thay đổi trong adjudication, extraction, temporal và runner
  với source-of-truth hierarchy và C0–C9 hiện có.
- Phụ lục [safety review](m1_thu_huong_branch_safety_supplement_20261003.md)
  ghi nhận hash sai ở 2/3 source bytes, helper tạo placeholder/rewrite lock,
  historical 108-block rerun có thể chạy mặc định và wrapper tự chạy inventory,
  Gate A lẫn tests, helper copy có thể ghi đè Stage 4.4 artifacts và hosted
  model mode. Không port các script hoặc PASS claims này.
- Chỉ port code có semantics đã nằm trong `docs/data_pipeline_spec.md` hoặc
  contract đã được phê duyệt. Không port sửa đổi protocol/source-lock,
  decision log, hoặc fallback production để giữ nhánh Thu Hương “PASS”.
- Không thay snapshot schema/hashes cũ tại chỗ; mọi semantic rebuild tạo run
  và artifacts phiên bản mới, ghi supersession.
- Đóng bước bằng diff review, downstream call graph và regression coverage
  cho các consumer bị ảnh hưởng.

### R3 — Hoàn tất C3: contract và temporal clocks

- Dùng `config/schema.yaml` làm contract máy đọc, đối chiếu mọi Parquet schema,
  PyArrow/dataclass và các cột thực từ gói ZIP.
- Viết và xin duyệt quyết định cho field migration, evidence-time basis,
  ingestion/retrieval/adjudication/acceptance clocks, identity, timezone và
  phạm vi reprocess. Tách quyết định khoa học khỏi execution report.
- Sau phê duyệt mới tạo contract version mới, migrate producer/consumer theo
  cùng contract; xóa fallback 2020, lấy retrieval làm evidence, tự gán timezone.
- Đóng bước bằng 17/17 contract audit, round-trip field preservation, thiếu
  temporal evidence bị quarantine/BLOCKED, không có field mất khi handoff.
- **Blocker hiện tại:** chính sách chưa duyệt; C3 vẫn BLOCKED.

### R4 — Hoàn tất C4–C6: mapping, text, claims và revisions

- C4: giữ MentionID và MappingDecisionID trong lineage; fingerprint catalog;
  mapping as-of chỉ nhận quyết định khả dụng tại cutoff. LogicalFactID/identity
  policy phải được duyệt.
- C5: giữ raw/body bytes cũ; normalization Unicode có version mới; EvidenceSpan
  bind clean-text hash/version; cache extraction bind đủ input/model/tokenizer/
  prompt/schema/decoding/runtime, locked replay thiếu hoặc bị sửa thì dừng.
- C6: SourceClaim theo nguồn, support aggregation và conflict decision tách
  riêng; nối FactVersion trước qua verified parent artifact; corrections và
  retractions append-only xuyên run.
- Đóng mỗi phần bằng runner integration trên fixture: alias/entity collision,
  Unicode/offsets, cache tampering, independent supports, conflict pending,
  correction/retraction. Fixture không cấp scientific PASS.
- **Blocker hiện tại:** identity, normalization và conflict policies chưa duyệt.
- **C4 update 2026-10-03:** runner-level fixtures now cover a late mapping in
  adjudication and a superseding mapping across two snapshot cutoffs; the
  focused suite passed 48 tests and Ruff passed. C4 remains partial because
  stable MentionID/MappingDecisionID lineage is missing and runtime schema
  remains incompatible. See [C4 runner report](m1_c4_runner_regression_20261003.md).
- **C5 update 2026-10-03:** extraction now fails closed when normalization is
  absent or requests unapproved NFC; locked cache identity includes exact
  dependency/parser/runtime fingerprints, and the extractor manifest is bound
  by a physical/semantic JSON ArtifactRef. Focused suite: 52 passed; Ruff
  passed. C5 remains production-blocked because schema lacks the version field,
  NFC and contract migration are unapproved, and the configured local runtime
  hash is not independently attested. See [C5 report](m1_c5_text_provenance_20261003.md).
- **C6 update 2026-10-03:** adjudication now persists per-provenance-path
  `source-claims-v1` JSON with stage hash bindings; a declared parent missing a
  verified FactVersion store fails closed. Cross-run support does not create a
  correction, while conflict/retraction remains pending. Focused suite: 25
  passed; full `tests/kg_pipeline/`: 176 passed. C6 remains partial because
  source independence/support aggregation and revision policy are not approved,
  and the runtime schema lacks those
  contracts, and no production parent chain was executed or verified. See
  [C6 report](m1_c6_claim_revision_20261003.md).

### R5 — Hoàn tất C7–C9: snapshot, handoff, parity và locked CI

- C7: mọi snapshot bind physical/semantic/input/code/config/mapping/boundary
  hashes; thiếu artifact/ref/gate invalidates certificate; chạy đúng thứ tự
  known/accepted → validity → revision → tombstone → mapping as-of. M2 nhận
  đúng snapshot manifest đã xác minh.
- C8: producer dựng Parquet; materializer đọc chính Parquet vào Neo4j thử
  nghiệm; đọc lại database và so node/edge sets, counts, relation/time metadata.
  Không tạo `neo4j_edges` từ cùng input rồi gọi đó là read-back.
- C9: locked mode chặn config draft, dependency thiếu lock, certificate sai
  run/hash, cache không replay và mọi gate bypass; CI tách code checks khỏi
  artifact-backed certification.
- Đóng bằng hai run fixture độc lập cùng semantic hashes, mutation/tamper
  failures và database read-back parity. Không chứng nhận production qua fixture.
- **Blocker hiện tại:** Gate A/G1/G2, verified artifact chain và Neo4j read-back.
- **C7 update 2026-10-03:** snapshot manifest `v2` binds exclusion hash and
  per-snapshot YAML output refs; M2 checks producer lineage, input/config/code/
  mapping/boundary hashes, support/exclusion provenance, and persisted G1/G2
  certificates. The public single-Parquet loader now requires a verified run
  context, closing the stage/gate bypass. Relevant suite: 204 passed; targeted
  Ruff passed. C7 remains fixture-only: acceptance-clock/schema, approved
  boundary policy, Gate A/G1/G2 and real frozen artifacts are missing. See
  [C7 report](m1_c7_snapshot_certification_20261003.md).
- **C8 update 2026-10-03:** added a verified-run materializer that reads
  canonical Parquet, writes append-only Neo4j entities/edges, reads back through
  separate transactions, and compares exact node/edge sets with temporal
  support metadata. `tests/kg_pipeline/` plus temporal/M2 adapter tests: 210
  passed; targeted Ruff passed. The tests use an in-memory driver double.
  A real read-back is blocked because no Neo4j driver/daemon is available and
  the Stage 4.10/acceptance-clock, Gate A/G1/G2 and frozen-artifact blockers
  remain. See [C8 report](m1_c8_neo4j_readback_20261003.md).

## Đường production — một stage mỗi lần

Trước mỗi stage, xác minh input, manifests, policy approval và mọi dependency.
Stage 4.3 chỉ đối chiếu read-only; không chạy lại 108-block acquisition và
không dùng mtime để tạo provenance. Các output chưa có trong ZIP cần được
export từ đúng producer run, giữ hash và lineage gốc.

Sau khi Gate A mở bằng evidence thật, xử lý và báo cáo riêng từng Stage
4.4 → 4.5 → 4.6 → 4.7 → 4.8 → 4.9 → 4.10 → 4.11 → 4.12 → 4.13 →
4.14 → 4.15 → 4.16 → 4.17 → 4.18. Mỗi stage kết thúc bằng report
`PASS | FAIL | BLOCKED`, artifact inventory/hashes và kiểm invariant; **dừng**
chờ yêu cầu tiếp tục. Không stage sau nào được mở chỉ vì stage trước có report
hoặc tests xanh.

Gói upstream cần truy xuất tối thiểu gồm immutable raw/body, retrievals/public
URLs/memberships, claims/span/text versions, mappings/availability, decisions
và clocks, resolved config/environment/cache, independent human gold cùng
threshold được duyệt, Gate A/G1/G2, transition metadata, snapshot support/
exclusions và Neo4j database read-back. Gói `evolving_kg_downstream_v2.zip`
chỉ là evidence kiểm tra output export; chưa thay thế những đầu vào này.

## Kế hoạch verification và tiêu chí hoàn tất

1. Chạy test hẹp sau mỗi patch, sau đó bộ `tests/kg_pipeline/`, invariant tests
   và các gate code-check thích hợp; lưu command/log, không tính fixture là
   scientific evidence.
2. Chạy `ruff check .` và diff checks trên đúng revision sạch sau khi thay đổi;
   cảnh báo truy cập thư mục temporary phải được ghi, không gộp thành PASS mù.
3. Chỉ production EXECUTED khi runner dùng artifacts thật/frozen; chỉ VERIFIED
   khi validator độc lập xác nhận manifests, clocks, lineage và hashes.
4. Chỉ `M1 DONE` khi Stage 4.3 được đối chiếu, stage bắt buộc tới 4.18 đều PASS,
   Gate A/G1/G2 có certificates đúng run/hash, có tối thiểu ba lineage thật
   source→snapshot cùng toàn corpus validation, Parquet–Neo4j full set equality,
   và M2 đọc đúng gói frozen đã chỉ định.

## Hiện trạng và điểm dừng

- Nhánh mới: `codex/m1-thu-huong-remediation`.
- Đã sửa validity-before-revision trong hàm tương thích `build_snapshot`.
- Chưa chạy tests hoặc production stages trong lượt này.
- Gói ZIP có 10 exports nhất quán về file hash/replay/CSV, nhưng thiếu
  provenance, mapping as-of, human gold, gates/manifests và Neo4j read-back.
- C3 và các quyết định identity/conflict/normalization chưa được duyệt;
  Gate A/G1/G2, production M1 và M2 tiếp tục BLOCKED.
