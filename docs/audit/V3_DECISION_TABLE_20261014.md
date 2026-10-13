# Bảng quyết định trước remediation production v3

Ngày: 14/10/2026. Phiên bản: 1. **REVIEW REQUIRED / NOT APPROVED / NOT APPLIED.**

Mục tiêu là xác định rõ lựa chọn khoa học nào cần duyệt và chứng cứ nào phải
cung cấp trước khi Stage 4.9 có thể chạy. Yêu cầu lập bảng và dọn repo không
được diễn giải thành approval cho schema migration, canonical identity, clocks
hoặc production reprocess. Các invariants đang có tiếp tục áp dụng.

## 1. Kết quả và phạm vi đã biết

- Đã khôi phục body/raw/receipts có hashes khớp references v3, trong phạm vi
  audit nêu ở [quy trình](../QUY_TRINH_THU_TRANSE_LEGACY_T01.md).
- 1.788/1.803 facts không bind exact evidence span; không sửa artifacts cũ.
- Canonical IDs là hash surface mentions; actual producer commit chưa được
  chứng thực, dù config/ID rules tương thích với họ nhánh producer.
- Current extractor đã có exact-span hashing và both-role grounding, đã
  regression-tested. Code tests PASS không giải quyết các dependencies bên dưới.
- Hai Markdown originals theo source lock hiện vẫn thiếu; proposal PDF đúng
  hash được giữ lại. Source-lock replacement không thể tự thực hiện bằng CRLF
  conversion, empty manifests hoặc hashes từ candidate branch.

## 2. Bảng quyết định để review

| ID | Nội dung cần chốt | Hướng đề xuất | Lựa chọn khác / hệ quả | Chứng cứ hoặc hồ sơ cần có | Trạng thái |
|---|---|---|---|---|---|
| V3-D01 | Authoritative sources | Giữ source-lock hiện tại và khôi phục hai originals đúng bytes | Nếu originals không còn: amendment chọn replacement bytes/hash, lý do và precedence từng khác biệt; không sửa lock trực tiếp | Originals hoặc [source amendment draft](m1_implementation_20261004/source_amendment_draft.md) có approval | EVIDENCE REQUIRED |
| V3-D02 | Actual producer lineage | Lấy run manifest, exact commit/dirty patch, code/config/model/cache hashes v3 | Nếu không lấy được: ghi UNVERIFIED lineage, chốt run mới từ verified inputs; không nhận candidate commit làm actual producer | Bundle của đúng producer run v3 | EVIDENCE REQUIRED |
| V3-D03 | Public contract migration | Giữ public field names của `config/schema.yaml`, explicit serializers và typed PK/FK/nullability; chọn version mới sau review matrix | Versioned rename chỉ khi có migration/amendment rõ; không dùng implicit alias hay bỏ fields | [C3 decision package](m1_c3_decision_package.md), [contract proposal](m1_implementation_20261004/policies/contract.md), full field matrix | DECISION REQUIRED |
| V3-D04 | Text representation và hashes | Giữ `clean-text-identity-v1`; bind body representation/version riêng với exact code-point span/hash | NFC hoặc normalization khác cần version, approval và rebuilding offsets từ stage body; không convert text rồi giữ span cũ | Body/parser/extractor/normalization contracts và cache fingerprints | DECISION REQUIRED |
| V3-D05 | Canonical identity và aliases | Adopt occurrence-level MentionID, append-only canonical registry/mapping decision có basis, availability, version và reviewer provenance | Legacy lowercase-name hashes chỉ tiếp tục ở audit/legacy; không đủ điều kiện cho mapping production | [identity proposal](m1_implementation_20261004/policies/identity.md), original mapping evidence hoặc kế hoạch adjudication mới | DECISION + EVIDENCE REQUIRED |
| V3-D06 | Evidence observation basis | Review public capture/revision evidence có exact payload/hash/URL/locator; basis không đủ thì pending | Publication/update metadata chỉ được dùng nếu có rule được đăng ký và evidence tương ứng; retrieval time tự nó không thay scientific clock | [temporal proposal](m1_implementation_20261004/policies/temporal.md), stage-specific evidence records | DECISION + EVIDENCE REQUIRED |
| V3-D07 | KG acceptance clock | Review proposed earliest time khi sufficient supports và identity decisions đều khả dụng, giữ engineering adjudication time riêng | Rule khác cần explicit scientific definition; không backdate hoặc lấy ingestion time thay acceptance | C3 acceptance definition và support/identity prerequisites đã chốt | DECISION REQUIRED |
| V3-D08 | Source support/conflict/revision | Append-only support groups có basis về independence, pending khi conflict chưa đủ policy | Không tự đặt số nguồn/ngưỡng/confidence hoặc chọn conflict winner từ model outcomes | [support/revision proposal](m1_implementation_20261004/policies/support_revision.md) và evidence group attestations | DECISION + EVIDENCE REQUIRED |
| V3-D09 | Reprocess scope | Run/version mới; nếu exact body representation được reuse thì bắt đầu claim/span Stage 4.9, review downstream impacts | Nếu normalization/body changes: bắt đầu từ stage body sớm nhất bị ảnh hưởng; không chỉ thay hash claims/facts cũ | [remediation scope](V3_REMEDIATION_SCOPE_20261014.md), approved dependencies và supersession/invalidation plan | DECISION REQUIRED |
| V3-D10 | Quality evaluation/gold | Review independent gold procedure và freeze thresholds từ pilot có thẩm quyền; giữ outcome blindness | Mẫu 30 diagnostic facts không tự trở thành gold hoặc accuracy estimate; MRR legacy không thay G2 | [quality proposal](m1_implementation_20261004/policies/quality.md), actual gold/procedure/threshold approvals | DECISION + EVIDENCE REQUIRED |
| V3-D11 | Window và boundaries | Giữ window hiện hành 01/03/2025–31/08/2026; review outcome-blind boundary procedure | Mở tới tháng 09/2026 cần amendment/approval; không rewrite cutoff cũ hoặc âm thầm bỏ T07–T10 | [boundary proposal](m1_implementation_20261004/policies/boundaries.md), cutoff policy và approved scope | DECISION REQUIRED nếu thay baseline |

Các hướng đề xuất D03–D11 chưa được tự áp dụng. Với D01/D02/D05/D06/D08/D10,
approval không tạo ra payload hoặc history đang thiếu; phải kiểm chứng evidence.
Không có lựa chọn nào cho phép một lần phê duyệt chung mở cả pipeline.

## 3. Hồ sơ proposal và exact hashes

Đã đối chiếu các file proposal hiện có với
`m1_implementation_20261004/policies/manifest.json`: **7/8 files khớp exact
hash**; `contract_field_matrix.yaml` lệch hash. Hash manifest tương thích với
bản CRLF mô phỏng từ file LF hiện tại, nhưng không được coi là exact original.
Status vẫn `PROPOSED_NOT_APPROVED`, `runtime_apply_allowed=false`. Giữ nguyên
manifest cũ; review contract matrix cần revision/hash binding mới trước approval.

| Hồ sơ | SHA-256 phiên bản đang review |
|---|---|
| contract.md | `5f74b7d93e38e0e40a4e1501b2773fd645b37c55014c7307137d24eccdd0c538` |
| contract_field_matrix.yaml (current bytes, manifest mismatch) | `9cc5e6079fb5f3635cb6bf25593e7b9a3312a12465efe7b3b72c6250371de6c3` |
| identity.md | `e235c95147c43f353c06a3799922277e0d10f97d51fbe1f7a2bbb8f66f2d910d` |
| temporal.md | `b2a31898f0f0a3e7606299e718507ea04d639fbe5b3f54460628ac12d965bd4a` |
| support_revision.md | `afd0a08250682ce55cdf78c10e7f03e6d97c823eeccefdc2662ce2cc5629942c` |
| quality.md | `53e409164d88924f5a199415a8922895f8348129488d601a8ed1b0d65dffd281` |
| boundaries.md | `071b126b325f8524afe455fcd7501d772473829188776c2d00b1027f81538db7` |

Review nội dung từng file/matrix, không chỉ tên hoặc table summary. Một sửa đổi
proposal cần revision/hash mới; không sửa file cũ rồi giữ approval reference.

Manifest cũ khai báo matrix hash
`716eaf74a1915fff4d39349b6071cd0a03cb7610ed8a3accb73ca151bbd2948c`.
Đối chiếu raw/LF/CRLF ở `outputs/repo_cleanup_20261014/policy_hash_review.json`.
Không bật schema migration từ proposal có binding lệch.

## 4. Mẫu phản hồi của người có thẩm quyền

Cho mỗi quyết định cần ghi đủ:

```text
Decision ID:
Lựa chọn / điều chỉnh được duyệt:
Policy ID, version, path và SHA-256:
Evidence references kèm hashes:
Người có thẩm quyền / nguồn approval:
Ngày và phạm vi hiệu lực:
Schema version / fields / clock definition còn cần hoàn thiện:
Affected stages và reprocess/supersession scope:
Conditions và blockers chưa được miễn:
```

Đây là mẫu trống, không tạo approval giả. Chưa ghi decision log và chưa tạo
amendment có hiệu lực trong lượt lập bảng này. Người duyệt có thể yêu cầu sửa
proposal hoặc cung cấp thêm evidence thay vì chấp nhận toàn bộ.

## 5. Thứ tự thực hiện sau review

1. Giải quyết source authority và producer/new-run lineage (D01/D02).
2. Chốt contract/text, identity, evidence/acceptance và support policies (D03–D08).
3. Implement đúng lựa chọn đã duyệt; chạy fixtures/contract/temporal tests.
4. Verify actual inputs/config baseline/Gate A; thiếu prerequisites vẫn BLOCKED.
5. Khi stage prerequisites đủ và user yêu cầu, execute riêng Stage 4.9 trong
   run mới; validate và viết Stage Report, rồi dừng. Không auto-advance 4.10.
6. Review quality/boundaries và downstream stages theo prerequisites của chúng.

Policy decisions có thể review song song, nhưng execution vẫn đúng thứ tự.
Không đổi ontology, seeds, metrics hoặc thresholds để làm cho code/quality PASS.

## 6. Trạng thái hoàn tất của lượt này

Đã lập bảng reviewable với 11 IDs, evidence gaps và exact proposal hashes.
Không thực hiện production stage hoặc scientific decision. Gate A/G1/G2 và
M2 production vẫn BLOCKED. File này là hồ sơ governance, không phải artifact
chứng nhận khoa học.
