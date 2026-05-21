from pathlib import Path
from unittest.mock import MagicMock

from acne_llm.llm.clinical_planner import ClinicalQueryPlanner
from acne_llm.llm.prompt_builder import PromptBuilder
from acne_llm.schemas import UserInput
from acne_llm.schemas.clinical import ClinicalQueryPlan


PROMPTS = str(Path(__file__).resolve().parents[1] / "config" / "prompts")


def test_clinical_query_plan_defaults():
    plan = ClinicalQueryPlan()

    assert plan.normalized_case.inflammation_level == "unknown"
    assert plan.rag_queries.query_vi == ""
    assert plan.missing_info == []


def test_clinical_planner_fallback_extracts_case_and_queries():
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("planner unavailable")
    planner = ClinicalQueryPlanner(llm=llm, prompt=PromptBuilder(PROMPTS))

    plan = planner.plan(UserInput(
        description="Em 22 tuổi, da dầu, mụn viêm ở cằm 4 tuần, đang dùng BHA."
    ))

    assert "papule" in plan.normalized_case.lesion_types
    assert "chin" in plan.normalized_case.distribution
    assert plan.normalized_case.demographics.age == 22
    assert plan.rag_queries.query_vi
    assert plan.rag_queries.query_en


def test_clinical_planner_clamps_out_of_range_confidence_without_fallback():
    llm = MagicMock()
    llm.generate_json.return_value = ClinicalQueryPlan(
        detected_language="vi",
        planner_confidence=1.0,
    ).model_dump_json().replace('"planner_confidence":1.0', '"planner_confidence":3')
    planner = ClinicalQueryPlanner(llm=llm, prompt=PromptBuilder(PROMPTS))

    plan = planner.plan(UserInput(description="Em bị mụn viêm ở cằm."))

    assert plan.planner_confidence == 1.0
    assert llm.generate_json.call_count == 1


def test_clinical_planner_parses_markdown_fenced_json():
    llm = MagicMock()
    llm.generate_json.return_value = (
        "```json\n"
        + ClinicalQueryPlan(
            detected_language="vi",
            planner_confidence=0.7,
        ).model_dump_json()
        + "\n```"
    )
    planner = ClinicalQueryPlanner(llm=llm, prompt=PromptBuilder(PROMPTS))

    plan = planner.plan(UserInput(description="Em bị mụn viêm ở cằm."))

    assert plan.detected_language == "vi"
    assert plan.planner_confidence == 0.7
    assert llm.generate_json.call_count == 1


def test_clinical_planner_safety_terms_include_retinol():
    llm = MagicMock()
    llm.generate_json.side_effect = RuntimeError("planner unavailable")
    planner = ClinicalQueryPlanner(llm=llm, prompt=PromptBuilder(PROMPTS))

    plan = planner.plan(UserInput(description="Mình đang dùng retinol để trị mụn."))

    assert "retinol" in plan.safety_terms
