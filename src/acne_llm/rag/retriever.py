"""Hybrid retriever: dense (Chroma) + sparse (BM25) with RRF fusion."""
from __future__ import annotations
from loguru import logger
from ..schemas import RetrievedChunk, RetrievalOutput
from .vectorstore import ChromaStore
from .embedder import Embedder
from .sparse import BM25Index

# Fix 2: boost score cho nguon tin cay cao sau RRF fusion
# PubMed, WebMD, Healthline (trust=high) duoc uu tien hon blog/bao thong thuong
# MEDIUM-6: Increased high-trust boost from 1.3 → 1.5
_TRUST_BOOST: dict[str, float] = {
    "high": 1.5,
    "medium": 1.0,
    "low": 0.7,
}

# MEDIUM-6: Extra boost for authoritative source types (applied on top of trust boost)
# Source tags như "hospital", "guidelines", "government", "authoritative" được ưu tiên
_AUTHORITY_TAG_BOOST = 1.15


def rrf_fusion(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + i + 1)
    return scores


class HybridRetriever:
    def __init__(self, store: ChromaStore, embedder: Embedder | None, bm25: BM25Index | None = None):
        self.store = store
        self.embedder = embedder
        self.bm25 = bm25

    def retrieve(self, query: str, top_k: int = 20,
                 mode: str = "hybrid") -> RetrievalOutput:
        dense_ids: list[str] = []
        sparse_ids: list[str] = []
        dense_meta: dict[str, dict] = {}

        dense_enabled = mode in ("dense", "hybrid") and self.embedder is not None
        if dense_enabled:
            try:
                q_emb = self.embedder.embed_query(query)
                res = self.store.query(q_emb, top_k=top_k * 2)
                ids_l = res.get("ids") or [[]]
                docs_l = res.get("documents") or [[]]
                metas_l = res.get("metadatas") or [[]]
                dists_l = res.get("distances") or [[]]
                ids = ids_l[0] if ids_l else []
                docs = docs_l[0] if docs_l else []
                metas = metas_l[0] if metas_l else []
                dists = dists_l[0] if dists_l else []
                dense_ids = list(ids)
                for cid, text, meta, dist in zip(ids, docs, metas, dists):
                    dense_meta[cid] = {"text": text, "meta": meta or {}, "dist": float(dist)}
            except Exception as e:
                logger.warning(f"[retriever] Dense retrieval unavailable, using sparse-only fallback: {e}")
                dense_ids = []

        sparse_hits: list[tuple[str, float]] = []
        if mode in ("sparse", "hybrid") and self.bm25 is not None:
            sparse_hits = self.bm25.query(query, top_k=top_k * 2)
            sparse_ids = [cid for cid, _ in sparse_hits]

        if mode == "dense":
            if dense_ids:
                ranked = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(dense_ids[:top_k])]
            else:
                logger.warning("[retriever] Dense mode requested but dense retrieval is unavailable; falling back to sparse")
                ranked = sparse_hits[:top_k]
        elif mode == "sparse":
            ranked = sparse_hits[:top_k]
        else:
            fused = rrf_fusion([dense_ids, sparse_ids]) if dense_ids else dict(sparse_hits)

            # Fix 2: apply trust boost dua tren metadata tu dense retrieval
            # Chunk chi co trong sparse (khong co trong dense_meta) giu score goc
            # MEDIUM-6: Added authority tag boost for hospital/guidelines sources
            _authority_tags = {"hospital", "guidelines", "government", "authoritative", "evidence-based", "pharmacopoeia"}
            for cid in list(fused.keys()):
                meta = dense_meta.get(cid, {}).get("meta", {})
                trust = meta.get("trust", "medium")
                tags = set(meta.get("tags", [])) if isinstance(meta.get("tags"), list) else set()
                score = fused[cid] * _TRUST_BOOST.get(trust, 1.0)
                if tags & _authority_tags:
                    score *= _AUTHORITY_TAG_BOOST
                fused[cid] = score

            ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]

        chunks: list[RetrievedChunk] = []
        for cid, score in ranked:
            if cid in dense_meta:
                dm = dense_meta[cid]
                text = dm["text"]
                meta = dm["meta"]
            else:
                got = self.store.get_by_id(cid)
                docs = got.get("documents") or []
                metas = got.get("metadatas") or []
                text = docs[0] if docs else ""
                meta = metas[0] if metas else {}
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

    def expand_context(self, retrieval: RetrievalOutput) -> RetrievalOutput:
        """Fix 3: Fetch prev/next chunk lien ke cho moi chunk trong ket qua.

        Sau khi reranker chon top-k, goi ham nay de mo rong ngu canh:
        moi chunk se duoc bo sung chunk truoc va sau (neu ton tai va chua co
        trong ket qua). Chunk mo rong nhan score = 0.5 * score chunk goc de
        phan biet voi chunk duoc retrieve truc tiep.

        Luu y: can Chroma da luu prev_chunk_id/next_chunk_id trong metadata
        (vectorstore.upsert da duoc cap nhat de luu 2 field nay).
        """
        if not retrieval.chunks:
            return retrieval

        existing_ids = {c.chunk_id for c in retrieval.chunks}
        id_to_score = {c.chunk_id: c.score for c in retrieval.chunks}
        extras: list[RetrievedChunk] = []

        for chunk in retrieval.chunks:
            for neighbor_key in ("prev_chunk_id", "next_chunk_id"):
                neighbor_id = chunk.metadata.get(neighbor_key, "")
                if not neighbor_id or neighbor_id in existing_ids:
                    continue
                try:
                    got = self.store.get_by_id(neighbor_id)
                    docs = got.get("documents") or []
                    metas = got.get("metadatas") or []
                    if not docs:
                        continue
                    text = docs[0]
                    meta = metas[0] if metas else {}
                    neighbor_score = id_to_score[chunk.chunk_id] * 0.5
                    extras.append(RetrievedChunk(
                        chunk_id=neighbor_id,
                        source=meta.get("source", ""),
                        text=text,
                        score=neighbor_score,
                        metadata=meta or {},
                    ))
                    existing_ids.add(neighbor_id)
                except Exception as e:
                    logger.debug(f"[expand_context] Khong lay duoc {neighbor_id}: {e}")

        if not extras:
            return retrieval

        all_chunks = retrieval.chunks + extras
        avg = sum(c.score for c in all_chunks) / len(all_chunks)
        logger.debug(f"[expand_context] +{len(extras)} neighbor chunks -> tong {len(all_chunks)}")
        return RetrievalOutput(
            query=retrieval.query,
            chunks=all_chunks,
            retrieval_mode=retrieval.retrieval_mode,
            num_chunks=len(all_chunks),
            avg_score=avg,
        )
