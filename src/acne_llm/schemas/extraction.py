"""Confidence-carrying extraction result for rule-based intake.

Mọi extractor rule-based (skin_type, products, severity, intent...) trả về
``FieldResult`` thay vì ``value | None``. Confidence được SUY RA từ chính quá
trình match (method + similarity + điều chỉnh ngữ cảnh), không phải ML/calibration.

Khung này KHÔNG đổi schema ngoài (UserInput): nó là kênh phụ nội bộ để
intent_router biết "chắc đến đâu" và degrade an toàn (hỏi lại) khi
confidence thấp — thuần rule, không gọi LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeAlias, TypeVar

T = TypeVar("T")

# Cách trích được giá trị — để audit/debug và để gán confidence base.
Method: TypeAlias = Literal["exact", "pattern", "fuzzy", "fallback", "llm", "none"]

# Confidence base theo method (heuristic khởi điểm; golden set sẽ tinh chỉnh).
METHOD_BASE_CONFIDENCE: dict[Method, float] = {
    "exact": 0.95,
    "pattern": 0.85,
    "fuzzy": 0.80,     # thường bị ghi đè bằng similarity thực tế
    "fallback": 0.45,
    "llm": 0.0,        # LLM extractor luôn truyền confidence do model cung cấp
    "none": 0.0,
}


def clamp01(x: float) -> float:
    """Kẹp về [0, 1]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass(frozen=True)
class FieldResult(Generic[T]):
    """Kết quả trích một field, kèm độ tin cậy.

    Attributes
    ----------
    value:
        Giá trị đã chuẩn hoá (None nếu không trích được).
    confidence:
        Độ tin cậy trong [0, 1]. Với method="fuzzy" thường bằng similarity.
    method:
        Cách trích được — exact/pattern/fuzzy/fallback/none.
    evidence:
        Span gốc đã khớp, để truy vết.
    """

    value: T | None
    confidence: float = 0.0
    method: Method = "none"
    evidence: str = ""

    def __post_init__(self) -> None:
        # frozen dataclass → dùng object.__setattr__ để kẹp confidence.
        object.__setattr__(self, "confidence", clamp01(self.confidence))

    def is_confident(self, threshold: float) -> bool:
        """True khi có giá trị VÀ confidence đạt ngưỡng cho trước."""
        return self.value is not None and self.confidence >= threshold

    @classmethod
    def none(cls) -> "FieldResult[T]":
        """Kết quả rỗng chuẩn — không trích được gì."""
        return cls(value=None, confidence=0.0, method="none", evidence="")

    @classmethod
    def make(
        cls,
        value: T | None,
        method: Method,
        *,
        confidence: float | None = None,
        evidence: str = "",
        adjust: float = 0.0,
    ) -> "FieldResult[T]":
        """Tạo FieldResult, tự suy confidence từ method nếu không truyền tay.

        - confidence: ép giá trị cụ thể (vd similarity của fuzzy).
        - adjust: cộng/trừ điều chỉnh ngữ cảnh (phủ định −, pronoun +...).
        """
        if value is None:
            return cls.none()
        base = METHOD_BASE_CONFIDENCE.get(method, 0.0) if confidence is None else confidence
        return cls(
            value=value,
            confidence=clamp01(base + adjust),
            method=method,
            evidence=evidence,
        )


@dataclass(frozen=True)
class ListFieldResult(Generic[T]):
    """Kết quả trích field dạng DANH SÁCH (products, medications, lesions...).

    Giữ confidence per-item để completeness/audit đọc, đồng thời expose
    ``values`` (list giá trị) cho code ráp UserInput như cũ.
    """

    items: tuple[FieldResult[T], ...] = field(default_factory=tuple)

    @property
    def values(self) -> list[T]:
        return [it.value for it in self.items if it.value is not None]

    @property
    def max_confidence(self) -> float:
        return max((it.confidence for it in self.items), default=0.0)

    def confident_values(self, threshold: float) -> list[T]:
        """Chỉ những item đạt ngưỡng confidence."""
        return [it.value for it in self.items if it.is_confident(threshold)]

    @classmethod
    def empty(cls) -> "ListFieldResult[T]":
        return cls(items=())


@dataclass
class ExtractionConfidence:
    """Map field -> FieldResult, kênh phụ cho completeness/router."""

    skin_type: FieldResult[str] = field(default_factory=FieldResult.none)
    sex: FieldResult[str] = field(default_factory=FieldResult.none)
    age: FieldResult[int] = field(default_factory=FieldResult.none)
    duration_weeks: FieldResult[int] = field(default_factory=FieldResult.none)
    is_pregnant: FieldResult[bool] = field(default_factory=FieldResult.none)
    is_breastfeeding: FieldResult[bool] = field(default_factory=FieldResult.none)
    inflammation: FieldResult[str] = field(default_factory=FieldResult.none)
    lesion_types: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    distribution: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    products: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    medications: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    allergies: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    scarring_signs: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    hormonal_factors: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    treatment_goals: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)
    red_flags: ListFieldResult[str] = field(default_factory=ListFieldResult.empty)

    def field(self, name: str) -> FieldResult | ListFieldResult:
        return getattr(self, name)
