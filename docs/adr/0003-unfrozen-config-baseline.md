# ADR 0003: Giữ configuration bundle đã đối chiếu ở trạng thái unfrozen

Trạng thái: Proposed; blocked vì cần scientific authority

## Bối cảnh

Repository có hai nhóm configuration không chứng minh được là tương đương và các source-locked original đang không có sẵn. `retrieved_at_real` và `ingested_at_real` chưa được chứng minh là alias; ontology file hiện hành có 10 relation trong khi lịch sử nói 11.

## Quyết định

Ghi toàn bộ candidate file hash và các khác biệt chưa resolve vào bundle `PROPOSED_UNFROZEN`. Không merge key, không chọn theo directory name/mtime/version number, không đổi relation/cardinality và không rename time field. Ticket A có thể inventory raw bytes nhưng không thể dùng proposal này để phát hành scientific data.

## Hệ quả

Gate A bị blocked cho tới khi có baseline được duyệt và source lock hợp lệ. Khi resolve phải nêu rõ semantic effect và artifact A/B/C/D nào cần run mới hoặc reprocessing.
