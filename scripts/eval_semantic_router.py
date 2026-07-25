#!/usr/bin/env python3
"""Calibrate and evaluate the local semantic intent router.

The runtime index is built from the train split only.  This command embeds the
held-out in-scope test split and the separate OOS set, selects an ambiguity
margin and an OOS distance threshold, compares against the legacy rule router,
and writes machine-readable metrics for the Round 3 report.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acne_llm.chat.fallback.intent_router import route_intent  # noqa: E402
from acne_llm.chat.normalizer import normalize_chat_message  # noqa: E402
from acne_llm.chat.fallback.semantic_router import (  # noqa: E402
    SemanticPrediction,
    SemanticRouter,
)
from acne_llm.rag.embedder import Embedder  # noqa: E402
from acne_llm.config import Settings  # noqa: E402
from evaluation.metrics.intake import intent_prf  # noqa: E402
from scripts.eval_unified_intake import _build_model_infer  # noqa: E402


IN_SCOPE_LABELS = ("advise", "knowledge", "clarify")
ALL_PREDICTION_LABELS = (*IN_SCOPE_LABELS, "reject")


class _NoQueryCacheEmbedder:
    """Use the repository model while measuring real per-turn embedding time."""

    def __init__(self, embedder: Embedder):
        self._embedder = embedder
        self.model_name = embedder.model_name

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._embedder.embed_passages(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embedder._embed_query_raw(text)


def _read_jsonl(path: Path, *, allowed: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != {"text", "intent"}:
            raise ValueError(
                f"{path}:{line_number}: expected exactly {{'text','intent'}}"
            )
        text = row.get("text")
        intent = row.get("intent")
        if not isinstance(text, str) or not text.strip() or intent not in allowed:
            raise ValueError(f"{path}:{line_number}: invalid text/intent")
        rows.append({"text": text.strip(), "intent": str(intent)})
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _winner(prediction: SemanticPrediction) -> str:
    return sorted(
        prediction.vote_scores.items(),
        key=lambda item: (-item[1], item[0]),
    )[0][0]


def _apply_thresholds(
    prediction: SemanticPrediction,
    *,
    oos_threshold: float,
    ambiguity_margin: float,
) -> str:
    if prediction.nearest_distance > oos_threshold:
        return "reject"
    winner = _winner(prediction)
    if winner != "clarify" and prediction.vote_margin < ambiguity_margin:
        return "clarify"
    return winner


def _class_metrics(
    rows: list[dict[str, str]],
    predictions: list[SemanticPrediction],
    *,
    oos_threshold: float,
    ambiguity_margin: float,
) -> dict[str, Any]:
    predicted = [
        _apply_thresholds(
            item,
            oos_threshold=oos_threshold,
            ambiguity_margin=ambiguity_margin,
        )
        for item in predictions
    ]
    total = len(rows)
    correct = sum(
        row["intent"] == label for row, label in zip(rows, predicted)
    )
    accepted_indices = [
        index for index, label in enumerate(predicted) if label != "reject"
    ]
    accepted_correct = sum(
        rows[index]["intent"] == predicted[index] for index in accepted_indices
    )
    confusion = {
        gold: {
            label: sum(
                row["intent"] == gold and prediction == label
                for row, prediction in zip(rows, predicted)
            )
            for label in ALL_PREDICTION_LABELS
        }
        for gold in IN_SCOPE_LABELS
    }
    per_class = {}
    for label in IN_SCOPE_LABELS:
        support = sum(row["intent"] == label for row in rows)
        hits = sum(
            row["intent"] == label and pred == label
            for row, pred in zip(rows, predicted)
        )
        per_class[label] = {
            "support": support,
            "correct": hits,
            "recall": hits / support if support else 0.0,
        }
    return {
        "accuracy": correct / total,
        "correct": correct,
        "total": total,
        "accepted_accuracy": (
            accepted_correct / len(accepted_indices) if accepted_indices else 0.0
        ),
        "in_scope_recall": len(accepted_indices) / total,
        "false_rejects": total - len(accepted_indices),
        "predicted_counts": dict(Counter(predicted)),
        "per_class": per_class,
        "confusion": confusion,
        "predictions": predicted,
    }


def _oos_curve_row(
    threshold: float,
    in_scope_predictions: list[SemanticPrediction],
    oos_predictions: list[SemanticPrediction],
) -> dict[str, float | int]:
    in_scope_kept = sum(
        prediction.nearest_distance <= threshold
        for prediction in in_scope_predictions
    )
    oos_rejected = sum(
        prediction.nearest_distance > threshold
        for prediction in oos_predictions
    )
    false_rejects = len(in_scope_predictions) - in_scope_kept
    predicted_rejects = oos_rejected + false_rejects
    in_scope_recall = in_scope_kept / len(in_scope_predictions)
    oos_recall = oos_rejected / len(oos_predictions)
    oos_precision = (
        oos_rejected / predicted_rejects if predicted_rejects else 1.0
    )
    oos_f1 = (
        2 * oos_precision * oos_recall / (oos_precision + oos_recall)
        if oos_precision + oos_recall
        else 0.0
    )
    return {
        "threshold": threshold,
        "in_scope_recall": in_scope_recall,
        "false_rejects": false_rejects,
        "oos_recall": oos_recall,
        "oos_precision": oos_precision,
        "oos_f1": oos_f1,
        "oos_rejected": oos_rejected,
    }


def _choose_margin(
    rows: list[dict[str, str]],
    predictions: list[SemanticPrediction],
) -> tuple[float, list[dict[str, float]]]:
    curve: list[dict[str, float]] = []
    for index in range(0, 31):
        margin = index / 100.0
        metrics = _class_metrics(
            rows,
            predictions,
            oos_threshold=2.0,
            ambiguity_margin=margin,
        )
        curve.append(
            {
                "margin": margin,
                "accuracy_without_oos_gate": metrics["accuracy"],
            }
        )
    selected = max(
        curve,
        # Among equally accurate margins, prefer the largest positive margin:
        # the product decision requires close top-two votes to become clarify.
        key=lambda row: (row["accuracy_without_oos_gate"], row["margin"]),
    )
    return float(selected["margin"]), curve


def _choose_oos_threshold(
    in_scope_predictions: list[SemanticPrediction],
    oos_predictions: list[SemanticPrediction],
    *,
    minimum_in_scope_recall: float,
) -> tuple[float, list[dict[str, float | int]]]:
    observed = [
        prediction.nearest_distance
        for prediction in [*in_scope_predictions, *oos_predictions]
    ]
    low = max(0.0, min(observed) - 0.02)
    high = min(2.0, max(observed) + 0.02)
    thresholds = sorted({
        round(value, 6)
        for value in np.linspace(low, high, 241).tolist()
    })
    curve = [
        _oos_curve_row(threshold, in_scope_predictions, oos_predictions)
        for threshold in thresholds
    ]
    eligible = [
        row
        for row in curve
        if row["in_scope_recall"] >= minimum_in_scope_recall
    ]
    if eligible:
        selected = max(
            eligible,
            key=lambda row: (
                row["oos_recall"],
                row["oos_precision"],
                -row["threshold"],
            ),
        )
    else:
        selected = max(
            curve,
            key=lambda row: (
                row["in_scope_recall"],
                row["oos_recall"],
                row["oos_precision"],
            ),
        )
    return float(selected["threshold"]), curve


def _legacy_rule_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    predicted: list[str] = []
    latencies_ms: list[float] = []
    for row in rows:
        user = normalize_chat_message(row["text"])
        started = time.perf_counter()
        decision = route_intent(
            row["text"],
            user,
            [],
            current_clinical=user.clinical,
        )
        latencies_ms.append((time.perf_counter() - started) * 1000)
        predicted.append(decision.primary_intent)
    correct = sum(
        row["intent"] == label for row, label in zip(rows, predicted)
    )
    return {
        "accuracy": correct / len(rows),
        "correct": correct,
        "total": len(rows),
        "predicted_counts": dict(Counter(predicted)),
        "latency_ms": _latency_summary(latencies_ms),
    }


def _unified_metrics(
    test_rows: list[dict[str, str]],
    oos_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Run the unified-intake arm directly, without semantic/rule fallback."""
    rows = [*test_rows, *oos_rows]
    predicted: list[str] = []
    latencies_ms: list[float] = []
    failures = 0
    infer, close = _build_model_infer(Settings())
    try:
        for index, row in enumerate(rows, 1):
            started = time.perf_counter()
            try:
                payload = infer(row["text"])
                intent = payload.get("intent")
                if intent not in ALL_PREDICTION_LABELS:
                    raise ValueError(f"invalid unified intent: {intent!r}")
                predicted.append(intent)
            except Exception:
                failures += 1
                predicted.append("__failure__")
            latencies_ms.append((time.perf_counter() - started) * 1000)
            if index % 25 == 0:
                print(f"[unified] {index}/{len(rows)}", flush=True)
    finally:
        close()

    gold = [row["intent"] for row in rows]
    in_scope_pred = predicted[: len(test_rows)]
    oos_pred = predicted[len(test_rows) :]
    shared = intent_prf(gold, predicted)
    return {
        "model": Settings().intake_model,
        "rows": len(rows),
        "failures": failures,
        "fallback_rate": round(failures / len(rows), 4),
        "fallback_executed": False,
        "accuracy": round(sum(g == p for g, p in zip(gold, predicted)) / len(rows), 4),
        "in_scope_accuracy": round(
            sum(row["intent"] == pred for row, pred in zip(test_rows, in_scope_pred))
            / len(test_rows),
            4,
        ),
        "oos_recall": round(
            sum(pred == "reject" for pred in oos_pred) / len(oos_pred),
            4,
        ),
        "intent_prf": shared,
        "predicted_counts": dict(Counter(predicted)),
        "latency_ms": _latency_summary(latencies_ms),
    }


def _latency_summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(array.max()),
    }


def _oos_subset_summary(
    predictions: list[SemanticPrediction],
    *,
    threshold: float,
) -> dict[str, float | int]:
    distances = [item.nearest_distance for item in predictions]
    rejected = sum(distance > threshold for distance in distances)
    return {
        "rows": len(distances),
        "rejected": rejected,
        "recall": rejected / len(distances) if distances else 0.0,
        "distance_min": min(distances) if distances else 0.0,
        "distance_median": statistics.median(distances) if distances else 0.0,
        "distance_max": max(distances) if distances else 0.0,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    train_path = (ROOT / args.train).resolve()
    test_path = (ROOT / args.test).resolve()
    oos_path = (ROOT / args.oos).resolve()
    cache_path = (ROOT / args.cache).resolve()
    output_path = (ROOT / args.output).resolve()

    train_rows = _read_jsonl(train_path, allowed=set(IN_SCOPE_LABELS))
    test_rows = _read_jsonl(test_path, allowed=set(IN_SCOPE_LABELS))
    oos_rows = _read_jsonl(oos_path, allowed={"reject"})
    if args.golden_oos_count > len(oos_rows):
        raise ValueError(
            f"--golden-oos-count={args.golden_oos_count} exceeds "
            f"OOS rows={len(oos_rows)}"
        )
    train_texts = {row["text"].casefold().strip() for row in train_rows}
    test_texts = {row["text"].casefold().strip() for row in test_rows}
    oos_texts = {row["text"].casefold().strip() for row in oos_rows}
    leakage = {
        "train_test_exact_overlap": len(train_texts & test_texts),
        "train_oos_exact_overlap": len(train_texts & oos_texts),
    }
    if any(leakage.values()):
        raise RuntimeError(f"exact split leakage detected: {leakage}")

    base_embedder = Embedder(
        model_name=args.model,
        device=args.device,
        batch_size=args.batch_size,
    )
    embedder = _NoQueryCacheEmbedder(base_embedder)
    router = SemanticRouter(
        embedder=embedder,
        train_path=train_path,
        cache_path=cache_path,
        k=args.k,
        oos_distance_threshold=2.0,
        ambiguity_margin=0.0,
    )

    test_predictions: list[SemanticPrediction] = []
    oos_predictions: list[SemanticPrediction] = []
    test_latencies_ms: list[float] = []
    oos_latencies_ms: list[float] = []
    for index, row in enumerate(test_rows, 1):
        started = time.perf_counter()
        test_predictions.append(
            router.predict(
                row["text"],
                oos_distance_threshold=2.0,
                ambiguity_margin=0.0,
            )
        )
        test_latencies_ms.append((time.perf_counter() - started) * 1000)
        if index % 50 == 0:
            print(f"[eval] in-scope {index}/{len(test_rows)}", flush=True)
    for index, row in enumerate(oos_rows, 1):
        started = time.perf_counter()
        oos_predictions.append(
            router.predict(
                row["text"],
                oos_distance_threshold=2.0,
                ambiguity_margin=0.0,
            )
        )
        oos_latencies_ms.append((time.perf_counter() - started) * 1000)
        if index % 25 == 0:
            print(f"[eval] OOS {index}/{len(oos_rows)}", flush=True)

    ambiguity_margin, ambiguity_curve = _choose_margin(
        test_rows,
        test_predictions,
    )
    oos_threshold, oos_curve = _choose_oos_threshold(
        test_predictions,
        oos_predictions,
        minimum_in_scope_recall=args.minimum_in_scope_recall,
    )
    semantic = _class_metrics(
        test_rows,
        test_predictions,
        oos_threshold=oos_threshold,
        ambiguity_margin=ambiguity_margin,
    )
    semantic.pop("predictions")
    selected_oos = _oos_curve_row(
        oos_threshold,
        test_predictions,
        oos_predictions,
    )
    golden_oos_predictions = oos_predictions[: args.golden_oos_count]
    generated_oos_predictions = oos_predictions[args.golden_oos_count :]
    rule = _legacy_rule_metrics(test_rows)
    unified = _unified_metrics(test_rows, oos_rows) if args.include_unified else None
    all_latencies = [*test_latencies_ms, *oos_latencies_ms]

    metrics = {
        "schema_version": 1,
        "model": args.model,
        "device": base_embedder.device,
        "k": args.k,
        "selected": {
            "oos_distance_threshold": oos_threshold,
            "ambiguity_margin": ambiguity_margin,
            "minimum_in_scope_recall_constraint": args.minimum_in_scope_recall,
        },
        "data": {
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "oos_rows": len(oos_rows),
            "train_counts": dict(Counter(row["intent"] for row in train_rows)),
            "test_counts": dict(Counter(row["intent"] for row in test_rows)),
            "train_sha256": _sha256(train_path),
            "test_sha256": _sha256(test_path),
            "oos_sha256": _sha256(oos_path),
            "leakage": leakage,
        },
        "semantic_test": semantic,
        "oos_detection": selected_oos,
        "oos_detection_by_source": {
            "golden_original": _oos_subset_summary(
                golden_oos_predictions,
                threshold=oos_threshold,
            ),
            "generated_clear": _oos_subset_summary(
                generated_oos_predictions,
                threshold=oos_threshold,
            ),
        },
        "legacy_rule_test": rule,
        "unified_intake": unified,
        "stated_rule_baseline_accuracy": 0.716,
        "latency_ms_real_local_embedding_plus_knn": {
            "all": _latency_summary(all_latencies),
            "in_scope": _latency_summary(test_latencies_ms),
            "oos": _latency_summary(oos_latencies_ms),
            "samples": len(all_latencies),
        },
        "distance_summary": {
            "in_scope": {
                "min": min(item.nearest_distance for item in test_predictions),
                "median": statistics.median(
                    item.nearest_distance for item in test_predictions
                ),
                "max": max(item.nearest_distance for item in test_predictions),
            },
            "oos": {
                "min": min(item.nearest_distance for item in oos_predictions),
                "median": statistics.median(
                    item.nearest_distance for item in oos_predictions
                ),
                "max": max(item.nearest_distance for item in oos_predictions),
            },
        },
        "ambiguity_curve": ambiguity_curve,
        "oos_curve": oos_curve,
        "index": {
            "rows": router.indexed_rows,
            "train_sha256": router.train_sha256,
            "cache_path": str(cache_path.relative_to(ROOT)),
            "cache_hit": router.cache_hit,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "semantic_accuracy": semantic["accuracy"],
                "rule_accuracy": rule["accuracy"],
                "unified_accuracy": unified["accuracy"] if unified else None,
                "in_scope_recall": selected_oos["in_scope_recall"],
                "oos_recall": selected_oos["oos_recall"],
                "oos_precision": selected_oos["oos_precision"],
                "oos_threshold": oos_threshold,
                "ambiguity_margin": ambiguity_margin,
                "latency_p95_ms": metrics[
                    "latency_ms_real_local_embedding_plus_knn"
                ]["all"]["p95"],
                "output": str(output_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return metrics


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="data/intent_classify.train.jsonl")
    parser.add_argument("--test", default="data/intent_classify.test.jsonl")
    parser.add_argument("--oos", default="data/subject_oos_eval.jsonl")
    parser.add_argument("--cache", default="data/intent_router_index.npz")
    parser.add_argument(
        "--output",
        default="reports/semantic_router_eval_20260719.json",
    )
    parser.add_argument("--model", default="AITeamVN/Vietnamese_Embedding")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--k", type=int, default=9)
    parser.add_argument(
        "--golden-oos-count",
        type=int,
        default=85,
        help="Leading OOS rows copied from the original golden dataset.",
    )
    parser.add_argument("--minimum-in-scope-recall", type=float, default=0.98)
    parser.add_argument(
        "--include-unified",
        action="store_true",
        help="also run the no-fallback unified-intake arm on test + OOS rows",
    )
    args = parser.parse_args(argv)
    if args.k < 1:
        parser.error("--k must be positive")
    if args.golden_oos_count < 0:
        parser.error("--golden-oos-count must be non-negative")
    if not 0.0 < args.minimum_in_scope_recall <= 1.0:
        parser.error("--minimum-in-scope-recall must be in (0,1]")
    return args


if __name__ == "__main__":
    evaluate(parse_args())
