# Pilot validation TransE-L2 T01 — 03/11/2026

**EXECUTED / VERIFIED trong phạm vi pilot Dev.** Đã train từ đầu ba seed
13/37/101 và kiểm lại toàn bộ các epoch từ artifacts đã lưu. Không cấp scientific
gate hoặc thay full-snapshot backbone.

## Công dụng trong quy trình đề tài

Pilot đo đồng thời training loss, validation loss và chất lượng xếp hạng trên
triple chưa dùng làm positive gradient examples. Nhờ vậy có thể đánh giá liệu
việc tối ưu TransE-L2 có đi cùng tín hiệu dự đoán held-out hay không, thay vì suy
ra hiệu quả từ training loss. Kết quả là chẩn đoán M2; không dùng để chỉnh anchors,
null buckets, SED+, H1/H2 hoặc tự chọn epoch cho backbone chính.

## Authorization và cấu hình đã chạy

Yêu cầu người dùng thực hiện bước kế tiếp sau candidate đã review được ghi trong
`outputs/kge_validation_registration/20261103_t01_dev_v1/approval.json`. Approval
chỉ bind stage `quality_validation_dev`, design SHA-256
`5f68b2d88c5978f8b0d689dfed1d1f8a262893966f1ad2d0a89b6cd2ef7e6bef`.
`approved.yaml` là file mới; candidate cũ được giữ nguyên.

- Canonical T01 data3.1, snapshot physical SHA-256
  `42ded6c58c7cb3ac27b07a964cd9a0bff802afcf43bf09f70c920cf13abcda5e`.
- 101 train / 20 validation; giữ exact memberships, đủ167 entities/10 relations.
- TransE-L2, d64, lr0.01, margin1, normalized entities, per-triple SGD; 50 epochs
  cố định cho từng seed. Không warm-start, early-stop, chọn best epoch hoặc test.
- Training negative filter chỉ theo train positives. Validation dùng20 fixed
  negative pairs đã bind; head/tail ranking có40 queries,167 candidates và known
  T01 positive filtering tại evaluation. Ties theo exact average rank.
- Preflight `ready=true`, `executed=false`, zero blockers trước khi cấp run directory.

Run: `outputs/kge_validation_dev/20261103_t01_three_seed_v1/`.

```powershell
.venv-m1/Scripts/python.exe scripts/run_kge_validation.py --config outputs/kge_validation_registration/20261103_t01_dev_v1/approved.yaml --execute --output outputs/kge_validation_dev/20261103_t01_three_seed_v1
```

## Kết quả quan sát

| Seed | Training loss epoch1→50 | Validation loss epoch1→50 | Validation MRR epoch1→50 | Hits@1/3/10 ở epoch50 |
|---|---:|---:|---:|---:|
| 13 | 1,0050 → 0,3946 | 0,9864 → 0,8882 | 0,0210 → 0,1203 | 0% / 22,5% / 32,5% |
| 37 | 1,0153 → 0,4093 | 0,9708 → 0,8397 | 0,0344 → 0,1004 | 0% / 12,5% / 30,0% |
| 101 | 0,9898 → 0,4221 | 0,9931 → 0,8761 | 0,0347 → 0,1481 | 0% / 20,0% / 35,0% |
| Mean ba seed | 1,0034 → 0,4087 | 0,9835 → 0,8680 | 0,0300 → 0,1229 | 0% / 18,3% / 32,5% |

- Training loss trung bình giảm **59,27%**; validation loss giảm **11,74%**.
  Validation MRR tăng **0,0929 điểm** và cải thiện ở cả ba seed. Đây là bằng chứng
  trực tiếp hơn training loss về tín hiệu dự đoán trên validation hiện có.
- Mean validation loss epoch31–40 **0,8998** → epoch41–50 **0,8775**; MRR tương ứng
  **0,0955 → 0,1142**. Xu hướng cuối vẫn cải thiện; chưa xác định plateau hoặc epoch tối ưu.
- Mean Hits@10 cuối **32,5%**, Hits@1 **0%** ở cả ba seed. Xếp hạng còn hạn chế.
- Final MRR ba seed khớp pilot d64 trước trong tolerance1e-14. Bằng chứng mới là
  validation loss/ranking trajectories, không phải mức MRR cuối mới cao hơn.

Biểu đồ raw epochs, CSV, summaries và scripts xuất kết quả ở
`outputs/kge_validation_pilot_report/20261103_t01_three_seed_v1/`.
Vùng tô trên hình là min–max giữa ba seed, không phải confidence interval.

## Kiểm chứng và giới hạn

- 3/3 jobs đúng config đã bind; **150 checkpoints/epoch records**, không skipped
  training sample trong **15.150 positive visits**.
- Verifier NumPy tính lại **150 validation losses và 6.000 ranking rows** từ
  checkpoint vectors; mỗi receipt bind child manifest và exact verifier source.
- Kiểm lại **513 training artifacts**, **7 training input refs** và exact input
  copies. Candidate **57 input refs/13 artifact refs** giữ nguyên, bao gồm42
  protected inputs. Parent/child mapping/snapshot/query identities khớp.
- Training online loss và fixed-pair validation loss có sampling/evaluation
  khác nhau; so xu hướng trong từng chuỗi, không suy diễn khoảng cách giữa hai
  đường là thước đo trực tiếp của overfitting. Online SGD trajectory không được
  độc lập replay; sample accounting và log lineage được kiểm.
- 20 triples đã được dùng làm validation/model selection từ trước; 40 head/tail
  queries không phải40 quan sát độc lập. Kết quả không là final test hoặc chứng
  minh khả năng khái quát toàn KG/multi-hop. Không đối chiếu baseline khác split.
- Không chạy acquisition, locked test, alignment/null/drift/M4; không đổi
  protocol, source lock, decisions, checkpoints lịch sử hoặc gate status.

## Bàn giao và điểm dừng

IMPLEMENTED/TESTED runner ở stage trước (688 passed/10 skipped); không sửa source
code hoặc rerun full suite trong lượt execution này. EXECUTED/VERIFIED: real T01
Dev pilot, numerical validation/ranking và lineage nêu trên; không production
certification. Stage report và exact derived-artifact manifest được lưu riêng,
không thêm/ghi đè files trong completed training run.

Thay đổi repo trong lượt này: báo cáo này và `docs/PROGRESS.md`; preparation,
training logs, plots và verification evidence nằm trong các output dirs mới.
Diff: `git diff -- docs/PROGRESS.md`; report mới chưa stage. Chưa commit/push.

**STOP sau pilot report.** Việc chọn thiết kế đánh giá độc lập hoặc mở rộng sang
backbone mới cần quyết định riêng và các readiness prerequisites phù hợp.
