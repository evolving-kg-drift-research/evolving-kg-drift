# C3-CONTRACT-01 — Contract migration

Version: 1. Status: **PROPOSED / NOT APPROVED**.
Finding: M1-009 / M1-RV-002. Authority: config/schema.yaml và đặc tả M1.

## Đề xuất cần duyệt

- Phiên bản public contract kế tiếp: 1.1.0; giữ nguyên tất cả tên bảng/cột đã
  khai báo, bao gồm `FactVersionID`, `LogicalFactID` và `url`.
- Mỗi bảng khai báo `fields`, `columns.{field}.arrow_type`, `nullable`,
  `primary_key`, `foreign_keys`. Runtime không được tự tạo aliases từ similarity.
- Serializer FactVersion ánh xạ tường minh `FactVersionID ↔ fact_version_id`,
  `LogicalFactID ↔ logical_fact_id`, `url ↔ source_url`. Tên đã trùng giữ nguyên.
  Fields hiện chưa biểu diễn được phải bổ sung model hoặc bảng liên kết; không bỏ.
- Giữ timestamp dưới dạng Arrow string ở v1.1 để giảm thay đổi vật lý; serializer
  chuẩn hóa timezone-aware thành UTC ISO-8601, domain validator kiểm strict.
  Giá trị declared timestamp không parse được được giữ ở raw metadata; không
  trở thành scientific clock. Không được tự suy timezone.
- IDs, versions, hashes, URLs và reason codes: string; offsets: int64;
  confidence: double hữu hạn trong [0,1]; flags: bool; claim ID collections:
  list<string> được sort/dedup; không stringify list thành JSON ở public fields.
- PK/FK bắt buộc không null. Required scientific clocks của accepted FactVersion
  không null; valid_to và supersedes_version_id nullable. Thiếu valid_from không
  được invent giá trị: không xuất active fact, giữ quyết định pending/quarantine.
- `object_id` và `object_value`: đúng một biểu diễn theo ontology; literal
  cần typed-value declaration riêng. V1 KGE chỉ nhận entity-object triples,
  các literal vẫn bảo toàn trong fact store và ledger, không ép thành entity.
- Giữ `ingested_at_real`, temporal basis/confidence/source và evidence span
  trong model; register phần provenance bổ sung theo bảng liên kết. Không
  lược bỏ provenance đang có chỉ để runtime khớp 17 bảng.
- Bổ sung `body_variants.normalization_version`; mention/provenance join phải
  giữ body variant, raw source và offsets. Giữ extraction candidates là bảng
  trung gian riêng; `claims` chỉ chứa các claim đã resolve/normalize.
- SourceClaim và support events là bảng phụ trợ được đăng ký version/type/PK/FK
  rõ ràng; không coi JSON report là public table tương đương.

## Phần phải có trước khi áp dụng

Đã xuất `contract_field_matrix.yaml`: 17 bảng/174 fields, proposed types,
nullability, runtime mapping và PK/FK; đây không phải schema runtime đã duyệt.
Cần duyệt matrix và hoàn thiện các bảng phụ trợ theo temporal/identity/support.
Nêu rõ
type/nullability của từng field và source event cung cấp giá trị. Các quy tắc
trên là thiết kế đề xuất, chưa là một schema hoàn chỉnh đã được duyệt; không
được apply migration chỉ bằng việc chấp thuận tên phiên bản.

## Ví dụ và kiểm chứng

- Hợp lệ: Python fact có `fact_version_id=F1`; serializer ghi `FactVersionID=F1`
  và deserializer tái tạo đúng model, mọi clocks và support IDs giữ nguyên nghĩa.
- Không hợp lệ: đổi tên `source_id` của body variant thành publisher source;
  ép `accepted_into_kg_at=ingested_at_real`; làm mất object_value/scope.
- Tests: exact names/types/nullability, missing/extra field, PK/FK, finite
  confidence, timestamp/offset domain, serializer round-trip, literal exclusions.
- Migration: run mới từ stage sớm nhất cần field không thể khôi phục; không
  sửa Parquet cũ hoặc tự cấp manifest mới cho ZIP thiếu dữ liệu.

Engineering đã làm: typed declaration auditor có tests và báo UNDECLARED khi
schema chưa khai báo. Runtime schema chưa migrate; 9/17 mismatch vẫn BLOCKED.
