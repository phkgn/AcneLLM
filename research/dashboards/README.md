# visualization/ — dashboard HTML cho BAO CAO he thong

Sinh cac trang dashboard (kien truc, KB, evaluation, workflow, finetune) bang
`generate_all.py`. Dau ra: `visualization/index.html` + cac thu muc con.

KHONG PHAI `visualize/` — thu muc do ve bieu do phan bo dataset.

# AcneLLM visualization catalog

Các chart dữ liệu được tạo lại từ source/data hiện tại bằng:

```powershell
.\.venv\Scripts\python.exe .\visualization\generate_all.py
```

Mở `index.html` để xem gallery. `manifest.json` ghi source path, kích thước,
mtime và SHA-256 của từng input đã dùng. Các nhóm output:

- `KB/`: nguồn chunk, trust/language/category, histogram độ dài và độ phủ tài liệu.
- `finetune_intaker/`: split, intent, case type, confidence, field coverage và quota.
- `finetune_generator/`: lấy duy nhất từ `datagen/roledata`; gồm split, sample kind,
  input style, synthetic context, retry/rejection audit, integrity và độ dài hội thoại.
- `evaluation/`: dataset v3.2, intake, retrieval và full six-arm ablation.
- `architecture/`: file `.drawio` bảy trang và PNG 1920×1080 dựng/kiểm tra bằng
  diagrams.net; gồm system context, chat/SSE, intake/safety, RAG/KB, finetune,
  evaluation và Docker deployment.
- `repository/`: package/LOC/file/test/model inventory và module architecture.
- `_overview/`: hình tổng quan quy mô artifact.

Không dùng ảnh cũ làm input. `generate_all.py` giữ nguyên PNG trong
`architecture/` nhưng đăng ký chúng vào gallery/manifest cùng provenance; khi
kiến trúc đổi, rebuild `.drawio` rồi export lại từ diagrams.net. Các biểu đồ eval
phải được hiểu cùng provenance trong `evaluation/reports/run_full_v3_2/`.
