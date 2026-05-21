"""Lightweight cleanup for free-form chat input.

This module intentionally does not remove emoji or medical punctuation such as
%, /, +, ., :, or parentheses. It only normalizes text enough for downstream
regex extraction and guardrails to see the same words the user typed.
"""
from __future__ import annotations

import re
import unicodedata


_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WORD_JOINER_RE = re.compile(r"(?<=\w)[_-](?=\w)")
_REPEATED_PUNCT_RE = re.compile(r"([!?.,])\1{2,}")
_WHITESPACE_RE = re.compile(r"\s+")


def preprocess_user_text(text: str) -> str:
    """Normalize user text without deleting medically meaningful symbols."""
    normalized = unicodedata.normalize("NFC", text or "")
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = _CONTROL_RE.sub(" ", normalized)
    normalized = _WORD_JOINER_RE.sub(" ", normalized)
    normalized = _REPEATED_PUNCT_RE.sub(r"\1\1", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
