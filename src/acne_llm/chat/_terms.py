"""Shared keyword term lists for intent routing and intake scoping.

Single source of truth — both ``intent_router`` and ``intake`` import from here
to avoid silent drift when one side is updated but the other is not.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Question / knowledge-signal terms
# Dùng để nhận diện câu hỏi dạng "là gì / tại sao / cách / bao lâu…"
# Cả intent_router (_QUESTION_TERMS) lẫn intake (_KNOWLEDGE_QUESTION_TERMS)
# đều cần tập hợp này — giờ chỉ còn một chỗ duy nhất.
# ---------------------------------------------------------------------------
QUESTION_TERMS: tuple[str, ...] = (
    # ── Câu hỏi trực tiếp ──────────────────────────────────────────────────
    "là gì", "la gi",
    "tại sao", "tai sao",
    "vì sao", "vi sao",
    "nguyên nhân", "nguyen nhan",
    "cách", "cach",
    "làm sao", "lam sao",
    "thế nào", "the nao",
    "như nào", "nhu nao",
    "có nên", "co nen",
    "hoạt động thế nào", "hoat dong the nao",
    "cơ chế", "co che",
    "tác dụng", "tac dung",
    "có sao không", "co sao khong",
    "có ảnh hưởng", "co anh huong",
    "có tốt không", "co tot khong",
    # ── Sản phẩm / thành phần ──────────────────────────────────────────────
    "nên dùng", "nen dung",
    "dùng gì", "dung gi",
    "sản phẩm nào", "san pham nao",
    "loại nào", "loai nao",
    "nên chọn", "nen chon",
    "có tốt không", "co tot khong",
    "hiệu quả không", "hieu qua khong",
    "có hiệu quả không", "co hieu qua khong",
    "có tác dụng không", "co tac dung khong",
    "có an toàn không", "co an toan khong",
    "có dùng được không", "co dung duoc khong",
    "review", "so sánh", "so sanh",
    "khác gì", "khac gi",
    "oil-free", "non-comedogenic",
    "không gây bít tắc", "khong gay bit tac",
    "mua ở đâu", "mua o dau",
    "giá bao nhiêu", "gia bao nhieu",
    # ── Thời gian / diễn biến ──────────────────────────────────────────────
    "bao lâu", "bao lau",
    "mấy tuần", "may tuan",
    "mấy tháng", "may thang",
    "bao nhiêu tuần", "bao nhieu tuan",
    "bao nhiêu tháng", "bao nhieu thang",
    "khi nào hết", "khi nao het",
    "khi nào khỏi", "khi nao khoi",
    # ── Lo ngại / đánh giá ─────────────────────────────────────────────────
    "có bình thường không", "co binh thuong khong",
    "có nguy hiểm không", "co nguy hiem khong",
    "có đáng lo không", "co dang lo khong",
    "có cần khám không", "co can kham khong",
    "có cần gặp bác sĩ không", "co can gap bac si khong",
    "có ảnh hưởng gì không", "co anh huong gi khong",
    "có cần lo không", "can lo khong",
    "có nặng không", "nặng không", "co nang khong", "nang khong",
    "có ổn không", "co on khong",
    # ── Điều trị ───────────────────────────────────────────────────────────
    "nên làm gì", "nen lam gi",
    "phải làm sao", "phai lam sao",
    "làm gì bây giờ", "lam gi bay gio",
    "xử lý thế nào", "xu ly the nao",
    "giải quyết thế nào", "giai quyet the nao",
    "điều trị thế nào", "dieu tri the nao",
    "cách trị", "cach tri",
    "cách chữa", "cach chua",
    "có tự khỏi không", "co tu khoi khong",
    "có tự hết không", "co tu het khong",
    "có cần điều trị không", "co can dieu tri khong",
    "cần làm gì", "can lam gi",
    "có phải đi khám không", "co phai di kham khong",
    "nên đi khám không", "nen di kham khong",
    "mụn có tự hết không", "mun co tu het khong",
    "có hết được không", "co het duoc khong",
    "có lan sang không", "co lan sang khong",
    "có lây không", "co lay khong",
    # ── Phân loại / định danh ──────────────────────────────────────────────
    "mụn này là gì", "mun nay la gi",
    "đây là mụn gì", "day la mun gi",
    "tình trạng này là gì", "tinh trang nay la gi",
    "loại da này", "loai da nay",
    "tại sao bị", "tai sao bi",
    "vì sao nổi", "vi sao noi",
    "nguyên nhân do đâu", "nguyen nhan do dau",
    "do đâu mà bị", "do dau ma bi",
    "tình trạng tôi", "tinh trang toi",
    "tình trạng của tôi", "tinh trang cua toi",
    "tình trạng mình", "tinh trang minh",
    "nghe có vẻ nặng không", "nghe co ve nang khong",
)
