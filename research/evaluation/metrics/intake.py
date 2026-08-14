"""Metrics for unified-intake evaluation.

Classification and set metrics remain implemented in ``classification``; this
module only exposes intake-shaped wrappers and the four intake-specific
measurements that do not already exist elsewhere.
"""
from __future__ import annotations

from collections.abc import Collection, Sequence

from evaluation.metrics.classification import (
    confusion_matrix,
    macro_f1,
    per_class_prf,
    set_micro_prf,
)


def intent_prf(gold: list[str], pred: list[str]) -> dict:
    """Return existing intent PRF metrics and their confusion matrix."""
    return {
        "per_class": per_class_prf(gold, pred),
        "macro_f1": macro_f1(gold, pred),
        "confusion_matrix": confusion_matrix(gold, pred),
    }


def list_prf(
    gold: Sequence[Collection[str]],
    pred: Sequence[Collection[str]],
) -> dict:
    """Return the existing micro PRF metrics for an intake list field."""
    assert len(gold) == len(pred)
    return set_micro_prf([(set(g), set(p)) for g, p in zip(gold, pred)])


def enum_validity(
    predicted: Sequence[str | None],
    valid_values: Collection[str],
) -> dict:
    """Measure the share of emitted enum values present in ``valid_values``."""
    emitted = [value for value in predicted if value is not None]
    valid = set(valid_values)
    hits = sum(value in valid for value in emitted)
    return {
        "rate": round(hits / len(emitted), 4) if emitted else None,
        "valid": hits,
        "invalid": len(emitted) - hits,
        "n": len(emitted),
    }


def expected_calibration_error(
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    bins: int = 10,
) -> float:
    """Compute ECE with equal-width bins over confidence values in ``[0, 1]``."""
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must have equal length")
    if bins <= 0:
        raise ValueError("bins must be positive")
    if any(confidence < 0.0 or confidence > 1.0 for confidence in confidences):
        raise ValueError("confidence must be in [0, 1]")
    if not confidences:
        return 0.0

    total = len(confidences)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        members = [
            position
            for position, confidence in enumerate(confidences)
            if lower <= confidence < upper
            or (index == bins - 1 and confidence == 1.0)
        ]
        if not members:
            continue
        mean_confidence = sum(confidences[position] for position in members) / len(members)
        accuracy = sum(bool(correct[position]) for position in members) / len(members)
        error += len(members) / total * abs(accuracy - mean_confidence)
    return round(error, 4)


def negation_leak(
    pairs: Sequence[tuple[Collection[str], Collection[str]]],
) -> dict:
    """Measure negated values that leak into the model's extracted values."""
    negated_total = 0
    leaked_total = 0
    affected_samples = 0
    for negated, predicted in pairs:
        negated_values = set(negated)
        leaked = negated_values & set(predicted)
        negated_total += len(negated_values)
        leaked_total += len(leaked)
        affected_samples += bool(leaked)
    return {
        "rate": round(leaked_total / negated_total, 4) if negated_total else None,
        "leaked": leaked_total,
        "negated": negated_total,
        "affected_samples": affected_samples,
        "n": len(pairs),
    }


def canonicalization_hit(
    pairs: Sequence[tuple[str, str | None]],
) -> dict:
    """Measure exact hits against expected canonical values."""
    hits = sum(predicted == expected for expected, predicted in pairs)
    return {
        "rate": round(hits / len(pairs), 4) if pairs else None,
        "hits": hits,
        "n": len(pairs),
    }


if __name__ == "__main__":
    assert enum_validity(["oily", "invalid", None], {"oily", "dry"})["rate"] == 0.5
    assert expected_calibration_error([0.0, 1.0], [False, True]) == 0.0
    assert negation_leak([({"BHA"}, {"BHA"})])["leaked"] == 1
    assert canonicalization_hit([("salicylic acid", "salicylic acid")])["rate"] == 1.0
