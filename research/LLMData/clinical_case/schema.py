"""Schema for clinical-case fine-tuning assistant outputs."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from acne_llm.schemas.clinical import NormalizedAcneCase, Severity


class ClinicalCaseRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "skincare",
        "otc_info",
        "prescription_boundary",
        "see_doctor",
        "lifestyle",
        "safety",
        "other",
    ] = "other"
    action: str
    rationale: Optional[str] = None
    guideline_refs: list[str] = Field(default_factory=list)


class GuidelineAlignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["aligned", "partial", "insufficient_info"] = "insufficient_info"
    refs: list[str] = Field(default_factory=list)
    notes: str = ""


class ClinicalCaseTrainingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_case: NormalizedAcneCase = Field(default_factory=NormalizedAcneCase)
    severity: Severity = "unknown"
    severity_rationale: str = ""
    recommendations: list[ClinicalCaseRecommendation] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    guideline_alignment: GuidelineAlignment = Field(default_factory=GuidelineAlignment)
    safety_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
