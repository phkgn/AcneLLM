"""S4 — RAG-only extractive: retrieval production đầy đủ (hybrid+MMR+rerank+filter),
KHÔNG gọi LLM. Trả top chunks dạng template cố định, không sinh chữ mới.
"""
from __future__ import annotations

from acne_llm.config import settings

from .base import SystemAdapter
from ._repo import build_eval_container, normalize_query


def _truncate_snippet(text: str, budget: int) -> str:
    """Prefer a complete verbatim sentence over a raw mid-sentence char cut."""
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    candidate = text[:budget].rstrip()
    sentence_cut = max(
        candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"),
        candidate.rfind("。"),
    )
    if sentence_cut >= max(40, int(budget * 0.45)):
        return candidate[:sentence_cut + 1].strip()
    # No complete sentence fits. Keep a word boundary and explicitly mark that
    # the quote is incomplete instead of presenting a cut fragment as a claim.
    word_cut = candidate.rsplit(" ", 1)[0].rstrip()
    return (word_cut or candidate) + "…"


class ExtractiveAdapter(SystemAdapter):
    def prepare(self) -> None:
        # model=None → container vẫn build LLM object nhưng không bao giờ gọi generate
        self.container = build_eval_container(model=None, sampling=None)
        if not self.container.rag_ready:
            raise RuntimeError("KB chưa sẵn sàng cho extractive baseline")

    def retrieve(self, sample: dict) -> dict:
        from acne_llm.utils.retrieval_query import build_retrieval_query_from_user
        from acne_llm.utils.chunk_filter import (
            drop_noisy_chunks, drop_query_mismatched_chunks,
        )

        cfg = self.config
        user, _prepared = normalize_query(self.container, sample)
        query = build_retrieval_query_from_user(
            user, clean_text_normalized=user.description
        )
        self._trace["query"] = query

        retriever = self.container.retriever
        if cfg.get("use_mmr_prefilter", True) and hasattr(retriever, "retrieve_with_mmr"):
            retrieval = retriever.retrieve_with_mmr(
                query, top_k=cfg.get("retrieve_top_k", settings.chat_retrieve_top_k),
                rerank_top_k=cfg.get(
                    "retrieve_top_k", settings.chat_retrieve_top_k
                ),
                mode="hybrid", mmr_lambda=cfg.get("mmr_lambda", 0.6),
            )
        else:
            retrieval = retriever.retrieve(
                query,
                top_k=cfg.get("retrieve_top_k", settings.chat_retrieve_top_k),
                mode="hybrid",
            )
        self._trace["retrieved_ids"] = [c.chunk_id for c in retrieval.chunks]

        if self.container.reranker is not None:
            retrieval = self.container.reranker.rerank(
                query, retrieval, top_k=cfg.get("rerank_top_k", 3)
            )
        filtered = drop_query_mismatched_chunks(
            drop_noisy_chunks(retrieval, min_score=0.0), query
        )
        if filtered is not None and filtered.chunks:
            retrieval = filtered
        chunks = retrieval.chunks[: cfg.get("rerank_top_k", 3)]
        self._trace["final_ids"] = [c.chunk_id for c in chunks]
        self._trace["context_chunks"] = [
            {"chunk_id": c.chunk_id, "text": (c.text or "")[:1500]} for c in chunks
        ]
        return {"query": query, "chunks": chunks}

    def generate(self, sample: dict, context: dict | None) -> dict:
        max_chars = self.config.get("max_snippet_chars", 700)
        chunks = (context or {}).get("chunks") or []
        if not chunks:
            answer = ("Không tìm thấy tài liệu phù hợp trong cơ sở tri thức "
                      "cho câu hỏi này. Bạn nên tham khảo bác sĩ da liễu.")
        else:
            blocks = []
            for i, c in enumerate(chunks, 1):
                meta = c.metadata or {}
                title = meta.get("title") or c.source or c.chunk_id
                snippet = _truncate_snippet(c.text or "", max_chars)
                blocks.append(f"Nguồn {i} — Theo \"{title}\" ({c.source}):\n{snippet}")
            blocks.append("Thông tin trích nguyên văn từ tài liệu tham khảo, "
                          "chỉ mang tính tham khảo, không thay thế bác sĩ da liễu.")
            answer = "\n\n".join(blocks)
        return {
            "answer": answer,
            "structured": None,
            "used_chunks": [c.chunk_id for c in chunks],
            "model_name": "extractive",
        }
