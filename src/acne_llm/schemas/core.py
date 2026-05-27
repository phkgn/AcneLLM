"""Core schemas — contract với vision (đề tài 27) và RAG (đề tài 28)."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


# ─────────── Vision ───────────

class VisionLesion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["comedone", "papule", "pustule", "nodule", "cyst", "scar", "other"]
    bbox: Optional[list[float]] = None  # [x, y, w, h] normalized
    confidence: float = Field(ge=0, le=1)


class VisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    severity_estimate: Literal["mild", "moderate", "severe", "unknown"] = "unknown"
    lesion_counts: dict[str, int] = Field(default_factory=dict)
    lesions: list[VisionLesion] = Field(default_factory=list)
    skin_regions: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    model_name: str = "mock"
    confidence: float = Field(ge=0, le=1, default=0.5)


# ─────────── User Input ───────────

class UserContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[Literal["male", "female", "other"]] = None
    skin_type: Optional[Literal["dry", "oily", "combination", "sensitive", "normal"]] = None
    is_pregnant: bool = False
    is_breastfeeding: bool = False
    allergies: list[str] = Field(default_factory=list)
    current_products: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    duration_weeks: Optional[int] = None

class AcneClinicalInput(BaseModel):
    """Optional structured acne intake data.

    This is additive: legacy clients can keep sending description/context only.
    """
    model_config = ConfigDict(extra="forbid")
    lesion_types: list[Literal[
        "whitehead",
        "blackhead",
        "closed_comedone",
        "papule",
        "pustule",
        "nodule",
        "cyst",
        "hidden_acne",
        "scar",
        "post_inflammatory_hyperpigmentation",
        "other",
    ]] = Field(default_factory=list)
    lesion_distribution: list[Literal[
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
    inflammation_level: Optional[Literal[
        "none", "mild", "moderate", "severe", "unknown",
    ]] = None
    scarring_signs: list[str] = Field(default_factory=list)
    medication_history: list[str] = Field(default_factory=list)
    hormonal_factors: list[str] = Field(default_factory=list)
    skincare_products: list[str] = Field(default_factory=list)
    canonical_ingredients: list[str] = Field(default_factory=list)
    usage_frequencies: list[str] = Field(default_factory=list)
    concentrations: list[float] = Field(default_factory=list)
    treatment_goals: list[str] = Field(default_factory=list)
    red_flags_input: list[str] = Field(default_factory=list)


class UserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=4000)
    context: UserContext = Field(default_factory=UserContext)
    clinical: Optional[AcneClinicalInput] = None
    vision: Optional[VisionOutput] = None
    mode: Literal["llm_only", "hybrid"] = "hybrid"


# ─────────── Retrieval ───────────

class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    source: str
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class RetrievalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    chunks: list[RetrievedChunk]
    retrieval_mode: Literal["dense", "sparse", "hybrid", "rerank"] = "hybrid"
    num_chunks: int = 0
    avg_score: float = 0.0


# ─────────── Advise Output ───────────

class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: int = Field(ge=1)
    action: str
    rationale: Optional[str] = None
    source_chunk_id: Optional[str] = None
    category: Literal[
        "skincare", "medication", "lifestyle", "procedure", "see_doctor", "other"
    ] = "other"


class RedFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flag: str
    severity: Literal["info", "warn", "urgent"] = "warn"
    reason: Optional[str] = None


class AdviseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())
    severity: Literal["mild", "moderate", "severe", "unknown"] = "unknown"
    acne_type_primary: str = "unknown"
    causes: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)
    used_chunks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)
    disclaimer: str = "Thông tin mang tính tham khảo, không thay thế chẩn đoán từ bác sĩ."
    mode: Literal["llm_only", "hybrid"] = "hybrid"
    model_name: str = ""
    latency_ms: int = 0
