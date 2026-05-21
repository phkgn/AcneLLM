import asyncio

import json

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from loguru import logger

from ...schemas import UserInput, AdviseOutput
from ...chat.runtime import stream_chat_sse
from ..deps import get_pipeline_for

router = APIRouter(tags=["chat"])

@router.post("/chat", response_model=AdviseOutput)
async def chat(inp: UserInput, request: Request):
    if inp.mode not in {"llm_only", "hybrid"}:
        raise HTTPException(
            status_code=400,
            detail=f"Pipeline '{inp.mode}' is not supported.",
        )
    try:
        pipeline = get_pipeline_for(inp.mode, request)
        # pipeline.run() calls synchronous httpx — offload to thread to avoid blocking event loop
        return await asyncio.to_thread(pipeline.run, inp)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("pipeline error")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")


@router.get("/chat/stream")
async def chat_stream(
    request: Request,
    message: str,
    session_id: str | None = None,
    mode: str = "auto",
):
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    c = request.app.state.container
    return StreamingResponse(
        stream_chat_sse(c, message=message, requested_mode=mode, session_id=session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    c = websocket.app.state.container
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

            for frame in stream_chat_sse(
                c,
                message=message,
                requested_mode=mode,
                session_id=session_id,
            ):
                line = next(
                    (item for item in frame.splitlines() if item.startswith("data: ")),
                    "",
                )
                if not line:
                    continue
                await websocket.send_json(json.loads(line[6:]))
    except WebSocketDisconnect:
        return
