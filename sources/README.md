# Authoritative source artifacts

Trước khi tạo `v0.1-source-lock`, đặt **đúng authoritative source bytes** được tham chiếu bởi `data/manifests/sources.lock.json` vào thư mục này.

`verify_w1.py` tính hash trực tiếp từ các file thật và so sánh với:

- `data/manifests/sources.lock.json`;
- `configs/protocol_v1.yaml`.

Không âm thầm thay bằng một PDF/DOCX/Markdown được export lại có SHA-256 khác, kể cả khi nội dung nhìn giống nhau. Nếu authoritative source thay đổi, đó phải là một provenance decision có chủ đích trước W1 source lock.

Expected filenames:

- `huce_evolving_kg_modular_proposal(8).pdf`
- `Research_Execution_Plan_v1.0.md`
- `Research_Execution_Plan_v1.1_Patch.md`
