"""Tầng confidence bọc quanh các extractor rule-based trong normalizer.

LEGACY: live fallback when ``EXTRACTOR_MODE=rule`` or the LLM extractor fails.

THIẾT KẾ 'bọc không phá vỡ':
- KHÔNG sửa normalizer.py. normalize_chat_message() và UserInput giữ nguyên 100%.
- Module này gọi LẠI chính các extractor cũ (tầng pattern), bổ sung tầng fuzzy
  cho field từ vựng, và tính FieldResult (value + confidence + method).
- Trả về map field -> FieldResult qua hàm song song extract_with_confidence().
  completeness/intent_router đọc map này để degrade an toàn khi confidence thấp.
- Thuần rule + fuzzy, KHÔNG gọi LLM.

Confidence (heuristic khởi điểm; golden set sẽ tinh chỉnh):
  pattern (regex cũ khớp)         → 0.85, ± điều chỉnh ngữ cảnh
  fuzzy   (canonical khớp mờ)     → = similarity
  fallback(suy luận bảo thủ)      → 0.45
  none                            → 0.0
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field as dc_field
import re

from ..schemas.extraction import FieldResult, ListFieldResult
from ..utils.fuzzy_match import find_in_text
from . import normalizer as nz
from .preprocess import prepare_user_text, strip_accents


# ---------------------------------------------------------------------------
# Lexicon canonical cho tầng fuzzy (task #4 — KHÔNG xoá regex cũ, chỉ bổ sung).
# Khái niệm mới từ nay = thêm 1 dòng canonical, fuzzy lo biến thể/sai chính tả.
# ---------------------------------------------------------------------------
# Chỉ đưa canonical ĐỦ DÀI vào tầng fuzzy. Token ngắn (spf, toner, kem, zinc,
# peel, bha...) để regex pattern lo — fuzzy với chúng khớp bừa từ tiếng Việt
# (nguyên nhân products precision thấp: fp cao). Ngưỡng 7 ký tự loại hết nhóm này.
_FUZZY_MIN_LEN = 7
PRODUCT_CANONICALS: tuple[str, ...] = tuple(dict.fromkeys(
    t.lower() for t in nz._PRODUCT_TERMS if len(t) >= _FUZZY_MIN_LEN
))
MEDICATION_CANONICALS: tuple[str, ...] = tuple(dict.fromkeys(
    t.lower() for t in nz._MEDICATION_TERMS if len(t) >= _FUZZY_MIN_LEN
))
_ALLERGY_ALIAS_TO_LABEL: dict[str, str] = {}
for _label, _pattern in nz._ALLERGY_TERMS:
    if _label == "unknown":
        continue
    _aliases = {
        _label,
        _label.replace("_", " "),
    }
    if _label == "salicylic_acid":
        _aliases.update({"salicylic acid", "acid salicylic"})
    elif _label == "benzoyl_peroxide":
        _aliases.update({"benzoyl peroxide"})
    elif _label == "sunscreen_chemical":
        _aliases.update({"chemical sunscreen", "oxybenzone", "avobenzone"})
    elif _label == "tea_tree":
        _aliases.update({"tea tree", "tram tra"})
    elif _label == "aloe_vera":
        _aliases.update({"aloe vera", "nha dam"})
    for _alias in _aliases:
        _alias_key = strip_accents(_alias).lower().strip()
        if len(_alias_key) >= _FUZZY_MIN_LEN:
            _ALLERGY_ALIAS_TO_LABEL[_alias_key] = _label
ALLERGY_CANONICALS: tuple[str, ...] = tuple(_ALLERGY_ALIAS_TO_LABEL)

# Review floor RIÊNG cho field từ vựng: cao hơn ngưỡng chung để fuzzy CHỈ bắt
# sai chính tả thật (niacinamid→niacinamide ~0.95), không khớp lỏng.
_VOCAB_FUZZY_REVIEW = 0.82


# Điều chỉnh ngữ cảnh (cộng vào confidence base).
_NEGATION_RE = re.compile(r"\b(?:không|khong|ko|chẳng|chang|chưa|chua)\b", re.I)
_QUESTION_RE = nz._SKIN_TYPE_QUESTION_RE  # tái dùng marker câu hỏi/so sánh đã có
_PRONOUN_RE = re.compile(r"\b(?:tôi|toi|mình|minh|em|cháu|chau|con)\b", re.I)


_VITAMIN_LETTER_RE = re.compile(r"vitamin\s+([a-z])\b", re.I)


def _vitamin_letter_ok(canonical: str, text_no_accent: str) -> bool:
    """Chặn fuzzy gộp nhầm 'vitamin k' -> 'vitamin c'.

    Nếu canonical là 'vitamin <chữ cái>' thì bắt buộc đúng chữ cái đó phải
    xuất hiện trong text; fuzzy vẫn tự do cho các term khác (lỗi chính tả thật).
    """
    m = _VITAMIN_LETTER_RE.fullmatch(canonical.strip())
    if not m:
        return True
    return f"vitamin {m.group(1).lower()}" in text_no_accent.lower()


def _context_adjust(text: str, span_hint: str = "") -> float:
    """Điều chỉnh confidence theo ngữ cảnh quanh match.

    − câu hỏi/so sánh (user hỏi, không khai báo)
    + có pronoun chủ ngữ (user tự khai)
    """
    adj = 0.0
    if _QUESTION_RE.search(text):
        adj -= 0.10
    if _PRONOUN_RE.search(text):
        adj += 0.05
    return adj


@dataclass
class ExtractionConfidence:
    """Map field -> FieldResult, kênh phụ cho completeness/router."""

    skin_type: FieldResult[str] = dc_field(default_factory=FieldResult.none)
    sex: FieldResult[str] = dc_field(default_factory=FieldResult.none)
    age: FieldResult[int] = dc_field(default_factory=FieldResult.none)
    duration_weeks: FieldResult[int] = dc_field(default_factory=FieldResult.none)
    is_pregnant: FieldResult[bool] = dc_field(default_factory=FieldResult.none)
    is_breastfeeding: FieldResult[bool] = dc_field(default_factory=FieldResult.none)
    inflammation: FieldResult[str] = dc_field(default_factory=FieldResult.none)
    lesion_types: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    distribution: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    products: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    medications: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    allergies: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    scarring_signs: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    hormonal_factors: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    treatment_goals: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)
    red_flags: ListFieldResult[str] = dc_field(default_factory=ListFieldResult.empty)

    def field(self, name: str) -> FieldResult | ListFieldResult:
        return getattr(self, name)


def _scalar(value, text: str, *, fallback_methods: tuple[str, ...] = ()) -> FieldResult:
    """Bọc một extractor scalar thành FieldResult với method=pattern + điều chỉnh."""
    if value is None:
        return FieldResult.none()
    adj = _context_adjust(text)
    return FieldResult.make(value, "pattern", evidence=text[:60], adjust=adj)


def _list_from_pattern(values: list[str], text: str) -> ListFieldResult:
    """Các item khớp bằng regex cũ → method=pattern."""
    adj = _context_adjust(text)
    items = tuple(
        FieldResult.make(v, "pattern", adjust=adj) for v in values
    )
    return ListFieldResult(items=items)


def _list_vocab(
    pattern_values: list[str],
    text_no_accent: str,
    canonicals: tuple[str, ...],
    *,
    accept: float,
    review: float,
    term_map: dict[str, str] | None = None,
    fuzzy_context_filter: "Callable[[str], bool] | None" = None,
) -> ListFieldResult:
    """Field từ vựng: hợp nhất regex (pattern, conf cao) + fuzzy (conf=sim).

    - Item đã khớp regex cũ → giữ conf pattern (ưu tiên).
    - Item mới chỉ fuzzy thấy → thêm với conf = similarity.
    - term_map: nếu có, dùng để canonical-hóa raw term → gold label (cho products).
    - fuzzy_context_filter: nếu có, mỗi fuzzy hit phải pass(raw) mới được nhận
      (vd: medications cần ngữ cảnh đang-dùng, tránh bắt tên thuốc trong câu hỏi).
    """
    items: list[FieldResult[str]] = []
    seen: set[str] = set()

    for v in pattern_values:
        mapped = term_map.get(v, v) if term_map else v
        key = strip_accents(mapped).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(FieldResult.make(mapped, "pattern"))

    for hit in find_in_text(text_no_accent, canonicals, accept=accept, review=review):
        raw = hit.canonical
        mapped = term_map.get(raw, raw) if term_map else raw
        key = strip_accents(mapped).lower()
        if key in seen:
            continue
        if fuzzy_context_filter is not None and not fuzzy_context_filter(raw):
            continue
        seen.add(key)
        items.append(FieldResult.make(mapped, "fuzzy", confidence=hit.similarity))

    return ListFieldResult(items=tuple(items))


def _list_vocab_aliases(
    pattern_values: list[str],
    text_no_accent: str,
    alias_to_label: dict[str, str],
    *,
    accept: float,
    review: float,
) -> ListFieldResult:
    """Like _list_vocab, but fuzzy matches aliases and emits schema labels."""
    items: list[FieldResult[str]] = []
    seen: set[str] = set()

    for v in pattern_values:
        key = strip_accents(v).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(FieldResult.make(v, "pattern"))

    aliases = tuple(alias_to_label)
    for hit in find_in_text(text_no_accent, aliases, accept=accept, review=review):
        label = alias_to_label.get(hit.canonical, hit.canonical)
        key = strip_accents(label).lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(FieldResult.make(label, "fuzzy", confidence=hit.similarity))

    return ListFieldResult(items=tuple(items))


def _bool_from_patterns(
    clean_text: str,
    clean_text_no_accent: str,
    *,
    positive: tuple[str, str],
    negative: tuple[str, str],
) -> FieldResult[bool]:
    """Return True/False only when the user explicitly mentions the boolean field."""
    pos_re, pos_no_accent_re = positive
    neg_re, neg_no_accent_re = negative
    if re.search(neg_re, clean_text, re.I) or re.search(neg_no_accent_re, clean_text_no_accent, re.I):
        return FieldResult.make(False, "pattern", confidence=0.90, evidence=clean_text[:60])
    if re.search(pos_re, clean_text, re.I) or re.search(pos_no_accent_re, clean_text_no_accent, re.I):
        return FieldResult.make(True, "pattern", confidence=0.90, evidence=clean_text[:60])
    return FieldResult.none()


def _has_allergy_context(clean_text: str, clean_text_no_accent: str) -> bool:
    return bool(
        re.search(nz._ALLERGY_REACTION_VERBS, clean_text, re.I)
        or re.search(nz._ALLERGY_REACTION_VERBS, clean_text_no_accent, re.I)
        or re.search(r"\ballerg(?:y|ic)\b", clean_text_no_accent, re.I)
    )


def extract_with_confidence(
    message: str,
    *,
    fuzzy_accept: float = 0.86,
    fuzzy_review: float = 0.72,
    clean_text: str | None = None,
    clean_text_no_accent: str | None = None,
) -> ExtractionConfidence:
    """Trả về confidence per-field. KHÔNG ráp UserInput (việc đó normalizer lo).

    Gọi lại chính extractor cũ → đảm bảo giá trị nhất quán với normalize_chat_message.
    """
    if clean_text is None:
        prepared = prepare_user_text(message)
        clean_text = prepared.clean_text
        clean_text_no_accent = prepared.clean_text_no_accent
    elif clean_text_no_accent is None:
        clean_text_no_accent = strip_accents(clean_text)

    texts = nz._texts_for_extraction(clean_text, clean_text_no_accent)

    # --- scalar ---
    skin_type = nz._extract_skin_type_from_texts(clean_text, clean_text_no_accent)
    sex = nz._first_extracted(texts, nz._extract_sex)
    age = nz._first_extracted(texts, nz._extract_age)
    duration = nz._first_extracted(texts, nz._extract_duration_weeks)
    is_pregnant = _bool_from_patterns(
        clean_text,
        clean_text_no_accent,
        positive=(
            r"\b(?:mang thai|có thai|co thai|đang bầu|dang bau|pregnant)\b",
            r"\b(?:mang thai|co thai|dang bau|pregnant)\b",
        ),
        negative=(
            r"\b(?:không|khong|ko|k)\s+(?:mang thai|có thai|co thai|bầu|bau)\b",
            r"\b(?:khong|ko|k)\s+(?:mang thai|co thai|bau)\b",
        ),
    )
    is_breastfeeding = _bool_from_patterns(
        clean_text,
        clean_text_no_accent,
        positive=(
            r"\b(?:cho con bú|cho con bu|breastfeeding)\b",
            r"\b(?:cho con bu|breastfeeding)\b",
        ),
        negative=(
            r"\b(?:không|khong|ko|k)\s+(?:cho con bú|cho con bu|breastfeeding)\b",
            r"\b(?:khong|ko|k)\s+(?:cho con bu|breastfeeding)\b",
        ),
    )

    # --- list (phân loại) ---
    lesion_vals = nz._merge_extracted(texts, nz._extract_lesions)
    dist_vals = nz._merge_extracted(texts, nz._extract_distributions)
    allergy_vals = nz._merge_extracted(texts, nz._extract_allergies)
    red_flag_vals = nz._merge_extracted(texts, nz._extract_red_flags)
    scarring_vals = nz._extract_scarring_signs_from_extracted(lesion_vals, red_flag_vals)
    hormonal_vals = nz._merge_extracted(texts, nz._extract_hormonal_factors)
    treatment_goal_vals = nz._merge_extracted(texts, nz._extract_treatment_goals)

    # --- inflammation (suy luận → evidence-count) ---
    infl = nz._strongest_inflammation(
        [nz._extract_inflammation(t, lesion_vals) for t in texts]
    )
    infl_result = _inflammation_confidence(infl, clean_text, lesion_vals)

    # --- field từ vựng (pattern + fuzzy) ---
    product_vals = nz._dedupe_accent_insensitive(nz._merge_extracted(texts, nz._extract_products))
    medication_vals = nz._dedupe_accent_insensitive(nz._merge_extracted(texts, nz._extract_medications))

    # Field từ vựng dùng review floor CAO riêng (giảm false-positive bịa product).
    _vocab_review = max(fuzzy_review, _VOCAB_FUZZY_REVIEW)
    products = _list_vocab(
        product_vals, clean_text_no_accent, PRODUCT_CANONICALS,
        accept=fuzzy_accept, review=_vocab_review,
        term_map=nz._PRODUCT_CANONICAL_MAP,
        fuzzy_context_filter=lambda raw: (
            _vitamin_letter_ok(raw, clean_text_no_accent)
            and nz._positive_mention(re.escape(raw), clean_text_no_accent)
        ),
    )
    _med_ctx_text = clean_text_no_accent.lower()
    medications = _list_vocab(
        medication_vals, clean_text_no_accent, MEDICATION_CANONICALS,
        accept=fuzzy_accept, review=_vocab_review,
        fuzzy_context_filter=lambda raw: nz._has_medication_use_context(_med_ctx_text, raw),
    )
    allergies = (
        _list_vocab_aliases(
            allergy_vals, clean_text_no_accent, _ALLERGY_ALIAS_TO_LABEL,
            accept=fuzzy_accept, review=_vocab_review,
        )
        if _has_allergy_context(clean_text, clean_text_no_accent)
        else _list_from_pattern(allergy_vals, clean_text)
    )

    return ExtractionConfidence(
        skin_type=_scalar(skin_type, clean_text),
        sex=_scalar(sex, clean_text),
        age=FieldResult.make(age, "pattern") if age is not None else FieldResult.none(),
        duration_weeks=FieldResult.make(duration, "pattern") if duration is not None else FieldResult.none(),
        is_pregnant=is_pregnant,
        is_breastfeeding=is_breastfeeding,
        inflammation=infl_result,
        lesion_types=_list_from_pattern(lesion_vals, clean_text),
        distribution=_list_from_pattern(dist_vals, clean_text),
        products=products,
        medications=medications,
        allergies=allergies,
        scarring_signs=_scarring_confidence(scarring_vals, lesion_vals, red_flag_vals),
        hormonal_factors=ListFieldResult(items=tuple(
            FieldResult.make(v, "pattern") for v in hormonal_vals
        )),
        treatment_goals=_list_from_pattern(treatment_goal_vals, clean_text),
        # red_flags: ưu tiên recall → method pattern, không trừ điều chỉnh câu hỏi
        red_flags=ListFieldResult(items=tuple(
            FieldResult.make(v, "pattern") for v in red_flag_vals
        )),
    )


def _inflammation_confidence(
    value: str | None,
    text: str,
    lesion_types: list[str],
) -> FieldResult[str]:
    """Severity là field SUY LUẬN → confidence theo mức bằng chứng.

    0.5 baseline + 0.2 nếu có từ mức độ rõ + 0.2 nếu lesion đồng thuận.
    'mild' suy từ lesion không rõ → fallback 0.45 (dưới ngưỡng → đẩy clarify).
    """
    if value is None:
        return FieldResult.none()

    # Explicit severity signals - dùng word boundary để tránh false trigger
    # "nặng" cần word boundary vì "nang" có thể xuất hiện trong từ khác
    explicit = re.compile(
        r"\b(?:nặng(?:\s*lắm)?|severe|nhẹ(?:\s*thôi)?|nhe(?:\s*thoi)?|mild|"
        r"vừa\s*nặng|vừa\s*nang|vua\s*nang|moderate|"
        r"đau(?:\s*nhiều|\s*nhieu|\s*lắm|\s*lam)?|dau(?:\s*nhieu|\s*lam)?|"
        r"sưng(?:\s*to|sung(?:\s*to)?)?|viêm(?:\s*nặng|\s*nang)?|viem(?:\s*nang)?)\b",
        re.I,
    ).search(text) is not None
    has_inflammatory = any(t in {"papule", "pustule", "nodule", "cyst"} for t in lesion_types)

    if value in {"severe", "moderate"} and explicit:
        conf = 0.90
        method = "pattern"
    elif value == "mild" and explicit:
        conf = 0.75
        method = "pattern"
    elif value == "mild" and not explicit and not has_inflammatory:
        # 'mild' do fallback từ lesion không rõ loại
        conf = 0.45
        method = "fallback"
    else:
        conf = 0.60
        method = "pattern"

    return FieldResult.make(value, method, confidence=conf, evidence=text[:60])


def _scarring_confidence(
    values: list[str],
    lesion_types: list[str],
    red_flags: list[str],
) -> ListFieldResult[str]:
    items: list[FieldResult[str]] = []
    for value in values:
        if value == "sẹo mụn":
            conf = 0.88 if "scar" in lesion_types else 0.78
        elif value == "thâm sau mụn":
            conf = 0.88 if "post_inflammatory_hyperpigmentation" in lesion_types else 0.78
        elif "scarring_risk" in red_flags:
            conf = 0.78
        else:
            conf = 0.65
        items.append(FieldResult.make(value, "pattern", confidence=conf))
    return ListFieldResult(items=tuple(items))


# ---------------------------------------------------------------------------
# Điểm conf tổng + hedging text cho prompt.
# Chấp nhận extract KHÔNG bao giờ đúng 100% → thay vì giả vờ chắc chắn,
# truyền độ chắc BẰNG LỜI (không số) vào prompt để model thận trọng đúng chỗ.
# ---------------------------------------------------------------------------

# Trọng số field bắt buộc cho điểm tổng. Field an toàn nặng hơn.
_OVERALL_WEIGHTS = {
    "is_pregnant": 1.8,
    "is_breastfeeding": 1.8,
    "allergies": 1.5,
    "inflammation": 1.5,   # severity ảnh hưởng mạnh tới mức độ tư vấn
    "lesion_types": 1.2,
    "distribution": 1.0,
    "scarring_signs": 1.0,
    "hormonal_factors": 0.8,
    "skin_type": 0.8,
    "treatment_goals": 0.5,
}

# Nhãn người-đọc cho từng field (để hedging tự nhiên).
_FIELD_LABELS_VI = {
    "skin_type": "loại da",
    "inflammation": "mức độ viêm",
    "lesion_types": "loại tổn thương",
    "distribution": "vị trí mụn",
    "products": "sản phẩm đang dùng",
    "medications": "thuốc đang dùng",
    "is_pregnant": "tình trạng mang thai",
    "is_breastfeeding": "tình trạng cho con bú",
    "allergies": "dị ứng/kích ứng",
    "scarring_signs": "sẹo hoặc thâm sau mụn",
    "hormonal_factors": "yếu tố nội tiết/khởi phát",
    "treatment_goals": "mục tiêu điều trị",
}


def _field_conf(ec: "ExtractionConfidence", name: str) -> float:
    """Lấy confidence đại diện của một field (0.0 nếu rỗng)."""
    fr = getattr(ec, name, None)
    if fr is None:
        return 0.0
    if hasattr(fr, "max_confidence"):   # ListFieldResult
        return fr.max_confidence
    return fr.confidence


def overall_confidence(ec: "ExtractionConfidence") -> float:
    """Điểm conf TỔNG = trung bình có trọng số các field bắt buộc CÓ giá trị.

    Chỉ tính field thực sự trích được (conf > 0) — field rỗng không kéo điểm
    xuống (vì 'không có' khác 'có nhưng không chắc'). Trả 0.0 nếu chưa có field nào.
    """
    num = den = 0.0
    for name, w in _OVERALL_WEIGHTS.items():
        c = _field_conf(ec, name)
        if c > 0.0:
            num += w * c
            den += w
    return round(num / den, 3) if den > 0 else 0.0


def build_confidence_hint(
    ec: "ExtractionConfidence",
    *,
    field_threshold: float,
    overall: float | None = None,
) -> str:
    """Sinh hedging BẰNG LỜI cho prompt (không số).

    - Field có giá trị nhưng conf < ngưỡng → liệt kê là 'chưa chắc'.
    - Một câu giọng điệu theo điểm tổng.
    Trả chuỗi rỗng nếu mọi thứ đều chắc (không cần hedging).
    """
    low_fields: list[str] = []
    for name in (
        "is_pregnant", "is_breastfeeding", "allergies",
        "inflammation", "lesion_types", "distribution", "skin_type",
        "scarring_signs", "hormonal_factors", "treatment_goals",
    ):
        fr = getattr(ec, name, None)
        if fr is None:
            continue
        # có giá trị?
        has_val = bool(getattr(fr, "values", None)) if hasattr(fr, "values") else (fr.value is not None)
        if not has_val:
            continue
        conf = _field_conf(ec, name)
        if conf < field_threshold:
            low_fields.append(_FIELD_LABELS_VI.get(name, name))

    if overall is None:
        overall = overall_confidence(ec)

    parts: list[str] = []
    if low_fields:
        parts.append(
            "Một số thông tin được suy đoán tự động và CHƯA CHẮC CHẮN: "
            + ", ".join(low_fields)
            + ". Nếu các thông tin này có vẻ mâu thuẫn với mô tả của người dùng, "
            "hãy hỏi lại để xác nhận thay vì khẳng định chắc chắn."
        )

    # Giọng điệu theo điểm tổng (chỉ thêm khi đã có field nào đó).
    if overall > 0.0:
        if overall < 0.6:
            parts.append(
                "Thông tin trích xuất còn HẠN CHẾ — hãy tư vấn thận trọng, "
                "nói rõ đây là nhận định sơ bộ dựa trên thông tin chưa đầy đủ, "
                "và khuyến khích người dùng bổ sung hoặc gặp bác sĩ nếu cần."
            )
        # overall cao → không thêm gì, giữ giọng tư vấn bình thường.

    return " ".join(parts)
