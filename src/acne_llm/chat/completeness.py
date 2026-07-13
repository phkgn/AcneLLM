"""Rule-based completeness checker for acne chat input."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..schemas import UserInput


_MIN_WORDS = 4

# Field priority for questioning (in order of importance for acne advice)
_CORE_FIELDS = ["lesion_types", "distribution", "inflammation"]
_SAFETY_FIELDS = ["is_pregnant", "is_breastfeeding", "allergies"]
_ALL_FIELDS = _CORE_FIELDS + _SAFETY_FIELDS + ["skin_type", "age", "duration_weeks", "hormonal_factors", "scarring_signs", "treatment_goals"]


def _has_acne_signal(user: UserInput) -> bool:
    if user.clinical:
        c = user.clinical
        if c.lesion_types or c.lesion_distribution or c.inflammation_level:
            return True
    ctx = user.context
    return bool(
        ctx.age is not None
        or ctx.duration_weeks is not None
        or ctx.current_products
        or ctx.medications
        or ctx.is_pregnant
        or ctx.is_breastfeeding
    )


def _has_enough_to_answer(user: UserInput) -> bool:
    """True khi da co du thong tin cot loi de LLM tu van -- khong can hoi them.

    Tieu chi: co it nhat mot trong:
    - lesion_types ro (papule, pustule, nodule...)
    - inflammation_level ro (mild/moderate/severe)
    - lesion_distribution ro -- user noi vi tri cu the
    Bat ky 1 trong 3 la du de tra loi so bo; khong can ca 3.
    """
    if not user.clinical:
        return False
    c = user.clinical
    specific_lesions = [x for x in c.lesion_types if x != "other"]
    specific_inflammation = (
        c.inflammation_level in {"moderate", "severe"}
        or (
            c.inflammation_level == "mild"
            and bool(specific_lesions or c.lesion_distribution)
        )
    )
    return bool(
        specific_lesions
        or specific_inflammation
        or c.lesion_distribution
    )


@dataclass
class CompletenessResult:
    kind: Literal["too_short", "missing_core", "partial", "complaint", "sufficient"]
    question: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    clarify_reason: str | None = None
    # partial=True: co du de tu van so bo, nhung append cau hoi o cuoi response
    partial_advise: bool = False
    # Low-confidence fields that should be hedged in LLM response
    low_confidence_fields: list[str] = field(default_factory=list)

    @property
    def followup_question(self) -> str | None:
        return self.question

    @property
    def level(self) -> str:
        # "partial" va "sufficient" deu cho LLM tu van -- chi "none" moi block
        if self.kind in ("sufficient", "partial"):
            return "sufficient"
        return "none"


def _is_in_intake_flow(history: list | None) -> bool:
    """True neu bot vua hoi cau hoi clarify intake o turn truoc."""
    if not history:
        return False
    last_assistant = next(
        (t for t in reversed(history) if t.role == "assistant"),
        None,
    )
    return last_assistant is not None and last_assistant.mode == "clarify"


def _resolve_min_conf() -> float:
    """Doc nguong extract_min_field_conf tu Settings (fallback 0.60)."""
    try:
        from ..config import settings
        return settings.extract_min_field_conf
    except Exception:
        return 0.60


# Questions for each field (missing_core vs partial variant)
_FIELD_QUESTIONS: dict[str, tuple[str, str]] = {
    "lesion_types": (
        "Mụn của bạn trông như thế nào? Ví dụ: mụn đầu đen, mụn đầu trắng, mụn viêm đỏ, mụn bọc/nang.",
        "Để tư vấn chính xác hơn — mụn của bạn trông như thế nào? Ví dụ: mụn đầu đen, mụn đầu trắng, mụn viêm đỏ, hay mụn bọc/nang.",
    ),
    "distribution": (
        "Mụn ở vùng nào trên cơ thể bạn? Ví dụ: mặt, trán, cằm, lưng, vai.",
        "Bạn có thể cho mình biết mụn ở vùng nào không? Ví dụ: mặt, trán, cằm, lưng, vai.",
    ),
    "inflammation": (
        "Mụn có bị viêm không? Ví dụ: có mụn đỏ, mụn sưng, có mụn mủ, hay chỉ có mụn đầu đen thôi?",
        None,
    ),
    "is_pregnant": (
        "Bạn có đang mang thai không?",
        None,
    ),
    "is_breastfeeding": (
        "Bạn có đang cho con bú không?",
        None,
    ),
    "allergies": (
        "Bạn có bị dị ứng với sản phẩm nào không?",
        None,
    ),
    "skin_type": (
        "Loại da của bạn là gì? Ví dụ: da dầu, da khô, da hỗn hợp, hay da nhạy cảm?",
        None,
    ),
    "age": (
        "Bạn bao nhiêu tuổi?",
        None,
    ),
    "duration_weeks": (
        "Bạn bị mụn này bao lâu rồi?",
        None,
    ),
    "hormonal_factors": (
        "Có yếu tố nào liên quan đến nội tiết không? Ví dụ: kinh nguyệt, stress, chế độ ăn.",
        None,
    ),
    "scarring_signs": (
        "Có sẹo hoặc thâm sau mụn chưa?",
        None,
    ),
    "treatment_goals": (
        "Mục tiêu điều trị của bạn là gì?",
        None,
    ),
}


def _get_field_question(field: str, kind: str) -> str | None:
    """Get question for field based on kind: 'missing_core' or 'partial'."""
    q = _FIELD_QUESTIONS.get(field)
    if q is None:
        return None
    return q[1] if kind == "partial" and len(q) > 1 else q[0]


def check_completeness(
    user: UserInput,
    history: list | None = None,
    asked_fields: set | None = None,
    confidence=None,
) -> CompletenessResult:
    """Kiem tra do day du de quyet dinh: tu van / hoi lai / partial.

    confidence: ExtractionConfidence | None.
      Khi pipeline truyen confidence, mot fieldchi tinh "da co" neu dat nguong
      extract_min_field_conf (degrade an toan: field yeu -> hoi lai dung field do).
      Khi None (test build UserInput tay), giu hanh vi cu (chi xet co gia tri).
    """
    asked_fields = asked_fields or set()
    _min_conf = _resolve_min_conf()

    def _field_ok(field_name: str, has_value: bool) -> bool:
        """Check if field has value AND meets confidence threshold."""
        if not has_value:
            return False
        # No confidence map -> behavior cu (chi xet co gia tri).
        if confidence is None:
            return True
        fr = getattr(confidence, field_name, None)
        if fr is None:
            return True
        # ListFieldResult -> confident_values; FieldResult -> is_confident.
        if hasattr(fr, "confident_values"):
            return bool(fr.confident_values(_min_conf))
        if hasattr(fr, "is_confident"):
            return fr.is_confident(_min_conf)
        return True

    def _field_has_value(field_name: str) -> bool:
        """Check if field has any value in user input."""
        if field_name in ("skin_type", "age", "is_pregnant", "is_breastfeeding"):
            val = getattr(user.context, field_name, None)
            return val is not None and val not in (False, "", [])
        elif field_name in ("inflammation",):
            val = getattr(user.clinical, "inflammation_level", None) if user.clinical else None
            return val is not None and val != "unknown"
        elif field_name == "lesion_types":
            val = getattr(user.clinical, "lesion_types", []) if user.clinical else []
            return bool(val and val != ["other"])
        elif field_name == "distribution":
            # Lưu ý: field trên AcneClinicalInput tên là `lesion_distribution`.
            val = getattr(user.clinical, "lesion_distribution", []) if user.clinical else []
            return bool(val and val != ["other"])
        elif field_name == "allergies":
            # allergies nằm ở UserContext, KHÔNG phải clinical.
            val = getattr(user.context, "allergies", []) if user.context else []
            return bool(val)
        elif field_name in ("hormonal_factors", "scarring_signs", "treatment_goals"):
            val = getattr(user.clinical, field_name, []) if user.clinical else []
            return bool(val)
        elif field_name == "duration_weeks":
            return user.context.duration_weeks is not None
        return False

    def _collect_low_confidence_fields() -> list[str]:
        """Collect fields that have values but low confidence (for hedging)."""
        if confidence is None:
            return []
        low = []
        for field_name in _ALL_FIELDS:
            if _field_has_value(field_name):
                fr = getattr(confidence, field_name, None)
                if fr is not None:
                    if hasattr(fr, "max_confidence"):
                        conf = fr.max_confidence
                    elif hasattr(fr, "confidence"):
                        conf = fr.confidence
                    else:
                        continue
                    if 0 < conf < _min_conf:
                        low.append(field_name)
        return low

    word_count = len(user.description.split())
    has_signal = _has_acne_signal(user)
    has_history = bool(history)
    in_intake_flow = _is_in_intake_flow(history)

    # Chi block "too_short" khi KHONG dang trong intake flow
    if word_count < _MIN_WORDS and not has_signal and not has_history and not in_intake_flow:
        return CompletenessResult(
            kind="too_short",
            question=(
                "Ban co the mo ta them ve tinh trang da khong? "
                "Vi du: mun gi, o dau, bi bao lau roi -- minh se tu van ngay nhe."
            ),
            missing_fields=["lesion_types", "distribution"],
            clarify_reason="too_short",
        )

    # Neu dang trong intake flow (user dang reply clarify) va da co du signal
    if in_intake_flow and (_has_enough_to_answer(user) or has_signal):
        return CompletenessResult(
            kind="sufficient",
            low_confidence_fields=_collect_low_confidence_fields(),
        )

    # Chỉ HỎI LẠI field thật sự chưa có giá trị, VÀ chỉ trong nhóm field lõi
    # + an toàn (không hỏi field phụ: tuổi, thời gian, loại da, mục tiêu, nội
    # tiết, sẹo). Field đã có giá trị nhưng confidence thấp KHÔNG hỏi lại nữa —
    # độ thiếu chắc chắn được xử lý mềm qua low_confidence_fields (hedging).
    # Generic acne intake asks only clinical core fields. Safety facts are
    # collected when the user mentions medication/pregnancy and are enforced
    # by the deterministic safety context; asking every user about pregnancy
    # and allergies creates irrelevant, repetitive clarification loops.
    _askable = _CORE_FIELDS
    missing: list[str] = []
    for field in _askable:
        has_val = _field_has_value(field)
        if not has_val and field not in asked_fields:
            missing.append(field)

    if not has_signal:
        return CompletenessResult(
            kind="sufficient",
            low_confidence_fields=_collect_low_confidence_fields(),
        )

    # Neu da co du thong tin cot loi -> partial (tu van + hoi bo sung)
    if _has_enough_to_answer(user):
        # Hoi field chua tung hoi (chi 1 field)
        for field in missing:
            if field not in asked_fields:
                q = _get_field_question(field, "partial")
                if q:
                    return CompletenessResult(
                        kind="partial",
                        question=q,
                        missing_fields=[field],
                        clarify_reason="partial",
                        partial_advise=True,
                        low_confidence_fields=_collect_low_confidence_fields(),
                    )
        return CompletenessResult(
            kind="sufficient",
            low_confidence_fields=_collect_low_confidence_fields(),
        )

    # Missing core: hoi truoc khi tu van
    for field in missing:
        if field not in asked_fields:
            q = _get_field_question(field, "missing_core")
            if q:
                return CompletenessResult(
                    kind="missing_core",
                    question=q,
                    missing_fields=[field],
                    clarify_reason="missing_core",
                    low_confidence_fields=_collect_low_confidence_fields(),
                )

    return CompletenessResult(
        kind="sufficient",
        low_confidence_fields=_collect_low_confidence_fields(),
    )
