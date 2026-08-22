## Phạm vi

- Module/owner:
- Issue/task:
- Thay đổi chính:

## Ảnh hưởng đến scientific contract

- [ ] Không thay đổi scientific/frozen contract.
- [ ] Có thay đổi contract/config và lý do đã được ghi bên dưới.

Affected protocol/config fields (nếu có):

## Tests / gates

- [ ] `python -m ruff check .`
- [ ] `python -m pytest -q`
- [ ] Đã chạy gate verification liên quan (`verify_w1.py`, `verify_g1.py`, `verify_w7.py` khi áp dụng)

Tests được thêm/cập nhật:

## Artifacts / provenance

- [ ] Không sinh retained artifact.
- [ ] Retained artifact có immutable manifest/hash trail.

## Freeze / amendment

- [ ] Pre-freeze hoặc không chạm frozen paths.
- [ ] Post-freeze sensitive change có `amendments/*.yaml` hợp lệ.

## Ghi chú tích hợp

Upstream/downstream owner(s) cần review interface này:
