"""Chuẩn hoá text + phát hiện trùng lặp cho datagen.

Trích từ `evaluation/datasets/generate_drafts.py` (đã xóa cùng refactor eval về
4 khâu). `datagen/gates.py` chỉ dùng 5 ký hiệu trong số 2.213 dòng của file đó,
nên chúng chuyển về đây — datagen tự sở hữu thứ mình dùng, eval không còn dính.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt, giữ ký tự gốc."""
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def normalized_tokens(text: str, *, accentless: bool = False) -> list[str]:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    if accentless:
        text = strip_diacritics(text)
    return TOKEN_RE.findall(text)


def normalized_text(text: str, *, accentless: bool = False) -> str:
    return " ".join(normalized_tokens(text, accentless=accentless))


def iter_ngrams(tokens: Sequence[str], n: int) -> Iterator[str]:
    if n <= 0:
        raise ValueError("ngram size phải > 0")
    for index in range(len(tokens) - n + 1):
        yield " ".join(tokens[index:index + n])


@dataclass
class ContaminationHit:
    kind: str
    mode: str
    overlap_count: int
    query_ngram_count: int
    overlap_ratio: float
    matched_ngrams: list[str]
    source_file: str
    source_line: int
    source_excerpt: str


class DuplicateGuard:
    """Loại trùng tuyệt đối và trùng cao theo Jaccard trong draft sinh ra."""

    def __init__(self, threshold: float = 0.88):
        if not 0 < threshold <= 1:
            raise ValueError("near duplicate threshold phải trong (0, 1]")
        self.threshold = threshold
        self._entries: list[tuple[str, str, set[str]]] = []
        self._exact: dict[str, list[str]] = {}

    def add(self, sample_id: str, text: str) -> None:
        normalized = normalized_text(text, accentless=True)
        self._entries.append((sample_id, normalized, set(normalized.split())))
        self._exact.setdefault(normalized, []).append(sample_id)

    def check(
        self,
        text: str,
        *,
        ignore_sample_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        ignored = ignore_sample_ids or set()
        normalized = normalized_text(text, accentless=True)
        exact_ids = [
            sample_id for sample_id in self._exact.get(normalized, [])
            if sample_id not in ignored
        ]
        if exact_ids:
            return {
                "kind": "exact_internal",
                "matched_sample_id": exact_ids[0],
                "score": 1.0,
            }
        tokens = set(normalized.split())
        if not tokens:
            return {"kind": "empty_normalized_query", "score": 1.0}
        # ponytail: quét O(n²) trên toàn bộ draft đã thêm. Bộ draft cỡ nghìn mẫu
        # nên chấp nhận được; đổi sang MinHash/LSH nếu vượt ~10k mẫu.
        best_id = ""
        best_score = 0.0
        for sample_id, _, existing_tokens in self._entries:
            if sample_id in ignored:
                continue
            union = tokens | existing_tokens
            score = len(tokens & existing_tokens) / len(union) if union else 1.0
            if score > best_score:
                best_id, best_score = sample_id, score
        if best_score >= self.threshold:
            return {
                "kind": "near_internal",
                "matched_sample_id": best_id,
                "score": round(best_score, 6),
            }
        return None


def demo() -> None:
    assert normalized_text("Mụn Viêm!", accentless=True) == "mun viem"
    assert list(iter_ngrams(["a", "b", "c"], 2)) == ["a b", "b c"]
    guard = DuplicateGuard(threshold=0.8)
    guard.add("s1", "mụn viêm ở cằm")
    assert guard.check("mun viem o cam")["kind"] == "exact_internal"
    assert guard.check("trị nám da mặt") is None
    print("contamination demo OK")


if __name__ == "__main__":
    demo()
