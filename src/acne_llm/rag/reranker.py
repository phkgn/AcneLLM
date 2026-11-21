"""Cross-encoder reranker (bge-reranker-v2-m3) voi score threshold va normalization."""
from __future__ import annotations
from collections import OrderedDict

from loguru import logger
from ..schemas import RetrievedChunk, RetrievalOutput

_RERANK_MIN_SIGMOID: float = 0.30


class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3",
                 device: str = "cpu", max_length: int = 512,
                 lazy: bool = False, batch_size: int = 16,
                 cache_size: int = 2048,
                 min_sigmoid_score: float = _RERANK_MIN_SIGMOID):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self.cache_size = cache_size
        self.min_sigmoid_score = min_sigmoid_score
        self._score_cache: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._model = None

        if not lazy:
            self._load()

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {self.model_name} on {self.device}")
            self._model = CrossEncoder(self.model_name, device=self.device,
                                       max_length=self.max_length)
            logger.info("Reranker ready")
        return self._model

    def _cache_get(self, key: tuple[str, str]) -> float | None:
        if self.cache_size <= 0:
            return None
        if key not in self._score_cache:
            return None
        score = self._score_cache.pop(key)
        self._score_cache[key] = score
        return score

    def _cache_put(self, key: tuple[str, str], score: float) -> None:
        if self.cache_size <= 0:
            return
        self._score_cache[key] = score
        self._score_cache.move_to_end(key)
        while len(self._score_cache) > self.cache_size:
            self._score_cache.popitem(last=False)

    def rerank(self, query: str, retrieval: RetrievalOutput,
               top_k: int = 5) -> RetrievalOutput:
        if not retrieval.chunks:
            return retrieval

        scores_by_id: dict[str, float] = {}
        missing_chunks: list[RetrievedChunk] = []

        for chunk in retrieval.chunks:
            key = (query, chunk.chunk_id)
            cached = self._cache_get(key)
            if cached is None:
                missing_chunks.append(chunk)
            else:
                scores_by_id[chunk.chunk_id] = cached

        if missing_chunks:
            m = self._load()
            pairs = [(query, c.text) for c in missing_chunks]
            raw_scores = m.predict(
                pairs,
                show_progress_bar=False,
                batch_size=self.batch_size,
            )
            for chunk, raw_score in zip(missing_chunks, raw_scores):
                value = float(raw_score)
                scores_by_id[chunk.chunk_id] = value
                self._cache_put((query, chunk.chunk_id), value)

        # KHONG sigmoid lai. CrossEncoder.predict() cua sentence-transformers DA
        # ap nn.Sigmoid() san khi num_labels=1 (xem cross_encoder/model.py:110)
        # -- bge-reranker-v2-m3 dung num_labels=1. Gia tri tra ve la XAC SUAT [0,1].
        #
        # Bug cu: ap sigmoid lan hai -> moi diem bi nen vao [0.500, 0.731] vi
        # sigmoid([0,1]) = [0.5, 0.731]. Quan sat thuc te: 20 chunk deu nam trong
        # 0.718-0.731, bien do 0.003 -> reranker MAT HET kha nang phan biet, thu tu
        # cuoi cung do nhieu quyet dinh. Xac suat that la 0.974 vs 0.999.
        # Cac nguong 0.30/0.45/0.58 truoc day deu duoc chinh theo dai bi nen nay.
        sigmoid_scores = dict(scores_by_id)

        # Log xac suat + BIEN DO. Bien do la thu can theo doi: gan 0 nghia la
        # reranker khong phan biet duoc gi va thu tu cuoi cung chi la nhieu.
        _summary = sorted(scores_by_id.values(), reverse=True)
        _spread = (_summary[0] - _summary[-1]) if len(_summary) > 1 else 0.0
        logger.debug(
            "[reranker] prob(top5): {} | min={:.4f} max={:.4f} spread={:.4f}",
            [round(x, 4) for x in _summary[:5]],
            _summary[-1], _summary[0], _spread,
        )

        all_pairs = sorted(
            [(c, sigmoid_scores[c.chunk_id]) for c in retrieval.chunks],
            key=lambda x: x[1],
            reverse=True,
        )

        top_pairs = all_pairs[:top_k]

        passed = [(c, s) for c, s in top_pairs if s >= self.min_sigmoid_score]
        dropped = len(top_pairs) - len(passed)
        if not passed:
            logger.debug(
                f"[reranker] Khong co chunk nao qua threshold sigmoid>={self.min_sigmoid_score:.2f} "
                f"-> tra empty, LLM se bao thieu thong tin"
            )
        elif dropped > 0:
            logger.debug(f"[reranker] loai {dropped} chunk duoi threshold sigmoid<{self.min_sigmoid_score:.2f}")

        new_chunks = [
            RetrievedChunk(
                chunk_id=c.chunk_id, source=c.source, text=c.text,
                score=float(s), metadata=c.metadata,
            ) for c, s in passed
        ]
        avg = sum(c.score for c in new_chunks) / len(new_chunks) if new_chunks else 0.0
        logger.debug(
            f"[reranker] {len(retrieval.chunks)} -> {len(new_chunks)} chunks "
            f"| avg_sigmoid={avg:.3f}"
        )
        if new_chunks:
            _chunk_summary = [
                (c.metadata.get("source", c.source or "?")[:35], round(c.score, 3))
                for c in new_chunks
            ]
            logger.debug("[reranker] top chunks: {}", _chunk_summary)
        # Log CA POOL kem source_type: can biet chunk guideline roi o dau moi quyet
        # dinh duoc cach ap boost tham quyen (pha hoa hay nhan he so).
        # Chi top-5 thi khong thay guideline vi chung nam duoi -- dung cho mu.
        logger.debug(
            "[reranker] ca pool: {}",
            [
                (
                    (c.metadata or {}).get("source_type", "?"),
                    (c.metadata or {}).get("source", c.source or "?")[:22],
                    round(s, 3),
                )
                for c, s in all_pairs
            ],
        )
        return RetrievalOutput(
            query=retrieval.query,
            chunks=new_chunks,
            retrieval_mode="rerank",
            num_chunks=len(new_chunks),
            avg_score=avg,
        )
