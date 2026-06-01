"""Small rule-based language helpers used before the final LLM call."""
from __future__ import annotations

import re
from typing import Literal


_VI_CHARS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")


def detect_language_heuristic(text: str) -> Literal["vi", "en", "mixed", "unknown"]:
    """Detect Vietnamese/English with cheap lexical rules, no LLM call."""
    lowered = text.lower()
    has_vi = any(ch in _VI_CHARS for ch in lowered)
    words = re.findall(r"[a-zA-Z]+", lowered)
    en_hits = sum(
        1 for w in words
        if w in {
            "acne", "pimple", "pimples", "blackhead", "whitehead", "comedone",
            "papule", "pustule", "nodule", "cyst", "chin", "cheek", "forehead",
            "benzoyl", "peroxide", "salicylic", "retinoid", "isotretinoin",
        }
    )
    if has_vi and en_hits:
        return "mixed"
    if has_vi:
        return "vi"
    if en_hits >= 1 or re.search(r"\b(i|my|have|can|use|treatment|skin)\b", lowered):
        return "en"
    return "unknown"
