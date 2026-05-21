from LLMData.clinical_case.schema import (
    ClinicalCaseRecommendation,
    ClinicalCaseTrainingOutput,
)
from LLMData.clinical_case.generator import generate_records
from LLMData.clinical_case.validator import validate_record


def _record(output: ClinicalCaseTrainingOutput) -> dict:
    return {
        "messages": [
            {"role": "system", "content": "Bạn là AcneLLM"},
            {"role": "user", "content": "Em bị mụn bọc đau và có sẹo"},
            {"role": "assistant", "content": output.model_dump_json()},
        ]
    }


def test_clinical_dataset_validator_accepts_safe_record():
    output = ClinicalCaseTrainingOutput(
        severity="severe",
        recommendations=[
            ClinicalCaseRecommendation(
                category="see_doctor",
                action="Đi khám bác sĩ da liễu để được đánh giá và điều trị phù hợp.",
                guideline_refs=["AAD_2024"],
            )
        ],
    )

    ok, reason, parsed = validate_record(_record(output))

    assert ok is True
    assert reason == "ok"
    assert parsed is not None


def test_clinical_dataset_validator_rejects_rx_dose():
    output = ClinicalCaseTrainingOutput(
        severity="moderate",
        recommendations=[
            ClinicalCaseRecommendation(
                category="prescription_boundary",
                action="Dùng isotretinoin 0.5 mg/kg/ngày.",
            )
        ],
    )

    ok, reason, _ = validate_record(_record(output))

    assert ok is False
    assert reason == "rx_dose_or_frequency"


def test_clinical_dataset_validator_rejects_non_json_assistant():
    record = {
        "messages": [
            {"role": "assistant", "content": "không phải json"},
        ]
    }

    ok, reason, _ = validate_record(record)

    assert ok is False
    assert reason == "assistant_content_not_json"


def test_clinical_dataset_validator_allows_safe_refusal_wording():
    output = ClinicalCaseTrainingOutput(
        severity="unknown",
        recommendations=[
            ClinicalCaseRecommendation(
                category="prescription_boundary",
                action="Không nên tự mua kháng sinh trị mụn; cần bác sĩ da liễu đánh giá.",
                rationale="Tránh tự dùng kháng sinh không phù hợp.",
                guideline_refs=["AAD_2024", "NICE_NG198"],
            )
        ],
    )

    ok, reason, _ = validate_record(_record(output))

    assert ok is True
    assert reason == "ok"


def test_clinical_case_generator_outputs_valid_records():
    records = generate_records()

    assert len(records) >= 10
    for record in records:
        ok, reason, parsed = validate_record(record)
        assert ok is True, reason
        assert parsed is not None
