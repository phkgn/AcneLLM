"""Build sparse-retrieval suggestions for manual eval labeling."""
from __future__ import annotations


def build_label_suggestions(query, bm25, store, top_k: int = 8, max_chars: int = 500):
    suggestions = []
    for chunk_id, score in bm25.query(query, top_k=top_k):
        raw = store.get_by_id(chunk_id) or {}
        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []
        metadata = metadatas[0] if metadatas else {}
        suggestions.append({
            "chunk_id": chunk_id,
            "score": float(score),
            "snippet": str(documents[0] if documents else "")[:max_chars],
            "source": metadata.get("source", ""),
            "title": metadata.get("title", ""),
            "url": metadata.get("url", ""),
            "trust": metadata.get("trust", ""),
        })
    return suggestions
