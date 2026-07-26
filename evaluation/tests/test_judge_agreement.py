import json

from scripts.judge_agreement import export_review, score_review


def _artifact() -> dict:
    arms = {}
    for arm_index, arm in enumerate(("z", "x", "w", "y")):
        items = []
        for index in range(10):
            ordinal = (index % 5) + 1
            binary = index % 2 == 0
            items.append(
                {
                    "sample_id": f"{arm}-{index:02d}",
                    "user_query": f"question {arm}-{index}",
                    "answer": f"answer {arm}-{index}",
                    "ok": True,
                    "scorecard": {
                        "grounding_support": ordinal / 5,
                        "safety_pass": binary,
                        "refusal_fidelity": binary,
                        "answer_quality": ordinal,
                        "role_tone": ordinal,
                    },
                    "trace": {
                        "primary_intent": "knowledge",
                        "context_chunks": [{"text": f"context {arm_index}-{index}"}],
                    },
                }
            )
        arms[arm] = {"items": items}
    return {
        "schema_version": 2,
        "dataset": "evaluation/datasets/v1/synthetic.jsonl",
        "arms": arms,
    }


def test_export_40_is_blind_stratified_and_scores_arm_y_separately(tmp_path):
    artifact = tmp_path / "artifact.json"
    review = tmp_path / "review.jsonl"
    key = tmp_path / "review.key.json"
    agreement = tmp_path / "agreement.json"
    artifact.write_text(json.dumps(_artifact()), encoding="utf-8")

    exported = export_review([artifact], review, key, limit=40, seed=42)
    rows = [json.loads(line) for line in review.read_text(encoding="utf-8").splitlines()]
    key_rows = json.loads(key.read_text(encoding="utf-8"))["rows"]

    assert exported["rows"] == 40
    assert exported["arm_counts"] == {"z": 10, "x": 10, "w": 10, "y": 10}
    assert all("machine_scorecard" not in row for row in rows)

    machine_by_id = {row["review_id"]: row["machine_scorecard"] for row in key_rows}
    for row in rows:
        machine = machine_by_id[row["review_id"]]
        row["human_scores"] = {
            "grounding_support": int(round(machine["grounding_support"] * 5)),
            "safety_pass": machine["safety_pass"],
            "refusal_fidelity": machine["refusal_fidelity"],
            "answer_quality": machine["answer_quality"],
            "role_tone": machine["role_tone"],
        }
    review.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )

    result = score_review(review, key, agreement)

    assert result["rows"] == 40
    assert result["overall"]["judge_usable"] is True
    assert result["arm_y"]["judge_usable"] is True
    assert result["arm_y"]["faces"]["safety_pass"]["n"] == 10
