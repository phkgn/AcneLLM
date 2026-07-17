import numpy as np

from evaluation.analysis.tune_grounding import (
    evaluate_thresholds,
    score_labels,
    select_threshold,
    validate_label_payload,
)


def test_threshold_sweep_reports_rate_precision_recall_and_f1() -> None:
    scored = [
        {"score": 0.9, "supported": True},
        {"score": 0.8, "supported": True},
        {"score": 0.7, "supported": False},
        {"score": 0.2, "supported": False},
    ]

    rows = evaluate_thresholds(scored, [0.65, 0.85])

    assert rows[0] == {
        "threshold": 0.65,
        "predicted_grounded_rate": 0.75,
        "precision": 0.6667,
        "recall": 1.0,
        "specificity": 0.5,
        "balanced_accuracy": 0.75,
        "f1": 0.8,
        "tp": 2,
        "fp": 1,
        "fn": 0,
        "tn": 1,
    }
    assert rows[1]["precision"] == 1.0
    assert rows[1]["recall"] == 0.5


def test_threshold_selection_rejects_high_f1_that_accepts_all_negatives() -> None:
    selected = select_threshold([
        {"threshold": 0.3, "f1": 0.82, "precision": 0.72, "specificity": 0.0},
        {"threshold": 0.5, "f1": 0.64, "precision": 0.79, "specificity": 0.63},
        {"threshold": 0.6, "f1": 0.30, "precision": 0.63, "specificity": 0.68},
    ])

    assert selected["threshold"] == 0.5


def test_grounding_calibration_requires_60_to_80_agent_labels() -> None:
    labels = [
        {
            "sample_id": f"d1-{index:04d}",
            "sentence": f"claim {index}",
            "supported": index % 2 == 0,
            "annotator": "agent",
        }
        for index in range(60)
    ]

    assert validate_label_payload({"labels": labels}) == labels


def test_score_labels_batches_embeddings_without_changing_max_combination() -> None:
    class FakeEmbedder:
        def __init__(self):
            self.calls: list[list[str]] = []

        def embed_passages(self, texts: list[str]) -> np.ndarray:
            self.calls.append(list(texts))
            vectors = {
                "claim": [1.0, 0.0],
                "other": [0.0, 1.0],
                "matching claim": [1.0, 0.0],
            }
            return np.asarray([vectors[text] for text in texts], dtype=float)

    embedder = FakeEmbedder()
    scored = score_labels(
        labels=[
            {"sample_id": "d1-0000", "sentence": "claim", "supported": True},
            {"sample_id": "d1-0001", "sentence": "other", "supported": False},
        ],
        records={
            "d1-0000": {"used_chunks": ["c1"]},
            "d1-0001": {"used_chunks": ["c1"]},
        },
        chunk_text={"c1": "matching claim"},
        embedder=embedder,
    )

    assert len(embedder.calls) == 2
    assert scored[0]["semantic_score"] == 1.0
    assert scored[0]["score"] == 1.0
    assert scored[1]["semantic_score"] == 0.0
