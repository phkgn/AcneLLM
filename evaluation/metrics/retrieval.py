"""Retrieval metrics T2 — binary (recall/hit/precision/MRR/MAP) + graded (nDCG 0-2).

Khác legacy (src/acne_llm/eval/metrics.py — binary only): thêm precision@k, MAP,
graded nDCG, duplicate rate, irrelevant-context rate. Pure functions, unit-tested.
"""
from __future__ import annotations

import math


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def hit_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(retrieved[:k]) & relevant else 0.0


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    topk = retrieved[:k]
    if not topk:
        return 0.0
    return len(set(topk) & relevant) / len(topk)


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for i, cid in enumerate(retrieved[:k], 1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def average_precision(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits, score = 0, 0.0
    for i, cid in enumerate(retrieved[:k], 1):
        if cid in relevant:
            hits += 1
            score += hits / i
    return score / min(len(relevant), k)


def ndcg_at_k_graded(retrieved: list[str], grades: dict[str, int], k: int) -> float:
    """nDCG với graded relevance 0–2 (Järvelin & Kekäläinen 2002), gain = 2^g - 1."""
    def gain(g: int) -> float:
        return (2 ** g) - 1
    dcg = sum(
        gain(grades.get(cid, 0)) / math.log2(i + 1)
        for i, cid in enumerate(retrieved[:k], 1)
    )
    ideal = sorted((g for g in grades.values() if g > 0), reverse=True)[:k]
    idcg = sum(gain(g) / math.log2(i + 1) for i, g in enumerate(ideal, 1))
    return dcg / idcg if idcg > 0 else 0.0


def irrelevant_rate(retrieved: list[str], grades: dict[str, int], k: int) -> float:
    """Tỉ lệ chunk grade-0 trong top-k (context noise)."""
    topk = retrieved[:k]
    if not topk:
        return 0.0
    return sum(1 for cid in topk if grades.get(cid, 0) == 0) / len(topk)


def duplicate_rate(texts: list[str], threshold: float = 0.9) -> float:
    """Near-duplicate theo Jaccard trên word shingles (không cần embedder)."""
    if len(texts) < 2:
        return 0.0
    sets = [set(t.lower().split()) for t in texts]
    dup = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = sets[i] | sets[j]
            if union and len(sets[i] & sets[j]) / len(union) >= threshold:
                dup += 1
                break
    return dup / len(texts)


def evaluate_query(retrieved: list[str], grades: dict[str, int],
                   ks: tuple[int, ...] = (1, 3, 5, 10)) -> dict[str, float]:
    relevant = {cid for cid, g in grades.items() if g > 0}
    out: dict[str, float] = {}
    for k in ks:
        out[f"hit@{k}"] = hit_at_k(retrieved, relevant, k)
        out[f"recall@{k}"] = recall_at_k(retrieved, relevant, k)
        out[f"precision@{k}"] = precision_at_k(retrieved, relevant, k)
        out[f"ndcg@{k}"] = ndcg_at_k_graded(retrieved, grades, k)
    out["mrr@10"] = mrr_at_k(retrieved, relevant, 10)
    out["map@10"] = average_precision(retrieved, relevant, 10)
    out["irrelevant@5"] = irrelevant_rate(retrieved, grades, 5)
    return out
