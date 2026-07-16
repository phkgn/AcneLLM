"""T2 — Retrieval eval trên qrels (graded 0-2) + ablation modes (A2-A5 blueprint).

Modes: sparse | dense | hybrid | hybrid_rerank | hybrid_mmr_rerank (production).
Query construction: production (build_retrieval_query_from_user) hoặc --raw-query (A4).

Usage:
    python -m evaluation.runners.run_retrieval \
        --dataset evaluation/datasets/v1/d8_qrels_seed.jsonl \
        [--modes sparse,dense,hybrid,hybrid_rerank,hybrid_mmr_rerank] \
        [--raw-query] [--top-k 10] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, REPORTS_DIR, build_run_meta, utcnow, write_jsonl  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.retrieval import duplicate_rate, evaluate_query  # noqa: E402
from evaluation.adapters._repo import build_eval_container, normalize_query  # noqa: E402

ALL_MODES = ["sparse", "dense", "hybrid", "hybrid_rerank", "hybrid_mmr_rerank"]


def retrieve_ids(container, mode: str, query: str, top_k: int) -> tuple[list[str], list[str], int]:
    """Trả (ids, texts, latency_ms) theo mode ablation."""
    retriever = container.retriever
    t0 = time.perf_counter()
    if mode in ("sparse", "dense", "hybrid"):
        result = retriever.retrieve(query, top_k=top_k, mode=mode)
    elif mode == "hybrid_rerank":
        result = retriever.retrieve(query, top_k=max(top_k, 15), mode="hybrid")
        if container.reranker is not None:
            result = container.reranker.rerank(query, result, top_k=top_k)
    elif mode == "hybrid_mmr_rerank":  # production path
        if hasattr(retriever, "retrieve_with_mmr"):
            result = retriever.retrieve_with_mmr(
                query, top_k=max(top_k, 15), rerank_top_k=max(top_k, 15),
                mode="hybrid", mmr_lambda=0.6,
            )
        else:
            result = retriever.retrieve(query, top_k=max(top_k, 15), mode="hybrid")
        if container.reranker is not None:
            result = container.reranker.rerank(query, result, top_k=top_k)
    else:
        raise ValueError(mode)
    ms = int((time.perf_counter() - t0) * 1000)
    chunks = result.chunks[:top_k]
    return [c.chunk_id for c in chunks], [c.text or "" for c in chunks], ms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evaluation/datasets/v1/d8_qrels_seed.jsonl")
    ap.add_argument("--modes", default=",".join(ALL_MODES))
    ap.add_argument("--raw-query", action="store_true",
                    help="A4 ablation: dùng raw text thay vì constructed query")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    samples = load_dataset(ROOT / args.dataset)[: args.limit]
    samples = [s for s in samples if s.get("relevance_grade")]
    if not samples:
        raise SystemExit("Dataset không có relevance_grade — cần qrels")
    needs_relabel = sum(1 for s in samples if s.get("annotation_status") == "needs_relabel")
    if needs_relabel:
        print(f"⚠ {needs_relabel}/{len(samples)} qrels đang needs_relabel (bm25-biased, R2) "
              "— kết quả CHỈ dùng tham khảo, không dùng cho báo cáo chính.")

    container = build_eval_container(model=None, sampling=None)
    if not container.rag_ready:
        raise SystemExit("KB chưa sẵn sàng (chroma_db + bm25_index.pkl)")

    from acne_llm.utils.retrieval_query import build_retrieval_query_from_user

    out_dir = REPORTS_DIR / "retrieval" / utcnow()[:19].replace(":", "")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"generated_at": utcnow(), "dataset": args.dataset,
                     "raw_query": args.raw_query, "n_queries": len(samples),
                     "needs_relabel": needs_relabel, "modes": {}}

    # Warm-up: load reranker/embedder TRƯỚC khi đo — tránh cold-load lẫn vào latency
    # (smoke run: hybrid_rerank 13.3s vs hybrid_mmr_rerank 332ms chỉ vì mode đầu chịu load)
    try:
        retrieve_ids(container, "hybrid_rerank", "mụn viêm ở cằm", 3)
    except Exception:
        pass

    for mode in args.modes.split(","):
        per_query, latencies = [], []
        for s in samples:
            if args.raw_query:
                query = s["user_query"]
            else:
                user, _ = normalize_query(container, s)
                query = build_retrieval_query_from_user(
                    user, clean_text_normalized=user.description)
            grades = {str(k): int(v) for k, v in s["relevance_grade"].items()}
            ids, texts, ms = retrieve_ids(container, mode, query, args.top_k)
            m = evaluate_query(ids, grades)
            m["dup_rate"] = duplicate_rate(texts[:5])
            per_query.append({"sample_id": s["sample_id"], "query_used": query[:200],
                              "retrieved": ids, **m})
            latencies.append(ms)
        agg = {k: round(mean(r[k] for r in per_query), 4)
               for k in per_query[0] if isinstance(per_query[0][k], (int, float))}
        agg["latency_ms_mean"] = int(mean(latencies))
        summary["modes"][mode] = agg
        write_jsonl(out_dir / f"{mode}.per_query.jsonl", per_query)
        print(f"[{mode}] " + " ".join(
            f"{k}={agg[k]}" for k in ("hit@3", "hit@5", "mrr@10", "ndcg@5",
                                      "irrelevant@5", "latency_ms_mean") if k in agg))

    summary["run_meta"] = build_run_meta()
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out_dir}")


if __name__ == "__main__":
    main()
