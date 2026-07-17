"""Tune the provisional grounding threshold on agent-annotated D1 sentences."""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.common import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    build_run_meta,
    ensure_repo_importable,
    read_jsonl,
)
from evaluation.metrics.grounding import (  # noqa: E402
    _cosines,
    _lexical_context_score,
)

ensure_repo_importable()


def validate_label_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    labels = payload.get("labels") or []
    if not 60 <= len(labels) <= 80:
        raise ValueError("grounding calibration must contain 60-80 D1 sentences")
    invalid = [
        index for index, label in enumerate(labels)
        if not isinstance(label, dict)
        or not str(label.get("sample_id") or "").startswith("d1-")
        or not str(label.get("sentence") or "").strip()
        or not isinstance(label.get("supported"), bool)
        or label.get("annotator") != "agent"
    ]
    if invalid:
        raise ValueError(
            "all labels require D1 sample_id, sentence, boolean supported, and "
            f"annotator=agent; invalid indexes: {invalid[:10]}"
        )
    return labels


def score_labels(
    labels: list[dict[str, Any]],
    records: dict[str, dict[str, Any]],
    chunk_text: dict[str, str],
    embedder: Any,
) -> list[dict[str, Any]]:
    """Batch the same lexical/embedding max used by GroundingScorer.

    Calibration has many claims sharing ten D1 contexts. Encoding per claim is
    semantically identical but needlessly slow on CPU, so contexts and claims
    are each encoded once.
    """
    contexts_by_sample: dict[str, list[str]] = {}
    unique_contexts: list[str] = []
    context_index: dict[str, int] = {}
    for label in labels:
        sample_id = str(label["sample_id"])
        if sample_id in contexts_by_sample:
            continue
        record = records[sample_id]
        contexts = [
            chunk_text[chunk_id]
            for chunk_id in record.get("used_chunks") or []
            if chunk_id in chunk_text
        ]
        contexts_by_sample[sample_id] = contexts
        for context in contexts:
            if context not in context_index:
                context_index[context] = len(unique_contexts)
                unique_contexts.append(context)

    context_embeddings = np.asarray(embedder.embed_passages(unique_contexts), dtype=float)
    claim_embeddings = np.asarray(
        embedder.embed_passages([str(label["sentence"]) for label in labels]),
        dtype=float,
    )
    scored: list[dict[str, Any]] = []
    for label, claim_embedding in zip(labels, claim_embeddings):
        contexts = contexts_by_sample[str(label["sample_id"])]
        if not contexts:
            scored.append({
                **label,
                "score": 0.0,
                "lexical_score": 0.0,
                "semantic_score": 0.0,
                "best_context_index": None,
            })
            continue
        indices = [context_index[context] for context in contexts]
        lexical_scores = [
            _lexical_context_score(str(label["sentence"]), context)
            for context in contexts
        ]
        semantic_scores = _cosines(claim_embedding, context_embeddings[indices]).tolist()
        combined = [
            max(lexical, semantic)
            for lexical, semantic in zip(lexical_scores, semantic_scores)
        ]
        best_index = int(np.argmax(combined))
        scored.append({
            **label,
            "score": round(float(combined[best_index]), 4),
            "lexical_score": round(float(lexical_scores[best_index]), 4),
            "semantic_score": round(float(semantic_scores[best_index]), 4),
            "best_context_index": best_index,
        })
    return scored


def evaluate_thresholds(
    scored: list[dict[str, Any]], thresholds: list[float]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        tp = fp = fn = tn = 0
        for item in scored:
            predicted = float(item["score"]) >= threshold
            expected = bool(item["supported"])
            tp += int(predicted and expected)
            fp += int(predicted and not expected)
            fn += int(not predicted and expected)
            tn += int(not predicted and not expected)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        specificity = tn / (tn + fp) if tn + fp else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({
            "threshold": threshold,
            "predicted_grounded_rate": round((tp + fp) / len(scored), 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "specificity": round(specificity, 4),
            "balanced_accuracy": round((recall + specificity) / 2, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        })
    return rows


def select_threshold(
    sweep: list[dict[str, Any]],
    min_specificity: float = 0.50,
    min_precision: float = 0.75,
) -> dict[str, Any]:
    """Choose F1 only among thresholds that retain negative discrimination."""
    eligible = [
        row for row in sweep
        if float(row.get("specificity") or 0.0) >= min_specificity
        and float(row.get("precision") or 0.0) >= min_precision
    ]
    candidates = eligible or sweep
    return max(
        candidates,
        key=lambda row: (
            row["f1"], row.get("balanced_accuracy", 0.0),
            row["precision"], row["threshold"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--labels", default="evaluation/configs/grounding_d1_manual_labels.json"
    )
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    labels_path = (ROOT / args.labels).resolve()
    payload = json.loads(labels_path.read_text(encoding="utf-8"))
    if Path(payload.get("dataset", "")).name != "d1_dev_seed.jsonl":
        parser.error("grounding threshold tuning is restricted to D1")
    try:
        labels = validate_label_payload(payload)
    except ValueError as exc:
        parser.error(str(exc))

    artifact_path = (ROOT / payload["artifact"]).resolve()
    records = {row["sample_id"]: row for row in read_jsonl(artifact_path)}
    with (ROOT / "data" / "bm25_index.pkl").open("rb") as handle:
        index = pickle.load(handle)  # noqa: S301 - trusted local repo artifact
    chunk_text = dict(zip(index["chunk_ids"], index["texts"]))

    from acne_llm.config import settings
    from acne_llm.rag.embedder import Embedder

    embedder = Embedder(
        model_name=settings.embedding_model,
        device=settings.device,
        lazy=True,
    )
    scored = score_labels(labels, records, chunk_text, embedder)

    sweep = evaluate_thresholds(
        scored, [round(value / 100, 2) for value in range(30, 91, 5)]
    )
    selected = select_threshold(sweep)
    unconstrained_f1_best = max(
        sweep,
        key=lambda row: (row["f1"], row["precision"], row["threshold"]),
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir) if args.out_dir else (
        REPORTS_DIR / "unit" / "grounding_threshold" / timestamp
    )
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {
        "dataset": payload["dataset"],
        "split": "D1",
        "artifact": payload["artifact"],
        "n_manually_labeled_sentences": len(scored),
        "label_policy": payload.get("label_policy"),
        "annotator": "agent",
        "not_human_gold": True,
        "label_origin_counts": {
            origin: sum(label.get("label_origin") == origin for label in labels)
            for origin in sorted({str(label.get("label_origin")) for label in labels})
        },
        "score_combination": "max(char_3gram_dice_by_context_sentence, embedding_cosine)",
        "threshold_sweep": sweep,
        "selected_threshold": selected["threshold"],
        "selection_rule": (
            "max F1 subject to specificity>=0.50 and precision>=0.75; "
            "protects negation/refutation negatives from class-imbalance collapse"
        ),
        "unconstrained_f1_best_threshold": unconstrained_f1_best["threshold"],
        "manual_precision_estimate": selected["precision"],
        "manual_recall_estimate": selected["recall"],
        "manual_specificity_estimate": selected["specificity"],
        "manual_balanced_accuracy_estimate": selected["balanced_accuracy"],
        "manual_f1_estimate": selected["f1"],
        "labels_with_scores": scored,
        "known_limitation": "negation/refutation is not resolved by similarity",
        "run_meta": build_run_meta({"labels": args.labels}),
    }
    path = out_dir / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
