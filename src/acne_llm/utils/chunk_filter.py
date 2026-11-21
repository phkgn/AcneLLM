"""Shared chunk-quality filters used by chat/_retrieval.py and evaluation adapters.

Centralising here ensures both code paths apply identical noise-removal and
score-pruning logic without duplication.
"""
from __future__ import annotations

from ..schemas import RetrievedChunk, RetrievalOutput
from ..rag.sparse import tokenize_vi

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
    "cho", "của", "cua", "tôi", "toi", "mình", "minh", "em", "nên", "nen",
    "dùng", "dung", "không", "khong", "được", "duoc", "với", "voi",
    "là", "la", "gì", "gi", "thì", "thi", "khi", "bị", "bi",
    "top", "các", "cac", "những", "nhung",
}

_CONCRETE_QUERY_MARKERS = (
    "kem chống nắng", "kem chong nang", "sunscreen", "spf",
    "isotretinoin", "tretinoin", "adapalene", "retinol",
    "benzoyl", "bpo", "aha", "bha", "salicylic",
    "mì cay", "mi cay", "đồ cay", "do cay", "sữa", "sua",
    "whey", "đường", "duong", "cà phê", "ca phe",
)


def _query_terms(query: str) -> set[str]:
    raw_terms = tokenize_vi(query, remove_stopwords=True)
    return {
        term.lower() for term in raw_terms
        if len(term) >= 3 and term not in _QUERY_STOP_TERMS
    }


def _has_concrete_query_marker(query: str) -> bool:
    lowered = query.lower()
    return any(marker in lowered for marker in _CONCRETE_QUERY_MARKERS)


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
    min_overlap: int = 2,
) -> RetrievalOutput | None:
    """Remove chunks whose text has zero keyword overlap with the query."""
    if retrieval is None:
        return None
    if not query.strip():
        return retrieval
    if not _has_concrete_query_marker(query):
        return retrieval
    query_tokens = _query_terms(query)
    if len(query_tokens) < min_overlap:
        return retrieval
    kept = []
    for chunk in retrieval.chunks:
        chunk_tokens = {
            token.lower()
            for token in tokenize_vi(chunk.text, remove_stopwords=True)
            if len(token) >= 3 and token.lower() not in _QUERY_STOP_TERMS
        }
        if len(chunk_tokens & query_tokens) >= min_overlap:
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


# ponytail: _FACE_REGION_TERMS / _NON_FACE_REGION_TERMS +
# drop_body_region_mismatched_chunks da bi xoa o Phase 7.
#
# No vut chunk noi "lung"/"nguc" khi query co "mat" -- nhung phac do mun
# lung va mun mat trung nhau phan lon, nen bang chung bi mat im lang, khong
# log, model khong biet minh vua bi lay di cai gi. Comment ngay tren call site
# o _retrieval.py da tu noi: "KHONG dung keyword mismatch filter vi
# cross-encoder da score relevance roi -- mismatch filter se drop nham".
#
# drop_acne_boils_mismatched_chunks ben duoi thi GIU: no chi bat khi query noi
# ro "mun boc" va khong noi "mun nhot", term deu 2+ tu, va phan biet
# acne nodule / furuncle la phan biet lam sang that.

def drop_acne_boils_mismatched_chunks(
    retrieval: RetrievalOutput | None,
    query: str,
) -> RetrievalOutput | None:
    """Do not use boil/furuncle-only documents as evidence for acne nodules."""
    if retrieval is None or not retrieval.chunks:
        return retrieval
    lowered_query = query.lower()
    asks_acne_nodule = any(term in lowered_query for term in ("mụn bọc", "mun boc"))
    explicitly_asks_boil = any(term in lowered_query for term in ("mụn nhọt", "mun nhot", "boil", "furuncle"))
    if not asks_acne_nodule or explicitly_asks_boil:
        return retrieval
    acne_nodule_terms = ("mụn bọc", "mun boc", "nodular acne", "cystic acne", "acne nodule")
    boil_terms = ("mụn nhọt", "mun nhot", "boil", "furuncle", "furunculosis", "skin abscess")
    kept: list[RetrievedChunk] = []
    for chunk in retrieval.chunks:
        meta = chunk.metadata or {}
        haystack = " ".join((str(meta.get("title") or ""), chunk.text)).lower()
        boil_only = any(term in haystack for term in boil_terms) and not any(
            term in haystack for term in acne_nodule_terms
        )
        if not boil_only:
            kept.append(chunk)
    if len(kept) == len(retrieval.chunks):
        return retrieval
    avg = sum(chunk.score for chunk in kept) / len(kept) if kept else 0.0
    return retrieval.model_copy(update={"chunks": kept, "num_chunks": len(kept), "avg_score": avg})
