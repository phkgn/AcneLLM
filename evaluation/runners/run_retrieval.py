#!/usr/bin/env python3
"""Khâu RAG — chấm chất lượng tài liệu retrieval mang về, bằng judge ngữ nghĩa.

Thay cho recall@k trên chunk vàng. Vì sao đổi:

  Chấm theo danh tính chunk là chấm oan. Nhiều đoạn cùng nói một chủ đề; retriever
  mang về đoạn KHÁC nhưng cũng trả lời được thì vẫn bị tính là trượt. Và bộ đề
  sinh theo đường đi ngược có `MAX_RESTATEMENT_COSINE = 0.88` — cố ý loại câu hỏi
  chép lại đoạn văn — nên recall đo được là con số bi quan có hệ thống.

  Judge hỏi thẳng: đoạn này có liên quan không, gộp lại có đủ trả lời không.
  Không cần biết "đoạn đúng" là đoạn nào.

Hệ quả thực dụng: chạy được trên BẤT KỲ tập câu hỏi nào, kể cả câu hỏi thật của
người dùng, vì không đòi hỏi ai phải gán nhãn chunk vàng trước.

Không sinh câu trả lời -> 1 lượt gọi judge mỗi câu, rẻ và nhanh. Judge client có
cache đĩa nên chạy lại gần như miễn phí.

Usage:
    python -m evaluation.runners.run_retrieval
    python -m evaluation.runners.run_retrieval --limit 30
    python -m evaluation.runners.run_retrieval --output evaluation/reports/rag/topk50.json
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import statistics as st
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from evaluation.adapters._repo import normalize_query  # noqa: E402
from evaluation.common import utcnow  # noqa: E402
from evaluation.judges import context as context_judge  # noqa: E402
from evaluation.judges.clients import JudgeClient  # noqa: E402

DEFAULT_DATASET = ROOT / "evaluation/datasets/eval_set.v3.jsonl"
DEFAULT_OUTPUT = ROOT / "evaluation/reports/rag/results.json"
DEFAULT_JUDGE = "gpt-5.4-mini-2026-03-17"


def _fmt(v: Any, pct: bool = False) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:.1%}" if pct else f"{v:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    from acne_llm.config import settings
    from acne_llm.di import build_container
    from acne_llm.chat._retrieval import retrieve_for_chat

    container = build_container(settings)
    if not container.rag_ready:
        raise SystemExit("RAG chưa sẵn sàng — kiểm tra data/chroma_db và bm25_index.pkl")
    judge = JudgeClient(provider="openai", model=args.judge_model)

    rows = [json.loads(l) for l in Path(args.dataset).read_text(encoding="utf-8")
            .splitlines() if l.strip()]
    # Ca reject/clarify test CHÍNH SÁCH, không test kiến thức — không có tài liệu
    # nào "đúng" cho chúng, chấm liên quan là vô nghĩa.
    rows = [r for r in rows if r.get("intent_label") in (None, "advise", "knowledge")]
    if args.limit:
        rows = rows[: args.limit]

    print(f"{len(rows)} câu · judge {args.judge_model} · "
          f"chat_retrieve_top_k={getattr(settings, 'chat_retrieve_top_k', '?')} "
          f"· chat_rerank_top_k={getattr(settings, 'chat_rerank_top_k', '?')}\n")

    records: list[dict[str, Any]] = []
    per_type: dict[str, list[float]] = collections.defaultdict(list)
    no_context = 0
    failed: list[dict[str, Any]] = []
    t0 = time.time()
    for i, sample in enumerate(rows, 1):
        user, _ = normalize_query(container, sample)
        out = retrieve_for_chat(container, user)
        chunks = list(out.chunks) if out else []
        if not chunks:
            no_context += 1

        # Một dòng hỏng KHÔNG được giết cả lượt chạy. Retrieval mất ~14s/câu
        # nên 197 câu là 45 phút; để judge trả JSON dị dạng ở câu 150 mà mất
        # sạch là quá đắt. Dòng hỏng ghi lại kèm lý do, chạy tiếp.
        try:
            scored = context_judge.score(
                judge,
                sample.get("user_query") or "",
                [c.text for c in chunks],
                sample.get("expected_answer_points") or [],
            )
        except Exception as exc:                       # noqa: BLE001
            failed.append({"sample_id": sample.get("sample_id"),
                           "error": f"{type(exc).__name__}: {exc}"})
            scored = {f: None for f in context_judge.FACES} | {"details": None}
        # Điểm từng đoạn gắn với source_type -> biết tầng nguồn nào thật sự dùng được.
        grades = ((scored.get("details") or {}).get("grades") or [])
        for chunk, g in zip(chunks, grades):
            per_type[str((chunk.metadata or {}).get("source_type") or "?")].append(g)

        records.append({
            "sample_id": sample.get("sample_id"),
            "n_chunks": len(chunks),
            "sources": [str((c.metadata or {}).get("source") or "?") for c in chunks],
            "source_types": [str((c.metadata or {}).get("source_type") or "?")
                             for c in chunks],
            **{f: scored.get(f) for f in context_judge.FACES},
            "details": scored.get("details"),
        })
        if not args.quiet:
            print(f"\r  {i}/{len(rows)}  ·  {(time.time() - t0) / i:.1f}s/câu", end="",
                  flush=True)
    print("\n")

    def col(face: str) -> list[float]:
        return [r[face] for r in records
                if isinstance(r.get(face), (int, float))]

    summary = {
        "generated_at": utcnow(),
        "dataset": str(args.dataset),
        "n": len(records),
        "no_context": no_context,
        "failed": failed,
        "judge_model": args.judge_model,
        "settings": {
            k: getattr(settings, k, None) for k in
            ("chat_retrieve_top_k", "chat_rerank_top_k", "chat_rerank_floor",
             "chat_max_context_chars", "embedding_model", "reranker_model")
        },
        "faces": {f: (round(st.mean(col(f)), 4) if col(f) else None)
                  for f in context_judge.FACES},
        "by_source_type": {
            t: {"n": len(v), "điểm_TB": round(st.mean(v), 3),
                "tỉ_lệ_dùng_được": round(
                    sum(1 for x in v if x >= context_judge.RELEVANT_THRESHOLD) / len(v), 3)}
            for t, v in sorted(per_type.items(), key=lambda kv: -len(kv[1]))
        },
        "judge_cost_usd": round(getattr(judge, "total_cost_usd", 0.0), 4),
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "rows": records},
                                   indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'mặt':22}{'điểm':>8}   thang")
    for f in context_judge.FACES:
        v = summary["faces"][f]
        if v is None:
            continue
        scale = "0-1" if f in ("context_precision", "ranking_quality") else "0-5"
        print(f"  {f:20}{_fmt(v):>8}   {scale}")
    print(f"\n  câu KHÔNG có tài liệu nào: {no_context}/{len(records)}")
    if failed:
        print(f"  ⚠ {len(failed)}/{len(records)} câu judge lỗi — KHÔNG tính vào điểm:")
        for f in failed[:5]:
            print(f"     {f['sample_id']}: {f['error'][:70]}")

    print(f"\n{'source_type':20}{'n đoạn':>8}{'điểm TB':>10}{'dùng được (≥3)':>18}")
    for t, s in summary["by_source_type"].items():
        print(f"  {t:18}{s['n']:>8}{s['điểm_TB']:>10.2f}{s['tỉ_lệ_dùng_được']:>17.0%}")

    print(f"\n  chi phí judge: ${summary['judge_cost_usd']:.3f}")
    print(f"  {out_path}")
    print("\n  Đọc: relevance cao mà sufficiency thấp = 'đúng chủ đề, không đủ trả lời'")
    print("  — đó là hình dạng của RAG có mà như không.")


if __name__ == "__main__":
    main()
