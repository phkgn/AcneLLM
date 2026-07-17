"""Single preparation path shared by POST, SSE, WebSocket and debug trace."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Literal, TYPE_CHECKING

from ..schemas import AdviseOutput, RetrievalOutput, UserInput
from ._retrieval import retrieve_for_chat
from .extraction_confidence import build_confidence_hint
from .intake import IntakeResult, run_intake
from .intent_router import RouteDecision
from .preprocess import prepare_user_text

if TYPE_CHECKING:
    from ..di import Container


ResponseFormat = Literal["text", "structured"]


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
    fixed_reply: str = ""
    retrieval_ms: int = 0


def _social_reply(message: str) -> tuple[str, str] | None:
    prepared = prepare_user_text(message)
    lowered = prepared.clean_text.lower().strip(" .!?,")
    if len(lowered.split()) > 8:
        return None
    if re.fullmatch(r"(?:ok(?:e|ay)?|ừ|uh|uk|ừm|uhm)", lowered):
        return "social_ack", "Ừ nhé."
    if re.fullmatch(r"(?:ha){2,}|h+a+h+a+|(?:he){2,}|(?:hi){2,}|lol+", lowered):
        return "social_laughter", "😄"
    if any(term in lowered for term in (
        "không muốn hỏi nữa", "khong muon hoi nua", "dừng lại", "dung lai",
        "thôi không hỏi", "thoi khong hoi",
    )):
        return "social_exit", "Được nhé. Khi nào cần bạn cứ quay lại."
    acne_content = any(term in lowered for term in (
        "mụn", "da", "thuốc", "kem", "bha", "bpo", "retinol", "nghệ", "nha đam",
    ))
    if (
        any(term in lowered for term in ("cảm ơn", "cam on", "thank you", "thanks"))
        and not acne_content
        and "?" not in message
    ):
        return "social_thanks", "Không có gì nhé."
    greeting_only = re.fullmatch(
        r"(?:xin chào|chào|hello|hi|hey)(?:\s+(?:bạn|bác sĩ|bs|ad|admin))?",
        lowered,
    )
    if greeting_only:
        return "social_greeting", "Chào bạn. Bạn cần hỏi gì về mụn?"
    return None


def _prepare_social_turn(message: str, kind: str, reply: str) -> PreparedChatTurn:
    prepared = prepare_user_text(message)
    route = RouteDecision(
        primary_intent="knowledge",
        confidence=1.0,
        query_subject="non_self",
        route_flags=[kind],
        reason_code=kind,
    )
    intake = IntakeResult(
        raw_message=message,
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
        user=UserInput(description=prepared.clean_text, mode="llm_only"),
        turn_snapshot=None,
        history=[],
        effective_mode="llm_only",
        scope_decision="pass_to_llm_soft",
        route_decision=route,
        normalized_query=prepared.clean_text,
        teencode_replaced=prepared.teencode_replaced,
    )
    return PreparedChatTurn(
        intake=intake,
        route_metadata=route.metadata(),
        mode="llm_only",
        template=None,
        retrieval_query=prepared.clean_text,
        retrieval=None,
        system_prompt="",
        user_prompt="",
        completeness_hint="",
        fixed_reply=reply,
        retrieval_ms=0,
    )


def _completeness_hint(intake: IntakeResult) -> str:
    completeness = intake.completeness
    if completeness is None or not completeness.followup_question:
        return ""
    missing = ", ".join(completeness.missing_fields)
    if completeness.kind == "too_short":
        return "Tin nhắn chưa rõ; hãy hỏi đúng một câu bổ sung cần thiết nhất."
    if completeness.kind in {"missing_core", "partial"}:
        return (
            f"Thông tin còn thiếu: {missing}. Tư vấn sơ bộ từ dữ kiện hiện tại "
            "và chỉ hỏi thêm một ý nếu thực sự cần."
        )
    return ""


def prepare_chat_turn(
    c: "Container",
    message: str,
    requested_mode: str = "auto",
    session_id: str | None = None,
    response_format: ResponseFormat = "text",
    user_override: UserInput | None = None,
    include_analytics: bool = False,
) -> PreparedChatTurn:
    """Prepare route, selected context, RAG and prompt exactly once."""
    social = _social_reply(message)
    if social is not None:
        return _prepare_social_turn(message, *social)
    intake = run_intake(
        c, message, session_id=session_id, mode_request=requested_mode,
        include_analytics=include_analytics,
    )
    if user_override is not None:
        # Compatibility adapter for the legacy structured POST payload. These
        # fields are explicit for this turn, but only confirmed safety facts
        # are allowed to persist/influence the system prompt.
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
    should_retrieve = (
        mode == "hybrid"
        and intake.scope_refusal is None
        and intake.effective_mode not in {"refuse", "clarify"}
        and primary_intent not in {"clarify", "reject"}
        and (intake.is_acne_signal or bool(intake.safety_terms) or bool(intake.history))
    )
    retrieval_ms = 0
    if should_retrieve:
        retrieval_started = time.perf_counter()
        retrieval = retrieve_for_chat(
            c,
            intake.user,
            None,
            route_flags=(intake.route_decision.route_flags if intake.route_decision else []),
            normalized_query=intake.normalized_query,
            safety_terms=intake.safety_terms,
        )
        retrieval_ms = int((time.perf_counter() - retrieval_started) * 1000)

    if intake.scope_refusal is not None or intake.effective_mode == "refuse":
        template = None
    elif response_format == "structured":
        template = "hybrid_user.j2" if mode == "hybrid" else "llm_only_user.j2"
    elif primary_intent == "clarify":
        template = "clarify_user.j2"
    elif primary_intent == "knowledge":
        template = "knowledge_user.j2"
    else:
        template = "stream_user.j2"

    system_prompt = user_prompt = ""
    hint = _completeness_hint(intake)
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
            clinical_plan=None,
            history=intake.history,
            route_metadata=route_metadata,
            completeness_hint=hint,
            confirmed_profile=intake.confirmed_profile,
            inline_citation=getattr(c.settings, "inline_citation", "off"),
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
        fixed_reply="",
        retrieval_ms=retrieval_ms,
    )


def generate_structured(c: "Container", prepared: PreparedChatTurn) -> AdviseOutput:
    """Generate the POST JSON response from the same prepared turn as streaming."""
    if prepared.fixed_reply:
        return AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=[prepared.fixed_reply],
            confidence=1.0,
            mode="llm_only",
            model_name="deterministic",
        )
    raw = c.llm.generate_json(
        prepared.system_prompt,
        prepared.user_prompt,
        schema=AdviseOutput.model_json_schema(),
    )
    parsed: AdviseOutput | None = None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    for candidate in (raw, match.group() if match else ""):
        if not candidate:
            continue
        try:
            parsed = AdviseOutput.model_validate(json.loads(candidate))
            break
        except Exception:
            continue
    if parsed is None:
        parsed = AdviseOutput(
            severity="unknown",
            acne_type_primary="unknown",
            causes=["Không thể phân tích phản hồi từ LLM, vui lòng thử lại."],
            confidence=0.1,
        )
    if str(getattr(c.settings, "inline_citation", "off")) != "model":
        from .inline_citations import strip_inline_citations_value

        parsed = AdviseOutput.model_validate(
            strip_inline_citations_value(parsed.model_dump(mode="python"))
        )
    parsed.used_chunks = [chunk.chunk_id for chunk in prepared.retrieval.chunks] if prepared.retrieval else []
    parsed.mode = prepared.mode
    parsed.model_name = getattr(c.llm, "model", "")
    return c.guardrails.post_check(parsed, prepared.intake.user)
