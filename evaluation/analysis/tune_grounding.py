"""Tune the provisional grounding threshold on 15 manually read D1 sentences."""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from evaluation.common import (  # noqa: E402
    REPORTS_DIR,
    ROOT,
    build_run_meta,
    ensure_repo_importable,
    read_jsonl,
)
from evaluation.metrics.grounding import GroundingScorer  # noqa: E402

ensure_repo_importable()


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
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({
            "threshold": threshold,
            "predicted_grounded_rate": round((tp + fp) / len(scored), 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        })
    return rows


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
    labels = payload.get("labels") or []
    if not 10 <= len(labels) <= 15:
        parser.error("manual calibration must contain 10-15 sentences")

    artifact_path = (ROOT / payload["artifact"]).resolve()
    records = {row["sample_id"]: row for row in read_jsonl(artifact_path)}
    with (ROOT / "data" / "bm25_index.pkl").open("rb") as handle:
        index = pickle.load(handle)  # noqa: S301 - trusted local repo artifact
    chunk_text = dict(zip(index["chunk_ids"], index["texts"]))

    from acne_llm.config import settings
    from acne_llm.rag.embedder import Embedder

    scorer = GroundingScorer(embedder=Embedder(
        model_name=settings.embedding_model,
        device=settings.device,
        lazy=True,
    ), threshold=0.0)
    scored: list[dict[str, Any]] = []
    for label in labels:
        record = records[label["sample_id"]]
        contexts = [
            chunk_text[chunk_id]
            for chunk_id in record.get("used_chunks") or []
            if chunk_id in chunk_text
        ]
        result = scorer.score(label["sentence"], contexts)
        sentence_score = (result.get("sentence_scores") or [{}])[0]
        scored.append({
            **label,
            "score": sentence_score.get("score", 0.0),
            "lexical_score": sentence_score.get("lexical_score", 0.0),
            "semantic_score": sentence_score.get("semantic_score", 0.0),
            "best_context_index": sentence_score.get("best_context_index"),
        })

    sweep = evaluate_thresholds(
        scored, [round(value / 100, 2) for value in range(50, 91, 5)]
    )
    selected = max(
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
        "score_combination": "max(char_3gram_dice_by_context_sentence, embedding_cosine)",
        "threshold_sweep": sweep,
        "selected_threshold": selected["threshold"],
        "manual_precision_estimate": selected["precision"],
        "manual_recall_estimate": selected["recall"],
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
