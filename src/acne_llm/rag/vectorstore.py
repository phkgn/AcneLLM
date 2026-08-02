"""Chroma vector store wrapper."""
from __future__ import annotations
from pathlib import Path
from ..schemas.kb import KBChunk, infer_source_type


class ChromaStore:
    def __init__(self, persist_dir: str = "./data/chroma_db",
                 collection: str = "acne_kb_vi"):
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=collection,
            embedding_function=None,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        chunks: list[KBChunk],
        embeddings: list[list[float]],
        batch_size: int = 512,
    ) -> None:
        if not chunks:
            return
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        batch_size = max(1, int(batch_size or 512))
        for start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[start:start + batch_size]
            batch_embeddings = embeddings[start:start + batch_size]
            self.col.upsert(
                ids=[c.chunk_id for c in batch_chunks],
                embeddings=batch_embeddings,
                documents=[c.text for c in batch_chunks],
                metadatas=[
                    {
                        "doc_id":       c.doc_id,
                        "title":        c.title,
                        "url":          str(c.url),
                        "source":       c.source_name,
                        "source_type":  c.source_type if c.source_type != "unknown" else infer_source_type(
                            source_name=c.source_name,
                            url=str(c.url),
                            tags=c.tags,
                            categories=c.categories,
                        ),
                        "trust":        c.trust_level,   # fallback cho chunks cũ
                        "lang":         c.language,
                        "categories":   ",".join(c.categories),
                        "tags":         ",".join(c.tags),
                        "position":     c.position,
                        "prev_chunk_id": c.prev_chunk_id or "",
                        "next_chunk_id": c.next_chunk_id or "",
                    }
                    for c in batch_chunks
                ],
            )

    def count(self) -> int:
        return self.col.count()

    def query(self, query_embedding, top_k: int = 20, filters: dict | None = None,
              include_distances: bool = True):
        try:
            import numpy as np
            embedding = np.asarray(query_embedding, dtype=float).reshape(-1).tolist()
        except Exception:
            embedding = [float(x) for x in query_embedding]
        # Chroma throws nếu n_results > collection count
        n = min(top_k, max(self.col.count(), 1))
        include = (
            ["documents", "metadatas", "distances"]
            if include_distances
            else ["documents", "metadatas"]
        )
        return self.col.query(
            query_embeddings=[embedding],
            n_results=n,
            where=filters or None,
            include=include,
        )

    def query_with_score_filter(
        self,
        query_embedding,
        top_k: int = 20,
        max_distance: float = 0.65,
        filters: dict | None = None,
        fallback_to_raw: bool = True,
    ):
        """Retrieve rồi lọc ngay các chunk có cosine distance > max_distance.

        Chroma trả distance (lower = more similar) với hnsw:space=cosine.
        distance = 1 - cosine_similarity → distance < 0.65 ≈ similarity > 0.35.
        """
        raw = self.query(query_embedding, top_k=top_k, filters=filters)
        ids_l = raw.get("ids") or [[]]
        docs_l = raw.get("documents") or [[]]
        metas_l = raw.get("metadatas") or [[]]
        dists_l = raw.get("distances") or [[]]

        ids = ids_l[0] if ids_l else []
        docs = docs_l[0] if docs_l else []
        metas = metas_l[0] if metas_l else []
        dists = dists_l[0] if dists_l else []

        filtered = [
            (cid, doc, meta, dist)
            for cid, doc, meta, dist in zip(ids, docs, metas, dists)
            if float(dist) <= max_distance
        ]
        # Optional fallback for callers that prefer recall over precision.
        # Chat retrieval disables this so a bad dense match cannot bypass the
        # distance gate and later appear as an irrelevant source.
        if not filtered and fallback_to_raw:
            return raw
        if not filtered:
            return {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }

        f_ids, f_docs, f_metas, f_dists = zip(*filtered)
        return {
            "ids": [list(f_ids)],
            "documents": [list(f_docs)],
            "metadatas": [list(f_metas)],
            "distances": [list(f_dists)],
        }

    def get_by_id(self, chunk_id: str):
        return self.col.get(ids=[chunk_id])


    def get_by_ids(self, chunk_ids: list[str]) -> dict:
        """Fetch nhiều chunks theo list IDs."""
        if not chunk_ids:
            return {"ids": [], "documents": [], "metadatas": []}
        return self.col.get(
            ids=chunk_ids,
            include=["documents", "metadatas"],
        )
