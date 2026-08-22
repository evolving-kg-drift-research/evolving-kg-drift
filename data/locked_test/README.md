# Locked-test boundary

Locked-test **payload không được commit vào Git** theo mặc định.

Thư mục này chỉ làm rõ boundary của repository. Trước W8 locked run phải implement access mechanism theo protocol:

- locked payload không khả dụng cho ordinary Dev workflows trước freeze;
- sau W7, locked runner chỉ có read-only access;
- access log + resolved config được ghi trước khi metrics được tạo;
- rerun chỉ vì documented engineering failure;
- contaminated/old run được giữ để audit.

Git diff/CODEOWNERS không thể chứng minh một developer chưa từng mở local ignored file. Không dùng Git path protection thay cho locked-run access procedure.
