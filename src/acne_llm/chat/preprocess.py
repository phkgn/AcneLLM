"""Lightweight cleanup for free-form chat input.

This module intentionally does not remove emoji or medical punctuation such as
%, /, +, ., :, or parentheses. It only normalizes text enough for downstream
regex extraction and guardrails to see the same words the user typed.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD_JOINER_RE = re.compile(r"(?<=\w)_(?=\w)")
_REPEATED_PUNCT_RE = re.compile(r"([!?.,])\1{2,}")

_WHITESPACE_RE = re.compile(r"\s+")

@dataclass(frozen=True)
class PreparedText:
    clean_text: str
    clean_text_no_accent: str
    teencode_replaced: list[str]


def preprocess_user_text(text: str) -> str:
    """Normalize user text without deleting medically meaningful symbols."""
    normalized = unicodedata.normalize("NFC", text or "")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = _CONTROL_RE.sub(" ", normalized)
    normalized = _WORD_JOINER_RE.sub(" ", normalized)
    normalized = _REPEATED_PUNCT_RE.sub(r"\1\1", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()


def strip_accents(text: str) -> str:
    """Return a no-accent version of Vietnamese text for scalable regex matching."""
    normalized = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D")



# ponytail: expand_teencode_for_retrieval + bang teencode da bi xoa. Caller cuoi
# cung la build_retrieval_query_from_user, cung bi xoa cung dot. Duong retrieval
# hien tai (build_current_turn_query) dung nguyen van luot hien tai, va intaker
# duoc train tren teencode tho nen mo rong o runtime tao train/serve skew.


def prepare_user_text(text: str) -> PreparedText:
    """Sanitize hostile characters only; leave wording to the model.

    Teencode expansion was removed: intaker được train trên 110 mẫu teencode
    thô ("ko", "k", "vs"), nên mở rộng ở runtime tạo train/serve skew — và
    word-joiner phía trên còn tách "BT-Cortin" thành mồi cho nó.
    """
    clean_text = preprocess_user_text(text)
    return PreparedText(
        clean_text=clean_text,
        clean_text_no_accent=strip_accents(clean_text),
        teencode_replaced=[],
    )


def light_normalize(message: str) -> str:
    """Normalize tối thiểu cho LLM: NFC + bỏ control chars nguy hiểm.

    Giữ nguyên dấu câu, emoji, emphasis (!!!), whitespace tự nhiên.
    Không collapse repeated punctuation, không lowercase.
    """
    text = unicodedata.normalize("NFC", message)
    # Bỏ invisible/control chars; giữ punctuation và whitespace người dùng gõ.
    text = _ZERO_WIDTH_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return text.strip()
