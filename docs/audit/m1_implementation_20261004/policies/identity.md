# C4-IDENTITY-01 — Mention và mapping as-of

Version: 1. Status: **PROPOSED / NOT APPROVED**.
Findings: M1-001/011/012; M1-RV-002.

## Đề xuất cần duyệt

- MentionID xác định từ body-variant identity, exact text hash, normalization
  version, span start/end và mention-rule version. Hash định danh occurrence,
  không chứng minh canonical identity.
- Giữ identity normalization hiện tại. Không dùng lowercase/fuzzy match để
  tự merge các tên hoặc bật NFC mới trong production.
- Canonical entity ID được cấp trong append-only registry có type và evidence;
  reuse entity chỉ khi mapping decision có basis tường minh.
- MappingDecision có mention_id, canonical_entity_id, availability, basis,
  confidence, policy version, reviewer provenance và supersedes reference.
- Scientific mapping availability phải có proof về evidence identity tại thời
  điểm đó; ngày reviewer làm việc lưu riêng, không tự backdate decision.
- Tra cứu quyết định theo mention_id và cutoff, không dùng current catalog.
  Nếu mapping chỉ xuất hiện sau evidence observation, claim vẫn có thể được
  xét ở thời điểm đủ mapping/support theo temporal policy; không đưa vào
  snapshot trước mapping availability.
- LogicalFactID theo ontology relation key hiện có cộng scope/context; thay
  key/ontology là semantic migration riêng, không giữ ID cũ giả vờ tương thích.
- Parent mapping thiếu, cycle, canonical collision hoặc competing decisions:
  BLOCKED/pending cần review; không chọn lexical ID làm người thắng.

## Ví dụ, migration và tests

- Hai lần xuất hiện “ABC” ở hai body variants có MentionID khác nhau; chúng chỉ
  cùng canonical entity sau quyết định có căn cứ.
- Alias công bố tháng 9 không resolve mention tháng 6 bằng current catalog.
- Mapping mới không làm thay mapping đang dùng trong snapshot cũ.
- Giữ mọi old mapping record. Rebuild claims/facts/snapshots trong run mới từ
  stage identity sớm nhất bị ảnh hưởng; lineage giữ mapping decision đã dùng.
- Tests: stable mention ID với input như nhau; đổi text/span/version đổi ID;
  alias muộn, collision, invalid chain, missing proof và exact round-trip.

Blockers: chưa có mapping history production và chưa có approval identity/
LogicalFactID policy. Không đổi schema/runtime resolver theo draft này.
