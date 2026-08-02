from acne_llm.chat._retrieval import merge_retrieval_outputs as merge_chat_outputs
from acne_llm.schemas import RetrievedChunk, RetrievalOutput


def _chunk(chunk_id: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source="test",
        text=f"text {chunk_id}",
        score=score,
        metadata={"title": chunk_id},
    )


def _output(ids: list[str]) -> RetrievalOutput:
    return RetrievalOutput(
        query="q",
        chunks=[_chunk(chunk_id, score=10 - i) for i, chunk_id in enumerate(ids)],
        retrieval_mode="hybrid",
        num_chunks=len(ids),
    )


def test_chat_merge_uses_same_rrf_order():
    merged = merge_chat_outputs(
        [_output(["a", "b", "c"]), _output(["b", "d", "a"])],
        combined_query="q1\nq2",
    )

    assert [chunk.chunk_id for chunk in merged.chunks][:2] == ["b", "a"]
    assert len({chunk.chunk_id for chunk in merged.chunks}) == len(merged.chunks)
    assert merged.query == "q1\nq2"
    assert merged.avg_score > 0
    assert max(chunk.score for chunk in merged.chunks) == 1.0
