"""Internal clinical-intake schemas for chat-only acne planning.

These models are intentionally additive. Public API responses still use
AdviseOutput, while these objects help normalize free-form chat into a stable
clinical case and bilingual RAG queries.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["mild", "moderate", "severe", "unknown"]
InflammationLevel = Literal["none", "mild", "moderate", "severe", "unknown"]


class ClinicalDemographics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Literal["male", "female", "other", "unknown"] = "unknown"
    skin_type: Literal[
        "dry", "oily", "combination", "sensitive", "normal", "unknown"
    ] = "unknown"
    is_pregnant: bool = False
    is_breastfeeding: bool = False


class NormalizedAcneCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    demographics: ClinicalDemographics = Field(default_factory=ClinicalDemographics)
    lesion_types: list[Literal[
        "comedone",
        "whitehead",
        "blackhead",
        "closed_comedone",
        "papule",
        "pustule",
        "nodule",
        "cyst",
        "scar",
        "post_inflammatory_hyperpigmentation",
        "other",
    ]] = Field(default_factory=list)
    distribution: list[Literal[
        "forehead",
        "cheeks",
        "chin",
        "jawline",
        "nose",
        "around_mouth",
        "back",
        "chest",
        "shoulders",
        "neck",
        "t_zone",
        "other",
    ]] = Field(default_factory=list)
    inflammation_level: InflammationLevel = "unknown"
    scarring_signs: list[str] = Field(default_factory=list)
    medication_history: list[str] = Field(default_factory=list)
    hormonal_factors: list[str] = Field(default_factory=list)
    skincare_products: list[str] = Field(default_factory=list)
    treatment_goals: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)


class ClinicalRagQueries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_vi: str = ""
    # M9: English query for bilingual RAG when language_switch detected
    query_en: str = ""


class ClinicalQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_language: Literal["vi", "en", "mixed", "unknown"] = "unknown"
    normalized_case: NormalizedAcneCase = Field(default_factory=NormalizedAcneCase)
    rag_queries: ClinicalRagQueries = Field(default_factory=ClinicalRagQueries)
    missing_info: list[str] = Field(default_factory=list)
    safety_terms: list[str] = Field(default_factory=list)
    planner_confidence: float = Field(default=0.5, ge=0, le=1)
