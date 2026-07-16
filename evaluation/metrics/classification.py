"""Classification metrics cho T1 unit eval (router, guardrails). Stdlib, unit-tested."""
from __future__ import annotations

from collections import Counter, defaultdict


def accuracy(gold: list[str], pred: list[str]) -> float:
    assert len(gold) == len(pred) and gold
    return sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)


def per_class_prf(gold: list[str], pred: list[str]) -> dict[str, dict]:
    labels = sorted(set(gold) | set(pred))
    out: dict[str, dict] = {}
    for lb in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == lb and p == lb)
        fp = sum(1 for g, p in zip(gold, pred) if g != lb and p == lb)
        fn = sum(1 for g, p in zip(gold, pred) if g == lb and p != lb)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[lb] = {"precision": round(prec, 4), "recall": round(rec, 4),
                   "f1": round(f1, 4), "support": tp + fn}
    return out


def macro_f1(gold: list[str], pred: list[str]) -> float:
    prf = per_class_prf(gold, pred)
    classes = [v for v in prf.values() if v["support"] > 0]
    return round(sum(c["f1"] for c in classes) / len(classes), 4) if classes else 0.0


def confusion_matrix(gold: list[str], pred: list[str]) -> dict[str, dict[str, int]]:
    mat: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g, p in zip(gold, pred):
        mat[g][p] += 1
    return {g: dict(row) for g, row in mat.items()}


def binary_rates(gold: list[bool], pred: list[bool]) -> dict:
    """TPR/FPR/TNR/FNR — cho OOD/scope detection (positive = out-of-scope)."""
    tp = sum(1 for g, p in zip(gold, pred) if g and p)
    fn = sum(1 for g, p in zip(gold, pred) if g and not p)
    fp = sum(1 for g, p in zip(gold, pred) if not g and p)
    tn = sum(1 for g, p in zip(gold, pred) if not g and not p)
    return {
        "tpr": round(tp / (tp + fn), 4) if tp + fn else None,
        "fnr": round(fn / (tp + fn), 4) if tp + fn else None,
        "fpr": round(fp / (fp + tn), 4) if fp + tn else None,
        "tnr": round(tn / (fp + tn), 4) if fp + tn else None,
        "n_pos": tp + fn, "n_neg": fp + tn,
    }


def set_micro_prf(pairs: list[tuple[set[str], set[str]]]) -> dict:
    """Micro P/R/F1 cho multi-label fields: pairs = [(gold_set, pred_set), ...]."""
    tp = sum(len(g & p) for g, p in pairs)
    fp = sum(len(p - g) for g, p in pairs)
    fn = sum(len(g - p) for g, p in pairs)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    jacc = [len(g & p) / len(g | p) for g, p in pairs if g | p]
    exact = [g == p for g, p in pairs]
    return {
        "micro_precision": round(prec, 4), "micro_recall": round(rec, 4),
        "micro_f1": round(f1, 4),
        "mean_jaccard": round(sum(jacc) / len(jacc), 4) if jacc else None,
        "exact_match": round(sum(exact) / len(exact), 4) if exact else None,
        "n": len(pairs),
    }


def label_distribution(values: list[str]) -> dict[str, int]:
    return dict(Counter(values).most_common())
