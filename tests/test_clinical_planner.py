"""Tests cho ClinicalQueryPlanner (rule-based, không LLM).

Sau refactor, ClinicalQueryPlanner không còn nhận llm/prompt trong __init__
và không gọi LLM nữa. Tất cả test liên quan đến LLM call được xóa/cập nhật.
"""
from acne_llm.llm.clinical_planner import ClinicalQueryPlanner
from acne_llm.chat.normalizer import normalize_chat_message
from acne_llm.schemas import UserInput
from acne_llm.schemas.clinical import ClinicalQueryPlan


def test_clinical_query_plan_defaults():
    plan = ClinicalQueryPlan()

    assert plan.normalized_case.inflammation_level == "unknown"
    assert plan.rag_queries.query_vi == ""
    assert plan.missing_info == []


def test_clinical_planner_no_llm_required():
    """ClinicalQueryPlanner khởi tạo được mà không cần LLM."""
    planner = ClinicalQueryPlanner()
    assert planner is not None


def test_clinical_planner_extracts_case_and_queries():
    """Planner đọc facts đã được normalizer extract, không tự normalize lại."""
    planner = ClinicalQueryPlanner()

    user = normalize_chat_message(
        "Em 22 tuổi, da dầu, mụn viêm ở cằm 4 tuần, đang dùng BHA."
    )
    plan = planner.plan(user)

    assert "papule" in plan.normalized_case.lesion_types
    assert "chin" in plan.normalized_case.distribution
    assert plan.normalized_case.demographics.age == 22
    assert plan.rag_queries.query_vi  # phải có query VI
    assert "papule" in plan.rag_queries.query_vi  # Phase A dùng VI + EN inline trong query_vi


def test_clinical_planner_returns_clinical_query_plan():
    """plan() luôn trả về ClinicalQueryPlan hợp lệ."""
    planner = ClinicalQueryPlanner()

    plan = planner.plan(UserInput(description="Em bị mụn viêm ở cằm."))

    assert isinstance(plan, ClinicalQueryPlan)
    assert plan.detected_language in ("vi", "en", "mixed", "unknown")
    # rule-based nên confidence thấp hơn LLM
    assert plan.planner_confidence <= 0.5


def test_clinical_planner_safety_terms_include_retinol():
    """Safety terms được extract đúng từ text."""
    planner = ClinicalQueryPlanner()

    plan = planner.plan(UserInput(description="Mình đang dùng retinol để trị mụn."))

    assert "retinol" in plan.safety_terms


def test_clinical_planner_plan_equals_fallback_plan():
    """plan() và fallback_plan() phải cho cùng kết quả."""
    planner = ClinicalQueryPlanner()
    user = normalize_chat_message("Mụn viêm đỏ ở má, 20 tuổi.")

    plan_a = planner.plan(user)
    plan_b = planner.fallback_plan(user)

    # Cùng lesion types và distribution
    assert set(plan_a.normalized_case.lesion_types) == set(plan_b.normalized_case.lesion_types)
    assert set(plan_a.normalized_case.distribution) == set(plan_b.normalized_case.distribution)
