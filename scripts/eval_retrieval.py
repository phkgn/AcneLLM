"""Offline retrieval evaluation with deterministic metric reporting."""
from __future__ import annotations

import json
from pathlib import Path

from acne_llm.eval.metrics import aggregate, mrr_at_k, ndcg_at_k, recall_at_k


def _build_retriever(mode: str):
    from acne_llm.config import settings
    from acne_llm.di import build_container

    container = build_container(settings)
    return container.retriever


def _run_eval(
    queries_path: str,
    mode: str = "hybrid",
    top_k: int = 10,
    n: int | None = None,
    verbose: bool = True,
    out: str | None = None,
):
    cases = [
        json.loads(line)
        for line in Path(queries_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if n is not None:
        cases = cases[:n]
    retriever = _build_retriever(mode)
    per_query = []
    skipped = 0
    hit1: list[float] = []
    hit5: list[float] = []
    mrr10: list[float] = []
    ndcg5: list[float] = []
    for case in cases:
        relevant = {str(x) for x in case.get("relevant_chunk_ids", []) if str(x).strip()}
        if not relevant:
            skipped += 1
            continue
        result = retriever.retrieve(str(case.get("query", "")), top_k=top_k, mode=mode)
        ids = [chunk.chunk_id for chunk in result.chunks]
        row = {
            "query": case.get("query", ""),
            "retrieved_chunk_ids": ids,
            "relevant_chunk_ids": sorted(relevant),
            "hit@1": recall_at_k(ids, relevant, 1),
            "hit@5": recall_at_k(ids, relevant, 5),
            "mrr@10": mrr_at_k(ids, relevant, 10),
            "ndcg@5": ndcg_at_k(ids, relevant, 5),
        }
        per_query.append(row)
        hit1.append(row["hit@1"])
        hit5.append(row["hit@5"])
        mrr10.append(row["mrr@10"])
        ndcg5.append(row["ndcg@5"])
    summary = {
        "evaluated": len(per_query),
        "skipped_no_gt": skipped,
        "hit@1": aggregate(hit1)["mean"],
        "hit@5": aggregate(hit5)["mean"],
        "mrr@10": aggregate(mrr10)["mean"],
        "ndcg@5": aggregate(ndcg5)["mean"],
    }
    summary["all_targets_met"] = (
        summary["hit@1"] >= 0.5
        and summary["hit@5"] >= 0.8
        and summary["mrr@10"] >= 0.5
        and summary["ndcg@5"] >= 0.5
    )
    report = {"summary": summary, "per_query": per_query}
    if out:
        Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
