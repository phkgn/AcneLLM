from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from acne_llm.chat.intake import run_intake
from acne_llm.chat.fallback.llm_extractor import ExtractorFallback
from acne_llm.chat.fallback.llm_router import RouterFallback
from acne_llm.chat.session import ConversationTurn
from acne_llm.chat.unified_intake import (
    UnifiedIntake,
    _RUNTIME_SYSTEM,
)
from acne_llm.config import Settings


def _node(value, confidence: float = 0.9) -> dict:
    return {"value": value, "confidence": confidence}


def _payload(
    description: str = "em 22 tuổi da dầu bị mụn viêm ở má",
    *,
    intent: str = "advise",
) -> dict:
    return {
        "intent": intent,
        "confidence": 0.94,
        "description": description,
        "context": {
            "age": _node(22),
            "sex": _node("female"),
            "skin_type": _node("oily"),
            "is_pregnant": _node(False),
            "is_breastfeeding": None,
            "duration_weeks": _node(8, 0.82),
            "allergies": [],
            "current_products": [_node("adapalene")],
            "medications": [],
        },
        "clinical": {
            "lesion_types": [_node("papule")],
            "inflammation_level": _node("moderate"),
            "lesion_distribution": [_node("cheeks")],
        },
    }


def _empty_payload(description: str, intent: str) -> dict:
    return {
        "intent": intent,
        "confidence": 0.91,
        "description": description,
        "context": {},
        "clinical": None,
    }


def _current_product_payload(description: str, product: str) -> dict:
    return {
        "intent": "advise",
        "confidence": 0.93,
        "description": description,
        "context": {
            "age": None,
            "sex": None,
            "skin_type": None,
            "is_pregnant": None,
            "is_breastfeeding": None,
            "duration_weeks": None,
            "allergies": [],
            "current_products": [_node(product)],
            "medications": [],
        },
        "clinical": None,
    }


class _Backend:
    def __init__(self, response: str = "", error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []
        self.close_count = 0

    def generate_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.close_count += 1


def _adapter(payload: dict | None = None) -> tuple[UnifiedIntake, _Backend]:
    response = json.dumps(payload or _payload(), ensure_ascii=False)
    backend = _Backend(response=response)
    return UnifiedIntake(backend, "acne-intake", 60.0), backend


def test_valid_unified_json_builds_route_and_user_with_one_inference():
    message = "em 22 tuổi da dầu bị mụn viêm ở má"
    adapter, backend = _adapter(_payload(message))

    decision = adapter.classify(message, [])
    extracted = adapter.run(
        clean_text=message,
        clean_text_no_accent="em 22 tuoi da dau bi mun viem o ma",
        mode="llm_only",
        history=[],
    )

    assert decision.primary_intent == "advise"
    assert decision.confidence == 0.94
    assert decision.source == "llm"
    assert decision.reason_code == "unified_intake"
    assert extracted.user.context.age == 22
    assert extracted.user.context.skin_type == "oily"
    assert extracted.user.clinical is not None
    assert extracted.user.clinical.lesion_types == ["papule"]
    assert extracted.confidence.age.method == "llm"
    assert len(backend.calls) == 1
    assert backend.calls[0]["temperature"] == 0.0
    assert backend.calls[0]["response_format"] == "json"


def test_runtime_anchor_is_byte_identical_to_training_anchor():
    canonical = Path("datagen/intakedata/system_prompt.canonical.txt").read_text(
        encoding="utf-8"
    )

    assert _RUNTIME_SYSTEM == canonical


def test_nested_unknown_enum_is_dropped_before_pydantic_validation():
    message = "da em rất dầu"
    payload = _payload(message)
    payload["context"]["skin_type"] = _node("very_oily")
    payload["clinical"]["lesion_types"].append(_node("not_a_lesion"))
    adapter, _ = _adapter(payload)

    result = adapter.run(
        clean_text=message,
        clean_text_no_accent="da em rat dau",
        mode="llm_only",
        history=[],
    )

    assert result.user.context.skin_type is None
    assert result.user.clinical is not None
    assert result.user.clinical.lesion_types == ["papule"]


@pytest.mark.parametrize(
    "response",
    [
        "",
        "not json",
        "Here is the answer with no object.",
        "[]",
        "{}",
        '{"intent":"advise"}',
        json.dumps({**_payload(), "intent": "personal_consult"}),
        json.dumps({**_payload(), "confidence": 1.1}),
        json.dumps({**_payload(), "extra": "not allowed"}),
        json.dumps({**_payload(), "context": {"age": _node(22)}}),
        json.dumps(
            {
                **_payload(),
                "context": {
                    **_payload()["context"],
                    "age": _node(["not", "an", "integer"]),
                },
            }
        ),
        json.dumps(
            {
                **_payload(),
                "clinical": {
                    **_payload()["clinical"],
                    "lesion_types": ["papule"],
                },
            }
        ),
    ],
)
def test_bad_output_always_becomes_interface_specific_fallback(response: str):
    router = UnifiedIntake(_Backend(response=response), "acne-intake", 60.0)
    extractor = UnifiedIntake(_Backend(response=response), "acne-intake", 60.0)

    with pytest.raises(RouterFallback):
        router.classify("mụn ở má", [])
    with pytest.raises(ExtractorFallback):
        extractor.run(
            clean_text="mụn ở má",
            clean_text_no_accent="mun o ma",
            mode="llm_only",
            history=[],
        )


@pytest.mark.parametrize("error", [TimeoutError("timeout"), RuntimeError("transport")])
def test_backend_failures_never_escape_as_raw_exceptions(error: Exception):
    router = UnifiedIntake(_Backend(error=error), "acne-intake", 60.0)
    extractor = UnifiedIntake(_Backend(error=error), "acne-intake", 60.0)

    with pytest.raises(RouterFallback):
        router.classify("mụn ở má", [])
    with pytest.raises(ExtractorFallback):
        extractor.run(
            clean_text="mụn ở má",
            clean_text_no_accent="mun o ma",
            mode="llm_only",
            history=[],
        )


@pytest.mark.parametrize("clean_text", ["", " ", "x" * 4_001])
def test_invalid_input_falls_back_without_calling_model(clean_text: str):
    payload = _empty_payload(clean_text or "valid", "clarify")
    router_backend = _Backend(json.dumps(payload))
    extractor_backend = _Backend(json.dumps(payload))
    router = UnifiedIntake(router_backend, "acne-intake", 60.0)
    extractor = UnifiedIntake(extractor_backend, "acne-intake", 60.0)

    with pytest.raises(RouterFallback):
        router.classify(clean_text, [])
    with pytest.raises(ExtractorFallback):
        extractor.run(
            clean_text=clean_text,
            clean_text_no_accent=clean_text,
            mode="llm_only",
            history=[],
        )

    assert router_backend.calls == []
    assert extractor_backend.calls == []


def test_pydantic_failure_is_converted_to_extractor_fallback():
    message = "mụn ở má"
    adapter, _ = _adapter(_payload(message))

    with pytest.raises(ExtractorFallback):
        adapter.run(
            clean_text=message,
            clean_text_no_accent="mun o ma",
            mode="not-a-valid-mode",
            history=[],
        )


def test_long_history_is_capped_but_still_injected_into_prompt():
    message = "mụn viêm ở má"
    adapter, backend = _adapter(_payload(message))
    history = [
        ConversationTurn(
            role="user" if index % 2 == 0 else "assistant",
            content=f"turn-{index}-" + "x" * 500,
        )
        for index in range(12)
    ]

    adapter.classify(message, history)

    prompt = backend.calls[0]["user"]
    history_json = prompt.split("FOLLOWUP_HISTORY_JSON:\n", 1)[1].split(
        "\nCURRENT_TURN:\n", 1
    )[0]
    sent_history = json.loads(history_json)
    assert len(sent_history) == 6
    assert all(len(turn["content"]) == 300 for turn in sent_history)
    assert prompt.endswith(message)


def test_plain_statement_after_answer_keeps_history():
    """Turn 2 kiểu 'tôi đã thử X rồi vẫn không đỡ' phải thấy được turn 1."""
    message = "tôi đã thử tắm kỹ và kì tay và lưng rồi vẫn k khá lên được bao nhiêu"
    adapter, backend = _adapter(_empty_payload(message, "knowledge"))
    history = [
        ConversationTurn(role="user", content="tôi 20 tuổi hay bị mụn ở lưng"),
        ConversationTurn(role="assistant", content="Mụn lưng thường do...", mode="hybrid"),
    ]

    adapter.classify(message, history)

    assert "FOLLOWUP_HISTORY_JSON:" in backend.calls[0]["user"]
    assert "20 tuổi" in backend.calls[0]["user"]


def test_real_followup_uses_the_five_message_window():
    message = "Vậy dùng sáng hay tối?"
    adapter, backend = _adapter(_empty_payload(message, "knowledge"))
    history = [
        ConversationTurn(role="user", content="oldest"),
        ConversationTurn(role="assistant", content="old assistant"),
        ConversationTurn(role="user", content="em đang dùng adapalene"),
        ConversationTurn(
            role="assistant",
            content="x" * 500,
            mode="clarify",
            turn_type="clarify",
        ),
    ]

    adapter.classify(message, history)

    prompt = backend.calls[0]["user"]
    history_json = prompt.split("FOLLOWUP_HISTORY_JSON:\n", 1)[1].split(
        "\nCURRENT_TURN:\n", 1
    )[0]
    sent_history = json.loads(history_json)
    assert [turn["content"] for turn in sent_history[:3]] == [
        "oldest",
        "old assistant",
        "em đang dùng adapalene",
    ]
    assert len(sent_history) == 4
    assert len(sent_history[-1]["content"]) == 300
    assert prompt.endswith(message)


def test_malformed_followup_history_falls_back_before_inference():
    message = "Vậy còn cái này?"
    backend = _Backend(json.dumps(_empty_payload(message, "knowledge")))
    adapter = UnifiedIntake(backend, "acne-intake", 60.0)
    history = [
        {"role": "assistant", "content": "trước đó", "mode": "clarify"},
        {"role": "tool", "content": "untrusted"},
    ]

    with pytest.raises(RouterFallback):
        adapter.classify(message, history)

    assert backend.calls == []


def test_malformed_recent_history_is_rejected_even_when_not_a_followup():
    message = "mụn viêm ở má"
    backend = _Backend(json.dumps(_payload(message)))
    adapter = UnifiedIntake(backend, "acne-intake", 60.0)

    with pytest.raises(RouterFallback):
        adapter.classify(message, [{"role": "tool", "content": "untrusted"}])

    assert backend.calls == []


def test_close_is_idempotent_for_shared_router_extractor_instance():
    adapter, backend = _adapter()

    adapter.close()
    adapter.close()

    assert backend.close_count == 1


class _SessionStore:
    def get_history(self, session_id):
        return []

    def get_user_context(self, session_id):
        return {}

    def get_asked_fields(self, session_id):
        return set()


def _container(adapter: UnifiedIntake):
    return SimpleNamespace(
        rag_ready=False,
        settings=SimpleNamespace(
            intake_mode="unified",
            extractor_mode="llm",
            extract_min_field_conf=0.60,
        ),
        llm_router=adapter,
        llm_extractor=adapter,
        semantic_router=None,
        guardrails=SimpleNamespace(
            pre_check=lambda user: None,
            scope_check=lambda user: None,
        ),
        session_store=_SessionStore(),
    )


@pytest.mark.parametrize(
    ("case", "message", "payload", "expected_intent"),
    [
        (
            "advise",
            "em 22 tuổi da dầu bị mụn viêm ở má",
            _payload("em 22 tuổi da dầu bị mụn viêm ở má"),
            "advise",
        ),
        (
            "knowledge",
            "BHA là gì?",
            _empty_payload("BHA là gì?", "knowledge"),
            "knowledge",
        ),
        (
            "negation",
            "em đã ngưng tretinoin, hiện đang dùng adapalene",
            _current_product_payload(
                "em đã ngưng tretinoin, hiện đang dùng adapalene",
                "adapalene",
            ),
            "advise",
        ),
        (
            "reject",
            "viết mã giao dịch tiền số",
            _empty_payload("viết mã giao dịch tiền số", "reject"),
            "reject",
        ),
        (
            "clarify",
            "da em dạo này lạ lắm",
            _empty_payload("da em dạo này lạ lắm", "clarify"),
            "clarify",
        ),
    ],
)
def test_run_intake_integration_uses_unified_contract_without_crashing(
    case: str,
    message: str,
    payload: dict,
    expected_intent: str,
):
    payload = deepcopy(payload)
    adapter, backend = _adapter(payload)

    result = run_intake(_container(adapter), message)

    assert result.route_decision is not None
    assert result.route_decision.primary_intent == expected_intent
    assert result.route_decision.reason_code == "unified_intake"
    assert len(backend.calls) == 1
    if case == "advise":
        assert result.user.context.age == 22
    if case == "negation":
        assert result.user.context.current_products == ["adapalene"]
        assert "tretinoin" not in result.user.context.current_products


def test_unified_remains_default_and_legacy_adapters_live_in_fallback_package():
    from acne_llm.chat.fallback.llm_extractor import LLMExtractor
    from acne_llm.chat.fallback.llm_router import LLMRouter

    assert Settings.model_fields["intake_mode"].default == "unified"
    assert LLMExtractor.__module__ == "acne_llm.chat.fallback.llm_extractor"
    assert LLMRouter.__module__ == "acne_llm.chat.fallback.llm_router"
