"""Generator v2 — sửa đúng ba chỗ so với v1, phần còn lại import lại.

1. `to_record` render tài liệu VÀO user message bằng `stream_user.j2` production.
   v1 để tài liệu ở field `synthetic_context` cạnh `messages`, rồi
   `finalize/export.py` chỉ ghi `{"id", "messages"}` -> 0/2.945 mẫu xuất ra có
   tài liệu. Đó là lý do `RRR - RNR = 0.000` trong run_full_v3_2: LoRA chưa từng
   nhìn thấy khối "Tài liệu tham khảo:" nên lúc chạy nó bỏ qua.
2. `CaseSpecV2` + `load_taxonomy` đọc thêm `len_chars`, `min_points`,
   `require_structure`, `last_turn_len_chars`.
3. `build_gen_prompt` bơm mục tiêu độ dài (bốc trong band, deterministic theo
   ordinal) và số ý bắt buộc; contract JSON có thêm khoá `points`.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..roledata.generator import (  # dùng lại nguyên vẹn
    AUGMENTED_STYLES,
    VARIATION_DIRECTIVES,
    planned_input_style,
)
from ..roledata.generator import OpenAIGenerator as OpenAIGeneratorV1
from ..roledata.generator import _extract_json as _extract_json_v1
from .config import CASE_TYPE_TARGETS, MODULE_ROOT, Config
from .knowledge import case_offsets, chunk_pool

__all__ = [
    "AUGMENTED_STYLES",
    "PROMPT_TEMPLATE_VARS",
    "CaseSpec",
    "OpenAIGenerator",
    "build_gen_prompt",
    "context_to_sources",
    "load_taxonomy",
    "planned_input_style",
    "render_user_message",
    "sample_len_target",
    "synthesize_context",
    "to_record",
]

logger = logging.getLogger(__name__)

RUNTIME_TEMPLATE = "stream_user.j2"

# Mọi biến `stream_user.j2` khai báo. `datagen/render_context.py` của v1 quên
# `prompt_note` nên với StrictUndefined nó raise ngay lần gọi đầu — đó là code
# chết chưa từng chạy. `test_render.py::test_template_vars_are_all_supplied` giữ
# danh sách này khớp template; template thêm biến mà quên khai ở đây thì test đỏ.
PROMPT_TEMPLATE_VARS: dict[str, object] = {
    "confirmed_safety_facts": "",
    "history_block": "",
    "prompt_note": "",
    "has_retrieved_context": False,
    "retrieved_context": "",
    "description": "",
}


DEFAULT_PROMPTS_DIR = MODULE_ROOT.parents[1] / "config" / "prompts"


def _prompts_env(prompts_dir: Path | None = None) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(prompts_dir or DEFAULT_PROMPTS_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=False,
    )


def format_sources(sources: Sequence[str]) -> str:
    """Đánh nhãn nguồn đúng như production làm trong `_retrieval`/prompt builder."""
    clean = [str(source).strip() for source in sources if str(source).strip()]
    return "\n\n".join(f"Nguồn {index} —\n{source}" for index, source in enumerate(clean, 1))


def render_user_message(
    description: str,
    sources: Sequence[str] | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Render một lượt user bằng CHÍNH template production `stream_user.j2`.

    Train và serve dùng chung một file template, nên không thể lệch định dạng —
    đó là toàn bộ mục đích của hàm này.
    """
    clean = str(description).strip()
    if not clean:
        raise ValueError("description không được rỗng")
    source_list = [str(item).strip() for item in (sources or []) if str(item).strip()]
    values = dict(PROMPT_TEMPLATE_VARS)
    values.update(
        description=clean,
        has_retrieved_context=bool(source_list),
        retrieved_context=format_sources(source_list),
    )
    return _prompts_env(prompts_dir).get_template(RUNTIME_TEMPLATE).render(**values).strip()


class OpenAIGenerator(OpenAIGeneratorV1):
    """Như v1, khác hai chỗ: probe khoan dung hơn, và TẮT thinking của DeepSeek.

    `deepseek-v4-flash` bật thinking MẶC ĐỊNH. Khi bật, model trả chain-of-thought
    vào `reasoning_content` còn `content` có thể rỗng — `_extract_json` thấy chuỗi
    không có `{` và raise, rồi retry 5 lần cùng lỗi. Đó chính là 19/22 reject của
    smoke lần đầu, và toàn rơi vào case dài (K1, B3, B4, R9) vì prompt càng phức
    tạp model càng nghĩ nhiều.

    `cfg.thinking = "disabled"` đã tồn tại từ v1 và có cả invariant trong
    `validate()`, nhưng CHƯA BAO GIỜ được gửi lên API — nó chỉ là biến trang trí.
    Giờ nó thật sự đi vào `extra_body`.
    """

    def _extra_body(self) -> dict[str, Any]:
        if self.cfg.provider != "deepseek":
            return {}
        return {"thinking": {"type": self.cfg.thinking}}

    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.65,
    ) -> dict[str, Any]:
        """Bản v1 + `extra_body` + thông báo lỗi nói được nguyên nhân.

        v1 chỉ raise "Provider response did not contain a JSON object" — không đủ
        để biết là content rỗng, bị cắt, hay model trả văn xuôi. Ba nguyên nhân
        đó sửa khác nhau, nên phải phân biệt được ngay trong log.
        """
        import asyncio as _asyncio

        delay = 1.0
        last_error: Exception | None = None
        extra_body = self._extra_body()
        for attempt in range(1, self.cfg.max_api_retries + 1):
            try:
                async with self._semaphore:
                    response = await self.client.chat.completions.create(
                        model=self.cfg.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens or self.cfg.max_output_tokens,
                        response_format={"type": "json_object"},
                        **({"extra_body": extra_body} if extra_body else {}),
                    )
                choice = response.choices[0]
                content = choice.message.content or ""
                if not content.strip():
                    reasoning = getattr(choice.message, "reasoning_content", None)
                    raise ValueError(
                        f"content RỖNG · finish_reason={choice.finish_reason} · "
                        f"reasoning_content={'có' if reasoning else 'không'} · "
                        f"thinking={self.cfg.thinking}"
                    )
                try:
                    return _extract_json_v1(content)
                except Exception as parse_error:
                    raise ValueError(
                        f"parse JSON hỏng · finish_reason={choice.finish_reason} · "
                        f"{len(content)} ký tự · {parse_error} · đuôi={content[-80:]!r}"
                    ) from parse_error
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Request %d/%d hỏng: %s: %s",
                    attempt,
                    self.cfg.max_api_retries,
                    type(exc).__name__,
                    str(exc)[:200],
                )
                if attempt < self.cfg.max_api_retries:
                    await _asyncio.sleep(delay + random.random() * 0.25)
                    delay = min(delay * 2, 16)
        raise RuntimeError(
            f"Request hỏng sau {self.cfg.max_api_retries} lần: {last_error}"
        ) from last_error

    async def probe(self) -> None:
        try:
            await super().probe()
            return
        except Exception as models_error:  # noqa: BLE001 - ghi lại rồi thử cách hai
            logger.info(
                "models.retrieve không dùng được (%s); probe bằng chat completion.",
                type(models_error).__name__,
            )
        await self._chat(
            [{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0.0,
        )


@dataclass(frozen=True, slots=True)
class CaseSpec:
    id: str
    sample_kind: str
    count: int
    context: bool
    behavior: str
    gate: str
    len_chars: list[int]
    min_points: int
    require_structure: bool
    last_turn_len_chars: list[int] | None = None
    user_turns: str | None = None
    anchor_pair_size: int | None = None

    # Hàm dùng lại từ v1 (`synthesize_context`, `_knowledge_sanity`) kiểm
    # `isinstance(case, CaseSpecV1)` rồi rơi về nhánh Mapping. CaseSpec v2 là
    # class khác nên luôn rơi vào nhánh đó — cấp __getitem__/get để nhánh ấy
    # chạy đúng, rẻ hơn là chép lại `synthesize_context`.
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __post_init__(self) -> None:
        lo, hi = self.len_chars
        if not (0 < lo < hi):
            raise ValueError(f"{self.id}: len_chars phải là [lo, hi] với 0 < lo < hi")
        if self.last_turn_len_chars is not None:
            last_lo, last_hi = self.last_turn_len_chars
            if not (0 < last_lo < last_hi):
                raise ValueError(f"{self.id}: last_turn_len_chars không hợp lệ")
        if self.min_points < 0:
            raise ValueError(f"{self.id}: min_points không được âm")
        if self.require_structure and self.min_points < 2:
            raise ValueError(f"{self.id}: require_structure chỉ có nghĩa khi min_points >= 2")


def load_taxonomy(cfg: Config) -> list[CaseSpec]:
    payload = yaml.safe_load(cfg.taxonomy_path.read_text(encoding="utf-8"))
    if payload.get("version") != "roledata-v2":
        raise ValueError("taxonomy.yaml phải có version roledata-v2")
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) != 16:
        raise ValueError("taxonomy.yaml phải định nghĩa đúng 16 group")
    cases = [CaseSpec(**item) for item in groups]
    if len({case.id for case in cases}) != 16:
        raise ValueError("taxonomy case ID phải là duy nhất")
    if {case.id: case.count for case in cases} != CASE_TYPE_TARGETS:
        raise ValueError("taxonomy count không khớp CASE_TYPE_TARGETS v2")
    return cases


def sample_len_target(case_id: str, ordinal: int, band: list[int], seed: int = 42) -> int:
    """Bốc một mục tiêu độ dài trong band, deterministic theo (case, ordinal).

    Bốc từng bản ghi thay vì đưa cả band cho teacher: đưa band thì model dồn hết
    về một chỗ, bốc thì phân bố trải đúng như thiết kế.
    """
    lo, hi = band
    rng = random.Random(f"{seed}:{case_id}:{ordinal}")
    return rng.randint(lo, hi)


def synthesize_context(
    case: CaseSpec | Mapping[str, Any], cfg: Config, sequence: int = 0
) -> tuple[list[dict[str, str]] | None, list[str], dict[str, Any]]:
    """Như v1 nhưng lấy chunk từ pool đã xếp ưu tiên guideline (xem `knowledge.py`).

    Khác v1 đúng một dòng về bản chất: nguồn chunk. Mọi nhánh theo case (B2 thiếu
    thông tin, B3 nguồn nhiễu, B4 hai nguồn mâu thuẫn, B5 cặp nông/sâu) giữ nguyên.
    """
    case_id = case.id if isinstance(case, CaseSpec) else str(case["id"])
    needs_context = case.context if isinstance(case, CaseSpec) else bool(case.get("context"))
    if not needs_context:
        return None, [], {}

    chunks = chunk_pool(cfg)
    # B5 phát theo cặp nông/sâu trên CÙNG một nguồn; case khác tiến một chunk mỗi bản ghi.
    source_sequence = sequence // 2 if case_id == "B5_depth_anchor" else sequence
    # Dải riêng cho từng case: không có offset thì 6 case cùng ăn chunk đầu pool.
    offset = case_offsets(tuple(CASE_TYPE_TARGETS.items())).get(case_id, 0)
    first = chunks[(offset + source_sequence) % len(chunks)]
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
    meta: dict[str, Any] = {"source_type": str(first.get("source_type") or "unknown")}

    if case_id == "B2_missing_answer":
        meta["missing_topic"] = "độ an toàn trong thai kỳ nếu nguồn không đề cập"
    elif case_id == "B3_irrelevant_chunk":
        context.append(
            {
                "label": "Nguồn nhiễu",
                "source_id": "synthetic-distractor-weather",
                "source_name": "Đoạn nhiễu kiểm thử",
                "text": (
                    "Thời tiết hôm nay có mây và giá điện thoại đang thay đổi. "
                    "Nội dung này không liên quan đến da mụn."
                ),
            }
        )
        sources.append("synthetic-distractor-weather")
    elif case_id == "B4_conflicting_docs":
        # Nguồn 2 lấy từ NỬA KIA của pool: vừa chắc chắn là tài liệu khác hẳn,
        # vừa không lấn sang dải của case khác (v1 dùng +17 nên hay lấn).
        second = chunks[(offset + sequence + len(chunks) // 2) % len(chunks)]
        second_id = str(second.get("chunk_id") or f"chunk-{sequence}-b")
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


def context_to_sources(context: list[dict[str, str]] | None) -> list[str]:
    """Chuyển context nội bộ thành các khối văn bản mà `stream_user.j2` nhận.

    `render_runtime_user` tự thêm tiền tố "Nguồn i —"; nhãn nội bộ (`Nguồn 1`,
    `Nguồn nhiễu`, `Nguồn 2`) chỉ dùng cho gate nên không lặp lại vào text.
    """
    if not context:
        return []
    return [str(item.get("text") or "").strip() for item in context if str(item.get("text") or "").strip()]


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
        "len_chars": case.len_chars,
        "min_points": case.min_points,
        "require_structure": case.require_structure,
    }
    case_id = str(values["id"])
    template_path = cfg.prompt_path(case_id)
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
    len_target = int(values.get("len_target") or 0)
    min_points = int(values.get("min_points") or 0)
    require_structure = bool(values.get("require_structure"))

    if case_id == "R9_multiturn":
        last_target = int(values.get("last_turn_len_target") or len_target)
        output_contract = (
            '{"turns":['
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."},'
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."},'
            '{"role":"user","content":"..."},{"role":"assistant","content":"..."}],'
            f'"input_style":"{requested_input_style}","audience":"teen|parent|medical_student"}}'
        )
        length_rule = (
            f"ĐỘ DÀI: mỗi lượt assistant ở giữa khoảng {len_target} ký tự. "
            f"Lượt assistant CUỐI CÙNG khoảng {last_target} ký tự và phải đưa lời khuyên "
            "đầy đủ, hành động được — KHÔNG được kết thúc hội thoại bằng một câu hỏi nữa."
        )
    else:
        points_field = ',"points":["ý 1","ý 2","ý 3"]' if min_points else ""
        output_contract = (
            '{"user":"...","assistant":"..."' + points_field
            + ',"input_style":"standard|teencode|no_accent|typo|mixed"'
            ',"audience":"teen|parent|medical_student|general"}'
        )
        length_rule = f"ĐỘ DÀI: câu trả lời của assistant khoảng {len_target} ký tự (±15%)."

    points_rule = ""
    if min_points:
        points_rule = (
            f"\n\nSỐ Ý BẮT BUỘC: câu trả lời phải phủ ít nhất {min_points} ý riêng biệt, "
            "hành động được (không phải {min} câu diễn giải cùng một ý). "
            "Liệt kê chính các ý đó vào khoá \"points\" — mỗi phần tử là một cụm ngắn "
            "trích từ chính câu trả lời, không phải tóm tắt viết lại."
        ).replace("{min}", str(min_points))
    if require_structure:
        points_rule += (
            "\n\nCẤU TRÚC BẮT BUỘC: trình bày các ý thành gạch đầu dòng hoặc đánh số, "
            "mỗi ý một dòng. Không viết thành một khối văn xuôi liền."
        )

    return [
        {
            "role": "system",
            "content": (
                # DeepSeek yêu cầu prompt phải chứa chữ "json" (thường) thì JSON mode
                # mới kích hoạt; thiếu nó API trả content rỗng. Giữ nguyên chữ này.
                "Bạn tạo dữ liệu huấn luyện hội thoại AcneLLM. Chỉ xuất đúng một json object hợp lệ "
                "(JSON), không Markdown, không giải thích. Không tiết lộ hoặc chép lại anchor. "
                "Assistant phải luôn dùng tiếng Việt chuẩn và tuân thủ toàn bộ luật an toàn."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CASE: {case_id}\nHÀNH VI: {values['behavior']}\n\n"
                f"YÊU CẦU RIÊNG:\n{case_instructions}\n\n"
                f"STYLE GUIDE:\n{style_guide}\n\n"
                f"{length_rule}{points_rule}\n\n"
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


def to_record(
    case: CaseSpec | Mapping[str, Any],
    user: str | None,
    assistant: str | None,
    anchor: str,
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Như v1, NHƯNG user message được render qua `config/prompts/stream_user.j2`.

    Đây là sửa lỗi chính của v2. Record xuất ra chỉ giữ `{"id", "messages"}`, nên
    tài liệu bắt buộc phải nằm TRONG `messages` mới sống sót qua export.
    """
    case_id = case.id if isinstance(case, CaseSpec) else str(case["id"])
    context_enabled = case.context if isinstance(case, CaseSpec) else bool(case.get("context"))
    context = meta.get("synthetic_context")
    sources = context_to_sources(context) if context_enabled else []

    turns = meta.get("turns")
    messages: list[dict[str, str]] = [{"role": "system", "content": anchor}]
    if turns is not None:
        if not isinstance(turns, list):
            raise ValueError("turns must be a list")
        first_user_done = False
        for turn in turns:
            if not isinstance(turn, dict):
                raise ValueError("each turn must be an object")
            role = str(turn.get("role", ""))
            content = str(turn.get("content", ""))
            if role == "user":
                # Chỉ lượt user ĐẦU mang tài liệu, giống production: retrieval chạy
                # theo lượt hiện tại và prompt chỉ có một khối "Tài liệu tham khảo".
                content = render_user_message(content, sources if not first_user_done else [])
                first_user_done = True
            messages.append({"role": role, "content": content})
    else:
        messages.extend(
            [
                {"role": "user", "content": render_user_message(str(user or ""), sources)},
                {"role": "assistant", "content": str(assistant or "")},
            ]
        )

    generation_meta = dict(meta.get("generation_meta") or {})
    return {
        "id": str(meta["record_id"]),
        "sample_kind": case_id,
        "input_style": str(meta.get("input_style") or "standard"),
        "context": context_enabled,
        "synthetic_context": context,
        "synthetic_context_sources": list(meta.get("synthetic_context_sources") or []),
        "anchor_group": generation_meta.get("anchor_group"),
        "messages": messages,
        "points": list(meta.get("points") or []),
        "len_target": meta.get("len_target"),
        "gate_results": {"passed": False, "checks": {}},
        "generation_meta": generation_meta,
        "gen_model": str(meta.get("gen_model") or "unknown"),
    }
