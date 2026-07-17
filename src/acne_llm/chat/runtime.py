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
import re
from typing import TYPE_CHECKING

from loguru import logger

from .session import ConversationTurn, get_session_store
from ._retrieval import citation_data, compute_evidence_quality
from .inline_citations import InlineCitationStripper
from .orchestrator import prepare_chat_turn
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
        prepared = prepare_chat_turn(
            c,
            message,
            requested_mode=requested_mode,
            session_id=session_id,
        )
        intake = prepared.intake
        clean_message = intake.clean_text
        history = intake.history
        user = intake.user
        mode = prepared.mode
        display_mode = "clarify" if intake.effective_mode == "clarify" else mode
        route_metadata = prepared.route_metadata
        persist_snapshot = _snapshot_for_persistence(intake)
        _primary_intent = (
            intake.route_decision.primary_intent if intake.route_decision else "advise"
        )
        # Dung container session store (JSONL in production; in-memory fallback for tests).
        sess = getattr(c, "session_store", None) or get_session_store()

        if prepared.fixed_reply:
            if session_id:
                sess.append_turn(session_id, ConversationTurn(
                    role="user",
                    content=intake.raw_message,
                    mode="llm_only",
                    metadata=route_metadata,
                ))
                sess.append_turn(session_id, ConversationTurn(
                    role="assistant",
                    content=prepared.fixed_reply,
                    mode="llm_only",
                ))
            yield _event("token", prepared.fixed_reply)
            yield _event("done", {
                "mode": "llm_only",
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "used_chunks": [],
                "session_id": session_id,
                "primary_intent": route_metadata.get("primary_intent"),
                "query_subject": route_metadata.get("query_subject"),
                "route_flags": route_metadata.get("route_flags", []),
            })
            return

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

        # Retrieval and prompt are prepared once by the shared orchestrator.
        retrieval = prepared.retrieval
        if retrieval is not None:
            logger.debug(
                "[{}] RAG: {} chunks in {:.0f}ms (scope={} plan={})",
                (session_id or "")[:8],
                len(retrieval.chunks),
                prepared.retrieval_ms,
                intake.scope_decision,
                False,
            )
        else:
            logger.debug(
                "[{}] RAG: skipped (mode={} signal={} plan={})",
                (session_id or "")[:8],
                mode,
                intake.is_acne_signal or bool(intake.safety_terms),
                False,
            )

        system, user_message = prepared.system_prompt, prepared.user_prompt

        # -- 5. LLM stream ----------------------------------------------------
        # Keep factual generation at the configured low temperature. Raising
        # knowledge temperature increased invented sources and unsupported claims.
        _default_temp = getattr(c.settings, "llm_temperature", 0.3)
        effective_temperature = (
            temperature
            if temperature is not None
            else _default_temp
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

        inline_citation_mode = str(getattr(c.settings, "inline_citation", "off"))
        if inline_citation_mode not in {"off", "model"}:
            logger.warning(
                "[%s] Invalid inline_citation=%r; falling back to off",
                (session_id or "")[:8],
                inline_citation_mode,
            )
            inline_citation_mode = "off"
        citation_stripper = (
            InlineCitationStripper() if inline_citation_mode == "off" else None
        )

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
                emitted = citation_stripper.feed(token) if citation_stripper else token
                if emitted:
                    tokens.append(emitted)
                    yield _event("token", emitted)

        if citation_stripper:
            tail = citation_stripper.finish()
            if tail:
                tokens.append(tail)
                yield _event("token", tail)

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

        # -- 5b. Citation output gate -----------------------------------------
        citation_repair = ""
        _require_citations = inline_citation_mode == "model"
        if _require_citations and retrieval is not None and retrieval.chunks and not re.search(r"\[\d+\]", full_text):
            citation_repair = " [1]"
            full_text += citation_repair
            yield _event("token", citation_repair)
            logger.warning(
                "[{}] Citation marker repaired deterministically with [1]",
                (session_id or "")[:8],
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
        citation_compliance = (
            bool(re.search(r"\[\d+\]", full_text))
            if used_chunks and _require_citations else None
        )
        if citation_compliance is False:
            logger.warning(
                "[{}] Citation compliance failed: retrieval used but no inline [N] marker",
                (session_id or "")[:8],
            )
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
                citation_compliance=citation_compliance,
            ))

        latency_ms = int((time.perf_counter() - started) * 1000)
        yield _event("done", {
            "mode": display_mode,
            "latency_ms": latency_ms,
            "used_chunks": used_chunks,
            "session_id": session_id,
            "evidence_quality": evidence_quality,
            "citation_compliance": citation_compliance,
            "primary_intent": route_metadata.get("primary_intent"),
            "query_subject": route_metadata.get("query_subject"),
            "route_flags": route_metadata.get("route_flags", []),
        })

    except Exception:
        logger.exception("Streaming chat failed")
        yield _event("error", "Đã xảy ra lỗi, vui lòng thử lại.")
        yield _event("done", {
            "mode": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "used_chunks": [],
              "session_id": session_id,
        })
