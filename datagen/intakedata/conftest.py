"""Shared pytest fixtures for the isolated intakedata module."""
from __future__ import annotations

from typing import Any

import pytest

from .anchor import load_anchor
from .config import Config
from .generator import to_record


def populated_context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "age": {"value": 22, "confidence": 0.97},
        "sex": {"value": "female", "confidence": 0.96},
        "skin_type": {"value": "oily", "confidence": 0.92},
        "is_pregnant": None,
        "is_breastfeeding": None,
        "duration_weeks": {"value": 8, "confidence": 0.9},
        "allergies": [],
        "current_products": [],
        "medications": [],
    }
    context.update(overrides)
    return context


def clinical_payload() -> dict[str, Any]:
    return {
        "lesion_types": [{"value": "papule", "confidence": 0.93}],
        "inflammation_level": {"value": "moderate", "confidence": 0.85},
        "lesion_distribution": [{"value": "cheeks", "confidence": 0.9}],
    }


@pytest.fixture
def anchor() -> str:
    return load_anchor(Config())


@pytest.fixture
def make_record(anchor: str):
    def factory(
        case_type: str = "advise_selfreport_simple",
        *,
        user: str = "Em 22 tuổi, da dầu và có mụn đỏ ở má.",
        payload: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        intent = (
            "knowledge"
            if case_type.startswith("knowledge_")
            else "clarify"
            if case_type.startswith("clarify_") or case_type == "glue_greeting_thanks"
            else "reject"
            if case_type.startswith("reject_")
            else "advise"
        )
        empty = (
            case_type.startswith(("knowledge_", "reject_"))
            or case_type == "glue_greeting_thanks"
        )
        value = payload or {
            "intent": intent,
            "confidence": 0.95 if intent != "clarify" else 0.62,
            "description": user,
            "context": {} if empty else populated_context(),
            "clinical": None if empty else clinical_payload(),
        }
        record = to_record(
            {
                "case_type": case_type,
                "quota": 1,
                "style_hint": "",
                "intent_hint": intent,
                "behavior": "",
            },
            {
                "user_turn": user,
                "history": history or [],
                "assistant_json": value,
            },
            anchor,
            source="test",
        )
        record["meta"]["judged"] = True
        return record

    return factory
