"""Audit hybrid retrieval fused-score distribution on sample queries.

Usage:
    $env:PYTHONPATH="src"; python scripts/audit_rag_fusion.py --queries data/sample_queries.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from acne_llm.config import settings
from acne_llm.di import build_container


def _read_queries(path: Path, limit: int) -> list[str]:
    queries: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if limit and len(queries) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                queries.append(line)
                continue
            query = obj.get("query") or obj.get("question") or obj.get("message") or obj.get("text")
            if query:
                queries.append(str(query))
    return queries


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * p)))
    return sorted(values)[idx]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default="data/sample_queries.jsonl")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    queries = _read_queries(Path(args.queries), args.limit)
    container = build_container(settings)
    if container.retriever is None:
        raise SystemExit("RAG is not ready; build/load KB before running audit.")

    scores: list[float] = []
    empty = 0
    for query in queries:
        out = container.retriever.retrieve(query, top_k=args.top_k, mode="hybrid")
        if not out.chunks:
            empty += 1
            continue
        scores.extend(float(chunk.score) for chunk in out.chunks)

    print(json.dumps({
        "queries": len(queries),
        "empty_queries": empty,
        "scores": len(scores),
        "min": min(scores) if scores else 0.0,
        "p10": _pct(scores, 0.10),
        "p50": statistics.median(scores) if scores else 0.0,
        "p90": _pct(scores, 0.90),
        "max": max(scores) if scores else 0.0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
