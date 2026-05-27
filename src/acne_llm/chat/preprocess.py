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
_WORD_JOINER_RE = re.compile(r"(?<=\w)[_-](?=\w)")
_REPEATED_PUNCT_RE = re.compile(r"([!?.,])\1{2,}")
_WHITESPACE_RE = re.compile(r"\s+")

_TEENCODE_MAP: dict[str, str] = {
    "dc": "được",
    "ko": "không",
    "vs": "với",
    "sp": "sản phẩm",
    "xit": "xịt",
    "bt": "bình thường",
    "bh": "bây giờ",
}
_TEENCODE_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(k) for k in sorted(_TEENCODE_MAP, key=len, reverse=True)) + r")(?!\w)",
    flags=re.IGNORECASE,
)


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


def normalize_teencode(text: str) -> tuple[str, list[str]]:
    """Expand common Vietnamese teencode tokens with word-boundary matching."""
    replaced: list[str] = []
    seen: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1).lower()
        if token not in seen:
            seen.add(token)
            replaced.append(token)
        return _TEENCODE_MAP[token]

    normalized = _TEENCODE_RE.sub(_replace, text or "")
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized, replaced


def prepare_user_text(text: str) -> PreparedText:
    """Preprocess, expand teencode, and create a no-accent extraction twin."""
    clean_text = preprocess_user_text(text)
    clean_text, replaced = normalize_teencode(clean_text)
    return PreparedText(
        clean_text=clean_text,
        clean_text_no_accent=strip_accents(clean_text),
        teencode_replaced=replaced,
    )
