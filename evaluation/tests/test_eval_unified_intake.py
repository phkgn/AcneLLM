import json
import random

from acne_llm.chat.preprocess import prepare_user_text
from acne_llm.chat.unified_intake import UnifiedIntake
from scripts.eval_unified_intake import evaluate_rows


class _MockBackend:
    def __init__(self, response: str):
        self.response = response

    def generate_text(self, **_kwargs) -> str:
        return self.response

    def close(self) -> None:
        return None


def _record() -> dict:
    text = "Da tôi dầu và có mụn đỏ ở cằm"
    gold = {
        "intent": "advise",
        "confidence": 0.9,
        "description": text,
        "context": {},
        "clinical": None,
    }
    return {
        "id": "fuzz-1",
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": text},
            {"role": "assistant", "content": json.dumps(gold)},
        ],
        "meta": {"case_type": "advise_selfreport_simple"},
    }


def test_evaluator_fuzz_khong_crash_voi_backend_mock():
    rng = random.Random(42)
    responses = ["not-json", "[]", "null", "{}"]
    for _ in range(40):
        responses.append(
            json.dumps(
                {
                    "intent": rng.choice(["advise", "invented", [], None]),
                    "confidence": rng.choice([-1, 0.5, 2, None]),
                    "context": rng.choice([{}, [], {"sex": ["bad"]}]),
                    "clinical": rng.choice(
                        [None, [], {"lesion_types": [[], {"value": {}}]}]
                    ),
                }
            )
        )

    for response in responses:
        intake = UnifiedIntake(_MockBackend(response), model="mock", timeout=1)

        def infer(text: str):
            prepared = prepare_user_text(text)
            intake._cache_key = None
            intake._cache_value = None
            return intake._infer(prepared.clean_text, [])

        report = evaluate_rows([_record()], infer)
        assert report["rows_evaluated"] == 1
        assert report["fallback_executed"] is False


def test_evaluator_reports_format_intent_extraction_and_latency_layers():
    def record(sample_id: str, text: str) -> dict:
        gold = {
            "intent": "advise",
            "confidence": 0.9,
            "description": text,
            "context": {
                "current_products": [
                    {"value": "benzoyl peroxide", "confidence": 0.9}
                ]
            },
            "clinical": None,
        }
        return {
            "id": sample_id,
            "messages": [
                {"role": "user", "content": text},
                {"role": "assistant", "content": json.dumps(gold)},
            ],
        }

    rows = [
        record("valid", "valid"),
        record("parse", "parse"),
        record("schema", "schema"),
    ]

    def infer(text: str) -> dict:
        if text == "parse":
            raise json.JSONDecodeError("bad", "x", 0)
        if text == "schema":
            return {}
        return {
            "intent": "advise",
            "confidence": 0.9,
            "description": text,
            "context": {
                "current_products": [
                    {"value": "benzoyl peroxde", "confidence": 0.9}
                ]
            },
            "clinical": None,
        }

    report = evaluate_rows(rows, infer)
    metrics = report["metrics"]
    assert metrics["format"]["schema_valid_rate"] == 0.3333
    assert metrics["format"]["parse_fail_rate"] == 0.3333
    assert metrics["format"]["schema_violation_rate"] == 0.3333
    assert metrics["intent"]["accuracy"] == 0.3333
    assert set(metrics["intent"]["per_class"]) == {
        "advise",
        "knowledge",
        "clarify",
        "reject",
    }
    assert metrics["extraction"]["per_field"]["context.current_products"]["match"] == "fuzzy"
    assert metrics["extraction"]["per_field"]["context.current_products"]["tp"] == 1
    assert metrics["latency"]["p50_ms"] >= 0
    assert metrics["latency"]["p95_ms"] >= metrics["latency"]["p50_ms"]
