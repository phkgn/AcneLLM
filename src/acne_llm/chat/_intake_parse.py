"""Shared parsing and validation helpers for legacy and unified intake."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..schemas import AcneClinicalInput, UserContext, UserInput
from ..schemas.extraction import FieldResult, ListFieldResult
from ..schemas.extraction import ExtractionConfidence
from .intake_contract import ExtractorFallback


_LESION = frozenset({
    "comedone",
    "whitehead",
    "blackhead",
    "closed_comedone",
    "papule",
    "pustule",
    "nodule",
    "cyst",
    "scar",
    "post_inflammatory_hyperpigmentation",
    "other",
})
_SKIN = frozenset({"dry", "oily", "combination", "sensitive", "normal", "unknown"})
_SEX = frozenset({"male", "female", "other"})
_INFLAMMATION = frozenset({"none", "mild", "moderate", "severe", "unknown"})
_DISTRIBUTION = frozenset({
    "forehead",
    "cheeks",
    "chin",
    "jawline",
    "nose",
    "around_mouth",
    "back",
    "chest",
    "shoulders",
    "neck",
    "t_zone",
    "other",
})
_INTENT = frozenset({"advise", "knowledge", "clarify", "reject"})
_CONTEXT_SCALARS = (
    "age",
    "sex",
    "skin_type",
    "is_pregnant",
    "is_breastfeeding",
    "duration_weeks",
)
_CONTEXT_LISTS = ("allergies", "current_products", "medications")
_CLINICAL_SCALARS = ("inflammation_level",)
_CLINICAL_LISTS = (
    "lesion_types",
    "lesion_distribution",
    "scarring_signs",
    "hormonal_factors",
    "treatment_goals",
)
# CHỈ áp cho đường LEGACY (fallback/llm_extractor.py + _OLLAMA_JSON_SCHEMA phẳng):
# ở đó confidence không do model sinh, field có value coi như đủ tin.
#
# Đường UNIFIED thì NGƯỢC LẠI: acne-intaker được fine-tune sinh nested
# {"value":...,"confidence":...} (xem datagen/intakedata/output/intake/
# intake.train.jsonl), khớp _RUNTIME_SYSTEM, và _scalar_node đọc đúng confidence
# đó. Nên ECE trên đường unified là đo thật, không đo hằng số.
# _DEFAULT_CONF chỉ là giá trị dùng khi node ở dạng phẳng/thiếu confidence.
_DEFAULT_CONF = 0.8


def _scalar_schema(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [value_schema, {"type": "null"}]}


def _list_schema(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": value_schema}


# Schema PHẲNG (value trực tiếp) và KHÔNG "required" → model chỉ cần xuất field
# tìm được, JSON nhỏ. Enum vẫn giữ để ràng chất lượng giá trị.
_OLLAMA_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "context": {
            "type": "object",
            "properties": {
                "age": _scalar_schema({"type": "integer", "minimum": 0, "maximum": 120}),
                "sex": _scalar_schema({"type": "string", "enum": sorted(_SEX)}),
                "skin_type": _scalar_schema({"type": "string", "enum": sorted(_SKIN)}),
                "is_pregnant": _scalar_schema({"type": "boolean"}),
                "is_breastfeeding": _scalar_schema({"type": "boolean"}),
                "duration_weeks": _scalar_schema({"type": "integer", "minimum": 0}),
                "allergies": _list_schema({"type": "string"}),
                "current_products": _list_schema({"type": "string"}),
                "medications": _list_schema({"type": "string"}),
            },
            "additionalProperties": False,
        },
        "clinical": {
            "type": "object",
            "properties": {
                "lesion_types": _list_schema({"type": "string", "enum": sorted(_LESION)}),
                "inflammation_level": _scalar_schema({"type": "string", "enum": sorted(_INFLAMMATION)}),
                "lesion_distribution": _list_schema({"type": "string", "enum": sorted(_DISTRIBUTION)}),
                "scarring_signs": _list_schema({"type": "string"}),
                "hormonal_factors": _list_schema({"type": "string"}),
                "treatment_goals": _list_schema({"type": "string"}),
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LLMExtractResult:
    user: UserInput
    confidence: ExtractionConfidence


def _extract_json(raw: str) -> str:
    """Remove common Ollama prose/fence noise and return the JSON span."""
    if not isinstance(raw, str) or not raw.strip():
        raise ExtractorFallback("extractor returned an empty non-text response")
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ExtractorFallback("extractor response does not contain a JSON object")
    return text[start : end + 1]


def _coerce_conf(raw: Any) -> float:
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_CONF
    return min(1.0, max(0.0, c))


def _scalar_node(section: Mapping[str, Any], key: str, prefix: str) -> tuple[Any, float]:
    """D: khoan dung. Chấp cả flat (value trần) lẫn legacy {value,confidence};
    thiếu key / sai kiểu → (None, 0.0) thay vì raise."""
    if not isinstance(section, Mapping) or key not in section:
        return None, 0.0
    node = section[key]
    if isinstance(node, Mapping):  # legacy {value, confidence}
        return node.get("value"), _coerce_conf(node.get("confidence", _DEFAULT_CONF))
    return (node, _DEFAULT_CONF) if node is not None else (None, 0.0)


def _list_nodes(
    section: Mapping[str, Any], key: str, prefix: str
) -> list[tuple[Any, float]]:
    """D: chấp mảng chuỗi trần lẫn mảng {value,confidence}; sai kiểu → bỏ qua."""
    raw = section.get(key) if isinstance(section, Mapping) else None
    if not isinstance(raw, list):
        return []
    result: list[tuple[Any, float]] = []
    for item in raw:
        if isinstance(item, Mapping):
            value = item.get("value")
            conf = _coerce_conf(item.get("confidence", _DEFAULT_CONF))
        else:
            value, conf = item, _DEFAULT_CONF
        result.append((value, conf if value is not None else 0.0))
    return result


def _sections(data: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = data if isinstance(data, Mapping) else {}
    context = root.get("context")
    clinical = root.get("clinical")
    return (
        context if isinstance(context, Mapping) else {},
        clinical if isinstance(clinical, Mapping) else {},
    )


def _validate_contract(data: Any) -> None:
    """Only real crash guard left: the model must return a JSON object.

    Everything below the root is handled by the tolerant field parsers, which
    drop unusable values instead of discarding the whole inference.
    """
    if not isinstance(data, Mapping):
        raise ExtractorFallback("extractor root is not a JSON object")


def _enum_fr(
    section: Mapping[str, Any],
    key: str,
    prefix: str,
    allowed: frozenset[str],
) -> FieldResult[str]:
    value, confidence = _scalar_node(section, key, prefix)
    if value is None or not isinstance(value, str):
        return FieldResult.none()
    normalized = value.strip().lower()
    if normalized not in allowed:
        # Enum hallucinations are explicitly dropped before Pydantic validation.
        return FieldResult.none()
    return FieldResult.make(normalized, "llm", confidence=confidence)


def _int_fr(
    section: Mapping[str, Any],
    key: str,
    prefix: str,
    *,
    maximum: int | None = None,
) -> FieldResult[int]:
    value, confidence = _scalar_node(section, key, prefix)
    if value is None or isinstance(value, bool):
        return FieldResult.none()
    try:  # D: chấp cả "22" (chuỗi) và 22; sai kiểu → drop, không raise
        if isinstance(value, str):
            value = value.strip()
            integer = int(float(value)) if value else None
        elif isinstance(value, (int, float)) and int(value) == value:
            integer = int(value)
        else:
            integer = None
    except (TypeError, ValueError):
        integer = None
    if integer is None or integer < 0 or (maximum is not None and integer > maximum):
        return FieldResult.none()
    return FieldResult.make(integer, "llm", confidence=confidence)


def _bool_fr(section: Mapping[str, Any], key: str, prefix: str) -> FieldResult[bool]:
    value, confidence = _scalar_node(section, key, prefix)
    if isinstance(value, bool):
        return FieldResult.make(value, "llm", confidence=confidence)
    if isinstance(value, str):  # D: chấp "true"/"false"/"co"/"khong"...
        low = value.strip().lower()
        if low in ("true", "1", "yes", "co", "có"):
            return FieldResult.make(True, "llm", confidence=confidence)
        if low in ("false", "0", "no", "khong", "không"):
            return FieldResult.make(False, "llm", confidence=confidence)
    return FieldResult.none()


def _lfr(
    section: Mapping[str, Any],
    key: str,
    prefix: str,
    allowed: frozenset[str] | None = None,
) -> ListFieldResult[str]:
    by_value: dict[str, FieldResult[str]] = {}
    for value, confidence in _list_nodes(section, key, prefix):
        if not isinstance(value, str):  # D: bỏ qua item sai kiểu, không raise
            continue
        normalized = value.strip()
        if not normalized:
            continue
        if allowed is not None:
            normalized = normalized.lower()
            if normalized not in allowed:
                continue
        candidate = FieldResult.make(normalized, "llm", confidence=confidence)
        previous = by_value.get(normalized)
        if previous is None or candidate.confidence > previous.confidence:
            by_value[normalized] = candidate
    return ListFieldResult(items=tuple(by_value.values()))


# ponytail: _raw_safety_overrides / _raw_safety_lists / _merge_safety_lfr da bi
# xoa. Ba ham nay chay regex tren MOI luot unified roi OR vao ket qua model.
#
# Ly do bo: chung tra loi sai cau hoi. Regex tra loi "chu 'mang thai' co xuat
# hien khong", con cong an toan can biet "nguoi dung CO DANG mang thai khong".
# Hai menh de khac nhau. Do tren 13 cau doi khang: sai 3 -- qua khu ("truoc em
# mang thai nhung gio sinh roi"), tu dinh chinh, va chu ngu ("chi toi dang mang
# thai" -> danh dau nguoi dung). Phu dinh/thi/quy chu ngu la viec cua model.
#
# rule_normalizer + rule_extractor van con nguyen, nhung chi chay khi
# UnifiedIntake nem ExtractorFallback (JSON khong parse duoc).


def _to_user_input(data: Mapping[str, Any], clean_text: str, mode: str) -> UserInput:
    _validate_contract(data)
    context, clinical = _sections(data)

    age = _int_fr(context, "age", "context", maximum=120)
    sex = _enum_fr(context, "sex", "context", _SEX)
    skin_type = _enum_fr(context, "skin_type", "context", _SKIN)
    pregnant = _bool_fr(context, "is_pregnant", "context")
    breastfeeding = _bool_fr(context, "is_breastfeeding", "context")
    duration = _int_fr(context, "duration_weeks", "context")
    allergies = _lfr(context, "allergies", "context")
    products = _lfr(context, "current_products", "context")
    medications = _lfr(context, "medications", "context")

    lesions = _lfr(clinical, "lesion_types", "clinical", _LESION)
    inflammation = _enum_fr(
        clinical, "inflammation_level", "clinical", _INFLAMMATION
    )
    distribution = _lfr(
        clinical, "lesion_distribution", "clinical", _DISTRIBUTION
    )
    scarring = _lfr(clinical, "scarring_signs", "clinical")
    hormonal = _lfr(clinical, "hormonal_factors", "clinical")
    goals = _lfr(clinical, "treatment_goals", "clinical")

    # Trich xuat HOAN TOAN do intaker. Truoc day co mot lop regex ghi de o day
    # ("safety net"), da bo: no khong doc duoc ngu nghia. Do thuc te tren 13 cau
    # doi khang -- "truoc em mang thai nhung gio sinh roi" -> True,
    # "chi toi dang mang thai" -> danh dau NGUOI DUNG mang thai. Phu dinh, thi va
    # chu ngu la viec cua model, khong phai cua bieu thuc chinh quy.
    is_pregnant = bool(pregnant.value)
    is_breastfeeding = bool(breastfeeding.value)

    clinical_has_signal = bool(
        lesions.values
        or distribution.values
        or scarring.values
        or hormonal.values
        or goals.values
        or inflammation.value not in (None, "unknown")
    )
    clinical_input = (
        AcneClinicalInput(
            lesion_types=lesions.values,
            inflammation_level=inflammation.value or "unknown",
            lesion_distribution=distribution.values,
            scarring_signs=scarring.values,
            hormonal_factors=hormonal.values,
            treatment_goals=goals.values,
        )
        if clinical_has_signal
        else None
    )
    return UserInput(
        description=clean_text,
        mode=mode,
        context=UserContext(
            age=age.value,
            sex=sex.value,
            skin_type=skin_type.value,
            is_pregnant=is_pregnant,
            is_breastfeeding=is_breastfeeding,
            allergies=allergies.values,
            current_products=products.values,
            medications=medications.values,
            duration_weeks=duration.value,
        ),
        clinical=clinical_input,
    )


def _to_extraction_confidence(
    data: Mapping[str, Any], *, clean_text: str = ""
) -> ExtractionConfidence:
    _validate_contract(data)
    context, clinical = _sections(data)
    pregnant = _bool_fr(context, "is_pregnant", "context")
    breastfeeding = _bool_fr(context, "is_breastfeeding", "context")
    medications = _lfr(context, "medications", "context")
    allergies = _lfr(context, "allergies", "context")
    return ExtractionConfidence(
        skin_type=_enum_fr(context, "skin_type", "context", _SKIN),
        sex=_enum_fr(context, "sex", "context", _SEX),
        age=_int_fr(context, "age", "context", maximum=120),
        duration_weeks=_int_fr(context, "duration_weeks", "context"),
        is_pregnant=pregnant,
        is_breastfeeding=breastfeeding,
        inflammation=_enum_fr(
            clinical, "inflammation_level", "clinical", _INFLAMMATION
        ),
        lesion_types=_lfr(clinical, "lesion_types", "clinical", _LESION),
        distribution=_lfr(
            clinical, "lesion_distribution", "clinical", _DISTRIBUTION
        ),
        products=_lfr(context, "current_products", "context"),
        medications=medications,
        allergies=allergies,
        scarring_signs=_lfr(clinical, "scarring_signs", "clinical"),
        hormonal_factors=_lfr(clinical, "hormonal_factors", "clinical"),
        treatment_goals=_lfr(clinical, "treatment_goals", "clinical"),
        red_flags=ListFieldResult.empty(),
    )
