"""Fuzzy matching cho intake extraction — thay viec liet ke bien the tay.

Chi giu lexicon CANONICAL nho; tang chuan hoa (bo dau + teencode) lo bien the,
fuzzy lo phan duoi: sai chinh ta, viet tat, brand la. Similarity = confidence.
Khong phu thuoc LLM. Chi rapidfuzz (deterministic).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz


@dataclass(frozen=True)
class FuzzyHit:
    canonical: str
    similarity: float
    query: str


def _tokens(text: str, max_ngram: int = 3) -> list[str]:
    words = [w for w in text.split() if w]
    grams: list[str] = []
    for n in range(1, max_ngram + 1):
        for i in range(len(words) - n + 1):
            grams.append(" ".join(words[i : i + n]))
    return grams


_LENGTH_GATE = 0.6


def best_match(query: str, canonicals: tuple[str, ...], *, scorer=fuzz.ratio) -> "FuzzyHit | None":
    """Canonical gan nhat voi mot cum query. fuzz.ratio + length-gate cung."""
    if not query or not canonicals:
        return None
    q = query.strip().lower()
    if not q:
        return None
    best_c = None
    best_s = -1.0
    for c in canonicals:
        if not c or not c.strip():
            continue
        lq, lc = len(q), len(c)
        if lc == 0 or lq == 0:
            continue
        if min(lq, lc) / max(lq, lc) < _LENGTH_GATE:
            continue
        s = scorer(q, c) / 100.0
        if s > best_s:
            best_s, best_c = s, c
    if best_c is None:
        return None
    return FuzzyHit(canonical=best_c, similarity=best_s, query=query)


def find_in_text(text: str, canonicals: tuple[str, ...], *, accept: float, review: float, max_ngram: int = 3) -> "list[FuzzyHit]":
    """Return accepted matches; ``review`` is only a lower prefilter threshold.

    Args:
        accept: Auto-accept threshold (high confidence, no manual review needed)
        review: Ignore weaker candidates; this function returns no review list
    """
    if not text or not canonicals:
        return []
    best_per_canonical: dict[str, FuzzyHit] = {}
    for gram in _tokens(text, max_ngram=max_ngram):
        hit = best_match(gram, canonicals)
        if hit is None:
            continue
        # Prefilter weak candidates before retaining only accept-level hits.
        if hit.similarity < review:
            continue
        prev = best_per_canonical.get(hit.canonical)
        if prev is None or hit.similarity > prev.similarity:
            best_per_canonical[hit.canonical] = hit
    hits = sorted(best_per_canonical.values(), key=lambda h: h.similarity, reverse=True)
    # Only return hits >= accept threshold (high confidence)
    return [h for h in hits if h.similarity >= accept]


@lru_cache(maxsize=256)
def _as_tuple(canonicals: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(c.strip().lower() for c in canonicals if c and c.strip()))


def classify(query: str, canonicals: tuple[str, ...]) -> "FuzzyHit | None":
    return best_match(query, _as_tuple(canonicals))
