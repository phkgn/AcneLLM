from acne_llm.rag.reranker import Reranker
from acne_llm.schemas import RetrievedChunk, RetrievalOutput


class _FakeCrossEncoder:
    def __init__(self):
        self.calls = []

    def predict(self, pairs, show_progress_bar=False, batch_size=16):
        self.calls.append((pairs, show_progress_bar, batch_size))
        return [float(i + 1) for i, _ in enumerate(pairs)]


def test_reranker_batches_and_caches_scores():
    model = _FakeCrossEncoder()
    reranker = Reranker(lazy=True, batch_size=4, cache_size=16)
    reranker._model = model
    retrieval = RetrievalOutput(
        query="q",
        chunks=[
            RetrievedChunk(chunk_id="c1", source="s", text="one", score=0.1, metadata={}),
            RetrievedChunk(chunk_id="c2", source="s", text="two", score=0.1, metadata={}),
        ],
    )

    first = reranker.rerank("mụn viêm", retrieval, top_k=2)
    second = reranker.rerank("mụn viêm", retrieval, top_k=2)

    assert [c.chunk_id for c in first.chunks] == ["c2", "c1"]
    assert [c.chunk_id for c in second.chunks] == ["c2", "c1"]
    assert len(model.calls) == 1
    assert model.calls[0][2] == 4
