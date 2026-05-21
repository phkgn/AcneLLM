"""Knowledge base schemas."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


SourceType = Literal[
    "nice_guideline",       # NICE Clinical Guidelines (UK)
    "aad_guideline",        # AAD Acne Guidelines (US)
    "jid_paper",            # Journal of Investigative Dermatology
    "pubmed_review",        # PubMed systematic review / meta-analysis
    "clinical_textbook",    # Textbook lâm sàng da liễu
    "vi_medical_site",      # Trang y tế tiếng Việt uy tín
    "en_medical_site",      # Trang y tế tiếng Anh uy tín (Healthline, WebMD, Mayo...)
    "forum_post",           # Diễn đàn / forum
    "blog",                 # Blog cá nhân / thương mại
    "unknown",              # Chưa phân loại
]


def _tokens(value: str | list[str] | tuple[str, ...] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value).lower()
    return str(value).lower()


def infer_source_type(
    *,
    source_name: str = "",
    domain: str = "",
    url: str = "",
    tags: str | list[str] | tuple[str, ...] | None = None,
    categories: str | list[str] | tuple[str, ...] | None = None,
) -> SourceType:
    """Infer granular source type for legacy chunks without source_type metadata."""
    haystack = " ".join([
        source_name.lower(),
        domain.lower(),
        url.lower(),
        _tokens(tags),
        _tokens(categories),
    ])

    if "nice" in haystack or "ng198" in haystack:
        return "nice_guideline"
    if "aad" in haystack or "american academy of dermatology" in haystack:
        return "aad_guideline"
    if "journal of investigative dermatology" in haystack or "jid" in haystack:
        return "jid_paper"
    if "pubmed" in haystack or "ncbi.nlm.nih.gov/pubmed" in haystack:
        return "pubmed_review"
    if any(t in haystack for t in ("bookshelf", "textbook", "openstax")):
        return "clinical_textbook"
    if any(t in haystack for t in ("forum", "reddit", "quora", "webtretho")):
        return "forum_post"
    if any(t in haystack for t in ("blog", "wordpress", "blogspot", "medium.com", "incidecoder")):
        return "blog"
    # Trang y tế tiếng Việt uy tín
    _VI_MEDICAL = (
        "vinmec", "hellobacsi", "tam anh", "tamanh",
        "benhvien", "bvdl", "bvdermato",
        "suckhoedoisong", "suckhoe", "youmed",
        "vnexpress", "tuoitre", "dantri",
        "yhocvietnam", "bacsy", "nhathuoc",
        "hospital", "medical", "phongkham", "clinics",
    )
    if any(t in haystack for t in _VI_MEDICAL):
        return "vi_medical_site"
    # Trang y tế tiếng Anh uy tín
    _EN_MEDICAL = (
        "healthline", "webmd", "mayoclinic", "mayo clinic",
        "msdmanuals", "msd manual", "medlineplus", "medline",
        "clevelandclinic", "cleveland clinic",
        "medicalnewstoday", "medical news today",
        "skinsight", "dermnetnz", "dermnet",
        "verywellhealth", "verywell",
    )
    if any(t in haystack for t in _EN_MEDICAL):
        return "en_medical_site"
    return "unknown"


class SourceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    source_name: str
    source_type: SourceType = "unknown"
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
    source_type: SourceType = "unknown"
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
    Axolotl (sharegpt), LLaMA-Factory, and Unsloth output format.
    """
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityRecord(BaseModel):
    """Structured knowledge entity -- hoat chat, thuoc, benh ly, thu thuat."""
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    entity_type: Literal[
        "active_ingredient", "medication", "condition",
        "procedure", "product_class", "anatomy",
    ]
    name_vi: str
    name_en: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    contraindications: list[str] = Field(default_factory=list)
    related_chunk_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
