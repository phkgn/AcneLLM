"""Unified Intake enum sets, constrained JSON schema, and validation."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

LESION = frozenset(
    {
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
    }
)
SKIN = frozenset({"dry", "oily", "combination", "sensitive", "normal", "unknown"})
SEX = frozenset({"male", "female", "other"})
INFLAMMATION = frozenset({"none", "mild", "moderate", "severe", "unknown"})
DISTRIBUTION = frozenset(
    {
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
    }
)
INTENT = frozenset({"advise", "knowledge", "clarify", "reject"})

CONTEXT_SCALARS = (
    "age",
    "sex",
    "skin_type",
    "is_pregnant",
    "is_breastfeeding",
    "duration_weeks",
)
CONTEXT_LISTS = ("allergies", "current_products", "medications")
CLINICAL_SCALARS = ("inflammation_level",)
CLINICAL_LISTS = ("lesion_types", "lesion_distribution")


def _node_schema(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "value": value_schema,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["value", "confidence"],
        "additionalProperties": False,
    }


def _nullable_node(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [_node_schema(value_schema), {"type": "null"}]}


def _node_list_schema(value_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": _node_schema(value_schema)}


def build_json_schema() -> dict[str, Any]:
    """Build the strict provider/train schema for one assistant JSON object.

    Structured Outputs requires every property in an object branch to be
    required.  ``context`` therefore has two legal branches: a truly empty
    object for no-extraction cases, or the complete serve key set with absent
    scalars represented as ``null`` and absent lists as ``[]``.
    """
    context_properties: dict[str, Any] = {
        "age": _nullable_node({"type": "integer", "minimum": 0, "maximum": 120}),
        "sex": _nullable_node({"type": "string", "enum": sorted(SEX)}),
        "skin_type": _nullable_node({"type": "string", "enum": sorted(SKIN)}),
        "is_pregnant": _nullable_node({"type": "boolean"}),
        "is_breastfeeding": _nullable_node({"type": "boolean"}),
        "duration_weeks": _nullable_node({"type": "integer", "minimum": 0}),
        "allergies": _node_list_schema({"type": "string", "minLength": 1}),
        "current_products": _node_list_schema({"type": "string", "minLength": 1}),
        "medications": _node_list_schema({"type": "string", "minLength": 1}),
    }
    populated_context = {
        "type": "object",
        "properties": context_properties,
        "required": list(context_properties),
        "additionalProperties": False,
    }
    empty_context = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }
    clinical_properties: dict[str, Any] = {
        "lesion_types": _node_list_schema(
            {"type": "string", "enum": sorted(LESION)}
        ),
        "inflammation_level": _node_schema(
            {"type": "string", "enum": sorted(INFLAMMATION)}
        ),
        "lesion_distribution": _node_list_schema(
            {"type": "string", "enum": sorted(DISTRIBUTION)}
        ),
    }
    clinical = {
        "type": "object",
        "properties": clinical_properties,
        "required": list(clinical_properties),
        "additionalProperties": False,
    }
    root_properties: dict[str, Any] = {
        "intent": {"type": "string", "enum": sorted(INTENT)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "description": {"type": "string", "minLength": 1, "maxLength": 4_000},
        "context": {"anyOf": [empty_context, populated_context]},
        "clinical": {"anyOf": [{"type": "null"}, clinical]},
    }
    return {
        "type": "object",
        "properties": root_properties,
        "required": list(root_properties),
        "additionalProperties": False,
    }


def build_generation_schema() -> dict[str, Any]:
    """Schema for the provider's synthetic pair wrapper."""
    history_item = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": ["user", "assistant"]},
            "content": {"type": "string", "minLength": 1, "maxLength": 4_000},
        },
        "required": ["role", "content"],
        "additionalProperties": False,
    }
    properties = {
        "user_turn": {"type": "string", "minLength": 1, "maxLength": 4_000},
        "history": {"type": "array", "items": history_item, "maxItems": 3},
        "assistant_json": build_json_schema(),
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _confidence(value: Any) -> bool:
    return _number(value) and 0 <= float(value) <= 1


def _node(
    value: Any,
    *,
    expected: type | tuple[type, ...],
    allowed: frozenset[str] | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"value", "confidence"}:
        return False
    raw = value["value"]
    if expected is int:
        type_ok = isinstance(raw, int) and not isinstance(raw, bool)
    else:
        type_ok = isinstance(raw, expected)
    if not type_ok or not _confidence(value["confidence"]):
        return False
    if allowed is not None and raw not in allowed:
        return False
    if minimum is not None and raw < minimum:
        return False
    if maximum is not None and raw > maximum:
        return False
    return True


def _node_list(
    value: Any, *, allowed: frozenset[str] | None = None
) -> bool:
    if not isinstance(value, list):
        return False
    seen: set[str] = set()
    for item in value:
        if not _node(item, expected=str, allowed=allowed):
            return False
        normalized = item["value"].strip().casefold()
        if not normalized or normalized in seen:
            return False
        seen.add(normalized)
    return True


def validate_intake_record(obj: Any) -> tuple[bool, list[str]]:
    """Validate one assistant object (or its JSON string) against the contract."""
    reasons: list[str] = []
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            return False, ["json_parse"]
    if not isinstance(obj, Mapping):
        return False, ["root_object"]

    expected_root = {"intent", "confidence", "description", "context", "clinical"}
    if set(obj) != expected_root:
        reasons.append("root_keys")
    if obj.get("intent") not in INTENT:
        reasons.append("intent")
    if not _confidence(obj.get("confidence")):
        reasons.append("confidence")
    description = obj.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 4_000:
        reasons.append("description")

    context = obj.get("context")
    context_keys = set(CONTEXT_SCALARS) | set(CONTEXT_LISTS)
    if not isinstance(context, Mapping):
        reasons.append("context_object")
    elif set(context) - context_keys:
        reasons.append("context_keys")
    else:
        scalar_specs = {
            "age": (int, None, 0, 120),
            "sex": (str, SEX, None, None),
            "skin_type": (str, SKIN, None, None),
            "is_pregnant": (bool, None, None, None),
            "is_breastfeeding": (bool, None, None, None),
            "duration_weeks": (int, None, 0, None),
        }
        for key, (expected, allowed, minimum, maximum) in scalar_specs.items():
            if key in context and context[key] is not None and not _node(
                context[key],
                expected=expected,
                allowed=allowed,
                minimum=minimum,
                maximum=maximum,
            ):
                reasons.append(f"context.{key}")
        for key in CONTEXT_LISTS:
            if key in context and not _node_list(context[key]):
                reasons.append(f"context.{key}")

    clinical = obj.get("clinical")
    if clinical is not None:
        expected_clinical = set(CLINICAL_SCALARS) | set(CLINICAL_LISTS)
        if not isinstance(clinical, Mapping):
            reasons.append("clinical_object")
        elif set(clinical) != expected_clinical:
            reasons.append("clinical_keys")
        else:
            if not _node_list(clinical["lesion_types"], allowed=LESION):
                reasons.append("clinical.lesion_types")
            if not _node(
                clinical["inflammation_level"],
                expected=str,
                allowed=INFLAMMATION,
            ):
                reasons.append("clinical.inflammation_level")
            if not _node_list(
                clinical["lesion_distribution"], allowed=DISTRIBUTION
            ):
                reasons.append("clinical.lesion_distribution")
            has_signal = bool(
                clinical.get("lesion_types")
                or clinical.get("lesion_distribution")
                or (
                    isinstance(clinical.get("inflammation_level"), Mapping)
                    and clinical["inflammation_level"].get("value")
                    not in {None, "unknown", "none"}
                )
            )
            if not has_signal:
                reasons.append("clinical_empty")

    return not reasons, reasons
