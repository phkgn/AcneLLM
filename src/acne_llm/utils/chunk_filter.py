"""Shared chunk-quality filters used by both pipeline/hybrid.py and chat/runtime.py.

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


# Marker "on-topic acne" — rộng hơn _CONCRETE_QUERY_MARKERS (vốn chỉ là tên sản phẩm).
# Dùng riêng cho vague-detection: một câu hỏi kiến thức rõ ràng về mụn (nhắc tới
# mụn / vị trí / cơ chế / nguyên nhân) KHÔNG nên bị coi là "vague" chỉ vì không
# nhắc tên sản phẩm cụ thể.
_ACNE_TOPIC_MARKERS = (
    # tổn thương / từ khoá mụn
    "mụn", "mun", "trứng cá", "trung ca", "acne", "comedone", "comedo",
    "sẩn", "san", "nang", "viêm", "viem", "thâm", "tham", "sẹo", "seo",
    "đầu đen", "dau den", "đầu trắng", "dau trang", "nhân mụn", "nhan mun",
    "papule", "pustule", "nodule", "cyst", "blackhead", "whitehead",
    "lỗ chân lông", "lo chan long", "bã nhờn", "ba nhon", "tuyến bã", "tuyen ba",
    # vị trí cơ thể
    "mặt", "mat", "trán", "tran", "má", "cằm", "cam", "mũi", "mui",
    "lưng", "lung", "ngực", "nguc", "vai", "cổ", "hàm", "ham",
    # khái niệm / nguyên nhân / cơ chế (câu hỏi knowledge)
    "nguyên nhân", "nguyen nhan", "cơ chế", "co che", "vì sao", "vi sao",
    "tại sao", "tai sao", "nội tiết", "noi tiet", "hormone", "hormonal",
    "vi khuẩn", "vi khuan", "dầu", "dau", "khác biệt", "khac biet",
    "so sánh", "so sanh", "phân biệt", "phan biet", "loại mụn", "loai mun",
    "điều trị", "dieu tri", "trị mụn", "tri mun", "phòng ngừa", "phong ngua",
)


def _is_acne_concrete_query(query: str) -> bool:
    """True khi query là câu hỏi/mô tả on-topic về mụn (không mơ hồ).

    Rộng hơn _has_concrete_query_marker: chấp nhận cả thuật ngữ mụn, vị trí cơ thể,
    và từ khái niệm/nguyên nhân — để câu hỏi knowledge rõ ràng không bị gắn "vague".
    """
    lowered = query.lower()
    if _has_concrete_query_marker(query):
        return True
    return any(marker in lowered for marker in _ACNE_TOPIC_MARKERS)


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
