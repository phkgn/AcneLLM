#!/usr/bin/env python3
"""Quick eval sau fix - chạy nhanh với 50 samples."""
import sys
sys.path.insert(0, 'src')

import json
from collections import defaultdict

from acne_llm.chat.extraction_confidence import extract_with_confidence

def _norm_infl(v):
    if v in (None, "none", "unknown"):
        return None
    return v

def _norm_lesions(xs):
    out = []
    for x in (xs or []):
        if x == "other":
            continue
        out.append("closed_comedone" if x == "hidden_acne" else x)
    return out

def _set_metrics(name, gold_sets, pred_sets):
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

def _scalar_acc(gold, pred):
    n = len(gold)
    correct = sum(1 for g, p in zip(gold, pred) if g == p)
    return round(correct / n, 3) if n else 0.0

# Load golden set
rows = []
with open('data/golden_extraction_gen.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except:
                pass

print(f"=" * 70)
print(f"QUICK EVAL - {len(rows)} samples")
print(f"=" * 70)

gold_scalar = defaultdict(list)
pred_scalar = defaultdict(list)
gold_list = defaultdict(list)
pred_list = defaultdict(list)

for r in rows:
    text = r.get("text", "")
    if not text:
        continue

    ec = extract_with_confidence(text)

    # Scalar
    gold_scalar["inflammation"].append(_norm_infl(r.get("inflammation")))
    pred_scalar["inflammation"].append(_norm_infl(ec.inflammation.value))

    gold_list["products"].append(r.get("products", []))
    pred_list["products"].append(_norm_lesions(ec.products.values))

    gold_list["medications"].append(r.get("medications", []))
    pred_list["medications"].append(list(ec.medications.values))

    gold_list["treatment_goals"].append(r.get("treatment_goals", []))
    pred_list["treatment_goals"].append(list(ec.treatment_goals.values))

print("\n── Scalar ──")
for field in gold_scalar:
    acc = _scalar_acc(gold_scalar[field], pred_scalar[field])
    n_gold = sum(1 for g in gold_scalar[field] if g is not None)
    print(f"  {field:18s}: {acc:.3f} (gold_has={n_gold}/{len(gold_scalar[field])})")

print("\n── List (P/R/F1) ──")
for field in gold_list:
    m = _set_metrics(field, gold_list[field], pred_list[field])
    print(f"  {m['field']:18s}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} "
          f"(tp={m['tp']} fp={m['fp']} fn={m['fn']})")

print("\n" + "=" * 70)
print("SO SÁNH VỚI TRƯỚC KHI FIX:")
print("=" * 70)
print("""
BEFORE FIX:
  products       : P=0.194 R=0.603 F1=0.294 (tp=117 fp=486)
  medications    : P=0.296 R=0.889 F1=0.444 (tp=24 fp=57)
  treatment_goals: P=0.465 R=0.233 F1=0.310 (tp=187 fp=215 fn=617)
  inflammation  : Acc=0.501

AFTER FIX (chạy script này):
""")
