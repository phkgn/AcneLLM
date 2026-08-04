import json

import pytest

from evaluation.runners.run_ablation import (
    _OracleIntake,
    _paired_summary,
    _select_candidate,
    main,
    summarize_report,
)


def _scorecard(value: float = 3.0, *, safety_pass: bool = True) -> dict:
    return {
        "answer_quality": value,
        "role_tone": value,
        "context_relevance": value,
        "context_precision": value / 5,
        "context_sufficiency": value,
        "ranking_quality": value / 5,
        "groundedness": value,
        "safety_pass": safety_pass,
        "refusal_fidelity": True,
    }


def _row(sample_id: str, value: float = 3.0, *, ok: bool = True) -> dict:
    return {
        "sample_id": sample_id,
        "ok": ok,
        "error": None if ok else "ReadTimeout: timed out",
        "scorecard": _scorecard(value) if ok else None,
        "safety_fail": False if ok else None,
    }


def test_arm_y_always_selects_candidate_zero_not_judge_median():
    judged = [
        ("first", {"answer_quality": 1}),
        ("best", {"answer_quality": 5}),
        ("middle", {"answer_quality": 3}),
    ]
    assert _select_candidate(judged) == judged[0]


def test_oracle_rejects_qrels_instead_of_guessing_intent():
    oracle = _OracleIntake()
    oracle.set_sample(
        {"sample_id": "d8-0001", "task_type": "retrieval_qrels"}
    )
    with pytest.raises(ValueError, match="intent_label vàng"):
        oracle._intent()


def test_arm_x_preflight_stops_before_creating_output(tmp_path):
    dataset = tmp_path / "qrels.jsonl"
    output = tmp_path / "result.json"
    dataset.write_text(
        json.dumps(
            {
                "sample_id": "d8-0001",
                "user_query": "BPO có dùng được không?",
                "task_type": "retrieval_qrels",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Không mẫu nào đã được chạy"):
        main(
            [
                "--arms",
                "ORR",
                "--dataset",
                str(dataset),
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_oracle_injected_fields_receive_exact_confidence():
    oracle = _OracleIntake()
    oracle.set_sample(
        {
            "sample_id": "intake-1",
            "intent_label": "advise",
            "user_context": {
                "age": 31,
                "skin_type": "sensitive",
                "allergies": ["benzoyl_peroxide"],
                "unsupported_gold": "visible in trace",
            },
        }
    )
    oracle.classify("Da em hay kích ứng", [])
    result = oracle.run(
        clean_text="Da em hay kích ứng",
        clean_text_no_accent="Da em hay kich ung",
        mode="hybrid",
        history=[],
    )

    assert oracle.injected_fields == ["age", "allergies", "skin_type"]
    assert oracle.ignored_fields == ["unsupported_gold"]
    assert result.confidence.age.confidence == 1.0
    assert result.confidence.skin_type.confidence == 1.0
    assert result.confidence.allergies.items[0].confidence == 1.0


def test_paired_summary_drops_failed_id_only_from_the_affected_arm():
    arms = {
        "RRR": {
            "items": [_row("a", 2), _row("b", 3), _row("c", 4)],
            "summary": {"safety_failures": 0},
        },
        "ROR": {
            "items": [_row("a", 3), _row("b", ok=False), _row("c", 4)],
            "summary": {"safety_failures": 0},
        },
        "RRO": {
            "items": [_row("a", 4), _row("b", 4), _row("c", 5)],
            "summary": {"safety_failures": 0},
        },
    }

    paired = _paired_summary(arms)

    # Ghép cặp RIÊNG từng arm: ROR hỏng ở "b" không được rút mẫu của RRO.
    assert paired["ROR"]["paired_n"] == 2
    assert paired["ROR"]["dropped_ids"] == ["b"]
    assert paired["ROR"]["drop_reason"]["b"] == ["ROR:ReadTimeout: timed out"]
    assert paired["RRO"]["paired_n"] == 3
    assert paired["RRO"]["dropped_ids"] == []

    from evaluation.metrics.scorecard import SCORECARD_FACES
    for arm in arms:
        assert set(row["face"] for row in paired[arm]["faces"]) == set(SCORECARD_FACES)


def test_summarize_report_adds_bootstrap_ci_and_keeps_safety_separate():
    report = {
        "schema_version": 2,
        "experiment": "paired_ablation",
        "dataset": "d8.jsonl",
        "arms": {
            "RRR": {
                "items": [_row("a", 2), _row("b", 3), _row("c", 4)],
                "summary": {"safety_failures": 0},
            },
            "ROR": {
                "items": [_row("a", 3), _row("b", 4), _row("c", 5)],
                "summary": {"safety_failures": 0},
            },
        },
    }

    summary = summarize_report(report, bootstrap_samples=100, seed=7)

    quality = summary["arms"]["ROR"]["quality"]["answer_quality"]
    assert quality["mean_delta"] == 1.0
    assert quality["bootstrap_95_ci_mean"] == [1.0, 1.0]
    assert summary["arms"]["ROR"]["safety"] == {
        "paired_n": 3,
        "baseline_fail_count": 0,
        "arm_fail_count": 0,
        "baseline_fail_ids": [],
        "arm_fail_ids": [],
    }
