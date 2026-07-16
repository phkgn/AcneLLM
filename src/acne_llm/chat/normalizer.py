"""Rule-based intake normalizer for one-box chat input.

The goal is not perfect medical NLP. It extracts high-signal safety and acne
context without adding another Ollama call before the actual answer.

Tách biệt 2 khái niệm:
  raw_for_llm  — chỉ NFC + bỏ control chars nguy hiểm, giữ emphasis gốc
                 ("MỤN BỌC!!!!" không bị collapse) → dùng làm description
  clean_text   — full preprocess (collapse whitespace, normalize punctuation)
                 → chỉ dùng nội bộ cho regex extraction
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal, cast

from ..schemas import AcneClinicalInput, UserContext, UserInput
from .preprocess import prepare_user_text, strip_accents


def _light_normalize(message: str) -> str:
    """Normalize tối thiểu cho LLM: NFC + bỏ control chars nguy hiểm.

    Giữ nguyên dấu câu, emoji, emphasis (!!!), whitespace tự nhiên.
    Không collapse repeated punctuation, không lowercase.
    """
    text = unicodedata.normalize("NFC", message)
    # Bỏ invisible/control chars; giữ punctuation và whitespace người dùng gõ.
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


_SKIN_TYPES: list[tuple[str, str]] = [
    ("oily", r"\b(?:"
     r"(?:da|mặt|mat|skin|vùng\s*t|vung\s*t|t-zone|t\s*zone)"
     r"(?:\s*(?:tôi|toi|mình|minh|em|cháu|chau|con))?\s*"
     # Cho phép trạng từ mức độ giữa 'da' và 'dầu': "da khá dầu", "da hơi dầu"…
     r"(?:(?:khá|kha|hơi|hoi|rất|rat|cũng|cung|khá\s*là|kha\s*la|nhìn\s*chung|nhin\s*chung)\s*)?"
     r"(?:"
     r"(?:có|co)\s*(?:nhiều\s*)?(?:dầu|dau)"
     r"|(?:dầu|dau(?!\s*(?:khi|lúc|luc|lắm|lam|quá|qua|rát|rat|nhói|nhoi)))\s*(?:nhiều|nhieu)?"
     r"|(?:nhiều|nhieu)\s*(?:dầu|dau)"
     r"|(?:nhờn|nhon)(?:\s*nhiều)?"
     r"|bóng\s*(?:dầu|nhờn|loáng)|bong\s*(?:dau|nhon|loang)"
     r"|(?:tiết|tiet)\s*(?:nhiều\s*)?(?:dầu|dau)"
     r"|(?:chảy|chay|bết|bet)\s*(?:dầu|dau)"
     r"|oily(?:\s*skin)?"
     r")"
     r"|(?:da\s*mặt|da\s*mat|da|mặt|mat|skin)"
     r"(?:(?!\b(?:ăn|an|món|mon|thức\s*ăn|thuc\s*an|sản\s*phẩm|san\s*pham|kem|dầu\s*ăn|dau\s*an)\b)[^.?!\n]){0,60}"
     r"(?:có|co)\s*(?:nhiều\s*)?(?:dầu|dau)"
     r"|(?:oily\s*skin|skin\s*(?:is\s*)?oily)"
     r"|(?:tiết|tiet)\s*(?:nhiều\s*)?(?:dầu|dau)"
     r")\b"),
    ("dry", r"\b(?:da\s*)?(?:"
     r"khô"
     r"|da\s*kho(?!\s*chiu)"
     r"|khô\s*căng|kho\s*cang"
     r"|dry\b"
     r"|bong\s*tróc|bong\s*troc"
     r"|căng\s*(?:da|mặt)|cang\s*(?:da|mat)"
     r"|thiếu\s*ẩm|thieu\s*am"
     r"|da\s*(?:bị\s*)?khô"
     r"|khô\s*ráp|kho\s*rap"
     r"|bong\s*da|bong\s*vảy"
     r"|tróc\s*da|troc\s*da"
     r"|ngứa\s*(?:do\s*)?khô"
     r")\b"),
    ("combination", r"\b(?:da\s*)?(?:"
     r"hỗn\s*hợp|hon\s*hop"
     r"|mixed\b|combination\b"
     r"|vùng\s*t\s*(?:thì\s*)?dầu"
     r"|da\s*hỗn\s*hợp"
     r"|da\s*kết\s*hợp"
     r"|vừa\s*dầu\s*vừa\s*khô"
     r"|dầu\s*ở\s*(?:trán|mũi|vùng\s*t).*khô\s*(?:ở\s*)?(?:má|hai\s*bên)"
     r"|t-zone\s*dầu"
     r")\b"),
    ("sensitive", r"\b(?:da\s*)?(?:"
     r"nhạy\s*cảm|nhay\s*cam"
     r"|dễ\s*kích\s*ứng|de\s*kich\s*ung"
     r"|sensitive\b"
     r"|dễ\s*dị\s*ứng|de\s*di\s*ung"
     r"|mỏng\s*manh|mong\s*manh"
     r"|da\s*(?:yếu|mỏng)"
     r"|hay\s*(?:đỏ\s*mặt|ửng\s*đỏ|kích\s*ứng)"
     r"|da\s*phản\s*ứng"
     r"|rosacea\b"
     r"|đỏ\s*ửng\s*(?:khi|lúc)"
     r"|reactive\s*skin"
     r")\b"),
    ("normal", r"\b(?:"
     r"da\s*thường|da\s*thuong"
     r"|normal\b"
     r"|da\s*bình\s*thường|da\s*binh\s*thuong"
     r"|da\s*bình\s*thường"
     r"|không\s*(?:quá\s*)?dầu\s*(?:không\s*(?:quá\s*)?khô)?"
     r")\b"),
]

_SEX_TERMS: list[tuple[str, str]] = [
    # male: có/không có subject pronoun, có/không có "là"
    ("male", r"(?:"
     # pronoun + là + noun
     r"\b(?:tôi|toi|mình|minh|em|cháu|chau|con|mình)\s*(?:là|la)\s*(?:nam|male|con\s*trai|boy|men|man|anh|chú|bạn\s*nam|giới\s*tính\s*nam)\b"
     # standalone: "nam giới", "giới tính nam", "con trai", gender identity phrases
     r"|\b(?:nam\s*giới|gioi\s*tinh\s*nam|giới\s*tính\s*(?:là\s*)?nam|bạn\s*trai\s*hỏi|con\s*trai\b|đàn\s*ông|dan\s*ong)\b"
     # pronoun + noun without "là" — e.g. "mình nam", "em nam"
     r"|\b(?:tôi|toi|mình|minh|em|cháu|chau)\s+(?:nam|male|boy|man)\b"
     r")"),
    # female: tương tự male
    ("female", r"(?:"
     r"\b(?:tôi|toi|mình|minh|em|cháu|chau|con|mình)\s*(?:là|la)\s*(?:nữ|nu|female|con\s*gái|girl|women|woman|chị|bạn\s*nữ|giới\s*tính\s*nữ)\b"
     r"|\b(?:nữ\s*giới|nu\s*gioi|giới\s*tính\s*(?:là\s*)?nữ|con\s*gái\b|phụ\s*nữ|phu\s*nu|bạn\s*gái\s*hỏi)\b"
     r"|\b(?:tôi|toi|mình|minh|em|cháu|chau)\s+(?:nữ|nu|female|girl|woman)\b"
     r")"),
]

_PRODUCT_TERMS = [
    # Acids / actives
    "bha", "aha", "pha", "lha",
    "salicylic acid", "acid salicylic", "salicylic",
    "azelaic acid", "acid azelaic",
    "glycolic acid", "acid glycolic", "glycolic",
    "lactic acid", "acid lactic",
    "mandelic acid",
    "niacinamide",
    "vitamin c", "vitamin b3", "vitamin b5",
    "hyaluronic acid", "acid hyaluronic",
    "vitamin a acid",
    # Retinoids
    "retinol", "retinoid", "retinal", "retinaldehyde",
    "tretinoin", "retin-a",
    "adapalene", "differin",
    "tazarotene",
    # Antibacterials / spot treatments
    "benzoyl peroxide", "bpo",
    "tea tree", "tràm trà", "tram tra",
    "sulfur", "lưu huỳnh", "luu huynh",
    "zinc", "kẽm",
    "clindamycin gel", "clindamycin",
    # Moisturizers / barriers
    "moisturizer", "kem dưỡng", "kem duong",
    "dưỡng ẩm", "duong am",
    "ceramide",
    "centella", "rau má", "rau ma",
    # Cleansers
    "sữa rửa mặt", "sua rua mat",
    "cleanser", "facial wash", "foaming",
    "gel rửa mặt", "gel rua mat",
    # Sunscreen
    "kem chống nắng", "kem chong nang",
    "sunscreen", "spf",
    # Masks / treatments
    "clay mask", "mặt nạ đất sét", "mat na dat set",
    "mặt nạ giấy", "mat na giay",
    "sheet mask",
    "peel", "chemical peel", "tẩy da chết", "tay da chet",
    # Toner / essence
    "toner", "nước hoa hồng", "nuoc hoa hong",
    "essence", "serum",
    # Spot / patch
    "acne patch", "miếng dán mụn", "mieng dan mun",
    "spot treatment",
    # Prescription-adjacent OTC
    "erylik", "epiduo", "benzac", "proactiv",
    "paula's choice", "paulas choice", "the ordinary",
    "cerave", "la roche-posay", "la roche posay",
    "bioderma", "vichy", "avene",
    "innisfree", "some by mi", "cosrx",
    "benton", "mizon", "scinic",
    # Spot / acne patches Vietnamese brand
    "acne patch", "miếng dán mụn", "mieng dan mun",
    "miếng dán", "patch mụn",
    # Common Vietnamese / local brands
    
    
    
    
    # Harmful
    "kem trộn", "kem tron",
    "kem không rõ nguồn gốc", "kem xách tay",
]

_MEDICATION_TERMS = [
    # Topical + oral retinoids — adapalene/tretinoin dùng cả topical lẫn oral context
    "isotretinoin", "accutane", "roaccutane", "oratane", "myorisan",
    "tretinoin", "retin-a",        # topical retinoid phổ biến — cần context detection
    "adapalene", "differin",       # topical retinoid OTC/Rx
    "tazarotene",                  # topical retinoid mạnh
    # Oral antibiotics
    "doxycycline", "minocycline", "tetracycline", "ada",
    "lymecycline", "sarecycline",
    "erythromycin", "azithromycin",
    "trimethoprim", "sulfamethoxazole",
    # Topical antibiotics
    "clindamycin", "clindagel",
    # Hormonal
    "spironolactone", "aldactone",
    "thuốc tránh thai", "thuoc tranh thai",
    "viên tránh thai", "vien tranh thai",
    "diane", "yasmin", "yaz", "belara", "microgynon",
    "cyproterone", "flutamide",
    # Corticosteroids
    "corticoid", "corticosteroid",
    "prednisone", "prednisolone",
    "dexamethasone", "betamethasone",
    "hydrocortisone",
    # Antihistamines / allergy
    "cetirizine", "loratadine", "fexofenadine",
    "thuốc dị ứng", "thuoc di ung",
    "kháng histamine", "khang histamine",
    # Other
    "metformin",   # dùng trong PCOS
    "zinc sulfate", "kẽm sulfate",
    "kẽm uống", "vien kem", "viên kẽm",
    "dapsone", "aczone",
    # Common Vietnamese brand names / OTC
    "triclosan", "erygel", "clindasol", "acnecide",
    "duac", "tactuo", "treclin",
    "thuốc bôi mụn", "thuoc boi mun",
    "kem trị mụn", "kem tri mun",
    "thuốc uống trị mụn", "thuoc uong tri mun",
    "kháng sinh trị mụn", "khang sinh tri mun",
]

_DISTRIBUTION_TERMS: list[tuple[str, str]] = [
    ("forehead", r"\b(?:"
     r"trán"
     r"|forehead"
     r"|vùng\s*trán|vung\s*tran"
     r"|giữa\s*trán|giua\s*tran"
     r"|trán\s*dầu"
     r"|trên\s*trán|tren\s*tran"
     r"|trán\s*đầu\s*(?:nhiều\s*)?mụn"
     r"|phần\s*trán|phan\s*tran"
     r"|mụn\s*(?:ở\s*)?trán|mun\s+o\s+tran"
     r"|mun\s+tran\b"
     r")\b"),
    ("cheeks", r"\b(?:"
     r"má"
     r"|cheeks?"
     r"|hai\s*bên\s*má|2\s*bên\s*má|hai\s*ben\s*ma|2\s*ben\s*ma"
     r"|(?:ở|o|trên|tren|vùng|vung|bên|ben|hai|gò|go)\s*(?:gò\s*)?(?:má|ma)"
     r"|(?:má|ma)\s*(?:phải|phai|trái|trai|hai\s*bên|hai\s*ben)"
     r"|mụn\s*(?:ở\s*)?má|mun\s+o\s+ma"
     r"|vùng\s*gò\s*má|vung\s*go\s*ma"
     r")\b"),
    ("chin", r"\b(?:"
     r"cằm"
     r"|chin\b"
     r"|dưới\s*cằm|duoi\s*cam"
     r"|vùng\s*cằm|vung\s*cam"
     r"|(?:ở|trên|dưới|vùng|phần|chóp|da)\s*cằm"
     r"|(?:o|tren|duoi|vung|phan|chop)\s*cam"
     r"|mụn\s*(?:ở\s*)?cằm|mun\s+o\s+cam"
     r"|phần\s*cằm|phan\s*cam"
     r"|cằm\s*dưới"
     r"|chóp\s*cằm"
     r")\b"),
    ("jawline", r"\b(?:"
     r"quai\s*hàm|quai\s*ham"
     r"|jawline"
     r"|xương\s*hàm|xuong\s*ham"
     r"|hàm\s*dưới|ham\s*duoi"
     r"|hàm"
     r"|dọc\s*theo\s*(?:quai\s*)?hàm|doc\s*theo\s*(?:quai\s*)?ham"
     r"|mụn\s*(?:dọc\s*)?(?:theo\s*)?hàm|mun\s+(?:o|dọc\s*theo|doc\s*theo|theo)\s*ham"
     r"|mun\s+ham\b"
     r"|viền\s*hàm|vien\s*ham"
     r"|hai\s*bên\s*hàm|hai\s*ben\s*ham"
     r")\b"),
    ("nose", r"\b(?:"
     r"mũi"
     r"|nose\b"
     r"|đầu\s*mũi|dau\s*mui"
     r"|cánh\s*mũi|canh\s*mui"
     r"|sống\s*mũi|song\s*mui"
     r"|vùng\s*mũi|vung\s*mui"
     r"|trên\s*mũi|tren\s*mui"
     r"|mụn\s*(?:ở\s*)?mũi|mun\s+o\s+mui"
     r"|mun\s+mui\b"
     r"|chóp\s*mũi|chop\s*mui"
     r"|(?:ở|o|da)\s*mũi|o\s*mui"
     r"|mũi\s*(?:trái|phải)|mui\s*(?:trai|phai)"
     r")\b"),
    ("around_mouth", r"\b(?:"
     r"quanh\s*miệng|quanh\s*mieng"
     r"|around\s*mouth|perioral"
     r"|mép|mep\b"
     r"|khóe\s*miệng|khoe\s*mieng"
     r"|vùng\s*miệng|vung\s*mieng"
     r"|quanh\s*(?:vùng\s*)?môi"
     r"|mụn\s*quanh\s*miệng"
     r"|xung\s*quanh\s*miệng"
     r"|dưới\s*môi|duoi\s*moi"
     r"|môi\s*(?:trên|dưới)"
     r")\b"),
    ("back", r"\b(?:"
     r"lưng|lung\b"
     r"|back\b"
     r"|sau\s*lưng|sau\s*lung"
     r"|mụn\s*(?:ở\s*)?lưng|mun\s*(?:o\s*)?lung"
     r"|giữa\s*lưng|giua\s*lung"
     r"|toàn\s*(?:bộ\s*)?lưng"
     r"|lưng\s*(?:trên|dưới|giữa)"
     r"|phần\s*lưng"
     r"|mụn\s*lưng|mun\s*lung"
     r"|da\s*lưng"
     r")\b"),
    ("chest", r"\b(?:"
     r"ngực|nguc\b"
     r"|chest\b"
     r"|trước\s*ngực|truoc\s*nguc"
     r"|vùng\s*ngực|vung\s*nguc"
     r"|ngực\s*(?:trên|dưới)"
     r"|mụn\s*(?:ở\s*)?ngực"
     r"|da\s*ngực"
     r"|phần\s*ngực"
     r"|xương\s*ức|xuong\s*uc"
     r"|mụn\s*ngực|mun\s*nguc"
     r")\b"),
    ("shoulders", r"\b(?:"
     r"bả\s*vai|ba\s*vai"
     r"|shoulder|shoulders"
     r"|vùng\s*vai|vung\s*vai"
     r"|hai\s*bên\s*vai|hai\s*ben\s*vai"
     r"|mụn\s*ở\s*vai|mun\s+o\s+vai"
     r"|mun\s+vai\b"
     r"|phần\s*vai|phan\s*vai"
     r"|bờ\s*vai|bo\s*vai"
     r"|(?:ở|o|trên|tren)\s*vai"
     r"|vai\s*(?:trái|phải|trai|phai)"
     r")\b"),
    ("neck", r"\b(?:"
     r"cổ(?!\s*(?:tay|chân|bình|chai|hủ|lọ))"
     r"|neck\b"
     r"|sau\s*gáy|sau\s*gay"
     r"|gáy"
     r"|vùng\s*gáy|vung\s*gay"
     r"|(?:ở|o)\s*gáy|o\s*gay"
     r"|mụn\s*(?:ở\s*)?gáy|mun\s+o\s+gay"
     r"|vùng\s*cổ|vung\s*co"
     r"|cổ\s*(?:trước|sau|bên)|co\s*(?:truoc|sau|ben)"
     r"|mụn\s*(?:ở\s*)?cổ|mun\s+o\s+co"
     r"|phần\s*cổ|phan\s*co"
     r"|da\s*cổ"
     r"|(?:ở|o)\s*cổ|o\s*co"
     r"|cổ\s*lan\s*xuống|co\s*lan\s*xuong"
     r"|lan\s*(?:xuống\s*)?(?:cổ|vùng\s*cổ)|lan\s*(?:xuong\s*)?(?:co|vung\s*co)"
     r")\b"),
    ("t_zone", r"\b(?:"
     r"t-zone|t\s*zone"
     r"|vùng\s*chữ\s*t|vung\s*chu\s*t"
     r"|vùng\s*t|vung\s*t\b"
     r"|chữ\s*t|chu\s*t"
     r"|t-zone(?:\s*dầu)?"
     r")\b"),
    ("other", r"\b(?:"
     r"da\s*mặt|tren\s*mat|ở\s*mặt"
     r"|vùng\s*mặt|vung\s*mat"
     r"|toàn\s*mặt|khắp\s*mặt"
     r"|face\b"
     r"|mông|(?:ở|o|vùng|vung|phần|phan)\s*mong|mun\s+o\s+mong"
     r"|đùi|(?:ở|o|vùng|vung|phần|phan)\s*dui|mun\s+o\s+dui"
     r"|da\s*đầu"
     r"|scalp\b"
     r"|(?:ở|o|vùng|vung|phần|phan|cánh|canh|cẳng|cang)\s*tay|mun\s+o\s+tay"
     r"|chân|(?:ở|o|vùng|vung|phần|phan)\s*chan|mun\s+o\s+chan"
     r"|toàn\s*thân|toan\s*than"
     r"|khắp\s*người|khap\s*nguoi"
     r"|da\s*toàn\s*thân"
     r")\b"),
]

_LESION_TERMS: list[tuple[str, str]] = [
    # Closed comedone / mụn ẩn / mụn cám
    ("closed_comedone", r"\b(?:"
     r"mụn\s*ẩn|mun\s*an|mụn\s*kín|mun\s*kin"
     r"|closed\s*comedone|microcomedone"
     r"|ẩn\s*dưới\s*da|an\s*duoi\s*da"
     r"|li\s*ti\s*dưới\s*da|liti\s*duoi\s*da"
     r"|mụn\s*(?:nhỏ\s*)?li\s*ti|mụn\s*liti|mun\s*(?:nho\s*)?li\s*ti"
     r"|mụn\s*đầu\s*trắng\s*kín"
     r"|mụn\s*cám"
     r"|mụn\s*nhân|nhân\s*mụn|nhan\s*mun"
     r"|comedone"
     r"|mụn\s*hạt\s*kê|hat\s*ke"
     r"|nổi\s*hạt\s*li\s*ti|hat\s*nho\s*li\s*ti"
     r"|mụn\s*trắng\s*nhỏ|mun\s*trang\s*nho"
     r"|b[íị]\s*(?:tắc\s*)?lỗ\s*chân\s*lông|bi\s*(?:tac\s*)?lo\s*chan\s*long"
     r"|bít\s*(?:tắc\s*)?lỗ\s*chân\s*lông|bit\s*(?:tac\s*)?lo\s*chan\s*long"
     r"|tắc\s*nghẽn\s*lỗ\s*chân\s*lông|tac\s*nghen\s*lo\s*chan\s*long"
     r")\b"),
    # Whitehead
    ("whitehead", r"\b(?:"
     r"mụn\s*đầu\s*trắng|mun\s*dau\s*trang"
     r"|whitehead"
     r"|đầu\s*trắng|dau\s*trang"
     r"|nhân\s*trắng|nhan\s*trang"
     r"|mụn\s*có\s*nhân\s*trắng"
     r"|đầu\s*trắng\s*nhỏ"
     r")\b"),
    # Blackhead
    ("blackhead", r"\b(?:"
     r"mụn\s*đầu\s*đen|mun\s*dau\s*den"
     r"|blackhead|open\s*comedone"
     r"|đầu\s*đen|dau\s*den"
     r"|nhân\s*đen|nhan\s*den"
     r"|chấm\s*đen|cham\s*den"
     r"|lỗ\s*chân\s*lông\s*(?:màu\s*)?đen|lo\s*chan\s*long\s*den"
     r"|lỗ\s*chân\s*lông\s*bị\s*tắc"
     r"|cặn\s*đen|can\s*den"
     r"|lỗ\s*lông\s*đen"
     r")\b"),
    # Papule — mụn viêm đỏ không có mủ
    ("papule", r"\b(?:"
     r"mụn\s*viêm|mun\s*viem"
     r"|papule"
     r"|sẩn\s*viêm|san\s*viem|sẩn\s*đỏ"
     r"|mụn\s*đỏ|mun\s*do"
     r"|sưng\s*đỏ|sung\s*do"
     r"|đỏ\s*(?:và\s*)?đau|do\s*dau"
     r"|mụn\s*sần|mun\s*san"
     r"|nổi\s*đỏ|noi\s*do"
     r"|mụn\s*cứng\s*đỏ"
     r"|nốt\s*đỏ|not\s*do"
     r"|mụn\s*viêm\s*đỏ"
     r"|hột\s*đỏ|hat\s*do"
     r"|viêm\s*đỏ(?!\s*đau)"
     r"|(?:có\s*)?màu\s*đỏ|mau\s*do"
     r"|ửng\s*đỏ|ung\s*do|đỏ\s*ửng|do\s*ung"
     r")\b"),
    # Pustule — có mủ
    ("pustule", r"\b(?:"
     r"mụn\s*mủ|mun\s*mu"
     r"|pustule"
     r"|có\s*(?:cả\s*)?mủ|co\s*(?:ca\s*)?mu"
     r"|đầu\s*mủ|dau\s*mu"
     r"|mủ\s*trắng|mu\s*trang"
     r"|mủ\s*vàng|mu\s*vang"
     r"|nhân\s*mủ|nhan\s*mu"
     r"|mụn\s*có\s*đầu(?:\s*mủ)?|mun\s*co\s*dau"
     r"|chảy\s*mủ|chay\s*mu"
     r"|mụn\s*có\s*nhân\s*(?:trắng|vàng|mủ)"
     r"|mụn\s*đầu\s*(?:vàng|trắng)\s*(?:có\s*)?mủ"
     r"|nặn\s*(?:ra\s*)?mủ|nan\s*(?:ra\s*)?mu"
     r"|mụn\s*chín"
     r")\b"),
    # Nodule — mụn bọc cứng sâu
    ("nodule", r"\b(?:"
     r"mụn\s*bọc|mun\s*boc"
     r"|mụn\s*cục|mun\s*cuc"
     r"|cục\s*mụn|cuc\s*mun"
     r"|(?:vài|mấy|những|nhiều)\s*cục\s*(?:mụn)?|(?:vai|may|nhieu)\s*cuc"
     r"|nổi\s*(?:vài|mấy)?\s*cục|noi\s*(?:vai|may)?\s*cuc"
     r"|mụn\s*(?:rất\s*)?to\b"
     r"|từng\s*cục|tung\s*cuc"
     r"|nổi\s*(?:từng\s*)?cục"
     r"|cục\s*cứng|cuc\s*cung"
     r"|cục\s*(?:to\s*)?dưới\s*da|cuc\s*duoi\s*da"
     r"|nodule"
     r"|nốt\s*sâu|not\s*sau"
     r"|mụn\s*sâu\s*(?:dưới\s*da)?|mun\s*sau"
     r"|u\s*cứng\s*dưới\s*da"
     r"|mụn\s*như\s*cục\s*u"
     r"|mụn\s*cứng\s*(?:sâu|dưới\s*da)"
     r"|sưng\s*cục\s*cứng"
     r"|đau\s*(?:và\s*)?cứng\s*dưới\s*da"
     r")\b"),
    # Cyst — nang
    ("cyst", r"\b(?:"
     r"mụn\s*nang|mun\s*nang"
     r"|cystic(?:\s*acne)?"
     r"|cyst"
     r"|u\s*nang"
     r"|nang\s*mụn|nang\s*mun"
     r"|mụn\s*nang\s*mủ"
     r"|nodulocystic"
     r"|mụn\s*bọc\s*nang"
     r"|nang\s*(?:to|lớn|cứng|mủ)?\s*(?:ở\s*)?dưới\s*da|nang\s*(?:to|lon|cung|mu)?\s*duoi\s*da"
     r"|có\s*nang\s*(?:to|lớn|cứng)|co\s*nang"
     r"|mụn\s*nước(?:\s*dưới\s*da)?"
     r"|bọc\s*mủ\s*lớn"
     r")\b"),
    # Scar — sẹo rỗ / lõm / phì đại
    ("scar", r"\b(?:"
     r"sẹo\s*mụn|seo\s*mun"
     r"|sẹo\s*rỗ|seo\s*ro"
     r"|sẹo\s*lõm|seo\s*lom"
     r"|sẹo\s*lồi|seo\s*loi"
     r"|sẹo|scar"
     r"|atrophic(?:\s*scar)?"
     r"|hypertrophic(?:\s*scar)?"
     r"|keloid"
     r"|lỗ\s*rỗ|lo\s*ro"
     r"|da\s*rỗ|da\s*bị\s*rỗ"
     r"|lỗ\s*chân\s*lông\s*to(?:\s*sau\s*mụn)?"
     r"|vết\s*sẹo|vet\s*seo"
     r"|để\s*lại\s*(?:vết\s*)?sẹo|de\s*lai\s*seo"
     r"|bị\s*rỗ(?:\s*da)?"
     r"|lõm\s*(?:da|mặt)|lom\s*mat"
     r"|mặt\s*(?:bị\s*)?rỗ"
     r")\b"),
    # PIH — thâm sau viêm
    ("post_inflammatory_hyperpigmentation", r"\b(?:"
     r"thâm\s*mụn|tham\s*mun"
     r"|vết\s*thâm|vet\s*tham"
     r"|thâm(?:\s*da)?|tham(?:\s*da)?"
     r"|tăng\s*sắc\s*tố|tang\s*sac\s*to"
     r"|pih"
     r"|hyperpigmentation"
     r"|vết\s*(?:màu\s*)?nâu|vet\s*nau"
     r"|vết\s*đen\s*sau\s*mụn|vet\s*den"
     r"|đốm\s*nâu|dom\s*nau"
     r"|mảng\s*thâm|mang\s*tham"
     r"|da\s*(?:bị\s*)?thâm"
     r"|thâm\s*(?:sau\s*)?(?:khi\s*)?(?:mụn|nặn)"
     r"|vết\s*thâm\s*(?:sau\s*mụn|đen)"
     r"|ố\s*nâu|o\s*nau"
     r"|đốm\s*đen|dom\s*den"
     r")\b"),
    # Generic — fallback (đặt cuối cùng, chỉ match khi không match được type cụ thể nào)
    ("other", r"\b(?:"
     r"mụn\s*trứng\s*cá|mun\s*trung\s*ca"
     r"|mụn\s*nhỏ|mun\s*nho"
     r"|nổi\s*mụn|noi\s*mun"
     r"|bị\s*mụn|bi\s*mun"
     r"|mụn\s*ở|mun\s*o"
     r"|da\s*nổi\s*(?:mụn)?"
     r"|mụn\s*nhiều|mun\s*nhieu"
     r"|mụn\s*(?:ở\s*)?(?:khắp|trên|dưới|xung\s*quanh)"
     r"|nổi\s*(?:hạt|nốt|mẩn)(?:\s*đỏ)?"
     r"|mẩn\s*đỏ|man\s*do"
     r"|mụn\s*trứng|mun\s*trung"
     r")\b"),
]

_HORMONAL_TERMS: list[tuple[str, str]] = [
    ("menstrual_cycle", r"\b(?:"
     r"trước\s*kỳ\s*kinh|truoc\s*ky\s*kinh"
     r"|tới\s*kỳ|toi\s*ky"
     r"|chu\s*kỳ\s*kinh|chu\s*ky\s*kinh"
     r"|kinh\s*nguyệt|kinh\s*nguyet"
     r"|menstrual|period\b"
     r"|hành\s*kinh|hanh\s*kinh"
     r"|đèn\s*đỏ|den\s*do"
     r"|ngày\s*(?:đèn|kinh)|ngay\s*(?:den|kinh)"
     r"|mụn\s*theo\s*(?:chu\s*kỳ|kỳ\s*kinh)"
     r"|mụn\s*(?:lên|nổi)\s*(?:khi|trước)\s*(?:có\s*)?kinh"
     r"|sắp\s*(?:có|tới)\s*kinh"
     r"|hormonal\s*acne"
     r"|mụn\s*nội\s*tiết\s*(?:nữ)?"
     r")\b"),
    ("pcos", r"\b(?:"
     r"pcos"
     r"|buồng\s*trứng\s*đa\s*nang|buong\s*trung\s*da\s*nang"
     r"|đa\s*nang\s*buồng\s*trứng"
     r"|polycystic(?:\s*ovary)?"
     r"|hội\s*chứng\s*buồng\s*trứng"
     r")\b"),
    ("stress", r"\b(?:"
     r"stress\b"
     r"|căng\s*thẳng|cang\s*thang"
     r"|thức\s*khuya|thuc\s*khuya"
     r"|ngủ\s*(?:ít|muộn|kém)|ngu\s*it"
     r"|mất\s*ngủ|mat\s*ngu"
     r"|áp\s*lực|ap\s*luc"
     r"|lo\s*lắng|lo\s*lang"
     r"|căng\s*não|cang\s*nao"
     r"|ôn\s*thi|on\s*thi"
     r"|thi\s*cử|thi\s*cu"
     r"|làm\s*việc\s*(?:nhiều|quá\s*sức)"
     r"|kiệt\s*sức|kiet\s*suc"
     r"|burn\s*out|burnout"
     r"|mụn\s*do\s*(?:stress|căng\s*thẳng)"
     r")\b"),
    ("diet", r"\b(?:"
     r"ăn\s*(?:nhiều\s*)?đường|an\s*(?:nhieu\s*)?duong"
     r"|ăn\s*ngọt|an\s*ngot"
     r"|sữa\s*(?:bò|tươi|động\s*vật)|sua\s*(?:bo|tuoi)"
     r"|ăn\s*sữa\b"
     r"|dairy\b"
     r"|ăn\s*(?:nhiều\s*)?tinh\s*bột|an\s*(?:nhieu\s*)?tinh\s*bot"
     r"|high\s*glycemic"
     r"|đồ\s*chiên(?:\s*rán)?|do\s*chien"
     r"|đồ\s*ngọt|do\s*ngot"
     r"|thức\s*ăn\s*nhanh|thuc\s*an\s*nhanh|fast\s*food"
     r"|đồ\s*ăn\s*dầu\s*mỡ"
     r"|ăn\s*cay"
     r"|sô-?cô-?la|chocolate"
     r"|ăn\s*uống\s*(?:không\s*lành\s*mạnh|thiếu\s*khoa\s*học)"
     r"|chế\s*độ\s*ăn"
     r")\b"),
    ("pregnancy", r"\b(?:"
     r"mang\s*thai|co\s*thai|có\s*thai"
     r"|đang\s*bầu|dang\s*bau"
     r"|thai\s*kỳ|thai\s*ky"
     r"|pregnant\b"
     r"|bầu\s*bì|bau\s*bi"
     r"|thai\s*phụ"
     r"|đang\s*(?:mang|có)\s*em\s*bé"
     r"|có\s*em\s*bé\s*rồi"
     r")\b"),
    ("postpartum", r"\b(?:"
     r"sau\s*sinh|sau\s*khi\s*sinh"
     r"|mới\s*sinh\s*(?:con|xong)|moi\s*sinh"
     r"|postpartum\b"
     r"|hậu\s*sản|hau\s*san"
     r"|cho\s*con\s*bú|cho\s*con\s*bu"
     r"|đang\s*(?:cho\s*)?nuôi\s*con\s*bằng\s*sữa\s*mẹ"
     r"|nuôi\s*con\s*bú"
     r"|sau\s*(?:khi\s*)?sinh\s*\d+\s*(?:tháng|tuần)"
     r")\b"),
    ("puberty", r"\b(?:"
     r"dậy\s*thì|day\s*thi"
     r"|tuổi\s*(?:dậy|teen|vị\s*thành\s*niên)|tuoi\s*day"
     r"|puberty\b"
     r"|tuổi\s*teen|teen\b"
     r"|cấp\s*[23]|lớp\s*(?:[6-9]|1[012])"
     r"|học\s*sinh|hoc\s*sinh"
     r"|adolescent"
     r")\b"),
]

_ALLERGY_REACTION_VERBS = (
    r"(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp|khong\s*hop"
    r"|không\s*dùng\s*được|khong\s*dung\s*duoc|bị\s*ứng|bi\s*ung"
    r"|không\s*chịu\s*được|khong\s*chiu\s*duoc)"
)
# Pattern xuôi: "dị ứng với X" | ngược: "X làm/gây kích ứng / bị kích ứng khi dùng X"
# Dùng window .{0,30} để cho phép từ trung gian ("làm da MÌnh bị kích ứng",
# "gây kích ứng cho da mình", v.v.) — không dùng \s* vì quá strict.
# F9.1: thêm verb anchor "(làm|gây|dẫn đến|khiến) da" để bắt "BHA làm da mình rát".
_ALLERGY_REACTION_AFTER = (
    r"(?:.{0,30}(?:kích\s*ứng|dị\s*ứng|nổi\s*đỏ|ngứa\s*rát|bỏng\s*rát|phản\s*ứng)"
    r"|.{0,20}không\s*hợp\s*(?:với\s*)?da"
    r"|.{0,15}gây\s*(?:mẩn|nổi\s*đỏ|đỏ\s*rát)"
    r"|.{0,15}(?:làm|gây|dẫn\s+đến|khiến)\s+da\s+\S+\s*(?:rát|đỏ|ngứa|kích\s*ứng|bỏng|châm\s*chích|khô))"
)

def _allergy_pattern(substance: str) -> str:
    """Tạo pattern match cả chiều xuôi lẫn ngược cho một chất."""
    fwd = rf"\b{_ALLERGY_REACTION_VERBS}\s+(?:với\s*|with\s*)?{substance}\b"
    rev = rf"\b{substance}\b{_ALLERGY_REACTION_AFTER}"
    return f"(?:{fwd}|{rev})"

_ALLERGY_TERMS: list[tuple[str, str]] = [
    # Retinoids — forward + reverse
    ("retinol",        _allergy_pattern(r"retinol")),
    ("retinoid",       _allergy_pattern(r"retinoid")),
    ("tretinoin",      _allergy_pattern(r"tretinoin")),
    ("adapalene",      _allergy_pattern(r"adapalene")),
    # Acids
    ("salicylic_acid", _allergy_pattern(r"(?:salicylic(?:\s*acid)?|acid\s*salicylic)")),
    ("benzoyl_peroxide", _allergy_pattern(r"(?:benzoyl(?:\s*peroxide)?|bpo)")),
    ("niacinamide",    _allergy_pattern(r"niacinamide")),
    # F9: tách BHA/AHA thành alias riêng để extract chính xác hơn.
    ("bha_irritation", _allergy_pattern(r"bha")),
    ("aha_irritation", _allergy_pattern(r"aha")),
    ("aha",            _allergy_pattern(r"(?:glycolic\s*acid|lactic\s*acid|acid\s*glycolic)")),
    ("tea_tree",       _allergy_pattern(r"(?:tea\s*tree|tram\s*tra|trang\s*tra)")),
    # Antibiotics
    ("clindamycin",    _allergy_pattern(r"clindamycin")),
    ("doxycycline",    _allergy_pattern(r"doxycycline")),
    ("penicillin",     _allergy_pattern(r"(?:penicillin|amoxicillin)")),
    ("erythromycin",   _allergy_pattern(r"erythromycin")),
    # Fragrance / preservatives
    ("fragrance",      _allergy_pattern(r"(?:huong\s*lieu|fragrance|mui\s*thom|nuoc\s*hoa)")),
    ("preservative",   _allergy_pattern(r"(?:chat\s*bao\s*quan|preservative|paraben)")),
    # Sunscreen
    ("sunscreen_chemical", _allergy_pattern(r"(?:chemical\s*sunscreen|oxybenzone|avobenzone|kem\s*chong\s*nang\s*hoa\s*hoc)")),
    # Natural
    ("aloe_vera",      _allergy_pattern(r"(?:nha\s*dam|aloe\s*vera|lo\s*hoi)")),
    ("centella",       _allergy_pattern(r"(?:rau\s*ma|centella|cica)")),
    # Generic / catch-all — chỉ dùng khi không match được substance cụ thể
    ("unknown",        r"(?:"
     r"\b(?:dị\s*ứng|di\s*ung)\b"
     r"|bị\s*dị\s*ứng"
     r"|hay\s*dị\s*ứng"
     r"|da\s*dị\s*ứng"
     r"|bị\s*ứng\s*(?:da|mặt|mình|khi|lúc|sau)"
     r"|da\s*bị\s*ứng"
     r"|mặt\s*bị\s*ứng"
     r"|(?:da|mặt|mình)\s*bị\s*ứng"
     r"|ứng\s*(?:đỏ|ngứa|rát|mặt|da)"
     r"|ứng\s*khi\s*(?:bôi|dùng|thoa|xài)"
     r"|không\s*hợp\s*(?:da|với\s*da|mặt)"
     r"|khong\s*hop\s*(?:da|mat)"
     r"|da\s*không\s*hợp"
     r"|bôi\s*vào\s*(?:bị\s*)?(?:ứng|dị\s*ứng|nổi\s*đỏ|ngứa|rát)"
     r"|dùng\s*(?:vào\s*)?(?:bị\s*)?(?:ứng|dị\s*ứng|nổi\s*đỏ|kích\s*ứng)"
     r"|skin\s*allergy|allergic\s*reaction"
     r")"),
]

_TREATMENT_GOAL_TERMS: list[tuple[str, str]] = [
    ("clear_acne", r"\b(?:"
     r"trị\s*mụn|tri\s*mun"
     r"|hết\s*mụn|het\s*mun"
     r"|trị\s*(?:dứt|tận\s*gốc)"
     r"|không\s*còn\s*mụn|khong\s*con\s*mun"
     r"|giảm\s*mụn|giam\s*mun"
     r"|bớt\s*mụn|bot\s*mun"
     r"|clear\s*(?:skin|acne)"
     r"|đẩy\s*(?:hết\s*)?mụn"
     r"|sạch\s*mụn|sach\s*mun"
     r"|làm\s*(?:sạch|giảm)\s*mụn"
     # Thêm patterns mới
     r"|làm\s*sao\s*(?:cho\s*)?hết\s*mụn"
     r"|làm\s*sao\s*(?:cho\s*)?bớt\s*mụn"
     r"|cho\s*(?:hết|bớt|giảm)\s*mụn"
     r"|muốn\s*(?:hết|bớt|trị|giảm)\s*mụn"
     r"|mong\s*muốn\s*(?:hết|trị)\s*mụn"
     r"|cần\s*(?:trị|hết|bớt)\s*mụn"
     r"|da\s*(?:hết|bớt)\s*mụn"
     r"|hết\s*(?:được\s*)?mụn"
     r"|khỏi\s*mụn|khoi\s*mun"
     r"|chữa\s*mụn|chua\s*mun"
     r"|hết\s*mụn\s*(?:đi|thôi)"
     r"|trị\s*hết\s*mụn"
     r")\b"),
    ("treat_scar", r"\b(?:"
     r"trị\s*sẹo|tri\s*seo"
     r"|xóa\s*sẹo|xoa\s*seo"
     r"|lấp\s*(?:đầy\s*)?sẹo|lap\s*seo"
     r"|mờ\s*sẹo|mo\s*seo"
     r"|sẹo\s*(?:lõm|rỗ)|seo\s*(?:lom|ro)"
     r"|phục\s*hồi\s*da|phuc\s*hoi\s*da"
     r"|scar\s*treatment"
     r"|điều\s*trị\s*sẹo"
     r"|lành\s*(?:vết\s*)?sẹo"
     r"|làm\s*đầy\s*sẹo"
     r")\b"),
    ("fade_hyperpigmentation", r"\b(?:"
     r"xóa\s*thâm|xoa\s*tham"
     r"|mờ\s*thâm|mo\s*tham"
     r"|trị\s*thâm|tri\s*tham"
     r"|làm\s*sáng\s*da|lam\s*sang\s*da"
     r"|thâm\s*sau\s*mụn|tham\s*sau\s*mun"
     r"|brightening\b"
     r"|fade\s*dark\s*spot"
     r"|even\s*skin\s*tone"
     r"|tone\s*da\s*đều"
     r"|bớt\s*thâm|bot\s*tham"
     r"|giảm\s*(?:vết\s*)?thâm"
     r"|đốm\s*nâu\s*(?:sau\s*mụn)?"
     r")\b"),
    ("reduce_oiliness", r"\b(?:"
     r"giảm\s*dầu|giam\s*dau"
     r"|bớt\s*(?:dầu|nhờn)|bot\s*(?:dau|nhon)"
     r"|thu\s*nhỏ\s*lỗ\s*chân\s*lông|thu\s*nho\s*lo\s*chan\s*long"
     r"|lỗ\s*chân\s*lông\s*(?:to|nhìn\s*thấy\s*rõ)"
     r"|kiểm\s*soát\s*dầu|kiem\s*soat\s*dau"
     r"|pore\s*(?:minimizer|tightening)?"
     r"|sebum\s*control"
     r"|mặt\s*bớt\s*nhờn"
     r"|kiểm\s*soát\s*nhờn"
     r")\b"),
    ("hydration", r"\b(?:"
     r"dưỡng\s*ẩm|duong\s*am"
     r"|cấp\s*ẩm|cap\s*am"
     r"|da\s*(?:bị\s*)?khô"
     r"|khô\s*da|kho\s*da"
     r"|hàng\s*rào\s*(?:bảo\s*vệ\s*)?da|hang\s*rao\s*da"
     r"|moisture\s*barrier"
     r"|hydration\b"
     r"|giữ\s*ẩm|giu\s*am"
     r"|da\s*thiếu\s*nước|da\s*thieu\s*nuoc"
     r"|phục\s*hồi\s*(?:hàng\s*rào\s*)?da"
     # Thêm patterns mới
     r"|cấp\s*nước|cap\s*nuoc"
     r"|ngậm\s*nước|ngam\s*nuoc"
     r"|cấp\s*độ\s*ẩm|cap\s*do\s*am"
     r"|thêm\s*độ\s*ẩm"
     r"|bổ\s*sung\s*ẩm"
     r"|làm\s*đẫm\s*da"
     r")\b"),
    ("reduce_inflammation", r"\b(?:"
     r"giảm\s*viêm|giam\s*viem"
     r"|bớt\s*(?:đỏ|sưng)|bot\s*(?:do|sung)"
     r"|giảm\s*(?:đỏ|sưng)|giam\s*(?:do|sung)"
     r"|calming\b|soothing\b"
     r"|anti.?inflammatory"
     r"|làm\s*dịu\s*da"
     r"|da\s*bớt\s*(?:kích\s*ứng|đỏ|viêm)"
     r"|giảm\s*kích\s*ứng|giam\s*kich\s*ung"
     r")\b"),
    ("prevent_acne", r"\b(?:"
     r"ngăn\s*(?:ngừa\s*)?mụn|ngan\s*(?:gua\s*)?mun"
     r"|phòng\s*(?:ngừa\s*)?mụn|phong\s*(?:gua\s*)?mun"
     r"|không\s*(?:bị\s*)?tái\s*phát|khong\s*tai\s*phat"
     r"|không\s*bị\s*(?:mụn\s*)?lại|khong\s*bi\s*lai"
     r"|prevent\s*acne"
     r"|maintenance\b"
     r"|duy\s*trì\s*(?:da\s*)?sạch"
     r"|mụn\s*không\s*tái\s*phát"
     r"|ngăn\s*mụn\s*(?:mới\s*)?nổi"
     # Thêm patterns mới
     r"|không\s*bị\s*mụn\s*(?:nữa|lại)"
     r"|ngừa\s*mụn|ngua\s*mun"
     r"|tránh\s*mụn|train\s*mun"
     r"|hạn\s*chế\s*mụn|han\s*che\s*mun"
     r"|giữ\s*(?:da\s*)?sạch"
     r"|bảo\s*vệ\s*da"
     r"|ngăn\s*(?:mụn\s*)?phát\s*sinh"
     r")\b"),
    ("build_routine", r"\b(?:"
     r"(?:xây\s*dựng|lập|tạo)\s*routine"
     r"|skincare\s*routine"
     r"|quy\s*trình\s*(?:dưỡng|chăm\s*sóc)\s*da"
     r"|chăm\s*sóc\s*da|cham\s*soc\s*da"
     r"|step\s*(?:chăm\s*sóc|dưỡng)"
     r"|cách\s*chăm\s*sóc\s*da"
     r"|thói\s*quen\s*dưỡng\s*da"
     r"|bắt\s*đầu\s*routine"
     r")\b"),
    ("product_recommendation", r"\b(?:"
     r"dùng\s*(?:sản\s*phẩm\s*)?gì|dung\s*(?:san\s*pham\s*)?gi"
     r"|nên\s*dùng(?:\s*gì)?|nen\s*dung"
     r"|sản\s*phẩm\s*nào|san\s*pham\s*nao"
     r"|recommend\b"
     r"|gợi\s*ý\s*(?:sản\s*phẩm|kem|serum)"
     r"|mua\s*(?:gì|loại\s*nào)|mua\s*gi"
     r"|loại\s*nào\s*tốt"
     r"|sản\s*phẩm\s*(?:tốt|phù\s*hợp)"
     r"|thành\s*phần\s*nào\s*(?:dùng|tốt)"
     r")\b"),
    ("see_doctor", r"\b(?:"
     r"(?:cần|nên|muốn)\s*(?:đi\s*)?khám|can\s*kham"
     r"|đi\s*khám|di\s*kham"
     r"|bác\s*sĩ\s*(?:da\s*liễu)?|bac\s*si"
     r"|dermatologist\b"
     r"|gặp\s*(?:bác\s*sĩ|bs)|gap\s*(?:bac\s*si|bs)"
     r"|cần\s*(?:kê|kê\s*đơn)\s*thuốc"
     r"|phòng\s*khám\s*da\s*liễu"
     r"|đi\s*bệnh\s*viện\s*(?:da\s*liễu)?"
     r"|khám\s*da\s*liễu"
     r")\b"),
]

_RED_FLAG_TERMS: list[tuple[str, str]] = [
    ("widespread", r"\b(?:"
     r"khắp|khap\b"
     r"|lan\s*rộng|lan\s*rong"
     r"|toàn\s*(?:bộ|mặt|lưng|thân)|toan\s*(?:bo|mat)"
     r"|rất\s*nhiều|rat\s*nhieu"
     r"|nổi\s*(?:khắp|đầy)|noi\s*(?:khap|day)"
     r"|bùng\s*phát|bung\s*phat"
     r"|outbreak\b"
     r"|dày\s*đặc|day\s*dac"
     r"|chi\s*chít|chi\s*chit"
     r"|mọc\s*(?:đầy|dày|khắp)|moc\s*(?:day|khap)"
     r"|ken\s*(?:dày|đặc)|ken\s*day"
     r"|đầy\s*(?:mặt|lưng|người)"
     r"|lan\s*(?:ra|xuống|sang|rộng)"
     r"|mụn\s*lan"
     r")\b"),
    ("painful_lesions", r"\b(?:"
     r"đau\s*(?:nhiều|lắm|quá|rất)|dau\s*(?:nhieu|lam|qua|rat)"
     r"|rất\s*đau|rat\s*dau"
     r"|đau\s*rát|dau\s*rat"
     r"|sưng\s*đau|sung\s*dau"
     r"|đau\s*nhói|dau\s*nhoi"
     r"|đau\s*khi\s*(?:chạm|sờ|ấn|đụng|cử\s*động|di\s*chuyển|mặc\s*áo|nằm)"
     r"|ấn\s*(?:vào\s*)?đau|an\s*(?:vao\s*)?dau"
     r"|chạm\s*(?:vào\s*)?(?:là\s*)?đau"
     r"|sờ\s*(?:vào\s*)?(?:là\s*)?đau"
     r"|đụng\s*(?:vào\s*)?đau"
     r"|đau\s*(?:khi\s*)?(?:sờ|chạm|ấn)"
     r"|nhức\s*(?:nhối|đầu\s*mụn)"
     r"|đau\s*âm\s*ỉ"
     # Chỉ khớp bản CÓ DẤU: twin không dấu 'kha/hoi/cung dau' trùng
     # 'khá/hơi/cũng dầu' (da dầu) → false painful. (accent-collision fix)
     r"|(?:khá|hơi|cũng|hơ)\s*đau"
     r"|sờ\s*(?:vào\s*)?(?:khá|hơi|thấy)?\s*đau|so\s*(?:vao\s*)?(?:kha|hoi|thay)?\s*dau"
     r"|cộm\s*(?:cộm|đau)|com\s*(?:com|dau)"
     r")\b"),
    ("purulent_lesions", r"\b(?:"
     r"có\s*(?:cả\s*)?mủ|co\s*(?:ca\s*)?mu"
     r"|chảy\s*mủ|chay\s*mu"
     r"|mủ\s*(?:vàng|trắng|xanh)|mu\s*(?:vang|trang|xanh)"
     r"|chảy\s*(?:dịch|nước)|chay\s*(?:dich|nuoc)"
     r"|rỉ\s*dịch|ri\s*dich"
     r"|có\s*(?:cả\s*)?máu|co\s*(?:ca\s*)?mau(?!\s*(?:đen|den|trắng|trang|đỏ|do|nâu|nau|vàng|vang|xanh))"
     r"|chảy\s*máu|chay\s*mau"
     r"|ra\s*máu|ra\s*mau"
     # Dạng đảo: "máu cũng ra nhiều", "máu ra nhiều", "máu chảy" — máu đứng trước động từ
     r"|máu\s*(?:cũng\s*|còn\s*)?(?:ra|chảy|rỉ)|mau\s*(?:cung\s*|con\s*)?(?:ra|chay|ri)"
     r"|bleeding\b"
     r"|nặn\s*ra\s*(?:mủ|máu|dịch)"
     r"|dịch\s*(?:vàng|mủ|chảy)"
     r")\b"),
    ("scarring_risk", r"\b(?:"
     r"sẹo\s*rỗ|seo\s*ro"
     r"|sẹo\s*lõm|seo\s*lom"
     r"|sẹo\s*lồi|seo\s*loi"
     r"|để\s*lại\s*(?:vết\s*)?sẹo|de\s*lai\s*seo"
     r"|sẹo|scar\b"
     r"|da\s*rỗ|lỗ\s*rỗ|lo\s*ro"
     r"|lõm\s*mặt|lom\s*mat"
     r"|bị\s*rỗ|bi\s*ro"
     r"|lo\s*sợ\s*(?:để\s*lại\s*)?sẹo"
     r")\b"),
    ("infection_signs", r"\b(?:"
     r"sốt|sot\b|fever\b"
     r"|nhiễm\s*trùng|nhiem\s*trung"
     r"|đỏ\s*lan\s*(?:ra|rộng)|do\s*lan"
     r"|sưng\s*nóng|sung\s*nong"
     r"|nóng\s*(?:ran|rát)|nong\s*(?:ran|rat)"
     r"|sưng\s*to\s*(?:bất\s*thường|nhanh)"
     r"|bị\s*sốt|bi\s*sot"
     r"|nóng\s*sốt|nong\s*sot"
     r"|sốt\s*(?:sau\s*(?:khi\s*)?nặn|cao)"
     r"|hạch\s*(?:sưng|nổi)"
     r"|viêm\s*mô\s*tế\s*bào|cellulitis"
     r"|đỏ\s*bừng\s*(?:lan\s*ra|rộng)"
     r")\b"),
    ("skin_irritation", r"(?:"
     r"\bbị\s*(?:kích\s*ứng|kich\s*ung)\b"     # bị kích ứng (user's skin)
     r"|\bda\s*(?:bị\s*)?(?:kích\s*ứng|kich\s*ung)\b"
     r"|\bbong\s*tróc\b|\bbong\s*troc\b"
     r"|\brát(?:\s*bỏng)?\b|\b(?:da|va)\s+rat\b"
     r"|\bnóng\s*rát\b|\bnong\s*rat\b"
     r"|\bchâm\s*chích\b|\bcham\s*chich\b"
     r"|\bngứa\s*(?:rát|nhiều)\b|\bngua\s*(?:rat|nhieu)\b"
     r"|\bbỏng\s*rát\b|\bbong\s*rat\b"
     r"|\bda\s*(?:bị\s*)?bỏng\b"
     r"|\bđỏ\s*(?:bừng|rộp)\b|\bdo\s*(?:bung|rop)\b"
     r"|\bphản\s*ứng\s*(?:da|mặt)\b"
     r"|\bdị\s*ứng\s*sau\s*(?:dùng|bôi|thoa)\b"
     r"|\bpeeling\s*(?:quá|mạnh)\b"
     r")"),
    ("treatment_failure", r"\b(?:"
     r"không\s*đỡ|khong\s*do\b"
     r"|không\s*cải\s*thiện|khong\s*cai\s*thien"
     r"|(?:dùng|bôi|uống).{0,30}(?:không\s*(?:đỡ|khỏi|hết))"
     r"|thất\s*bại\s*điều\s*trị"
     r"|mãi\s*không\s*khỏi|mai\s*khong\s*khoi"
     r"|không\s*(?:khỏi|hết)|khong\s*(?:khoi|het)"
     r"|kháng\s*(?:trị|thuốc)"
     r"|điều\s*trị\s*(?:nhiều\s*lần|lâu|mãi)\s*(?:không\s*(?:đỡ|khỏi))?"
     r"|tái\s*đi\s*tái\s*lại|tai\s*di\s*tai\s*lai"
     r")\b"),
    ("no_prior_treatment", r"\b(?:"
     r"chưa\s*(?:dùng|xài|điều\s*trị|bôi|thử|dùng\s*gì)|chua\s*(?:dung|xai)"
     r"|lần\s*đầu\s*(?:bị|dùng)"
     r"|không\s*dùng\s*(?:gì|thuốc|kem|kháng\s*sinh)"
     r"|khong\s*dung\s*(?:gi|thuoc|kem|khang\s*sinh)"
     r"|chưa\s*từng\s*(?:điều\s*trị|dùng\s*thuốc)"
     r")\b"),
    ("chronic", r"\b(?:"
     r"lâu\s*rồi|lau\s*roi"
     r"|mãi\s*không|mai\s*khong"
     r"|tái\s*(?:đi\s*tái\s*lại|phát\s*nhiều\s*lần)"
     r"|tai\s*(?:di\s*tai\s*lai|phat)"
     r"|hay\s*bị\s*lại|hay\s*bi\s*lai"
     r"|năm\s*nào\s*cũng\s*bị"
     r"|\d+\s*(?:năm|nam|tháng|thang)\s*(?:rồi|roi|nay)"
     r"|mụn\s*mãn\s*tính"
     r"|bị\s*từ\s*(?:nhỏ|bé|lâu)"
     r")\b"),
    ("self_treatment_risk", r"\b(?:"
     r"(?:tự\s*)?nặn\s*mụn|(?:tu\s*)?nan\s*mun"
     r"|tự\s*nặn|tu\s*nan"
     r"|cậy\s*mụn|cay\s*mun"
     r"|nặn\s*vài\s*cục|nan\s*vai\s*cuc"
     r"|nặn\s*(?:ra\s*)?(?:máu|mủ)"
     r"|sau\s*khi\s*nặn|sau\s*khi\s*nan"
     r"|bôi\s*kem\s*trộn|boi\s*kem\s*tron"
     r"|tự\s*mua\s*thuốc|tu\s*mua\s*thuoc"
     r"|chích\s*mụn|chich\s*mun"
     r"|tự\s*chích|tu\s*chich"
     r"|lăn\s*kim\s*(?:tại\s*nhà|nhà)?|lan\s*kim"
     r"|đắp\s*(?:đất|sét|thuốc\s*tự\s*pha)"
     r"|tự\s*điều\s*trị\s*(?:tại\s*nhà)?"
     r")\b"),
]


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_floats(items: list[float]) -> list[float]:
    seen: set[float] = set()
    out: list[float] = []
    for item in items:
        value = round(float(item), 8)
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _texts_for_extraction(clean_text: str, clean_text_no_accent: str | None = None) -> list[str]:
    texts = [clean_text]
    no_accent = clean_text_no_accent if clean_text_no_accent is not None else strip_accents(clean_text)
    if no_accent and no_accent != clean_text:
        texts.append(no_accent)
    return texts


def _merge_extracted(texts: list[str], extractor) -> list[str]:
    merged: list[str] = []
    for text in texts:
        merged.extend([str(x) for x in extractor(text)])
    return _dedupe(merged)


def _dedupe_accent_insensitive(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = strip_accents(str(item)).lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _first_extracted(texts: list[str], extractor):
    for text in texts:
        value = extractor(text)
        if value is not None:
            return value
    return None


_AcneCount = Literal["few", "moderate_count", "many"]


def _extract_acne_count(text: str) -> _AcneCount | None:
    """Ước lượng số lượng mụn: few / moderate_count / many.

    Dùng để calibrate inflammation inference — "1-2 nốt đỏ" là few dù có papule.
    Không expose ra schema ngoài; chỉ dùng nội bộ trong _extract_inflammation.
    """
    # Many: từ ngữ chỉ số lượng lớn
    _many = (
        r"\b(?:"
        r"rất\s*nhiều|rat\s*nhieu"
        r"|đầy\s*(?:mặt|lưng|người|da)"
        r"|chi\s*chít|chi\s*chit"
        r"|dày\s*đặc|day\s*dac"
        r"|khắp\s*(?:mặt|người|nơi|da)|khap"
        r"|nổi\s*(?:nhiều|đầy|khắp)|noi\s*nhieu"
        r"|mụn\s*(?:nhiều\s*(?:lắm|quá)|lên\s*nhiều|mọc\s*nhiều)"
        r"|bùng\s*phát|bung\s*phat"
        r"|hàng\s*chục|hang\s*chuc"
        r"|[2-9]\d+\s*(?:nốt|cái|mụn)"          # >= 20
        r")\b"
    )
    if _has(_many, text):
        return "many"

    # Few: từ ngữ rõ ràng chỉ 1-3 mụn
    _few = (
        r"\b(?:"
        r"(?:chỉ\s*)?(?:1|một|2|hai|3|ba)\s*(?:nốt|cái|mụn|hạt)(?:\s*nhỏ)?"
        r"|vài\s*(?:nốt|cái|mụn)\s*(?:nhỏ|thôi)?"
        r"|1-?2\s*(?:nốt|cái|mụn)"
        r"|2-?3\s*(?:nốt|cái|mụn)"
        r"|chỉ\s*(?:vài|một\s*ít)\s*(?:mụn|nốt)"
        r"|ít\s*(?:mụn|nốt)\s*(?:thôi|thay)?"
        r"|mụn\s*ít\s*(?:thôi|lắm)?"
        r"|không\s*nhiều"
        r")\b"
    )
    if _has(_few, text):
        return "few"

    return None


def _extract_age(text: str) -> int | None:
    patterns = [
        # Pattern 1: "22 tuổi" / "tuoi" — ưu tiên cao nhất, dùng full word
        r"\b(?:em|tôi|toi|mình|minh|cháu|chau|con)?\s*(\d{1,3})\s*(?:tuổi|tuoi)\b",
        # Pattern 2: "18t" — chỉ match khi KHÔNG theo sau bởi từ chỉ thời gian
        # Negative lookahead: không match "2t nay", "10t rồi", "3t qua"
        r"\b(\d{1,3})\s*t\b(?!\s*(?:nay|rồi|roi|qua|trước|truoc|sau|nữa|nua|hơn|hon))",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        age = int(m.group(1))
        # Tuổi hợp lý 5–80; dưới 5 hoặc trên 80 khả năng cao là duration/số khác
        if 5 <= age <= 80:
            return age
    return None


def _extract_duration_weeks(text: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\s*(năm|nam\b|ngày|ngay|tuần|tuan|tháng|thang)\b", text, re.I)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    if unit in {"năm", "nam"}:
        return value * 52
    if unit in {"ngày", "ngay"}:
        return max(1, round(value / 7))
    if unit in {"tháng", "thang"}:
        return value * 4
    return value


_SkinType = Literal["dry", "oily", "combination", "sensitive", "normal"]


# F5.1: Câu so sánh / câu hỏi chung không khai báo skin type cá nhân.
# Ví dụ: "da dầu có dễ bị mụn hơn da khô không?" — không phải user nói họ da dầu.
# Drop skin_type khi có các marker này trong cùng câu.
_SKIN_TYPE_QUESTION_MARKERS = (
    r"có\s+\S+.{0,40}\s+không\b",
    r"phải\s+\S+.{0,40}\s+không\b",
    r"hơn\s+\S+.{0,40}\s+không\b",
    r"dễ\s+\S+.{0,30}\s+hơn\b",
    r"khác\s+(?:gì|nhau)\b",
    r"so\s*sánh\b|so\s*sanh\b",
)
_SKIN_TYPE_QUESTION_RE = re.compile(
    "(?:" + "|".join(_SKIN_TYPE_QUESTION_MARKERS) + ")",
    flags=re.IGNORECASE,
)


def _extract_skin_type(text: str) -> _SkinType | None:
    # F5.1: nếu câu có markers so sánh / câu hỏi tổng quát → không extract skin type.
    # "da dầu có dễ bị mụn hơn da khô không" → user đang hỏi, không khai báo.
    if _SKIN_TYPE_QUESTION_RE.search(text):
        return None
    for value, pattern in _SKIN_TYPES:
        if _has(pattern, text):
            return cast(_SkinType, value)
    return None


def _extract_skin_type_from_texts(clean_text: str, clean_text_no_accent: str) -> _SkinType | None:
    value = _extract_skin_type(clean_text)
    if value is not None:
        return value
    if clean_text_no_accent and clean_text_no_accent != clean_text:
        if _has(r"\b(?:da|mặt)\s*đau\b", clean_text):
            return None
        return _extract_skin_type(clean_text_no_accent)
    return None


_Sex = Literal["male", "female", "other"]


def _extract_sex(text: str) -> _Sex | None:
    for value, pattern in _SEX_TERMS:
        if _has(pattern, text):
            return cast(_Sex, value)
    return None


# ── Phủ định / ngừng dùng — dùng chung cho product + canonical ingredient ──
# CHỈ nhận cue sát term (0-2 từ) để "không dùng X nữa" bị loại, còn
# "không bị kích ứng khi dùng X" (đang dùng, không phủ định) vẫn giữ.
_DISCONTINUE_CUE = (
    r"(?:không|khong|ko|chẳng|chang|chả|chưa|chua|ngưng|ngung|ngừng|"
    r"dừng|đừng|bỏ|bo|hết|het|thôi|thoi|tránh|tranh|stop|quit|no\s+longer)"
)


def _discontinued_before(before: str) -> bool:
    """True nếu ~30 ký tự cuối của `before` có cue phủ định/ngừng dùng sát term."""
    tail = before[-30:]
    return re.search(
        _DISCONTINUE_CUE + r"\s+(?:\w+\s+){0,2}$", tail, re.IGNORECASE
    ) is not None


def _positive_mention(pattern: str, text: str) -> bool:
    """True nếu có ít nhất một occurrence của pattern KHÔNG bị phủ định/ngừng dùng."""
    for m in re.finditer(pattern, text, re.IGNORECASE):
        if not _discontinued_before(text[:m.start()]):
            return True
    return False


def _has_product_use_context(lowered: str, term: str) -> bool:
    """Check if a product term appears in usage context (not just mentioned).

    Returns True only if the text indicates the user is CURRENTLY USING the product,
    not just asking about it.
    """
    for match in re.finditer(re.escape(term), lowered):
        start = match.start()
        before = lowered[max(0, start - 80):start]
        after = lowered[match.end():match.end() + 40]
        window = before + term + after

        # ── Phủ định / ngừng dùng: "không dùng X nữa", "ngưng/bỏ/hết X" ──
        if _discontinued_before(before):
            continue

        # ── Loại trừ: hỏi tư vấn, nghe nói, muốn biết ──
        # "hỏi về X", "muốn biết về X", "X có tốt không"
        if _has(r"(?:hỏi|muốn|mong|muon|tìm\s*hiểu|so\s*sánh|so\s*sanh)\b", before):
            continue
        if _has(r"(?:có\s+(?:nên|dùng|tốt|hay|bôi|thoa))?\s*(?:không|ko|k|chứ|chu)\b", after):
            continue
        if _has(r"\b(?:nên|dùng|tốt|hay|bôi|thoa|chọn|recommend|review)\b", after):
            continue
        # "X làm/gây ..." - đang nói về tác dụng phụ, không phải đang dùng
        if _has(r"(?:làm|gây|bị)\s+.{0,20}(?:kích\s*ứng|dị\s*ứng|rát|đỏ|ngứa)", before):
            continue
        # "X có tốt không" - câu hỏi
        if _has(r"có\s+.{0,30}\s*(?:không|tốt|hay|dùng)\b", before):
            continue

        # ── Xác nhận đang dùng: aspect marker trước sản phẩm ──
        # "đang dùng X", "đang bôi X", "có dùng X"
        if _has(r"\b(?:đang|dang|đã|da|mới|moi|vừa|vua|từng|tung|hiện\s*tại|hien\s*tai)\b", before):
            return True
        # "dùng X", "bôi X", "thoa X", "xài X" - verb trước
        if _has(r"\b(?:dùng|dung|bôi|boi|thoa|xài|xai|sử\s*dụng|su\s*dung|apply|đã\s*apply|chuyển\s*sang|chuyen\s*sang|đổi\s*sang|doi\s*sang)\b", before):
            return True
        # verb sau: "X dùng rồi", "X bôi sáng tối"
        if _has(r"\b(?:dùng|rồi|roi|thoa|bôi|apply)\b", after):
            return True
        # "của tôi là X" - sở hữu
        if _has(r"(?:của|cua|của\s*tôi)\s*$", before) or _has(r"^(?:tôi|toi|mình|minh)\s+(?:đang\s*)?(?:dùng|xài|bôi)", lowered):
            return True
        # Kèm frequency: "dùng X 2 lần/ngày", "bôi X sáng tối"
        if _has(rf"\b(?:dùng|dung|bôi|boi|thoa|xài)\s*{re.escape(term)}.{{0,30}}\b(?:lần|lan|sáng|tối|ngày|buổi)", window):
            return True
        if _has(r"\b(?:sáng|tối|ngày|buổi)\s*.{0,20}\b(?:dùng|dung|bôi|boi|thoa)", window):
            return True
    return False


# Canonical map: raw VN/partial terms → gold label-space (English)
_PRODUCT_CANONICAL_MAP: dict[str, str] = {
    # Cleansers
    "sữa rửa mặt": "cleanser",
    "sua rua mat": "cleanser",
    "gel rửa mặt": "cleanser",
    "gel rua mat": "cleanser",
    "facial wash": "cleanser",
    "foaming": "cleanser",
    "cleanser": "cleanser",
    # Moisturizers
    "kem dưỡng": "moisturizer",
    "kem duong": "moisturizer",
    "dưỡng ẩm": "moisturizer",
    "duong am": "moisturizer",
    "moisturizer": "moisturizer",
    # Sunscreen
    "kem chống nắng": "sunscreen",
    "kem chong nang": "sunscreen",
    "sunscreen": "sunscreen",
    "spf": "sunscreen",
    # BHA
    "bha": "BHA",
    "salicylic acid": "salicylic acid",
    "acid salicylic": "salicylic acid",
    "salicylic": "salicylic acid",
    # AHA
    "aha": "AHA",
    "glycolic acid": "glycolic acid",
    "acid glycolic": "glycolic acid",
    "glycolic": "glycolic acid",
    "lactic acid": "lactic acid",
    # Vitamin C
    "vitamin c": "vitamin c",
    # Niacinamide
    "niacinamide": "niacinamide",
    # Hyaluronic acid
    "hyaluronic acid": "hyaluronic acid",
    "acid hyaluronic": "hyaluronic acid",
    # Ceramide
    "ceramide": "ceramide",
    # Centella
    "centella": "centella",
    "rau má": "centella",
    "rau ma": "centella",
    # Benzoyl peroxide
    "benzoyl peroxide": "benzoyl peroxide",
    "bpo": "benzoyl peroxide",
    # Retinoids — keep as-is (gold uses these labels)
    "retinol": "retinol",
    "retinoid": "retinoid",
    "retinal": "retinol",
    "retinaldehyde": "retinol",
    "tretinoin": "tretinoin",
    "retin-a": "tretinoin",
    "adapalene": "adapalene",
    "differin": "adapalene",
    "tazarotene": "tazarotene",
    # Toner
    "toner": "toner",
    "nước hoa hồng": "toner",
    "nuoc hoa hong": "toner",
    # Serum
    "serum": "serum",
    # Azelaic acid
    "azelaic acid": "azelaic acid",
    "acid azelaic": "azelaic acid",
    # Tea tree
    "tea tree": "tea tree",
    # Clindamycin (topical product context)
    "clindamycin": "clindamycin",
    # Glycolic (already covered above via AHA)
}


def _extract_products(text: str) -> list[str]:
    lowered = text.lower()
    found_raw = [
        term for term in _PRODUCT_TERMS
        if _has(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
        and _has_product_use_context(lowered, term)
    ]
    # Apply canonical mapping → gold label-space
    canonical: list[str] = []
    for term in found_raw:
        mapped = _PRODUCT_CANONICAL_MAP.get(term)
        if mapped:
            canonical.append(mapped)
        else:
            canonical.append(term)
    return _dedupe(canonical)


def _extract_canonical_ingredients(
    products: list[str],
    medications: list[str],
    clean_text: str,
    clean_text_no_accent: str,
) -> list[str]:
    canonical: list[str] = []
    prod_med = " ".join(products + medications).lower()

    def _in_use(text_pat: str, prod_med_pat: str) -> bool:
        # Đã xác nhận qua products/medications (đã lọc usage) → chắc chắn đang dùng.
        if _has(prod_med_pat, prod_med):
            return True
        # Hoặc được nhắc trong text mà KHÔNG bị phủ định/ngừng dùng.
        return (
            _positive_mention(text_pat, clean_text)
            or _positive_mention(text_pat, clean_text_no_accent)
        )

    bha = r"(?<!\w)(?:bha|salicylic(?:\s+acid)?|acid\s+salicylic)(?!\w)"
    aha = r"(?<!\w)(?:aha|glycolic(?:\s+acid)?|acid\s+glycolic)(?!\w)"
    tret = r"(?<!\w)(?:vitamin\s+a\s+acid|tretinoin|retin-a)(?!\w)"

    if _in_use(bha, r"(?<!\w)(?:bha|salicylic|acid\s+salicylic)(?!\w)"):
        canonical.append("salicylic_acid")
    if _in_use(aha, r"(?<!\w)(?:aha|glycolic|acid\s+glycolic)(?!\w)"):
        canonical.append("glycolic_acid")

    # Conservative VA handling: uppercase VA is accepted; lowercase "va" is not,
    # because no-accent "và" also becomes "va".
    if re.search(r"(?<!\w)VA(?!\w)", clean_text) or _in_use(tret, tret):
        canonical.append("tretinoin")

    return _dedupe(canonical)


def _extract_usage_frequencies(text: str) -> list[str]:
    found: list[str] = []
    if _has(
        r"\b(?:sáng\s*tối|sang\s*toi|ngày\s*2\s*lần|ngay\s*2\s*lan|"
        r"2\s*lần\s*/\s*ngày|2\s*lan\s*/\s*ngay|2\s*lần\s*mỗi\s*ngày|"
        r"2\s*lan\s*moi\s*ngay|twice\s*daily)\b",
        text,
    ):
        found.append("twice_daily")
    if _has(
        r"\b(?:cách\s*ngày|cach\s*ngay|2\s*ngày\s*/\s*lần|2\s*ngay\s*/\s*lan|"
        r"mỗi\s*2\s*ngày|moi\s*2\s*ngay|hai\s*ngày\s*một\s*lần|"
        r"hai\s*ngay\s*mot\s*lan|every\s*other\s*day)\b",
        text,
    ):
        found.append("every_other_day")
    return _dedupe(found)


def _extract_concentrations(text: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*%", text):
        try:
            values.append(float(match.group(1).replace(",", ".")) / 100.0)
        except ValueError:
            continue
    return _dedupe_floats(values)


def _has_medication_use_context(lowered: str, term: str) -> bool:
    for match in re.finditer(re.escape(term), lowered):
        start = match.start()
        before = lowered[max(0, start - 80):start]   # mở rộng 60→80 để bắt "đang bôi X"
        after = lowered[match.end():match.end() + 40]
        window = before + term + after

        # ── Loại trừ: hỏi tư vấn, nghe nói, được khuyên ──
        if _has(r"(?:có|co)\s*(?:nên|nen|cần|can|thể|the)\s+(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung)", before):
            continue
        if _has(r"\b(?:nên|nen|muốn|muon|định|dinh|tự\s*ý|tu\s*y|mua)\s+(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung)\b", before):
            continue
        if _has(r"\b(?:khuyên|khuyen|gợi\s*ý|goi\s*y|nghe\s*nói|nghe\s*noi|trên\s*mạng|tren\s*mang|nghe\s*bảo|nghe\s*bao)\b", before):
            continue
        if _has(r"\b(?:(?:có|co)\s*(?:nên|nen|cần|can)|(?:nên|nen)\s*(?:dùng|dung|uống|uong)|(?:có|co)\s*(?:thể|the)\s*(?:dùng|dung))\b", before):
            continue

        # ── Loại trừ: phủ định "không/chưa/ngưng/dừng/tránh + verb" ngay trước thuốc ──
        # vd: "không dùng tretinoin", "ngưng bôi adapalene"
        if _has(
            r"\b(?:không|khong|ko|k|chưa|chua|đừng|dung|ngưng|ngung|dừng|tránh|tranh)\b"
            r"\s+(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung)\s*$",
            before,
        ):
            continue

        # ── Xác nhận đang dùng: aspect marker trước thuốc (ưu tiên cao nhất) ──
        if _has(r"\b(?:đang|dang|đã|da|mới|moi|vừa|vua|từng|tung|hiện\s*tại|hien\s*tai)\b", before):
            return True

        # ── Loại trừ: câu hỏi/giả định về thuốc (khi KHÔNG có dấu hiệu đang dùng) ──
        # vd: "Uống thuốc tránh thai có giúp hết mụn không?", "tretinoin có tốt không",
        #     "isotretinoin là gì", "vai trò của ... là gì"
        if _has(
            r"(?:có|co)\s+(?:giúp|giup|hết|het|nên|nen|tốt|tot|bị|bi|được|duoc|"
            r"hiệu\s*quả|hieu\s*qua|tác\s*dụng|tac\s*dung|vai\s*trò|vai\s*tro)"
            r"|\b(?:là\s*gì|la\s*gi|thế\s*nào|the\s*nao|ra\s*sao|"
            r"có\s*nên|co\s*nen|có\s*thể|co\s*the)\b",
            window,
        ):
            continue

        # ── Xác nhận: verb dùng thuốc trước hoặc sau ──
        # Lưu ý: KHÔNG có "ngưng/ngung" và "dừng/dung" ở đây vì chúng là negation
        if _has(r"\b(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung)\b", before):
            return True
        if _has(r"\b(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung)\b", after):
            return True
        # ── Xác nhận: bác sĩ kê ──
        if _has(r"\b(?:bác\s*sĩ|bac\s*si|bs|doctor)\s*(?:kê|ke|cho)\b|\b(?:kê|ke)\s*(?:thêm)?\b", before):
            return True
        # ── Xác nhận: kèm thời gian dùng ("được 2 tháng", "3 tuần nay") ──
        if _has(r"\bđược\s*\d{1,3}\s*(?:ngày|tuần|tháng)\b|\b\d{1,3}\s*(?:ngày|tuần|tháng)\s*(?:nay|rồi)?\b", window):
            return True
        # ── Xác nhận: "tối bôi", "buổi tối dùng", "sáng thoa" ──
        if _has(r"\b(?:tối|buổi\s*tối|sáng|buổi\s*sáng|ngày\s*\d+\s*lần|mỗi\s*(?:tối|ngày|sáng))\b", window):
            return True
    return False


def _extract_medications(text: str) -> list[str]:
    lowered = text.lower()
    found = [
        term for term in _MEDICATION_TERMS
        if _has(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
        and _has_medication_use_context(lowered, term)
    ]
    return _dedupe("adapalene" if term == "ada" else term for term in found)


_LesionType = Literal[
    "comedone", "whitehead", "blackhead", "closed_comedone", "papule", "pustule",
    "nodule", "cyst", "scar",
    "post_inflammatory_hyperpigmentation", "other",
]
_Distribution = Literal[
    "forehead", "cheeks", "chin", "jawline", "nose", "around_mouth",
    "back", "chest", "shoulders", "neck", "t_zone", "other",
]


def _extract_distributions(text: str) -> list[_Distribution]:
    return cast(list[_Distribution], _dedupe([value for value, pattern in _DISTRIBUTION_TERMS if _has(pattern, text)]))


def _extract_lesions(text: str) -> list[_LesionType]:
    return cast(list[_LesionType], _dedupe([value for value, pattern in _LESION_TERMS if _has(pattern, text)]))


def _extract_hormonal_factors(text: str) -> list[str]:
    return _dedupe([value for value, pattern in _HORMONAL_TERMS if _has(pattern, text)])


def _extract_red_flags(text: str) -> list[str]:
    """Extract red flags. Painful_lesions bổ sung: bare 'đau' trong context mụn."""
    results: list[str] = []
    for value, pattern in _RED_FLAG_TERMS:
        if _has(pattern, text):
            results.append(value)

    # Bổ sung painful_lesions: "đau" + mụn trong window (self-description)
    if "painful_lesions" not in results:
        _acne_pain_context = (
            r"(?:"
            r"\b(?:mụn|mun|cục|cuc|nốt|not)\s*(?:bị\s*)?(?:hơi\s*)?đau\b"
            r"|\bđau\s*(?:ở\s*)?(?:mụn|mun|cục|cuc|nốt|not)\b"
            r"|\b(?:mụn|mun|cục|cuc|nốt|not).{0,30}\bđau\b"
            r"|\bđau\b.{0,30}(?:mụn|mun|cục|cuc|nốt|not)\b"
            r")"
        )
        if _has(_acne_pain_context, text) and _is_self_description(text):
            results.append("painful_lesions")

    return _dedupe(results)


def _extract_allergies(text: str) -> list[str]:
    """Extract các chất user dị ứng / kích ứng.

    "unknown" là catch-all generic — nếu cùng câu có chất canonical cụ thể
    (retinol, bha, niacinamide, ...), drop "unknown" để tránh nhiễu.
    """
    found = [value for value, pattern in _ALLERGY_TERMS if _has(pattern, text)]
    deduped = _dedupe(found)
    if "unknown" in deduped and any(v != "unknown" for v in deduped):
        deduped = [v for v in deduped if v != "unknown"]
    return deduped


# Signals that user is seeking treatment advice for their acne
_SEEK_TREATMENT_SIGNALS = (
    r"\b(?:"
    r"tư\s*vấn|tu\s*van"
    r"|giúp|giup"
    r"|làm\s*sao|lam\s*sao"
    r"|phải\s*làm\s*gì|phai\s*lam\s*gi"
    r"|nên\s*(?:làm|dùng|bôi|chọn)|nen\s*(?:lam|dung|boi|chon)"
    r"|có\s*cách\s*nào|co\s*cach\s*nao"
    r"|cần\s*(?:làm|dùng|bôi|điều\s*trị)|can\s*(?:lam|dung|boi)"
    r"|muốn\s*(?:hỏi|biết|tìm|trị)|muon\s*(?:hoi|biet|tim|tri)"
    r"|xin\s*(?:hỏi|tư\s*vấn|giúp)|xin\s*(?:hoi|tu\s*van|giup)"
    r"|cách\s*(?:trị|điều\s*trị|chữa)|cach\s*(?:tri|dieu\s*tri|chua)"
    r"|what\s*should|how\s*to"
    r"|giải\s*pháp|giai\s*phap"
    r"|khắc\s*phục|khac\s*phuc"
    r")\b"
)

# Signals that user HAS acne (self-description) — for clear_acne default inference
_HAS_ACNE_SELF = (
    r"\b(?:"
    r"bị\s*mụn|bi\s*mun"
    r"|nổi\s*mụn|noi\s*mun"
    r"|da\s*(?:tôi|toi|mình|minh|em|cháu|chau)\s*(?:bị|có|nổi)\s*mụn"
    r"|mụn\s*(?:của|trên|ở|mình|tôi|em)"
    r"|mụn\s*(?:nhiều|đỏ|viêm|bọc|mủ|nổi|khắp)"
    r"|mun\s*(?:nhieu|do|viem|boc|mu|noi|khap)"
    r"|có\s*mụn\s*(?:ở|trên|khắp)"
    r")\b"
)


def _extract_treatment_goals(text: str) -> list[str]:
    """Extract mục tiêu điều trị của user."""
    found = [value for value, pattern in _TREATMENT_GOAL_TERMS if _has(pattern, text)]

    # Default clear_acne: user mô tả đang bị mụn + tìm kiếm lời khuyên/tư vấn
    if "clear_acne" not in found:
        has_self_acne = _has(_HAS_ACNE_SELF, text)
        has_seek = _has(_SEEK_TREATMENT_SIGNALS, text)
        not_pure_knowledge = not (_is_knowledge_question(text) and not _is_self_description(text))
        if has_self_acne and has_seek and not_pure_knowledge:
            found = ["clear_acne"] + found

    # Infer reduce_inflammation: mụn viêm + đang tìm cách xử lý
    _inflam_lesion_signal = (
        r"\b(?:mụn\s*viêm|mun\s*viem"
        r"|mụn\s*đỏ|mun\s*do"
        r"|sưng\s*đỏ|sung\s*do"
        r"|viêm\s*đỏ|viem\s*do"
        r"|mụn\s*mủ|mun\s*mu"
        r"|papule|pustule"
        r")\b"
    )
    if "reduce_inflammation" not in found:
        if _has(_inflam_lesion_signal, text) and _has(_SEEK_TREATMENT_SIGNALS, text):
            found.append("reduce_inflammation")

    # Infer see_doctor: severity signals → bác sĩ nên được khuyên
    _severe_acne_signal = (
        r"\b(?:mụn\s*nặng|mun\s*nang\b"
        r"|nodulocystic"
        r"|mụn\s*bọc\s*nang|mun\s*boc\s*nang"
        r"|nhiễm\s*trùng|nhiem\s*trung"
        r"|viêm\s*nặng|viem\s*nang"
        r"|sốt|sot\b|fever"
        r"|có\s*(?:cả\s*)?máu|chảy\s*máu"
        r"|mụn\s*mức\s*độ\s*nặng"
        r")\b"
    )
    if "see_doctor" not in found:
        if _has(_severe_acne_signal, text) and _has(_HAS_ACNE_SELF, text):
            found.append("see_doctor")

    return _dedupe(found)


def _extract_scarring_signs_from_extracted(
    lesion_types: list[str],
    red_flags: list[str],
) -> list[str]:
    """Normalize scar/PIH signals into the free-text scarring_signs schema field."""
    signs: list[str] = []
    if "scar" in lesion_types or "scarring_risk" in red_flags:
        signs.append("sẹo mụn")
    if "post_inflammatory_hyperpigmentation" in lesion_types:
        signs.append("thâm sau mụn")
    return _dedupe(signs)


_Inflammation = Literal["none", "mild", "moderate", "severe", "unknown"]
_INFLAMMATION_ORDER: dict[str, int] = {
    "unknown": 0,
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}


def _strongest_inflammation(values: list[str | None]) -> _Inflammation | None:
    best: str | None = None
    for value in values:
        if value is None:
            continue
        if best is None or _INFLAMMATION_ORDER.get(value, 0) > _INFLAMMATION_ORDER.get(best, 0):
            best = value
    return cast(_Inflammation, best) if best is not None else None


def _is_self_description(text: str) -> bool:
    """Trả True nếu câu mô tả tình trạng da / mụn của chính người viết (ngôi thứ nhất).

    Phân biệt "tôi bị mụn" (self-description) vs "mình muốn hỏi về mụn" (knowledge question).
    Yêu cầu ĐỒNG THỜI: (a) pronoun ngôi-1 VÀ (b) mô tả triệu chứng cụ thể.
    """
    _first_person_pronoun = r"\b(?:tôi|toi|mình|minh|em|cháu|chau|con)\b"
    _symptom_descriptor = (
        r"\b(?:"
        r"bị\s*mụn|bi\s*mun"
        r"|nổi\s*mụn|noi\s*mun"
        r"|có\s*mụn|co\s*mun"
        r"|da\s*(?:tôi|toi|mình|minh|em|cháu|chau)"
        r"|mặt\s*(?:tôi|toi|mình|minh|em|cháu|chau)"
        r"|mụn\s*(?:ở|trên|khắp|bị|nổi)"
        r"|mụn\s*(?:đang|mới|vừa|hay)"
        r"|mụn\s*(?:của\s*(?:tôi|toi|em|mình))"
        r"|da\s*(?:đang\s*(?:bị|có|nổi)|bị|có\s*mụn)"
        r"|nổi\s*(?:mụn|sẩn|nốt|hạt)"
        r"|bị\s*(?:viêm|sưng|đỏ|ngứa|rát)"
        r"|mụn\s*(?:viêm|đỏ|mủ|bọc|nang|cục)"
        r")\b"
    )
    has_pronoun = _has(_first_person_pronoun, text)
    has_symptom = _has(_symptom_descriptor, text)
    return has_pronoun and has_symptom


def _is_knowledge_question(text: str) -> bool:
    """Trả True nếu câu là hỏi định nghĩa / so sánh chung, không mô tả tình trạng bản thân."""
    _knowledge_markers = (
        r"\b(?:"
        r"là\s*gì|la\s*gi"
        r"|phân\s*biệt|phan\s*biet"
        r"|khác\s*(?:gì|nhau)|khac\s*(?:gi|nhau)"
        r"|so\s*sánh|so\s*sanh"
        r"|giải\s*thích|giai\s*thich"
        r"|định\s*nghĩa|dinh\s*nghia"
        r"|tại\s*sao\s*(?:mụn|da)"
        r"|nguyên\s*nhân\s*(?:gây|của)\s*mụn"
        r"|cơ\s*chế\s*(?:gây|của)"
        r")\b"
    )
    return _has(_knowledge_markers, text)


def _extract_inflammation(text: str, lesion_types: list[_LesionType]) -> _Inflammation | None:
    # Gate: câu hỏi kiến thức chung không có ngôi-1 → không suy inflammation
    if _is_knowledge_question(text) and not _is_self_description(text):
        return None

    # Severe: CHỈ fire khi có ngữ cảnh mụn rõ ràng — tránh "vết thương nặng", "sốt thông thường"
    # Gate: severe chỉ suy khi là self-description có liên quan đến mụn
    _acne_context = r"\b(?:mụn|mun|viêm|viem|da\s*(?:mặt|mat)|acne)\b"
    _has_acne_context = _has(_acne_context, text)

    # Severe: fire khi có ngữ cảnh mụn + tín hiệu rõ ràng
    _severe_signal = (
        r"\b(?:"
        r"(?:mụn|mun|viêm|viem)\s*nặng(?:\s*lắm)?|severe\s*acne\b"
        r"|mụn\s*(?:rất\s*)?to(?:\s*và\s*đau)?"
        r"|từng\s*cục(?:\s*cứng)?"
        r"|sưng\s*(?:to\s*)?(?:và\s*)?đau"
        r"|đau\s*(?:nhiều|lắm|rất|quá)"
        r"|rất\s*đau"
        r"|lan\s*rộng|lan\s*rong|khắp\s*(?:mặt|lưng|người)"
        r"|nodulocystic"
        r"|mụn\s*(?:bọc\s*)?nang\s*(?:to|nhiều)"
        r"|mụn\s*(?:nổi\s*)?khắp"
        r"|dày\s*đặc\s*(?:mụn)?"
        r"|viêm\s*nặng|viem\s*nang"
        r"|mụn\s*mức\s*độ\s*nặng"
        r")\b"
    )
    if _has(_severe_signal, text):
        return "severe"
    # nodule + đau → severe (bao gồm cả "hơi đau" trong ngữ cảnh nodule)
    if "nodule" in lesion_types and _has(r"\b(?:đau|dau|pain|painful|nhức)\b", text) and _has_acne_context:
        return "severe"
    # máu → severe khi có acne context (không fire trên "bé bị sốt")
    if _has(r"\b(?:có\s*(?:cả\s*)?máu|chảy\s*máu|ra\s*máu|máu\s*chảy|máu\s*(?:cũng\s*|còn\s*)?(?:ra|chảy|rỉ)|bleeding)\b", text) and _has_acne_context:
        return "severe"
    # sốt + acne context → severe
    if _has(r"\b(?:sốt|sot|fever|nhiễm\s*trùng|nhiem\s*trung|nóng\s*sốt|nong\s*sot|hạch\s*sưng)\b", text) and _has_acne_context:
        return "severe"

    # Count context — dùng để calibrate: few + inflammatory lesion → mild, không phải moderate
    acne_count = _extract_acne_count(text)

    # Lesion type sets
    _purely_comedonal_lesions = {"whitehead", "blackhead", "closed_comedone"}
    _active_inflammatory_lesions = {"papule", "pustule", "nodule", "cyst"}
    _sequelae_lesions = {"scar", "post_inflammatory_hyperpigmentation"}
    _has_inflammatory_lesion = any(t in lesion_types for t in _active_inflammatory_lesions)
    _has_any_lesion = bool(lesion_types)

    # None: comedone/sequelae/other only + explicit "không viêm/sưng/đau" → non-inflammatory
    _no_inflammation_signal = (
        r"\b(?:"
        r"không\s*(?:bị\s*)?(?:viêm|sưng|đỏ|đau)|khong\s*(?:bi\s*)?(?:viem|sung|do|dau)"
        r"|không\s*(?:bị\s*)?viêm\s*(?:không\s*(?:bị\s*)?sưng)?"
        r"|không\s*sưng\s*không\s*đau|khong\s*sung\s*khong\s*dau"
        r"|không\s*đỏ\s*không\s*đau|khong\s*do\s*khong\s*dau"
        r"|không\s*có\s*(?:dấu\s*hiệu\s*|dau\s*hieu\s*)?(?:viêm|viem)"
        r"|khong\s*co\s*(?:dau\s*hieu\s*)?viem"
        r"|non.?inflammatory"
        r"|mụn\s*không\s*(?:bị\s*)?viêm|mun\s*khong\s*(?:bi\s*)?viem"
        r")\b"
    )
    _only_comedonal = (_has_any_lesion and
                       all(t in _purely_comedonal_lesions for t in lesion_types))
    _explicit_no_inflam = _has(_no_inflammation_signal, text)

    if (_only_comedonal or _explicit_no_inflam) and not _has_inflammatory_lesion:
        return "none"

    # Mild explicit signal — kiểm tra TRƯỚC khi suy từ lesion type
    # Bao gồm cả dạng có/không dấu để xử lý cả clean_text lẫn clean_text_no_accent
    _mild_signal = (
        r"\b(?:"
        r"nhẹ|nhe\b|mild\b"
        r"|nhỏ|nho\b"                                               # small = mild
        r"|mụn\s*(?:nhỏ|nho|ít|it|vài\s*cái|vai\s*cai|1-?2\s*(?:nốt|not|cái|cai|mụn|mun))"
        r"|ít\s*mụn|it\s*mun"
        r"|mụn\s*ít\s*(?:thôi|thoi|vài\s*cái|vai\s*cai)?|mun\s*it\b"
        r"|ít\s*thôi|it\s*thoi"                                     # "ít thôi" / "it thoi"
        r"|vài\s*(?:nốt|not|mụn|mun|cái|cai)|vai\s*(?:not|mun|cai)\b"  # vài nốt/mụn
        r"|không\s*(?:bị\s*)?(?:đau|dau|sưng|sung|viêm|viem)|khong\s*(?:bi\s*)?(?:dau|sung|viem)"
        r"|mụn\s*không\s*(?:sưng|đau)|mun\s*khong\s*(?:sung|dau)"
        r"|chỉ\s*(?:vài|vai|1-?2)\s*(?:nốt|not|mụn|mun|cái|cai)|chi\s*(?:vai|1-?2)\s*(?:not|mun|cai)"
        r")\b"
    )
    _has_mild_signal = _has(_mild_signal, text) or acne_count == "few"

    # Moderate: tín hiệu TƯỜNG MINH — không suy từ lesion đơn thuần
    _moderate_signal = (
        r"\b(?:"
        r"viêm\s*(?:vừa|nhẹ\s*đến\s*vừa)|moderate\b"
        r"|sưng\s*đỏ(?!\s*(?:và\s*)?đau\s*nhiều)"
        r"|mụn\s*đỏ\s*(?:và\s*)?sưng"
        r"|viêm\s*đỏ"
        r"|mụn\s*mủ(?:\s*(?:vàng|trắng|xanh))?|mun\s*mu(?:\s*(?:vang|trang|xanh))?"
        r")\b"
    )
    _has_explicit_moderate = _has(_moderate_signal, text)

    # Suy moderate từ lesion: CHỈ KHI có inflammatory lesion + không có mild signal + self-desc
    _lesion_moderate = (_has_inflammatory_lesion and not _has_mild_signal
                        and _is_self_description(text))

    if _has_explicit_moderate or _lesion_moderate:
        return "moderate"

    # Mild: explicit mild signal + có inflammatory lesion (vd "vài nốt đỏ nhỏ")
    if _has_mild_signal and _has_inflammatory_lesion:
        return "mild"

    # Mild: explicit mild signal + self-description (vd "nhẹ thôi", "mụn ít")
    if _has_mild_signal and _is_self_description(text):
        return "mild"

    # Không đủ tín hiệu rõ ràng → không suy
    return None


# Mụn đã khỏi / thuộc quá khứ — chỉ còn quan tâm thâm/sẹo.
# Khi khớp, ta KHÔNG suy mụn viêm đang hoạt động (papule/pustule/nodule/cyst)
# và ép inflammation = none, vì gold coi đây là ca đã hết mụn.
_ACNE_RESOLVED_PATTERNS: tuple[str, ...] = (
    r"\b(?:đã|giờ|hiện\s*(?:giờ|tại)?|nay|bây\s*giờ)\s*(?:đã\s*)?hết\s*mụn\b",
    r"\bhết\s*mụn\s*(?:rồi|lâu\s*rồi|hẳn|sạch)\b",
    r"\bmụn\s*(?:đã|giờ|nay)\s*(?:đã\s*)?(?:hết|hết\s*rồi|khỏi|lặn|xẹp|đỡ\s*hẳn)\b",
    r"\bmụn\s*(?:đã\s*)?khỏi\b",
    r"\bkhỏi\s*mụn\b",
    r"\bsau\s*(?:khi\s*)?hết\s*mụn\b",
    r"\bmụn\s*hết\s*(?:rồi|hẳn|sạch)\b",
    r"\btừng\s*bị\s*mụn\b",
    r"\bhồi\b.{0,40}\b(?:giờ|nay|bây\s*giờ)\s*(?:đã\s*)?hết\b",
    # unaccented
    r"\b(?:da|gio|hien)\s*(?:da\s*)?het\s*mun\b",
    r"\bhet\s*mun\s*roi\b",
    r"\bmun\s*(?:da|gio|nay)\s*(?:het|khoi|lan|xep)\b",
    r"\btung\s*bi\s*mun\b",
)
# Nếu có tín hiệu mụn ĐANG hoạt động thì KHÔNG áp guard (tránh suppress nhầm ca hỗn hợp).
_ACNE_PRESENT_PATTERNS: tuple[str, ...] = (
    r"\b(?:vẫn|van)\s*(?:còn|con|bị|bi|đang|dang)\b",
    r"\bhiện\s*(?:tại\s*)?(?:vẫn\s*)?(?:đang\s*)?(?:bị|nổi|mọc|còn)\b",
    r"\bđang\s*bị\s*mụn\b|dang\s*bi\s*mun",
    r"\b(?:dạo|dao|gần|gan)\s*(?:này|nay|đây|day)\b",
    r"\bmới\s*(?:nổi|lên|mọc|bị)\b|moi\s*(?:noi|len|moc|bi)",
    r"\bmọc\s*(?:thêm|nhiều)\b|moc\s*(?:them|nhieu)",
)

_ACTIVE_INFLAMMATORY_LESIONS = frozenset(
    {"papule", "pustule", "nodule", "cyst", "other"}
)


def _acne_resolved(clean_text: str, clean_text_no_accent: str) -> bool:
    for pat in _ACNE_PRESENT_PATTERNS:
        if _has(pat, clean_text) or _has(pat, clean_text_no_accent):
            return False
    for pat in _ACNE_RESOLVED_PATTERNS:
        if _has(pat, clean_text) or _has(pat, clean_text_no_accent):
            return True
    return False


def _contains_positive(text: str, positive: str, negative: str) -> bool:
    if _has(negative, text):
        return False
    return _has(positive, text)


def normalize_chat_message(
    message: str,
    mode: str = "auto",
    clean_text: str | None = None,
    clean_text_no_accent: str | None = None,
) -> UserInput:
    """Convert a free-form chat message into the existing UserInput schema.

    description = raw_for_llm  (NFC + strip control chars, giữ emphasis gốc)
    Regex extraction dùng clean_text + clean_text_no_accent — chỉ là local var.
    """
    # raw_for_llm: tối thiểu để LLM thấy ngôn ngữ tự nhiên đầy đủ
    raw_for_llm = _light_normalize(message)

    # clean_text: full preprocess chỉ dùng nội bộ cho regex.
    # Intake truyền sẵn để mỗi request chỉ preprocess một lần; legacy callers
    # không truyền thì normalizer tự tính để giữ tương thích.
    if clean_text is None:
        prepared = prepare_user_text(message)
        clean_text = prepared.clean_text
        clean_text_no_accent = prepared.clean_text_no_accent
    elif clean_text_no_accent is None:
        clean_text_no_accent = strip_accents(clean_text)

    extraction_texts = _texts_for_extraction(clean_text, clean_text_no_accent)
    lesion_types = cast(list[_LesionType], _merge_extracted(extraction_texts, _extract_lesions))
    distribution = cast(list[_Distribution], _merge_extracted(extraction_texts, _extract_distributions))

    # Guard "mụn đã khỏi": nếu mụn thuộc quá khứ, bỏ các lesion viêm đang hoạt
    # động (giữ lại thâm/sẹo/comedone user vẫn đang quan tâm) và ép viêm = none.
    acne_resolved = _acne_resolved(clean_text, clean_text_no_accent or "")
    if acne_resolved:
        lesion_types = cast(
            list[_LesionType],
            [lt for lt in lesion_types if lt not in _ACTIVE_INFLAMMATORY_LESIONS],
        )

    inflammation = _strongest_inflammation(
        [_extract_inflammation(text, lesion_types) for text in extraction_texts]
    )
    if acne_resolved:
        # Mụn đã khỏi → không còn viêm hoạt động.
        inflammation = cast(_Inflammation, "none")
    red_flags = _merge_extracted(extraction_texts, _extract_red_flags)
    medications = _dedupe_accent_insensitive(
        _merge_extracted(extraction_texts, _extract_medications)
    )
    products = _dedupe_accent_insensitive(
        _merge_extracted(extraction_texts, _extract_products)
    )
    hormonal_factors = _merge_extracted(extraction_texts, _extract_hormonal_factors)
    allergies = _merge_extracted(extraction_texts, _extract_allergies)
    treatment_goals = _merge_extracted(extraction_texts, _extract_treatment_goals)
    scarring_signs = _extract_scarring_signs_from_extracted(lesion_types, red_flags)
    canonical_ingredients = _extract_canonical_ingredients(
        products,
        medications,
        clean_text,
        clean_text_no_accent,
    )
    usage_frequencies = _merge_extracted(extraction_texts, _extract_usage_frequencies)
    concentrations = _dedupe_floats(
        [value for text in extraction_texts for value in _extract_concentrations(text)]
    )

    # Suy female CHỈ từ tín hiệu chắc chắn (kinh nguyệt/thai/sau sinh/PCOS),
    # KHÔNG đoán từ đại từ chị/em vì không đáng tin.
    sex = _first_extracted(extraction_texts, _extract_sex)
    if sex is None and any(
        h in {"menstrual_cycle", "pregnancy", "postpartum", "pcos"}
        for h in hormonal_factors
    ):
        sex = cast(_Sex, "female")

    context = UserContext(
        age=_first_extracted(extraction_texts, _extract_age),
        sex=sex,
        skin_type=_extract_skin_type_from_texts(clean_text, clean_text_no_accent),
        is_pregnant=_contains_positive(
            clean_text,
            r"\b(?:mang thai|có thai|co thai|đang bầu|dang bau|pregnant)\b",
            r"\b(?:không|khong|ko|k)\s+(?:mang thai|có thai|co thai|bầu|bau)\b",
        ) or _contains_positive(
            clean_text_no_accent,
            r"\b(?:mang thai|co thai|dang bau|pregnant)\b",
            r"\b(?:khong|ko|k)\s+(?:mang thai|co thai|bau)\b",
        ),
        is_breastfeeding=_contains_positive(
            clean_text,
            r"\b(?:cho con bú|cho con bu|breastfeeding)\b",
            r"\b(?:không|khong|ko|k)\s+(?:cho con bú|cho con bu|breastfeeding)\b",
        ) or _contains_positive(
            clean_text_no_accent,
            r"\b(?:cho con bu|breastfeeding)\b",
            r"\b(?:khong|ko|k)\b",
        ),
        current_products=products,
        medications=medications,
        duration_weeks=_first_extracted(extraction_texts, _extract_duration_weeks),
        allergies=allergies,
    )

    clinical = AcneClinicalInput(
        lesion_types=lesion_types,
        lesion_distribution=distribution,
        inflammation_level=inflammation if inflammation is not None else "unknown",
        scarring_signs=scarring_signs,
        medication_history=medications,
        skincare_products=products,
        canonical_ingredients=canonical_ingredients,
        usage_frequencies=usage_frequencies,
        concentrations=concentrations,
        red_flags_input=red_flags,
        treatment_goals=treatment_goals,
        hormonal_factors=hormonal_factors,
    ) if (
        lesion_types or distribution or inflammation or red_flags or hormonal_factors
        or medications or products or canonical_ingredients or usage_frequencies
        or concentrations
    ) else None

    safe_mode = mode if mode in {"hybrid", "llm_only"} else "hybrid"
    return UserInput(description=raw_for_llm, context=context, clinical=clinical, mode=safe_mode)
