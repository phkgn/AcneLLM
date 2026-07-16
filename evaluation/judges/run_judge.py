"""Chấm điểm results bằng LLM judge (blind, cached, cost-tracked).

Pointwise + faithfulness (claim extract → entailment với context) cho mọi record;
pairwise 2 chiều (swap) cho các cặp pre-registered trong experiment config.

Usage:
    python -m evaluation.judges.run_judge --run-dir evaluation/reports/main_2x2_t3 \
        --dataset evaluation/datasets/v1/d2_test.jsonl \
        [--provider deepseek] [--pairs s0:s1,s2:s3] [--limit 50]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, append_jsonl, read_jsonl  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.judges.clients import JudgeClient, load_prompt  # noqa: E402

POINTWISE_AXES = ["correctness", "completeness", "safety", "relevance",
                  "fluency", "instruction_following"]


def _context_text(record: dict) -> str:
    """Ghép context THẬT từ trace: ưu tiên context_chunks (adapter lưu text đầy đủ),
    fallback citations snippet (SSE). Nếu chỉ có id không text → trả '(không có)' để
    judge KHÔNG chấm faithfulness trên placeholder (tránh not_found giả)."""
    trace = record.get("trace") or {}
    parts = [f"[{c['chunk_id']}] {c['text']}"
             for c in trace.get("context_chunks") or [] if c.get("text")]
    if not parts:
        parts = [f"[{c.get('chunk_id', '?')}] {c.get('snippet') or c.get('text', '')}"
                 for c in trace.get("citations") or []
                 if c.get("snippet") or c.get("text")]
    return "\n\n".join(parts) or "(không có tài liệu)"


def build_pointwise_prompt(record: dict, sample: dict) -> str:
    return load_prompt(
        "pointwise",
        question=sample["user_query"],
        user_context=json.dumps(sample.get("user_context") or {}, ensure_ascii=False),
        context=_context_text(record),
        expected_points="\n".join(f"- {p}" for p in sample.get("expected_answer_points") or []) or "(không có)",
        forbidden_claims="\n".join(f"- {c}" for c in sample.get("forbidden_claims") or []) or "(không có)",
        answer=record.get("answer") or "(rỗng)",
    )


def judge_pointwise(client: JudgeClient, record: dict, sample: dict) -> dict | None:
    return client.judge(build_pointwise_prompt(record, sample))


def judge_error_class(client: JudgeClient, record: dict, sample: dict) -> dict | None:
    """Error classifier (§10) — chỉ gọi cho record bị điểm kém."""
    prompt = load_prompt(
        "error_classify",
        question=sample["user_query"],
        expected_behavior=sample.get("expected_behavior") or "(không có)",
        context=_context_text(record),
        answer=record.get("answer") or "(rỗng)",
    )
    return client.judge(prompt)


def judge_faithfulness(client: JudgeClient, record: dict) -> dict | None:
    """Faithfulness = supported / total claims (RAGAS-style). Chỉ cho hệ có context."""
    context = _context_text(record)
    if context.startswith("(không"):
        return None
    extraction = client.judge(load_prompt("claim_extract", answer=record.get("answer") or ""))
    claims = (extraction or {}).get("claims") or []
    if not claims:
        return None
    verdicts = []
    for claim in claims:
        v = client.judge(load_prompt("entailment", context=context, claim=claim["text"]))
        verdicts.append({**claim, "verdict": (v or {}).get("verdict", "invalid")})
    supported = sum(1 for v in verdicts if v["verdict"] == "supported")
    contradicted = sum(1 for v in verdicts if v["verdict"] == "contradicted")
    return {
        "n_claims": len(verdicts),
        "faithfulness": round(supported / len(verdicts), 4),
        "contradiction_rate": round(contradicted / len(verdicts), 4),
        "claims": verdicts,
    }


def judge_pair(client: JudgeClient, rec_a: dict, rec_b: dict, sample: dict,
               rng: random.Random) -> dict:
    """Pairwise 2 chiều swap (Wang et al. 2024): mâu thuẫn → tie."""
    def one(a: dict, b: dict) -> str:
        res = client.judge(load_prompt(
            "pairwise",
            question=sample["user_query"],
            user_context=json.dumps(sample.get("user_context") or {}, ensure_ascii=False),
            expected_points="\n".join(sample.get("expected_answer_points") or []) or "(không có)",
            answer_a=a.get("answer") or "(rỗng)",
            answer_b=b.get("answer") or "(rỗng)",
        ))
        return (res or {}).get("winner", "invalid")
    w1 = one(rec_a, rec_b)                       # A=hệ 1, B=hệ 2
    w2 = one(rec_b, rec_a)                       # swap
    w2_mapped = {"A": "B", "B": "A"}.get(w2, w2)
    verdict = w1 if w1 == w2_mapped and w1 in ("A", "B") else "tie"
    return {"forward": w1, "backward": w2, "verdict": verdict}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--provider", default="deepseek", choices=["deepseek", "openai"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--pairs", default=None, help="vd: s0:s1,s1:s3")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-faithfulness", action="store_true")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    samples = {s["sample_id"]: s for s in load_dataset(ROOT / args.dataset)}
    client = JudgeClient(args.provider, args.model)
    rng = random.Random(42)

    results = {p.stem.replace(".results", ""): read_jsonl(p)
               for p in sorted(run_dir.glob("*.results.jsonl"))}

    # Pointwise + faithfulness
    for system_id, records in results.items():
        out_path = run_dir / f"{system_id}.judged.jsonl"
        done = {r["sample_id"] for r in read_jsonl(out_path)} if out_path.exists() else set()
        for rec in records[: args.limit]:
            if rec["sample_id"] in done or not rec.get("ok"):
                continue
            sample = samples.get(rec["sample_id"])
            if sample is None:
                continue
            pointwise = judge_pointwise(client, rec, sample)
            row = {"sample_id": rec["sample_id"], "system_id": system_id,
                   "judge_model": client.model,
                   "pointwise": pointwise,
                   "judge_status": "valid" if pointwise is not None else "invalid"}
            if pointwise is None:
                row["judge_error"] = "pointwise_parse_failure"
            if not args.skip_faithfulness and rec.get("used_chunks"):
                row["faithfulness"] = judge_faithfulness(client, rec)
            pw = row["pointwise"] or {}
            if any(isinstance(pw.get(a), (int, float)) and pw[a] <= 2
                   for a in ("correctness", "safety")):
                row["error_class"] = judge_error_class(client, rec, sample)
            append_jsonl(out_path, row)
        print(f"[{system_id}] judged -> {out_path} | cost=${client.total_cost_usd:.3f}")

    # Pairwise pre-registered
    if args.pairs:
        for pair in args.pairs.split(","):
            a, b = pair.split(":")
            out_path = run_dir / f"pairwise_{a}_vs_{b}.jsonl"
            done = ({r["sample_id"] for r in read_jsonl(out_path)}
                    if out_path.exists() else set())
            recs_a = {r["sample_id"]: r for r in results.get(a, []) if r.get("ok")}
            recs_b = {r["sample_id"]: r for r in results.get(b, []) if r.get("ok")}
            for sid in list(recs_a.keys() & recs_b.keys())[: args.limit]:
                if sid in done:
                    continue
                verdict = judge_pair(client, recs_a[sid], recs_b[sid],
                                     samples[sid], rng)
                append_jsonl(out_path, {"sample_id": sid, "pair": [a, b], **verdict})
            print(f"[{a} vs {b}] -> {out_path}")

    print(f"\nTổng judge calls: {client.calls} | cost ước tính: ${client.total_cost_usd:.2f}")


if __name__ == "__main__":
    main()
