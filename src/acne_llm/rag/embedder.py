"""Embedding wrapper. Eager-load model at startup for fast inference."""
from __future__ import annotations
import numpy as np
from loguru import logger


def _normalize_device(device: str) -> str:
    requested = (device or "cpu").strip().lower()
    if requested == "gpu":
        requested = "cuda"
    if requested == "cuda":
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        logger.warning("CUDA/GPU requested but unavailable; falling back to CPU")
        return "cpu"
    return requested


class Embedder:
    def __init__(self, model_name: str = "AITeamVN/Vietnamese_Embedding",
                 device: str = "cpu", batch_size: int = 32,
                 lazy: bool = False):
        self.model_name = model_name
        self.device = _normalize_device(device)
        self.batch_size = batch_size
        self._model = None
        self.dim: int = 1024  # default for BGE-M3

        if not lazy:
            self._load()  # eager load at startup

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedder: {self.model_name} on {self.device}")
            self._model = SentenceTransformer(self.model_name, device=self.device)
            if hasattr(self._model, "get_embedding_dimension"):
                self.dim = self._model.get_embedding_dimension()
            else:
                self.dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"Embedder ready (dim={self.dim})")
        return self._model

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        """Embed list of passages -- no cache, dung khi build KB."""
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        m = self._load()
        return m.encode(
            texts, batch_size=self.batch_size,
            normalize_embeddings=True, show_progress_bar=True,
            convert_to_numpy=True,
        )

    def embed_query(self, query: str) -> np.ndarray:
        """Embed single query voi cache (cache miss -> compute -> store)."""
        from ..cache import cached_embed_query
        return cached_embed_query(self, query)

    def _embed_query_raw(self, query: str) -> np.ndarray:
        """Internal: compute embedding truc tiep, khong qua cache (tranh de quy)."""
        m = self._load()
        return m.encode(
            [query], normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )[0]
