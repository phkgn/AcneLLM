"""Relabel the 985-row flat golden extraction corpus into Unified Intake SFT."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .generator import to_record
from .schema import DISTRIBUTION, INFLAMMATION, INTENT, LESION, SEX, SKIN, validate_intake_record
from .writer import iter_jsonl

_VI_DIACRITICS = set(
    "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_NEGATION = re.compile(
    r"\b(?:không\s+dùng(?:\s+nữa)?|đã\s+ngưng|đã\s+ngừng|bỏ\s+rồi|nghỉ\s+dùng)\b",
    re.IGNORECASE,
)
_AMBIGUOUS = re.compile(
    r"\b(?:chắc|hình\s+như|có\s+lẽ|tầm|khoảng|cỡ|không\s+chắc)\b",
    re.IGNORECASE,
)
_INGREDIENTS = (
    "bha",
    "aha",
    "retinol",
    "tretinoin",
    "adapalene",
    "differin",
    "benzoyl peroxide",
    "bpo",
    "azelaic",
    "niacinamide",
)
_ALIASES = {
    "bha": "salicylic acid",
    "salicylic_acid": "salicylic acid",
    "bpo": "benzoyl peroxide",
    "differin": "adapalene",
    "retin-a": "tretinoin",
    "roaccutane": "isotretinoin",
    "oratane": "isotretinoin",
}


def _canonical(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = " ".join(value.strip().split())
    return _ALIASES.get(cleaned.casefold(), cleaned)


def _node(value: Any, confidence: float) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"value": value, "confidence": round(confidence, 3)}


def _node_list(values: Any, confidence: float) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        value = _canonical(raw)
        if value is None:
            continue
        marker = value.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append({"value": value, "confidence": round(confidence, 3)})
    return result


def _has_extraction_signal(row: Mapping[str, Any]) -> bool:
    return any(
        row.get(key) not in (None, "", [], "unknown")
        for key in (
            "skin_type",
            "sex",
            "age",
            "duration_weeks",
            "is_pregnant",
            "is_breastfeeding",
            "inflammation",
            "lesions",
            "distribution",
            "products",
            "medications",
            "allergies",
        )
    )


def _case_type(row: Mapping[str, Any]) -> str:
    intent = str(row.get("intent") or "")
    text = str(row.get("text") or "")
    folded = text.casefold()
    if intent == "knowledge":
        mentioned = sum(token in folded for token in _INGREDIENTS)
        compare = any(
            cue in folded
            for cue in ("khác gì", "so với", "so sánh", "hay dùng", "phối hợp")
        )
        if mentioned >= 2 and compare:
            return "knowledge_ingredient_compare"
        if mentioned and any(
            cue in folded
            for cue in ("có tốt", "có nên", "nên dùng", "dùng được", "phù hợp", "thế nào")
        ):
            return "knowledge_product_trap"
        return "knowledge_general"
    if intent == "reject":
        if any(
            cue in folded
            for cue in ("bỏ qua hướng dẫn", "system prompt", "dan", "lộ prompt", "đóng vai")
        ):
            return "reject_jailbreak_meta"
        if any(
            cue in folded
            for cue in ("kê đơn", "liều", "isotretinoin", "kháng sinh", "tự uống")
        ):
            return "reject_unsafe_rx"
        return "reject_ood"
    if intent == "clarify":
        if len(text.split()) <= 12 and any(
            cue in folded for cue in ("chào", "cảm ơn", "thanks", "hello", "ok")
        ):
            return "glue_greeting_thanks"
        return "clarify_vague"

    if _NEGATION.search(text):
        return "advise_negation_stopped"
    if row.get("duration_weeks") is not None:
        return "advise_duration_convert"
    if text and not any(char in _VI_DIACRITICS for char in folded):
        return "advise_noaccent"
    if any(token in folded for token in ("skin", "acne", "routine", "barrier", "active")):
        return "advise_mixed_vi_en"
    if _AMBIGUOUS.search(text) and _has_extraction_signal(row):
        return "advise_ambiguous_lowconf"
    signal_count = sum(
        bool(row.get(key))
        for key in (
            "skin_type",
            "sex",
            "age",
            "inflammation",
            "lesions",
            "distribution",
            "products",
            "medications",
            "allergies",
        )
    )
    return "advise_selfreport_rich" if signal_count >= 4 else "advise_selfreport_simple"


def _enum_errors(row: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("intent") not in INTENT:
        errors.append("intent")
    if row.get("sex") is not None and row.get("sex") not in SEX:
        errors.append("sex")
    if row.get("skin_type") is not None and row.get("skin_type") not in SKIN:
        errors.append("skin_type")
    inflammation = row.get("inflammation")
    if inflammation is not None and inflammation not in INFLAMMATION:
        errors.append("inflammation")
    lesions = row.get("lesions")
    if isinstance(lesions, list) and any(value not in LESION for value in lesions):
        errors.append("lesions")
    distribution = row.get("distribution")
    if isinstance(distribution, list) and any(
        value not in DISTRIBUTION for value in distribution
    ):
        errors.append("distribution")
    return errors


def relabel_row(
    row: Mapping[str, Any], anchor: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Map one flat row; invalid/unmappable rows return reasons instead."""
    text = row.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, ["missing_text"]
    errors = _enum_errors(row)
    if errors:
        return None, [f"enum_{reason}" for reason in errors]

    intent = str(row["intent"])
    case_type = _case_type(row)
    reliable = row.get("reliable") is not False
    field_confidence = 0.94 if reliable else 0.78
    if case_type == "advise_ambiguous_lowconf":
        field_confidence = 0.5
    intent_confidence = {
        "advise": 0.94,
        "knowledge": 0.96,
        "clarify": 0.62,
        "reject": 0.96,
    }[intent]

    empty_case = intent in {"knowledge", "reject"} or case_type == "glue_greeting_thanks"
    if empty_case:
        context: dict[str, Any] = {}
        clinical = None
    else:
        age = row.get("age")
        duration = row.get("duration_weeks")
        context = {
            "age": _node(age, field_confidence)
            if isinstance(age, int) and not isinstance(age, bool)
            else None,
            "sex": _node(row.get("sex"), field_confidence),
            "skin_type": _node(row.get("skin_type"), field_confidence),
            "is_pregnant": _node(row.get("is_pregnant"), field_confidence)
            if isinstance(row.get("is_pregnant"), bool)
            else None,
            "is_breastfeeding": _node(
                row.get("is_breastfeeding"), field_confidence
            )
            if isinstance(row.get("is_breastfeeding"), bool)
            else None,
            "duration_weeks": _node(duration, field_confidence)
            if isinstance(duration, int) and not isinstance(duration, bool)
            else None,
            "allergies": _node_list(row.get("allergies"), field_confidence),
            "current_products": _node_list(row.get("products"), field_confidence),
            "medications": _node_list(row.get("medications"), field_confidence),
        }
        lesion_nodes = _node_list(row.get("lesions"), field_confidence)
        distribution_nodes = _node_list(row.get("distribution"), field_confidence)
        inflammation = row.get("inflammation")
        has_clinical = bool(
            lesion_nodes
            or distribution_nodes
            or inflammation not in (None, "none", "unknown")
        )
        clinical = (
            {
                "lesion_types": lesion_nodes,
                "inflammation_level": _node(
                    inflammation or "unknown", field_confidence
                ),
                "lesion_distribution": distribution_nodes,
            }
            if has_clinical
            else None
        )

    assistant_json = {
        "intent": intent,
        "confidence": intent_confidence,
        "description": text,
        "context": context,
        "clinical": clinical,
    }
    ok, validation_reasons = validate_intake_record(assistant_json)
    if not ok:
        return None, [f"schema_{reason}" for reason in validation_reasons]

    spec = {
        "case_type": case_type,
        "quota": 0,
        "style_hint": "",
        "intent_hint": intent,
        "behavior": "",
    }
    record = to_record(
        spec,
        {"user_turn": text, "history": [], "assistant_json": assistant_json},
        anchor,
        source="golden_relabel",
        seed={"reliable": reliable},
    )
    record["meta"]["judged"] = True
    return record, []


def load_relabelled_seeds(
    path: Path, anchor: str
) -> tuple[list[dict[str, Any]], Counter[str]]:
    records: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    for row in iter_jsonl(path):
        record, reasons = relabel_row(row, anchor)
        if record is None:
            rejected.update(reasons or ["unmappable"])
        else:
            records.append(record)
    return records, rejected
