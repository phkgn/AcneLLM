import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.metrics.classification import (
    accuracy, binary_rates, confusion_matrix, macro_f1, per_class_prf, set_micro_prf,
)


def test_accuracy_and_confusion():
    gold = ["advise", "advise", "reject", "knowledge"]
    pred = ["advise", "clarify", "reject", "knowledge"]
    assert accuracy(gold, pred) == 0.75
    assert confusion_matrix(gold, pred)["advise"] == {"advise": 1, "clarify": 1}


def test_per_class_prf_reject_recall():
    gold = ["reject", "reject", "advise"]
    pred = ["reject", "advise", "advise"]
    prf = per_class_prf(gold, pred)
    assert prf["reject"]["recall"] == 0.5
    assert prf["reject"]["precision"] == 1.0
    assert prf["reject"]["support"] == 2


def test_macro_f1_ignores_unsupported_classes():
    gold = ["a", "a", "b"]
    pred = ["a", "a", "c"]          # class c: pred-only, support=0 → không tính macro
    assert 0 < macro_f1(gold, pred) < 1


def test_binary_rates():
    gold = [True, True, False, False]
    pred = [True, False, True, False]
    r = binary_rates(gold, pred)
    assert r["tpr"] == 0.5 and r["fpr"] == 0.5 and r["n_pos"] == 2


def test_set_micro_prf():
    pairs = [({"a", "b"}, {"a"}), ({"c"}, {"c", "d"})]
    out = set_micro_prf(pairs)
    assert out["micro_recall"] == 0.6667     # tp=2, fn=1 (rounded)
    assert out["micro_precision"] == 0.6667  # tp=2, fp=1 (rounded)
    assert out["exact_match"] == 0.0
    assert out["n"] == 2
