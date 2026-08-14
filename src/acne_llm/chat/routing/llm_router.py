"""Generative LLM-first intent router for chat intake.

The router receives only the cleaned current turn and up to three recent
conversation turns.  Any transport, model, JSON, or contract failure is
converted to :class:`RouterFallback` so intake can use the semantic router and
then the legacy deterministic router without changing pipeline order.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from ...llm.ollama_backend import OllamaBackend
from .intent_router import PrimaryIntent, RouteDecision
from ..preprocess import strip_accents


_ALLOWED_INTENTS: frozenset[str] = frozenset(
    {"advise", "knowledge", "clarify", "reject"}
)
_RUNTIME_SYSTEM = (
    "Bạn là bộ định tuyến ý định cho hệ tư vấn da mụn. "
    "Chỉ trả về đúng một JSON object theo schema, không tư vấn hay giải thích."
)
_OLLAMA_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": sorted(_ALLOWED_INTENTS),
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
    },
    "required": ["intent", "confidence"],
    "additionalProperties": False,
}


class RouterFallback(Exception):
    """Signal that intake must fall back to semantic, then rule routing."""


class LLMRouter:
    """Call a dedicated generative router and adapt its flat JSON output."""

    def __init__(self, backend: OllamaBackend, model: str, timeout: float):
        self._llm = backend
        self._model = model
        self._timeout = float(timeout)

    @property
    def model(self) -> str:
        return self._model

    @property
    def timeout(self) -> float:
        return self._timeout

    def classify(self, clean_text: str, history: list) -> RouteDecision:
        try:
            raw = self._llm.generate_text(
                system=_RUNTIME_SYSTEM,
                user=_build_prompt(clean_text, history),
                temperature=0.0,
                response_format=_OLLAMA_JSON_SCHEMA,
            )
            data = json.loads(_extract_json(raw))
            intent = _coerce_intent(data)
            confidence = _coerce_confidence(data)
            return RouteDecision(
                primary_intent=intent,
                confidence=confidence,
                source="llm",
                reason_code="llm_router",
            )
        except RouterFallback:
            raise
        except Exception as exc:
            raise RouterFallback(
                f"{self._model} routing failed: {type(exc).__name__}: {exc}"
            ) from exc

    def close(self) -> None:
        close = getattr(self._llm, "close", None)
        if callable(close):
            close()


def _short_history(history: list) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for turn in list(history or [])[-3:]:
        if isinstance(turn, Mapping):
            role = turn.get("role")
            content = turn.get("content")
        else:
            role = getattr(turn, "role", None)
            content = getattr(turn, "content", None)
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        compact = " ".join(content.split())[:300]
        if compact:
            turns.append({"role": role, "content": compact})
    return turns


def _build_prompt(clean_text: str, history: list) -> str:
    if not isinstance(clean_text, str) or not clean_text.strip():
        raise RouterFallback("router clean_text must be non-empty")
    payload = {
        "clean_text": clean_text,
        "clean_text_no_accent": strip_accents(clean_text),
        "history": _short_history(history),
    }
    return (
        "Phân loại INPUT_JSON sau. Chỉ xuất một JSON object.\nINPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _extract_json(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise RouterFallback("router returned an empty non-text response")
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RouterFallback("router response does not contain a JSON object")
    return text[start : end + 1]


def _coerce_intent(data: Any) -> PrimaryIntent:
    if not isinstance(data, Mapping):
        raise RouterFallback("router root is not a JSON object")
    raw = data.get("intent")
    if not isinstance(raw, str):
        raise RouterFallback("router intent is missing or not text")
    intent = raw.strip().lower()
    if intent not in _ALLOWED_INTENTS:
        raise RouterFallback(f"router intent is outside the repository enum: {raw!r}")
    return intent  # type: ignore[return-value]


def _coerce_confidence(data: Mapping[str, Any]) -> float:
    raw = data.get("confidence")
    if isinstance(raw, bool):
        raise RouterFallback("router confidence must be numeric")
    try:
        confidence = float(raw)
    except (TypeError, ValueError) as exc:
        raise RouterFallback("router confidence is missing or invalid") from exc
    if confidence != confidence:
        raise RouterFallback("router confidence is NaN")
    return max(0.0, min(1.0, confidence))
