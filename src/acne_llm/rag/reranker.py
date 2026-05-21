"""Cross-encoder reranker (bge-reranker-v2-m3)."""
from __future__ import annotations
from loguru import logger
from ..schemas import RetrievedChunk, RetrievalOutput


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3",
                 device: str = "cpu", max_length: int = 512,
                 lazy: bool = False):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self._model = None

        if not lazy:
            self._load()  # eager load at startup

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {self.model_name} on {self.device}")
            self._model = CrossEncoder(self.model_name, device=self.device,
                                       max_length=self.max_length)
            logger.info("Reranker ready")
        return self._model

    def rerank(self, query: str, retrieval: RetrievalOutput,
               top_k: int = 5) -> RetrievalOutput:
        if not retrieval.chunks:
            return retrieval
        m = self._load()
        pairs = [(query, c.text) for c in retrieval.chunks]
        scores = m.predict(pairs, show_progress_bar=False)
        ranked = sorted(zip(retrieval.chunks, scores), key=lambda x: float(x[1]),
                        reverse=True)[:top_k]
        new_chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id, source=c.source, text=c.text,
                score=float(s), metadata=c.metadata,
            ) for c, s in ranked
        ]
        avg = sum(c.score for c in new_chunks) / len(new_chunks) if new_chunks else 0.0
        return RetrievalOutput(
            query=query, chunks=new_chunks, retrieval_mode="rerank",
            num_chunks=len(new_chunks), avg_score=avg,
        )
