# AcneLLM visualization catalog

Toàn bộ hình trong thư mục này được tạo lại từ source/data hiện tại bằng:

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
- `workflow/`: runtime, RAG, datagen, evaluation và Docker input-to-output flows.
- `repository/`: package/LOC/file/test/model inventory và module architecture.
- `_overview/`: hình tổng quan quy mô artifact.

Không dùng ảnh cũ làm input; mỗi lần chạy đều đọc artifact hiện tại. Các biểu đồ
eval phải được hiểu cùng provenance trong `evaluation/reports/run_full_v3_2/`.
