import asyncio
import json
import time

from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from ...schemas import UserInput, AdviseOutput
from ...chat.intake import MAX_MESSAGE_CHARS, MAX_MESSAGE_WORDS, _count_words, run_intake
from ...chat.runtime import stream_chat_sse
from ...chat.session import ConversationTurn, get_session_store
from ...db.audit import AuditEntry
from ..deps import get_pipeline_for

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=AdviseOutput)
async def chat(request: Request, payload: dict = Body(...)):
    if "message" in payload:
        return await _chat_new_body(payload, request)

    inp = UserInput.model_validate(payload)
    if inp.mode not in {"llm_only", "hybrid"}:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline '{inp.mode}' is not supported.",
        )
    try:
        pipeline = get_pipeline_for(inp.mode, request)
        return await asyncio.to_thread(pipeline.run, inp)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("pipeline error")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


async def _chat_new_body(payload: dict, request: Request) -> AdviseOutput:
    message = str(payload.get("message", ""))
    if not message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"message must be <= {MAX_MESSAGE_CHARS} characters")
    if _count_words(message) > MAX_MESSAGE_WORDS:
        raise HTTPException(
            status_code=413,
            detail=f"Tin nhắn quá dài. Vui lòng rút gọn xuống tối đa {MAX_MESSAGE_WORDS} từ.",
        )

    c = request.app.state.container
    session_id = payload.get("session_id")
    mode_request = str(payload.get("mode", "auto"))
    started = time.perf_counter()
    try:
        intake = run_intake(c, message, session_id=session_id, mode_request=mode_request)
        store = getattr(c, "session_store", None) or get_session_store()
        route_metadata = intake.route_decision.metadata() if intake.route_decision else {}

        if intake.scope_refusal is not None:
            out = intake.scope_refusal
            out.model_name = getattr(c.llm, "model", "")
            out.latency_ms = int((time.perf_counter() - started) * 1000)
            # Bug #5 fix: increment guardrail trigger metric
            metrics = getattr(request.app.state, "metrics", None)
            if metrics is not None:
                metrics.guardrail_trigger_count += 1
            if session_id:
                store.append_turn(
                    session_id,
                    ConversationTurn(
                        role="user",
                        # F10b: lưu nguyên văn user gõ, không phải bản đã preprocess.
                        content=intake.raw_message,
                        mode=out.mode,
                        normalized_snapshot=intake.turn_snapshot,
                        metadata=route_metadata,
                    ),
                )
                store.append_turn(
                    session_id,
                    ConversationTurn(role="assistant", content=out.disclaimer, mode=out.mode),
                )
            return out

        if intake.effective_mode == "clarify":
            question = intake.completeness.followup_question if intake.completeness else ""
            out = AdviseOutput(
                severity="unknown",
                acne_type_primary="unknown",
                causes=[question or "Cần thêm thông tin trước khi tư vấn"],
                recommendations=[],
                red_flags=[],
                used_chunks=[],
                confidence=0.0,
                mode="llm_only",
                model_name=getattr(c.llm, "model", ""),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            if session_id:
                store.append_turn(
                    session_id,
                    ConversationTurn(
                        role="user",
                        # F10b: lưu nguyên văn user gõ, không phải bản đã preprocess.
                        content=intake.raw_message,
                        mode="llm_only",
                        normalized_snapshot=intake.turn_snapshot,
                        metadata=route_metadata,
                    ),
                )
                store.append_turn(
                    session_id,
                    ConversationTurn(role="assistant", content=question, mode="clarify"),
                )
            return out

        mode = "hybrid" if intake.effective_mode == "hybrid" else "llm_only"
        pipeline = get_pipeline_for(mode, request)
        out = await asyncio.to_thread(
            pipeline.run,
            intake.user,
            intake.clinical_plan,
            True,
            intake.history,
            route_metadata,
            safety_terms=intake.safety_terms,
        )
        if session_id:
            store.append_turn(
                session_id,
                ConversationTurn(
                    role="user",
                    # F10b: lưu nguyên văn user gõ, không phải bản đã preprocess.
                    content=intake.raw_message,
                    mode=mode,
                    normalized_snapshot=intake.turn_snapshot,
                    metadata=route_metadata,
                ),
            )
            store.append_turn(
                session_id,
                ConversationTurn(
                    role="assistant",
                    content="; ".join(out.causes + [r.action for r in out.recommendations]),
                    mode=mode,
                    used_chunks=out.used_chunks,
                ),
            )
        audit = getattr(c, "audit_store", None)
        if audit is not None:
            audit.log(AuditEntry(
                user_message=intake.clean_text,
                assistant_response="; ".join(
                    out.causes + [r.action for r in out.recommendations]
                ),
                used_chunk_ids=out.used_chunks,
                scope_decision=intake.scope_decision or "",
                latency_ms=int((time.perf_counter() - started) * 1000),
                model_used=getattr(c.llm, "model", ""),
                session_id=session_id,
            ))
        return out
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chat intake/pipeline error")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


@router.get("/chat/stream")
async def chat_stream(
    request: Request,
    message: str,
    session_id: str | None = None,
    mode: str = "auto",
    temperature: float | None = Query(default=None, ge=0.0, le=1.0),
):
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"message must be <= {MAX_MESSAGE_CHARS} characters")
    if _count_words(message) > MAX_MESSAGE_WORDS:
        raise HTTPException(
            status_code=413,
            detail=f"Tin nhắn quá dài. Vui lòng rút gọn xuống tối đa {MAX_MESSAGE_WORDS} từ.",
        )

    c = request.app.state.container
    return StreamingResponse(
        stream_chat_sse(
            c,
            message=message,
            requested_mode=mode,
            session_id=session_id,
            temperature=temperature,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/debug/trace")
async def debug_trace(
    request: Request,
    message: str,
    session_id: str | None = None,
    mode: str = "auto",
):
    """Trace ĐẦY ĐỦ từng stage của pipeline cho pipeline_simulator.html.

    Tái dùng CHÍNH các lời gọi mà runtime/stream dùng (run_intake →
    extract_with_confidence → retrieve_for_chat → c.prompt.build) nên kết quả
    GIỐNG Y CHANG production, không phải mô phỏng lại. Read-only: KHÔNG ghi
    session, KHÔNG gọi LLM (dừng ngay trước bước stream).
    """
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"message must be <= {MAX_MESSAGE_CHARS} chars")

    c = request.app.state.container
    from ...chat.preprocess import prepare_user_text
    from ...chat.extraction_confidence import extract_with_confidence
    from ...chat._retrieval import retrieve_for_chat, citation_data

    t0 = time.perf_counter()

    # ① Preprocess
    prepared = prepare_user_text(message)

    # ②–⑥ Intake (normalize, guardrails, route, fold, completeness, plan)
    intake = run_intake(c, message, session_id=session_id, mode_request=mode)
    user = intake.user
    route = intake.route_decision
    route_metadata = route.metadata() if route else {}

    # Confidence per-field (kênh phụ — chính cái dùng ở completeness)
    ec = extract_with_confidence(
        message,
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )

    def _fr(fr) -> dict | None:
        if fr is None:
            return None
        if hasattr(fr, "items"):  # ListFieldResult
            return {
                "values": fr.values,
                "items": [
                    {"value": it.value, "confidence": round(it.confidence, 3), "method": it.method}
                    for it in fr.items
                ],
            }
        return {"value": fr.value, "confidence": round(fr.confidence, 3), "method": fr.method}

    confidence_block = {
        name: _fr(getattr(ec, name))
        for name in (
            "skin_type", "sex", "age", "duration_weeks", "inflammation",
            "lesion_types", "distribution", "products", "medications", "red_flags",
        )
    }

    cl = user.clinical
    trace: dict = {
        "input": {"raw": message, "chars": len(message)},
        "stage_1_preprocess": {
            "clean_text": prepared.clean_text,
            "clean_text_no_accent": prepared.clean_text_no_accent,
            "teencode_replaced": prepared.teencode_replaced,
        },
        "stage_2_normalize": {
            "age": user.context.age,
            "sex": user.context.sex,
            "skin_type": user.context.skin_type,
            "is_pregnant": user.context.is_pregnant,
            "is_breastfeeding": user.context.is_breastfeeding,
            "current_products": user.context.current_products,
            "medications": user.context.medications,
            "duration_weeks": user.context.duration_weeks,
            "lesion_types": (cl.lesion_types if cl else []),
            "lesion_distribution": (cl.lesion_distribution if cl else []),
            "inflammation_level": (cl.inflammation_level if cl else None),
            "red_flags_input": (cl.red_flags_input if cl else []),
            "hormonal_factors": (cl.hormonal_factors if cl else []),
            "treatment_goals": (cl.treatment_goals if cl else []),
        },
        "stage_2b_confidence": confidence_block,
        "stage_3_guardrails": {
            "scope_decision": intake.scope_decision,
            "pii_detected": intake.pii_detected,
            "safety_terms": intake.safety_terms,
            "refused": intake.scope_refusal is not None,
        },
        "stage_4_route": {
            "primary_intent": route_metadata.get("primary_intent"),
            "query_subject": route_metadata.get("query_subject"),
            "confidence": route_metadata.get("intent_confidence"),
            "route_flags": route_metadata.get("route_flags", []),
            "reason_code": getattr(route, "reason_code", None),
        },
        "stage_5_completeness": (
            {
                "kind": intake.completeness.kind,
                "level": intake.completeness.level,
                "missing_fields": intake.completeness.missing_fields,
                "question": intake.completeness.followup_question,
                "checked": True,
            }
            if intake.completeness is not None
            else {"checked": False, "reason": "skipped (knowledge/clarify/reject hoặc không acne-scope)"}
        ),
        "stage_6_clinical_plan": (
            {
                "built": True,
                "query_vi": getattr(getattr(intake.clinical_plan, "rag_queries", None), "query_vi", None),
                "detected_language": getattr(intake.clinical_plan, "detected_language", None),
            }
            if intake.clinical_plan is not None
            else {"built": False}
        ),
        "effective_mode": intake.effective_mode,
    }

    # Nếu reject/clarify → dừng, trả thẳng (giống runtime không retrieve/không prompt)
    _intent = route_metadata.get("primary_intent")
    if intake.scope_refusal is not None or intake.effective_mode in ("refuse", "clarify"):
        trace["stage_7_retrieve"] = {"ran": False, "reason": f"effective_mode={intake.effective_mode}"}
        trace["stage_8_prompt"] = {
            "built": False,
            "reason": "reject/clarify → trả lời cố định, không build prompt tư vấn",
            "fixed_reply": (intake.scope_refusal.disclaimer if intake.scope_refusal
                            else (intake.completeness.followup_question if intake.completeness else "")),
        }
        trace["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return trace

    # ⑦ Retrieve (chỉ khi hybrid + acne signal, GIỐNG runtime)
    clinical_plan = intake.clinical_plan
    rag_signal = intake.is_acne_signal or clinical_plan is not None or bool(intake.safety_terms)
    retrieval = None
    if intake.effective_mode == "hybrid" and rag_signal and _intent not in {"clarify", "reject"}:
        retrieval = await asyncio.to_thread(
            retrieve_for_chat,
            c, user, clinical_plan,
            route_flags=(route.route_flags if route else []),
            normalized_query=intake.normalized_query,
            safety_terms=intake.safety_terms,
        )
    trace["stage_7_retrieve"] = {
        "ran": retrieval is not None,
        "num_chunks": len(retrieval.chunks) if retrieval else 0,
        "chunks": [citation_data(ch) for ch in (retrieval.chunks if retrieval else [])],
    }

    # ⑧ Build prompt — TÁI DÙNG c.prompt.build y như runtime
    if _intent == "clarify":
        _template = "clarify_user.j2"
    elif _intent == "knowledge":
        _template = "knowledge_user.j2"
    else:
        _template = "stream_user.j2"
    try:
        system, user_message = c.prompt.build(
            user=user,
            retrieval=retrieval,
            template=_template,
            detected_language=(clinical_plan.detected_language if clinical_plan else "unknown"),
            query_vi=(clinical_plan.rag_queries.query_vi if clinical_plan else intake.normalized_query),
            max_context_chars=getattr(c.settings, "chat_max_context_chars", 4500),
            clinical_plan=clinical_plan,
            history=intake.history,
            route_metadata=route_metadata,
            system_override=c.prompt.system_stream(),
            completeness_hint=None,
        )
        trace["stage_8_prompt"] = {
            "built": True,
            "template": _template,
            "system": system,
            "user_message": user_message,
            "total_chars": len(system) + len(user_message),
            "approx_tokens": (len(system) + len(user_message)) // 3.5,
        }
    except Exception as e:
        trace["stage_8_prompt"] = {"built": False, "error": str(e), "template": _template}

    trace["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return trace


def _parse_sse_frame(frame: str) -> dict | None:
    """Parse SSE frame string thanh dict. Tra None neu khong hop le."""
    line = next(
        (item for item in frame.splitlines() if item.startswith("data: ")),
        "",
    )
    if not line:
        return None
    try:
        return json.loads(line[6:])
    except json.JSONDecodeError:
        return None


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    c = websocket.app.state.container
    loop = asyncio.get_event_loop()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                message = str(payload.get("message", ""))
                mode = str(payload.get("mode", "auto"))
                session_id = payload.get("session_id")
            except json.JSONDecodeError:
                message = raw
                mode = "auto"
                session_id = None

            if not message.strip():
                await websocket.send_json({"event": "error", "data": "message is required"})
                continue
            if len(message) > MAX_MESSAGE_CHARS:
                await websocket.send_json({
                    "event": "error",
                    "data": f"message must be <= {MAX_MESSAGE_CHARS} characters",
                })
                continue
            if _count_words(message) > MAX_MESSAGE_WORDS:
                await websocket.send_json({
                    "event": "error",
                    "data": f"Tin nhắn quá dài. Vui lòng rút gọn xuống tối đa {MAX_MESSAGE_WORDS} từ.",
                })
                continue

            # FIX: Stream tung frame ngay khi LLM generate — khong buffer toan bo.
            # Truoc day: list(stream_chat_sse(...)) buffer het truoc khi gui → user
            # thay man hinh trang trong suot thoi gian LLM chay.
            # Sau fix: dung asyncio.Queue lam bridge giua sync generator (thread)
            # va async WebSocket sender — token xuat hien tren UI ngay khi co.
            _SENTINEL = object()
            queue: asyncio.Queue = asyncio.Queue(maxsize=64)

            def _producer():
                """Chay trong thread rieng; push tung SSE frame vao queue."""
                def _put(item) -> None:
                    asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()

                try:
                    for frame in stream_chat_sse(
                        c,
                        message=message,
                        requested_mode=mode,
                        session_id=session_id,
                    ):
                        _put(frame)
                except Exception as exc:
                    logger.exception("WS stream producer error")
                    _err = json.dumps({"event": "error", "data": str(exc)})
                    _put(f"data: {_err}\n\n")
                finally:
                    _put(_SENTINEL)

            producer_future = loop.run_in_executor(None, _producer)

            # Consume: gui moi frame ngay khi nhan duoc tu queue
            while True:
                frame = await queue.get()
                if frame is _SENTINEL:
                    break
                parsed = _parse_sse_frame(frame)
                if parsed is not None:
                    await websocket.send_json(parsed)

            # Dam bao thread producer da ket thuc
            await producer_future

    except WebSocketDisconnect:
        return


# ── Feedback endpoint ─────────────────────────────────────────────────────────

class FeedbackPayload(BaseModel):
    message_id: str
    rating: str            # "up" | "down"
    session_id: str | None = None
    audit_id: int | None = None
    comment: str = ""


@router.post("/chat/feedback", status_code=201)
async def submit_feedback(request: Request, payload: FeedbackPayload):
    """Nhan thumbs up/down tu frontend, luu vao bang feedback."""
    if payload.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating phai la up hoac down")
    c = request.app.state.container
    audit = getattr(c, "audit_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail="Audit store không khả dụng")
    rowid = audit.log_feedback(
        message_id=payload.message_id,
        rating=payload.rating,
        session_id=payload.session_id,
        audit_id=payload.audit_id,
        comment=payload.comment,
    )
    return {"ok": True, "feedback_id": rowid}
