"""Streaming chat runtime -- orchestrator chinh cho /chat/stream va /ws/chat.

Flow:
    message -> intake (guardrails + route) -> retrieve -> build_prompt
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
from ._retrieval import compute_evidence_quality, source_data
from .orchestrator import prepare_chat_turn
from ._safety import get_safety_suffix
from ..db.audit import AuditEntry
from ..guardrails.pii import mask_pii
from ..utils.logging import log_pipeline_stage

if TYPE_CHECKING:
    from ..di import Container
    from .intake import IntakeResult


# -- SSE helper ---------------------------------------------------------------

def _event(event: str, data) -> str:
    payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _snapshot_for_persistence(intake: "IntakeResult"):
    route = intake.route_decision
    if route is None or route.primary_intent != "advise":
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
    sid_short = (session_id or "no-session")[:8]
    prepared = None  # except doc lai de tra ban cung cua refusal khi generator chet
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
        sess = c.session_store

        # M5: Progress/follow-up intent — annotate route_metadata so prompt builder
        # and session store know this is a treatment check-in turn.
        _rflags = intake.route_decision.route_flags if intake.route_decision else []
        if "progress_followup" in _rflags:
            route_metadata["is_progress_followup"] = True
            # Increment follow-up counter in session for future turns context
            if session_id and hasattr(sess, "increment_followup_count"):
                sess.increment_followup_count(session_id, 1.0)

        # Refusal không còn short-circuit: guardrail quyết nội dung, generator
        # viết câu chữ, get_safety_suffix nối lại bản cứng ở cuối.
        if intake.scope_refusal is not None:
            _gr = getattr(c, "guardrails", None)
            if _gr is not None:
                _gr.trigger_count = getattr(_gr, "trigger_count", 0) + 1
            log_pipeline_stage(
                session_id,
                "SAFETY",
                started,
                level="WARNING",
                result="refusal_to_generator",
                reason=(intake.scope_refusal.causes or ["refusal"])[0],
            )

        # Retrieval and prompt are prepared once by the shared orchestrator.
        retrieval = prepared.retrieval

        system, user_message = prepared.system_prompt, prepared.user_prompt

        # -- 5. LLM stream ----------------------------------------------------
        # Keep factual generation at the configured low temperature. Raising
        # knowledge temperature increased invented sources and unsupported claims.
        _default_temp = getattr(c.settings, "llm_temperature", 0.35)
        effective_temperature = (
            temperature
            if temperature is not None
            else _default_temp
        )
        prompt_chars = len(system) + len(user_message)
        generation_started = time.perf_counter()
        log_pipeline_stage(
            session_id,
            "GENERATE",
            generation_started,
            level="DEBUG",
            status="prompt_ready",
            prompt_chars=prompt_chars,
            approx_tokens=int(prompt_chars / 3.5),
            temperature=effective_temperature,
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
            log_pipeline_stage(
                session_id,
                "GENERATE",
                generation_started,
                level="DEBUG",
                status="empathy_prefix",
            )

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
                log_pipeline_stage(
                    session_id,
                    "GENERATE",
                    generation_started,
                    level="DEBUG",
                    status="first_token",
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
            log_pipeline_stage(
                session_id,
                "OUTPUT",
                generation_started,
                level="WARNING",
                guard="cjk_strip",
                stripped_chars=_cjk_total,
            )

        full_text = pre_prefix + "".join(tokens)
        log_pipeline_stage(
            session_id,
            "GENERATE",
            generation_started,
            status="done",
            chunks=len(tokens),
            chars=len(full_text),
        )

        used_chunks = [c.chunk_id for c in retrieval.chunks] if retrieval else []
        if retrieval:
            for chunk in retrieval.chunks:
                yield _event("source", source_data(chunk))

        # -- 6. Safety suffix -------------------------------------------------
        # Tang hau kiem tren text la tang hau kiem DUY NHAT. Ban cu dua tren
        # AdviseOutput (guardrails.post_check) da bi xoa o Phase 3 vi prose
        # streaming khong co object nao de dua vao; luat dang giu duy nhat tu do
        # -- lieu luong cu the -- da duoc port vao get_safety_suffix.
        route_flags = intake.route_decision.route_flags if intake.route_decision else []
        is_knowledge_intent = (
            intake.route_decision is not None
            and intake.route_decision.primary_intent == "knowledge"
        )
        safety_route_flags = route_flags
        if is_knowledge_intent and "urgent_personal_case" not in route_flags:
            safety_route_flags = [f for f in route_flags if f != "urgency_red_flag"]
        warning_suffix = (
            ""
            if _primary_intent == "reject"
            else get_safety_suffix(
                full_text,
                user,
                route_flags=safety_route_flags,
                skip_generic_disclaimer=is_knowledge_intent,
                recent_turns=history,
                current_turn_text=message,
            )
        )

        if warning_suffix:
            yield _event("token", warning_suffix)

        # ponytail: bo doan noi cau hoi bo sung. Generator thay lich su va thay
        # du kien trong nen tu quyet dinh hoi hay khong -- va no van hoi bat ke
        # prompt bao dung, nen noi them chi tao cau hoi THU HAI. Viec chan hoi
        # lap cung khong can `asked_fields` nua: model doc duoc luot truoc no da
        # hoi gi. Xem git history neu can khoi phuc.

        # -- 8. Persist session -----------------------------------------------
        full_assistant_text = full_text + (warning_suffix or "")
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
        output_started = time.perf_counter()
        log_pipeline_stage(
            session_id,
            "OUTPUT",
            output_started,
            status="done",
            mode=display_mode,
            chars=len(full_assistant_text),
            used_chunks=len(used_chunks),
            total_ms=latency_ms,
        )
        yield _event("done", {
            "mode": display_mode,
            "latency_ms": latency_ms,
            "used_chunks": used_chunks,
            "session_id": session_id,
            "evidence_quality": evidence_quality,
            "primary_intent": route_metadata.get("primary_intent"),
            "route_flags": route_metadata.get("route_flags", []),
        })

    except Exception:
        logger.exception(
            "[{}] {:<10} status=error ({:.0f}ms)",
            sid_short,
            "OUTPUT",
            (time.perf_counter() - started) * 1000,
        )
        # Refusal di qua generator de model viet cau chu (xem orchestrator).
        # Nghia la khi generator chet, canh bao an toan bien mat hoan toan --
        # dung cai luot ma ta KHONG duoc phu thuoc LLM. Ban cung cua guardrail
        # van con trong scope_refusal.disclaimer, tra thang no.
        _refusal = getattr(getattr(prepared, "intake", None), "scope_refusal", None)
        if _refusal is not None and getattr(_refusal, "disclaimer", ""):
            yield _event("token", _refusal.disclaimer)
        else:
            yield _event("error", "Đã xảy ra lỗi, vui lòng thử lại.")
        yield _event("done", {
            "mode": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "used_chunks": [],
              "session_id": session_id,
        })
