"""Shared chunk-quality filters used by both pipeline/hybrid.py and chat/runtime.py.

Centralising here ensures both code paths apply identical noise-removal and
score-pruning logic without duplication.
"""
from __future__ import annotations

import re

from ..schemas import RetrievedChunk, RetrievalOutput

# ── Noisy-chunk markers ───────────────────────────────────────────────────────

_NOISY_MARKERS: tuple[str, ...] = (
    "view source",
    "template editor protected",
    "module:",
    "talk:",
    "/w/index.php?",
    "action=edit",
    "oldid=",
)

_QUERY_STOP_TERMS = {
    "mụn", "mun", "acne", "trứng", "trung", "cá", "ca", "da", "skin",
    "cho", "của", "cua", "tôi", "toi", "mình", "minh", "em", "nên", "nen",
    "dùng", "dung", "không", "khong", "được", "duoc", "với", "voi",
    "là", "la", "gì", "gi", "thì", "thi", "khi", "bị", "bi",
}

_CONCRETE_QUERY_MARKERS = (
    "kem chống nắng", "kem chong nang", "sunscreen", "spf",
    "isotretinoin", "tretinoin", "adapalene", "retinol",
    "benzoyl", "bpo", "aha", "bha", "salicylic",
    "mì cay", "mi cay", "đồ cay", "do cay", "sữa", "sua",
    "whey", "đường", "duong", "cà phê", "ca phe",
)


def _query_terms(query: str) -> set[str]:
    lowered = query.lower()
    raw_terms = re.findall(r"[\w%+]+", lowered, flags=re.UNICODE)
    return {
        term for term in raw_terms
        if len(term) >= 3 and term not in _QUERY_STOP_TERMS
    }


def is_noisy_chunk(chunk: RetrievedChunk) -> bool:
    """Return True when a chunk is likely a Wikipedia meta-page or edit artefact."""
    meta = chunk.metadata or {}
    title = str(meta.get("title", "")).lower()
    url = str(meta.get("url", "")).lower()
    source = str(meta.get("source", chunk.source or "")).lower()

    if any(m in title for m in _NOISY_MARKERS):
        return True
    if any(m in url for m in _NOISY_MARKERS):
        return True
    if "wikipedia" in source and ("talk:" in title or "view source" in title):
        return True
    return False


def drop_noisy_chunks(
    retrieval: RetrievalOutput | None,
    min_score: float = 0.0,
) -> RetrievalOutput | None:
    """Filter out noisy chunks and those below *min_score*.

    Returns the original object unchanged when nothing is filtered
    (avoids unnecessary allocation).  Returns None when *retrieval* is None.
    """
    if retrieval is None or not retrieval.chunks:
        return retrieval

    kept = [
        c for c in retrieval.chunks
        if (not is_noisy_chunk(c)) and float(c.score) >= min_score
    ]

    if len(kept) == len(retrieval.chunks):
        return retrieval

    if not kept:
        return RetrievalOutput(
            query=retrieval.query,
            chunks=[],
            retrieval_mode=retrieval.retrieval_mode,
            num_chunks=0,
            avg_score=0.0,
        )

    avg = sum(c.score for c in kept) / len(kept)
    return RetrievalOutput(
        query=retrieval.query,
        chunks=kept,
        retrieval_mode=retrieval.retrieval_mode,
        num_chunks=len(kept),
        avg_score=avg,
    )


def drop_query_mismatched_chunks(
    retrieval: RetrievalOutput | None,
    query: str,
    min_overlap: int = 1,
) -> RetrievalOutput | None:
    """Remove chunks whose text has zero keyword overlap with the query."""
    if retrieval is None:
        return None
    if not query.strip():
        return retrieval
    query_tokens = set(query.lower().split())
    kept = []
    for chunk in retrieval.chunks:
        chunk_tokens = set(chunk.text.lower().split())
        if chunk_tokens & query_tokens:
            kept.append(chunk)
    if len(kept) == len(retrieval.chunks):
        return retrieval
    avg = sum(c.score for c in kept) / len(kept) if kept else 0.0
    return RetrievalOutput(
        query=retrieval.query,
        chunks=kept,
        retrieval_mode=retrieval.retrieval_mode,
        num_chunks=len(kept),
        avg_score=avg,
    )
