"""roledatav2 — sinh ROLE-data v2, kế thừa `datagen.roledata`.

Khác v1 đúng bốn điểm, mọi thứ còn lại dùng lại nguyên code v1:

1. Tài liệu tham khảo được render VÀO `messages[user]` (v1 để ở field anh em
   `synthetic_context` rồi `finalize/export.py` vứt đi -> 0/2.945 mẫu có tài liệu).
2. Mỗi case có band độ dài `len_chars` thay vì để độ dài trôi tự do.
3. Case mang nội dung phải liệt kê `points` và gate kiểm đủ số ý.
4. Quota dịch từ nhóm vai/giọng sang nhóm mang nội dung.

Anchor, writer, split, export dùng lại v1 không sửa.
"""

__all__ = ["config", "gates", "generator", "pipeline"]
