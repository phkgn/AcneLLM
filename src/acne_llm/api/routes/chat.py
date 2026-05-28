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
