"""Single preparation path shared by SSE, WebSocket, evaluation, and debug trace."""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import TYPE_CHECKING

from ..schemas import RetrievalOutput, UserInput
from ._retrieval import retrieve_for_chat
from .extraction_confidence import build_confidence_hint
from .intake import IntakeResult, run_intake
from .fallback.intent_router import RouteDecision
from .preprocess import prepare_user_text
from ..utils.logging import log_pipeline_stage

if TYPE_CHECKING:
    from ..di import Container


@dataclass
class PreparedChatTurn:
    intake: IntakeResult
    route_metadata: dict
    mode: str
    template: str | None
    retrieval_query: str
    retrieval: RetrievalOutput | None
    system_prompt: str
    user_prompt: str
    completeness_hint: str
    retrieval_ms: int = 0


def _completeness_hint(intake: IntakeResult) -> str:
    completeness = intake.completeness
    if completeness is None or not completeness.followup_question:
        return ""
    missing = ", ".join(completeness.missing_fields)
    return (
        f"Thông tin còn thiếu: {missing}. Tư vấn từ dữ kiện hiện tại nhưng "
        "KHÔNG đặt câu hỏi bổ sung trong phần sinh; hệ thống sẽ nối chính xác "
        f"một câu hỏi sau: {completeness.followup_question}"
    )


def prepare_chat_turn(
    c: "Container",
    message: str,
    requested_mode: str = "auto",
    session_id: str | None = None,
    user_override: UserInput | None = None,
    include_analytics: bool = False,
) -> PreparedChatTurn:
    """Prepare route, selected context, RAG and prompt exactly once."""
    intake = run_intake(
        c, message, session_id=session_id, mode_request=requested_mode,
        include_analytics=include_analytics,
    )
    if (
        user_override is not None
        and intake.route_decision is not None
        and intake.route_decision.primary_intent in {"advise", "knowledge"}
    ):
        # Explicit profile fields supplied by trusted local callers (CLI/eval).
        # Only confirmed safety facts may influence the prompt.
        intake.user = user_override
        intake.confirmed_profile = {
            "is_pregnant": bool(user_override.context.is_pregnant),
            "is_breastfeeding": bool(user_override.context.is_breastfeeding),
            "allergies": list(user_override.context.allergies or []),
            "medications": list(user_override.context.medications or []),
            "current_products": list(user_override.context.current_products or []),
        }
        explicit_safety = []
        if user_override.context.is_pregnant:
            explicit_safety.append("pregnancy")
        if user_override.context.is_breastfeeding:
            explicit_safety.append("breastfeeding")
        explicit_safety.extend(str(item).lower() for item in user_override.context.medications or [])
        intake.safety_terms = list(dict.fromkeys([*intake.safety_terms, *explicit_safety]))
    route_metadata = intake.route_decision.metadata() if intake.route_decision else {}
    primary_intent = str(route_metadata.get("primary_intent") or "advise")
    mode = "hybrid" if intake.effective_mode == "hybrid" else "llm_only"

    retrieval = None
    retrieval_started = time.perf_counter()
    should_retrieve = (
        mode == "hybrid"
        and intake.scope_refusal is None
        and intake.effective_mode not in {"refuse", "clarify"}
        and primary_intent not in {"clarify", "reject"}
        and (intake.is_acne_signal or bool(intake.safety_terms) or bool(intake.history))
    )
    retrieval_ms = 0
    if should_retrieve:
        retrieval = retrieve_for_chat(
            c,
            intake.user,
            route_flags=(intake.route_decision.route_flags if intake.route_decision else []),
            normalized_query=intake.normalized_query,
            safety_terms=intake.safety_terms,
        )
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)
    log_pipeline_stage(
        session_id,
        "RAG",
        retrieval_started,
        status=("ready" if retrieval is not None else "skipped"),
        mode=mode,
        chunks=(len(retrieval.chunks) if retrieval is not None else 0),
        scope=intake.scope_decision,
    )

    # Rule không được tự viết câu trả lời. Guardrail quyết NỘI DUNG (ruling),
    # generator viết CÂU CHỮ. Bản disclaimer cứng vẫn được nối lại ở
    # runtime.get_safety_suffix nên ràng buộc y khoa không mất.
    if intake.scope_refusal is not None or intake.effective_mode == "refuse":
        template = "refuse_user.j2"
    elif primary_intent == "reject":
        template = "reject_user.j2"
    elif primary_intent == "clarify":
        template = "clarify_user.j2"
    elif primary_intent == "knowledge":
        template = "knowledge_user.j2"
    else:
        template = "stream_user.j2"

    system_prompt = user_prompt = ""
    hint = _completeness_hint(intake)
    refusal = intake.scope_refusal
    if refusal is not None:
        hint = refusal.disclaimer or "\n".join(refusal.causes)
    # Hedge cho known_facts: field trích xuất confidence thấp -> nhắc LLM hỏi lại
    # thay vì khẳng định (known_facts hiện inject như "đã xác nhận + bất biến").
    if intake.extraction_confidence is not None:
        conf_hint = build_confidence_hint(intake.extraction_confidence, field_threshold=0.6)
        if conf_hint:
            hint = (hint + " " + conf_hint).strip() if hint else conf_hint
    if template is not None:
        system_prompt, user_prompt = c.prompt.build(
            user=intake.user,
            retrieval=retrieval,
            template=template,
            detected_language="unknown",
            query_vi="",
            max_context_chars=getattr(c.settings, "chat_max_context_chars", 4500),
            history=intake.history,
            route_metadata=route_metadata,
            completeness_hint=hint,
            confirmed_profile=intake.confirmed_profile,
        )

    return PreparedChatTurn(
        intake=intake,
        route_metadata=route_metadata,
        mode=mode,
        template=template,
        retrieval_query=intake.normalized_query,
        retrieval=retrieval,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        completeness_hint=hint,
        retrieval_ms=retrieval_ms,
    )


def generate_prose(
    c: "Container",
    prepared: PreparedChatTurn,
    temperature: float | None = None,
) -> str:
    """Generate non-stream prose from the same prompt contract as SSE.

    T3 eval and the CLI use this helper. The user-facing HTTP route remains SSE;
    T4 covers stream transport, persistence and event-level post-processing.
    """
    text = c.llm.generate_text(
        prepared.system_prompt,
        prepared.user_prompt,
        temperature=temperature,
    )
    text = re.sub(r"[一-鿿぀-ゟ゠-ヿ가-힯]+", "", text)
    return text
