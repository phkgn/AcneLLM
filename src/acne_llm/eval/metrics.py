"""Retrieval metrics: Recall@k, MRR@k, NDCG@k."""
from __future__ import annotations
import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    topk = retrieved[:k]
    return len(set(topk) & relevant) / len(relevant)


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for i, cid in enumerate(retrieved[:k], 1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    dcg = 0.0
    for i, cid in enumerate(retrieved[:k], 1):
        if cid in relevant:
            dcg += 1.0 / math.log2(i + 1)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / idcg if idcg > 0 else 0.0


def aggregate(scores: list[float]) -> dict:
    if not scores:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    return {
        "mean": round(sum(scores) / len(scores), 4),
        "min": round(min(scores), 4),
        "max": round(max(scores), 4),
        "n": len(scores),
    }
