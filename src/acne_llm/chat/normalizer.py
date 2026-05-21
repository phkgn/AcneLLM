"""Rule-based intake normalizer for one-box chat input.

The goal is not perfect medical NLP. It extracts high-signal safety and acne
context without adding another Ollama call before the actual answer.
"""
from __future__ import annotations

import re

from ..schemas import AcneClinicalInput, UserContext, UserInput


_SKIN_TYPES: list[tuple[str, str]] = [
    ("oily", r"\bda\s*(?:dau|dầu|nhờn|nhon)\b"),
    ("dry", r"\bda\s*(?:khô|kho)\b"),
    ("combination", r"\bda\s*(?:hỗn\s*hợp|hon\s*hop|mixed|combination)\b"),
    ("sensitive", r"\bda\s*(?:nhạy\s*cảm|nhay\s*cam|sensitive)\b"),
    ("normal", r"\bda\s*(?:thường|thuong|normal)\b"),
]

_PRODUCT_TERMS = [
    "bha",
    "aha",
    "pha",
    "retinol",
    "retinoid",
    "tretinoin",
    "adapalene",
    "isotretinoin",
    "benzoyl peroxide",
    "bpo",
    "salicylic acid",
    "azelaic acid",
    "niacinamide",
    "vitamin c",
    "kem chống nắng",
    "sunscreen",
    "sữa rửa mặt",
    "cleanser",
    "moisturizer",
    "kem dưỡng",
]

_DISTRIBUTION_TERMS: list[tuple[str, str]] = [
    ("forehead", r"\b(?:trán|tran|forehead)\b"),
    ("cheeks", r"\b(?:má|ma|cheek|cheeks)\b"),
    ("chin", r"\b(?:cằm|cam|chin)\b"),
    ("jawline", r"\b(?:quai hàm|quai ham|jawline|hàm|ham)\b"),
    ("nose", r"\b(?:mũi|mui|nose)\b"),
    ("around_mouth", r"\b(?:quanh miệng|quanh mieng|around mouth|mép|mep)\b"),
    ("back", r"\b(?:lưng|lung|back)\b"),
    ("chest", r"\b(?:ngực|nguc|chest)\b"),
    ("shoulders", r"\b(?:vai|shoulder|shoulders)\b"),
    ("neck", r"\b(?:cổ|co|neck)\b"),
    ("t_zone", r"\b(?:t-zone|vùng chữ t|vung chu t)\b"),
]

_LESION_TERMS: list[tuple[str, str]] = [
    ("closed_comedone", r"\b(?:mụn\s*ẩn|mun\s*an|closed comedone|mụn đầu trắng kín)\b"),
    ("whitehead", r"\b(?:mụn\s*đầu\s*trắng|mun\s*dau\s*trang|whitehead)\b"),
    ("blackhead", r"\b(?:mụn\s*đầu\s*đen|mun\s*dau\s*den|blackhead)\b"),
    ("papule", r"\b(?:mụn\s*viêm|mun\s*viem|papule|sẩn viêm)\b"),
    ("pustule", r"\b(?:mụn\s*mủ|mun\s*mu|pustule)\b"),
    ("nodule", r"\b(?:mụn\s*bọc|mun\s*boc|nodule|mụn\s*nang|cyst)\b"),
    ("scar", r"\b(?:sẹo|seo|scar)\b"),
    ("post_inflammatory_hyperpigmentation", r"\b(?:thâm|tham|hyperpigmentation)\b"),
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
        r"\b(?:em|tôi|toi|mình|minh)?\s*(\d{1,3})\s*(?:tuổi|tuoi)\b",
        r"\b(\d{1,3})\s*t\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue
        age = int(m.group(1))
        if 0 <= age <= 120:
            return age
    return None


def _extract_duration_weeks(text: str) -> int | None:
    m = re.search(r"\b(\d{1,3})\s*(ngày|ngay|tuần|tuan|tháng|thang)\b", text, re.I)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    if unit in {"ngày", "ngay"}:
        return max(1, round(value / 7))
    if unit in {"tháng", "thang"}:
        return value * 4
    return value


def _extract_skin_type(text: str) -> str | None:
    for value, pattern in _SKIN_TYPES:
        if _has(pattern, text):
            return value
    return None


def _extract_products(text: str) -> list[str]:
    lowered = text.lower()
    found = [term for term in _PRODUCT_TERMS if term in lowered]
    return _dedupe(found)


def _extract_distributions(text: str) -> list[str]:
    return _dedupe([value for value, pattern in _DISTRIBUTION_TERMS if _has(pattern, text)])


def _extract_lesions(text: str) -> list[str]:
    return _dedupe([value for value, pattern in _LESION_TERMS if _has(pattern, text)])


def _extract_inflammation(text: str, lesion_types: list[str]) -> str | None:
    if _has(r"\b(?:nặng|nang|bọc|sưng đau|đau nhiều|severe)\b", text):
        return "severe"
    if any(t in lesion_types for t in ("papule", "pustule", "nodule")):
        return "moderate"
    if lesion_types:
        return "mild"
    return None


def _contains_positive(text: str, positive: str, negative: str) -> bool:
    if _has(negative, text):
        return False
    return _has(positive, text)


def normalize_chat_message(message: str, mode: str = "auto") -> UserInput:
    """Convert a free-form chat message into the existing UserInput schema."""
    text = message.strip()
    lesion_types = _extract_lesions(text)
    distribution = _extract_distributions(text)
    inflammation = _extract_inflammation(text, lesion_types)

    context = UserContext(
        age=_extract_age(text),
        skin_type=_extract_skin_type(text),
        is_pregnant=_contains_positive(
            text,
            r"\b(?:mang thai|có thai|co thai|đang bầu|dang bau|pregnant)\b",
            r"\b(?:không|khong|ko|k)\s+(?:mang thai|có thai|co thai|bầu|bau)\b",
        ),
        is_breastfeeding=_contains_positive(
            text,
            r"\b(?:cho con bú|cho con bu|breastfeeding)\b",
            r"\b(?:không|khong|ko|k)\s+(?:cho con bú|cho con bu|breastfeeding)\b",
        ),
        current_products=_extract_products(text),
        duration_weeks=_extract_duration_weeks(text),
    )

    clinical = AcneClinicalInput(
        lesion_types=lesion_types,
        lesion_distribution=distribution,
        inflammation_level=inflammation,
    ) if lesion_types or distribution or inflammation else None

    safe_mode = mode if mode in {"hybrid", "llm_only"} else "hybrid"
    return UserInput(description=text, context=context, clinical=clinical, mode=safe_mode)
