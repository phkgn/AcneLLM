"""Quality filter for crawled documents — language-aware.

Hệ thống 2 tầng TÁCH BIỆT theo ngôn ngữ (VI / EN):
- STRONG: 1 từ là đủ pass
- MEDIUM: cần ≥ MIN_MEDIUM_HITS_VI (1) hoặc MIN_MEDIUM_HITS_EN (2)

Sửa bias EN:
1. Tách STRONG/MEDIUM riêng cho VI và EN
2. Ngưỡng MEDIUM thấp hơn cho VI (1 hit thay vì 2)
3. Vùng scan rộng hơn cho VI (5000 chars thay vì 3000 — VI viết kể chuyện)
4. Mở rộng từ vựng VI thêm colloquial terms còn thiếu
5. score_quality boost VI ×1.3 vì keyword list nhỏ hơn EN
"""
try:
    from langdetect import detect as _detect_lang
except Exception:
    _detect_lang = None


def detect_lang(text: str) -> str | None:
    if _detect_lang is None:
        return None
    try:
        return _detect_lang(text[:500])
    except Exception:
        return None


# =============================================================================
# acne_keywords.py — Từ khóa lọc bài viết cho hệ thống tư vấn mụn
# Phạm vi: Mụn đầu trắng · Mụn đầu đen · Mụn viêm · Tư vấn loại da mụn
# =============================================================================

# ─── Ngưỡng theo ngôn ngữ ────────────────────────────────────────────────────
MIN_MEDIUM_HITS_VI = 2   # VI duyệt 2 medium words để tránh nhiễu báo tổng hợp
MIN_MEDIUM_HITS_EN = 2   # EN y khoa → giữ nguyên
CHECK_ZONE_VI = 8000     # VI để keyword muộn trong bài → scan nhiều hơn
CHECK_ZONE_EN = 3000     # EN front-load keyword


# ─── STRONG VI — 1 từ là đủ pass ─────────────────────────────────────────────
# Ghi chú thay đổi:
#   ✂ XÓA "mụn cóc"   → wart (HPV), không phải acne
STRONG_KEYWORDS_VI = [
    # --- Cốt lõi ---
    "trứng cá", "da liễu",

    # --- Ba loại mụn trọng tâm ---
    "mụn đầu đen",          # blackhead / open comedone
    "mụn đầu trắng",        # whitehead / closed comedone
    "mụn viêm",             # inflammatory acne (papule, pustule, nodule, cyst)

    # --- Phân loại mụn mở rộng (vẫn trong chuyên môn) ---
    "mụn trứng cá",         # acne vulgaris tổng quát
    "mụn mủ",               # pustule
    "mụn nội tiết",         # hormonal acne
    "mụn bọc",              # nodulo-cystic
    "mụn cám",              # comedonal acne / microcomedone nhẹ
    "mụn ẩn",               # closed comedone ẩn dưới da
    "mụn do stress",        # stress-induced acne
    "mụn tuổi dậy thì",     # adolescent acne
    "mụn hormonal",         # hormonal acne (gộp với nội tiết nhưng hay xuất hiện độc lập)
    "viêm nang lông",       # folliculitis — thường nhầm / đi cùng acne
    "nang bã nhờn",         # sebaceous cyst / milia liên quan

    # --- Triệu chứng & hậu quả mụn ---
    "sẹo mụn",
    "thâm mụn",
    "sẹo rỗ", "sẹo lõm",
    "nhân mụn", "nặn mụn", "bấm mụn", "đẩy nhân mụn",
    "tăng sắc tố sau viêm",   # PIH tiếng Việt
    "đỏ sau mụn",             # PIE tiếng Việt

    # --- Điều trị / can thiệp ---
    "điều trị mụn", "trị mụn", "xóa mụn",
    "kem trị mụn", "thuốc trị mụn", "gel trị mụn",

    # --- Hoạt chất điều trị mụn (tên quốc tế dùng trong bài VI) ---
    "isotretinoin", "tretinoin", "adapalene", "tazarotene",
    "benzoyl peroxide", "salicylic acid", "azelaic acid",
    "retinoid", "retinol",
]


# ─── STRONG EN — 1 từ là đủ pass ─────────────────────────────────────────────
# Ghi chú thay đổi:
#   ✂ XÓA "acne rosacea"        → rosacea là bệnh da riêng biệt, không phải acne vulgaris
#   ✂ XÓA "perioral dermatitis" → viêm da quanh miệng, không phải acne
#   ✂ XÓA "integumentary", "anatomy", "skin layer", "epidermis", "dermis"
#          → giải phẫu học tổng quát; quá rộng so với phạm vi tư vấn mụn
STRONG_KEYWORDS_EN = [
    # --- Core ---
    "acne", "acne vulgaris",

    # --- Lesion types (ba loại trọng tâm + mở rộng) ---
    "blackhead",            # open comedone
    "whitehead",            # closed comedone
    "comedone", "comedones",
    "microcomedone",        # tiền thân của mọi loại mụn
    "papule",               # mụn sẩn (inflammatory)
    "pustule",              # mụn mủ (inflammatory)
    "nodule",               # mụn nốt (severe inflammatory)
    "cystic acne",          # mụn bọc nang
    "acne lesion", "acneiform",

    # --- Post-acne sequelae ---
    "post-inflammatory hyperpigmentation", "pih",
    "post-inflammatory erythema", "pie",
    "acne scar", "atrophic scar", "hypertrophic scar", "keloid scar",
    "ice pick scar", "boxcar scar", "rolling scar",

    # --- Microbiology ---
    "cutibacterium acnes", "c. acnes",
    "propionibacterium acnes", "p. acnes",
    "sebaceous gland", "pilosebaceous",

    # --- Treatment / procedures ---
    "isotretinoin", "tretinoin", "adapalene", "tazarotene",
    "accutane", "roaccutane",
    "benzoyl peroxide",
    "salicylic acid", "azelaic acid",
    "differin", "retin-a",
    "intralesional steroid",
    "chemical peel for acne",

    # --- Dermatology context ---
    "folliculitis",         # sát với acne, thường đi cùng
]


# ─── MEDIUM VI — cần ≥ MIN_MEDIUM_HITS_VI ────────────────────────────────────
# Ghi chú thay đổi:
#   ✂ XÓA "skincare"        → English lẫn, quá rộng
#   ✂ XÓA "vitamin c serum" → brightening, không đặc thù mụn
#   ✨ THÊM loạt từ mô tả comedone & inflammatory để phủ đủ 3 nhóm mụn
MEDIUM_KEYWORDS_VI = [
    # --- Loại da liên quan mụn ---
    "da dầu", "da nhờn", "da hỗn hợp", "da nhạy cảm",
    "da mụn",               # colloquial, rất phổ biến

    # --- Sinh lý da & lỗ chân lông ---
    "bã nhờn", "tiết bã nhờn", "tăng tiết bã nhờn",
    "tế bào chết",
    "lỗ chân lông", "bít lỗ chân lông", "tắc nghẽn lỗ chân lông",
    "nang lông",
    "vùng da", "da mặt",

    # --- Mụn không viêm (comedonal) ---
    "mụn không viêm",
    "mụn có nhân",
    "comedone",             # dùng cả trong bài tiếng Việt chuyên sâu
    "nhân mở", "nhân đóng",
    "bít tắc", "bí da",

    # --- Mụn viêm & triệu chứng ---
    "viêm đỏ", "sưng tấy", "tấy đỏ",
    "kích ứng",
    "mụn tái phát", "mụn theo chu kỳ", "mụn mới mọc",
    "mụn ẩn", "đẩy mụn",

    # --- Hệ quả & bề mặt da ---
    "tróc da", "đỏ da", "da bong tróc",
    "rụng da",              # desquamation khi dùng retinoid/BHA
    "da căng bóng",

    # --- Chăm sóc da mụn ---
    "rửa mặt", "sữa rửa mặt", "tẩy trang",
    "làm sạch da",
    "dưỡng da", "chăm sóc da",
    "se khít lỗ chân lông",

    # --- Hoạt chất trị mụn ---
    "kháng sinh bôi", "kháng sinh uống",
    "retinoid", "retinol",
    "niacinamide",          # kiểm soát bã nhờn, giảm PIH
    "bha",                  # beta-hydroxy acid — salicylic acid
    "aha",                  # alpha-hydroxy acid — glycolic, lactic
    "benzoyl peroxide",     # lặp lại từ STRONG để tăng recall medium

    # --- Chuyên môn điều trị ---
    "điều trị mụn", "nguyên nhân mụn",
    "liệu trình da liễu",
    "thói quen chăm sóc da",

    # --- Da liễu & Kháng sinh phổ rộng ---
    "da liễu", "bác sĩ da liễu", "chuyên khoa da liễu",
    "bệnh viện da liễu", "phòng khám da liễu",
    "sẹo lồi",
    "spironolactone", "doxycycline", "minocycline", "clindamycin",
]


# ─── MEDIUM EN — cần ≥ MIN_MEDIUM_HITS_EN ────────────────────────────────────
# Ghi chú thay đổi:
#   ✂ XÓA "dry skin"          → không phải skin type acne-prone điển hình
#   ✂ XÓA "hyaluronic acid"   → hydration ingredient, không đặc thù trị mụn
#   ✂ XÓA "tranexamic acid"   → dùng cho melasma/pigmentation, lạc chủ đề
#   ✂ XÓA "centella asiatica" → wound healing tổng quát, không đặc thù acne
#   ✨ THÊM các từ phân loại comedone & inflammatory rõ hơn
MEDIUM_KEYWORDS_EN = [
    # --- Core colloquial ---
    "acne", "pimple", "breakout", "blemish", "spot", "zit",

    # --- Comedone-specific (mụn đầu đen / đầu trắng) ---
    "open comedone",
    "closed comedone",
    "clogged pores", "blocked pores",
    "pore congestion",

    # --- Inflammatory acne ---
    "inflammatory", "inflammation", "anti-inflammatory",
    "inflamed pimple", "painful pimple",

    # --- Skin types relevant to acne ---
    "oily skin", "combination skin", "acne-prone skin",
    "sensitive skin",       # giữ: dùng khi chọn sản phẩm trị mụn

    # --- Physiology ---
    "sebum", "excess sebum", "skin barrier",
    "hormonal", "hormones", "androgens",

    # --- Clinical / care ---
    "dermatologist", "dermatology", "skin condition",
    "skincare routine",
    "moisturizer", "cleanser",

    # --- Broad antibiotics / meds ---
    "spironolactone", "doxycycline", "minocycline",
    "clindamycin", "erythromycin",

    # --- Acne-specific ingredients ---
    "glycolic acid",        # AHA cho acne
    "lactic acid",          # AHA nhẹ hơn
    "mandelic acid",        # AHA cho da nhạy cảm bị mụn
    "niacinamide",          # kiểm soát bã nhờn
    "tea tree",             # kháng khuẩn tự nhiên
    "zinc",                 # kháng viêm / trị mụn
    "sulfur mask",          # mặt nạ lưu huỳnh
    "clay mask",            # hút bã nhờn
    "bha", "aha",
]


# =============================================================================
# Backward-compatible exports
# =============================================================================
STRONG_KEYWORDS = tuple(dict.fromkeys(STRONG_KEYWORDS_VI + STRONG_KEYWORDS_EN))
MEDIUM_KEYWORDS = tuple(dict.fromkeys(MEDIUM_KEYWORDS_VI + MEDIUM_KEYWORDS_EN))

# Broad words removed in previous revisions (retained for audit trail)
_REMOVED_BROAD = {
    "test", "help", "clear", "review", "routine",
    "gel", "cream", "mask", "toner", "serum",
    "healing", "trigger", "advice", "tips", "hack",
    "recommendation",
}

def _count_keywords(lower_text: str, keywords: list[str]) -> tuple[int, list[str]]:
    found = [k for k in keywords if k in lower_text]
    return len(found), found


def passes_quality(text: str, title: str, lang: str = "vi") -> tuple[bool, str]:
    if not text or not title:
        return False, "empty"
    tlen = len(text)
    if tlen < 300:
        return False, f"too_short({tlen})"
    if tlen > 80_000:
        return False, f"too_long({tlen})"
    if len(title.strip()) < 5:
        return False, "title_too_short"

    # noise ratio
    non_alpha = sum(
        1 for c in text
        if not (c.isalnum() or c.isspace() or c in
                ".,;:!?()-—'\"àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệ"
                "ìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
                "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌ"
                "ÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ")
    )
    if tlen > 0 and non_alpha / tlen > 0.45:
        return False, "too_noisy"

    # Chọn keyword list + ngưỡng theo ngôn ngữ
    is_vi = (lang == "vi")
    strong_kws = STRONG_KEYWORDS_VI if is_vi else STRONG_KEYWORDS_EN
    medium_kws = MEDIUM_KEYWORDS_VI if is_vi else MEDIUM_KEYWORDS_EN
    min_hits = MIN_MEDIUM_HITS_VI if is_vi else MIN_MEDIUM_HITS_EN
    zone_len = CHECK_ZONE_VI if is_vi else CHECK_ZONE_EN

    check_zone = (title + " " + text[:zone_len]).lower()

    # Tầng 1: 1 STRONG keyword là đủ
    n_strong, found_strong = _count_keywords(check_zone, strong_kws)
    if n_strong >= 1:
        return True, f"strong:{found_strong[0]}"

    # Tầng 2: cần ≥ min_hits MEDIUM keywords
    n_medium, found_medium = _count_keywords(check_zone, medium_kws)
    if n_medium >= min_hits:
        return True, f"medium:{n_medium}hits"

    return False, f"no_keyword(strong=0,medium={n_medium}<{min_hits})"


def score_quality(text: str, lang: str = "vi") -> float:
    """Heuristic score 0–1. Boost VI ×1.3 để bù keyword list nhỏ hơn EN."""
    l_score = min(len(text) / 6000.0, 1.0)
    p_score = min(text.count("\n\n") / 20.0, 1.0)

    lower = text[:CHECK_ZONE_VI if lang == "vi" else CHECK_ZONE_EN].lower()
    strong_kws = STRONG_KEYWORDS_VI if lang == "vi" else STRONG_KEYWORDS_EN
    medium_kws = MEDIUM_KEYWORDS_VI if lang == "vi" else MEDIUM_KEYWORDS_EN

    n_strong, _ = _count_keywords(lower, strong_kws)
    n_medium, _ = _count_keywords(lower, medium_kws)
    kw_score = min((n_strong * 3 + n_medium) / 15.0, 1.0)

    # Boost VI để compensate keyword list nhỏ hơn
    if lang == "vi":
        kw_score = min(kw_score * 1.3, 1.0)

    return round(0.4 * l_score + 0.2 * p_score + 0.4 * kw_score, 3)
