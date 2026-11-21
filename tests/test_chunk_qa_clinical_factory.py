import json
import re
from types import SimpleNamespace

import pytest

from acne_llm.schemas.clinical import NormalizedAcneCase
from LLMData.chunk_qa.config import Config
from LLMData.chunk_qa.generator import generate_cases_for_chunk
from LLMData.chunk_qa.loader import _authority_score, _is_eligible
from LLMData.chunk_qa.rule_filter import apply_rules_with_context
from LLMData.chunk_qa.safety_cases import build_curated_safety_samples
from LLMData.chunk_qa.writer import build_record


class _FakeCompletions:
    async def create(self, **kwargs):
        payload = {
            "items": [
                {
                    "raw_user_message": "Em bị mụn bọc đau ở cằm và có sẹo.",
                    "normalized_case": {
                        "demographics": {
                            "age": None,
                            "sex": "unknown",
                            "skin_type": "unknown",
                            "is_pregnant": False,
                            "is_breastfeeding": False,
                        },
                        "lesion_types": ["nodule", "scar"],
                        "distribution": ["chin"],
                        "inflammation_level": "severe",
                        "scarring_signs": ["sẹo mới"],
                        "medication_history": [],
                        "hormonal_factors": [],
                        "skincare_products": [],
                        "treatment_goals": ["ngừa sẹo"],
                        "red_flags": ["scarring_risk"],
                        "missing_info": ["age", "duration"],
                    },
                    "guideline_context": "Mụn nốt đau hoặc có sẹo nên được bác sĩ da liễu đánh giá.",
                    "assistant_answer": (
                        "Mô tả của bạn có dấu hiệu mụn viêm sâu và nguy cơ sẹo. "
                        "Bạn nên gặp bác sĩ da liễu sớm để được đánh giá trực tiếp, "
                        "đồng thời tránh tự nặn hoặc tự dùng thuốc kê đơn."
                    ),
                    "case_type": "severe_nodular_scarring",
                    "severity": "severe",
                    "safety_flags": ["dermatology_referral"],
                    "guideline_refs": ["AAD_2024", "NICE_NG198"],
                    "confidence": "high",
                }
            ]
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )


class _FakeClient:
    chat = SimpleNamespace(completions=_FakeCompletions())


@pytest.mark.asyncio
async def test_generate_cases_for_chunk_parses_normalized_case():
    cfg = Config()
    cfg.cases_per_chunk = 1

    out = await generate_cases_for_chunk(
        _FakeClient(),
        cfg,
        {
            "chunk_id": "guideline::0001",
            "text": "Severe nodular acne and scarring should be assessed by a dermatologist.",
            "source_name": "NICE NG198",
            "trust_level": "high",
            "tags": ["guidelines"],
        },
    )

    assert len(out) == 1
    NormalizedAcneCase.model_validate(out[0]["normalized_case"])
    assert out[0]["severity"] == "severe"
    assert "AAD_2024" in out[0]["guideline_refs"]


def test_writer_builds_runtime_like_chat_record():
    item = build_curated_safety_samples()[0]
    record = build_record(
        item=item,
        rule_filter={"passed": True, "reason": ""},
        source_chunk={"chunk_id": "x::1", "title": "Guideline", "url": "u", "trust_level": "high"},
    )

    assert record["sample_type"] == "clinical_chat_response"
    roles = [m["role"] for m in record["messages"]]
    assert roles == ["system", "user", "assistant"]
    user_content = record["messages"][1]["content"]
    assert "<raw_user_message>" in user_content
    assert "<normalized_case>" in user_content
    assert "<guideline_context>" in user_content
    case_json = re.search(r"<normalized_case>(.*?)</normalized_case>", user_content, re.S).group(1)
    NormalizedAcneCase.model_validate(json.loads(case_json))


def test_loader_scores_high_trust_guideline_chunks():
    cfg = Config()
    chunk = {
        "chunk_id": "official_guideline::0001",
        "language": "en",
        "text": "acne vulgaris guideline management " * 20,
        "trust_level": "high",
        "source_name": "NICE NG198",
        "tags": ["guidelines", "high-trust"],
        "categories": ["acne", "guidelines"],
    }

    assert _is_eligible(chunk, cfg) is True
    assert _authority_score(chunk) >= 5


def test_final_answer_rules_reject_unsafe_patterns():
    severe_case = {
        "demographics": {
            "age": None,
            "sex": "unknown",
            "skin_type": "unknown",
            "is_pregnant": False,
            "is_breastfeeding": False,
        },
        "lesion_types": ["nodule"],
        "distribution": ["chin"],
        "inflammation_level": "severe",
        "scarring_signs": [],
        "medication_history": [],
        "hormonal_factors": [],
        "skincare_products": [],
        "treatment_goals": [],
        "red_flags": [],
        "missing_info": [],
    }

    assert not apply_rules_with_context(
        "Bạn có thể dùng isotretinoin 20 mg mỗi ngày.",
        normalized_case=severe_case,
        severity="severe",
    )["passed"]
    assert not apply_rules_with_context(
        "Bạn chỉ cần kháng sinh uống để trị mụn.",
        normalized_case=severe_case,
        severity="moderate",
    )["passed"]
    assert not apply_rules_with_context(
        "Bạn nên dưỡng ẩm và theo dõi thêm.",
        normalized_case=severe_case,
        severity="severe",
    )["passed"]


def test_curated_safety_samples_pass_rules():
    for item in build_curated_safety_samples():
        res = apply_rules_with_context(
            item["assistant_answer"],
            item["raw_user_message"],
            normalized_case=item["normalized_case"],
            severity=item["severity"],
        )
        assert res["passed"], res
