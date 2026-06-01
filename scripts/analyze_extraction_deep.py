#!/usr/bin/env python3
"""Phân tích sâu nguyên nhân extraction issues - chạy trên Windows."""
import sys
sys.path.insert(0, 'src')

import json
from collections import defaultdict, Counter

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

print(f"=" * 80)
print(f"PHÂN TÍCH EXTRACTION ISSUES - {len(rows)} samples")
print(f"=" * 80)

from acne_llm.chat.extraction_confidence import extract_with_confidence

# ============ 1. PRODUCTS ANALYSIS ============
print("\n" + "=" * 80)
print("1. PRODUCTS ANALYSIS")
print("=" * 80)

product_fp_sources = defaultdict(list)
product_fp_by_intent = defaultdict(list)
intent_counts = Counter(r.get('intent', 'unknown') for r in rows)

for r in rows:
    text = r.get('text', '')
    ec = extract_with_confidence(text)
    pred_p = set(ec.products.values)
    gold_p = set(r.get('products', []))

    for p in pred_p - gold_p:
        product_fp_sources[p].append({
            'text': text[:100],
            'intent': r.get('intent'),
            'gold': list(gold_p)
        })
        product_fp_by_intent[r.get('intent')].append(p)

print(f"\nIntent distribution in golden set:")
for intent, count in intent_counts.most_common():
    print(f"  {intent}: {count} ({count/len(rows)*100:.1f}%)")

print(f"\nTop 20 Products FALSE POSITIVES:")
fp_total = 0
for product, samples in sorted(product_fp_sources.items(), key=lambda x: -len(x[1]))[:20]:
    print(f"\n  [{product}]: {len(samples)} FPs")
    for s in samples[:3]:
        print(f"    Intent: {s['intent']}")
        print(f"    Gold: {s['gold']}")
        print(f"    Text: \"{s['text']}\"")
    fp_total += len(samples)

print(f"\nTotal FP products: {fp_total}")

print(f"\nFP by Intent:")
for intent, fps in sorted(product_fp_by_intent.items(), key=lambda x: -len(x[1])):
    unique_fps = Counter(fps)
    print(f"  {intent}: {len(fps)} FPs, top: {unique_fps.most_common(5)}")

# ============ 2. TREATMENT_GOALS ANALYSIS ============
print("\n" + "=" * 80)
print("2. TREATMENT_GOALS ANALYSIS")
print("=" * 80)

goal_fn_samples = []
goal_type_fn = defaultdict(list)

for r in rows:
    text = r.get('text', '')
    ec = extract_with_confidence(text)
    pred_g = set(ec.treatment_goals.values)
    gold_g = set(r.get('treatment_goals', []))

    for g in gold_g - pred_g:
        goal_fn_samples.append({
            'goal': g,
            'text': text[:100],
            'intent': r.get('intent')
        })
        goal_type_fn[g].append(text[:80])

print(f"\nTop 20 Treatment Goals FALSE NEGATIVES:")
for i, sample in enumerate(goal_fn_samples[:20]):
    print(f"\n  [{sample['goal']}] (intent: {sample['intent']})")
    print(f"    Text: \"{sample['text']}\"")

print(f"\nFN count by goal type:")
for goal, texts in sorted(goal_type_fn.items(), key=lambda x: -len(x[1]))[:15]:
    print(f"  {goal}: {len(texts)} FNs")

# ============ 3. INFLAMMATION ANALYSIS ============
print("\n" + "=" * 80)
print("3. INFLAMMATION ANALYSIS")
print("=" * 80)

infl_confusion = defaultdict(lambda: defaultdict(int))
infl_samples = defaultdict(lambda: defaultdict(list))

for r in rows:
    text = r.get('text', '')
    ec = extract_with_confidence(text)
    pred_i = ec.inflammation.value
    gold_i = r.get('inflammation')
    if gold_i in ('none', 'unknown'):
        gold_i = None

    infl_confusion[gold_i][pred_i] += 1
    if gold_i != pred_i:
        infl_samples[gold_i][pred_i].append(text[:100])

print(f"\nConfusion Matrix (gold -> pred):")
print(f"{'Gold':<12} | {'Correct':<10} | {'Wrong predictions'}")
print("-" * 60)
for gold_val in sorted([k for k in infl_confusion.keys()], key=lambda x: (x is None, str(x))):
    preds = infl_confusion[gold_val]
    correct = preds.get(gold_val, 0)
    total = sum(preds.values())
    wrong = {k: v for k, v in preds.items() if k != gold_val}
    print(f"{str(gold_val):<12} | {correct:>5}/{total:<4} ({correct/total*100:>5.1f}%) | {wrong}")

print(f"\nSample errors by gold->pred pair:")
for gold_val in sorted([k for k in infl_samples.keys()], key=lambda x: (x is None, str(x))):
    for pred_val in infl_samples[gold_val]:
        samples = infl_samples[gold_val][pred_val]
        print(f"\n  {gold_val} -> {pred_val} ({len(samples)} samples):")
        for s in samples[:3]:
            print(f"    \"{s}\"")

# ============ 4. LESIONS ANALYSIS ============
print("\n" + "=" * 80)
print("4. LESIONS ANALYSIS")
print("=" * 80)

lesion_confusion = defaultdict(lambda: defaultdict(int))

for r in rows:
    text = r.get('text', '')
    ec = extract_with_confidence(text)
    pred_l = set(ec.lesion_types.values)
    gold_l = set(r.get('lesions', []))

    def norm_lesions(les):
        out = []
        for x in les:
            if x == "hidden_acne":
                out.append("closed_comedone")
            elif x != "other":
                out.append(x)
        return set(out)

    pred_l = norm_lesions(pred_l)
    gold_l = norm_lesions(gold_l)

    for l in gold_l | pred_l:
        if l in pred_l and l in gold_l:
            lesion_confusion[l]['TP'] += 1
        elif l in pred_l and l not in gold_l:
            lesion_confusion[l]['FP'] += 1
        elif l not in pred_l and l in gold_l:
            lesion_confusion[l]['FN'] += 1

print(f"\nLesion type performance:")
print(f"{'Type':<35} | {'TP':>5} | {'FP':>5} | {'FN':>5} | {'P':>6} | {'R':>6} | {'F1':>6}")
print("-" * 80)
for lesion in sorted(lesion_confusion.keys(), key=lambda x: -lesion_confusion[x]['TP']):
    tp = lesion_confusion[lesion]['TP']
    fp = lesion_confusion[lesion].get('FP', 0)
    fn = lesion_confusion[lesion].get('FN', 0)
    p = tp / (tp + fp) if (tp + fp) > 0 else 0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    print(f"{lesion:<35} | {tp:>5} | {fp:>5} | {fn:>5} | {p:>6.3f} | {r:>6.3f} | {f1:>6.3f}")

# ============ 5. INTENT vs EXTRACTION CORRELATION ============
print("\n" + "=" * 80)
print("5. INTENT IMPACT ON EXTRACTION")
print("=" * 80)

intent_extraction_stats = defaultdict(lambda: {'total': 0, 'fp_products': 0, 'fp_meds': 0})

for r in rows:
    intent = r.get('intent', 'unknown')
    text = r.get('text', '')
    ec = extract_with_confidence(text)

    pred_p = set(ec.products.values)
    gold_p = set(r.get('products', []))
    pred_m = set(ec.medications.values)
    gold_m = set(r.get('medications', []))

    intent_extraction_stats[intent]['total'] += 1
    intent_extraction_stats[intent]['fp_products'] += len(pred_p - gold_p)
    intent_extraction_stats[intent]['fp_meds'] += len(pred_m - gold_m)

print(f"\nIntent vs FP rates:")
print(f"{'Intent':<12} | {'Count':>6} | {'FP/products':>12} | {'FP/meds':>10}")
print("-" * 50)
for intent in ['advise', 'knowledge', 'clarify', 'reject']:
    stats = intent_extraction_stats[intent]
    total = stats['total']
    fp_p = stats['fp_products'] / total if total > 0 else 0
    fp_m = stats['fp_meds'] / total if total > 0 else 0
    print(f"{intent:<12} | {total:>6} | {fp_p:>12.2f} | {fp_m:>10.2f}")

# ============ 6. SAMPLE TEXT ANALYSIS ============
print("\n" + "=" * 80)
print("6. SAMPLE DIVERSITY ANALYSIS")
print("=" * 80)

text_lens = [len(r.get('text', '')) for r in rows]
print(f"\nText length stats:")
print(f"  Min: {min(text_lens)}, Max: {max(text_lens)}, Avg: {sum(text_lens)/len(text_lens):.1f}")

teencode_indicators = ['ko', 'dc', 'k ', 'e ', 'm ', 'vs', 'b ', 'sp ']
teencode_count = sum(1 for r in rows for t in teencode_indicators if t in r.get('text', '').lower())
print(f"  Samples with teencode: {teencode_count} ({teencode_count/len(rows)*100:.1f}%)")

formal_indicators = ['tôi', 'em', 'cháu', 'con']
formal_count = sum(1 for r in rows for t in formal_indicators if t in r.get('text', ''))
print(f"  Samples with formal pronouns: {formal_count} ({formal_count/len(rows)*100:.1f}%)")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
