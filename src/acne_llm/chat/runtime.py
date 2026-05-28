"""Streaming chat runtime -- orchestrator chinh cho /chat/stream va /ws/chat.

Flow:
    message -> intake (guardrails + completeness) -> retrieve -> build_prompt
    -> llm.stream_text -> safety suffix -> SSE events -> persist session -> audit
"""
from __future__ import annotations

from collections.abc import Iterator
import inspect
import json
import time
from typing import TYPE_CHECKING

from loguru import logger

from .intake import run_intake
from .session import ConversationTurn, get_session_store
from ._retrieval import retrieve_for_chat, citation_data, compute_evidence_quality
from ._safety import get_safety_suffix
from ..db.audit import AuditEntry
from ..guardrails.ood_detector import mask_pii

if TYPE_CHECKING:
    from ..di import Container
    from .intake import IntakeResult


# -- SSE helper ---------------------------------------------------------------

def _event(event: str, data) -> str:
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _snapshot_for_persistence(intake: "IntakeResult"):
    route = intake.route_decision
    if route is None or route.query_subject != "self":
        return None
    return intake.turn_snapshot


def _supports_keyword(callable_obj, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return True
    return (
        keyword in signature.parameters
        or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())
    )


# -- Main stream entry point --------------------------------------------------

def stream_chat_sse(
    c: "Container",
    message: str,
    requested_mode: str = "auto",
    session_id: str | None = None,
    temperature: float | None = None,
) -> Iterator[str]:
    """Yield SSE-formatted strings cho chat UI (Next.js EventSource)."""
    started = time.perf_counter()
    try:
        intake = run_intake(c, message, session_id=session_id, mode_request=requested_mode)
        clean_message = intake.clean_text
        history = intake.history
        user = intake.user
        mode = "hybrid" if intake.effective_mode == "hybrid" else "llm_only"
        display_mode = "clarify" if intake.effective_mode == "clarify" else mode
        route_metadata = intake.route_decision.metadata() if intake.route_decision else {}
        persist_snapshot = _snapshot_for_persistence(intake)
        _primary_intent = (
            intake.route_decision.primary_intent if intake.route_decision else "advise"
        )
        # Dung container session store (JSONL in production; in-memory fallback for tests).
        sess = getattr(c, "session_store", None) or get_session_store()

        # M5: Progress/follow-up intent — annotate route_metadata so prompt builder
        # and session store know this is a treatment check-in turn.
        _rflags = intake.route_decision.route_flags if intake.route_decision else []
        if "progress_followup" in _rflags:
            route_metadata["is_progress_followup"] = True
            # Increment follow-up counter in session for future turns context
            if session_id and hasattr(sess, "increment_followup_count"):
                sess.increment_followup_count(session_id, 1.0)

        # -- 1. Scope refusal -------------------------------------------------
        if intake.scope_refusal is not None:
            # Bug #5 fix: track guardrail trigger count
            _gr = getattr(c, "guardrails", None)
            if _gr is not None:
                _gr.trigger_count = getattr(_gr, "trigger_count", 0) + 1
            assistant_text = (
                intake.scope_refusal.disclaimer
                or "\n".join(intake.scope_refusal.causes)
            )
            if session_id:
                sess.append_turn(
                    session_id,
                    ConversationTurn(
                        role="user",
                        # F10: lưu nguyên văn user gõ, không phải bản đã preprocess.
                        # Fold/normalize sẽ re-run trên history nếu cần.
                        content=intake.raw_message,
                        mode=mode,
                        normalized_snapshot=persist_snapshot,
                        metadata=route_metadata,
                    ),
                )
                sess.append_turn(
                    session_id,
                    ConversationTurn(role="assistant", content=assistant_text, mode="llm_only"),
                )
            yield _event("token", assistant_text)
            yield _event("done", {
                "mode": "refuse",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "used_chunks": [],
                "session_id": session_id,
            })
            return

        # -- 2. Completeness hint (soft) --------------------------------------
        # Thay vì block LLM với hardcoded string, chuyển completeness thành
        # instruction inject vào prompt để model tự hỏi một cách tự nhiên.
        completeness = intake.completeness
        completeness_hint: str | None = None
        if completeness is not None and completeness.followup_question:
            if completeness.kind == "too_short":
                completeness_hint = (
                    "Tin nhắn rất ngắn, chưa rõ tình trạng mụn. "
                    "Hãy trả lời thân thiện và hỏi thêm: loại mụn gì, ở đâu, bị bao lâu."
                )
            elif completeness.kind == "missing_core":
                missing = ", ".join(completeness.missing_fields)
                completeness_hint = (
                    f"Chưa có thông tin: {missing}. "
                    "Có thể tư vấn sơ bộ nếu có đủ dữ liệu khác, "
                    "rồi hỏi tự nhiên 1 câu để làm rõ thêm ở cuối."
                )
            elif completeness.kind == "partial" and completeness.partial_advise:
                missing = ", ".join(completeness.missing_fields)
                completeness_hint = (
                    f"Thông tin còn thiếu: {missing}. "
                    "Tư vấn dựa trên thông tin hiện có, "
                    "rồi hỏi tự nhiên 1 câu bổ sung ở cuối nếu cần."
                )

        # -- 3. Retrieve ------------------------------------------------------
        clinical_plan = intake.clinical_plan
        rag_signal = intake.is_acne_signal or clinical_plan is not None or bool(intake.safety_terms)
        t_rag = time.perf_counter()
        _route_flags_for_rag = intake.route_decision.route_flags if intake.route_decision else []
        retrieval = (
            retrieve_for_chat(
                c,
                user,
                clinical_plan,
                route_flags=_route_flags_for_rag,
                normalized_query=intake.normalized_query,
                safety_terms=intake.safety_terms,
            )
            if mode == "hybrid" and rag_signal and _primary_intent not in {"clarify", "reject"}
            else None
        )
        if retrieval is not None:
            logger.debug(
                "[{}] RAG: {} chunks in {:.0f}ms (scope={} plan={})",
                (session_id or "")[:8],
                len(retrieval.chunks),
                (time.perf_counter() - t_rag) * 1000,
                intake.scope_decision,
                clinical_plan is not None,
            )
        else:
            logger.debug(
                "[{}] RAG: skipped (mode={} signal={} plan={})",
                (session_id or "")[:8],
                mode,
                rag_signal,
                clinical_plan is not None,
            )

        # -- 4. Build prompt --------------------------------------------------
        # Chọn template theo primary_intent.
        if _primary_intent == "clarify":
            _template = "clarify_user.j2"
        elif _primary_intent == "knowledge":
            _template = "knowledge_user.j2"
        else:
            _template = "stream_user.j2"
        system, user_message = c.prompt.build(
            user=user,
            retrieval=retrieval,
            template=_template,
            detected_language=(
                clinical_plan.detected_language if clinical_plan else "unknown"
            ),
            query_vi=(
                clinical_plan.rag_queries.query_vi if clinical_plan else intake.normalized_query
            ),
            max_context_chars=getattr(c.settings, "chat_max_context_chars", 4500),
            clinical_plan=clinical_plan,
            history=history,
            route_metadata=route_metadata,
            system_override=c.prompt.system_stream(),
            completeness_hint=completeness_hint,
        )

        # -- 5. LLM stream ----------------------------------------------------
        # Knowledge queries cần temperature cao hơn để model không tự cắt sớm
        _default_temp = getattr(c.settings, "llm_temperature", 0.3)
        _knowledge_temp = max(_default_temp, 0.5)
        effective_temperature = (
            temperature
            if temperature is not None
            else (_knowledge_temp if _primary_intent == "knowledge" else _default_temp)
        )
        prompt_chars = len(system) + len(user_message)
        logger.debug(
            "[{}] PROMPT: {:.0f} chars (~{:.0f} tokens) -> LLM",
            (session_id or "")[:8],
            prompt_chars,
            prompt_chars / 3.5,
        )
        # M7 + M2: Pre-stream prefixes (repeated question / empathy)
        pre_prefix = ""
        route_flags_pre = intake.route_decision.route_flags if intake.route_decision else []

        if "crisis_signal" in route_flags_pre:
            # Crisis overrides everything — gentle acknowledgment first
            pre_prefix = (
                "Mình hiểu bạn đang rất khó chịu và lo lắng. "
                "Nếu bạn cảm thấy quá căng thẳng, hãy nói chuyện với người thân hoặc "
                "chuyên gia tâm lý nhé. Về phần da, "
            )
            yield _event("token", pre_prefix)
            logger.debug("[{}] Crisis signal — empathy prefix yielded", (session_id or "")[:8])
        elif "emotional_distress" in route_flags_pre:
            # M2: Empathy prefix for emotional distress (không crisis)
            pre_prefix = "Mình hiểu mụn có thể ảnh hưởng đến tâm lý nhiều lắm — "
            yield _event("token", pre_prefix)
            logger.debug("[{}] Emotional distress — empathy prefix yielded", (session_id or "")[:8])
        elif "repeated_question" in route_flags_pre:
            # M7: Repeated question acknowledgment
            pre_prefix = "Như mình đã chia sẻ, "
            yield _event("token", pre_prefix)
            logger.debug("[{}] Repeated question — prefix yielded", (session_id or "")[:8])

        t_llm = time.perf_counter()
        tokens: list[str] = []
        first_token = True
        # Knowledge queries: không hard-cap output, để model tự dừng khi xong
        _stream_num_predict = -1 if _primary_intent == "knowledge" else None
        stream_kwargs = {"temperature": effective_temperature}
        if (
            _stream_num_predict is not None
            and _supports_keyword(c.llm.stream_text, "num_predict")
        ):
            stream_kwargs["num_predict"] = _stream_num_predict
        import re as _re
        _CJK_RE = _re.compile(r"[一-鿿぀-ゟ゠-ヿ가-힯]+")
        _cjk_total = 0

        stream_iter = c.llm.stream_text(system, user_message, **stream_kwargs)
        for token in stream_iter:
            if first_token:
                logger.debug(
                    "[{}] LLM first token in {:.0f}ms",
                    (session_id or "")[:8],
                    (time.perf_counter() - t_llm) * 1000,
                )
                first_token = False
            # Guard: strip CJK per-token trước khi yield ra UI
            if _CJK_RE.search(token):
                clean_token = _CJK_RE.sub("", token)
                _cjk_total += len(token) - len(clean_token)
                token = clean_token
            if token:
                tokens.append(token)
                yield _event("token", token)

        if _cjk_total > 0:
            logger.warning(
                "[{}] CJK guard: stripped {} CJK chars from LLM stream",
                (session_id or "")[:8],
                _cjk_total,
            )

        full_text = pre_prefix + "".join(tokens)
        logger.debug(
            "[{}] LLM done: {} tokens in {:.0f}ms",
            (session_id or "")[:8],
            len(tokens),
            (time.perf_counter() - t_llm) * 1000,
        )

        # -- 6. Safety suffix -------------------------------------------------
        # Streaming text is not an AdviseOutput, so avoid constructing a dummy
        # object for post_check. Keep only text-aware suffix rules here.
        route_flags = intake.route_decision.route_flags if intake.route_decision else []
        is_knowledge_intent = (
            intake.route_decision is not None
            and intake.route_decision.primary_intent == "knowledge"
        )
        safety_route_flags = route_flags
        if is_knowledge_intent and "urgent_personal_case" not in route_flags:
            safety_route_flags = [f for f in route_flags if f != "urgency_red_flag"]
        warning_suffix = get_safety_suffix(
            full_text,
            user,
            route_flags=safety_route_flags,
            skip_generic_disclaimer=is_knowledge_intent,
            recent_turns=history,
            current_turn_text=message,
        )

        if warning_suffix:
            yield _event("token", warning_suffix)

        # -- 6b. Partial advise follow-up question ----------------------------
        # kind="partial": LLM đã trả lời sơ bộ; append câu hỏi bổ sung ở cuối
        # để không block response nhưng vẫn thu thập thêm thông tin.
        partial_question_suffix = ""
        if (
            intake.completeness is not None
            and intake.completeness.kind == "partial"
            and intake.completeness.partial_advise
            and intake.completeness.followup_question
        ):
            partial_question_suffix = "\n\n" + intake.completeness.followup_question
            yield _event("token", partial_question_suffix)
            # Bug fix: mark fields as asked so completeness checker doesn't
            # repeat the same follow-up question on subsequent turns.
            if intake.completeness.missing_fields and session_id:
                sess.mark_fields_asked(session_id, intake.completeness.missing_fields)

        # -- 7. Citations -----------------------------------------------------
        used_chunks = [chunk.chunk_id for chunk in retrieval.chunks] if retrieval else []
        if retrieval:
            for chunk in retrieval.chunks:
                yield _event("citation", citation_data(chunk))

        # -- 8. Persist session -----------------------------------------------
        full_assistant_text = full_text + (warning_suffix or "") + partial_question_suffix
        assistant_mode = "clarify" if intake.effective_mode == "clarify" else mode
        if session_id:
            sess.append_turn(
                session_id,
                ConversationTurn(
                    role="user",
                    # F10: lưu nguyên văn user gõ, không phải bản đã preprocess.
                    content=intake.raw_message,
                    mode=mode,
                    normalized_snapshot=persist_snapshot,
                    metadata=route_metadata,
                ),
            )
            sess.append_turn(
                session_id,
                ConversationTurn(
                    role="assistant",
                    content=full_assistant_text,
                    mode=assistant_mode,
                    used_chunks=used_chunks,
                ),
            )

        # -- 9. Evidence quality
        evidence_quality = compute_evidence_quality(retrieval)

        # -- 10. Audit log -----------------------------------------------------
        audit = getattr(c, "audit_store", None)
        if audit is not None:
            masked_clean_message = mask_pii(clean_message) if intake.pii_detected else clean_message
            masked_normalized_query = (
                mask_pii(intake.normalized_query) if intake.pii_detected else intake.normalized_query
            )
            audit.log(AuditEntry(
                user_message=masked_clean_message,
                assistant_response=full_assistant_text,
                used_chunk_ids=used_chunks,
                scope_decision=intake.scope_decision or "",
                latency_ms=int((time.perf_counter() - started) * 1000),
                model_used=getattr(c.llm, "model", ""),
                temperature=temperature,
                session_id=session_id,
                normalized_query=masked_normalized_query,
                extracted_entities=intake.extracted_entities,
                pii_detected=intake.pii_detected,
                teencode_replaced=intake.teencode_replaced,
            ))

        latency_ms = int((time.perf_counter() - started) * 1000)
        yield _event("done", {
            "mode": display_mode,
            "latency_ms": latency_ms,
            "used_chunks": used_chunks,
            "session_id": session_id,
            "evidence_quality": evidence_quality,
            "primary_intent": route_metadata.get("primary_intent"),
            "query_subject": route_metadata.get("query_subject"),
            "route_flags": route_metadata.get("route_flags", []),
        })

    except Exception as e:
        logger.exception("Streaming chat failed")
        yield _event("error", "Đã xảy ra lỗi, vui lòng thử lại.")
        yield _event("done", {
            "mode": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "used_chunks": [],
              "session_id": session_id,
        })
