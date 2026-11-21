"""Diễn đạt độ chắc của extraction thành lời cho prompt (đường chính).

Dùng mỗi lượt trong ``orchestrator.prepare_chat_turn`` bất kể intake đi
đường LLM hay đường rule fallback.
"""
from __future__ import annotations

from ..schemas.extraction import ExtractionConfidence


# ---------------------------------------------------------------------------
# Điểm conf tổng + hedging text cho prompt.
# Chấp nhận extract KHÔNG bao giờ đúng 100% → thay vì giả vờ chắc chắn,
# truyền độ chắc BẰNG LỜI (không số) vào prompt để model thận trọng đúng chỗ.
# ---------------------------------------------------------------------------

# Trọng số field bắt buộc cho điểm tổng. Field an toàn nặng hơn.
_OVERALL_WEIGHTS = {
    "is_pregnant": 1.8,
    "is_breastfeeding": 1.8,
    "allergies": 1.5,
    "inflammation": 1.5,   # severity ảnh hưởng mạnh tới mức độ tư vấn
    "lesion_types": 1.2,
    "distribution": 1.0,
    "scarring_signs": 1.0,
    "hormonal_factors": 0.8,
    "skin_type": 0.8,
    "treatment_goals": 0.5,
}

# Nhãn người-đọc cho từng field (để hedging tự nhiên).
_FIELD_LABELS_VI = {
    "skin_type": "loại da",
    "inflammation": "mức độ viêm",
    "lesion_types": "loại tổn thương",
    "distribution": "vị trí mụn",
    "products": "sản phẩm đang dùng",
    "medications": "thuốc đang dùng",
    "is_pregnant": "tình trạng mang thai",
    "is_breastfeeding": "tình trạng cho con bú",
    "allergies": "dị ứng/kích ứng",
    "scarring_signs": "sẹo hoặc thâm sau mụn",
    "hormonal_factors": "yếu tố nội tiết/khởi phát",
    "treatment_goals": "mục tiêu điều trị",
}


def _field_conf(ec: "ExtractionConfidence", name: str) -> float:
    """Lấy confidence đại diện của một field (0.0 nếu rỗng)."""
    fr = getattr(ec, name, None)
    if fr is None:
        return 0.0
    if hasattr(fr, "max_confidence"):   # ListFieldResult
        return fr.max_confidence
    return fr.confidence


def overall_confidence(ec: "ExtractionConfidence") -> float:
    """Điểm conf TỔNG = trung bình có trọng số các field bắt buộc CÓ giá trị.

    Chỉ tính field thực sự trích được (conf > 0) — field rỗng không kéo điểm
    xuống (vì 'không có' khác 'có nhưng không chắc'). Trả 0.0 nếu chưa có field nào.
    """
    num = den = 0.0
    for name, w in _OVERALL_WEIGHTS.items():
        c = _field_conf(ec, name)
        if c > 0.0:
            num += w * c
            den += w
    return round(num / den, 3) if den > 0 else 0.0


def build_confidence_hint(
    ec: "ExtractionConfidence",
    *,
    field_threshold: float,
    overall: float | None = None,
) -> str:
    """Sinh hedging BẰNG LỜI cho prompt (không số).

    - Field có giá trị nhưng conf < ngưỡng → liệt kê là 'chưa chắc'.
    - Một câu giọng điệu theo điểm tổng.
    Trả chuỗi rỗng nếu mọi thứ đều chắc (không cần hedging).
    """
    low_fields: list[str] = []
    for name in (
        "is_pregnant", "is_breastfeeding", "allergies",
        "inflammation", "lesion_types", "distribution", "skin_type",
        "scarring_signs", "hormonal_factors", "treatment_goals",
    ):
        fr = getattr(ec, name, None)
        if fr is None:
            continue
        # có giá trị?
        has_val = bool(getattr(fr, "values", None)) if hasattr(fr, "values") else (fr.value is not None)
        if not has_val:
            continue
        conf = _field_conf(ec, name)
        if conf < field_threshold:
            low_fields.append(_FIELD_LABELS_VI.get(name, name))

    if overall is None:
        overall = overall_confidence(ec)

    parts: list[str] = []
    if low_fields:
        parts.append(
            "Một số thông tin được suy đoán tự động và CHƯA CHẮC CHẮN: "
            + ", ".join(low_fields)
            + ". Nếu các thông tin này có vẻ mâu thuẫn với mô tả của người dùng, "
            "hãy hỏi lại để xác nhận thay vì khẳng định chắc chắn."
        )

    # Giọng điệu theo điểm tổng (chỉ thêm khi đã có field nào đó).
    if overall > 0.0:
        if overall < 0.6:
            parts.append(
                "Thông tin trích xuất còn HẠN CHẾ — hãy tư vấn thận trọng, "
                "nói rõ đây là nhận định sơ bộ dựa trên thông tin chưa đầy đủ, "
                "và khuyến khích người dùng bổ sung hoặc gặp bác sĩ nếu cần."
            )
        # overall cao → không thêm gì, giữ giọng tư vấn bình thường.

    return " ".join(parts)
