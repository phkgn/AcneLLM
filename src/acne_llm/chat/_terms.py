"""Shared keyword term lists for intent routing and intake scoping.

Single source of truth — both ``intent_router`` and ``intake`` import from here
to avoid silent drift when one side is updated but the other is not.
"""
from __future__ import annotations

from functools import lru_cache
import re


@lru_cache(maxsize=128)
def _terms_regex(terms: tuple[str, ...]) -> re.Pattern[str] | None:
    cleaned = tuple(dict.fromkeys(t.strip().lower() for t in terms if t and t.strip()))
    if not cleaned:
        return None
    pattern = "|".join(re.escape(term) for term in sorted(cleaned, key=len, reverse=True))
    return re.compile(pattern, flags=re.IGNORECASE)


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """Fast shared substring matcher for static chat term lists."""
    regex = _terms_regex(tuple(terms))
    return bool(regex and regex.search(text.lower()))


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
    "nghe có vẻ nặng không", "nghe co ve nang khong",
)


COMPLAINT_TERMS: tuple[str, ...] = (
    # Chê câu trả lời — không dấu
    "tu van vay", "tu van the",
    "tra loi vay", "tra loi the",
    "khong hieu", "hoi lai", "hoi roi",
    "noi roi", "biet roi", "hoi hoai", "lap lai",
    "tu van kieu gi", "cau tra loi vo nghia",
    "khong giup duoc gi", "toan hoi lai",
    "vo ich", "khong dung", "tra loi sai",
    "te qua", "chan qua", "hieu gi dau",
    "tra loi linh tinh", "khong chinh xac",
    "bot vo dung", "bot do", "tra loi lan",
    "khong ro rang", "kho hieu", "khong thuc te",
    "co biet gi dau", "biet gi ma tu van",
    "tra loi cu", "tra loi nhu nhau",
    "vong vo", "dai dong", "khong truong hop",
    # unicode
    "tư vấn vậy", "tư vấn thế",
    "trả lời vậy", "trả lời thế",
    "không hiểu", "hỏi lại", "hỏi rồi",
    "nói rồi", "biết rồi", "hỏi hoài", "lặp lại",
    "tư vấn kiểu gì", "câu trả lời vô nghĩa",
    "không giúp được gì", "toàn hỏi lại",
    "vô ích", "không đúng", "trả lời sai",
    "tệ quá", "chán quá", "hiểu gì đâu",
    "trả lời linh tinh", "không chính xác",
    "bot vô dụng", "bot dở", "trả lời lan",
    "không rõ ràng", "khó hiểu", "không thực tế",
    "có biết gì đâu", "biết gì mà tư vấn",
    "trả lời cũ", "trả lời như nhau",
    "vòng vo", "dài dòng", "không đúng trường hợp",
    "hỏi mãi", "hỏi nhiều quá", "tại sao hỏi nhiều",
    "hỏi lắm vậy", "hỏi hoài không tư vấn",
    "sao cứ hỏi", "chỉ hỏi không trả lời",
)


CASE_INTAKE_TERMS: tuple[str, ...] = (
    # Chủ ngữ + bị/nổi
    "toi bi", "minh bi", "em bi", "ban than bi", "chau bi", "con bi",
    "minh dang bi", "toi dang bi", "em dang bi",
    "bi mun", "mun o", "noi mun", "noi o",
    "mun xuat hien", "mun moi noi",
    # Loại tổn thương — không dấu
    "co sung", "sung do", "dau den", "dau trang",
    "mun boc", "mun viem", "mun mu", "mun nan", "mun nang",
    "mun dau den", "mun dau trang", "mun li ti",
    "hat li ti", "hat nho", "mun kho", "mun an",
    "mun sam", "mun cam", "mun than",
    # Vị trí + chủ sở hữu — không dấu
    "da toi", "mat toi", "lung toi", "co toi", "nguoi toi",
    "da minh", "mat minh", "lung minh",
    "mat em", "lung em", "cam em", "tran em",
    "tren mat", "o mat", "o lung", "o co", "o vai",
    "o tran", "o cam", "o ma", "o mui", "o hang",
    # Thời gian / diễn biến — không dấu
    "hay bi", "thuong bi", "gan day", "dao nay", "tuan nay",
    "hom nay noi", "moi noi", "tu nhien noi", "tu nhien bi",
    "noi nhieu", "bi nhieu", "bi nang", "bi lau",
    "khong het", "mai khong het", "khong khoi",
    "keo dai", "lau roi", "bao lau roi",
    "ngay cang nhieu", "ngay cang nang",
    "lan ra", "lan xuong", "lan sang",
    # Diễn biến đặc biệt
    "bot o mat lai noi o", "giam o mat nhung",
    "het tren mat roi noi", "chuyen xuong",
    # Unicode
    "tôi bị", "mình bị", "em bị", "bản thân bị", "cháu bị", "con bị",
    "mình đang bị", "tôi đang bị", "em đang bị",
    "bị mụn", "mụn ở", "nổi mụn", "nổi ở",
    "mụn xuất hiện", "mụn mới nổi",
    "có sưng", "sưng đỏ", "đầu đen", "đầu trắng",
    "mụn bọc", "mụn viêm", "mụn mủ", "mụn nang",
    "mụn đầu đen", "mụn đầu trắng", "mụn li ti",
    "hạt li ti", "hạt nhỏ", "mụn khô", "mụn ẩn",
    "mụn cám", "mụn thâm",
    "da tôi", "mặt tôi", "lưng tôi", "cổ tôi", "người tôi",
    "da mình", "mặt mình", "lưng mình",
    "mặt em", "lưng em", "cằm em", "trán em",
    "trên mặt", "ở mặt", "ở lưng", "ở cổ", "ở vai",
    "ở trán", "ở cằm", "ở má", "ở mũi",
    "hay bị", "thường bị", "gần đây", "dạo này", "tuần này",
    "hôm nay nổi", "mới nổi", "tự nhiên nổi", "tự nhiên bị",
    "nổi nhiều", "bị nhiều", "bị nặng", "bị lâu",
    "không hết", "mãi không hết", "không khỏi",
    "kéo dài", "lâu rồi", "bao lâu rồi",
    "ngày càng nhiều", "ngày càng nặng",
    "lan ra", "lan xuống", "lan sang",
    "bớt ở mặt lại nổi ở", "giảm ở mặt nhưng",
    "hết trên mặt rồi nổi", "chuyển xuống",
    "mụn lan", "lan từ", "từ mặt xuống",
)
