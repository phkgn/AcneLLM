import re
import unicodedata

# ── RAG cleaning (light) ──────────────────────────────────────────────────────

# PDF tiếng Việt đời cũ (font VN-Times, TCVN3) map ƣ/Ƣ = U+01A3/U+01A2 — chữ "OI"
# của ngôn ngữ châu Phi — thay cho ư/Ư, và dùng vùng Private Use cho bullet.
# NFC KHÔNG sửa được: đây là các chữ cái khác nhau, không tương đương chuẩn tắc.
# Không sửa thì "người" thành "ngƣời" → BM25 không khớp, embedder mã hoá như từ lạ.
PDF_ARTIFACTS = str.maketrans({
    "\u01a3": "\u01b0", "\u01a2": "\u01af",   # LATIN LETTER OI → U WITH HORN
    "\u0131": "i",                          # i không chấm
    # Vùng Private Use = mã 0x20–0xFF của font Symbol/Wingdings. Chữ Latin thường
    # trong Symbol ánh xạ sang Hy Lạp: a→α, b→β, k→κ (TNF-α, IL-1β, NF-κB).
    "\uf020": " ", "\uf02d": "-", "\uf0b7": "•",   # space · gạch · bullet
    "\uf076": "•", "\uf0d8": "•", "\uf0e0": "→",   # bullet · bullet · mũi tên
    "\uf061": "α", "\uf062": "β", "\uf06b": "κ",   # Symbol a/b/k → Hy Lạp
    "\u00a0": " ", "\u2009": " ", "\u2005": " ",  # nbsp / thin / four-per-em space
    "\u00ad": "",                           # soft hyphen — cắt từ vô hình
})

BOILERPLATE_PATTERNS = [
    r"(?i)đọc thêm[:\s].+?(\n|$)",
    r"(?i)xem thêm[:\s].+?(\n|$)",
    r"(?i)nguồn[:\s]https?://\S+",
    r"(?i)liên hệ.+?\d{9,11}",
    r"(?i)đăng ký.+?(nhận tin|tư vấn)",
    r"\n{3,}",
]


def clean_vi_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(PDF_ARTIFACTS)
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Fine-tuning cleaning (aggressive) ────────────────────────────────────────
# Removes contact info, doctor signatures, marketing, navigation noise
# that the model should never memorize.

_FT_PATTERNS = [
    # Contact info
    (r"(?im)^(địa chỉ|cơ sở\s*\d*|chi nhánh)\s*[:：]\s*.+$", ""),
    (r"(?im)^(hotline|điện thoại|số điện thoại|tel|phone|zalo)\s*[:：]\s*[\d\s\-\.\(\)]+$", ""),
    (r"(?i)(hotline|điện thoại|liên hệ ngay)[^\n]{0,60}\d{9,11}", ""),
    # Social / marketing
    (r"(?im)^(fanpage|facebook|instagram|tiktok|youtube|zalo page)\s*[:：]\s*.+$", ""),
    (r"(?i)(theo dõi|follow us|like fanpage|subscribe).{0,80}", ""),
    (r"(?i)(đặt lịch|book lịch|book ngay|đặt hẹn|đăng ký khám).{0,100}", ""),
    (r"(?i)(khuyến mãi|ưu đãi|giảm giá|voucher|mã giảm giá).{0,80}", ""),
    # Doctor / author signatures
    (r"(?im)^(bs\.|bác sĩ|ths\.bs\.|pgs\.ts|gs\.ts|ths\.|ts\.)\s+[A-ZÀÁẢÃẠĂẶÂẦẤ][^\n]{3,50}$", ""),
    (r"(?im)^(tác giả|biên soạn|kiểm duyệt|reviewed by)\s*[:：]\s*.+$", ""),
    # Navigation / breadcrumbs
    (r"(?i)(trang chủ\s*[>»/]\s*).+?(?=\n|$)", ""),
    (r"(?i)(chia sẻ bài viết|share bài|in bài viết|print article).{0,60}", ""),
    (r"(?i)(bài viết liên quan|xem thêm bài|có thể bạn quan tâm).{0,200}", ""),
    # Copyright / disclaimer footers
    (r"(?im)^©.+$", ""),
    (r"(?i)(bản quyền thuộc|all rights reserved|copyright).{0,80}", ""),
    (r"(?i)(thông tin trong bài (viết|này) chỉ mang tính (chất )?tham khảo).{0,200}", ""),
    # Raw URLs
    (r"https?://[^\s\)\"']+", ""),
    # Email addresses
    (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", ""),
    # Standalone phone numbers (10–11 digits, various formats)
    (r"\b(0|\+84)\s?[3-9]\d[\s.\-]?\d{3}[\s.\-]?\d{4}\b", ""),
    # "Vinmec / BV XYZ" institutional marketing tail
    (r"(?i)(hệ thống y tế|bệnh viện đa khoa|phòng khám|trung tâm y tế)\s+\w+.{0,120}$", ""),
]

# Compile once
_FT_COMPILED = [(re.compile(pat), repl) for pat, repl in _FT_PATTERNS]


def clean_for_finetuning(text: str) -> str:
    """Aggressive cleaning for fine-tuning dataset — removes all PII, contact
    info, marketing noise, and navigation artifacts that the model must not learn."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(PDF_ARTIFACTS)
    text = re.sub(r"[\u200b-\u200f\ufeff\xa0]", " ", text)

    for pattern, repl in _FT_COMPILED:
        text = pattern.sub(repl, text)

    # Collapse whitespace artifacts left by removals
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Drop lines that became too short (< 4 chars) after cleaning — likely nav remnants
    lines = [ln for ln in text.splitlines() if len(ln.strip()) >= 4 or ln.strip() == ""]
    text = "\n".join(lines)
    return text.strip()
