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
from typing import TYPE_CHECKING, Literal, cast

from ..schemas import AcneClinicalInput, UserContext, UserInput
from .preprocess import preprocess_user_text


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
    ("oily", r"\b(?:da\s*)?(?:"
     r"dau|dầu"
     r"|nhờn|nhon"
     r"|bóng\s*dầu|bong\s*dau"
     r"|oily\b"
     r"|tiết\s*(?:nhiều\s*)?dầu|tiet\s*(?:nhieu\s*)?dau"
     r"|bóng\s*nhờn|bong\s*nhon"
     r"|da\s*bóng(?:\s*nhờn)?"
     r"|dầu\s*nhiều|dau\s*nhieu"
     r"|nhờn\s*nhiều"
     r"|chảy\s*dầu|chay\s*dau"
     r"|bết\s*dầu|bet\s*dau"
     r"|bóng\s*loáng"
     r")\b"),
    ("dry", r"\b(?:da\s*)?(?:"
     r"khô|kho\b"
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
     r"|kết\s*hợp"
     r"|da\s*hỗn\s*hợp"
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
    ("normal", r"\b(?:da\s*)?(?:"
     r"thường|thuong\b"
     r"|normal\b"
     r"|bình\s*thường|binh\s*thuong"
     r"|da\s*bình\s*thường"
     r"|không\s*(?:quá\s*)?dầu\s*(?:không\s*(?:quá\s*)?khô)?"
     r")\b"),
]

_SEX_TERMS: list[tuple[str, str]] = [
    ("male", r"\b(?:tôi|toi|mình|minh|em|cháu|chau|mình)?\s*(?:là|la)?\s*(?:nam|male|con\s*trai|boy|men|man|anh|chú|bạn\s*nam|giới\s*tính\s*nam)\b"),
    ("female", r"\b(?:tôi|toi|mình|minh|em|cháu|chau|mình)?\s*(?:là|la)?\s*(?:nữ|nu|female|con\s*gái|girl|women|woman|chị|bạn\s*nữ|giới\s*tính\s*nữ)\b"),
]

_PRODUCT_TERMS = [
    # Acids / actives
    "bha", "aha", "pha", "lha",
    "salicylic acid", "acid salicylic",
    "azelaic acid", "acid azelaic",
    "glycolic acid", "acid glycolic",
    "lactic acid", "acid lactic",
    "mandelic acid",
    "niacinamide",
    "vitamin c", "vitamin b3", "vitamin b5",
    "hyaluronic acid", "acid hyaluronic",
    # Retinoids
    "retinol", "retinoid", "retinal", "retinaldehyde",
    "tretinoin", "retin-a",
    "adapalene", "differin",
    "tazarotene",
    # Antibacterials / spot treatments
    "benzoyl peroxide", "bpo",
    "tea tree", "tràm trà", "tram tra",
    "sulfur", "lưu huỳnh", "luu huynh",
    "zinc", "kẽm", "kem",
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
    "đông y", "dong y", "thuốc nam", "thuoc nam",
    "lá trầu không", "la trau khong",
    "nghệ", "nghe", "tinh nghệ", "tinh nghe",
    "dầu dừa", "dau dua", "coconut oil",
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
    "doxycycline", "minocycline", "tetracycline",
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
     r"trán|tran"
     r"|forehead"
     r"|vùng\s*trán|vung\s*tran"
     r"|giữa\s*trán|giua\s*tran"
     r"|trán\s*dầu"
     r"|trên\s*trán|tren\s*tran"
     r"|trán\s*đầu\s*(?:nhiều\s*)?mụn"
     r"|phần\s*trán"
     r")\b"),
    ("cheeks", r"\b(?:"
     r"má|ma\b"
     r"|hai\s*bên\s*má|2\s*bên\s*má"
     r"|cheek|cheeks"
     r"|vùng\s*má|bên\s*má"
     r"|gò\s*má|go\s*ma"
     r"|má\s*(?:phải|trái|hai\s*bên)"
     r"|mụn\s*(?:ở\s*)?má|mun\s*(?:o\s*)?ma"
     r"|da\s*má|vùng\s*gò\s*má"
     r"|hai\s*má"
     r")\b"),
    ("chin", r"\b(?:"
     r"cằm|cam\b"
     r"|chin\b"
     r"|dưới\s*cằm|duoi\s*cam"
     r"|vùng\s*cằm|vung\s*cam"
     r"|mụn\s*(?:ở\s*)?cằm|mun\s*(?:o\s*)?cam"
     r"|phần\s*cằm"
     r"|cằm\s*dưới"
     r"|chóp\s*cằm"
     r")\b"),
    ("jawline", r"\b(?:"
     r"quai\s*hàm|quai\s*ham"
     r"|jawline"
     r"|xương\s*hàm|xuong\s*ham"
     r"|hàm\s*dưới|ham\s*duoi"
     r"|hàm|ham\b"
     r"|dọc\s*theo\s*(?:quai\s*)?hàm"
     r"|mụn\s*(?:dọc\s*)?(?:theo\s*)?hàm"
     r"|viền\s*hàm|vien\s*ham"
     r"|hai\s*bên\s*hàm"
     r")\b"),
    ("nose", r"\b(?:"
     r"mũi|mui\b"
     r"|nose\b"
     r"|đầu\s*mũi|dau\s*mui"
     r"|cánh\s*mũi|canh\s*mui"
     r"|sống\s*mũi|song\s*mui"
     r"|vùng\s*mũi|cuong\s*mui"
     r"|trên\s*mũi"
     r"|mụn\s*(?:ở\s*)?mũi"
     r"|chóp\s*mũi"
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
     r"vai|vai\b"
     r"|bả\s*vai|ba\s*vai"
     r"|shoulder|shoulders"
     r"|vùng\s*vai"
     r"|hai\s*bên\s*vai"
     r"|mụn\s*(?:ở\s*)?vai"
     r"|phần\s*vai"
     r"|bờ\s*vai"
     r")\b"),
    ("neck", r"\b(?:"
     r"cổ(?!\s*(?:tay|chân|bình|chai|hủ|lọ))|co\b"
     r"|neck\b"
     r"|sau\s*gáy|sau\s*gay"
     r"|gáy|gay\b"
     r"|vùng\s*cổ|vung\s*co"
     r"|cổ\s*(?:trước|sau|bên)"
     r"|mụn\s*(?:ở\s*)?cổ|mun\s*(?:o\s*)?co"
     r"|phần\s*cổ"
     r"|da\s*cổ"
     r"|cổ\s*lan\s*xuống"
     r"|lan\s*(?:xuống\s*)?(?:cổ|vùng\s*cổ)"
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
     r"|mông|mong\b"
     r"|đùi|dui\b"
     r"|da\s*đầu|da\s*dau"
     r"|scalp\b"
     r"|tay\b|chân|chan\b"
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
     r"|mụn\s*nhỏ\s*li\s*ti|mụn\s*liti"
     r"|mụn\s*đầu\s*trắng\s*kín"
     r"|mụn\s*cám|mun\s*cam"
     r"|mụn\s*nhân|nhân\s*mụn|nhan\s*mun"
     r"|comedone"
     r"|mụn\s*hạt\s*kê|hat\s*ke"
     r"|nổi\s*hạt\s*li\s*ti|hat\s*nho\s*li\s*ti"
     r"|mụn\s*trắng\s*nhỏ|mun\s*trang\s*nho"
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

_ALLERGY_TERMS: list[tuple[str, str]] = [
    # Retinoids
    ("retinol",        r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp|khong\s*hop|không\s*dùng\s*được|khong\s*dung\s*duoc|bị\s*ứng)\s+(?:với\s*|with\s*)?retinol\b"),
    ("retinoid",       r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp|bị\s*ứng)\s+(?:với\s*)?retinoid\b"),
    ("tretinoin",      r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*chịu\s*được|bi\s*ung)\s+(?:với\s*)?tretinoin\b"),
    ("adapalene",      r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp)\s+(?:với\s*)?adapalene\b"),
    # Acids
    ("salicylic_acid", r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp|không\s*chịu)\s+(?:với\s*)?(?:salicylic|bha|acid\s*salicylic)\b"),
    ("benzoyl_peroxide", r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp)\s+(?:với\s*)?(?:benzoyl|bpo|benzoyl\s*peroxide)\b"),
    ("niacinamide",    r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung|không\s*hợp)\s+(?:với\s*)?niacinamide\b"),
    ("aha",            r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung)\s+(?:với\s*)?(?:aha|glycolic\s*acid|lactic\s*acid|acid\s*glycolic)\b"),
    ("tea_tree",       r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|kich\s*ung)\s+(?:với\s*)?(?:tea\s*tree|tràm\s*trà|tram\s*tra)\b"),
    # Antibiotics
    ("clindamycin",    r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|không\s*hợp)\s+(?:với\s*)?clindamycin\b"),
    ("doxycycline",    r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng)\s+(?:với\s*)?doxycycline\b"),
    ("penicillin",     r"\b(?:dị\s*ứng|di\s*ung)\s+(?:với\s*)?(?:penicillin|amoxicillin|kháng\s*sinh\s*nhóm\s*beta)\b"),
    ("erythromycin",   r"\b(?:dị\s*ứng|di\s*ung)\s+(?:với\s*)?erythromycin\b"),
    # Fragrance / preservatives
    ("fragrance",      r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng|không\s*hợp)\s+(?:với\s*)?(?:hương\s*liệu|huong\s*lieu|fragrance|mùi\s*thơm|nước\s*hoa)\b"),
    ("preservative",   r"\b(?:dị\s*ứng|di\s*ung|không\s*hợp)\s+(?:với\s*)?(?:chất\s*bảo\s*quản|chat\s*bao\s*quan|preservative|paraben)\b"),
    # Sunscreen agents
    ("sunscreen_chemical", r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng)\s+(?:với\s*)?(?:kem\s*chống\s*nắng\s*hóa\s*học|chemical\s*sunscreen|oxybenzone|avobenzone|kem\s*chống\s*nắng)\b"),
    # Natural / food-derived
    ("aloe_vera",      r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng)\s+(?:với\s*)?(?:nha\s*đam|nha\s*dam|aloe\s*vera|lô\s*hội|lo\s*hoi)\b"),
    ("centella",       r"\b(?:dị\s*ứng|di\s*ung|kích\s*ứng)\s+(?:với\s*)?(?:rau\s*má|rau\s*ma|centella|cica)\b"),
    # Generic / catch-all natural language
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
     r"ngăn\s*(?:ngừa\s*)?mụn|ngan\s*(?:ngua\s*)?mun"
     r"|phòng\s*(?:ngừa\s*)?mụn|phong\s*(?:ngua\s*)?mun"
     r"|không\s*(?:bị\s*)?tái\s*phát|khong\s*tai\s*phat"
     r"|không\s*bị\s*(?:mụn\s*)?lại|khong\s*bi\s*lai"
     r"|prevent\s*acne"
     r"|maintenance\b"
     r"|duy\s*trì\s*(?:da\s*)?sạch"
     r"|mụn\s*không\s*tái\s*phát"
     r"|ngăn\s*mụn\s*(?:mới\s*)?nổi"
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
     r")\b"),
    ("purulent_lesions", r"\b(?:"
     r"có\s*(?:cả\s*)?mủ|co\s*(?:ca\s*)?mu"
     r"|chảy\s*mủ|chay\s*mu"
     r"|mủ\s*(?:vàng|trắng|xanh)|mu\s*(?:vang|trang|xanh)"
     r"|chảy\s*(?:dịch|nước)|chay\s*(?:dich|nuoc)"
     r"|rỉ\s*dịch|ri\s*dich"
     r"|có\s*(?:cả\s*)?máu|co\s*(?:ca\s*)?mau"
     r"|chảy\s*máu|chay\s*mau"
     r"|ra\s*máu|ra\s*mau"
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
    ("skin_irritation", r"\b(?:"
     r"kích\s*ứng|kich\s*ung"
     r"|bong\s*tróc|bong\s*troc"
     r"|rát(?:\s*bỏng)?|rat\b"
     r"|nóng\s*rát|nong\s*rat"
     r"|châm\s*chích|cham\s*chich"
     r"|ngứa\s*(?:rát|nhiều)|ngua\s*(?:rat|nhieu)"
     r"|bỏng\s*rát|bong\s*rat"
     r"|da\s*(?:bị\s*)?bỏng"
     r"|đỏ\s*(?:bừng|rộp)|do\s*(?:bung|rop)"
     r"|phản\s*ứng\s*da"
     r"|dị\s*ứng\s*(?:sau\s*dùng|với)"
     r"|peeling\s*(?:quá|mạnh)"
     r")\b"),
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
     r"|\d+\s*(?:năm|tháng)\s*(?:rồi|nay)\s*(?:bị|mụn)"
     r"|mụn\s*mãn\s*tính"
     r"|bị\s*từ\s*(?:nhỏ|bé|lâu)"
     r")\b"),
    ("self_treatment_risk", r"\b(?:"
     r"(?:tự\s*)?nặn\s*mụn|(?:tu\s*)?nan\s*mun"
     r"|tự\s*nặn|tu\s*nan"
     r"|cậy\s*mụn|cay\s*mun"
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


def _extract_skin_type(text: str) -> _SkinType | None:
    for value, pattern in _SKIN_TYPES:
        if _has(pattern, text):
            return cast(_SkinType, value)
    return None


_Sex = Literal["male", "female", "other"]


def _extract_sex(text: str) -> _Sex | None:
    for value, pattern in _SEX_TERMS:
        if _has(pattern, text):
            return cast(_Sex, value)
    return None


def _extract_products(text: str) -> list[str]:
    lowered = text.lower()
    found = [term for term in _PRODUCT_TERMS if _has(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)]
    return _dedupe(found)


def _has_medication_use_context(lowered: str, term: str) -> bool:
    for match in re.finditer(re.escape(term), lowered):
        start = match.start()
        before = lowered[max(0, start - 80):start]   # mở rộng 60→80 để bắt "đang bôi X"
        after = lowered[match.end():match.end() + 40]
        window = before + term + after

        # ── Loại trừ: hỏi tư vấn, nghe nói, được khuyên ──
        if _has(r"(?:có\s*(?:nên|cần|thể)|nên|muốn|định|tự\s*ý|mua)\s+(?:uống|bôi|thoa|dùng|xài|sử\s*dụng)", before):
            continue
        if _has(r"\b(?:khuyên|gợi\s*ý|goi\s*y|nghe\s*nói|nghe\s*noi|trên\s*mạng|tren\s*mang|nghe\s*bảo)\b", before):
            continue
        if _has(r"\b(?:có\s*nên|có\s*cần|nên\s*dùng|nên\s*uống|có\s*thể\s*dùng)\b", before):
            continue

        # ── Xác nhận đang dùng: aspect marker trước thuốc ──
        if _has(r"\b(?:đang|dang|đã|da|mới|moi|vừa|vua|từng|tung|hiện\s*tại|hien\s*tai)\b", before):
            return True
        # ── Xác nhận: verb dùng thuốc trước hoặc sau ──
        if _has(r"\b(?:uống|uong|bôi|boi|thoa|dùng|dung|xài|xai|sử\s*dụng|su\s*dung|ngưng|ngung|dừng|dung)\b", before):
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
    return _dedupe(found)


_LesionType = Literal[
    "whitehead", "blackhead", "closed_comedone", "papule", "pustule",
    "nodule", "cyst", "hidden_acne", "scar",
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
    return _dedupe([value for value, pattern in _RED_FLAG_TERMS if _has(pattern, text)])


def _extract_allergies(text: str) -> list[str]:
    """Extract các chất user dị ứng / kích ứng."""
    found = [value for value, pattern in _ALLERGY_TERMS if _has(pattern, text)]
    return _dedupe(found)


def _extract_treatment_goals(text: str) -> list[str]:
    """Extract mục tiêu điều trị của user."""
    found = [value for value, pattern in _TREATMENT_GOAL_TERMS if _has(pattern, text)]
    return _dedupe(found)


_Inflammation = Literal["none", "mild", "moderate", "severe", "unknown"]


def _extract_inflammation(text: str, lesion_types: list[_LesionType]) -> _Inflammation | None:
    # Severe: mụn nặng / nhiễm trùng / máu / sốt / cụm từ mức độ nặng tường minh
    _severe_signal = (
        r"\b(?:"
        r"nặng(?:\s*lắm)?|severe\b"
        r"|mụn\s*(?:rất\s*)?to(?:\s*và\s*đau)?"
        r"|từng\s*cục(?:\s*cứng)?"
        r"|sưng\s*(?:to\s*)?(?:và\s*)?đau"
        r"|đau\s*(?:nhiều|lắm|rất|quá)"
        r"|rất\s*đau"
        r"|lan\s*rộng|khắp\s*(?:mặt|lưng|người)"
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
    if "nodule" in lesion_types and _has(r"\b(?:đau|dau|pain|painful|nhức)\b", text):
        return "severe"
    if _has(r"\b(?:có\s*(?:cả\s*)?máu|chảy\s*máu|ra\s*máu|máu\s*chảy|bleeding)\b", text):
        return "severe"
    if _has(r"\b(?:sốt|sot|fever|nhiễm\s*trùng|nhiem\s*trung|nóng\s*sốt|nong\s*sot|hạch\s*sưng)\b", text):
        return "severe"

    # Moderate: viêm đỏ có mủ / sưng nhẹ / tường minh "vừa"
    _moderate_signal = (
        r"\b(?:"
        r"viêm\s*(?:vừa|nhẹ\s*đến\s*vừa)|moderate\b"
        r"|sưng\s*đỏ(?!\s*(?:và\s*)?đau\s*nhiều)"
        r"|có\s*(?:mụn\s*)?viêm"
        r"|mụn\s*đỏ\s*(?:và\s*)?sưng"
        r")\b"
    )
    if _has(_moderate_signal, text) or any(t in lesion_types for t in ("papule", "pustule", "nodule")):
        return "moderate"

    # Mild: chỉ mụn không viêm hoặc viêm nhẹ tường minh
    _mild_signal = (
        r"\b(?:"
        r"nhẹ|mild\b"
        r"|mụn\s*(?:nhỏ|ít|vài\s*cái)"
        r"|ít\s*mụn"
        r"|mụn\s*ít\s*(?:thôi|thay)?"
        r"|không\s*(?:đau|sưng|viêm)"
        r"|mụn\s*không\s*(?:sưng|đau)"
        r")\b"
    )
    if _has(_mild_signal, text) or lesion_types:
        return "mild"
    return None


def _contains_positive(text: str, positive: str, negative: str) -> bool:
    if _has(negative, text):
        return False
    return _has(positive, text)


def normalize_chat_message(
    message: str,
    mode: str = "auto",
    clean_text: str | None = None,
) -> UserInput:
    """Convert a free-form chat message into the existing UserInput schema.

    description = raw_for_llm  (NFC + strip control chars, giữ emphasis gốc)
    Regex extraction dùng clean_text (full preprocess) — chỉ là local var.
    """
    # raw_for_llm: tối thiểu để LLM thấy ngôn ngữ tự nhiên đầy đủ
    raw_for_llm = _light_normalize(message)

    # clean_text: full preprocess chỉ dùng nội bộ cho regex.
    # Intake truyền sẵn để mỗi request chỉ preprocess một lần; legacy callers
    # không truyền thì normalizer tự tính để giữ tương thích.
    if clean_text is None:
        clean_text = preprocess_user_text(message)

    lesion_types = _extract_lesions(clean_text)
    distribution = _extract_distributions(clean_text)
    inflammation = _extract_inflammation(clean_text, lesion_types)
    red_flags = _extract_red_flags(clean_text)
    medications = _extract_medications(clean_text)
    products = _extract_products(clean_text)
    hormonal_factors = _extract_hormonal_factors(clean_text)
    allergies = _extract_allergies(clean_text)
    treatment_goals = _extract_treatment_goals(clean_text)

    context = UserContext(
        age=_extract_age(clean_text),
        sex=_extract_sex(clean_text),
        skin_type=_extract_skin_type(clean_text),
        is_pregnant=_contains_positive(
            clean_text,
            r"\b(?:mang thai|có thai|co thai|đang bầu|dang bau|pregnant)\b",
            r"\b(?:không|khong|ko|k)\s+(?:mang thai|có thai|co thai|bầu|bau)\b",
        ),
        is_breastfeeding=_contains_positive(
            clean_text,
            r"\b(?:cho con bú|cho con bu|breastfeeding)\b",
            r"\b(?:không|khong|ko|k)\s+(?:cho con bú|cho con bu|breastfeeding)\b",
        ),
        current_products=products,
        medications=medications,
        duration_weeks=_extract_duration_weeks(clean_text),
        allergies=allergies,
    )

    clinical = AcneClinicalInput(
        lesion_types=lesion_types,
        lesion_distribution=distribution,
        inflammation_level=inflammation,
        scarring_signs=_dedupe([value for value, pattern in _RED_FLAG_TERMS
                                if value in ("scar", "pih") and _has(pattern, clean_text)]),
        medication_history=medications,
        skincare_products=products,
        red_flags_input=red_flags,
        treatment_goals=treatment_goals,
        hormonal_factors=hormonal_factors,
    ) if lesion_types or distribution or inflammation or red_flags or hormonal_factors or medications or products or treatment_goals or allergies else None

    safe_mode = mode if mode in {"hybrid", "llm_only"} else "hybrid"
    return UserInput(description=raw_for_llm, context=context, clinical=clinical, mode=safe_mode)
