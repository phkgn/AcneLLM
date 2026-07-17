from __future__ import annotations

import numpy as np

from evaluation.metrics.grounding import GroundingScorer, normalize_grounding_text


class _FakeEmbedder:
    """Tiny deterministic semantic map; no model/network needed in unit tests."""

    _vectors = {
        "benzoyl peroxide giup giam mun viem": [1.0, 0.0, 0.0],
        "bpo co the ho tro cac ton thuong mun bi viem": [0.98, 0.02, 0.0],
        "uong nuoc chanh se chua khoi mun sau mot dem": [0.0, 1.0, 0.0],
        "khong co bang chung rang socola luon gay mun": [0.0, 0.0, 1.0],
        "socola luon gay mun": [0.0, 0.0, 1.0],
    }

    def _embed(self, text: str) -> np.ndarray:
        key = normalize_grounding_text(text)
        value = self._vectors.get(key, [0.2, 0.2, 0.2])
        vector = np.asarray(value, dtype=float)
        return vector / np.linalg.norm(vector)

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._embed(text) for text in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)


def _score(answer: str, context: str, threshold: float = 0.8) -> dict:
    scorer = GroundingScorer(embedder=_FakeEmbedder(), threshold=threshold)
    return scorer.score(answer=answer, contexts=[context])


def test_grounding_accepts_direct_quote() -> None:
    result = _score(
        "Benzoyl peroxide giúp giảm mụn viêm.",
        "Hướng dẫn: Benzoyl peroxide giúp giảm mụn viêm.",
    )

    assert result["grounded_sentence_rate"] == 1.0
    assert result["unsupported_sentences"] == []


def test_grounding_accepts_semantic_paraphrase() -> None:
    result = _score(
        "BPO có thể hỗ trợ các tổn thương mụn bị viêm.",
        "Benzoyl peroxide giúp giảm mụn viêm.",
    )

    assert result["grounded_sentence_rate"] == 1.0


def test_grounding_rejects_hallucinated_claim() -> None:
    result = _score(
        "Uống nước chanh sẽ chữa khỏi mụn sau một đêm.",
        "Benzoyl peroxide giúp giảm mụn viêm.",
    )

    assert result["grounded_sentence_rate"] == 0.0
    assert result["unsupported_sentences"] == [
        "Uống nước chanh sẽ chữa khỏi mụn sau một đêm."
    ]


def test_grounding_normalization_preserves_medical_numbers_and_ranges() -> None:
    normalized = normalize_grounding_text(
        "Bôi adapalene 0.1% rồi chờ 15–20 phút; không phải 01%."
    )

    assert "0.1%" in normalized
    assert "15-20" in normalized
    assert "01%" in normalized


def test_grounding_excludes_disclaimer_question_and_greeting_from_denominator() -> None:
    result = _score(
        "Mức độ: nhẹ\nLoại mụn chính: mụn viêm\nChào bạn! Bạn có đang mang thai không? Thông tin này không thay thế chẩn đoán của bác sĩ.",
        "Benzoyl peroxide giúp giảm mụn viêm.",
    )

    assert result["eligible_sentence_count"] == 0
    assert result["grounded_sentence_rate"] is None


def test_myth_refutation_is_a_documented_similarity_limitation() -> None:
    result = _score(
        "Socola luôn gây mụn.",
        "Không có bằng chứng rằng socola luôn gây mụn.",
    )

    # Lexical/embedding similarity cannot reliably distinguish a claim from its
    # negation. Keep this explicit until an NLI/refutation-aware metric is added.
    assert result["grounded_sentence_rate"] == 1.0
    assert "negation_or_refutation" in result["limitations"]
