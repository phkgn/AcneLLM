from __future__ import annotations

import json

import pytest

from acne_llm.chat.routing.llm_router import LLMRouter, RouterFallback


class _Backend:
    def __init__(self, response: str = "", error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []
        self.closed = False

    def generate_text(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True


def _router(response: str = "", error: Exception | None = None):
    backend = _Backend(response=response, error=error)
    return LLMRouter(backend, "acnellm-intent", 8.0), backend


def _input_payload(call: dict) -> dict:
    return json.loads(call["user"].split("INPUT_JSON:\n", 1)[1])


def test_valid_json_builds_llm_route_and_uses_constrained_decoding():
    router, backend = _router('{"intent":"advise","confidence":0.93}')

    decision = router.classify("Tôi bị mụn ở má", [])

    assert decision.primary_intent == "advise"
    assert decision.confidence == 0.93
    assert decision.source == "llm"
    assert decision.reason_code == "llm_router"
    assert backend.calls[0]["temperature"] == 0.0
    assert backend.calls[0]["response_format"]["required"] == [
        "intent",
        "confidence",
    ]


def test_parser_accepts_extra_keys_and_coerces_numeric_confidence():
    router, _ = _router(
        '{"intent":" KNOWLEDGE ","confidence":"1.4","unused":"ignored"}'
    )

    decision = router.classify("Retinol là gì?", [])

    assert decision.primary_intent == "knowledge"
    assert decision.confidence == 1.0


def test_prompt_sends_no_accent_text_and_only_latest_three_valid_turns():
    router, backend = _router('{"intent":"advise","confidence":0.9}')
    history = [
        {"role": "user", "content": "turn zero"},
        {"role": "assistant", "content": "turn one"},
        {"role": "tool", "content": "must be ignored"},
        {"role": "user", "content": "turn two"},
        {"role": "assistant", "content": "turn three"},
    ]

    router.classify("ớt bôi lên má trị được không", history)

    payload = _input_payload(backend.calls[0])
    assert payload["clean_text"] == "ớt bôi lên má trị được không"
    assert payload["clean_text_no_accent"] == "ot boi len ma tri duoc khong"
    assert payload["history"] == [
        {"role": "user", "content": "turn two"},
        {"role": "assistant", "content": "turn three"},
    ]


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        '{"intent":"personal_consult","confidence":0.9}',
        '{"intent":"advise"}',
        '{"intent":"advise","confidence":"unknown"}',
    ],
)
def test_invalid_or_out_of_enum_output_requests_fallback(response: str):
    router, _ = _router(response)

    with pytest.raises(RouterFallback):
        router.classify("mụn ở cằm", [])


def test_backend_timeout_requests_fallback():
    router, _ = _router(error=TimeoutError("router timed out"))

    with pytest.raises(RouterFallback, match="TimeoutError"):
        router.classify("mụn ở cằm", [])


@pytest.mark.parametrize(
    ("message", "history", "response", "expected"),
    [
        (
            "My acne is getting worse and hurts. What should I do?",
            [],
            '{"intent":"advise","confidence":0.96}',
            "advise",
        ),
        (
            "chin",
            [
                {"role": "user", "content": "I have painful facial acne."},
                {"role": "assistant", "content": "Where is it concentrated?"},
            ],
            '{"intent":"advise","confidence":0.93}',
            "advise",
        ),
        (
            "ớt bôi lên má trị được không",
            [{"role": "user", "content": "Mình đang bị mụn viêm ở má."}],
            '{"intent":"advise","confidence":0.95}',
            "advise",
        ),
        (
            "goku với vegeta ai mạnh hơn",
            [],
            '{"intent":"reject","confidence":0.98}',
            "reject",
        ),
    ],
)
def test_mocked_behavior_cases_route_to_repository_enum(
    message: str,
    history: list,
    response: str,
    expected: str,
):
    router, backend = _router(response)

    decision = router.classify(message, history)

    assert decision.primary_intent == expected
    assert _input_payload(backend.calls[0])["history"] == history[-3:]


def test_close_releases_dedicated_backend():
    router, backend = _router('{"intent":"clarify","confidence":0.5}')

    router.close()

    assert backend.closed is True
