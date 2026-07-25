"""Legacy dedicated LLM extractor adapter.

The parsing contract lives in :mod:`acne_llm.chat._intake_parse` so the
unified adapter and this rollback path share one implementation.
"""
from __future__ import annotations

from collections.abc import Mapping
import json

from ...llm.ollama_backend import OllamaBackend
from .._intake_parse import (
    ExtractorFallback,
    LLMExtractResult,
    _OLLAMA_JSON_SCHEMA,
    _extract_json,
    _to_extraction_confidence,
    _to_user_input,
    _validate_contract,
)


_RUNTIME_SYSTEM = (
    "Bạn là bộ trích xuất dữ liệu cho hội thoại tư vấn mụn. "
    "Chỉ trả về đúng một JSON theo contract của model, không tư vấn hay giải thích."
)


class LLMExtractor:
    """Call the former dedicated Ollama extractor and adapt its JSON contract."""

    def __init__(self, backend: OllamaBackend, model: str, timeout: float):
        self._llm = backend
        self._model = model
        self._timeout = float(timeout)

    @property
    def model(self) -> str:
        return self._model

    def run(
        self,
        *,
        clean_text: str,
        clean_text_no_accent: str,
        mode: str,
        history: list,
    ) -> LLMExtractResult:
        try:
            raw = self._call(clean_text, clean_text_no_accent, history)
            data = json.loads(_extract_json(raw))
            _validate_contract(data)
            user = _to_user_input(data, clean_text, mode)
            confidence = _to_extraction_confidence(data, clean_text=clean_text)
            return LLMExtractResult(user=user, confidence=confidence)
        except ExtractorFallback:
            raise
        except Exception as exc:
            raise ExtractorFallback(
                f"{self._model} extraction failed: {type(exc).__name__}: {exc}"
            ) from exc

    def _call(self, clean_text: str, clean_text_no_accent: str, history: list) -> str:
        prompt = _build_prompt(clean_text, clean_text_no_accent, history)
        return self._llm.generate_text(
            system=_RUNTIME_SYSTEM,
            user=prompt,
            temperature=0.0,
            response_format=_OLLAMA_JSON_SCHEMA,
        )

    def close(self) -> None:
        close = getattr(self._llm, "close", None)
        if callable(close):
            close()


def _build_prompt(clean_text: str, clean_text_no_accent: str, history: list) -> str:
    """Serialize current text plus the latest three short role/content turns."""
    short_history: list[dict[str, str]] = []
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
            short_history.append({"role": role, "content": compact})

    payload = {
        "clean_text": clean_text,
        "clean_text_no_accent": clean_text_no_accent,
        "history": short_history,
    }
    return (
        "Trích xuất INPUT_JSON sau theo đúng schema đã quy định. "
        "Chỉ xuất một JSON object.\nINPUT_JSON:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )
