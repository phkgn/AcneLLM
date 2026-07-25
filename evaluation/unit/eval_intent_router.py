"""T1 — Legacy fallback intent eval on gold primary-intent labels.

Dataset schema: intent_label ∈ {advise|knowledge|clarify|reject}.

Usage:
    python -m evaluation.unit.eval_intent_router \
        --dataset evaluation/datasets/v1/t1_intent_seed.jsonl [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from evaluation.common import ROOT, REPORTS_DIR, ensure_repo_importable, utcnow, write_jsonl  # noqa: E402
from evaluation.datasets.registry import load_dataset  # noqa: E402
from evaluation.metrics.classification import (  # noqa: E402
    accuracy, confusion_matrix, macro_f1, per_class_prf,
)


def predict(sample: dict) -> dict:
    ensure_repo_importable()
    from acne_llm.chat.preprocess import prepare_user_text
    from acne_llm.chat.normalizer import normalize_chat_message
    from acne_llm.chat.fallback.intent_router import route_intent

    raw = sample["user_query"]
    prepared = prepare_user_text(raw)
    user = normalize_chat_message(
        raw, mode="auto",
        clean_text=prepared.clean_text,
        clean_text_no_accent=prepared.clean_text_no_accent,
    )
    decision = route_intent(prepared.clean_text, user, history=[])
    return {
        "primary_intent": decision.primary_intent,
        "confidence": decision.confidence,
        "reason_code": decision.reason_code,
        "route_flags": list(decision.route_flags or []),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evaluation/datasets/v1/t1_intent_seed.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    samples = load_dataset(ROOT / args.dataset)[: args.limit]
    samples = [s for s in samples if s.get("intent_label")]
    rows, gold_i, pred_i = [], [], []
    for s in samples:
        p = predict(s)
        rows.append({"sample_id": s["sample_id"], "query": s["user_query"],
                     "gold_intent": s["intent_label"], "pred": p,
                     "intent_ok": p["primary_intent"] == s["intent_label"]})
        gold_i.append(s["intent_label"])
        pred_i.append(p["primary_intent"])

    prf = per_class_prf(gold_i, pred_i)
    report = {
        "generated_at": utcnow(), "n": len(rows), "dataset": args.dataset,
        "intent_accuracy": round(accuracy(gold_i, pred_i), 4),
        "intent_macro_f1": macro_f1(gold_i, pred_i),
        "intent_per_class": prf,
        # reject là safety-critical: recall phải ≥ 0.95 (gate)
        "reject_recall": prf.get("reject", {}).get("recall"),
        "confusion": confusion_matrix(gold_i, pred_i),
    }
    out = REPORTS_DIR / "unit" / "intent_router"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    write_jsonl(out / "per_sample.jsonl", rows)
    write_jsonl(out / "failures.jsonl", [r for r in rows if not r["intent_ok"]])
    print(json.dumps({k: v for k, v in report.items() if k != "confusion"},
                     indent=2, ensure_ascii=False))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
