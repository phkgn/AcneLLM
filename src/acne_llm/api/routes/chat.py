import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import require_admin
from ...chat.intake import MAX_MESSAGE_CHARS, MAX_MESSAGE_WORDS, _count_words
from ...chat.runtime import stream_chat_sse
from ...chat.orchestrator import prepare_chat_turn

router = APIRouter(tags=["chat"])


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


@router.get("/debug/trace", dependencies=[Depends(require_admin)])
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
    from ...chat._retrieval import source_data
    from ...chat.fallback.rule_extractor import extract_with_confidence

    t0 = time.perf_counter()

    # ① Preprocess
    prepared = prepare_user_text(message)

    # ②–⑤ Intake (normalize, guardrails, route, fold).
    prepared_turn = await asyncio.to_thread(
        prepare_chat_turn, c, message, mode, session_id,
        include_analytics=True,
    )
    intake = prepared_turn.intake
    user = intake.user
    route = intake.route_decision
    route_metadata = route.metadata() if route else {}

    # Confidence per-field -> hedge trong prompt (confidence_hint)
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
            "confidence": route_metadata.get("intent_confidence"),
            "route_flags": route_metadata.get("route_flags", []),
            "reason_code": getattr(route, "reason_code", None),
        },
        "effective_mode": intake.effective_mode,
    }

    # Nếu reject/clarify → dừng, trả thẳng (giống runtime không retrieve/không prompt)
    _intent = route_metadata.get("primary_intent")
    if intake.scope_refusal is not None or intake.effective_mode in ("refuse", "clarify"):
        trace["stage_7_retrieve"] = {"ran": False, "reason": f"effective_mode={intake.effective_mode}"}
        trace["stage_8_prompt"] = {
            "built": False,
            "reason": "reject/clarify → trả lời cố định, không build prompt tư vấn",
            "fixed_reply": (intake.scope_refusal.disclaimer
                            if intake.scope_refusal else ""),
        }
        trace["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return trace

    # ⑦ Retrieve (chỉ khi hybrid + acne signal, GIỐNG runtime)
    retrieval = prepared_turn.retrieval
    trace["stage_7_retrieve"] = {
        "ran": retrieval is not None,
        "query": prepared_turn.retrieval_query,
        "selected_context": [
            {"role": turn.role, "content": turn.content} for turn in intake.history
        ],
        "confirmed_profile": intake.confirmed_profile,
        "num_chunks": len(retrieval.chunks) if retrieval else 0,
        "chunks": [source_data(ch) for ch in (retrieval.chunks if retrieval else [])],
    }

    # ⑧ Build prompt — TÁI DÙNG c.prompt.build y như runtime
    _template = prepared_turn.template
    try:
        system, user_message = prepared_turn.system_prompt, prepared_turn.user_prompt
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


# ponytail: endpoint /ws/chat va _parse_sse_frame da bi xoa. Frontend chi
# dung SSE (frontend/src/lib/api.ts), khong client nao mo WebSocket. Doan cu
# la cau noi asyncio.Queue giua sync generator va async sender -- doan phuc
# tap nhat file nay, phuc vu zero request. Xem git history neu can khoi phuc.


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
