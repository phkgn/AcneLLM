from evaluation.unit.eval_context_sensitivity import (
    CANARY_TOKEN,
    add_in_memory_canary,
    char_ngram_similarity,
    summarize_results,
)
from acne_llm.schemas import RetrievalOutput, RetrievedChunk


def _retrieval() -> RetrievalOutput:
    return RetrievalOutput(
        query="q",
        chunks=[
            RetrievedChunk(
                chunk_id="c1",
                source="s",
                text="Benzoyl peroxide hỗ trợ mụn viêm.",
                score=0.9,
                metadata={"title": "t", "source": "s"},
            )
        ],
    )


def test_canary_injection_is_copy_only_and_never_mutates_retrieval() -> None:
    original = _retrieval()

    injected = add_in_memory_canary(original)

    assert [chunk.chunk_id for chunk in original.chunks] == ["c1"]
    assert CANARY_TOKEN not in original.chunks[0].text
    assert injected.chunks[0].chunk_id == "eval-only-canary"
    assert CANARY_TOKEN in injected.chunks[0].text


def test_char_ngram_similarity_has_expected_extremes() -> None:
    assert char_ngram_similarity("mụn viêm", "mụn viêm") == 1.0
    assert char_ngram_similarity("abc", "xyz") == 0.0


def test_context_sensitivity_summary_reports_distances_and_red_flag() -> None:
    summary = summarize_results([
        {
            "canary_adopted": True,
            "embedding_cosine": 0.9,
            "char_ngram_similarity": 0.7,
        },
        {
            "canary_adopted": False,
            "embedding_cosine": 0.7,
            "char_ngram_similarity": 0.5,
        },
    ], low_sensitivity_threshold=0.25)

    assert summary["canary_adoption_rate"] == 0.5
    assert summary["embedding_distance_mean"] == 0.2
    assert summary["char_ngram_distance_mean"] == 0.4
    assert summary["context_swap_sensitivity_mean"] == 0.3
    assert summary["low_context_sensitivity_red_flag"] is False
