"""Async TokenRouter client and ROLE record materialization."""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import yaml
from openai import AsyncOpenAI

from .config import CASE_TYPE_TARGETS, Config
from .render_context import render_runtime_user


GENERATOR_VERSION = "v4-role-generator-2"
STYLE_INSTRUCTIONS = {
    "standard": "User viết tiếng Việt chuẩn, tự nhiên; không chèn từ tiếng Anh lạc lõng.",
    "teencode": "User dùng ít teencode phổ biến như k/ko, dc/đc, j, z; câu vẫn đủ ý và dễ hiểu.",
    "no_accent": "Toàn bộ user message không dấu nhưng vẫn đủ chủ-vị/động từ và đọc tự nhiên.",
    "typo": "User có 1-3 lỗi gõ tự nhiên nhưng vẫn đọc hiểu ngay.",
    "mixed": "User trộn nhẹ teencode/không dấu/typo nhưng không biến thành chuỗi khó hiểu.",
}
PHRASING_SEEDS = (
    "Mở đầu trực tiếp bằng quan sát cụ thể, tránh 'mình hiểu'.",
    "Dùng một câu hỏi ngắn kiểu hội thoại, không liệt kê ba loại mụn theo khuôn.",
    "Đổi nhịp câu và đại từ nhưng giữ register nhất quán.",
    "Ưu tiên động từ đời thường; không lặp nguyên văn câu hỏi của slot khác.",
    "Viết như một tin nhắn thật, tránh disclaimer nếu không cần.",
    "Nếu cần làm rõ, chỉ hỏi một hoặc hai ý và thay đổi cách diễn đạt.",
)

CASE_CONSTRAINTS = {
    "R1": "Chỉ nói danh tính, năng lực và giới hạn; không đưa kiến thức điều trị.",
    "R2": (
        "Tạo persona teen/phụ huynh/sinh viên y hỏi AcneLLM có thể điều chỉnh cách giải thích theo trình độ của họ không; "
        "KHÔNG hỏi triệu chứng, nguyên nhân, routine hay treatment. Answer chỉ xác nhận sẽ đổi register/depth và hỏi họ muốn "
        "mức giải thích nào; tuyệt đối không đưa fact chăm sóc. Ví dụ teen: 'Em không rành thuật ngữ, bạn giải thích dễ hiểu được không?' "
        "-> 'Được, mình sẽ dùng từ đơn giản và giải thích từng ý; em muốn bản ngắn hay kỹ hơn?'."
    ),
    "R3": "Không phán xét chuyện nặn mụn/kem trộn/bỏ skincare; chuyển hướng tích cực, không tên thuốc/số liệu.",
    "R4": "Công nhận cảm xúc vừa đủ rồi hỗ trợ trong vai, không trị liệu tâm lý.",
    "R5": "User mơ hồ; assistant chỉ hỏi 1-2 ý trọng tâm, không dùng câu clarify khuôn mẫu.",
    "R6": "Đúng ba nhịp ghi nhận -> giới hạn -> lựa chọn hỗ trợ an toàn.",
    "R7": "Ngắn, ấm, kéo nhẹ về phạm vi da mụn.",
    "R8": "Giữ vai trước jailbreak, từ chối êm và không lặp nguyên văn injection phổ biến.",
    "R9": "4-6 lượt, trộn ít nhất 3 hành vi R1-R8; xưng hô xuyên suốt nhất quán.",
    "B1": "Context 2-4 fact trực tiếp; answer có ít nhất 4 câu fact bám sát context.",
    "B2": (
        "Context cùng chủ đề nhưng cố ý thiếu đáp án. Chỉ dùng fact ít rủi ro về làm sạch dịu nhẹ, "
        "dưỡng ẩm không bít tắc, tránh cạy nặn. Không dùng thuốc, hút thuốc, ăn uống, hormone/nội tiết. "
        "User phải hỏi một chủ đề KHÔNG có trong context như ăn đường, thức khuya, stress hoặc ánh sáng spa. "
        "Answer phải chứa NGUYÊN VĂN 'Tài liệu chưa đề cập' và không thêm fact ngoài context."
    ),
    "B3": "Nguồn 1 có ít nhất 4 fact liên quan; Nguồn 2 trung tính nhưng lạc đề; answer chỉ dùng Nguồn 1.",
    "B4": (
        "BẮT BUỘC đúng ví dụ an toàn: Nguồn 1 khuyên gel/lotion nhẹ cho da dầu; Nguồn 2 khuyên cream "
        "đặc hơn khi da khô hoặc kích ứng. Không thuốc/hoạt chất/liều/thời gian, không ăn uống/hormone. "
        "Answer nêu cả hai điều kiện, nói nguồn khác nhau, không tự phân xử và khuyên hỏi bác sĩ."
    ),
    "B5": (
        "Chỉ routine cơ bản: làm sạch dịu nhẹ, dưỡng ẩm không bít tắc, tránh cạy nặn, chống nắng. "
        "Không thuốc/hoạt chất, hút thuốc, ăn uống, sữa, hormone/nội tiết. Cùng anchor phải cùng docs; "
        "Context phải viết thành đúng 4 câu fact riêng: làm sạch dịu nhẹ; dưỡng ẩm không gây bít tắc; "
        "tránh cạy/nặn; chống nắng. Mỗi answer cũng có đúng 4 câu fact tương ứng, diễn đạt sát từng câu nguồn. "
        "Beginner dùng từ đơn giản; advanced dùng register kỹ thuật hơn nhưng TUYỆT ĐỐI không thêm cơ chế, "
        "lợi ích hay fact không có trong 4 câu nguồn."
    ),
}


@dataclass(frozen=True)
class Slot:
    id: str
    case_id: str
    sample_kind: str
    input_style: str
    ordinal: int
    anchor_group: str | None = None
    anchor_depth: str | None = None
    anchor_sources: tuple[str, ...] = ()


@dataclass
class GenerationBatch:
    candidates: list[dict[str, Any]]
    elapsed_seconds: float
    usage: dict[str, Any]


class BudgetExceededError(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_taxonomy(cfg: Config) -> dict[str, Any]:
    payload = yaml.safe_load(cfg.taxonomy_path.read_text(encoding="utf-8")) or {}
    groups = payload.get("groups") or {}
    if set(groups) != set(CASE_TYPE_TARGETS):
        raise RuntimeError("role_taxonomy.yaml không khớp R1-R9 + B1-B5 trong config.py")
    return payload


def extract_production_system(cfg: Config) -> str:
    text = cfg.model_file_path.read_text(encoding="utf-8")
    match = re.search(r'SYSTEM\s+"""(.*?)"""', text, re.DOTALL)
    if not match:
        raise RuntimeError(f"Không tìm thấy SYSTEM triple-quoted trong {cfg.model_file_path}")
    return match.group(1)


def deterministic_style(ordinal: int) -> str:
    """Exactly 30% augmented styles over each complete block of 20."""
    position = ordinal % 20
    if position < 14:
        return "standard"
    return {
        14: "teencode",
        15: "teencode",
        16: "no_accent",
        17: "no_accent",
        18: "typo",
        19: "mixed",
    }[position]


def _global_ordinal(case_id: str, index: int) -> int:
    ordinal = 0
    for current, count in CASE_TYPE_TARGETS.items():
        if current == case_id:
            return ordinal + index - 1
        ordinal += count
    raise KeyError(case_id)


def make_slot(
    case_id: str,
    index: int,
    sample_kind: str,
    *,
    style: str | None = None,
    anchor_sources: Sequence[str] = (),
) -> Slot:
    ordinal = _global_ordinal(case_id, index)
    anchor_group = None
    anchor_depth = None
    if case_id == "B5":
        anchor_group = f"b5-anchor-{(index - 1) // 2 + 1:04d}"
        anchor_depth = "beginner" if index % 2 else "advanced"
    return Slot(
        id=f"role-{case_id.casefold()}-{index:06d}",
        case_id=case_id,
        sample_kind=sample_kind,
        input_style=style or deterministic_style(ordinal),
        ordinal=ordinal,
        anchor_group=anchor_group,
        anchor_depth=anchor_depth,
        anchor_sources=tuple(anchor_sources),
    )


def smoke_slots(taxonomy: dict[str, Any], only_case: str | None = None) -> list[Slot]:
    groups = taxonomy["groups"]
    selected = [only_case] if only_case else list(CASE_TYPE_TARGETS)
    slots = [make_slot(case_id, 1, groups[case_id]["sample_kind"], style="standard") for case_id in selected]
    if only_case == "B5" or only_case is None:
        slots.append(make_slot("B5", 2, groups["B5"]["sample_kind"], style="standard"))
    if only_case is None:
        slots.extend([
            make_slot("R2", 2, groups["R2"]["sample_kind"], style="teencode"),
            make_slot("R3", 2, groups["R3"]["sample_kind"], style="no_accent"),
            make_slot("R5", 2, groups["R5"]["sample_kind"], style="typo"),
        ])
    return sorted({slot.id: slot for slot in slots}.values(), key=lambda slot: slot.ordinal)


def parse_json_array(text: str) -> list[dict[str, Any]]:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("["), value.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Model response không chứa JSON array")
    parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, list) or any(not isinstance(item, dict) for item in parsed):
        raise ValueError("Model response phải là JSON array các object")
    return parsed


def build_generation_messages(
    slots: Sequence[Slot],
    *,
    style_guide: str,
    production_system: str,
    taxonomy: dict[str, Any],
    feedback: dict[str, str],
    banned_questions: Sequence[str],
) -> list[dict[str, str]]:
    specs: list[dict[str, Any]] = []
    for slot in slots:
        behavior = taxonomy["groups"][slot.case_id]["behavior"]
        spec: dict[str, Any] = {
            "slot_id": slot.id,
            "case": slot.case_id,
            "sample_kind": slot.sample_kind,
            "input_style": slot.input_style,
            "style_instruction": STYLE_INSTRUCTIONS[slot.input_style],
            "behavior": behavior,
            "case_constraints": CASE_CONSTRAINTS[slot.case_id],
            "phrasing_seed": PHRASING_SEEDS[slot.ordinal % len(PHRASING_SEEDS)],
            "previous_rejection": feedback.get(slot.id),
            "anchor_group": slot.anchor_group,
            "anchor_depth": slot.anchor_depth,
        }
        if slot.anchor_sources:
            spec["anchor_sources_exact"] = list(slot.anchor_sources)
        specs.append(spec)
    system = (
        "Bạn tạo dữ liệu ROLE cho AcneLLM. Chỉ xuất JSON hợp lệ, không markdown.\n\n"
        f"STYLE GUIDE:\n{style_guide}\n\nSYSTEM PRODUCTION:\n{production_system}"
    )
    user = f"""Tạo đúng một object cho từng slot và trả về duy nhất JSON array.

Schema:
{{"slot_id":"...","context_sources":["..."],"turns":[{{"user":"...","assistant":"..."}}]}}

Luật cứng:
- R1-R8/B1-B5 đúng 1 turn; R9 có 4-6 turn.
- R1-R9 context_sources=[]; assistant không nêu thuốc/hoạt chất/liều/nồng độ/thời gian.
- B1/B3/B5: ít nhất 80% câu fact phải bám sát context. B2 phải viết đúng “Tài liệu chưa đề cập”.
- Riêng B5: context gồm 4 câu fact tách biệt và mỗi answer có đúng 4 câu fact đối ứng; depth chỉ đổi register, không thêm cơ chế.
- B3 có ít nhất 2 nguồn, trong đó một nguồn lạc đề. B4 đúng 2 nguồn, nêu cả Nguồn 1/Nguồn 2, sự khác nhau và hướng hỏi bác sĩ.
- Mỗi anchor_group B5 là một CẶP: context_sources giống tuyệt đối; beginner giải thích đơn giản, advanced sâu hơn. Nếu có anchor_sources_exact thì chép đúng list đó.
- Answer luôn tiếng Việt chuẩn. input standard không chèn các từ như mostly/actually/basically.
- Teencode/no_accent/mixed phải là câu hoàn chỉnh dễ hiểu, có động từ; teencode chỉ dùng shorthand phổ biến.
- Giữ xưng hô nhất quán: nếu gọi “Cô ơi/Chú ơi/Bác ơi” thì không tự xưng “mình”.
- Không chép nguyên văn câu user đã dùng; xoay cách hỏi theo phrasing_seed.
- Không thêm/bỏ/đổi slot_id.

Các câu user cấm reuse nguyên văn:
{json.dumps(list(banned_questions)[-30:], ensure_ascii=False)}

SLOTS:
{json.dumps(specs, ensure_ascii=False, indent=2)}
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _clean_turns(raw: Any) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for turn in raw if isinstance(raw, list) else []:
        if not isinstance(turn, dict):
            continue
        user = str(turn.get("user") or "").strip()
        assistant = str(turn.get("assistant") or "").strip()
        if user and assistant:
            turns.append({"user": user, "assistant": assistant})
    return turns


def materialize_record(
    slot: Slot,
    candidate: dict[str, Any],
    *,
    production_system: str,
    model: str,
    attempt: int,
) -> tuple[dict[str, Any], list[str], list[str]]:
    turns = _clean_turns(candidate.get("turns"))
    raw_sources = candidate.get("context_sources")
    sources = [str(value).strip() for value in raw_sources if str(value).strip()] if isinstance(raw_sources, list) else []
    errors: list[str] = []
    minimum, maximum = (4, 6) if slot.case_id == "R9" else (1, 1)
    if not minimum <= len(turns) <= maximum:
        errors.append(f"turn_count={len(turns)} expected={minimum}..{maximum}")
    if slot.case_id.startswith("R") and sources:
        errors.append("group_a_must_not_have_context")
    if slot.case_id.startswith("B") and not sources:
        errors.append("group_b_requires_context")
    if slot.case_id == "B3" and len(sources) < 2:
        errors.append("b3_requires_at_least_two_sources")
    if slot.case_id == "B4" and len(sources) != 2:
        errors.append("b4_requires_exactly_two_sources")
    if slot.anchor_sources and tuple(sources) != slot.anchor_sources:
        errors.append("b5_anchor_sources_not_reused_exactly")

    messages: list[dict[str, str]] = [{"role": "system", "content": production_system}]
    raw_users: list[str] = []
    for turn in turns:
        raw_users.append(turn["user"])
        messages.append({
            "role": "user",
            "content": render_runtime_user(turn["user"], sources if slot.case_id.startswith("B") else []),
        })
        messages.append({"role": "assistant", "content": turn["assistant"]})
    record = {
        "id": slot.id,
        "sample_kind": slot.sample_kind,
        "input_style": slot.input_style,
        "synthetic_context": slot.case_id.startswith("B"),
        "knowledge_leak_check": "pending" if slot.case_id.startswith("R") else "not_applicable",
        "grounded_sentence_rate": None,
        "gen_model": model,
        "synthetic_context_sources": sources,
        "raw_user_messages": raw_users,
        "anchor_group": slot.anchor_group,
        "anchor_depth": slot.anchor_depth,
        "generation_metadata": {
            "generator_version": GENERATOR_VERSION,
            "provider": "tokenrouter_openai_compatible",
            "generated_at": utcnow(),
            "attempt": attempt,
        },
        "messages": messages,
    }
    return record, errors, raw_users


def _usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
    data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
    details = data.get("completion_tokens_details") or {}
    return {
        "prompt_tokens": int(data.get("prompt_tokens") or 0),
        "completion_tokens": int(data.get("completion_tokens") or 0),
        "reasoning_tokens": int(details.get("reasoning_tokens") or 0),
        "total_tokens": int(data.get("total_tokens") or 0),
    }


class AsyncRoleGenerator:
    """Async OpenAI-compatible client with retries and a shared cost guard."""

    def __init__(self, cfg: Config):
        if not cfg.api_key:
            raise RuntimeError("Thiếu DATAGEN_API_KEY trong .env")
        self.cfg = cfg
        self.client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=cfg.timeout_s,
            max_retries=0,
        )
        self._usage_lock = asyncio.Lock()
        self._reserved_cost = 0.0
        self.calls: list[dict[str, Any]] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.reasoning_tokens = 0

    @property
    def actual_cost_usd(self) -> float:
        return (
            self.prompt_tokens * self.cfg.input_price_per_million
            + self.completion_tokens * self.cfg.output_price_per_million
        ) / 1_000_000

    async def _reserve(self, messages: Sequence[dict[str, str]], max_tokens: int) -> float:
        estimated_input = sum(len(message["content"]) for message in messages) // 3 + 512
        ceiling = (
            estimated_input * self.cfg.input_price_per_million
            + max_tokens * self.cfg.output_price_per_million
        ) / 1_000_000
        async with self._usage_lock:
            if self.actual_cost_usd + self._reserved_cost + ceiling > self.cfg.max_cost_usd:
                raise BudgetExceededError(
                    f"Request ceiling ${ceiling:.4f} sẽ vượt budget ${self.cfg.max_cost_usd:.2f}"
                )
            self._reserved_cost += ceiling
        return ceiling

    async def _record_usage(self, usage: dict[str, Any], ceiling: float, elapsed: float, kind: str) -> None:
        async with self._usage_lock:
            self._reserved_cost = max(0.0, self._reserved_cost - ceiling)
            self.prompt_tokens += usage["prompt_tokens"]
            self.completion_tokens += usage["completion_tokens"]
            self.reasoning_tokens += usage["reasoning_tokens"]
            self.calls.append({"kind": kind, "elapsed_seconds": round(elapsed, 3), "usage": usage})

    async def _release(self, ceiling: float) -> None:
        async with self._usage_lock:
            self._reserved_cost = max(0.0, self._reserved_cost - ceiling)

    async def list_models(self) -> list[str]:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = await self.client.models.list()
                return sorted(model.id for model in response.data)
            except Exception as exc:
                last_error = exc
                if attempt == 3 or not _transient(exc):
                    raise
                await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Không gọi được /v1/models: {last_error}")

    async def short_completion(self) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": "Chỉ trả lời đúng một từ tiếng Việt: được"},
            {"role": "user", "content": "Kiểm tra kết nối."},
        ]
        response, elapsed = await self._completion(messages, max_tokens=16, retries=3, kind="preflight")
        content = str(response.choices[0].message.content or "").strip()
        usage = _usage_dict(response)
        return {"content": content, "usage": usage, "elapsed_seconds": elapsed}

    async def generate_batch(self, messages: Sequence[dict[str, str]]) -> GenerationBatch:
        response, elapsed = await self._completion(
            messages,
            max_tokens=self.cfg.max_output_tokens,
            retries=self.cfg.max_retries,
            kind="generation",
        )
        content = str(response.choices[0].message.content or "")
        return GenerationBatch(parse_json_array(content), elapsed, _usage_dict(response))

    async def _completion(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int,
        retries: int,
        kind: str,
    ) -> tuple[Any, float]:
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            ceiling = await self._reserve(messages, max_tokens)
            started = time.perf_counter()
            try:
                response = await self.client.chat.completions.create(
                    model=self.cfg.model,
                    messages=list(messages),
                    max_tokens=max_tokens,
                    temperature=0.2 if kind == "preflight" else 0.7,
                    extra_body={"thinking": {"type": self.cfg.thinking}},
                )
                elapsed = time.perf_counter() - started
                await self._record_usage(_usage_dict(response), ceiling, elapsed, kind)
                return response, elapsed
            except Exception as exc:
                await self._release(ceiling)
                last_error = exc
                if attempt >= retries or not _transient(exc):
                    raise
                await asyncio.sleep(min(2 ** attempt, 30) + random.random())
        raise RuntimeError(f"API thất bại sau {retries} lần: {last_error}")

    def usage_summary(self) -> dict[str, Any]:
        return {
            "calls": len(self.calls),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "actual_cost_usd": round(self.actual_cost_usd, 8),
            "input_price_per_million": self.cfg.input_price_per_million,
            "output_price_per_million": self.cfg.output_price_per_million,
            "call_details": list(self.calls),
        }


def _transient(exc: Exception) -> bool:
    text = str(exc).casefold()
    return any(token in text for token in (
        "503", "no_available_workers", "service unavailable", "timeout", "timed out", "429", "rate limit"
    ))
