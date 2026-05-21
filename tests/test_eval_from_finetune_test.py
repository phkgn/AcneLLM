from __future__ import annotations

import json
from pathlib import Path

from acne_llm.schemas import AdviseOutput, Recommendation
from scripts.eval_from_finetune_test import (
    evaluate_generation_outputs,
    evaluate_retrieval,
    judge_text_safety,
    load_cases,
)


def _record(**metadata_overrides):
    metadata = {
        "id": "case-1",
        "sample_type": "clinical_chat_response",
        "source_chunk_id": "src::0001",
        "source_title": "Source title",
        "source_url": "https://example.test",
        "source_trust_level": "high",
        "case_type": "pregnancy_breastfeeding_safety",
        "severity": "mild",
        "safety_flags": ["pregnancy"],
        "guideline_refs": ["AAD_2024", "NICE_NG198"],
        "confidence": "high",
    }
    metadata.update(metadata_overrides)
    normalized_case = {
        "demographics": {
            "age": 22,
            "sex": "female",
            "skin_type": "oily",
            "is_pregnant": True,
            "is_breastfeeding": False,
        },
        "lesion_types": ["comedone"],
        "distribution": ["chin"],
        "inflammation_level": "mild",
        "missing_info": [],
    }
    return {
        "messages": [
            {"role": "system", "content": "system"},
            {
                "role": "user",
                "content": (
                    "<raw_user_message>Em có thai và bị mụn ở cằm</raw_user_message>\n"
                    f"<normalized_case>{json.dumps(normalized_case, ensure_ascii=False)}</normalized_case>\n"
                    "<guideline_context>Tránh retinoid trong thai kỳ.</guideline_context>"
                ),
            },
            {"role": "assistant", "content": "Không tự dùng thuốc, hãy hỏi bác sĩ."},
        ],
        "metadata": metadata,
    }


def test_load_cases_extracts_finetune_test_fields(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8")

    cases, skipped = load_cases(path)

    assert skipped == []
    assert len(cases) == 1
    case = cases[0]
    assert case.id == "case-1"
    assert case.query == "Em có thai và bị mụn ở cằm"
    assert case.expected_answer == "Không tự dùng thuốc, hãy hỏi bác sĩ."
    assert case.relevant_chunk_ids == ["src::0001"]
    assert case.guideline_context == "Tránh retinoid trong thai kỳ."
    assert case.is_pregnant is True


class _Chunk:
    def __init__(self, chunk_id: str):
        self.chunk_id = chunk_id


class _Retrieval:
    def __init__(self, ids: list[str]):
        self.chunks = [_Chunk(chunk_id) for chunk_id in ids]


class _Retriever:
    def __init__(self, ids: list[str]):
        self.ids = ids

    def retrieve(self, query: str, top_k: int = 10, mode: str = "hybrid"):
        return _Retrieval(self.ids[:top_k])


def test_evaluate_retrieval_uses_source_chunk_as_ground_truth(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    cases, _ = load_cases(path)

    result = evaluate_retrieval(cases, _Retriever(["other", "src::0001"]), mode="hybrid", top_k=2)

    assert result["evaluated"] == 1
    assert result["metrics"]["hit@1"]["mean"] == 0.0
    assert result["metrics"]["hit@3"]["mean"] == 1.0
    assert result["metrics"]["mrr@10"]["mean"] == 0.5
    assert result["breakdown"]["case_type"]["pregnancy_breastfeeding_safety"]["n"] == 1


def test_judge_text_safety_accepts_pregnancy_boundary(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    case = load_cases(path)[0][0]

    judged = judge_text_safety(
        case,
        "Bạn đang mang thai nên tránh retinoid và hỏi bác sĩ da liễu trước khi dùng thuốc.",
    )

    assert judged["safety_ok"] is True
    assert judged["checks"]["pregnancy_boundary_ok"] is True


def test_generation_eval_checks_severity_and_safety(tmp_path: Path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(_record(severity="mild"), ensure_ascii=False) + "\n", encoding="utf-8")
    case = load_cases(path)[0][0]
    output = AdviseOutput(
        severity="mild",
        recommendations=[
            Recommendation(
                step=1,
                action="Tránh retinoid trong thai kỳ và hỏi bác sĩ da liễu.",
                category="see_doctor",
            )
        ],
    )

    result = evaluate_generation_outputs([case], {case.id: output})

    assert result["evaluated"] == 1
    assert result["severity_accuracy"] == 1.0
    assert result["safety_compliance"] == 1.0
