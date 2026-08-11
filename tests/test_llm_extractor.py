from __future__ import annotations

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from acne_llm.chat.session import get_session_store
from acne_llm.chat.intake import (
    IntakeResult,
    run_intake,
)
from acne_llm.chat.fallback.llm_extractor import (
    ExtractorFallback,
    LLMExtractor,
    _to_extraction_confidence,
    _to_user_input,
)
from acne_llm.chat.session import ConversationTurn
from acne_llm.schemas import UserInput


def _payload() -> dict:
    return {
        "context": {
            "age": {"value": 22, "confidence": 0.91},
            "sex": {"value": "female", "confidence": 0.88},
            "skin_type": {"value": "oily", "confidence": 0.83},
            "is_pregnant": {"value": False, "confidence": 0.95},
            "is_breastfeeding": {"value": None, "confidence": 0.0},
            "duration_weeks": {"value": 8, "confidence": 0.72},
            "allergies": [
                {"value": "benzoyl_peroxide", "confidence": 0.84},
            ],
            "current_products": [
                {"value": "BHA", "confidence": 0.78},
            ],
            "medications": [
                {"value": "doxycycline", "confidence": 0.81},
            ],
        },
        "clinical": {
            "lesion_types": [
                {"value": "papule", "confidence": 0.87},
                {"value": "not_a_lesion", "confidence": 0.99},
            ],
            "inflammation_level": {"value": "moderate", "confidence": 0.76},
            "lesion_distribution": [
                {"value": "cheeks", "confidence": 0.89},
                {"value": "cheek", "confidence": 0.99},
            ],
            "scarring_signs": [
                {"value": "sẹo lõm", "confidence": 0.7},
            ],
            "hormonal_factors": [
                {"value": "menstrual_cycle", "confidence": 0.73},
            ],
            "treatment_goals": [
                {"value": "giảm mụn viêm", "confidence": 0.8},
            ],
        },
    }


class _Backend:
    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response if response is not None else json.dumps(_payload())
        self.error = error
        self.calls: list[dict] = []

    def generate_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        return None


def _extractor(payload: dict | None = None) -> tuple[LLMExtractor, _Backend]:
    backend = _Backend(json.dumps(payload or _payload(), ensure_ascii=False))
    return LLMExtractor(backend, "acne-extractor:1.5b", 20.0), backend


def _container(*, extractor_mode: str, llm_extractor=None):
    return SimpleNamespace(
        rag_ready=False,
        settings=SimpleNamespace(
            extractor_mode=extractor_mode,
            extract_min_field_conf=0.60,
        ),
        llm_extractor=llm_extractor,
        semantic_router=None,
        guardrails=SimpleNamespace(
            pre_check=lambda user: None,
            scope_check=lambda user: None,
        ),
        clinical_planner=None,
        session_store=get_session_store(),
    )


def test_valid_json_builds_user_input_and_drops_unknown_enums():
    data = _payload()

    user = _to_user_input(data, "em 22 tuổi bị mụn viêm ở má", "llm_only")

    assert isinstance(user, UserInput)
    assert user.description == "em 22 tuổi bị mụn viêm ở má"
    assert user.mode == "llm_only"
    assert user.context.age == 22
    assert user.context.skin_type == "oily"
    assert user.context.allergies == ["benzoyl_peroxide"]
    assert user.clinical is not None
    assert user.clinical.lesion_types == ["papule"]
    assert user.clinical.lesion_distribution == ["cheeks"]


def test_confidence_maps_every_completeness_field_with_llm_method():
    confidence = _to_extraction_confidence(_payload())

    completeness_fields = (
        "lesion_types",
        "distribution",
        "inflammation",
        "is_pregnant",
        "is_breastfeeding",
        "allergies",
        "skin_type",
        "age",
        "duration_weeks",
        "hormonal_factors",
        "scarring_signs",
        "treatment_goals",
    )
    assert all(confidence.field(name) is not None for name in completeness_fields)
    assert confidence.age.is_confident(0.9)
    assert confidence.is_pregnant.is_confident(0.9)
    assert confidence.age.method == "llm"
    assert confidence.lesion_types.confident_values(0.8) == ["papule"]
    assert confidence.lesion_types.items[0].method == "llm"
    assert confidence.red_flags.items == ()


def test_extractor_result_contains_fields_only_and_never_a_route():
    extractor, _ = _extractor()

    result = extractor.run(
        clean_text="em 22 tuổi bị mụn viêm ở má",
        clean_text_no_accent="em 22 tuoi bi mun viem o ma",
        mode="llm_only",
        history=[],
    )

    assert result.user.context.age == 22
    assert not hasattr(result, "route")


@pytest.mark.parametrize(
    "backend",
    [
        _Backend("not json"),               # không có JSON object
        _Backend("[1, 2, 3]"),              # root không phải object
        _Backend(error=TimeoutError("extractor timeout")),
    ],
)
def test_model_json_contract_and_timeout_failures_raise_extractor_fallback(backend):
    extractor = LLMExtractor(backend, "acne-extractor:1.5b", 20.0)

    with pytest.raises(ExtractorFallback):
        extractor.run(
            clean_text="tôi bị mụn",
            clean_text_no_accent="toi bi mun",
            mode="llm_only",
            history=[],
        )


def test_partial_and_flat_json_parse_without_fallback():
    """D (khoan dung): JSON phẳng / thiếu key không còn fallback — parse từng phần."""
    backend = _Backend(json.dumps({"context": {"age": 22, "sex": "female"}, "clinical": {}}))
    extractor = LLMExtractor(backend, "acne-extractor:1.5b", 20.0)
    result = extractor.run(
        clean_text="nu 22 tuoi bi mun",
        clean_text_no_accent="nu 22 tuoi bi mun",
        mode="llm_only",
        history=[],
    )
    assert result.user.context.age == 22
    assert result.user.context.sex == "female"
    assert result.user.context.skin_type is None


def test_intaker_la_nguon_duy_nhat_cho_thai_ky():
    """Regex KHONG con ghi de model.

    Truoc day mot lop regex quet raw text roi ep is_pregnant=True voi confidence
    1.0. Da bo: no doc duoc chu chu khong doc duoc ngu nghia -- "truoc em mang
    thai nhung gio sinh roi" va "chi toi dang mang thai" deu bi no gan cho nguoi
    dung. Phu dinh, thi va quy chu ngu tra ve cho intaker.
    """
    data = _payload()
    data["context"]["is_pregnant"] = {"value": False, "confidence": 0.93}
    extractor, _ = _extractor(data)

    result = extractor.run(
        clean_text="em đang mang thai và bị mụn viêm",
        clean_text_no_accent="em dang mang thai va bi mun viem",
        mode="llm_only",
        history=[],
    )

    # Van ban co chu "mang thai" nhung model noi False -> theo model.
    assert result.user.context.is_pregnant is False
    assert result.confidence.is_pregnant.value is False


def test_thai_ky_theo_dung_gia_tri_model_tra_ve():
    data = _payload()
    data["context"]["is_pregnant"] = {"value": True, "confidence": 0.88}
    extractor, _ = _extractor(data)

    result = extractor.run(
        clean_text="em bầu 5 tháng, mụn nhiều ở cằm",
        clean_text_no_accent="em bau 5 thang, mun nhieu o cam",
        mode="llm_only",
        history=[],
    )

    assert result.user.context.is_pregnant is True
    assert result.confidence.is_pregnant.confidence == 0.88


def test_thuoc_va_di_ung_khong_con_duoc_regex_bo_sung():
    """Model bo sot thi coi nhu khong co -- khong con lop regex OR vao."""
    data = _payload()
    data["context"]["medications"] = []
    data["context"]["allergies"] = []
    extractor, _ = _extractor(data)

    result = extractor.run(
        clean_text="tôi đang uống doxycycline và bị dị ứng với benzoyl peroxide",
        clean_text_no_accent="toi dang uong doxycycline va bi di ung voi benzoyl peroxide",
        mode="llm_only",
        history=[],
    )

    assert result.user.context.medications == []
    assert result.user.context.allergies == []


def test_prompt_contains_only_three_latest_short_history_turns():
    extractor, backend = _extractor()
    history = [
        ConversationTurn(role="user", content="oldest turn must disappear"),
        ConversationTurn(role="assistant", content="assistant context"),
        ConversationTurn(role="user", content="recent user context"),
        ConversationTurn(role="assistant", content="x" * 500),
    ]

    extractor.run(
        clean_text="mụn này nên làm gì",
        clean_text_no_accent="mun nay nen lam gi",
        mode="llm_only",
        history=history,
    )

    prompt = backend.calls[0]["user"]
    response_schema = backend.calls[0]["response_format"]
    assert "oldest turn must disappear" not in prompt
    assert "assistant context" in prompt
    assert "recent user context" in prompt
    assert "x" * 301 not in prompt
    assert set(response_schema["properties"]) == {"context", "clinical"}
    assert "intent" not in response_schema["properties"]
    assert response_schema["additionalProperties"] is False


def test_run_intake_falls_back_to_same_rule_path_when_extractor_fails():
    class _FailingExtractor:
        def run(self, **kwargs):
            raise ExtractorFallback("broken model output")

    message = "tôi 22 tuổi da dầu bị mụn ở cằm"
    llm_result = run_intake(
        _container(extractor_mode="llm", llm_extractor=_FailingExtractor()),
        message,
    )
    rule_result = run_intake(_container(extractor_mode="rule"), message)

    assert llm_result.user.model_dump() == rule_result.user.model_dump()
    assert llm_result.route_decision == rule_result.route_decision
    assert llm_result.extraction_confidence == rule_result.extraction_confidence


def test_run_intake_uses_llm_objects_without_bypassing_normal_gates():
    extractor, _ = _extractor()

    result = run_intake(
        _container(extractor_mode="llm", llm_extractor=extractor),
        "em 22 tuổi bị mụn viêm ở má",
    )

    assert isinstance(result, IntakeResult)
    assert result.scope_refusal is None
    assert result.effective_mode == "llm_only"
    assert result.route_decision is not None
    assert result.route_decision.source == "rule"
    assert result.route_decision.reason_code == "personal_acne_case"
    assert result.user.context.age == 22
    assert result.extraction_confidence is not None
    assert result.extraction_confidence.age.method == "llm"


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        (
            "em 22 tuổi da dầu bị mụn viêm 2 bên má gần 2 tháng, "
            "benzoyl peroxide có nên dùng không",
            "advise",
        ),
        (
            "benzoyl peroxide với tretinoin khác nhau thế nào",
            "knowledge",
        ),
        (
            "con em 2 tuổi bị nổi mụn sữa ở má phải làm sao",
            "advise",
        ),
    ],
)
def test_run_intake_routes_independently_from_field_extractor(
    message,
    expected_intent,
):
    extractor, _ = _extractor()

    result = run_intake(
        _container(extractor_mode="llm", llm_extractor=extractor),
        message,
    )

    assert result.route_decision is not None
    assert result.route_decision.primary_intent == expected_intent
    assert result.route_decision.source == "rule"


def test_low_confidence_model_fields_cannot_change_pre_extraction_route():
    data = deepcopy(_payload())
    for node in data["clinical"]["lesion_types"]:
        node["confidence"] = 0.20
    data["clinical"]["inflammation_level"]["confidence"] = 0.20
    for node in data["clinical"]["lesion_distribution"]:
        node["confidence"] = 0.20
    for name in ("scarring_signs", "hormonal_factors", "treatment_goals"):
        for node in data["clinical"][name]:
            node["confidence"] = 0.20
    extractor, _ = _extractor(data)

    result = run_intake(
        _container(extractor_mode="llm", llm_extractor=extractor),
        "mụn viêm",
    )

    assert result.user.clinical is not None
    assert result.route_decision is not None
    assert result.route_decision.primary_intent == "advise"
    assert result.route_decision.reason_code == "personal_acne_case"


def test_unknown_scalar_enum_is_dropped_before_pydantic_validation():
    data = deepcopy(_payload())
    data["context"]["skin_type"]["value"] = "very_oily"

    user = _to_user_input(data, "da em rất dầu", "llm_only")
    confidence = _to_extraction_confidence(data)

    assert user.context.skin_type is None
    assert confidence.skin_type.value is None
