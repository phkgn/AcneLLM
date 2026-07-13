"""Compact normalized RAG query and extracted-entity helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..schemas import UserInput

_HIGH_PRECISION_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bbha\b", re.I), "salicylic acid"),
    (re.compile(r"\bbpo\b", re.I), "benzoyl peroxide"),
    (re.compile(r"\bdifferin\b", re.I), "adapalene"),
    (re.compile(r"\bmụn đầu đen\b|\bmun dau den\b", re.I), "open comedone blackhead"),
    (re.compile(r"\bmụn bọc\b|\bmun boc\b", re.I), "nodular acne cystic acne acne nodule"),
)

# Cue phủ định / đã-ngừng-dùng đứng NGAY TRƯỚC tên sản phẩm → KHÔNG đưa alias vào
# query (tránh hồi sinh thực thể người dùng đã bỏ). Xử lý ở một chỗ để mọi alias
# đều thừa hưởng negation scope, thay vì vá từng case.
_NEG_CUES: tuple[str, ...] = (
    "khong dung", "khong xai", "khong su dung", "khong con", "khong thoa", "khong boi",
    "ngung dung", "ngung", "da ngung", "dung lai", "thoi dung", "het dung", "bo dung",
    "khong dung nua", "doi tu", "thay vi", "khong xai nua",
)
# "bỏ <sản phẩm>" = ngừng dùng, nhưng loại trừ "bổ sung/bỏ qua/bỏ vào" (không phủ định).
_NEG_RE = re.compile(r"\bbo\b(?!\s*(?:sung|qua|vao|di\b))")


def _no_accent(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


# Ranh giới mệnh đề: chỉ xét phủ định TRONG cùng mệnh đề với sản phẩm, để
# "không dùng BHA nữa, giờ dùng differin" chỉ phủ định BHA, không phủ định differin.
_CLAUSE_BOUNDARY = re.compile(r"[,.;:]|\bgio\b|\bnhung\b|\bhien\b|\bbay gio\b")


def _alias_is_negated(text_no_accent_lower: str, start: int) -> bool:
    """True nếu có cue phủ định trong mệnh đề đứng ngay trước vị trí alias match."""
    prefix = text_no_accent_lower[:start]
    boundaries = [m.end() for m in _CLAUSE_BOUNDARY.finditer(prefix)]
    clause = prefix[boundaries[-1]:] if boundaries else prefix
    return any(cue in clause for cue in _NEG_CUES) or _NEG_RE.search(clause) is not None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _compact_text(text: str, max_chars: int = 700) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rsplit(" ", 1)[0].strip()


def build_retrieval_query(
    lesions: list[str] | None = None,
    skin_type: str | None = None,
    canonical_ingredients: list[str] | None = None,
    clean_text_normalized: str = "",
    severity: str | None = None,
    distribution: list[str] | None = None,
    products: list[str] | None = None,
    medications: list[str] | None = None,
    duration_weeks: int | None = None,
    usage_frequencies: list[str] | None = None,
    concentrations: list[float] | None = None,
    red_flags: list[str] | None = None,
) -> str:
    """Build the canonical compact query used by dense/sparse RAG."""
    parts: list[str] = []
    if lesions:
        parts.append("lesions " + " ".join(_dedupe(lesions)))
    if distribution:
        parts.append("distribution " + " ".join(_dedupe(distribution)))
    if severity and severity not in {"unknown", "none"}:
        parts.append(f"severity {severity}")
    if skin_type:
        parts.append(f"skin_type {skin_type}")
    if canonical_ingredients:
        parts.append("canonical_ingredients " + " ".join(_dedupe(canonical_ingredients)))
    if products:
        parts.append("products " + " ".join(_dedupe(products)))
    if medications:
        parts.append("medications " + " ".join(_dedupe(medications)))
    if duration_weeks is not None:
        parts.append(f"duration_weeks {duration_weeks}")
    if usage_frequencies:
        parts.append("frequency " + " ".join(_dedupe(usage_frequencies)))
    if concentrations:
        formatted = " ".join(f"{float(value):.8g}" for value in concentrations)
        parts.append("concentration " + formatted)
    if red_flags:
        parts.append("red_flags " + " ".join(_dedupe(red_flags)))

    clean = _compact_text(clean_text_normalized)
    if clean:
        parts.append("text " + clean)
    return " ; ".join(parts).strip()


def build_retrieval_query_from_user(
    user: UserInput,
    clean_text_normalized: str = "",
) -> str:
    clinical = user.clinical
    return build_retrieval_query(
        lesions=list(clinical.lesion_types) if clinical else [],
        skin_type=user.context.skin_type,
        canonical_ingredients=list(clinical.canonical_ingredients) if clinical else [],
        clean_text_normalized=clean_text_normalized or user.description,
        severity=clinical.inflammation_level if clinical else None,
        distribution=list(clinical.lesion_distribution) if clinical else [],
        products=list(user.context.current_products or []),
        medications=list(user.context.medications or []),
        duration_weeks=user.context.duration_weeks,
        usage_frequencies=list(clinical.usage_frequencies) if clinical else [],
        concentrations=list(clinical.concentrations) if clinical else [],
        red_flags=list(clinical.red_flags_input) if clinical else [],
    )


def build_current_turn_query(
    clean_text: str,
    recent_history: list[object] | None = None,
) -> str:
    """Build the production RAG query from the current message first.

    Only explicit, high-precision aliases and the previous relevant user turn
    may be added. Structured/inferred clinical labels are deliberately absent.
    """
    current = _compact_text(clean_text)
    current_na = _no_accent(current).lower()
    expansions: list[str] = []
    for pattern, canonical in _HIGH_PRECISION_ALIASES:
        match = pattern.search(current)
        if match is None:
            continue
        if _alias_is_negated(current_na, match.start()):
            continue  # sản phẩm đã bị phủ định/ngừng dùng → bỏ alias
        expansions.append(canonical)
    parts = [current]
    if expansions:
        parts.append("aliases: " + " ".join(_dedupe(expansions)))
    lowered = current.lower()
    if any(term in lowered for term in ("nguy hiểm", "nguy hiem", "dấu hiệu nặng", "dau hieu nang")):
        parts.append("safety topic: severe acne red flags infection when to see dermatologist")
    previous_user = next(
        (
            _compact_text(str(getattr(turn, "content", "")), max_chars=300)
            for turn in reversed(recent_history or [])
            if getattr(turn, "role", "") == "user"
        ),
        "",
    )
    if previous_user:
        parts.append("recent context: " + previous_user)
    return "\n".join(part for part in parts if part)


def extracted_entities_from_user(user: UserInput) -> dict[str, Any]:
    clinical = user.clinical
    return {
        "lesions": list(clinical.lesion_types) if clinical else [],
        "skin_type": user.context.skin_type,
        "severity": clinical.inflammation_level if clinical else None,
        "distribution": list(clinical.lesion_distribution) if clinical else [],
        "products": list(user.context.current_products or []),
        "medications": list(user.context.medications or []),
        "canonical_ingredients": list(clinical.canonical_ingredients) if clinical else [],
        "duration_weeks": user.context.duration_weeks,
        "usage_frequencies": list(clinical.usage_frequencies) if clinical else [],
        "concentrations": list(clinical.concentrations) if clinical else [],
        "red_flags": list(clinical.red_flags_input) if clinical else [],
    }
