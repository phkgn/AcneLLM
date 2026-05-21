"""Admin endpoints -- audit log, session stats, feedback stats."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["admin"], prefix="/api/v1/admin")


@router.get("/audit")
async def get_audit_log(
    request: Request,
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Tra ve audit log gan nhat."""
    c = request.app.state.container
    audit = getattr(c, "audit_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail="Audit store not available")
    entries = audit.query(session_id=session_id, limit=limit, offset=offset)
    total = audit.count(session_id=session_id)
    return {"total": total, "limit": limit, "offset": offset, "entries": entries}


@router.get("/sessions/stats")
async def session_stats(request: Request):
    """Thong ke so session dang active."""
    c = request.app.state.container
    sess = getattr(c, "session_store", None)
    if sess is None:
        raise HTTPException(status_code=503, detail="Session store not available")
    return {"active_sessions": sess.active_count()}


@router.get("/feedback/stats")
async def feedback_stats(request: Request):
    """Tong hop thumbs up/down: tong so, ti le hai long."""
    c = request.app.state.container
    audit = getattr(c, "audit_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail="Audit store not available")
    return audit.feedback_stats()


@router.get("/feedback")
async def list_feedback(
    request: Request,
    rating: str | None = Query(default=None, pattern="^(up|down)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Xem danh sach feedback gan nhat. Filter theo rating=up|down."""
    c = request.app.state.container
    audit = getattr(c, "audit_store", None)
    if audit is None:
        raise HTTPException(status_code=503, detail="Audit store not available")
    return {"entries": audit.recent_feedback(rating=rating, limit=limit, offset=offset)}
