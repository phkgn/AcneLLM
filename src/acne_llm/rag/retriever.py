"""Hybrid retriever: dense (Chroma) + sparse (BM25) with RRF fusion."""
from __future__ import annotations
import numpy as np
from loguru import logger
from ..schemas import RetrievedChunk, RetrievalOutput
from ..schemas.kb import infer_source_type
from .vectorstore import ChromaStore
from .embedder import Embedder
from .sparse import BM25Index

# Source-type specific boost — granular hơn trust_level 3-tier.
# Áp dụng sau RRF fusion để guideline sources nổi lên mà không cần
# nhúng từ "guideline" vào query text.
_SOURCE_TYPE_BOOST: dict[str, float] = {
    "nice_guideline":    1.50,
    "aad_guideline":     1.50,
    "jid_paper":         1.30,
    "pubmed_review":     1.20,
    "clinical_textbook": 1.20,
    "vi_medical_site":   1.00,
    "forum_post":        0.80,
    "blog":              0.70,
    "unknown":           1.00,
}
# Fallback cho chunks cũ chưa có source_type (chỉ có trust_level generic)
_TRUST_LEVEL_BOOST: dict[str, float] = {"high": 1.4, "medium": 1.0, "low": 0.7}
_AUTHORITY_TAG_BOOST = 1.15
_DENSE_MAX_DISTANCE: float = 0.48  # tightened: loại chunk xa centroid (was 0.60)
_MIN_FUSION_SCORE: float = 0.015   # tightened: loại chunk score quá thấp (was 0.005)


def _split_meta_list(value) -> list[str]:
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _source_type_from_meta(meta: dict) -> str:
    source_type = str(meta.get("source_type") or "unknown")
    if source_type != "unknown":
        return source_type
    inferred = infer_source_type(
        source_name=str(meta.get("source") or meta.get("source_name") or ""),
        domain=str(meta.get("domain") or ""),
        url=str(meta.get("url") or ""),
        tags=_split_meta_list(meta.get("tags")),
        categories=_split_meta_list(meta.get("categories")),
    )
    if inferred != "unknown":
        meta["source_type"] = inferred
    return inferred


def _trust_boost(meta: dict) -> float:
    source_type = _source_type_from_meta(meta)
    if source_type and source_type != "unknown":
        return _SOURCE_TYPE_BOOST.get(source_type, 1.0)
    return _TRUST_LEVEL_BOOST.get(str(meta.get("trust") or "medium"), 1.0)


def rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return scores


def mmr_select(
    chunks: list[RetrievedChunk],
    embedder: Embedder | None,
    top_k: int,
    lambda_mult: float = 0.6,
) -> list[RetrievedChunk]:
    """Maximal Marginal Relevance — giảm chunk lặp nội dung."""
    if embedder is None or len(chunks) <= top_k:
        return chunks[:top_k]
    texts = [c.text for c in chunks]
    try:
        embs = embedder.embed_passages(texts)
    except Exception as e:
        logger.debug(f"[MMR] embed failed, skip MMR: {e}")
        return chunks[:top_k]
    raw_scores = np.array([c.score for c in chunks], dtype=float)
    s_min, s_max = raw_scores.min(), raw_scores.max()
    norm_scores = (raw_scores - s_min) / (s_max - s_min) if s_max > s_min else np.ones_like(raw_scores)
    selected_idx: list[int] = []
    remaining = list(range(len(chunks)))
    for _ in range(top_k):
        if not remaining:
            break
        if not selected_idx:
            best = max(remaining, key=lambda i: norm_scores[i])
        else:
            sel_embs = embs[selected_idx]
            best, best_mmr = -1, -float("inf")
            for i in remaining:
                rel = float(norm_scores[i])
                sim = float(np.max(embs[i] @ sel_embs.T))
                mmr = lambda_mult * rel - (1 - lambda_mult) * sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best = i
        selected_idx.append(best)
        remaining.remove(best)
    return [chunks[i] for i in selected_idx]


class HybridRetriever:
    def __init__(
        self,
        store: ChromaStore,
        embedder: Embedder | None,
        bm25: BM25Index | None = None,
        dense_max_distance: float = _DENSE_MAX_DISTANCE,
    ):
        self.store = store
        self.embedder = embedder
        self.bm25 = bm25
        self.dense_max_distance = dense_max_distance

    def retrieve(self, query: str, top_k: int = 15, mode: str = "hybrid",
                 domain_filter: dict | None = None) -> RetrievalOutput:
        """Hybrid retrieval với distance filter, trust boost và score pruning."""
        dense_ids: list[str] = []
        sparse_ids: list[str] = []
        dense_meta: dict[str, dict] = {}
        fetch_k = min(top_k * 3, 60)

        dense_enabled = mode in ("dense", "hybrid") and self.embedder is not None
        if dense_enabled:
            try:
                q_emb = self.embedder.embed_query(query)
                res = self.store.query_with_score_filter(
                    q_emb, top_k=fetch_k,
                    max_distance=self.dense_max_distance,
                    filters=domain_filter,
                    fallback_to_raw=False,
                )
                ids = (res.get("ids") or [[]])[0]
                docs = (res.get("documents") or [[]])[0]
                metas = (res.get("metadatas") or [[]])[0]
                dists = (res.get("distances") or [[]])[0]
                dense_ids = list(ids)
                for cid, text, meta, dist in zip(ids, docs, metas, dists):
                    dense_meta[cid] = {"text": text, "meta": meta or {}, "dist": float(dist)}
                logger.debug(f"[retriever] dense={len(dense_ids)} chunks (max_dist={self.dense_max_distance})")
            except Exception as e:
                logger.warning(f"[retriever] Dense unavailable, sparse-only: {e}")
                dense_ids = []

        sparse_hits: list[tuple[str, float]] = []
        if mode in ("sparse", "hybrid") and self.bm25 is not None:
            sparse_hits = self.bm25.query(query, top_k=fetch_k)
            sparse_ids = [cid for cid, _ in sparse_hits]
            logger.debug(f"[retriever] sparse={len(sparse_ids)} hits")

        ranked: list[tuple[str, float]]
        if mode == "dense":
            if dense_ids:
                ranked = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(dense_ids[:top_k])]
            else:
                logger.warning("[retriever] Dense unavailable; falling back to sparse")
                ranked = sparse_hits[:top_k]
        elif mode == "sparse":
            ranked = sparse_hits[:top_k]
        else:
            fused = rrf_fusion([dense_ids, sparse_ids]) if dense_ids else dict(sparse_hits)
            _authority_tags = {"hospital", "guidelines", "government", "authoritative", "evidence-based", "pharmacopoeia"}

            # FIX: Batch fetch metadata cho sparse-only chunks thay vì N lần get_by_id
            _sparse_only_cids = [cid for cid in fused if not dense_meta.get(cid, {}).get("meta")]
            _batch_meta: dict[str, dict] = {}
            if _sparse_only_cids:
                try:
                    _got = self.store.get_by_ids(_sparse_only_cids)
                    for _cid, _m in zip(_got.get("ids") or [], _got.get("metadatas") or []):
                        _batch_meta[_cid] = _m or {}
                except Exception as _e:
                    logger.debug(f"[retriever] batch meta fetch failed: {_e}")

            for cid in list(fused.keys()):
                meta = dense_meta.get(cid, {}).get("meta") or _batch_meta.get(cid, {})
                raw_tags = meta.get("tags", "")
                tags = set(raw_tags.split(",")) if isinstance(raw_tags, str) and raw_tags else set()
                score = fused[cid] * _trust_boost(meta)
                if tags & _authority_tags:
                    score *= _AUTHORITY_TAG_BOOST
                fused[cid] = score
            fused = {cid: s for cid, s in fused.items() if s >= _MIN_FUSION_SCORE}
            ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
            logger.debug(f"[retriever] hybrid fused={len(ranked)} chunks")

        # FIX: Batch fetch text+meta cho tất cả chunks không có trong dense_meta
        _missing_cids = [cid for cid, _ in ranked if cid not in dense_meta]
        _fetched: dict[str, tuple[str, dict]] = {}
        if _missing_cids:
            try:
                _res = self.store.get_by_ids(_missing_cids)
                for _cid, _doc, _m in zip(
                    _res.get("ids") or [],
                    _res.get("documents") or [],
                    _res.get("metadatas") or [],
                ):
                    _fetched[_cid] = (_doc or "", _m or {})
            except Exception as _e:
                logger.debug(f"[retriever] batch fetch failed: {_e}")

        chunks: list[RetrievedChunk] = []
        for cid, score in ranked:
            if cid in dense_meta:
                text = dense_meta[cid]["text"]
                meta = dense_meta[cid]["meta"]
            else:
                text, meta = _fetched.get(cid, ("", {}))
            if not text:
                continue
            _source_type_from_meta(meta)
            chunks.append(RetrievedChunk(
                chunk_id=cid,
                source=meta.get("source", ""),
                text=text,
                score=float(score),
                metadata=meta or {},
            ))

        avg = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        return RetrievalOutput(
            query=query, chunks=chunks,
            retrieval_mode=mode if mode in ("dense", "sparse", "hybrid") else "hybrid",
            num_chunks=len(chunks), avg_score=avg,
        )

    def retrieve_with_mmr(self, query: str, top_k: int = 15, rerank_top_k: int = 10,
                          mode: str = "hybrid", domain_filter: dict | None = None,
                          mmr_lambda: float = 0.6) -> RetrievalOutput:
        """Retrieve rồi áp MMR diversity filter để giảm chunk lặp nội dung."""
        raw = self.retrieve(query, top_k=top_k, mode=mode, domain_filter=domain_filter)
        if not raw.chunks:
            return raw
        diverse = mmr_select(raw.chunks, self.embedder, top_k=rerank_top_k, lambda_mult=mmr_lambda)
        avg = sum(c.score for c in diverse) / len(diverse) if diverse else 0.0
        return RetrievalOutput(
            query=raw.query, chunks=diverse,
            retrieval_mode=raw.retrieval_mode,
            num_chunks=len(diverse), avg_score=avg,
        )

    def expand_context(self, retrieval: RetrievalOutput) -> RetrievalOutput:
        """Fetch prev/next chunk liền kề sau rerank để mở rộng ngữ cảnh."""
        if not retrieval.chunks:
            return retrieval

        existing_ids = {c.chunk_id for c in retrieval.chunks}
        id_to_score = {c.chunk_id: c.score for c in retrieval.chunks}
        neighbor_parent: dict[str, str] = {}
        neighbor_ids: list[str] = []

        for chunk in retrieval.chunks:
            for nk in ("prev_chunk_id", "next_chunk_id"):
                nid = chunk.metadata.get(nk, "")
                if not nid or nid in existing_ids or nid in neighbor_parent:
                    continue
                neighbor_parent[nid] = chunk.chunk_id
                neighbor_ids.append(nid)

        if not neighbor_ids:
            return retrieval

        try:
            got = self.store.get_by_ids(neighbor_ids)
        except Exception as e:
            logger.debug(f"[expand_context] Không lấy được neighbor chunks: {e}")
            return retrieval

        ids = got.get("ids") or []
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        by_id: dict[str, tuple[str, dict]] = {}
        for cid, text, meta in zip(ids, docs, metas):
            by_id[cid] = (text or "", meta or {})

        extras: list[RetrievedChunk] = []
        for nid in neighbor_ids:
            found = by_id.get(nid)
            if found is None:
                continue
            text, meta = found
            parent_score = id_to_score.get(neighbor_parent.get(nid, ""), 0.0)
            extras.append(RetrievedChunk(
                chunk_id=nid,
                source=meta.get("source", ""),
                text=text,
                score=parent_score * 0.5,
                metadata=meta,
            ))

        if not extras:
            return retrieval

        combined = retrieval.chunks + extras
        combined.sort(key=lambda c: c.score, reverse=True)
        avg = sum(c.score for c in combined) / len(combined) if combined else 0.0
        logger.debug(f"[expand_context] +{len(extras)} neighbor chunks -> tong {len(combined)}")
        return RetrievalOutput(
            query=retrieval.query,
            chunks=combined,
            retrieval_mode=retrieval.retrieval_mode,
            num_chunks=len(combined),
            avg_score=avg,
        )

    def retrieve_safety_pass(
        self,
        query: str,
        safety_terms: list[str],
        top_k: int = 5,
    ) -> RetrievalOutput:
        """Second retrieve pass cho context an toan y te (thai ky, thuoc).

        Filter Chroma chi lay guideline source_types, sau do dense retrieve.
        Duoc goi tu pipeline khi safety_terms khong rong.
        """
        _EMPTY = RetrievalOutput(
            query=query, chunks=[], retrieval_mode="hybrid",
            num_chunks=0, avg_score=0.0,
        )
        if not safety_terms or not self.embedder:
            return _EMPTY

        safety_query = query + " " + " ".join(safety_terms)
        domain_filter = {"source_type": {"$in": [
            "nice_guideline", "aad_guideline", "jid_paper",
            "pubmed_review", "clinical_textbook",
        ]}}

        try:
            qvec = self.embedder.embed_query(safety_query)
            raw = self.store.query_with_score_filter(
                qvec, top_k=top_k, filters=domain_filter
            )
        except Exception as e:
            logger.debug(f"[safety_pass] query failed: {e}")
            return _EMPTY

        ids = (raw.get("ids") or [[]])[0]
        if not ids:
            try:
                raw = self.store.query_with_score_filter(qvec, top_k=top_k)
            except Exception as e:
                logger.debug(f"[safety_pass] fallback query failed: {e}")
                return _EMPTY
            ids = (raw.get("ids") or [[]])[0]
        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        chunks = []
        for cid, text, meta, dist in zip(ids, docs, metas, dists):
            score = max(0.0, 1.0 - float(dist))
            meta = meta or {}
            source_type = _source_type_from_meta(meta)
            if source_type not in domain_filter["source_type"]["$in"]:
                continue
            chunks.append(RetrievedChunk(
                chunk_id=cid, source=meta.get("source", ""), text=text or "",
                score=score, metadata=meta or {},
            ))

        chunks.sort(key=lambda c: c.score, reverse=True)
        avg = sum(c.score for c in chunks) / len(chunks) if chunks else 0.0
        logger.debug(f"[safety_pass] {len(chunks)} guideline chunks for safety context")
        return RetrievalOutput(
            query=safety_query, chunks=chunks,
            retrieval_mode="hybrid",
            num_chunks=len(chunks), avg_score=avg,
        )
