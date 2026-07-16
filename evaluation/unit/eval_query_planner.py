"""T1 — Query planner / query construction eval (property-based, không cần gold).

Kiểm tra bất biến của ClinicalQueryPlanner (rule-based) + build_retrieval_query_from_user:
  P1 query_vi không rỗng
  P2 lesion trong UserInput → xuất hiện trong query (mapping term hoặc raw)
  P3 distribution trong UserInput → xuất hiện trong query
  P4 red_flags/is_pregnant → safety_terms không rỗng
  P5 canonical query (build_retrieval_query_from_user) chứa description
  P6 query không dài quá 1200 chars (tránh nuốt context budget)
Gold-optional: nếu sample có `expected_query_terms` → check chứa đủ.

Chất lượng END-TO-END của query đo ở T2 ablation A4 (constructed vs raw recall) —
file này chỉ bắt lỗi cấu trúc trước khi đến retrieval.

Usage:
    python -m evaluation.unit.eval_query_planner \
        --dataset evaluation/datasets/v1/t1_intent_seed.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, REPORTS_DIR, ensure_repo_importable, utcnow, write_jsonl  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402


def check_sample(sample: dict) -> dict:
    ensure_repo_importable()
    from acne_llm.chat.preprocess import prepare_user_text
    from acne_llm.chat.normalizer import normalize_chat_message
    from acne_llm.llm.clinical_planner import ClinicalQueryPlanner
    from acne_llm.utils.retrieval_query import build_retrieval_query_from_user

    raw = sample["user_query"]
    prepared = prepare_user_text(raw)
    user = normalize_chat_message(
        raw, mode="auto",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    plan = ClinicalQueryPlanner().plan(user)
    query_vi = (plan.rag_queries.query_vi or "").lower()
    canonical = build_retrieval_query_from_user(
        user, clean_text_normalized=user.description
    ).lower()

    lesions = [str(x).lower() for x in (getattr(user, "lesion_types", None) or [])]
    dist = [str(x).lower() for x in (getattr(user, "lesion_distribution", None) or [])]
    red_flags = list(getattr(user, "red_flags_input", None) or [])
    is_pregnant = bool(getattr(getattr(user, "user_context", None), "is_pregnant", False))

    checks = {
        "P1_query_nonempty": bool(query_vi.strip()),
        "P2_lesions_in_query": (
            None if not lesions
            else all(t in query_vi or t in canonical for t in lesions)
        ),
        "P3_distribution_in_query": (
            None if not dist
            else all(t in query_vi or t in canonical for t in dist)
        ),
        "P4_safety_terms_on_redflag": (
            None if not (red_flags or is_pregnant)
            else bool(plan.safety_terms)
        ),
        "P5_canonical_has_description": (
            user.description.lower()[:60] in canonical if user.description else None
        ),
        "P6_query_length_ok": len(query_vi) <= 1200,
    }
    expected = [t.lower() for t in sample.get("expected_query_terms") or []]
    if expected:
        checks["G1_expected_terms"] = all(t in query_vi or t in canonical
                                          for t in expected)
    return {
        "sample_id": sample["sample_id"], "query": raw,
        "query_vi": query_vi[:300], "canonical": canonical[:300],
        "safety_terms": list(plan.safety_terms or []),
        "checks": checks,
        "all_ok": all(v is not False for v in checks.values()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evaluation/datasets/v1/t1_intent_seed.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    samples = load_dataset(ROOT / args.dataset)[: args.limit]
    rows = [check_sample(s) for s in samples]

    prop_rates: dict[str, dict] = {}
    for key in sorted({k for r in rows for k in r["checks"]}):
        vals = [r["checks"][key] for r in rows if r["checks"].get(key) is not None]
        prop_rates[key] = {
            "pass_rate": round(sum(1 for v in vals if v) / len(vals), 4) if vals else None,
            "n_applicable": len(vals),
        }
    report = {"generated_at": utcnow(), "n": len(rows), "dataset": args.dataset,
              "properties": prop_rates,
              "all_ok_rate": round(sum(r["all_ok"] for r in rows) / len(rows), 4)}
    out = REPORTS_DIR / "unit" / "query_planner"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    write_jsonl(out / "per_sample.jsonl", rows)
    write_jsonl(out / "failures.jsonl", [r for r in rows if not r["all_ok"]])
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
