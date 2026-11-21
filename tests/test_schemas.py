from acne_llm.schemas import (
    UserInput, AcneClinicalInput,
    AdviseOutput, Recommendation, RedFlag, VisionOutput,
)


def test_user_input_minimal():
    u = UserInput(description="Em bị mụn ở cằm")
    assert u.mode == "hybrid"
    assert u.context.is_pregnant is False
    assert u.clinical is None


def test_user_input_validation_empty():
    import pytest
    with pytest.raises(Exception):
        UserInput(description="")


def test_user_input_clinical_optional_full():
    u = UserInput(
        description="Em bị mụn viêm ở cằm",
        clinical=AcneClinicalInput(
            lesion_types=["whitehead", "papule", "pustule", "closed_comedone"],
            lesion_distribution=["chin", "cheeks"],
            inflammation_level="moderate",
            scarring_signs=["dark_marks"],
            medication_history=["benzoyl peroxide"],
            hormonal_factors=["menstrual_flare"],
            skincare_products=["BHA 2%"],
            canonical_ingredients=["salicylic_acid"],
            usage_frequencies=["twice_daily"],
            concentrations=[0.02],
            treatment_goals=["reduce_inflammation"],
            red_flags_input=[],
        ),
    )
    assert u.clinical is not None
    assert "papule" in u.clinical.lesion_types
    assert u.clinical.inflammation_level == "moderate"
    assert u.clinical.canonical_ingredients == ["salicylic_acid"]
    assert u.clinical.usage_frequencies == ["twice_daily"]
    assert u.clinical.concentrations == [0.02]


def test_user_input_clinical_rejects_invalid_lesion():
    import pytest
    with pytest.raises(Exception):
        UserInput(
            description="Em bị mụn",
            clinical={"lesion_types": ["invalid_acne_type"]},
        )


def test_advise_output_roundtrip():
    out = AdviseOutput(
        severity="moderate",
        acne_type_primary="papule",
        causes=["tắc nghẽn nang lông"],
        recommendations=[Recommendation(step=1, action="rửa mặt 2 lần/ngày")],
        red_flags=[RedFlag(flag="cẩn thận", severity="warn")],
        confidence=0.7,
    )
    dumped = out.model_dump_json()
    back = AdviseOutput.model_validate_json(dumped)
    assert back.severity == "moderate"
    assert back.recommendations[0].step == 1


def test_vision_output_default():
    v = VisionOutput()
    assert v.severity_estimate == "unknown"
    assert v.confidence == 0.5
