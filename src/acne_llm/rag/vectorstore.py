"""Chroma vector store wrapper."""
from __future__ import annotations
from pathlib import Path
from ..schemas.kb import KBChunk


class ChromaStore:
    def __init__(self, persist_dir: str = "./data/chroma_db",
                 collection: str = "acne_kb_vi"):
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        # embedding_function=None: project tu embed bang sentence-transformers,
        # khong de chromadb load onnxruntime default (tranh DLL error tren Windows)
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=collection,
            embedding_function=None,  # embeddings duoc inject truc tiep khi upsert/query
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[KBChunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self.col.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "url": str(c.url),
                    "source": c.source_name,
                    "trust": c.trust_level,
                    "lang": c.language,
                    "categories": ",".join(c.categories),
                    "tags": ",".join(c.tags),
                    "position": c.position,
                    # Luu linked-list de context expansion dung sau rerank
                    "prev_chunk_id": c.prev_chunk_id or "",
                    "next_chunk_id": c.next_chunk_id or "",
                }
                for c in chunks
            ],
        )

    def count(self) -> int:
        return self.col.count()

    def query(self, query_embedding, top_k: int = 20, filters: dict | None = None):
        try:
            import numpy as np
            embedding = np.asarray(query_embedding, dtype=float).reshape(-1).tolist()
        except Exception:
            embedding = [float(x) for x in query_embedding]
        return self.col.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=filters or None,
        )

    def get_by_id(self, chunk_id: str):
        return self.col.get(ids=[chunk_id])
