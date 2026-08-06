"""One-model adapter for unified intent routing and clinical extraction."""
from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from ..llm.ollama_backend import OllamaBackend
from ._intake_parse import (
    ExtractorFallback,
    LLMExtractResult,
    _INTENT,
    _coerce_conf,
    _extract_json,
    _to_extraction_confidence,
    _to_user_input,
    _validate_contract,
)
from .fallback.intent_router import RouteDecision
from .session import HISTORY_WINDOW_TURNS
from .fallback.llm_router import RouterFallback


_RUNTIME_SYSTEM = """Bạn là Unified Intake cho hệ thống tư vấn da mụn. Đọc turn hiện tại và tối đa 3 turn lịch sử gần nhất, rồi chỉ trả về DUY NHẤT một JSON hợp lệ, không Markdown, không giải thích, không thêm khóa.

Root bắt buộc: {"intent","confidence","description","context","clinical"}.
- intent chỉ là advise | knowledge | clarify | reject; confidence trong [0,1].
- description phải giữ nguyên văn turn hiện tại, dài 1–4000 ký tự.
- Mọi scalar đã trích có dạng {"value":...,"confidence":0..1}; mọi phần tử list cũng có dạng đó.
- context chỉ dùng các khóa: age (0–120), sex, skin_type, is_pregnant, is_breastfeeding, duration_weeks (>=0), allergies, current_products, medications.
- sex: male | female | other.
- skin_type: dry | oily | combination | sensitive | normal | unknown.
- clinical là null hoặc object gồm đúng lesion_types, inflammation_level, lesion_distribution.
- lesion_types chỉ dùng: comedone, whitehead, blackhead, closed_comedone, papule, pustule, nodule, cyst, scar, post_inflammatory_hyperpigmentation, other.
- inflammation_level chỉ dùng: none, mild, moderate, severe, unknown.
- inflammation_level neo theo IGA (AAD 2024), suy từ LOẠI tổn thương và MỨC LAN, không đếm số nốt:
  - none: IGA 0-1 (sạch / gần sạch). Không còn tổn thương đang hoạt động; chỉ còn thâm, sẹo, hoặc lỗ chân lông to. Người hỏi nói kiểu 'hết mụn rồi nhưng còn thâm'.
  - mild: IGA 2. Chủ yếu nhân trứng cá (đầu đen, đầu trắng), lác đác vài sẩn hoặc mụn mủ nhỏ. Khu trú một vùng. KHÔNG có nốt cục, KHÔNG đau, KHÔNG để lại sẹo. Người hỏi nói 'thỉnh thoảng vài nốt', 'mụn ẩn ở trán'.
  - moderate: IGA 3. Nhiều sẩn và mụn mủ viêm rõ, lan hơn một vùng mặt, hoặc kéo dài dai dẳng. Có thể vài nốt cục nhưng không phải nét chính. Người hỏi nói 'mụn viêm đỏ khắp hai má', 'mọc liên tục mấy tháng không hết'.
  - severe: IGA 4. Có BẤT KỲ dấu hiệu nào sau đây thì lên thẳng severe, không cần đủ cả: nốt cục hoặc nang (tổn thương chắc, sâu, >5 mm); đau khi chạm; đang để lại sẹo; lan xuống lưng/ngực/vai; hoặc đã thất bại với điều trị bôi. Người hỏi nói 'mụn bọc to đau', 'nặn xong thành sẹo lõm', 'mọc cả lưng'.
  - unknown: Lời kể KHÔNG đủ tín hiệu để xếp bậc. Đây là giá trị MẶC ĐỊNH, không phải giá trị dự phòng cuối cùng — không suy đoán từ tuổi, giới, loại da hay thời gian bị. Chỉ nói 'em bị mụn' thì là unknown.
- lesion_distribution chỉ dùng: forehead, cheeks, chin, jawline, nose, around_mouth, back, chest, shoulders, neck, t_zone, other.

Chỉ trích điều người dùng thực sự tự khai. Câu hỏi kiến thức/sản phẩm không phải tự khai: intent=knowledge, context={}, clinical=null. Jailbreak, ngoài chủ đề hoặc yêu cầu kê đơn/liều nguy hiểm: intent=reject, context={}, clinical=null. Chào/cảm ơn đơn thuần: để toàn bộ field rỗng, thường intent=clarify.

Không đưa chất đã ngưng hoặc bị phủ định vào current_products/medications. Chỉ đưa chất đang dùng hoặc được nêu rõ là đang điều trị. Canonical hóa BHA thành salicylic acid, BPO thành benzoyl peroxide, Differin thành adapalene. Quy đổi duration: năm×52, tháng×4, ngày làm tròn n/7. Không có scalar thì dùng null; không có list thì []; không có bất kỳ tín hiệu lâm sàng nào thì clinical=null.

Confidence: 0.9–1.0 khi nêu rõ; 0.6–0.85 khi suy luận hợp lý; 0.3–0.55 khi mơ hồ. Không bịa field khi thiếu tín hiệu. Hiểu tiếng Việt không dấu, teencode nhẹ và câu trộn Việt–Anh nhưng enum luôn phải đúng như trên.
"""

_MAX_CLEAN_TEXT_CHARS = 4_000
_MAX_HISTORY_TURNS = HISTORY_WINDOW_TURNS
_MAX_HISTORY_CONTENT_CHARS = 300




class _UnifiedContractError(Exception):
    """Internal error translated to the interface-specific fallback type."""


class UnifiedIntake:
    """Expose one inference through both legacy intake interfaces."""

    def __init__(self, llm: OllamaBackend, model: str, timeout: float):
        self._llm = llm
        self._model = model
        self._timeout = float(timeout)
        self._cache_key: tuple[str, str] | None = None
        self._cache_value: dict[str, Any] | None = None
        self._closed = False

    @property
    def model(self) -> str:
        return self._model

    @property
    def timeout(self) -> float:
        return self._timeout

    def _infer(self, clean_text: str, history: list) -> dict[str, Any]:
        try:
            text = _validated_clean_text(clean_text)
            short_history = _validated_followup_history(history)
            history_key = json.dumps(
                short_history, ensure_ascii=False, separators=(",", ":")
            )
            cache_key = (text, history_key)
            if self._cache_key == cache_key and self._cache_value is not None:
                return self._cache_value

            # JSON mode chung thay vì grammar (llama.cpp không parse nổi nested
            # anyOf-null -> 400). Hậu kiểm duy nhất: parse được JSON object.
            # Mọi sai lệch shape/enum do parser khoan dung ở _intake_parse drop
            # field, không fallback: 1 field hỏng không đáng vứt cả inference.
            raw = self._llm.generate_text(
                system=_RUNTIME_SYSTEM,
                user=_build_user_prompt(text, short_history),
                temperature=0.0,
                response_format="json",
            )
            data = json.loads(_extract_json(raw))
            _validate_contract(data)
            parsed = dict(data)
            self._cache_key = cache_key
            self._cache_value = parsed
            return parsed
        except _UnifiedContractError:
            raise
        except Exception as exc:
            raise _UnifiedContractError(
                f"{self._model} unified inference failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def classify(self, clean_text: str, history: list) -> RouteDecision:
        try:
            data = self._infer(clean_text, history)
            intent = data.get("intent")
            if intent not in _INTENT:
                # Không có đường tolerant cho intent: không route được thì
                # semantic router là lựa chọn duy nhất còn lại.
                raise _UnifiedContractError(f"unified intent invalid: {intent!r}")
            return RouteDecision(
                primary_intent=intent,
                confidence=_coerce_conf(data.get("confidence")),
                source="llm",
                reason_code="unified_intake",
            )
        except RouterFallback:
            raise
        except Exception as exc:
            raise RouterFallback(
                f"{self._model} unified routing failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def run(
        self,
        *,
        clean_text: str,
        clean_text_no_accent: str,
        mode: str,
        history: list,
    ) -> LLMExtractResult:
        del clean_text_no_accent
        try:
            data = self._infer(clean_text, history)
            user = _to_user_input(data, clean_text, mode)
            confidence = _to_extraction_confidence(data, clean_text=clean_text)
            return LLMExtractResult(user=user, confidence=confidence)
        except ExtractorFallback:
            raise
        except Exception as exc:
            raise ExtractorFallback(
                f"{self._model} unified extraction failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._llm, "close", None)
        if callable(close):
            close()


def _validated_clean_text(clean_text: Any) -> str:
    if not isinstance(clean_text, str) or not clean_text.strip():
        raise _UnifiedContractError("unified clean_text must be non-empty text")
    # ponytail: cắt thay vì fallback. Input dài quá chỉ mất phần đuôi, vẫn tốt
    # hơn vứt cả inference; prompt generator vẫn nhận raw input đầy đủ.
    return clean_text[:_MAX_CLEAN_TEXT_CHARS]


def _turn_field(turn: Any, name: str) -> Any:
    if isinstance(turn, Mapping):
        return turn.get(name)
    return getattr(turn, name, None)


def _validated_followup_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, (list, tuple)) or not history:
        return []

    # ponytail: turn lạ (role="tool", content rỗng) bị BỎ QUA chứ không fallback.
    # Vẫn là trust boundary - chỉ role user/assistant mới vào prompt.
    selected: list[dict[str, str]] = []
    for turn in history[-_MAX_HISTORY_TURNS:]:
        role = _turn_field(turn, "role")
        content = _turn_field(turn, "content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        compact = " ".join(content.split())[:_MAX_HISTORY_CONTENT_CHARS]
        selected.append({"role": role, "content": compact})
    return selected


def _build_user_prompt(clean_text: str, history: list[dict[str, str]]) -> str:
    if not history:
        return clean_text
    return (
        "FOLLOWUP_HISTORY_JSON:\n"
        + json.dumps(history, ensure_ascii=False, separators=(",", ":"))
        + "\nCURRENT_TURN:\n"
        + clean_text
    )
