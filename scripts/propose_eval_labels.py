"""Generate candidate labels for eval queries.

This script does not assign ground-truth labels automatically. It enriches each
query with sparse retrieval suggestions so a human can review and populate
`relevant_chunk_ids` in the benchmark file.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from acne_llm.rag.sparse import BM25Index
from acne_llm.rag.vectorstore import ChromaStore
from config.settings import settings

app = typer.Typer()


def _load_queries(path: str) -> list[dict]:
    items: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def _fetch_chunk_preview(store: ChromaStore, chunk_id: str, max_chars: int = 180) -> dict:
    got = store.get_by_id(chunk_id)
    docs = got.get("documents") or []
    metas = got.get("metadatas") or []
    text = docs[0] if docs else ""
    meta = metas[0] if metas else {}
    return {
        "chunk_id": chunk_id,
        "source": meta.get("source", ""),
        "title": meta.get("title", ""),
        "url": meta.get("url", ""),
        "trust": meta.get("trust", meta.get("trust_level", "")),
        "score": 0.0,
        "snippet": text[:max_chars] + ("…" if len(text) > max_chars else ""),
    }


def build_label_suggestions(
    query: str,
    bm25: BM25Index,
    store: ChromaStore,
    top_k: int = 8,
    max_chars: int = 180,
) -> list[dict]:
    hits = bm25.query(query, top_k=top_k)
    suggestions: list[dict] = []
    for chunk_id, score in hits:
        preview = _fetch_chunk_preview(store, chunk_id, max_chars=max_chars)
        preview["score"] = round(float(score), 4)
        suggestions.append(preview)
    return suggestions


@app.command()
def run(
    queries: str = "data/sample_queries.jsonl",
    out: str = "data/eval_labels/suggested_eval_queries.jsonl",
    top_k: int = 8,
    max_chars: int = 180,
):
    q_path = Path(queries)
    if not q_path.exists():
        logger.error(f"queries not found: {queries}")
        raise typer.Exit(1)

    bm25_path = Path(settings.bm25_path)
    chroma_dir = Path(settings.chroma_dir)
    if not bm25_path.exists():
        raise RuntimeError(f"BM25 index not found: {bm25_path}")
    if not chroma_dir.exists():
        raise RuntimeError(f"ChromaDB directory not found: {chroma_dir}")

    queries_data = _load_queries(queries)
    bm25 = BM25Index.load(str(bm25_path))
    store = ChromaStore(persist_dir=str(chroma_dir))

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_hits = 0
    zero_hit_cases = 0
    source_counts: Counter[str] = Counter()

    with open(out_path, "w", encoding="utf-8") as f:
        for item in queries_data:
            query = item["query"]
            suggestions = build_label_suggestions(
                query=query,
                bm25=bm25,
                store=store,
                top_k=top_k,
                max_chars=max_chars,
            )
            suggested_ids = [s["chunk_id"] for s in suggestions]
            if not suggested_ids:
                zero_hit_cases += 1
            total_hits += len(suggested_ids)
            for s in suggestions:
                source_counts[s.get("source", "")] += 1

            record = {
                **item,
                "suggested_relevant_chunk_ids": suggested_ids,
                "label_candidates": suggestions,
                "labeling": {
                    "suggestion_mode": "bm25",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = (
        f"# Eval label suggestions\n\n"
        f"- Queries: {len(queries_data)}\n"
        f"- Top-k suggestions per query: {top_k}\n"
        f"- Total suggested hits: {total_hits}\n"
        f"- Zero-hit queries: {zero_hit_cases}\n"
        f"- Top sources: {', '.join(f'{k}:{v}' for k, v in source_counts.most_common(8)) or 'none'}\n"
        f"- Output: {out_path}\n"
    )
    summary_path = out_path.with_suffix(".md")
    summary_path.write_text(summary, encoding="utf-8")
    logger.success(f"✅ Suggestions written to {out_path}")


if __name__ == "__main__":
    app()
