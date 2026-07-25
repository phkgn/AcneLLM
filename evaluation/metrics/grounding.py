"""Deterministic, eval-only sentence grounding metric.

Each eligible answer sentence is matched against the exact/fallback source
text by character n-gram coverage and embedding cosine; the stronger signal
wins.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


DEFAULT_GROUNDING_THRESHOLD = 0.50
_DECIMAL_DOT = "__grounding_decimal_dot__"
_ABBREVIATIONS = ("bs.", "ths.", "ts.", "pgs.", "gs.", "vd.")
_DISCLAIMER_PATTERNS = (
    "khong thay the chan doan",
    "khong thay the tu van",
    "chi mang tinh tham khao",
    "thong tin mang tinh tham khao",
)
_GREETING_PREFIXES = (
    "chao ban",
    "xin chao",
    "cam on ban",
    "rat vui duoc ho tro",
)
_METADATA_PREFIXES = ("muc do ", "loai mun chinh ")


class EmbedderLike(Protocol):
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def normalize_grounding_text(text: str) -> str:
    """Normalize Vietnamese text while preserving decimal/range evidence."""
    value = unicodedata.normalize("NFD", str(text or "").casefold())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d")
    value = re.sub(r"[‐‑‒–—−]", "-", value)
    value = re.sub(r"[^a-z0-9\s.%\-]", " ", value)
    value = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def split_vietnamese_sentences(text: str) -> list[str]:
    """Bounded Vietnamese-aware splitter for generated prose and JSON flattening."""
    protected = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    protected = re.sub(r"(?<=\d)\.(?=\d)", _DECIMAL_DOT, protected)
    for abbreviation in _ABBREVIATIONS:
        pattern = re.compile(re.escape(abbreviation), re.IGNORECASE)
        protected = pattern.sub(abbreviation.replace(".", _DECIMAL_DOT), protected)

    fragments = re.split(r"(?<=[.!?])\s+|\n+|\s+-\s+", protected)
    sentences: list[str] = []
    for fragment in fragments:
        restored = fragment.replace(_DECIMAL_DOT, ".").strip()
        restored = re.sub(r"^[-*•]\s*", "", restored).strip()
        if restored:
            sentences.append(restored)
    return sentences


def _is_eligible_sentence(sentence: str) -> bool:
    stripped = sentence.strip()
    if not stripped or stripped.endswith("?"):
        return False
    normalized = normalize_grounding_text(stripped)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in _GREETING_PREFIXES):
        return False
    if any(pattern in normalized for pattern in _DISCLAIMER_PATTERNS):
        return False
    metadata_probe = normalized + " "
    if any(metadata_probe.startswith(prefix) for prefix in _METADATA_PREFIXES):
        return False
    return True


def _char_ngram_dice(claim: str, context_unit: str, n: int = 3) -> float:
    claim_norm = normalize_grounding_text(claim)
    context_norm = normalize_grounding_text(context_unit)
    if not claim_norm or not context_norm:
        return 0.0
    if claim_norm in context_norm:
        return 1.0
    if len(claim_norm) < n:
        return float(claim_norm in context_norm)
    claim_ngrams = {
        claim_norm[index:index + n] for index in range(len(claim_norm) - n + 1)
    }
    context_ngrams = {
        context_norm[index:index + n]
        for index in range(max(0, len(context_norm) - n + 1))
    }
    return 2 * len(claim_ngrams & context_ngrams) / max(
        len(claim_ngrams) + len(context_ngrams), 1
    )


def _lexical_context_score(claim: str, context: str) -> float:
    # Compare with local context sentences, not a whole multi-paragraph chunk;
    # whole-chunk recall over-rewards generic words in unsupported compound claims.
    units = split_vietnamese_sentences(context) or [context]
    return max((_char_ngram_dice(claim, unit) for unit in units), default=0.0)


def _cosines(query: np.ndarray, passages: np.ndarray) -> np.ndarray:
    query_array = np.asarray(query, dtype=float).reshape(-1)
    passage_array = np.asarray(passages, dtype=float)
    if passage_array.ndim == 1:
        passage_array = passage_array.reshape(1, -1)
    q_norm = np.linalg.norm(query_array)
    p_norms = np.linalg.norm(passage_array, axis=1)
    denominator = p_norms * q_norm
    return np.divide(
        passage_array @ query_array,
        denominator,
        out=np.zeros_like(p_norms, dtype=float),
        where=denominator > 0,
    )


@dataclass
class GroundingScorer:
    embedder: EmbedderLike | None = None
    threshold: float = DEFAULT_GROUNDING_THRESHOLD

    def score(self, answer: str, contexts: list[str]) -> dict[str, Any]:
        clean_contexts = [str(context).strip() for context in contexts if str(context).strip()]
        sentences = split_vietnamese_sentences(answer)
        eligible = [sentence for sentence in sentences if _is_eligible_sentence(sentence)]
        result: dict[str, Any] = {
            "grounded_sentence_rate": None,
            "unsupported_sentences": [],
            "eligible_sentence_count": len(eligible),
            "grounded_sentence_count": 0,
            "threshold": self.threshold,
            "combination": "max(char_3gram_dice_by_context_sentence, embedding_cosine)",
            "sentence_scores": [],
            "limitations": ["negation_or_refutation"],
        }
        if not eligible or not clean_contexts:
            if eligible and not clean_contexts:
                result["unsupported_sentences"] = eligible
            return result

        context_embeddings = None
        if self.embedder is not None:
            context_embeddings = self.embedder.embed_passages(clean_contexts)

        grounded_count = 0
        unsupported: list[str] = []
        for sentence in eligible:
            lexical_scores = [
                _lexical_context_score(sentence, context) for context in clean_contexts
            ]
            semantic_scores = [0.0] * len(clean_contexts)
            if self.embedder is not None and context_embeddings is not None:
                semantic_scores = _cosines(
                    self.embedder.embed_query(sentence), context_embeddings
                ).tolist()
            combined = [
                max(lexical, semantic)
                for lexical, semantic in zip(lexical_scores, semantic_scores)
            ]
            best_index = int(np.argmax(combined))
            best_score = float(combined[best_index])
            grounded = best_score >= self.threshold
            grounded_count += int(grounded)
            if not grounded:
                unsupported.append(sentence)
            result["sentence_scores"].append({
                "sentence": sentence,
                "grounded": grounded,
                "score": round(best_score, 4),
                "lexical_score": round(float(lexical_scores[best_index]), 4),
                "semantic_score": round(float(semantic_scores[best_index]), 4),
                "best_context_index": best_index,
            })

        result["grounded_sentence_count"] = grounded_count
        result["grounded_sentence_rate"] = round(grounded_count / len(eligible), 4)
        result["unsupported_sentences"] = unsupported
        return result

    def score_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return self.score(
            answer=str(record.get("answer") or ""),
            contexts=contexts_from_record(record),
        )


def contexts_from_record(record: dict[str, Any]) -> list[str]:
    """Prefer exact rendered context; fall back to trace chunk snapshots."""
    trace = record.get("trace") or {}
    exact = trace.get("faithfulness_context")
    if isinstance(exact, str) and exact.strip():
        blocks = re.split(r"\n\s*---\s*\n", exact)
        parsed = [block.strip() for block in blocks if block.strip()]
        return parsed or [exact.strip()]

    chunks = trace.get("context_chunks") or []
    return [
        str(chunk.get("text") or "").strip()
        for chunk in chunks
        if isinstance(chunk, dict) and str(chunk.get("text") or "").strip()
    ]
