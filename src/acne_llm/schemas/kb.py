"""Knowledge base schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class SourceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    source_name: str
    trust_level: Literal["high", "medium", "low"] = "medium"
    language: Literal["vi", "en"] = "vi"
    crawled_at: datetime
    robots_allowed: bool = True
    license: Optional[str] = None


class DocumentRaw(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    url: str
    title: str
    text: str
    html_len: int = 0
    text_len: int = 0
    source: SourceMeta
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    summary: Optional[str] = None
    quality_score: float = Field(ge=0, le=1, default=0.5)


class KBChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    doc_id: str
    text: str
    text_len: int = 0
    position: int = 0
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None

    url: str
    title: str
    source_name: str
    trust_level: Literal["high", "medium", "low"] = "medium"
    language: Literal["vi", "en"] = "vi"
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    embedding: Optional[list[float]] = None


class LLMData(BaseModel):
    """Alpaca-style fine-tuning record produced from crawled content.

    instruction: derived from article title (acts as the user prompt)
    input:       empty string (no additional context needed for augmentation)
    output:      cleaned article text (the expected model response)
    metadata:    provenance for filtering/dedup downstream
    """
    model_config = ConfigDict(extra="forbid")
    id: str
    instruction: str
    input: str = ""
    output: str
    metadata: dict = Field(default_factory=dict)


Intent = Literal[
    "ask_cause",        # Nguyên nhân gây mụn
    "ask_symptoms",     # Dấu hiệu, triệu chứng nhận biết
    "ask_treatment",    # Phương pháp điều trị
    "ask_medication",   # Thông tin thuốc / hoạt chất
    "ask_routine",      # Skincare routine hàng ngày
    "ask_safety",       # Tác dụng phụ, chống chỉ định
    "ask_comparison",   # So sánh phương pháp / sản phẩm
    "ask_when_doctor",  # Khi nào cần gặp bác sĩ
    "ask_general",      # Định nghĩa, thông tin chung
]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str


class QASample(BaseModel):
    """One conversational Q&A pair in ChatML format, derived from a crawled doc.

    `messages` is the training signal — matches the format expected by
    Axolotl (sharegpt), LLaMA-Factory, and Unsloth out-of-the-box.
    """
    model_config = ConfigDict(extra="forbid")
    id: str
    messages: list[ChatMessage]
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    entity_type: Literal[
        "active_ingredient", "medication", "condition", "procedure",
        "product_class", "anatomy",
    ]
    name_vi: str
    name_en: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    description: str
    contraindications: list[str] = Field(default_factory=list)
    related_chunk_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
