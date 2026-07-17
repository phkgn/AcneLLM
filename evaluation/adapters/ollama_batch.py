"""S0-S3 T3 adapter for the production prose prompt contract.

The adapter shares ``prepare_chat_turn`` with SSE, then performs one non-stream
``generate_text`` call for batch efficiency. It never requests a JSON schema.
"""
from __future__ import annotations

import re

from .base import SystemAdapter
from ._repo import build_eval_container, normalize_query


class _PromptCapture:
    """Delegate PromptBuilder while retaining the exact rendered user prompt."""

    def __init__(self, delegate, inline_citation: str = "off"):
        self._delegate = delegate
        self._inline_citation = inline_citation
        self.last_user_prompt = ""

    def build(self, *args, **kwargs):
        kwargs["inline_citation"] = self._inline_citation
        result = self._delegate.build(*args, **kwargs)
        if isinstance(result, tuple) and len(result) == 2:
            self.last_user_prompt = result[1]
        return result

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def _extract_retrieved_context(user_prompt: str) -> str:
    """Extract exact context from prose prompts; retain legacy XML support."""
    prompt = user_prompt or ""
    prose_match = re.search(
        r"\[TÀI LIỆU Y KHOA THAM KHẢO\]\s*(.*?)"
        r"(?=\n\[CÂU HỎI HIỆN TẠI\])",
        prompt,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if prose_match:
        return prose_match.group(1).strip()
    legacy_match = re.search(
        r"<retrieved_context>\s*(.*?)\s*</retrieved_context>",
        prompt,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return legacy_match.group(1).strip() if legacy_match else ""


class OllamaBatchAdapter(SystemAdapter):
    def prepare(self) -> None:
        cfg = self.config
        self.container = build_eval_container(cfg["model"], cfg.get("sampling"))
        if cfg.get("retrieval") and not self.container.rag_ready:
            raise RuntimeError(
                "KB chưa sẵn sàng (chroma_db + bm25_index.pkl) nhưng condition yêu cầu retrieval"
            )
        inline_mode = str(cfg.get("inline_citation", "off"))
        self.container.settings = self.container.settings.model_copy(
            update={"inline_citation": inline_mode}
        )
        self._prompt_capture = _PromptCapture(
            self.container.prompt,
            inline_citation=inline_mode,
        )
        self.container.prompt = self._prompt_capture
        assert self.container.llm.model == cfg["model"], (
            f"Model mismatch: container={self.container.llm.model} config={cfg['model']}"
        )
        assert not self.container.llm.fallback_model, "eval must disable fallback"

    def retrieve(self, sample: dict) -> dict:
        from acne_llm.chat.orchestrator import prepare_chat_turn

        self._prompt_capture.last_user_prompt = ""
        user, prepared_text = normalize_query(self.container, sample)
        requested_mode = "hybrid" if self.config.get("retrieval") else "llm_only"
        turn = prepare_chat_turn(
            self.container,
            sample["user_query"],
            requested_mode=requested_mode,
            session_id=None,
            user_override=user,
        )
        return {
            "turn": turn,
            "normalized_user": user,
            "prepared_clean_text": prepared_text.clean_text,
        }

    def generate(self, sample: dict, context: dict | None) -> dict:
        from acne_llm.chat.orchestrator import generate_prose

        if context is None:
            context = self.retrieve(sample)
        turn = context["turn"]
        normalized_user = context["normalized_user"]
        answer = generate_prose(self.container, turn)
        model_name = getattr(self.container.llm, "model", None)
        if model_name != self.config["model"]:
            raise RuntimeError(
                f"FALLBACK DETECTED: answered by {model_name!r}, expected {self.config['model']!r}"
            )

        used = [chunk.chunk_id for chunk in turn.retrieval.chunks] if turn.retrieval else []
        rendered_prompt = self._prompt_capture.last_user_prompt
        exact_context = _extract_retrieved_context(rendered_prompt)
        self._trace.update({
            "normalized_user": normalized_user.model_dump(mode="json"),
            "prepared_clean_text": context["prepared_clean_text"],
            "route_metadata": turn.route_metadata,
            "retrieval_query": turn.retrieval_query,
            "template": turn.template,
            "rendered_user_prompt": rendered_prompt,
            "prompt_chars": len(turn.system_prompt) + len(rendered_prompt),
            "prompt_contains_inline_citation_instruction": "Đặt [N]" in rendered_prompt,
            "prompt_contains_chunk_ref": "chunk_ref=" in rendered_prompt,
        })
        if used and exact_context:
            self._trace["faithfulness_context"] = exact_context
        if turn.retrieval is not None:
            self._trace["context_chunks"] = [
                {"chunk_id": chunk.chunk_id, "text": (chunk.text or "")[:1500]}
                for chunk in turn.retrieval.chunks
            ]
        return {
            "answer": answer,
            "structured": None,
            "used_chunks": used,
            "model_name": model_name,
        }

    def cleanup(self) -> None:
        try:
            self.container.llm.close()
        except Exception:
            pass
