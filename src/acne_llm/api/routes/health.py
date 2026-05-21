import asyncio

from fastapi import APIRouter, Depends
from ..deps import get_container

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(c=Depends(get_container)):
    ollama_ok = await asyncio.to_thread(c.llm.health)
    try:
        kb_count = await asyncio.to_thread(c.store.count) if c.store is not None else -1
    except Exception:
        kb_count = -1
    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama": ollama_ok,
        "model": c.llm.model,
        "kb_chunks": kb_count,
        "bm25_loaded": c.bm25 is not None,
    }


@router.get("/models")
async def models(c=Depends(get_container)):
    models = await asyncio.to_thread(c.llm.list_models)
    return {"models": models, "current": c.llm.model}
