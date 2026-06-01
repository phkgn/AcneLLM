#!/usr/bin/env python3
"""Eval task EXTRACT trên golden set — precision/recall/F1 per-field.

Đọc golden set (golden_extraction_gen.jsonl - format đầy đủ), chạy
extract_with_confidence() trên từng câu, so với nhãn.

Các fields được eval:
  - Scalar: skin_type, sex, age, duration_weeks, is_pregnant, is_breastfeeding, inflammation
  - List: lesions, distribution, products, medications, allergies, scarring_signs,
          hormonal_factors, treatment_goals, red_flags

Usage:
    python scripts/eval_extraction.py
    python scripts/eval_extraction.py --golden data/golden_extraction_gen.jsonl
    python scripts/eval_extraction.py --limit 100
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acne_llm.chat.extraction_confidence import extract_with_confidence  # noqa: E402


def _load(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _set_metrics(name, gold_sets, pred_sets):
    """Micro precision/recall/F1 cho field dạng list (tập)."""
    tp = fp = fn = 0
    for g, p in zip(gold_sets, pred_sets):
        g, p = set(g or []), set(p or [])
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"field": name, "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "tp": tp, "fp": fp, "fn": fn}


def _norm_infl(v):
    """Chuẩn hoá inflammation: 'none'/'unknown' ↔ None (golden cũ)."""
    if v in (None, "none", "unknown"):
        return None
    return v


def _norm_lesions(xs):
    """Chuẩn hoá lesions: bỏ 'other', map 'hidden_acne' → 'closed_comedone'."""
    out = []
    for x in (xs or []):
        if x == "other":
            continue
        out.append("closed_comedone" if x == "hidden_acne" else x)
    return out


def _drop_other(xs):
    return [x for x in (xs or []) if x != "other"]


def _scalar_acc(gold, pred):
    """Accuracy cho field đơn trị (None coi là một lớp)."""
    n = len(gold)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    return round(correct / n, 3) if n else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="data/golden_extraction_gen.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="0 = tất cả")
    ap.add_argument("--show-errors", action="store_true", help="hiển thị chi tiết lỗi")
    args = ap.parse_args()

    path = (ROOT / args.golden) if not Path(args.golden).is_absolute() else Path(args.golden)
    if not path.exists():
        print(f"ERROR: không thấy {path}", file=sys.stderr)
        sys.exit(1)

    rows = _load(path)
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print("ERROR: golden set rỗng", file=sys.stderr)
        sys.exit(1)

    # Gom theo field
    gold_scalar = defaultdict(list)
    pred_scalar = defaultdict(list)
    gold_list = defaultdict(list)
    pred_list = defaultdict(list)
    conf_correct, conf_wrong = defaultdict(list), defaultdict(list)
    errors = []

    for i, r in enumerate(rows):
        text = r.get("text", "")
        if not text:
            continue

        ec = extract_with_confidence(text)

        # ── Scalar fields ──
        gold_scalar["skin_type"].append(r.get("skin_type"))
        pred_scalar["skin_type"].append(ec.skin_type.value)
        if r.get("skin_type") is not None or ec.skin_type.value is not None:
            if ec.skin_type.value == r.get("skin_type"):
                conf_correct["skin_type"].append(ec.skin_type.confidence)
            else:
                conf_wrong["skin_type"].append(ec.skin_type.confidence)

        gold_scalar["sex"].append(r.get("sex"))
        pred_scalar["sex"].append(ec.sex.value)

        gold_scalar["age"].append(r.get("age"))
        pred_scalar["age"].append(ec.age.value)

        gold_scalar["duration_weeks"].append(r.get("duration_weeks"))
        pred_scalar["duration_weeks"].append(ec.duration_weeks.value)

        gold_scalar["is_pregnant"].append(r.get("is_pregnant"))
        pred_scalar["is_pregnant"].append(ec.is_pregnant.value)

        gold_scalar["is_breastfeeding"].append(r.get("is_breastfeeding"))
        pred_scalar["is_breastfeeding"].append(ec.is_breastfeeding.value)

        gold_scalar["inflammation"].append(_norm_infl(r.get("inflammation")))
        pred_scalar["inflammation"].append(_norm_infl(ec.inflammation.value))

        # ── List fields ──
        gold_list["lesions"].append(_norm_lesions(r.get("lesions", [])))
        pred_list["lesions"].append(_norm_lesions(ec.lesion_types.values))

        gold_list["distribution"].append(_drop_other(r.get("distribution", [])))
        pred_list["distribution"].append(_drop_other(ec.distribution.values))

        gold_list["products"].append(r.get("products", []))
        pred_list["products"].append(list(ec.products.values))

        gold_list["medications"].append(r.get("medications", []))
        pred_list["medications"].append(list(ec.medications.values))

        gold_list["allergies"].append(r.get("allergies", []))
        pred_list["allergies"].append(list(ec.allergies.values))

        gold_list["scarring_signs"].append(r.get("scarring_signs", []))
        pred_list["scarring_signs"].append(list(ec.scarring_signs.values))

        gold_list["hormonal_factors"].append(r.get("hormonal_factors", []))
        pred_list["hormonal_factors"].append(list(ec.hormonal_factors.values))

        gold_list["treatment_goals"].append(r.get("treatment_goals", []))
        pred_list["treatment_goals"].append(list(ec.treatment_goals.values))

        gold_list["red_flags"].append(r.get("red_flags", []))
        pred_list["red_flags"].append(list(ec.red_flags.values))

        # ── Collect errors ──
        if args.show_errors:
            short_text = text[:60]
            for field in ["lesions", "distribution", "products", "medications", "allergies"]:
                gold_f = set(r.get(field, []) or [])
                pred_f = set(pred_list[field][-1])
                if gold_f != pred_f:
                    errors.append(f"[{i}] {field}: gold={gold_f} pred={pred_f} | {short_text}")

    # ── Print results ──
    print("=" * 70)
    print(f"EVAL EXTRACT — {len(rows)} câu | {path.name}")
    print("=" * 70)

    print("\n── Scalar (accuracy) ──")
    for field in gold_scalar:
        acc = _scalar_acc(gold_scalar[field], pred_scalar[field])
        n_gold = sum(1 for g in gold_scalar[field] if g is not None)
        n_total = len(gold_scalar[field])
        print(f"  {field:18s}: {acc:.3f} (gold_has={n_gold}/{n_total})")

    print("\n── List (micro P/R/F1) ──")
    for field in gold_list:
        m = _set_metrics(field, gold_list[field], pred_list[field])
        print(f"  {m['field']:18s}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} "
              f"(tp={m['tp']} fp={m['fp']} fn={m['fn']})")

    # Confidence sanity
    print("\n── Confidence sanity (skin_type) ──")
    if conf_correct["skin_type"] or conf_wrong["skin_type"]:
        avg_c = sum(conf_correct["skin_type"]) / len(conf_correct["skin_type"]) if conf_correct["skin_type"] else 0
        avg_w = sum(conf_wrong["skin_type"]) / len(conf_wrong["skin_type"]) if conf_wrong["skin_type"] else 0
        print(f"  skin_type: conf_đúng={avg_c:.3f}(n={len(conf_correct['skin_type'])}) "
              f"conf_sai={avg_w:.3f}(n={len(conf_wrong['skin_type'])})")

    # Errors
    if args.show_errors and errors:
        print(f"\n── Chi tiết lỗi ({len(errors)} items) ──")
        for err in errors[:30]:
            print(f"  {err}")
        if len(errors) > 30:
            print(f"  ... và {len(errors) - 30} lỗi khác")


if __name__ == "__main__":
    main()
