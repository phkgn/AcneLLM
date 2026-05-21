"""Chat retrieval helpers -- query building, RRF fusion, retrieve + rerank."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ..schemas import RetrievedChunk, RetrievalOutput, UserInput
from ..schemas.clinical import ClinicalQueryPlan
from ..utils.chunk_filter import drop_noisy_chunks, drop_query_mismatched_chunks
from ..cache import cached_retrieve

if TYPE_CHECKING:
    from ..di import Container


# -- Query builder ------------------------------------------------------------

def build_query_from_user(user: UserInput) -> str:
    """Tao query ngan gon tu UserInput de truyen vao retriever."""
    parts = [user.description]
    c = user.context
    context_bits: list[str] = []
    if c.age is not None:
        context_bits.append(f"{c.age} tuoi")
    if c.skin_type:
        context_bits.append(f"da {c.skin_type}")
    if c.is_pregnant:
        context_bits.append("mang thai")
    if c.is_breastfeeding:
        context_bits.append("cho con bu")
    if c.current_products:
        context_bits.append("dang dung " + ", ".join(c.current_products))
    if c.duration_weeks is not None:
        context_bits.append(f"keo dai {c.duration_weeks} tuan")
    if context_bits:
        parts.append("; ".join(context_bits))

    if user.clinical:
        clinical_bits = []
        if user.clinical.lesion_types:
            clinical_bits.append("loai mun " + ", ".join(user.clinical.lesion_types))
        if user.clinical.lesion_distribution:
            clinical_bits.append("vi tri " + ", ".join(user.clinical.lesion_distribution))
        if user.clinical.inflammation_level:
            clinical_bits.append("muc viem " + user.clinical.inflammation_level)
        if clinical_bits:
            parts.append("; ".join(clinical_bits))
    return "\n".join(parts)


# -- RRF fusion ---------------------------------------------------------------

def rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return scores


def merge_retrieval_outputs(
    outputs: list[RetrievalOutput], combined_query: str
) -> RetrievalOutput:
    """Gop nhieu RetrievalOutput bang RRF fusion."""
    by_id: dict[str, RetrievedChunk] = {}
    for output in outputs:
        for chunk in output.chunks:
            if chunk.chunk_id not in by_id:
                by_id[chunk.chunk_id] = RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    source=chunk.source,
                    text=chunk.text,
                    score=0.0,
                    metadata=chunk.metadata,
                )
    fused = rrf_fusion([[chunk.chunk_id for chunk in output.chunks] for output in outputs])
    chunks = []
    for chunk_id, score in fused.items():
        chunk = by_id[chunk_id]
        chunk.score = score
        chunks.append(chunk)
    chunks.sort(key=lambda c: c.score, reverse=True)
    avg = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
    return RetrievalOutput(
        query=combined_query,
        chunks=chunks,
        retrieval_mode="hybrid",
        num_chunks=len(chunks),
        avg_score=avg,
    )


# -- Main retrieve entry point ------------------------------------------------

def retrieve_for_chat(
    c: "Container",
    user: UserInput,
    clinical_plan: ClinicalQueryPlan | None = None,
    route_flags: list[str] | None = None,
) -> RetrievalOutput | None:
    """Retrieve + rerank chunks cho chat stream. Tra None neu RAG chua san sang.

    Args:
        route_flags: Route flags from intent router. When "language_switch" is
            present and detected_language == "en", an additional English query
            is issued alongside the Vietnamese one (bilingual RAG, M9).
    """
    if not c.rag_ready or c.retriever is None:
        return None

    settings = c.settings
    min_score = float(getattr(settings, "chat_min_citation_score", 0.25))
    top_k = getattr(settings, "chat_retrieve_top_k", 8)
    route_flags = route_flags or []

    queries = []
    if clinical_plan is not None:
        queries = [
            q.strip()
            for q in [clinical_plan.rag_queries.query_vi]
            if q and q.strip()
        ]
    if not queries:
        queries = [build_query_from_user(user)]

    # M9: Language switch — thêm English query song song (bilingual RAG)
    if "language_switch" in route_flags and clinical_plan is not None:
        en_query = getattr(clinical_plan.rag_queries, "query_en", "").strip()
        if en_query and en_query not in queries:
            queries.append(en_query)
            logger.debug("[retrieval] Language switch — added EN query: {!r}", en_query[:60])

    # M3: Product safety check — khi user hỏi về kết hợp hoạt chất (retinol+BHA, AHA+BPO...)
    # Inject ingredient interaction terms vào safety_terms để trigger safety pass retrieve
    # guideline chunks về contraindication / safe combination.
    if "product_safety_check" in route_flags and clinical_plan is not None:
        _ingredient_safety_terms = [
            "ingredient interaction", "active combination", "contraindication skincare",
            "retinol aha bha", "benzoyl peroxide retinoid", "safe combination actives",
            "ket hop hoat chat", "ket hop retinol aha", "chong chi dinh ket hop",
        ]
        existing = set(clinical_plan.safety_terms)
        added = [t for t in _ingredient_safety_terms if t not in existing]
        if added:
            clinical_plan.safety_terms = list(clinical_plan.safety_terms) + added
            logger.debug("[retrieval] product_safety_check — injected {} ingredient safety terms", len(added))

    # Cache key: bao gom clinical context sau fold de tranh share cache
    # giua cac turn co session facts khac nhau (vi du: turn 2 co lesion, turn 1 khong)
    _ctx = user.context
    _cl = user.clinical
    _clinical_fingerprint = (
        _ctx.age,
        _ctx.sex,
        _ctx.skin_type,
        _ctx.duration_weeks,
        tuple(sorted(_cl.lesion_types)) if _cl else (),
        tuple(sorted(_cl.lesion_distribution)) if _cl else (),
        (_cl.inflammation_level or "") if _cl else "",
        tuple(sorted(_cl.hormonal_factors)) if _cl else (),
        tuple(sorted(_ctx.medications or [])),
        tuple(sorted(_ctx.current_products or [])),
    )
    _cache_key = (
        tuple(queries),
        top_k,
        getattr(settings, "chat_rerank_top_k", 3),
        min_score,
        _clinical_fingerprint,
    )

    def _do_retrieve_and_rerank() -> RetrievalOutput | None:
        rerank_query: str
        if len(queries) == 1:
            ret = c.retriever.retrieve(queries[0], top_k=top_k, mode="hybrid")
            rerank_query = queries[0]
        else:
            outputs = [
                c.retriever.retrieve(q, top_k=top_k, mode="hybrid") for q in queries
            ]
            rerank_query = "\n".join(queries)
            ret = merge_retrieval_outputs(outputs, combined_query=rerank_query)

        # Safety pass: guideline chunks cho cau hoi lien quan thai ky / thuoc ke don
        if (
            clinical_plan is not None
            and clinical_plan.safety_terms
            and hasattr(c.retriever, "retrieve_safety_pass")
        ):
            safety = c.retriever.retrieve_safety_pass(
                rerank_query,
                clinical_plan.safety_terms,
                top_k=getattr(settings, "chat_safety_top_k", 5),
            )
            if safety.chunks:
                ret = merge_retrieval_outputs([ret, safety], combined_query=rerank_query)

        if c.reranker is None:
            return drop_query_mismatched_chunks(
                drop_noisy_chunks(ret, min_score=min_score),
                rerank_query,
            )
        try:
            reranked = c.reranker.rerank(
                rerank_query,
                ret,
                top_k=getattr(settings, "chat_rerank_top_k", 3),
            )
            return drop_query_mismatched_chunks(
                drop_noisy_chunks(reranked, min_score=min_score),
                rerank_query,
            )
        except Exception as e:
            logger.warning(f"Chat reranker unavailable, using raw retrieval: {e}")
            return drop_query_mismatched_chunks(
                drop_noisy_chunks(ret, min_score=min_score),
                rerank_query,
            )

    return cached_retrieve(_do_retrieve_and_rerank, _cache_key)


# -- Citation helper ----------------------------------------------------------

def citation_data(chunk: RetrievedChunk) -> dict:
    """Chuyen RetrievedChunk thanh dict gui qua SSE event 'citation'."""
    meta = chunk.metadata or {}
    return {
        "chunk_id": chunk.chunk_id,
        "source": meta.get("source", chunk.source),
        "title": meta.get("title", ""),
        "url": meta.get("url", ""),
        "score": round(chunk.score, 4),
        "text": chunk.text[:220],
    }


# -- Evidence quality ---------------------------------------------------------

def compute_evidence_quality(retrieval) -> str:
    """Tinh muc do tin cay dua tren avg reranker score cua cac chunks.

    Returns:
        "strong"     -- avg score >= 0.65  (nhieu bang chung chat luong cao)
        "moderate"   -- avg score 0.40-0.65
        "weak"       -- avg score < 0.40   (it hoac bang chung kem chat luong)
        "unverified" -- khong co retrieval (llm_only mode)
    """
    if retrieval is None or not retrieval.chunks:
        return "unverified"
    avg = sum(c.score for c in retrieval.chunks) / len(retrieval.chunks)
    if avg >= 0.65:
        return "strong"
    if avg >= 0.40:
        return "moderate"
    return "weak"
