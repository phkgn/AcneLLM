from evaluation.analysis.tune_grounding import evaluate_thresholds


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
        "f1": 0.8,
        "tp": 2,
        "fp": 1,
        "fn": 0,
        "tn": 1,
    }
    assert rows[1]["precision"] == 1.0
    assert rows[1]["recall"] == 0.5
