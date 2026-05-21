"""Rule-based completeness checker for acne chat input."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..schemas import UserInput


_MIN_WORDS = 4


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


def check_completeness(
    user: UserInput,
    history: list | None = None,
    asked_fields: set | None = None,
) -> CompletenessResult:
    asked_fields = asked_fields or set()
    word_count = len(user.description.split())
    has_signal = _has_acne_signal(user)
    has_history = bool(history)
    in_intake_flow = _is_in_intake_flow(history)

    # Chi block "too_short" khi KHONG dang trong intake flow
    # (reply ngan "o ma", "mun viem" la hop le khi bot vua hoi)
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
    # -> khong hoi them nua, de LLM tu van luon voi thong tin hien co.
    if in_intake_flow and (_has_enough_to_answer(user) or has_signal):
        return CompletenessResult(kind="sufficient")

    clinical = user.clinical
    missing: list[str] = []
    if not (clinical and clinical.lesion_types):
        missing.append("lesion_types")
    if not (clinical and clinical.lesion_distribution):
        missing.append("distribution")

    if not has_signal:
        return CompletenessResult(kind="sufficient")

    # Neu da co du thong tin cot loi (lesion, inflammation hoac location ro)
    # -> partial: tu van luon nhung append cau hoi bo sung o cuoi response
    if _has_enough_to_answer(user):
        # Chi goi hoi field phu mot lan (chua tung hoi) -- khong block LLM
        if "lesion_types" in missing and "lesion_types" not in asked_fields:
            return CompletenessResult(
                kind="partial",
                question=(
                    "De tu van chinh xac hon -- mun cua ban trong nhu the nao? "
                    "Vi du: mun dau den, mun dau trang, mun viem do, hay mun boc/nang."
                ),
                missing_fields=["lesion_types"],
                clarify_reason="partial",
                partial_advise=True,
            )
        if "distribution" in missing and "distribution" not in asked_fields:
            return CompletenessResult(
                kind="partial",
                question=(
                    "Ban co the cho minh biet mun o vung nao khong? "
                    "Vi du: mat, tran, cam, lung, vai."
                ),
                missing_fields=["distribution"],
                clarify_reason="partial",
                partial_advise=True,
            )
        return CompletenessResult(kind="sufficient")

    # Chi hoi field chua tung hoi, hoi tung cai mot theo thu tu uu tien
    if "lesion_types" in missing and "lesion_types" not in asked_fields:
        return CompletenessResult(
            kind="missing_core",
            question=(
                "Mun cua ban trong nhu the nao? "
                "Vi du: mun dau den, mun dau trang, mun viem do, mun boc/nang."
            ),
            missing_fields=["lesion_types"],
            clarify_reason="missing_core",
        )

    if "distribution" in missing and "distribution" not in asked_fields:
        return CompletenessResult(
            kind="missing_core",
            question=(
                "Mun o vung nao tren co the ban? "
                "Vi du: mat, tran, cam, lung, vai."
            ),
            missing_fields=["distribution"],
            clarify_reason="missing_core",
        )

    # Da hoi du cac field hoac khong con field nao thieu -> cho LLM tu van
    return CompletenessResult(kind="sufficient")
