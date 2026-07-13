"""Chat retrieval helpers -- query building, RRF fusion, retrieve + rerank."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ..schemas import RetrievedChunk, RetrievalOutput, UserInput
from ..schemas.clinical import ClinicalQueryPlan
from ..utils.chunk_filter import (
    drop_acne_boils_mismatched_chunks,
    drop_body_region_mismatched_chunks,
    drop_noisy_chunks,
    drop_query_mismatched_chunks,
)
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
    max_score = max(fused.values(), default=0.0)
    chunks = []
    for chunk_id, score in fused.items():
        chunk = by_id[chunk_id]
        chunk.score = float(score / max_score) if max_score > 0 else 0.0
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


# -- Medical safety terms for safety pass gate --------------------------------

# FIX: Safety pass chỉ chạy khi có ít nhất 1 medical safety term thực sự.
# Generic ingredient terms từ product_safety_check KHÔNG trigger safety pass
# để tránh extra embed + Chroma query không cần thiết (~50-100ms/request).
_MEDICAL_SAFETY_TERMS = frozenset({
    "mang thai", "pregnant", "pregnancy",
    "cho con bu", "cho con bú", "breastfeeding", "lactation",
    "isotretinoin", "retinoid", "tretinoin", "adapalene", "tazarotene",
    "doxycycline", "minocycline", "tetracycline", "khang sinh", "kháng sinh", "antibiotic",
})

# Query fallback dùng khi plan=False + không có concrete acne signal trong query gốc.
# Giúp dense retriever kéo đúng chunk kiến thức chung về mụn thay vì chunk ngẫu nhiên.
_VAGUE_QUERY_FALLBACK = (
    "mụn trứng cá nguyên nhân cơ chế tuyến bã nhờn acne pathophysiology "
    "vulgaris cause sebum follicle"
)


def _has_medical_safety_terms(safety_terms: list[str]) -> bool:
    return any(
        any(marker in str(t).lower() for marker in _MEDICAL_SAFETY_TERMS)
        for t in safety_terms
    )


# -- Main retrieve entry point ------------------------------------------------

def retrieve_for_chat(
    c: "Container",
    user: UserInput,
    clinical_plan: ClinicalQueryPlan | None = None,
    route_flags: list[str] | None = None,
    normalized_query: str | None = None,
    safety_terms: list[str] | None = None,
) -> RetrievalOutput | None:
    """Retrieve + rerank chunks cho chat stream. Tra None neu RAG chua san sang."""
    if not c.rag_ready or c.retriever is None:
        return None

    settings = c.settings
    min_score = float(getattr(settings, "chat_min_citation_score", 0.25))
    top_k = getattr(settings, "chat_retrieve_top_k", 8)
    route_flags = route_flags or []
    safety_terms = list(dict.fromkeys(safety_terms or []))

    # Production retrieval is current-turn-first. The planner remains available
    # to debug analytics but cannot rewrite this query.
    query = normalized_query.strip() if normalized_query else user.description.strip()
    _cache_safety_terms = tuple(sorted(safety_terms))
    _cache_key = (
        "chat-query-v2",
        query,
        top_k,
        getattr(settings, "chat_rerank_top_k", 3),
        min_score,
        _cache_safety_terms,
    )
    effective_rerank_top_k = getattr(settings, "chat_rerank_top_k", 3)

    def _do_retrieve_and_rerank() -> RetrievalOutput | None:
        def _noise_filter(output: RetrievalOutput) -> RetrievalOutput:
            """Chỉ loại noisy chunks — dùng SAU reranker (score đã tin cậy)."""
            after_noise = drop_noisy_chunks(output, min_score=min_score)
            if after_noise is not None and len(after_noise.chunks) < len(output.chunks):
                logger.debug(
                    "[retrieval] drop_noisy: {} -> {} chunks (min_score={:.2f})",
                    len(output.chunks), len(after_noise.chunks), min_score,
                )
            return (after_noise if after_noise is not None and after_noise.chunks else output)

        def _full_filter(output: RetrievalOutput, query: str) -> RetrievalOutput:
            """Noise + keyword mismatch — dùng khi KHÔNG có reranker (raw retrieval)."""
            after_noise = _noise_filter(output)
            filtered = drop_query_mismatched_chunks(after_noise, query)
            if filtered is not None and len(filtered.chunks) < len(after_noise.chunks):
                logger.debug(
                    "[retrieval] drop_mismatched: {} -> {} chunks (query={!r:.80})",
                    len(after_noise.chunks), len(filtered.chunks), query,
                )
            return filtered if filtered is not None and filtered.chunks else after_noise

        retrieve_query = query
        rerank_query = query
        ret = c.retriever.retrieve(retrieve_query, top_k=top_k, mode="hybrid")

        # FIX: Safety pass chi chay khi co medical safety term thuc su
        # (pregnancy, isotretinoin, khang sinh...) — khong chay voi generic
        # ingredient terms tu product_safety_check de tranh extra embed +
        # Chroma query khong can thiet (~50-100ms/request).
        all_safety_terms = list(dict.fromkeys(
            safety_terms
        ))
        if (
            all_safety_terms
            and _has_medical_safety_terms(all_safety_terms)
            and hasattr(c.retriever, "retrieve_safety_pass")
        ):
            safety = c.retriever.retrieve_safety_pass(
                rerank_query,
                all_safety_terms,
                top_k=getattr(settings, "chat_safety_top_k", 5),
            )
            if safety.chunks:
                ret = merge_retrieval_outputs([ret, safety], combined_query=rerank_query)

        if c.reranker is None:
            return _full_filter(ret, rerank_query)
        try:
            reranked = c.reranker.rerank(
                rerank_query,
                ret,
                top_k=effective_rerank_top_k,
            )
            # OOD guard: nếu reranker không tìm được chunk nào liên quan
            # (avg sigmoid thấp + max score gần 0.5 = random logit),
            # trả None để LLM trả lời không dùng RAG thay vì inject chunk nhiễu.
            _ood_floor = float(getattr(settings, "chat_rerank_ood_floor", 0.45))
            _keep_floor = float(getattr(settings, "chat_rerank_keep_floor", _ood_floor))
            if reranked.chunks:
                _avg = sum(c.score for c in reranked.chunks) / len(reranked.chunks)
                _max = max(c.score for c in reranked.chunks)
                # Ngưỡng MỀM: giữ riêng chunk vượt keep_floor thay vì all-or-nothing.
                _kept = [c for c in reranked.chunks if c.score >= _keep_floor]
                if not _kept:
                    logger.info(
                        "[retrieval] OOD guard: avg_sigmoid={:.3f} max={:.3f} < keep_floor={:.3f} "
                        "— dropping {} chunks (query={!r:.80})",
                        _avg, _max, _keep_floor, len(reranked.chunks), rerank_query,
                    )
                    return None
                if len(_kept) < len(reranked.chunks):
                    logger.debug(
                        "[retrieval] OOD soft-filter: kept {}/{} chunks (keep_floor={:.3f} max={:.3f})",
                        len(_kept), len(reranked.chunks), _keep_floor, _max,
                    )
                    reranked = reranked.model_copy(update={"chunks": _kept, "num_chunks": len(_kept)})
            # Sau reranker: chỉ loại noisy chunks, KHÔNG dùng keyword mismatch filter
            # vì cross-encoder đã score relevance rồi — mismatch filter sẽ drop nhầm.
            semantic_filtered = drop_acne_boils_mismatched_chunks(reranked, rerank_query)
            region_filtered = drop_body_region_mismatched_chunks(semantic_filtered, rerank_query)
            if region_filtered is not None and not region_filtered.chunks:
                return None
            return _noise_filter(region_filtered or reranked)
        except Exception as e:
            logger.warning(f"Chat reranker unavailable, using raw retrieval: {e}")
            return _full_filter(ret, rerank_query)

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
