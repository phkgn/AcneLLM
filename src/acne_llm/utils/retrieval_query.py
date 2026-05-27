"""Compact normalized RAG query and extracted-entity helpers."""
from __future__ import annotations

import re
from typing import Any

from ..schemas import UserInput


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
