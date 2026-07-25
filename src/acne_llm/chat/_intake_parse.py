"""Shared parsing and validation helpers for legacy and unified intake."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Any

from ..schemas import AcneClinicalInput, UserContext, UserInput
from ..schemas.extraction import FieldResult, ListFieldResult
from . import extraction_confidence as legacy_confidence
from . import normalizer as legacy_rules
from .extraction_confidence import ExtractionConfidence
from .preprocess import strip_accents


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
# A: Confidence KHÔNG còn do LLM sinh (giảm ~50% kích thước JSON + độ phức tạp
# grammar → decode nhanh, ít truncate/timeout). Confidence thật đã tính riêng ở
# extraction_confidence.py; field có value coi như đủ tin (_DEFAULT_CONF).
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


class ExtractorFallback(Exception):
    """Signal that intake must use the deterministic rule fallback."""


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


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExtractorFallback(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], path: str) -> None:
    expected_set = set(expected)
    actual = set(value)
    missing = sorted(expected_set - actual)
    extra = sorted(actual - expected_set)
    if missing or extra:
        raise ExtractorFallback(f"{path} keys invalid: missing={missing}, extra={extra}")


def _confidence(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExtractorFallback(f"{path} must be a number in [0,1]")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ExtractorFallback(f"{path} outside [0,1]")
    return result


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


def _validate_contract(data: Any, *, unified: bool = False) -> None:
    """Validate the common root and, when requested, the unified wire contract.

    The legacy extractor deliberately remains tolerant of partial field output.
    Unified inference uses the strict branch because routing and extraction
    share one response and must either both trust it or both fall back.
    """
    if not isinstance(data, Mapping):
        raise ExtractorFallback("extractor root is not a JSON object")
    if not unified:
        return

    _exact_keys(
        data,
        ("intent", "confidence", "description", "context", "clinical"),
        "unified root",
    )
    if data["intent"] not in _INTENT:
        raise ExtractorFallback("unified intent is outside the repository enum")
    _confidence(data["confidence"], "unified confidence")
    description = data["description"]
    if not isinstance(description, str) or not 1 <= len(description) <= 4_000:
        raise ExtractorFallback("unified description must contain 1-4000 characters")

    context = _mapping(data["context"], "unified context")
    expected_context = (*_CONTEXT_SCALARS, *_CONTEXT_LISTS)
    if context:
        _exact_keys(context, expected_context, "unified context")
        _validate_scalar_wire_node(
            context["age"], "unified context.age", expected=int, minimum=0, maximum=120
        )
        _validate_scalar_wire_node(
            context["sex"], "unified context.sex", expected=str
        )
        _validate_scalar_wire_node(
            context["skin_type"], "unified context.skin_type", expected=str
        )
        _validate_scalar_wire_node(
            context["is_pregnant"],
            "unified context.is_pregnant",
            expected=bool,
        )
        _validate_scalar_wire_node(
            context["is_breastfeeding"],
            "unified context.is_breastfeeding",
            expected=bool,
        )
        _validate_scalar_wire_node(
            context["duration_weeks"],
            "unified context.duration_weeks",
            expected=int,
            minimum=0,
        )
        for key in _CONTEXT_LISTS:
            _validate_list_wire_nodes(
                context[key], f"unified context.{key}", expected=str
            )

    clinical = data["clinical"]
    if clinical is None:
        return
    clinical_obj = _mapping(clinical, "unified clinical")
    expected_clinical = ("lesion_types", "inflammation_level", "lesion_distribution")
    _exact_keys(clinical_obj, expected_clinical, "unified clinical")
    _validate_list_wire_nodes(
        clinical_obj["lesion_types"],
        "unified clinical.lesion_types",
        expected=str,
    )
    _validate_scalar_wire_node(
        clinical_obj["inflammation_level"],
        "unified clinical.inflammation_level",
        nullable=False,
        expected=str,
    )
    _validate_list_wire_nodes(
        clinical_obj["lesion_distribution"],
        "unified clinical.lesion_distribution",
        expected=str,
    )


def _validate_scalar_wire_node(
    node: Any,
    path: str,
    *,
    nullable: bool = True,
    expected: type | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    if node is None and nullable:
        return
    value = _mapping(node, path)
    _exact_keys(value, ("value", "confidence"), path)
    _confidence(value["confidence"], f"{path}.confidence")
    raw = value["value"]
    if expected is int:
        valid_type = isinstance(raw, int) and not isinstance(raw, bool)
    else:
        valid_type = expected is None or isinstance(raw, expected)
    if not valid_type:
        expected_name = expected.__name__ if expected is not None else "valid"
        raise ExtractorFallback(f"{path}.value must be {expected_name}")
    if minimum is not None and raw < minimum:
        raise ExtractorFallback(f"{path}.value is below {minimum}")
    if maximum is not None and raw > maximum:
        raise ExtractorFallback(f"{path}.value is above {maximum}")


def _validate_list_wire_nodes(
    value: Any, path: str, *, expected: type | None = None
) -> None:
    if not isinstance(value, list):
        raise ExtractorFallback(f"{path} must be a list")
    for index, node in enumerate(value):
        item_path = f"{path}[{index}]"
        _validate_scalar_wire_node(
            node,
            item_path,
            nullable=False,
            expected=expected,
        )
        raw = node["value"]
        if expected is str and not raw.strip():
            raise ExtractorFallback(f"{item_path}.value must be non-empty")


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


def _raw_safety_overrides(clean_text: str) -> tuple[bool, bool]:
    """Detect explicit first-person pregnancy/breastfeeding statements.

    The patterns are intentionally narrower than generic topic mentions such as
    "nguy hiểm khi mang thai".  This safety net exists so a small model cannot
    turn an explicit current-state safety fact from true to false.
    """
    text = strip_accents(clean_text.lower())
    pregnant_negative = re.search(
        r"\b(?:khong|ko|k|chua)\s+(?:dang\s+)?(?:mang thai|co thai|bau)\b", text
    )
    breastfeeding_negative = re.search(
        r"\b(?:khong|ko|k|chua)\s+(?:dang\s+)?cho con bu\b", text
    )
    pregnant_positive = re.search(
        r"\b(?:toi|minh|em|chau|con)\s+(?:dang\s+)?(?:mang thai|co thai|bau)\b"
        r"|\bdang\s+(?:mang thai|co thai|bau)\b|\bmoi\s+co thai\b",
        text,
    )
    breastfeeding_positive = re.search(
        r"\b(?:toi|minh|em|chau|con)\s+(?:dang\s+)?cho con bu\b"
        r"|\bdang\s+cho con bu\b",
        text,
    )
    return (
        bool(pregnant_positive and not pregnant_negative),
        bool(breastfeeding_positive and not breastfeeding_negative),
    )


def _raw_safety_lists(clean_text: str) -> tuple[list[str], list[str]]:
    """Run only the existing medication/allergy regexes as a safety net."""
    clean_text_no_accent = strip_accents(clean_text)
    texts = legacy_rules._texts_for_extraction(clean_text, clean_text_no_accent)
    medications = legacy_rules._dedupe_accent_insensitive(
        legacy_rules._merge_extracted(texts, legacy_rules._extract_medications)
    )
    allergy_patterns = legacy_rules._merge_extracted(texts, legacy_rules._extract_allergies)
    if legacy_confidence._has_allergy_context(clean_text, clean_text_no_accent):
        allergies = legacy_confidence._list_vocab_aliases(
            allergy_patterns,
            clean_text_no_accent,
            legacy_confidence._ALLERGY_ALIAS_TO_LABEL,
            accept=0.86,
            review=0.82,
        ).values
    else:
        allergies = allergy_patterns
    return medications, allergies


def _merge_safety_lfr(
    model_values: ListFieldResult[str], raw_values: list[str]
) -> ListFieldResult[str]:
    """OR model values with deterministic raw-text safety matches."""
    by_value = {str(item.value).lower(): item for item in model_values.items if item.value}
    for value in raw_values:
        key = str(value).lower()
        rule_value = FieldResult.make(
            value,
            "pattern",
            confidence=0.95,
            evidence="raw_text_safety_override",
        )
        current = by_value.get(key)
        if current is None or current.confidence < rule_value.confidence:
            by_value[key] = rule_value
    return ListFieldResult(items=tuple(by_value.values()))


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
    raw_medications, raw_allergies = _raw_safety_lists(clean_text)
    medications = _merge_safety_lfr(medications, raw_medications)
    allergies = _merge_safety_lfr(allergies, raw_allergies)

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

    raw_pregnant, raw_breastfeeding = _raw_safety_overrides(clean_text)
    # safety net: regex raw-text overrides the model so hard-refuse does not
    # depend on a single 1.5B extraction decision.
    is_pregnant = raw_pregnant or bool(pregnant.value)
    is_breastfeeding = raw_breastfeeding or bool(breastfeeding.value)

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
    raw_pregnant, raw_breastfeeding = _raw_safety_overrides(clean_text)
    raw_medications, raw_allergies = _raw_safety_lists(clean_text)
    medications = _merge_safety_lfr(medications, raw_medications)
    allergies = _merge_safety_lfr(allergies, raw_allergies)
    if raw_pregnant:
        pregnant = FieldResult.make(
            True, "llm", confidence=1.0, evidence="raw_text_safety_override"
        )
    if raw_breastfeeding:
        breastfeeding = FieldResult.make(
            True, "llm", confidence=1.0, evidence="raw_text_safety_override"
        )

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
