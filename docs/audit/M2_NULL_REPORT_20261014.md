# M2 — empirical null và Leave-Target-Out — 14/10/2026

Nhánh `codex/m2-drift-workflow`, base `2860235`. User yêu cầu
**"Hãy thực hiện bước tiếp theo"** sau alignment stage đã verify.
Stage config `configs/m2_null_v1.yaml` bind approved Dev config và alignment
manifest `920b78c4ec057ff95f3e6cd812394cf3cae43e275f286779bfeee583ca6403ea`.
Receipt kiểm độc lập alignment được bind bằng exact SHA-256; stage kiểm lại
mọi input/artifact hashes và verifier-code fingerprint của receipt. Noise
measurement dùng saved Q/fit means; không training, chọn lại anchors hoặc
thực hiện alignment mới.

## Thiết kế trước execution

- Population: toàn bộ persistent entities trong 9 adjacent transitions,
  **6.897 entity×transition**, không lựa chọn theo drift/RR/H1.
- Mỗi entity×transition có đúng 6 noise observations: pairs (13,37),
  (13,101), (37,101) ở mỗi endpoint. Giữ endpoint/pair IDs và alignment/
  checkpoint/anchor hashes riêng; không xem seed-pair observations là các
  statistical units độc lập.
- Noise = `1 - cos((x_seedA - mu_source) Q, x_seedB - mu_target)` từ saved
  centered alignment. Chỉ 54 within-snapshot alignment inputs; không đo
  cross-time displacement ở stage này. Undefined centered cosine phải fatal,
  norm floor 1e-12 giữ mức guard đang có của math helper.
- Degree bins `<3`, `3–5`, `>=6`, chỉ bằng snapshot trước. Merge pooled sparse
  buckets strictly adjacent, chọn neighbor nhiều observations hơn, tie về trái;
  min pooled/reference observations 5. Không merge dựa trên MAD magnitude.
- Bucket membership sau pooled merge được giữ cố định cho LTO. Mỗi target
  bỏ cả 6 observations của chính mình khỏi reference; không target-specific
  remerge. Lưu reference entity count và observation count để thấy support thật.
- Null median/MAD; robust scale `1.4826*MAD`. Empty reference: median/MAD/
  scale=None và reason; insufficient samples hoặc MAD<1e-12: unavailable có
  reason, giữ các statistics tính được. Không bịa zero defaults hoặc dùng
  epsilon để cứu degenerate reference. Epsilon 1e-4 đã duyệt chưa được dùng
  vì SED+ thuộc stage sau.
- Ghi population/degrees/pair jobs và resolved config trước noise computation.
  Component version `saved_alignment_empirical_null_v1`, hai independent
  computation repeats cho mỗi transition, append-only outputs/manifests.

## Engineering verification trước execution

Targeted workflow + six-pair null/drift regressions: **23 passed** trên
Python 3.11.9; Ruff toàn repo PASS. Fixtures kiểm all-six target exclusion,
target-observation perturbation không đổi chính target LTO reference,
empty/zero-MAD/insufficient references, adjacency/ties/empty middle bucket,
thiếu pair/degree/entity, wrong endpoint, unavailable alignment, non-finite
or out-of-range noise, zero centered norm, nullable statistics, exact Parquet
bytes và independent verifier rejection của target-inclusion/fake defaults.
Threshold 7/17 chỉ xuất hiện ở unit fixtures để chạm boundary/merge cases;
production Dev stage giữ approved threshold 5.

Parquet contracts versioned trong schema metadata:
`saved_null_observations_v1`, `saved_null_lto_v1`. Observation provenance và
degree/bucket fields required; LTO median/MAD/scale nullable cho unavailable.
JSON null artifacts và experiment manifests nối hai analysis Parquet tables
với exact upstream hashes, không có unprovenanced dataframes.

## Execution và independent validation

Run: `outputs/m2_null/20261014T042450Z_43e91590/`.
Lệnh execution: `.venv-m1/Scripts/python.exe scripts/run_m2_null.py`.
Stage hoàn tất trong 59,49 giây, đúng **41.382 observations / 6.897
entity×transition**. Có đủ six endpoint-pair IDs cho mọi row group;
**6.897/6.897 LTO references available** theo approved rules. Không có sparse
merge trên dữ liệu thật: mọi nonempty pooled bucket đã có ít nhất 6 observations
và ngưỡng đã duyệt là 5. Giữ nguyên buckets sau LTO, không đổi ngưỡng.

| Transition | Entity×transition | Noise rows | Low / medium / high entities | Min LTO reference entities |
|---|---:|---:|---|---:|
| T01→T02 | 167 | 1.002 | 150 / 15 / 2 | 1 |
| T02→T03 | 343 | 2.058 | 313 / 23 / 7 | 6 |
| T03→T04 | 503 | 3.018 | 464 / 27 / 12 | 11 |
| T04→T05 | 646 | 3.876 | 597 / 34 / 15 | 14 |
| T05→T06 | 787 | 4.722 | 719 / 50 / 18 | 17 |
| T06→T07 | 936 | 5.616 | 864 / 50 / 22 | 21 |
| T07→T08 | 1.057 | 6.342 | 969 / 64 / 24 | 23 |
| T08→T09 | 1.176 | 7.056 | 1.071 / 79 / 26 | 25 |
| T09→T10 | 1.282 | 7.692 | 1.154 / 98 / 30 | 29 |

9/9 null JSON repeat pairs exact bytes; noise-observation computation repeats
cũng exact serialized rows. Hai global Parquet files được serialize hai lần
trước lưu, exact physical bytes trong cùng môi trường. Mọi values hữu hạn;
LTO MAD nhỏ nhất **0.0181775981**, vượt guard 1e-12. Không dùng epsilon hoặc
statistics downstream để thay đổi availability/buckets.

**Giới hạn support có thật:** high bucket T01→T02 có 2 entities; mỗi target LTO
chỉ còn **1 reference entity / 6 correlated seed-pair observations**. Available
ở đây nghĩa là đủ approved observation-count/MAD guards, không chứng minh
reference population lớn hay 6 độc lập statistical samples. Support counts
được lưu trong mỗi LTO row; không tự gộp lại bucket hoặc thay protocol sau
khi thấy kết quả.

Lệnh independent validation: `.venv-m1/Scripts/python.exe
scripts/verify_m2_null.py --run outputs/m2_null/20261014T042450Z_43e91590`.
Report `independent_verification_20261014T042638Z_7d9e8c02.json`:

- Tính lại **41.382/41.382 centered noise values** bằng vectorized NumPy từ
  saved checkpoints/Q/means, không gọi primary noise function.
- Reconstruct buckets/adjacent merges từ pretransition degrees; tính lại
  **6.897/6.897 LTO references**, median/MAD/scale và availability, xác nhận
  loại cả sáu observations của target. Parquet/JSON thống nhất exact values.
- Kiểm **491/491 input hashes**, **55/55 artifact hashes**, archived code,
  **9/9 transition manifests**, config/mapping/endpoint/seed/anchor/checkpoint
  lineage và exact null replays.
- Raw external snapshots, prior backbone/alignment artifacts, approved
  configuration và executable code không đổi trong execution.

Aggregate manifest SHA-256:
`7bdd6de62fc0f506661957e15909a9ecc43bdcfe935227425d22635436976b89`.

## Bàn giao và verification tiers

Artifacts cho drift stage:

- `noise_observations.parquet`: 41.382 rows, endpoint/seed identities,
  displacement, alignment/checkpoint/anchor hashes và pretransition degree/bucket.
- `lto_statistics.parquet`: 6.897 entity×transition rows, median/MAD/robust
  scale, reference entity/observation counts, availability/reason và null hash.
- Per-transition `null_repeat_1.json` / `null_repeat_2.json` chứa six-value
  arrays, degree/bucket mappings, merge log, pooled stats và target LTO stats;
  experiment manifests nối complete immutable lineage.
- Registered jobs, resolved config, input/code hashes+copies, alignment
  verification receipt, aggregate summary/manifest và independent report.

**IMPLEMENTED:** saved-artifact noise/null/LTO component, stage runner,
analysis schemas và independent verifier.
**TESTED:** targeted 23 passed; full repository **479 passed, 10 skipped**
trong 18,08 giây trên Python 3.11.9; Ruff toàn repo và diff checks PASS.
Lệnh full suite: `.venv-m1/Scripts/python.exe -m pytest -q -rs -p
no:cacheprovider --basetemp=outputs/m2_null_full_regression_20261014`.
10 skips có sẵn trong `tests/test_hard_invariants.py:149–196`, không dùng để
certify scientific gates.
**EXECUTED:** null/LTO Dev stage trên real artifact-backed inputs.
**VERIFIED:** independent arithmetic/Parquet/lineage checks kể trên, chỉ
phạm vi null Dev; không scientific G3/M1 certification.

Files mới: `src/drift/artifact_null.py`, `scripts/run_m2_null.py`,
`scripts/verify_m2_null.py`, `tests/test_m2_null_workflow.py`,
`configs/m2_null_v1.yaml`, báo cáo này. Cập nhật `docs/M2_EXECUTION_PLAN.md`
và `docs/PROGRESS.md`, giữ các M1 edits hiện có. Code/docs mới còn untracked,
chưa commit/push; dữ liệu/generated outputs không stage. Diff tracked:
`git diff -- docs/PROGRESS.md`.

Stage tiếp theo sau yêu cầu riêng: dùng ba **cross_time** alignment results
đã lưu cho từng transition để tính median temporal displacement, signed
excess và SED+ bằng LTO statistics đã verify. Không retrain, chọn lại anchors
hoặc tạo private snapshots. Stage null này dừng tại báo cáo.

## Phạm vi và điểm dừng

M2 Dev trên real external-package artifacts theo user-authorized M1 exception;
không temporal identity/M1/G3 certification. Chưa tính delta_time, signed
excess, SED+, QA/H1 hoặc M4. STOP sau báo cáo stage theo AGENTS.md §8.2 và
stage config. Không sửa historical artifacts, protocol/source lock hoặc
đọc locked_test. Python 3.10 local chưa tested.
