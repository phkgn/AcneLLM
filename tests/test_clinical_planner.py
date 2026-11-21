"""Regression checks for the intentionally retired clinical planner."""
from pathlib import Path

from acne_llm.schemas import clinical as clinical_schemas


def test_clinical_planner_runtime_module_is_retired():
    project_root = Path(__file__).resolve().parents[1]

    assert not (project_root / "src/acne_llm/llm/clinical_planner.py").exists()


def test_clinical_planner_wire_schemas_are_retired():
    assert not hasattr(clinical_schemas, "ClinicalQueryPlan")
    assert not hasattr(clinical_schemas, "ClinicalRagQueries")
