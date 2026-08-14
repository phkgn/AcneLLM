"""OpenAI-backed synthetic sample generation for the independent ROLE pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .config import Config

logger = logging.getLogger(__name__)

AUGMENTED_STYLES = ("teencode", "no_accent", "typo", "mixed")

# Xiết prompt cho đa dạng: mỗi lần sinh chèn 1 chỉ thị biến hoá để tránh model
# hội tụ về cùng khuôn mở đầu/từ chối/disclaimer (nguyên nhân reject phrase_frequency).
VARIATION_DIRECTIVES = (
    "Đi thẳng vào nội dung chính, KHÔNG dùng câu chào hay câu mở đầu quen thuộc.",
    "Đổi mới cấu trúc câu và từ vựng; tránh mọi cụm sáo mòn và mẫu câu lặp lại.",
    "Diễn đạt từ chối/nhắc giới hạn theo cách MỚI, không dùng khuôn cứng giống mẫu trước.",
    "Ưu tiên câu chủ động, ngắn gọn; đa dạng động từ và cách xưng hô theo ngữ cảnh.",
    "Biến hoá độ dài và nhịp câu; câu mở đầu phải khác các câu trả lời thông thường.",
    "Chọn góc tiếp cận riêng cho tình huống này; không tái sử dụng câu kết mẫu.",
)


def planned_input_style(case_id: str, ordinal: int) -> str:
    """Return a deterministic 30% user-only augmentation schedule.

    Every PLAN quota is divisible by ten, so ordinals ending in 3, 6, or 9
    produce exactly 30% augmented user turns for a full case budget.
    """
    if ordinal <= 0:
        raise ValueError("ordinal must be positive")
    if ordinal % 10 not in {3, 6, 9}:
        return "standard"
    offset = sum(case_id.encode("utf-8")) + ordinal
    return AUGMENTED_STYLES[offset % len(AUGMENTED_STYLES)]


@dataclass(frozen=True, slots=True)
class CaseSpec:
    id: str
    sample_kind: str
    count: int
    context: bool
    behavior: str
    gate: str
    user_turns: str | None = None
    anchor_pair_size: int | None = None


def load_taxonomy(cfg: Config) -> list[CaseSpec]:
    payload = yaml.safe_load(cfg.taxonomy_path.read_text(encoding="utf-8"))
    if payload.get("version") != "roledata-v1":
        raise ValueError("taxonomy.yaml must have version roledata-v1")
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) != 16:
        raise ValueError("taxonomy.yaml must define exactly 16 groups")
    cases = [CaseSpec(**item) for item in groups]
    if len({case.id for case in cases}) != 16:
        raise ValueError("taxonomy case IDs must be unique")
    return cases


def _load_chunks(path: Path, limit: int = 512) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    keywords = ("mụn", "trứng cá", "acne", "retinoid", "benzoyl", "salicylic")
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            text = str(item.get("text") or "").strip()
            if len(text) < 180 or not any(token in text.casefold() for token in keywords):
                continue
            chunks.append(item)
            if len(chunks) >= limit:
                break
    if not chunks:
        raise ValueError(f"No usable acne chunks found in {path}")
    return chunks


def synthesize_context(
    case: CaseSpec | Mapping[str, Any], cfg: Config, sequence: int = 0
) -> tuple[list[dict[str, str]] | None, list[str], dict[str, Any]]:
    case_id = case.id if isinstance(case, CaseSpec) else str(case["id"])
    needs_context = case.context if isinstance(case, CaseSpec) else bool(case.get("context"))
    if not needs_context:
        return None, [], {}

    chunks = _load_chunks(cfg.knowledge_chunks_path)
    # B5 is emitted in adjacent beginner/advanced pairs over the exact same
    # source. Other context cases advance one chunk per record.
    source_sequence = sequence // 2 if case_id == "B5_depth_anchor" else sequence
    first = chunks[source_sequence % len(chunks)]
    source_id = str(first.get("chunk_id") or first.get("doc_id") or f"chunk-{sequence}")
    source_name = str(first.get("source_name") or first.get("title") or "Tài liệu mụn trong repo")
    context: list[dict[str, str]] = [
        {
            "label": "Nguồn 1",
            "source_id": source_id,
            "source_name": source_name,
            "text": str(first["text"])[:2_600],
        }
    ]
    sources = [source_id]
    meta: dict[str, Any] = {}

    if case_id == "B2_missing_answer":
        meta["missing_topic"] = "độ an toàn trong thai kỳ nếu nguồn không đề cập"
    elif case_id == "B3_irrelevant_chunk":
        context.append(
            {
                "label": "Nguồn nhiễu",
                "source_id": "synthetic-distractor-weather",
                "source_name": "Đoạn nhiễu kiểm thử",
                "text": "Thời tiết hôm nay có mây và giá điện thoại đang thay đổi. Nội dung này không liên quan đến da mụn.",
            }
        )
        sources.append("synthetic-distractor-weather")
    elif case_id == "B4_conflicting_docs":
        second = chunks[(sequence + 17) % len(chunks)]
        second_id = str(second.get("chunk_id") or f"chunk-{sequence + 17}")
        context.append(
            {
                "label": "Nguồn 2",
                "source_id": second_id,
                "source_name": str(second.get("source_name") or second.get("title") or "Tài liệu 2"),
                "text": (
                    str(second["text"])[:2_200]
                    + "\n[Ghi chú tình huống kiểm thử: nguồn này đưa ra kết luận khác Nguồn 1; "
                    "không tự chọn một bên khi thiếu căn cứ phân giải.]"
                ),
            }
        )
        sources.append(second_id)
    elif case_id == "B5_depth_anchor":
        meta["anchor_group"] = f"anchor-{source_id}"
        meta["depth"] = "beginner" if sequence % 2 == 0 else "advanced"
    elif case_id == "K1_knowledge_anchor":
        meta["knowledge_topic"] = "kiến thức mụn có thể kiểm chứng trực tiếp từ Nguồn 1"
    return context, sources, meta


def build_gen_prompt(
    case: CaseSpec | Mapping[str, Any],
    cfg: Config,
    anchor: str,
    style_guide: str,
) -> list[dict[str, str]]:
    values = dict(case) if isinstance(case, Mapping) else {
        "id": case.id,
        "sample_kind": case.sample_kind,
        "behavior": case.behavior,
        "context": case.context,
    }
    case_id = str(values["id"])
    template_path = cfg.module_root / "prompts" / f"{case_id}.j2"
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing prompt template: {template_path}")
    environment = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    case_instructions = environment.get_template(template_path.name).render(**values)
    context = values.get("synthetic_context")
    context_json = json.dumps(context, ensure_ascii=False, indent=2) if context else "Không có."
    requested_input_style = str(values.get("requested_input_style") or "standard")

    if case_id == "R9_multiturn":
        output_contract = (
            '{"turns":['
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."},'
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."},'
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."}],'
            f'"input_style":"{requested_input_style}","audience":"teen|parent|medical_student"}}'
        )
    else:
        output_contract = (
            '{"user":"...","assistant":"...","input_style":"standard|teencode|no_accent|typo|mixed",'
            '"audience":"teen|parent|medical_student|general"}'
        )

    return [
        {
            "role": "system",
            "content": (
                "Bạn tạo dữ liệu huấn luyện hội thoại AcneLLM. Chỉ xuất đúng một JSON object hợp lệ, "
                "không Markdown, không giải thích. Không tiết lộ hoặc chép lại anchor. Assistant phải "
                "luôn dùng tiếng Việt chuẩn và tuân thủ toàn bộ luật an toàn."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CASE: {case_id}\nHÀNH VI: {values['behavior']}\n\n"
                f"YÊU CẦU RIÊNG:\n{case_instructions}\n\n"
                f"STYLE GUIDE:\n{style_guide}\n\n"
                f"YÊU CẦU ĐA DẠNG (bắt buộc): {random.choice(VARIATION_DIRECTIVES)} "
                "Mỗi mẫu phải khác biệt rõ về từ ngữ, câu mở đầu và cấu trúc so với mẫu thông thường; "
                "tuyệt đối không lặp lại khuôn câu từ chối hay disclaimer.\n\n"
                f"INPUT STYLE BẮT BUỘC: {requested_input_style}. Chỉ biến đổi lời user; "
                "assistant luôn dùng tiếng Việt chuẩn. Trả đúng nhãn này trong input_style.\n\n"
                f"TÀI LIỆU THAM KHẢO:\n{context_json}\n\n"
                "QUY TẮC ANCHOR CẦN TUÂN THỦ (không chép vào câu trả lời):\n"
                f"{anchor}\n\nOUTPUT CONTRACT:\n{output_contract}\n"
                "Không thêm khóa ngoài contract. Với case grounded, mọi câu khẳng định của assistant "
                "phải dùng từ/cụm từ có căn cứ trực tiếp trong tài liệu để grounded_rate đạt ít nhất 0.8."
            ),
        },
    ]


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Provider response did not contain a JSON object")
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Provider response JSON must be an object")
    return value


class OpenAIGenerator:
    def __init__(self, cfg: Config) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared by repo
            raise RuntimeError("The openai package is required for roledata generation") from exc
        self.cfg = cfg
        self.client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=cfg.request_timeout_s,
            max_retries=0,
        )
        self._semaphore = asyncio.Semaphore(cfg.concurrency)

    async def probe(self) -> None:
        async with self._semaphore:
            await self.client.models.retrieve(self.cfg.model)

    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.65,
    ) -> dict[str, Any]:
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(1, self.cfg.max_api_retries + 1):
            try:
                async with self._semaphore:
                    response = await self.client.chat.completions.create(
                        model=self.cfg.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens or self.cfg.max_output_tokens,
                        response_format={"type": "json_object"},
                    )
                content = response.choices[0].message.content or ""
                return _extract_json(content)
            except Exception as exc:  # provider/network errors are retried separately
                last_error = exc
                logger.warning(
                    "OpenAI request attempt %d/%d failed: %s",
                    attempt,
                    self.cfg.max_api_retries,
                    type(exc).__name__,
                )
                if attempt < self.cfg.max_api_retries:
                    await asyncio.sleep(delay + random.random() * 0.25)
                    delay = min(delay * 2, 16)
        raise RuntimeError(
            f"OpenAI request failed after {self.cfg.max_api_retries} attempts: {last_error}"
        ) from last_error

    async def generate(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        return await self._chat(messages, temperature=self.cfg.temperature)

    async def judge_knowledge(self, context: str, answer: str) -> int:
        result = await self._chat(
            [
                {
                    "role": "system",
                    "content": "Chấm tính đúng sự thật của câu trả lời chỉ theo tài liệu. Chỉ xuất JSON.",
                },
                {
                    "role": "user",
                    "content": (
                        "Tài liệu:\n" + context + "\n\nCâu trả lời:\n" + answer
                        + '\n\nXuất {"score":1-5,"reason":"ngắn gọn"}. Điểm 4-5 chỉ khi không có khẳng định sai hoặc vượt nguồn.'
                    ),
                },
            ],
            max_tokens=180,
            temperature=0.0,
        )
        try:
            score = int(result.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        return min(5, max(0, score))

    async def close(self) -> None:
        await self.client.close()


def to_record(
    case: CaseSpec | Mapping[str, Any],
    user: str | None,
    assistant: str | None,
    anchor: str,
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    case_id = case.id if isinstance(case, CaseSpec) else str(case["id"])
    context_enabled = case.context if isinstance(case, CaseSpec) else bool(case.get("context"))
    turns = meta.get("turns")
    messages: list[dict[str, str]] = [{"role": "system", "content": anchor}]
    if turns is not None:
        if not isinstance(turns, list):
            raise ValueError("turns must be a list")
        for turn in turns:
            if not isinstance(turn, dict):
                raise ValueError("each turn must be an object")
            messages.append({"role": str(turn.get("role", "")), "content": str(turn.get("content", ""))})
    else:
        messages.extend(
            [
                {"role": "user", "content": str(user or "")},
                {"role": "assistant", "content": str(assistant or "")},
            ]
        )

    generation_meta = dict(meta.get("generation_meta") or {})
    return {
        "id": str(meta["record_id"]),
        "sample_kind": case_id,
        "input_style": str(meta.get("input_style") or "standard"),
        "context": context_enabled,
        "synthetic_context": meta.get("synthetic_context"),
        "synthetic_context_sources": list(meta.get("synthetic_context_sources") or []),
        "anchor_group": generation_meta.get("anchor_group"),
        "messages": messages,
        "gate_results": {"passed": False, "checks": {}},
        "generation_meta": generation_meta,
        "gen_model": str(meta.get("gen_model") or "unknown"),
    }
