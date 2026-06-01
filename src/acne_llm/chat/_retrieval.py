"""Chat retrieval helpers -- query building, RRF fusion, retrieve + rerank."""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from ..schemas import RetrievedChunk, RetrievalOutput, UserInput
from ..schemas.clinical import ClinicalQueryPlan
from ..utils.chunk_filter import drop_noisy_chunks, drop_query_mismatched_chunks, _has_concrete_query_marker, _is_acne_concrete_query
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

    queries = []
    if clinical_plan is not None:
        queries = [
            q.strip()
            for q in [clinical_plan.rag_queries.query_vi]
            if q and q.strip()
        ]
    if not queries:
        queries = [normalized_query.strip() if normalized_query else build_query_from_user(user)]

    # M3: Product safety check — khi user hoi ve ket hop hoat chat (retinol+BHA, AHA+BPO...)
    # Inject ingredient interaction terms vao safety_terms de trigger safety pass retrieve
    # guideline chunks ve contraindication / safe combination.
    if "product_safety_check" in route_flags:
        _ingredient_safety_terms = [
            "ingredient interaction", "active combination", "contraindication skincare",
            "retinol aha bha", "benzoyl peroxide retinoid", "safe combination actives",
            "ket hop hoat chat", "ket hop retinol aha", "chong chi dinh ket hop",
        ]
        existing = set((clinical_plan.safety_terms if clinical_plan is not None else []) + safety_terms)
        added = [t for t in _ingredient_safety_terms if t not in existing]
        if added:
            if clinical_plan is not None:
                clinical_plan.safety_terms = list(clinical_plan.safety_terms) + added
            else:
                safety_terms = list(safety_terms) + added
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
        _ctx.is_pregnant,
        _ctx.is_breastfeeding,
        tuple(sorted(_cl.lesion_types)) if _cl else (),
        tuple(sorted(_cl.lesion_distribution)) if _cl else (),
        (_cl.inflammation_level or "") if _cl else "",
        tuple(sorted(_cl.hormonal_factors)) if _cl else (),
        tuple(sorted(_ctx.medications or [])),
        tuple(sorted(_ctx.current_products or [])),
    )
    _cache_safety_terms = tuple(sorted(
        [*(clinical_plan.safety_terms if clinical_plan is not None else []), *safety_terms]
    ))
    _cache_key = (
        tuple(queries),
        top_k,
        getattr(settings, "chat_rerank_top_k", 3),
        min_score,
        _clinical_fingerprint,
        _cache_safety_terms,
    )

    # FIX 1: Khi plan=False và query không có concrete acne signal,
    # dùng fallback query để tránh kéo chunk không liên quan (e.g. "người sống
    # thực vật có thể bị mụn không" → text message reminder chunks).
    has_plan = clinical_plan is not None
    # Chỉ coi là "vague" khi query KHÔNG hề on-topic về mụn (không nhắc mụn/vị trí/
    # nguyên nhân/cơ chế...). Câu hỏi knowledge rõ ràng như "khác biệt nguyên nhân
    # mụn mặt vs lưng" có topic marker → KHÔNG inject fallback (tránh làm loãng retrieval).
    if not has_plan and len(queries) == 1 and not _is_acne_concrete_query(queries[0]):
        logger.debug(
            "[retrieval] vague query detected (plan=False, off-topic / no acne marker) "
            "— injecting fallback query alongside original"
        )
        queries = [queries[0], _VAGUE_QUERY_FALLBACK]

    # FIX 4: Dùng top_k lớn hơn khi có clinical_plan đầy đủ để LLM có đủ context.
    effective_rerank_top_k = (
        getattr(settings, "chat_rerank_top_k_clinical", 5)
        if has_plan
        else getattr(settings, "chat_rerank_top_k", 3)
    )

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

        retrieve_query: str
        rerank_query: str
        if len(queries) == 1:
            retrieve_query = queries[0]
            ret = c.retriever.retrieve(retrieve_query, top_k=top_k, mode="hybrid")
        else:
            outputs = [
                c.retriever.retrieve(q, top_k=top_k, mode="hybrid") for q in queries
            ]
            retrieve_query = "\n".join(queries)
            ret = merge_retrieval_outputs(outputs, combined_query=retrieve_query)

        # Dùng rerank_query dạng câu tự nhiên cho cross-encoder nếu có.
        # Tránh mismatch format giữa query structured và chunk text tự nhiên.
        _plan_rerank_q = (
            clinical_plan.rag_queries.rerank_query
            if clinical_plan is not None and clinical_plan.rag_queries.rerank_query
            else ""
        )
        rerank_query = _plan_rerank_q or retrieve_query
        if _plan_rerank_q:
            logger.debug("[retrieval] rerank_query (natural): {:.80}", rerank_query)

        # FIX: Safety pass chi chay khi co medical safety term thuc su
        # (pregnancy, isotretinoin, khang sinh...) — khong chay voi generic
        # ingredient terms tu product_safety_check de tranh extra embed +
        # Chroma query khong can thiet (~50-100ms/request).
        all_safety_terms = list(dict.fromkeys(
            [*(clinical_plan.safety_terms if clinical_plan is not None else []), *safety_terms]
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
            return _noise_filter(reranked)
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
