"""Knowledge-base retrieval endpoints."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..deps import get_container

router = APIRouter(tags=["kb"])


def _require_rag(c):
    if not c.rag_ready:
        raise HTTPException(
            status_code=503,
            detail="RAG not ready. Run: python scripts/build_kb.py --step embed",
        )


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 10
    mode: str = "hybrid"


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/kb/retrieve")
async def retrieve(body: RetrieveRequest, request: Request):
    c = get_container(request)
    _require_rag(c)
    retrieval = await asyncio.to_thread(
        c.retriever.retrieve, body.query, body.top_k, body.mode
    )
    top = retrieval
    if c.reranker is not None:
        top = await asyncio.to_thread(
            c.reranker.rerank, body.query, retrieval, body.top_k
        )
    return {
        "query": body.query,
        "mode": body.mode,
        "chunks": [
            {
                "chunk_id": ch.chunk_id,
                "source": ch.source,
                "text": ch.text,
                "score": ch.score,
            }
            for ch in top.chunks
        ],
    }


@router.get("/kb/stats")
async def kb_stats(request: Request):
    c = get_container(request)
    try:
        total_chunks = c.store.count() if c.store is not None else -1
    except Exception:
        total_chunks = -1
    return {
        "rag_ready": c.rag_ready,
        "total_chunks": total_chunks,
        "bm25_loaded": c.bm25 is not None,
        "embedder_model": getattr(c.embedder, "model_name", None),
        "reranker_model": getattr(c.reranker, "model_name", None),
    }


@router.get("/kb/chunk/{chunk_id}")
async def get_chunk(chunk_id: str, request: Request):
    c = get_container(request)
    _require_rag(c)
    got = c.store.get_by_id(chunk_id)
    docs = got.get("documents") or []
    metas = got.get("metadatas") or []
    if not docs:
        raise HTTPException(status_code=404, detail=f"Chunk '{chunk_id}' not found")
    return {
        "chunk_id": chunk_id,
        "text": docs[0],
        "metadata": metas[0] if metas else {},
    }


@router.post("/kb/search")
async def kb_search(body: SearchRequest, request: Request):
    c = get_container(request)
    _require_rag(c)
    retrieval = await asyncio.to_thread(
        c.retriever.retrieve, body.query, body.top_k * 2, "hybrid"
    )
    top = retrieval
    if c.reranker is not None:
        top = await asyncio.to_thread(
            c.reranker.rerank, body.query, retrieval, body.top_k
        )
    return {
        "query": body.query,
        "results": [
            {
                "chunk_id": ch.chunk_id,
                "source": ch.source,
                "text": ch.text[:300] + ("…" if len(ch.text) > 300 else ""),
                "score": ch.score,
            }
            for ch in top.chunks
        ],
    }
