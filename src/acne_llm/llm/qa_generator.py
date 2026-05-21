"""Generate conversational Q&A pairs from crawled documents for fine-tuning.

Uses any OpenAI-compatible API (DeepSeek, OpenAI, local vLLM, etc.)
or local Ollama backend.
Output: list[QASample] in ChatML format (system / user / assistant turns).
"""
from __future__ import annotations
import json
import uuid
import asyncio
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from ..schemas.kb import QASample, ChatMessage

# ── System prompt embedded in every training sample ──────────────────────────

_SYSTEM_VI = (
    "Bạn là trợ lý tư vấn da liễu chuyên về mụn trứng cá, được huấn luyện "
    "dựa trên kiến thức y khoa và da liễu học. Hãy trả lời ngắn gọn, chính xác, "
    "dễ hiểu. Khi không chắc chắn, hãy khuyên người dùng gặp bác sĩ da liễu."
)

_SYSTEM_EN = (
    "You are a dermatology assistant specializing in acne. Your answers are "
    "concise, evidence-based, and easy to understand. When uncertain, always "
    "recommend consulting a dermatologist."
)

# ── Generation prompts ────────────────────────────────────────────────────────

_GEN_PROMPT_VI = """\
Dưới đây là một bài viết y tế về da liễu / mụn trứng cá.

---
{text}
---

Hãy tạo ra ĐÚNG {n} cặp Q&A đa dạng, được rút ra TỪ NỘI DUNG BÀI VIẾT này.

YÊU CẦU QUAN TRỌNG:
• Câu hỏi: tự nhiên như người dùng thực sự hỏi chatbot (không dùng "bài viết", "tác giả")
• Câu trả lời: ngắn gọn 80–250 từ, đúng trọng tâm, KHÔNG lặp lại câu hỏi
• Không bịa đặt thông tin ngoài bài viết
• Không bao gồm địa chỉ, hotline, tên bác sĩ cụ thể, quảng cáo
• Phủ các intent khác nhau: nguyên nhân, triệu chứng, điều trị, thuốc, routine, an toàn, so sánh, khi nào gặp bác sĩ

Trả về JSON hợp lệ theo đúng cấu trúc:
{{
  "pairs": [
    {{
      "question": "...",
      "answer": "...",
      "intent": "ask_treatment"
    }}
  ]
}}

Intent hợp lệ: ask_cause, ask_symptoms, ask_treatment, ask_medication, ask_routine, ask_safety, ask_comparison, ask_when_doctor, ask_general
"""

_GEN_PROMPT_EN = """\
Below is a medical article about dermatology / acne.

---
{text}
---

Generate EXACTLY {n} diverse Q&A pairs extracted FROM the article content above.

REQUIREMENTS:
• Question: natural language a real user would ask a chatbot (no "the article", "the author")
• Answer: concise 80–250 words, on-point, do NOT repeat the question
• Do not hallucinate information outside the article
• Do not include addresses, phone numbers, specific doctor names, or ads
• Cover diverse intents: cause, symptoms, treatment, medication, routine, safety, comparison, when-to-see-doctor

Return valid JSON only:
{{
  "pairs": [
    {{
      "question": "...",
      "answer": "...",
      "intent": "ask_treatment"
    }}
  ]
}}

Valid intents: ask_cause, ask_symptoms, ask_treatment, ask_medication, ask_routine, ask_safety, ask_comparison, ask_when_doctor, ask_general
"""

_VALID_INTENTS = {
    "ask_cause", "ask_symptoms", "ask_treatment", "ask_medication",
    "ask_routine", "ask_safety", "ask_comparison", "ask_when_doctor", "ask_general",
}

# Adaptive n_pairs based on article length
def _n_pairs(text_len: int) -> int:
    if text_len < 800:
        return 3
    if text_len < 2000:
        return 6
    if text_len < 4000:
        return 10
    return 15


class QAGenerator:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        max_concurrency: int = 5,
        temperature: float = 0.6,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._sem = asyncio.Semaphore(max_concurrency)
        self._temperature = temperature

    async def generate(
        self,
        doc_id: str,
        text: str,
        lang: str,
        source_meta: dict[str, Any],
        n_override: int | None = None,
    ) -> list[QASample]:
        """Generate Q&A pairs for one document. Returns [] on failure."""
        n = n_override or _n_pairs(len(text))
        system_prompt = _SYSTEM_VI if lang == "vi" else _SYSTEM_EN
        gen_prompt = (_GEN_PROMPT_VI if lang == "vi" else _GEN_PROMPT_EN).format(
            text=text[:6000],  # cap to avoid token explosion
            n=n,
        )

        async with self._sem:
            for attempt in range(4):
                try:
                    resp = await self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": gen_prompt},
                        ],
                        temperature=self._temperature,
                        response_format={"type": "json_object"},
                        timeout=60,
                    )
                    raw = resp.choices[0].message.content or ""
                    pairs = json.loads(raw).get("pairs", [])
                    return self._to_samples(pairs, doc_id, lang, system_prompt, source_meta)
                except Exception as exc:
                    wait = 2 ** attempt
                    logger.warning(f"[QAGen] doc={doc_id} attempt={attempt+1} err={exc} retry in {wait}s")
                    await asyncio.sleep(wait)

        logger.error(f"[QAGen] Giving up on doc={doc_id} after 4 attempts")
        return []

    def _to_samples(
        self,
        pairs: list[dict],
        doc_id: str,
        lang: str,
        system_prompt: str,
        source_meta: dict[str, Any],
    ) -> list[QASample]:
        samples: list[QASample] = []
        for p in pairs:
            question = (p.get("question") or "").strip()
            answer = (p.get("answer") or "").strip()
            intent = p.get("intent", "ask_general")

            if not question or not answer:
                continue
            # Discard very short/long answers — likely malformed
            word_count = len(answer.split())
            if word_count < 20 or word_count > 500:
                continue
            if intent not in _VALID_INTENTS:
                intent = "ask_general"

            samples.append(QASample(
                id=str(uuid.uuid4()),
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=question),
                    ChatMessage(role="assistant", content=answer),
                ],
                metadata={
                    "intent": intent,
                    "language": lang,
                    "source_doc_id": doc_id,
                    **source_meta,
                },
            ))
        return samples

    async def close(self) -> None:
        await self._client.close()


# ── Ollama-based Q&A Generator (no API key required) ────────────────────────

_OLLAMA_SYSTEM_VI = (
    "Bạn là trợ lý chuyên tạo dữ liệu huấn luyện cho mô hình tư vấn da liễu. "
    "Luôn trả về JSON hợp lệ, không thêm text bên ngoài JSON."
)


class OllamaQAGenerator:
    """Q&A generator using local Ollama (no API key required).

    Uses the same OllamaBackend from the main LLM pipeline.
    Slower than API-based generators but fully local.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model: str = "qwen2.5:7b",
        num_ctx: int = 8192,
        temperature: float = 0.6,
    ):
        from ..llm.ollama_backend import OllamaBackend
        self._llm = OllamaBackend(
            base_url=ollama_url,
            model=model,
            num_ctx=num_ctx,
        )
        self._temperature = temperature
        self._sem = asyncio.Semaphore(1)  # Ollama best with sequential requests

    async def generate(
        self,
        doc_id: str,
        text: str,
        lang: str,
        source_meta: dict[str, Any],
        n_override: int | None = None,
    ) -> list[QASample]:
        n = n_override or _n_pairs(len(text))
        system_prompt = _SYSTEM_VI if lang == "vi" else _SYSTEM_EN
        gen_prompt = (_GEN_PROMPT_VI if lang == "vi" else _GEN_PROMPT_EN).format(
            text=text[:5000],
            n=n,
        )

        async with self._sem:
            for attempt in range(3):
                try:
                    raw = await asyncio.to_thread(
                        self._llm.generate_text,
                        system=_OLLAMA_SYSTEM_VI if lang == "vi" else _OLLAMA_SYSTEM_VI,
                        user=gen_prompt,
                        temperature=self._temperature,
                    )
                    # Ollama may wrap JSON in markdown or add preamble
                    raw = self._extract_json(raw)
                    pairs = json.loads(raw).get("pairs", [])
                    return _to_samples_static(pairs, doc_id, lang, system_prompt, source_meta)
                except Exception as exc:
                    wait = 2 ** attempt
                    logger.warning(f"[OllamaQAGen] doc={doc_id} attempt={attempt+1} err={exc} retry in {wait}s")
                    await asyncio.sleep(wait)

        logger.error(f"[OllamaQAGen] Giving up on doc={doc_id} after 3 attempts")
        return []

    @staticmethod
    def _extract_json(raw: str) -> str:
        raw = raw.strip()
        # Remove markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(lines).strip()
        # Find first { and last }
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]
        return raw

    async def close(self) -> None:
        self._llm.close()


def _to_samples_static(
    pairs: list[dict],
    doc_id: str,
    lang: str,
    system_prompt: str,
    source_meta: dict[str, Any],
) -> list[QASample]:
    samples: list[QASample] = []
    for p in pairs:
        question = (p.get("question") or "").strip()
        answer = (p.get("answer") or "").strip()
        intent = p.get("intent", "ask_general")

        if not question or not answer:
            continue
        word_count = len(answer.split())
        if word_count < 20 or word_count > 500:
            continue
        if intent not in _VALID_INTENTS:
            intent = "ask_general"

        samples.append(QASample(
            id=str(uuid.uuid4()),
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=question),
                ChatMessage(role="assistant", content=answer),
            ],
            metadata={
                "intent": intent,
                "language": lang,
                "source_doc_id": doc_id,
                **source_meta,
            },
        ))
    return samples
