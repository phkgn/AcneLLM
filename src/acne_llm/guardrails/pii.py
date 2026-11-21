"""Phat hien va che PII trong text nguoi dung.

Truoc day file ten `ood_detector.py` va chua ca class OodDetector (phat hien
cau ngoai domain bang embedding). Class do bi xoa o Phase 4: `di.py` truyen
enable_ood=False nen no chua tung chay mot lan nao trong production, va viec
quyet dinh pham vi gio thuoc ve intaker/SemanticRouter.

Con lai dung mot viec: che so dien thoai / email / CMND truoc khi ghi audit log.
"""
from __future__ import annotations
import re


_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # CMND / CCCD: 9 hoặc 12 chữ số
    (re.compile(r"\b\d{9}\b|\b\d{12}\b"), "[ID_MASKED]"),
    # Số điện thoại VN: 03x, 07x, 08x, 09x, 0[2-9]x (10 số) hoặc +84...
    (re.compile(r"\b(?:\+84|0)(?:[3-9]\d{8}|[1-9]\d{8})\b"), "[PHONE_MASKED]"),
    # Email
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[EMAIL_MASKED]"),
    # Địa chỉ: số nhà + tên đường (heuristic)
    (re.compile(
        r"\b\d{1,4}[/\-]?\d{0,4}\s+"
        r"(?:đường|phố|ngõ|hẻm|quận|phường|xã|huyện|tỉnh|tp\.?|thành phố)\b",
        re.IGNORECASE | re.UNICODE,
    ), "[ADDRESS_MASKED]"),
    # Số tài khoản ngân hàng (12–19 chữ số liên tiếp)
    (re.compile(r"\b\d{12,19}\b"), "[ACCOUNT_MASKED]"),
]


def mask_pii(text: str) -> str:
    """Trả về text đã mask PII. Dùng khi ghi log, KHÔNG dùng để từ chối."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def contains_pii(text: str) -> bool:
    """Kiểm tra nhanh text có PII không (để log cảnh báo)."""
    return any(p.search(text) for p, _ in _PII_PATTERNS)


# ─── OOD Detector ──────────────────────────────────────────────────────────

# Seed queries đại diện "acne domain" — dùng để build centroid khi không
